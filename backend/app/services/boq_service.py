"""Build BOQ records from document analyses and export Excel."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO, StringIO
import csv

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis import DocumentAnalysis
from app.models.boq import BOQ, BOQItem, BOQItemStatus, BOQStatus
from app.models.cad import CadModel
from app.models.project import Project
from app.services.bid_service import build_boq_items_from_template, get_active_template
from app.services.csi_mapper import enrich_quantity_item
from app.services.processing import load_findings

# AutoVAD standard: confidence below this → Engineer Review
CONFIDENCE_VERIFIED_THRESHOLD = 97

BOQ_EXPORT_HEADERS = [
    "Item Number",
    "Standard Bid Item Number",
    "Item Description",
    "Unit",
    "Quantity",
    "Cost",
    "Total Cost",
    "AI Confidence",
    "Status",
    "Source",
    "Calculation Method",
]


def _money2(value: Decimal | float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _qty2(value: Decimal | float | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def standard_bid_item_number(item: BOQItem) -> str:
    """Agency/state bid code from template; empty when AutoVAD default / unmapped."""
    if item.bid_template_line_id and item.item_code:
        return str(item.item_code)
    return ""


def status_label_for_item(item: BOQItem) -> str:
    """Display status for AutoVAD BOQ standard."""
    if item.status == BOQItemStatus.VERIFIED:
        return "Verified"
    if item.status in {BOQItemStatus.NEEDS_REVIEW, BOQItemStatus.DRAFT}:
        return "Engineer Review"
    if item.status == BOQItemStatus.APPROVED:
        return "Verified"
    return "Engineer Review"


def resolve_item_status(confidence: float | None, *, force_review: bool = False) -> BOQItemStatus:
    if force_review:
        return BOQItemStatus.NEEDS_REVIEW
    if confidence is not None and float(confidence) >= CONFIDENCE_VERIFIED_THRESHOLD:
        return BOQItemStatus.VERIFIED
    return BOQItemStatus.NEEDS_REVIEW


def _merge_item(merged: dict[str, dict], item: dict) -> None:
    item = enrich_quantity_item(item)
    code_key = (item.get("csi_code") or item.get("item_code") or "").strip().lower()
    key = f"{code_key}|{(item.get('description') or '').strip().lower()}|{(item.get('unit') or '').strip().lower()}"
    if not item.get("description"):
        return
    if key not in merged:
        merged[key] = dict(item)
        return
    existing = merged[key]
    try:
        existing_qty = Decimal(str(existing.get("quantity") or 0))
        new_qty = Decimal(str(item.get("quantity") or 0))
        existing_conf = Decimal(str(existing.get("confidence") or 0))
        new_conf = Decimal(str(item.get("confidence") or 0))
    except Exception:
        return
    if new_conf > existing_conf:
        merged[key] = dict(item)
    elif new_conf == existing_conf and new_qty > existing_qty:
        existing["quantity"] = float(new_qty)


def generate_boq_for_project(
    db: Session,
    project: Project,
    user_id: int,
    *,
    document_ids: list[int] | None = None,
) -> BOQ:
    """Build a BOQ from all analyses/CAD, or only the given document_ids (per-file BOQ)."""
    analyses = list(
        db.scalars(select(DocumentAnalysis).where(DocumentAnalysis.project_id == project.id)).all()
    )
    cad_models = list(db.scalars(select(CadModel).where(CadModel.project_id == project.id)).all())

    scope_ids = {int(i) for i in document_ids} if document_ids else None
    if scope_ids is not None:
        analyses = [a for a in analyses if a.document_id in scope_ids]
        cad_models = [c for c in cad_models if c.document_id in scope_ids]

    active = get_active_template(db, project.id)
    has_template = bool(active and active.lines)

    if not analyses and not cad_models:
        if scope_ids:
            raise ValueError(
                "No analysis for the selected file(s). Run Analyze (PDF) or Process CAD (DWG/DXF) on that file first."
            )
        raise ValueError("No analyzed documents or CAD models. Upload design plans and run Analyze first.")

    merged: dict[str, dict] = {}
    for analysis in analyses:
        findings = load_findings(analysis)
        for item in findings.get("items") or []:
            payload = dict(item)
            payload.setdefault("source_document_id", analysis.document_id)
            _merge_item(merged, payload)

    for cad in cad_models:
        if not cad.quantities_json:
            continue
        import json

        try:
            qty_items = json.loads(cad.quantities_json)
        except json.JSONDecodeError:
            qty_items = []
        for item in qty_items:
            payload = dict(item)
            payload["source_document_id"] = cad.document_id
            payload["calculation_method"] = payload.get("calculation_method") or "CAD geometry takeoff"
            _merge_item(merged, payload)

    extracted = list(merged.values())

    if not extracted:
        raise ValueError(
            "No quantities found from the selected file(s). "
            "Run Analyze / Process CAD first, then Generate BOQ again."
            if scope_ids
            else "No quantities found from design plans. Upload PDF/DWG and run Analyze / Process CAD first."
        )

    if has_template:
        # Only bid items evidenced in the plans, aligned to the active agency template.
        items_list = build_boq_items_from_template(extracted, list(active.lines))
        matched = sum(
            1
            for i in items_list
            if i.get("bid_template_line_id") and float(i.get("bid_match_confidence") or 0) > 0
        )
        unmapped = sum(1 for i in items_list if i.get("bid_match_method") == "unmapped")
        notes_extra = (
            f" Matched plan takeoff to bid template '{active.name}' "
            f"({matched} template item(s); {unmapped} unmapped takeoff item(s)). "
            "Unused bid-list lines were omitted."
        )
        if not items_list:
            raise ValueError(
                "Could not match any plan quantities to the active bid template. "
                "Re-analyze plans after uploading the template, or check descriptions/units."
            )
    else:
        # AutoVAD default: CSI-enriched takeoff BOQ
        items_list = [enrich_quantity_item(dict(item)) for item in extracted]
        notes_extra = (
            " Generated with AutoVAD default CSI schedule (no bid template uploaded)."
            " Upload a bid list so Generate BOQ maps only the bid items needed for this project."
        )

    from app.models.document import Document

    scope_label = ""
    if scope_ids:
        docs = list(db.scalars(select(Document).where(Document.id.in_(scope_ids))).all())
        names = [d.original_filename for d in docs]
        if len(names) == 1:
            scope_label = f" · {names[0]}"
        elif names:
            scope_label = f" · {len(names)} files"
        notes_extra += f" Scope: selected document_id(s) {sorted(scope_ids)}."

    latest_version = db.scalar(select(func.max(BOQ.version)).where(BOQ.project_id == project.id)) or 0
    boq = BOQ(
        project_id=project.id,
        title=f"{project.name} - BOQ v{latest_version + 1}{scope_label}",
        version=latest_version + 1,
        status=BOQStatus.AI_GENERATED,
        currency="USD",
        notes=(
            "Generated from document AI + CAD with CSI codes, units, and confidence scores."
            + notes_extra
        ),
        created_by=user_id,
    )
    db.add(boq)
    db.flush()

    for idx, item in enumerate(items_list, start=1):
        conf = item.get("confidence")
        conf_f = float(conf) if conf is not None else None
        force_review = item.get("bid_match_method") in {"unmatched", "unmapped"} or (
            bool(item.get("bid_template_line_id")) and float(item.get("quantity") or 0) == 0
        )
        status = resolve_item_status(conf_f, force_review=force_review)
        qty = _qty2(item.get("quantity"))
        rate = _money2(item["rate"]) if item.get("rate") is not None else None
        amount = _money2(qty * rate) if rate is not None else None
        unit = str(item.get("unit") or "UNIT").strip().upper() or "UNIT"
        db.add(
            BOQItem(
                boq_id=boq.id,
                item_number=str(idx),
                item_code=item.get("item_code"),
                csi_code=item.get("csi_code"),
                description=str(item.get("description")),
                category=item.get("category"),
                unit=unit,
                quantity=qty,
                rate=rate,
                amount=amount,
                source_document_id=item.get("source_document_id"),
                source_page=item.get("source_page"),
                source_reference=item.get("source_reference"),
                calculation_method=item.get("calculation_method"),
                confidence=Decimal(str(conf)) if conf is not None else None,
                bid_template_line_id=item.get("bid_template_line_id"),
                bid_match_confidence=item.get("bid_match_confidence"),
                status=status,
            )
        )

    db.commit()
    return db.scalar(
        select(BOQ).options(selectinload(BOQ.items)).where(BOQ.id == boq.id)
    )  # type: ignore[return-value]


def list_project_boqs(db: Session, project_id: int) -> list[BOQ]:
    return list(
        db.scalars(
            select(BOQ)
            .options(selectinload(BOQ.items))
            .where(BOQ.project_id == project_id)
            .order_by(BOQ.version.desc())
        ).all()
    )


def get_boq(db: Session, boq_id: int) -> BOQ | None:
    return db.scalar(select(BOQ).options(selectinload(BOQ.items)).where(BOQ.id == boq_id))


def _sorted_boq_items(boq: BOQ) -> list[BOQItem]:
    return sorted(
        boq.items,
        key=lambda x: int(x.item_number) if str(x.item_number).isdigit() else 0,
    )


def export_boq_csv(boq: BOQ) -> bytes:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(BOQ_EXPORT_HEADERS)
    for item in _sorted_boq_items(boq):
        qty = _qty2(item.quantity)
        cost = _money2(item.rate)
        total = _money2(qty * cost) if cost is not None else None
        writer.writerow(
            [
                item.item_number,
                standard_bid_item_number(item),
                item.description,
                (item.unit or "UNIT").upper(),
                f"{qty:.2f}",
                f"{cost:.2f}" if cost is not None else "",
                f"{total:.2f}" if total is not None else "",
                f"{float(item.confidence):.2f}" if item.confidence is not None else "",
                status_label_for_item(item),
                item.source_reference or "",
                item.calculation_method or "",
            ]
        )
    return buffer.getvalue().encode("utf-8")


def export_boq_excel(boq: BOQ) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"

    headers = BOQ_EXPORT_HEADERS
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="0D1F19")
    header_font = Font(color="D9FF43", bold=True)
    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(1, col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    items = _sorted_boq_items(boq)
    for row_idx, item in enumerate(items, start=2):
        qty = float(_qty2(item.quantity))
        cost = _money2(item.rate)
        status = status_label_for_item(item)

        ws.cell(row_idx, 1, item.item_number)
        ws.cell(row_idx, 2, standard_bid_item_number(item))
        ws.cell(row_idx, 3, item.description)
        ws.cell(row_idx, 4, (item.unit or "UNIT").upper())

        qty_cell = ws.cell(row_idx, 5, qty)
        qty_cell.number_format = "0.00"

        if cost is not None:
            cost_cell = ws.cell(row_idx, 6, float(cost))
            cost_cell.number_format = "0.00"
            total_cell = ws.cell(row_idx, 7, f"=E{row_idx}*F{row_idx}")
            total_cell.number_format = "0.00"
        else:
            ws.cell(row_idx, 6, "")
            ws.cell(row_idx, 7, "")

        if item.confidence is not None:
            conf_cell = ws.cell(row_idx, 8, round(float(item.confidence), 2))
            conf_cell.number_format = "0.00"
        else:
            ws.cell(row_idx, 8, "")

        status_cell = ws.cell(row_idx, 9, status)
        if status == "Verified":
            status_cell.font = Font(color="006100", bold=True)
            status_cell.fill = PatternFill("solid", fgColor="C6EFCE")
        else:
            status_cell.font = Font(color="9C0006", bold=True)
            status_cell.fill = PatternFill("solid", fgColor="FFC7CE")

        ws.cell(row_idx, 10, item.source_reference or "")
        ws.cell(row_idx, 11, item.calculation_method or "")

    last_row = max(2, len(items) + 1)
    status_dv = DataValidation(
        type="list",
        formula1='"Verified,Engineer Review"',
        allow_blank=False,
        showDropDown=False,
        showErrorMessage=True,
        errorTitle="Invalid status",
        error="Choose Verified or Engineer Review",
    )
    status_dv.add(f"I2:I{last_row}")
    ws.add_data_validation(status_dv)

    green_fill = PatternFill("solid", fgColor="C6EFCE")
    green_font = Font(color="006100", bold=True)
    red_fill = PatternFill("solid", fgColor="FFC7CE")
    red_font = Font(color="9C0006", bold=True)
    ws.conditional_formatting.add(
        f"I2:I{last_row}",
        FormulaRule(formula=['$I2="Verified"'], fill=green_fill, font=green_font),
    )
    ws.conditional_formatting.add(
        f"I2:I{last_row}",
        FormulaRule(formula=['$I2="Engineer Review"'], fill=red_fill, font=red_font),
    )

    widths = [12, 22, 42, 10, 12, 12, 12, 14, 16, 28, 28]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    meta = wb.create_sheet("Meta")
    meta.append(["BOQ Title", boq.title])
    meta.append(["Version", boq.version])
    meta.append(["Status", boq.status.value])
    meta.append(["Currency", boq.currency])
    meta.append(["Notes", boq.notes or ""])
    meta.append(["Generated by", "AutoVAD"])
    meta.append(
        [
            "Template rule",
            "User bid template when active; otherwise AutoVAD default CSI schedule",
        ]
    )
    meta.append(
        [
            "Status rule",
            f"Verified when AI confidence >= {CONFIDENCE_VERIFIED_THRESHOLD}; else Engineer Review",
        ]
    )
    meta.append(["Columns", ", ".join(BOQ_EXPORT_HEADERS)])

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
