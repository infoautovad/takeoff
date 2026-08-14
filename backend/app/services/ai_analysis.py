"""Civil document intelligence: OpenAI when configured, heuristic fallback otherwise.

PDF plans use text/tables PLUS rendered drawing sheets via OpenAI vision so
engineering drawings (not only OCR text) drive BOQ quantities.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.services.extractors import ExtractedContent

CIVIL_PATTERNS: list[tuple[str, str, str, str]] = [
    # description_key, category, unit_hint, regex
    ("GSB", "Pavement", "m3", r"\bGSB\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cu\.?\s*m|cubic\s*meters?)"),
    ("WMM", "Pavement", "m3", r"\bWMM\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cu\.?\s*m|cubic\s*meters?)"),
    ("DBM", "Pavement", "m3", r"\bDBM\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|cu\.?\s*m|cubic\s*meters?)"),
    ("Bituminous Concrete", "Pavement", "m3", r"\b(?:BC|Bituminous\s*Concrete)\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|t|ton|tons?)"),
    ("Asphalt", "Pavement", "m3", r"\bAsphalt\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³|t|ton|tons?)"),
    ("Earthwork Cut", "Earthwork", "m3", r"\b(?:Cut|Excavation)\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³)"),
    ("Earthwork Fill", "Earthwork", "m3", r"\b(?:Fill|Embankment)\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³)"),
    ("Concrete", "Structures", "m3", r"\bConcrete\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m3|m³)"),
    ("Kerb", "Roadside", "m", r"\bKerb(?:ing)?\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m|lm|lin(?:ear)?\s*m)"),
    ("Culvert", "Drainage", "nos", r"\bCulvert(?:s)?\b.*?(\d{1,4})\s*(nos?|no\.?|each|ea)"),
    ("Drainage", "Drainage", "m", r"\bDrain(?:age)?\b.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(m|lm)"),
    ("Road Width", "Geometry", "m", r"\b(?:Road|Carriageway)\s*Width\b.*?(\d{1,2}(?:\.\d+)?)\s*m\b"),
]

ITEM_ALIASES = {
    "gsb": ("GSB", "Pavement", "m3"),
    "granular sub base": ("GSB", "Pavement", "m3"),
    "wmm": ("WMM", "Pavement", "m3"),
    "wet mix macadam": ("WMM", "Pavement", "m3"),
    "dbm": ("DBM", "Pavement", "m3"),
    "dense bituminous macadam": ("DBM", "Pavement", "m3"),
    "bc": ("Bituminous Concrete", "Pavement", "m3"),
    "bituminous concrete": ("Bituminous Concrete", "Pavement", "m3"),
    "asphalt": ("Asphalt", "Pavement", "m3"),
    "kerb": ("Kerb", "Roadside", "m"),
    "curb": ("Kerb", "Roadside", "m"),
    "culvert": ("Culvert", "Drainage", "nos"),
    "concrete": ("Concrete", "Structures", "m3"),
    "excavation": ("Earthwork Cut", "Earthwork", "m3"),
    "cut": ("Earthwork Cut", "Earthwork", "m3"),
    "fill": ("Earthwork Fill", "Earthwork", "m3"),
    "embankment": ("Earthwork Fill", "Earthwork", "m3"),
}


def analyze_content(
    *,
    filename: str,
    content: ExtractedContent,
    document_id: int,
    bid_catalog: list[dict[str, Any]] | None = None,
    file_path: Path | str | None = None,
) -> dict[str, Any]:
    from app.config import get_settings
    from app.services.openai_client import openai_configured

    settings = get_settings()
    path = Path(file_path) if file_path else None

    if openai_configured():
        text_result: dict[str, Any] | None = None
        vision_result: dict[str, Any] | None = None
        errors: list[str] = []

        try:
            text_result = _analyze_with_openai(
                filename=filename,
                content=content,
                document_id=document_id,
                bid_catalog=bid_catalog,
            )
        except Exception as exc:
            errors.append(f"text AI: {exc}")

        # Deterministic pass: water main / utility quantities from plan labels & callouts
        label_result = _analyze_utility_labels(
            filename=filename,
            content=content,
            document_id=document_id,
        )

        if (
            settings.openai_pdf_vision_enabled
            and path
            and path.exists()
            and path.suffix.lower() == ".pdf"
        ):
            try:
                vision_result = _analyze_pdf_drawings_with_vision(
                    filename=filename,
                    content=content,
                    document_id=document_id,
                    pdf_path=path,
                    bid_catalog=bid_catalog,
                    max_pages=settings.openai_vision_max_pages,
                    dpi=settings.openai_vision_dpi,
                    min_score=settings.openai_vision_min_score,
                    force_utility_pages=settings.openai_vision_force_utility_pages,
                    scan_all_pages=settings.openai_vision_scan_all_pages,
                    batch_pages=settings.openai_vision_batch_pages,
                )
            except Exception as exc:
                errors.append(f"drawing vision: {exc}")

        merged_parts = [r for r in (text_result, label_result, vision_result) if r]
        if len(merged_parts) >= 2:
            merged = merged_parts[0]
            for part in merged_parts[1:]:
                merged = _merge_analysis_results(merged, part)
            if errors:
                merged["notes"] = (merged.get("notes") or "") + " | ".join(errors)
            return merged
        if vision_result:
            return vision_result
        if label_result and label_result.get("items"):
            return label_result
        if text_result and text_result.get("items"):
            return text_result
        if text_result:
            return text_result

        heuristic = _analyze_heuristic(filename=filename, content=content, document_id=document_id)
        if errors:
            heuristic["notes"] = f"OpenAI failed ({'; '.join(errors)}); used heuristic fallback."
        return heuristic

    return _analyze_heuristic(filename=filename, content=content, document_id=document_id)


def _analyze_heuristic(*, filename: str, content: ExtractedContent, document_id: int) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1) Structured tables (CSV/Excel/PDF tables)
    for table in content.tables:
        page = table.get("page")
        rows = table.get("rows") or []
        if not rows:
            continue
        header = [c.lower() for c in rows[0]]
        qty_idx = _find_col(header, ["qty", "quantity", "quantities", "qnty"])
        desc_idx = _find_col(header, ["item", "description", "desc", "particular", "material"])
        unit_idx = _find_col(header, ["unit", "uom"])
        code_idx = _find_col(header, ["code", "item code", "item_code"])

        if qty_idx is None and len(header) >= 3:
            # common layout: Item, Unit, Qty
            for i, h in enumerate(header):
                if "unit" in h:
                    unit_idx = i
                if any(k in h for k in ("item", "desc", "material")):
                    desc_idx = i
                if any(k in h for k in ("qty", "quantity")):
                    qty_idx = i
            if qty_idx is None and len(header) >= 3:
                desc_idx, unit_idx, qty_idx = 0, 1, 2

        data_rows = rows[1:] if desc_idx is not None else rows
        for row in data_rows:
            if not row or desc_idx is None or qty_idx is None:
                # try freeform first cell mapping
                joined = " ".join(row).strip()
                if not joined:
                    continue
                mapped = _map_alias(joined)
                qty = _parse_number(row[-1] if row else None)
                if mapped and qty is not None:
                    key = mapped[0].lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(
                        _item(
                            description=mapped[0],
                            category=mapped[1],
                            unit=row[unit_idx] if unit_idx is not None and unit_idx < len(row) and row[unit_idx] else mapped[2],
                            quantity=qty,
                            document_id=document_id,
                            page=page,
                            source=f"{filename}" + (f" - Table p.{page}" if page else " - Table"),
                            method="Extracted from tabular quantity sheet",
                            confidence=92,
                        )
                    )
                continue

            if desc_idx >= len(row) or qty_idx >= len(row):
                continue
            desc = row[desc_idx].strip()
            qty = _parse_number(row[qty_idx])
            if not desc or qty is None:
                continue
            mapped = _map_alias(desc)
            description = mapped[0] if mapped else desc
            category = mapped[1] if mapped else "General"
            unit = (
                row[unit_idx].strip()
                if unit_idx is not None and unit_idx < len(row) and row[unit_idx].strip()
                else (mapped[2] if mapped else "unit")
            )
            code = row[code_idx].strip() if code_idx is not None and code_idx < len(row) else None
            key = description.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(
                _item(
                    description=description,
                    category=category,
                    unit=unit,
                    quantity=qty,
                    item_code=code,
                    document_id=document_id,
                    page=page,
                    source=f"{filename}" + (f" - Table p.{page}" if page else " - Table"),
                    method="Extracted from quantity table",
                    confidence=94,
                )
            )

    # 2) Regex over free text
    text = content.text or ""
    for desc, category, unit_hint, pattern in CIVIL_PATTERNS:
        if desc.lower() in seen:
            continue
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        qty = _parse_number(match.group(1))
        if qty is None:
            continue
        unit = (match.group(2) if match.lastindex and match.lastindex >= 2 else unit_hint) or unit_hint
        unit = _normalize_unit(unit)
        page = _guess_page(text, match.start(), content)
        seen.add(desc.lower())
        items.append(
            _item(
                description=desc,
                category=category,
                unit=unit,
                quantity=qty,
                document_id=document_id,
                page=page,
                source=f"{filename}" + (f" - Page {page}" if page else ""),
                method="Pattern match from document text",
                confidence=78,
            )
        )

    # Water main / utility labels & callouts (often the only size/LF source on plans)
    for it in (_analyze_utility_labels(filename=filename, content=content, document_id=document_id).get("items") or []):
        key = str(it.get("description") or "").lower()
        if key and key not in seen:
            seen.add(key)
            items.append(it)

    # Geometry notes
    facts: list[dict[str, Any]] = []
    width_match = re.search(r"\b(?:Road|Carriageway)\s*Width\b[^\d]{0,20}(\d{1,2}(?:\.\d+)?)\s*m\b", text, re.I)
    if width_match:
        facts.append({"key": "road_width_m", "value": width_match.group(1), "source_page": _guess_page(text, width_match.start(), content)})

    chainage_match = re.search(r"\b(?:Chainage|Ch\.?)\s*[:\-]?\s*([\d\+\.]+(?:\s*(?:to|\-)\s*[\d\+\.]+)?)", text, re.I)
    if chainage_match:
        facts.append({"key": "chainage", "value": chainage_match.group(1), "source_page": _guess_page(text, chainage_match.start(), content)})

    summary = (
        f"Analyzed '{filename}' with heuristic civil extractor. "
        f"Found {len(items)} quantity item(s)"
        + (f" and {len(facts)} geometry/note fact(s)." if facts else ".")
    )
    if not items:
        summary += " No explicit quantities found — flagging for engineer review."

    return {
        "engine": "heuristic",
        "summary": summary,
        "facts": facts,
        "items": items,
        "needs_review": len(items) == 0,
    }


def _catalog_prompt_bits(bid_catalog: list[dict[str, Any]] | None) -> tuple[str, str, str]:
    catalog = bid_catalog or []
    catalog_preview = json.dumps(catalog[:100], ensure_ascii=True)[:12000] if catalog else "[]"
    if catalog:
        system = (
            "You are a USA civil/highway quantity surveyor AI for AutoVAD. "
            "An agency bid template is active. Extract ONLY items needed for THIS project "
            "with evidence in the plans (drawings, details, schedules). Return STRICT JSON only."
        )
        catalog_rules = f"""
ACTIVE BID TEMPLATE (Standard Bid Item Number / description / unit):
{catalog_preview}

Template rules:
- Do NOT dump the entire bid list.
- Only include bid lines evidenced in the plans/drawings/tables.
- When matched, use the template description EXACTLY, its unit, and Standard Bid Item Number as item_code.
- Unmatched but evidenced work may still be included with empty item_code.
"""
        code_hint = "Use Standard Bid Item Numbers from the active template when matched."
    else:
        system = (
            "You are a USA civil/highway quantity surveyor AI for AutoVAD. "
            "Extract measurable BOQ items using AutoVAD default CSI-oriented civil items. "
            "Return STRICT JSON only."
        )
        catalog_rules = """
No agency bid template — use AutoVAD default civil/CSI descriptions
(earthwork, pavement layers, curb/gutter, sidewalk, drainage, utilities, manholes, etc.).
"""
        code_hint = "Prefer USA CSI MasterFormat codes when identifiable."
    return system, catalog_rules, code_hint


def _items_from_openai_payload(
    data: dict[str, Any],
    *,
    filename: str,
    document_id: int,
    default_method: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw_item in data.get("items") or []:
        qty = _parse_number(raw_item.get("quantity"))
        if qty is None or not raw_item.get("description"):
            continue
        conf = _parse_number(raw_item.get("confidence")) or Decimal("80")
        items.append(
            _item(
                description=str(raw_item.get("description")).strip(),
                category=str(raw_item.get("category") or "General"),
                unit=str(raw_item.get("unit") or "unit"),
                quantity=qty,
                item_code=(str(raw_item["item_code"]) if raw_item.get("item_code") else None),
                document_id=document_id,
                page=raw_item.get("source_page"),
                source=f"{filename}"
                + (f" - Page {raw_item.get('source_page')}" if raw_item.get("source_page") else "")
                + (f" - {raw_item.get('source_reference')}" if raw_item.get("source_reference") else ""),
                method=str(raw_item.get("calculation_method") or default_method),
                confidence=float(conf),
                status=str(raw_item.get("status") or "needs_review"),
                source_reference=raw_item.get("source_reference"),
            )
        )
    return items


def _analyze_with_openai(
    *,
    filename: str,
    content: ExtractedContent,
    document_id: int,
    bid_catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.openai_client import ask_openai_json

    clipped = (content.text or "")[:50000]
    tables_preview = json.dumps(content.tables[:12], ensure_ascii=True)[:18000]
    system, catalog_rules, code_hint = _catalog_prompt_bits(bid_catalog)

    user = f"""
Extract measurable BOQ items from the document TEXT and TABLES.
(Drawing sheets are analyzed separately via vision — still capture every table/schedule/label quantity here.)

Rules:
- Only extract quantities that are explicitly stated or clearly calculable.
- PRIORITIZE utility LABELS / CALLOUTS for water main / watermain / WM (size + LF when present).
  Examples: 8" WATER MAIN, PROP. WM 12", 8" DIP WM STA 10+00 TO 12+50, WATERMAIN 245 LF.
- Also capture water valves, bends, hydrants, sanitary/storm mains from labels when sized/quantified.
- Keep pipe SIZE in the description (e.g. "8-Inch Water Main"). Unit LF for mains, EA for fittings.
- If unsure, omit inventing values and mark needs_review.
{catalog_rules}

Document filename: {filename}
Document id: {document_id}

TEXT:
{clipped}

TABLES_JSON:
{tables_preview}

Return JSON shape:
{{
  "summary": "string",
  "facts": [{{"key":"water_main_size_in","value":"8","source_page":1}}],
  "items": [
    {{
      "item_code": "optional Standard Bid Item Number or CSI",
      "description": "8-Inch Water Main",
      "category": "Utilities",
      "unit": "LF",
      "quantity": 245,
      "source_page": 4,
      "source_reference": "Plan label 8\\" WATER MAIN",
      "calculation_method": "Extracted from drawing label/callout",
      "confidence": 92,
      "status": "needs_review"
    }}
  ],
  "needs_review": false
}}
"""
    data = ask_openai_json(system + " " + code_hint, user)
    items = _items_from_openai_payload(
        data, filename=filename, document_id=document_id, default_method="OpenAI text/table extraction"
    )
    return {
        "engine": "openai",
        "summary": data.get("summary") or f"OpenAI text-analyzed '{filename}'.",
        "facts": data.get("facts") or [],
        "items": items,
        "needs_review": bool(data.get("needs_review")) or len(items) == 0,
    }


def _analyze_utility_labels(
    *,
    filename: str,
    content: ExtractedContent,
    document_id: int,
) -> dict[str, Any]:
    """Deterministic extraction of water main / utility quantities from label text."""
    from app.services.utility_labels import extract_utility_label_items

    raw_items = extract_utility_label_items(
        content.text or "",
        filename=filename,
        document_id=document_id,
    )
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        qty = _parse_number(raw.get("quantity"))
        if qty is None or not raw.get("description"):
            continue
        items.append(
            _item(
                description=str(raw["description"]),
                category=str(raw.get("category") or "Utilities"),
                unit=str(raw.get("unit") or "LF"),
                quantity=qty,
                document_id=document_id,
                page=raw.get("source_page"),
                source=f"{filename} - {raw.get('source_reference') or 'label'}",
                method=str(raw.get("calculation_method") or "Plan label/callout"),
                confidence=float(raw.get("confidence") or 85),
                status=str(raw.get("status") or "needs_review"),
                source_reference=raw.get("source_reference"),
            )
        )
    return {
        "engine": "label-parser",
        "summary": (
            f"Label/callout parser found {len(items)} utility item(s) "
            f"(water main / fittings / related) in '{filename}'."
        ),
        "facts": [],
        "items": items,
        "needs_review": True,
    }


def _analyze_pdf_drawings_with_vision(
    *,
    filename: str,
    document_id: int,
    pdf_path: Path,
    bid_catalog: list[dict[str, Any]] | None = None,
    max_pages: int = 0,
    dpi: int = 150,
    min_score: float = 18.0,
    force_utility_pages: bool = True,
    scan_all_pages: bool = True,
    batch_pages: int = 8,
    content: ExtractedContent | None = None,
) -> dict[str, Any]:
    from app.services.openai_client import ask_openai_vision_json
    from app.services.pdf_vision import iter_rendered_pdf_batches, plan_pdf_vision_pages

    plan = plan_pdf_vision_pages(
        pdf_path,
        max_pages=max_pages,
        min_score=min_score,
        force_utility_pages=force_utility_pages,
        scan_all_pages=scan_all_pages,
        batch_pages=batch_pages,
    )
    if not plan.selected_pages:
        raise RuntimeError("No PDF pages could be rendered for vision")

    system, catalog_rules, code_hint = _catalog_prompt_bits(bid_catalog)

    # Hint model with OCR snippets that look like water-main labels
    label_hints = ""
    if content and content.text:
        snippets = []
        for line in (content.text or "").splitlines():
            low = line.lower()
            if any(k in low for k in ("water main", "watermain", " wm", "wm ", 'water"', "dip wm", "prop. wm", "proposed wm")):
                snippets.append(line.strip()[:160])
            if len(snippets) >= 40:
                break
        if snippets:
            label_hints = "OCR/label snippets that may appear on sheets:\n" + "\n".join(f"- {s}" for s in snippets)

    vision_system = (
        system
        + " "
        + code_hint
        + " Focus on drawings AND utility labels/callouts (especially water mains)."
    )
    all_items: list[dict[str, Any]] = []
    all_facts: list[Any] = []
    summaries: list[str] = []
    vision_pages_meta: list[dict[str, Any]] = []
    batch_errors: list[str] = []
    batch_index = 0

    for batch in iter_rendered_pdf_batches(pdf_path, plan, dpi=dpi, batch_pages=batch_pages):
        batch_index += 1
        page_meta = ", ".join(f"p{p.page} ({p.reason})" for p in batch)
        images = [{"page": p.page, "png_b64": p.png_b64} for p in batch]
        vision_pages_meta.extend({"page": p.page, "reason": p.reason} for p in batch)
        coverage_note = (
            f"This is batch {batch_index} of the PDF. "
            f"Document has {plan.page_count} page(s); this request covers pages "
            f"{[p.page for p in batch]}. Extract ALL bid/takeoff items visible on THESE sheets only."
        )
        user = f"""
You are looking at RENDERED ENGINEERING PLAN SHEETS from a civil PDF (not just OCR text).

Document: {filename}
Rendered sheets: {page_meta}
{coverage_note}

Primary job:
- Read drawings, plan views, profiles, typical details, dimensions, hatch notes, CALLOUTS/LABELS,
  and quantity notes ON THE SHEETS.
- CRITICAL: Utility pipe sizes and lengths are often ONLY in labels (not tables), especially:
  water main / watermain / WM / PROP. WM, with sizes like 6", 8", 12" and lengths in LF or by stationing.
- Extract each sized water main as its own BOQ line (e.g. "8-Inch Water Main", unit LF).
- Also extract valves, bends, tees, hydrants, sanitary/storm mains, MH/inlets from labels/symbols.
- Prefer measured geometry when dimensions/scales/stationing support it.
- Do NOT invent work that is not shown. If approximate from the drawing, lower confidence.
{catalog_rules}

{label_hints}

Return JSON:
{{
  "summary": "what the drawings show for takeoff (mention water mains found in labels)",
  "facts": [{{"key":"water_main_label","value":"8\\" WM","source_page":3}}],
  "items": [
    {{
      "item_code": "optional",
      "description": "8-Inch Water Main",
      "category": "Utilities",
      "unit": "LF",
      "quantity": 245,
      "source_page": 4,
      "source_reference": "Plan label — 8\\" WATER MAIN",
      "calculation_method": "Read from drawing label/callout (and/or station length)",
      "confidence": 90,
      "status": "needs_review"
    }}
  ],
  "needs_review": true
}}
"""
        try:
            data = ask_openai_vision_json(vision_system, user, images)
        except Exception as exc:
            batch_errors.append(f"batch {batch_index} pages {[p.page for p in batch]}: {exc}")
            continue
        batch_items = _items_from_openai_payload(
            data,
            filename=filename,
            document_id=document_id,
            default_method="OpenAI vision — engineering drawing sheet",
        )
        all_items.extend(batch_items)
        all_facts.extend(data.get("facts") or [])
        if data.get("summary"):
            summaries.append(str(data["summary"]))

    # Merge duplicate keys across batches (same desc/unit)
    merged_pack = _merge_analysis_results(
        {"items": [], "facts": [], "summary": "", "needs_review": False},
        {
            "items": all_items,
            "facts": all_facts,
            "summary": " ".join(summaries).strip(),
            "needs_review": len(all_items) == 0,
            "vision_pages": vision_pages_meta,
        },
    )
    items = merged_pack.get("items") or all_items
    scanned = len(plan.selected_pages)
    summary = (
        f"Vision-analyzed {scanned}/{plan.page_count} page(s) from '{filename}' "
        f"in {batch_index} batch(es)."
    )
    if summaries:
        summary = f"{summary} {' '.join(summaries[:3])}"
    if plan.truncated:
        summary += (
            f" Safety cap skipped {len(plan.skipped_pages)} page(s) "
            f"(set OPENAI_VISION_MAX_PAGES=0 and OPENAI_VISION_SCAN_ALL_PAGES=true for full scan)."
        )
    if batch_errors:
        summary += " Batch errors: " + " | ".join(batch_errors[:5])

    return {
        "engine": "openai+vision",
        "summary": summary,
        "facts": merged_pack.get("facts") or all_facts,
        "items": items,
        "needs_review": bool(merged_pack.get("needs_review"))
        or len(items) == 0
        or plan.truncated
        or bool(batch_errors),
        "vision_pages": vision_pages_meta,
        "notes": (" | ".join(batch_errors) if batch_errors else None),
        "vision_coverage": {
            "page_count": plan.page_count,
            "selected_pages": plan.selected_pages,
            "skipped_pages": plan.skipped_pages,
            "truncated": plan.truncated,
            "scan_all": plan.scan_all,
            "batch_pages": batch_pages,
            "batches": batch_index,
            "forced_utility_pages": plan.forced_utility_pages,
        },
    }


def _merge_analysis_results(text_result: dict[str, Any], vision_result: dict[str, Any]) -> dict[str, Any]:
    """Union text/table items with drawing-vision items; keep best confidence per key."""
    merged: dict[str, dict[str, Any]] = {}

    def key_for(item: dict[str, Any]) -> str:
        code = str(item.get("item_code") or item.get("csi_code") or "").strip().lower()
        desc = str(item.get("description") or "").strip().lower()
        unit = str(item.get("unit") or "").strip().lower()
        return f"{code}|{desc}|{unit}"

    for source in (text_result.get("items") or [], vision_result.get("items") or []):
        for item in source:
            k = key_for(item)
            if not item.get("description"):
                continue
            if k not in merged:
                merged[k] = dict(item)
                continue
            existing = merged[k]
            try:
                old_c = float(existing.get("confidence") or 0)
                new_c = float(item.get("confidence") or 0)
                old_q = float(existing.get("quantity") or 0)
                new_q = float(item.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if new_c > old_c + 2:
                merged[k] = dict(item)
            elif abs(new_c - old_c) <= 2 and new_q > old_q:
                merged[k] = dict(item)

    items = list(merged.values())
    facts = list(text_result.get("facts") or []) + list(vision_result.get("facts") or [])
    summary = (
        f"{vision_result.get('summary') or ''} "
        f"Also merged text/table takeoff ({len(text_result.get('items') or [])} text items, "
        f"{len(vision_result.get('items') or [])} drawing items → {len(items)} unique)."
    ).strip()
    return {
        "engine": "openai+vision",
        "summary": summary,
        "facts": facts,
        "items": items,
        "needs_review": bool(text_result.get("needs_review") or vision_result.get("needs_review"))
        or len(items) == 0,
        "vision_pages": vision_result.get("vision_pages") or [],
        "vision_coverage": vision_result.get("vision_coverage")
        or text_result.get("vision_coverage"),
    }


def answer_engineering_question(*, question: str, context: str) -> dict[str, Any]:
    from app.services.openai_client import openai_configured

    if openai_configured():
        try:
            return _answer_with_openai(question=question, context=context)
        except Exception as exc:
            fallback = _answer_heuristic(question=question, context=context)
            fallback["answer"] = f"{fallback['answer']}\n\n(Note: OpenAI unavailable: {exc})"
            return fallback
    return _answer_heuristic(question=question, context=context)


def _answer_with_openai(*, question: str, context: str) -> dict[str, Any]:
    from app.services.openai_client import ask_openai_json

    system = (
        "You are AutoVAD, an assistant for civil engineers working on USA road projects. "
        "Answer using ONLY the project context. If unknown, say you don't have enough information. "
        "Return STRICT JSON only."
    )
    user = f"""
CONTEXT:
{context[:50000]}

QUESTION:
{question}

Return JSON:
{{
  "answer": "markdown-friendly answer",
  "sources": [{{"label":"Page 18 – Table 4.2","document_id":1,"page":18}}]
}}
"""
    data = ask_openai_json(system, user, temperature=0.2)
    return {
        "answer": data.get("answer") or "No answer returned.",
        "sources": data.get("sources") or [],
        "engine": "openai",
    }


def _answer_heuristic(*, question: str, context: str) -> dict[str, Any]:
    q = question.lower()
    sources: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in context.splitlines() if ln.strip()]

    def find_lines(keywords: list[str]) -> list[str]:
        hits = []
        for ln in lines:
            low = ln.lower()
            if any(k in low for k in keywords):
                hits.append(ln)
            if len(hits) >= 8:
                break
        return hits

    if "road width" in q or "carriageway" in q:
        hits = find_lines(["road width", "carriageway width", "width"])
        if hits:
            return {"answer": "From project documents:\n- " + "\n- ".join(hits[:5]), "sources": sources, "engine": "heuristic"}

    if "gsb" in q:
        hits = find_lines(["gsb"])
        if hits:
            return {"answer": "GSB references found:\n- " + "\n- ".join(hits[:6]), "sources": sources, "engine": "heuristic"}

    if "wmm" in q:
        hits = find_lines(["wmm"])
        if hits:
            return {"answer": "WMM references found:\n- " + "\n- ".join(hits[:6]), "sources": sources, "engine": "heuristic"}

    if "culvert" in q:
        hits = find_lines(["culvert"])
        if hits:
            return {"answer": "Culvert references found:\n- " + "\n- ".join(hits[:6]), "sources": sources, "engine": "heuristic"}

    if "pavement" in q or "layer" in q:
        hits = find_lines(["gsb", "wmm", "dbm", "bituminous", "asphalt", "pavement"])
        if hits:
            return {"answer": "Pavement-related findings:\n- " + "\n- ".join(hits[:8]), "sources": sources, "engine": "heuristic"}

    if "boq" in q or "quantity" in q or "how much" in q:
        hits = find_lines(["quantity", "qty", "m3", "gsb", "wmm", "boq"])
        if hits:
            return {"answer": "Quantity-related findings:\n- " + "\n- ".join(hits[:8]), "sources": sources, "engine": "heuristic"}

    # generic keyword search
    keywords = [w for w in re.findall(r"[a-zA-Z]{3,}", q) if w not in {"what", "where", "show", "find", "this", "that", "from", "with", "have", "many", "much"}]
    hits = find_lines(keywords[:4]) if keywords else []
    if hits:
        return {
            "answer": "I found these related excerpts in the project documents:\n- " + "\n- ".join(hits[:8]),
            "sources": sources,
            "engine": "heuristic",
        }

    return {
        "answer": (
            "I don't have enough extracted information to answer confidently yet. "
            "Run AI analysis on the uploaded documents, then ask again."
        ),
        "sources": [],
        "engine": "heuristic",
    }


def _item(
    *,
    description: str,
    category: str,
    unit: str,
    quantity: Decimal,
    document_id: int,
    page: int | None,
    source: str,
    method: str,
    confidence: float,
    item_code: str | None = None,
    status: str = "needs_review",
    source_reference: str | None = None,
) -> dict[str, Any]:
    from app.services.csi_mapper import enrich_quantity_item

    raw = {
        "item_code": item_code,
        "description": description,
        "category": category,
        "unit": unit,
        "quantity": float(quantity),
        "source_document_id": document_id,
        "source_page": page,
        "source_reference": source_reference or source,
        "calculation_method": method,
        "confidence": confidence,
        "status": status,
    }
    return enrich_quantity_item(raw)


def _map_alias(text: str) -> tuple[str, str, str] | None:
    low = text.lower()
    for key, value in ITEM_ALIASES.items():
        if key in low:
            return value
    return None


def _find_col(header: list[str], names: list[str]) -> int | None:
    for i, h in enumerate(header):
        for n in names:
            if n == h or n in h:
                return i
    return None


def _parse_number(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _normalize_unit(unit: str) -> str:
    u = unit.strip().lower().replace("³", "3")
    mapping = {
        "m3": "m3",
        "cu.m": "m3",
        "cu m": "m3",
        "cubic meter": "m3",
        "cubic meters": "m3",
        "m": "m",
        "lm": "m",
        "lin m": "m",
        "linear m": "m",
        "nos": "nos",
        "no": "nos",
        "no.": "nos",
        "each": "nos",
        "ea": "nos",
        "t": "t",
        "ton": "t",
        "tons": "t",
    }
    return mapping.get(u, unit.strip())


def _guess_page(full_text: str, pos: int, content: ExtractedContent) -> int | None:
    prefix = full_text[:pos]
    pages = re.findall(r"--- Page (\d+) ---", prefix)
    if pages:
        return int(pages[-1])
    if content.pages:
        return content.pages[0].page
    return None
