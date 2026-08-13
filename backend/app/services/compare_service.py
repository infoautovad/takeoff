from __future__ import annotations

import json
from difflib import SequenceMatcher, unified_diff

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis import DocumentAnalysis
from app.models.boq import BOQ
from app.models.comparison import ComparisonResult
from app.models.document import Document
from app.services.processing import load_findings


def compare_boqs(db: Session, *, project_id: int, left_boq_id: int, right_boq_id: int, user_id: int) -> ComparisonResult:
    left = db.scalar(select(BOQ).options(selectinload(BOQ.items)).where(BOQ.id == left_boq_id, BOQ.project_id == project_id))
    right = db.scalar(select(BOQ).options(selectinload(BOQ.items)).where(BOQ.id == right_boq_id, BOQ.project_id == project_id))
    if not left or not right:
        raise ValueError("Both BOQs must belong to this project")

    left_map = {i.description.lower().strip(): i for i in left.items}
    right_map = {i.description.lower().strip(): i for i in right.items}

    missing = []
    extra = []
    qty_diff = []
    unit_mismatch = []

    for key, li in left_map.items():
        ri = right_map.get(key)
        if not ri:
            missing.append({"description": li.description, "quantity": float(li.quantity), "unit": li.unit})
            continue
        if li.unit.lower() != ri.unit.lower():
            unit_mismatch.append({"description": li.description, "left_unit": li.unit, "right_unit": ri.unit})
        if float(li.quantity) != float(ri.quantity):
            qty_diff.append(
                {
                    "description": li.description,
                    "left_qty": float(li.quantity),
                    "right_qty": float(ri.quantity),
                    "delta": float(ri.quantity) - float(li.quantity),
                }
            )

    for key, ri in right_map.items():
        if key not in left_map:
            extra.append({"description": ri.description, "quantity": float(ri.quantity), "unit": ri.unit})

    summary = (
        f"Compared BOQ v{left.version} vs v{right.version}: "
        f"{len(missing)} missing, {len(extra)} extra, {len(qty_diff)} quantity diffs, {len(unit_mismatch)} unit mismatches."
    )
    payload = {
        "missing_in_right": missing,
        "extra_in_right": extra,
        "quantity_differences": qty_diff,
        "unit_mismatches": unit_mismatch,
    }
    row = ComparisonResult(
        project_id=project_id,
        comparison_type="boq",
        left_label=f"BOQ v{left.version}",
        right_label=f"BOQ v{right.version}",
        summary=summary,
        result_json=json.dumps(payload, ensure_ascii=True),
        created_by=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def compare_drawings(
    db: Session,
    *,
    project_id: int,
    left_document_id: int,
    right_document_id: int,
    user_id: int,
) -> ComparisonResult:
    left_doc = db.get(Document, left_document_id)
    right_doc = db.get(Document, right_document_id)
    if not left_doc or not right_doc or left_doc.project_id != project_id or right_doc.project_id != project_id:
        raise ValueError("Both documents must belong to this project")

    left_analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_id == left_document_id))
    right_analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_id == right_document_id))
    left_text = (left_analysis.extracted_text if left_analysis else "") or ""
    right_text = (right_analysis.extracted_text if right_analysis else "") or ""
    if not left_text or not right_text:
        raise ValueError("Analyze both documents before comparing revisions")

    ratio = SequenceMatcher(None, left_text, right_text).ratio()
    diff_lines = list(
        unified_diff(
            left_text.splitlines()[:400],
            right_text.splitlines()[:400],
            fromfile=left_doc.original_filename,
            tofile=right_doc.original_filename,
            lineterm="",
        )
    )[:200]

    left_items = {i.get("description", "").lower(): i for i in load_findings(left_analysis).get("items") or []}
    right_items = {i.get("description", "").lower(): i for i in load_findings(right_analysis).get("items") or []}
    added = [right_items[k] for k in right_items.keys() - left_items.keys()]
    removed = [left_items[k] for k in left_items.keys() - right_items.keys()]
    changed = []
    for k in left_items.keys() & right_items.keys():
        if left_items[k].get("quantity") != right_items[k].get("quantity"):
            changed.append({"description": k, "from": left_items[k].get("quantity"), "to": right_items[k].get("quantity")})

    summary = (
        f"Drawing text similarity {ratio:.1%}. "
        f"Quantity items: {len(added)} added, {len(removed)} removed, {len(changed)} changed."
    )
    payload = {
        "similarity": round(ratio, 4),
        "added_items": added,
        "removed_items": removed,
        "changed_quantities": changed,
        "diff_excerpt": diff_lines,
    }
    row = ComparisonResult(
        project_id=project_id,
        comparison_type="drawing",
        left_label=left_doc.original_filename,
        right_label=right_doc.original_filename,
        summary=summary,
        result_json=json.dumps(payload, ensure_ascii=True),
        created_by=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
