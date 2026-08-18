"""Orchestrates document processing and analysis persistence."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import DocumentAnalysis
from app.models.cad import CadJobStatus, CadModel
from app.models.document import Document, ProcessingStatus
from app.services.ai_analysis import analyze_content
from app.services.bid_service import get_active_template
from app.services.cad.engine import detect_cad_format, process_cad_document
from app.services.extractors import extract_file
from app.services.storage import storage_service


def _bid_catalog_for_project(db: Session, project_id: int) -> list[dict]:
    active = get_active_template(db, project_id)
    if not active or not active.lines:
        return []
    return [
        {
            "item_code": line.item_code,
            "csi_code": line.csi_code,
            "description": line.description,
            "unit": line.unit,
            "line_number": line.line_number,
        }
        for line in sorted(active.lines, key=lambda x: (x.sort_order, x.id))
    ]


def process_document(db: Session, document: Document) -> DocumentAnalysis:
    """Analyze a document. CAD/DWG/DXF/LandXML files use the CAD engine."""
    if detect_cad_format(document):
        return _process_cad_as_analysis(db, document)

    document.processing_status = ProcessingStatus.PROCESSING
    document.error_message = None
    db.commit()

    try:
        path = storage_service.resolve_local_path(document.storage_key)
        if not path.exists():
            raise FileNotFoundError("Stored file not found")

        content = extract_file(path, document.document_type)
        document.page_count = content.page_count

        result = analyze_content(
            filename=document.original_filename,
            content=content,
            document_id=document.id,
            bid_catalog=_bid_catalog_for_project(db, document.project_id),
            file_path=path,
        )

        findings: dict = {
            "facts": result.get("facts") or [],
            "items": result.get("items") or [],
            "needs_review": result.get("needs_review", False),
        }
        if result.get("vision_pages"):
            findings["vision_pages"] = result["vision_pages"]
        if result.get("vision_coverage"):
            findings["vision_coverage"] = result["vision_coverage"]
        if result.get("notes"):
            findings["notes"] = result["notes"]

        analysis = _upsert_analysis(
            db,
            document,
            engine=result.get("engine", "heuristic"),
            summary=result.get("summary"),
            extracted_text=(content.text or "")[:200000],
            findings=findings,
        )
        document.processing_status = ProcessingStatus.COMPLETED
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as exc:
        document.processing_status = ProcessingStatus.FAILED
        document.error_message = str(exc)
        db.commit()
        raise


def _process_cad_as_analysis(db: Session, document: Document) -> DocumentAnalysis:
    """Run CAD Intelligence Engine and mirror quantities into DocumentAnalysis for BOQ/chat."""
    model = process_cad_document(db, document)
    db.refresh(model)

    qty_items: list[dict] = []
    if model.quantities_json:
        try:
            qty_items = json.loads(model.quantities_json) or []
        except json.JSONDecodeError:
            qty_items = []

    facts = [
        f"CAD format: {model.source_format.value}",
        f"CAD engine: {model.engine}",
        f"CAD status: {model.status.value}",
        f"Quantity candidates: {len(qty_items)}",
    ]
    if model.error_message:
        facts.append(f"CAD error: {model.error_message}")

    needs_review = True
    if model.status == CadJobStatus.QUANTIFIED and qty_items:
        needs_review = any(float(i.get("confidence") or 0) < 90 for i in qty_items)
    elif model.status in {CadJobStatus.NEEDS_AUTODESK, CadJobStatus.FAILED}:
        needs_review = True

    summary = model.summary or f"CAD processing for '{document.original_filename}' → {model.status.value}."
    if model.status == CadJobStatus.FAILED:
        summary = (
            f"CAD processing failed for '{document.original_filename}'. "
            f"{model.error_message or 'Unknown error'}. "
            "Retry Process CAD, or export DWG → DXF for local parsing."
        )
    elif model.status == CadJobStatus.NEEDS_AUTODESK:
        summary = (
            f"DWG '{document.original_filename}' needs Autodesk APS credentials "
            "or a DXF/LandXML export for local takeoff."
        )
    elif qty_items:
        summary = (
            f"CAD takeoff for '{document.original_filename}': "
            f"{len(qty_items)} quantity item(s) ready for Estimate Of Quantities generation and engineer review."
        )

    analysis = _upsert_analysis(
        db,
        document,
        engine=model.engine or "cad_engine",
        summary=summary,
        extracted_text=summary,
        findings={
            "facts": facts,
            "items": qty_items,
            "needs_review": needs_review,
            "cad_model_id": model.id,
            "cad_status": model.status.value,
        },
    )
    # Keep document status aligned with CAD outcome (process_cad_document already set it).
    if model.status == CadJobStatus.FAILED:
        document.processing_status = ProcessingStatus.FAILED
        document.error_message = model.error_message
    else:
        document.processing_status = ProcessingStatus.COMPLETED
        document.error_message = None
    db.commit()
    db.refresh(analysis)
    return analysis


def _upsert_analysis(
    db: Session,
    document: Document,
    *,
    engine: str,
    summary: str | None,
    extracted_text: str,
    findings: dict,
) -> DocumentAnalysis:
    analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_id == document.id))
    if not analysis:
        analysis = DocumentAnalysis(document_id=document.id, project_id=document.project_id)
        db.add(analysis)
    analysis.engine = engine
    analysis.summary = summary
    analysis.extracted_text = extracted_text
    analysis.findings_json = json.dumps(findings, ensure_ascii=True)
    db.flush()
    return analysis


def process_project_documents(db: Session, project_id: int) -> list[DocumentAnalysis]:
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.asc())
        ).all()
    )
    results: list[DocumentAnalysis] = []
    for doc in documents:
        try:
            results.append(process_document(db, doc))
        except Exception:
            # Keep going so one bad file doesn't block the project batch.
            continue
    return results


def load_findings(analysis: DocumentAnalysis | None) -> dict:
    if not analysis or not analysis.findings_json:
        return {"facts": [], "items": [], "needs_review": False}
    try:
        return json.loads(analysis.findings_json)
    except json.JSONDecodeError:
        return {"facts": [], "items": [], "needs_review": False}


def get_project_cad_models(db: Session, project_id: int) -> list[CadModel]:
    return list(db.scalars(select(CadModel).where(CadModel.project_id == project_id)).all())
