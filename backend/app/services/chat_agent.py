"""Agentic project chat — detect intents and execute website actions after login."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.boq import BOQ
from app.models.cad import CadModel
from app.models.document import Document
from app.models.project import Project
from app.services.bid_service import get_active_template, list_templates, map_boq_to_template
from app.services.boq_service import generate_boq_for_project, list_project_boqs
from app.services.cad.engine import detect_cad_format, process_cad_document
from app.services.cost_service import generate_cost_estimate, list_sor
from app.services.processing import process_document, process_project_documents


@dataclass
class PlannedAction:
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    action: str
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


# Intent keywords → action
_ACTION_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "export_boq_excel",
        [
            r"\b(update|export|download|generate|create|make|give|send)\b.*\b(boq|bill of quantities).*\b(excel|xlsx|spreadsheet)\b",
            r"\b(excel|xlsx)\b.*\b(boq|bill of quantities)\b",
            r"\bupdate\b.*\b(my\s+)?(boq\s+)?excel\b",
            r"\bboq\b.*\bexcel\b",
            r"\bexcel\b.*\bboq\b",
        ],
    ),
    (
        "export_boq_csv",
        [
            r"\b(export|download|generate)\b.*\b(boq|bill of quantities).*\bcsv\b",
            r"\bcsv\b.*\b(boq|bill of quantities)\b",
        ],
    ),
    (
        "generate_boq",
        [
            r"\b(generate|create|build|make|refresh|update)\b.*\b(boq|bill of quantities)\b",
            r"\bboq\b.*\b(generate|create|refresh|update)\b",
        ],
    ),
    (
        "analyze_all",
        [
            r"\b(analyze|analyse|process|extract)\b.*\b(all\s+)?(documents?|files?|plans?|pdfs?)\b",
            r"\brun\b.*\b(ai\s+)?analysis\b",
            r"\banalyze\b.*\bproject\b",
        ],
    ),
    (
        "analyze_one",
        [
            r"\b(analyze|analyse|process|extract)\b.*\b(this|the|file|document|pdf|plan)\b",
            r"\banalyze\b.+\.(pdf|xlsx|xls|csv|dxf|dwg|xml)\b",
        ],
    ),
    (
        "process_cad",
        [
            r"\b(process|run|parse)\b.*\b(cad|dxf|dwg|landxml|civil\s*3d)\b",
            r"\bcad\b.*\b(process|takeoff|quantit)",
        ],
    ),
    (
        "map_bid",
        [
            r"\b(map|match)\b.*\b(bid|template|bid\s*list)\b",
            r"\bbid\b.*\b(map|match|template)\b",
        ],
    ),
    (
        "estimate_cost",
        [
            r"\b(estimate|calculate|compute)\b.*\b(cost|price|amount)\b",
            r"\bcost\b.*\b(estimate|estimation)\b",
            r"\brun\b.*\bcost\b",
        ],
    ),
    (
        "project_status",
        [
            r"\b(status|summary|overview|what('s| is) ready|progress)\b",
            r"\bwhat\s+(do\s+i\s+have|files|documents|boq)\b",
        ],
    ),
    (
        "help",
        [
            r"\b(what can you do|help|commands|capabilities)\b",
        ],
    ),
]


def plan_actions(question: str, documents: list[Document]) -> list[PlannedAction]:
    q = question.strip()
    q_low = q.lower()
    planned: list[PlannedAction] = []

    # Filename-targeted analyze
    matched_docs = _match_documents(q_low, documents)
    for pattern_group in _ACTION_PATTERNS:
        name, patterns = pattern_group
        if any(re.search(p, q_low) for p in patterns):
            if name == "analyze_one":
                if matched_docs:
                    planned.append(PlannedAction("analyze_one", {"document_id": matched_docs[0].id, "filename": matched_docs[0].original_filename}))
                else:
                    planned.append(PlannedAction("analyze_all", {}))
            elif name == "export_boq_excel":
                # Refresh BOQ first so Excel is up to date
                planned.append(PlannedAction("generate_boq", {}))
                planned.append(PlannedAction("export_boq_excel", {}))
            elif name == "export_boq_csv":
                planned.append(PlannedAction("generate_boq", {}))
                planned.append(PlannedAction("export_boq_csv", {}))
            else:
                planned.append(PlannedAction(name, {}))
            break

    # If user said analyze + a filename but no pattern caught, still analyze that file
    if not planned and matched_docs and re.search(r"\b(analyze|analyse|process|extract)\b", q_low):
        planned.append(
            PlannedAction(
                "analyze_one",
                {"document_id": matched_docs[0].id, "filename": matched_docs[0].original_filename},
            )
        )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[PlannedAction] = []
    for a in planned:
        key = f"{a.name}:{a.params.get('document_id', '')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(a)
    return unique


def execute_actions(
    db: Session,
    *,
    project: Project,
    user_id: int,
    actions: list[PlannedAction],
) -> list[ActionResult]:
    results: list[ActionResult] = []
    for action in actions:
        try:
            results.append(_execute_one(db, project=project, user_id=user_id, action=action))
        except Exception as exc:
            results.append(ActionResult(action=action.name, ok=False, message=str(exc)))
    return results


def format_action_answer(results: list[ActionResult], *, question: str) -> tuple[str, list[dict[str, Any]]]:
    if not results:
        return "", []

    lines = ["**Done.** I ran this on your project:"]
    sources: list[dict[str, Any]] = []
    for r in results:
        icon = "✓" if r.ok else "✗"
        lines.append(f"- {icon} **{r.action.replace('_', ' ')}**: {r.message}")
        if r.data:
            sources.append({"type": "action", "action": r.action, "ok": r.ok, **r.data})
            if r.data.get("download"):
                sources.append(
                    {
                        "type": "download",
                        "label": r.data.get("download_label") or "Download",
                        "href": r.data["download"],
                        "filename": r.data.get("filename"),
                    }
                )

    # Extra guidance for excel update requests
    if any(r.action == "export_boq_excel" and r.ok for r in results):
        lines.append("")
        lines.append(
            "Your BOQ Excel is ready — use the **Download Excel** button below "
            "(or BOQ tab → Excel). I can’t edit a file already open on your PC; "
            "download this fresh export instead."
        )

    lines.append("")
    lines.append("Ask another command anytime, e.g. *analyze all files*, *generate BOQ*, *process CAD*, *estimate cost*.")
    return "\n".join(lines), sources


def help_text() -> str:
    return (
        "I can run project actions after you log in. Try:\n"
        "- **Analyze all files** / **Analyze drainage.pdf**\n"
        "- **Generate BOQ**\n"
        "- **Update/export my BOQ Excel** (refreshes BOQ + download link)\n"
        "- **Export BOQ CSV**\n"
        "- **Process CAD** (DXF/DWG/LandXML)\n"
        "- **Map bid template**\n"
        "- **Estimate cost** (needs SOR uploaded)\n"
        "- **Project status**\n\n"
        "You can also ask engineering questions about quantities, CSI, pavement, etc."
    )


def _execute_one(db: Session, *, project: Project, user_id: int, action: PlannedAction) -> ActionResult:
    name = action.name

    if name == "help":
        return ActionResult(action=name, ok=True, message="Listed available chat commands.", data={"help": True})

    if name == "project_status":
        docs = list(db.scalars(select(Document).where(Document.project_id == project.id)).all())
        boqs = list_project_boqs(db, project.id)
        cad = list(db.scalars(select(CadModel).where(CadModel.project_id == project.id)).all())
        templates = list_templates(db, project.id)
        sor = list_sor(db, project.id)
        msg = (
            f"{len(docs)} document(s), {len(boqs)} BOQ version(s), "
            f"{len(cad)} CAD model(s), {len(templates)} bid template(s), {len(sor)} SOR item(s)."
        )
        return ActionResult(
            action=name,
            ok=True,
            message=msg,
            data={
                "documents": len(docs),
                "boqs": len(boqs),
                "cad_models": len(cad),
                "bid_templates": len(templates),
                "sor_items": len(sor),
            },
        )

    if name == "analyze_all":
        docs = list(db.scalars(select(Document).where(Document.project_id == project.id)).all())
        if not docs:
            return ActionResult(action=name, ok=False, message="No documents uploaded yet.")
        analyses = process_project_documents(db, project.id)
        return ActionResult(
            action=name,
            ok=True,
            message=f"Analyzed {len(analyses)}/{len(docs)} document(s).",
            data={"analyzed": len(analyses), "total_documents": len(docs)},
        )

    if name == "analyze_one":
        doc_id = action.params.get("document_id")
        doc = db.get(Document, doc_id) if doc_id else None
        if not doc or doc.project_id != project.id:
            return ActionResult(action=name, ok=False, message="Document not found in this project.")
        analysis = process_document(db, doc)
        import json

        findings = {}
        if analysis.findings_json:
            try:
                findings = json.loads(analysis.findings_json)
            except json.JSONDecodeError:
                findings = {}
        items = findings.get("items") or []
        cad_status = findings.get("cad_status")
        if cad_status == "failed":
            return ActionResult(
                action="process_cad",
                ok=False,
                message=(
                    f"CAD processing failed for '{doc.original_filename}'. "
                    f"{doc.error_message or analysis.summary or 'Unknown error'}"
                ),
                data={
                    "document_id": doc.id,
                    "analysis_id": analysis.id,
                    "items": 0,
                    "engine": analysis.engine,
                    "cad_status": cad_status,
                },
            )
        return ActionResult(
            action="process_cad" if detect_cad_format(doc) else name,
            ok=True,
            message=(
                f"Analyzed '{doc.original_filename}' with {analysis.engine}: "
                f"{len(items)} quantity item(s)"
                + (f" (CAD status: {cad_status})" if cad_status else "")
                + "."
            ),
            data={
                "document_id": doc.id,
                "analysis_id": analysis.id,
                "items": len(items),
                "engine": analysis.engine,
                "cad_status": cad_status,
            },
        )

    if name == "generate_boq":
        boq = generate_boq_for_project(db, project, user_id)
        return ActionResult(
            action=name,
            ok=True,
            message=f"Generated {boq.title} with {len(boq.items)} item(s).",
            data={"boq_id": boq.id, "version": boq.version, "items": len(boq.items)},
        )

    if name in {"export_boq_excel", "export_boq_csv"}:
        boq = db.scalar(
            select(BOQ)
            .options(selectinload(BOQ.items))
            .where(BOQ.project_id == project.id)
            .order_by(BOQ.version.desc())
        )
        if not boq:
            return ActionResult(action=name, ok=False, message="No BOQ found. Generate BOQ first.")
        kind = "excel" if name == "export_boq_excel" else "csv"
        ext = "xlsx" if kind == "excel" else "csv"
        filename = f"AutoVAD_BOQ_v{boq.version}_{project.id}.{ext}"
        return ActionResult(
            action=name,
            ok=True,
            message=f"BOQ v{boq.version} {kind.upper()} is ready for download ({len(boq.items)} items).",
            data={
                "boq_id": boq.id,
                "version": boq.version,
                "download": f"/api/boq/{boq.id}/export/{kind}",
                "download_label": f"Download BOQ {kind.upper()}",
                "filename": filename,
            },
        )

    if name == "process_cad":
        docs = list(db.scalars(select(Document).where(Document.project_id == project.id)).all())
        cad_docs = [d for d in docs if detect_cad_format(d)]
        if not cad_docs:
            return ActionResult(action=name, ok=False, message="No CAD/Civil files (DXF/DWG/LandXML/JSON) in this project.")
        processed = 0
        qty_total = 0
        for doc in cad_docs:
            model = process_cad_document(db, doc)
            processed += 1
            qty_total += len(model.quantities or [])
        return ActionResult(
            action=name,
            ok=True,
            message=f"Processed {processed} CAD file(s), {qty_total} quantity row(s).",
            data={"processed": processed, "quantities": qty_total},
        )

    if name == "map_bid":
        active = get_active_template(db, project.id)
        if not active:
            return ActionResult(action=name, ok=False, message="No active bid template. Upload one in the Bid templates tab first.")
        boq = db.scalar(select(BOQ).where(BOQ.project_id == project.id).order_by(BOQ.version.desc()))
        if not boq:
            return ActionResult(action=name, ok=False, message="No BOQ to map. Generate BOQ first.")
        result = map_boq_to_template(db, boq_id=boq.id, template_id=active.id)
        return ActionResult(
            action=name,
            ok=True,
            message=f"Mapped {result['matched']}/{result['total']} BOQ items to '{active.name}'.",
            data=result,
        )

    if name == "estimate_cost":
        sor = list_sor(db, project.id)
        if not sor:
            return ActionResult(action=name, ok=False, message="Upload a SOR (Schedule of Rates) in the Cost tab first.")
        boq = db.scalar(select(BOQ).where(BOQ.project_id == project.id).order_by(BOQ.version.desc()))
        if not boq:
            return ActionResult(action=name, ok=False, message="No BOQ found. Generate BOQ first.")
        est = generate_cost_estimate(db, project_id=project.id, boq_id=boq.id, user_id=user_id)
        return ActionResult(
            action=name,
            ok=True,
            message=f"Cost estimate total: {est.currency} {float(est.total_amount):,.2f}.",
            data={"estimate_id": est.id, "total_amount": float(est.total_amount), "currency": est.currency},
        )

    return ActionResult(action=name, ok=False, message=f"Unknown action '{name}'.")


def _match_documents(question_low: str, documents: list[Document]) -> list[Document]:
    hits: list[Document] = []
    for doc in documents:
        name = doc.original_filename.lower()
        stem = name.rsplit(".", 1)[0]
        if name in question_low or stem in question_low:
            hits.append(doc)
            continue
        # loose token match on distinctive parts
        tokens = [t for t in re.split(r"[^a-z0-9]+", stem) if len(t) >= 4]
        if tokens and all(t in question_low for t in tokens[:2]):
            hits.append(doc)
    return hits
