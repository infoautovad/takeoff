"""Generate a confidential Word pack of AutoVAD unique core code only (not full files)."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_PATH = HERE / "AutoVAD_Unique_Core_Code_Confidential.docx"

_spec = importlib.util.spec_from_file_location("autovad_ip_brief", HERE / "_generate_ip_brief.py")
_brief = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_brief)

RED = _brief.RED
DARK = _brief.DARK
BLUE = _brief.BLUE
apply_header = _brief.apply_header
apply_footer = _brief.apply_footer
centered = _brief.centered
para = _brief.para
bullets = _brief.bullets
add_table = _brief.add_table
set_run_font = _brief.set_run_font

# Unique methods → live symbols. Only distinctive logic; no CRUD / glue / full files.
SECTIONS: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    (
        "U-01  Bid-schedule-authoritative pay-item copy",
        "Copy Bid Items / EOQ grid rows as the pay-item list, keep blank cells, and lock only when the table looks like a true bid schedule.",
        [
            ("backend/app/services/ai_analysis.py", "py", "_is_bid_schedule_table"),
            ("backend/app/services/ai_analysis.py", "py", "_is_strict_schedule_lock_row"),
            ("backend/app/services/ai_analysis.py", "py", "_should_lock_strict_schedule_mode"),
            ("backend/app/services/ai_analysis.py", "py", "_items_from_document_tables"),
            ("backend/app/services/ai_analysis.py", "py", "_focused_reread_schedule_pages_with_vision"),
            ("backend/app/services/ai_analysis.py", "py", "_finalize_analysis"),
        ],
    ),
    (
        "U-02  Multi-engine drawing takeoff fusion + model-compat client",
        "Fuse text, tables, vision, labels, and CAD. Drop parameters newer OpenAI models reject so graphic sheets do not return an empty EOQ.",
        [
            ("backend/app/services/openai_client.py", "py", "_supports_custom_temperature"),
            ("backend/app/services/openai_client.py", "py", "_create_dropping_unsupported"),
            ("backend/app/services/processing.py", "py", "process_document"),
        ],
    ),
    (
        "U-03  Incidental-to-bid-item exclusion",
        "Drop bedding, fittings, trench extras, and similar work marked incidental. Do not add those quantities onto the parent item.",
        [
            ("backend/app/services/incidental.py", "py", "has_incidental_language"),
            ("backend/app/services/incidental.py", "py", "description_is_incidental_child"),
            ("backend/app/services/incidental.py", "py", "skip_text_extraction"),
            ("backend/app/services/incidental.py", "py", "should_drop_incidental_item"),
        ],
    ),
    (
        "U-04  Similar-item location combining",
        "Sum the same pay item from different sheets. Keep pipe size, N-P-K, remove vs install, and Alternate A vs B apart.",
        [
            ("backend/app/services/item_combine.py", "py", "pay_items_similar"),
            ("backend/app/services/item_combine.py", "py", "combine_similar_pay_items"),
        ],
    ),
    (
        "U-05  Traffic Control sign rollup with schedule companions",
        "Roll plan signs to one SqFt item when there is no schedule. When a Bid Items Traffic Control section exists, copy those rows and drop invented signs.",
        [
            ("backend/app/services/traffic_control.py", "py", "is_plan_device_takeoff"),
            ("backend/app/services/traffic_control.py", "py", "is_distinct_traffic_pay_item"),
            ("backend/app/services/traffic_control.py", "py", "_filter_plan_invented_when_schedule"),
            ("backend/app/services/traffic_control.py", "py", "consolidate_traffic_control_signs"),
        ],
    ),
    (
        "U-06  Size-aware CAD quantity engine",
        "Turn CAD entities into civil pay items by network, detected pipe size, length, and fittings.",
        [
            ("backend/app/services/cad/quantity_engine.py", "py", "extract_size_label"),
            ("backend/app/services/cad/quantity_engine.py", "py", "detect_network"),
            ("backend/app/services/cad/quantity_engine.py", "py", "classify_fitting"),
            ("backend/app/services/civil_estimator.py", "py", "trench_items_from_pipes"),
        ],
    ),
    (
        "U-07  Civil 3D / DWG station-offset takeoff",
        "Export alignments, pipes, and paper-space callouts, then build centerline-relative LT/RT lengths and bid summary.",
        [
            ("backend/cad_plugins/AutoVadCivilTakeoff/Commands.cs", "cs", "RunTakeoff"),
            ("backend/cad_plugins/AutoVadCivilTakeoff/Commands.cs", "cs", "TryExportCivil"),
            ("backend/app/services/cad/utility_stationing.py", "py", "build_bid_summary_from_detail"),
        ],
    ),
    (
        "U-08  Municipal EOQ grouping, alternates, and Mobilization",
        "Group in agency EOQ order. Alternate A/B are their own sections. Strip Alternate prefixes from descriptions. Keep Mobilization as 1 LS.",
        [
            ("backend/app/services/eoq_groups.py", "py", "detect_alternate_section"),
            ("backend/app/services/eoq_groups.py", "py", "strip_alternate_label"),
            ("backend/app/services/eoq_groups.py", "py", "resolve_eoq_group"),
            ("backend/app/services/eoq_service.py", "py", "ensure_mobilization_item"),
            ("frontend/src/utils/eoqGroups.ts", "ts", "detectAlternateSection"),
            ("frontend/src/utils/eoqGroups.ts", "ts", "stripAlternateLabel"),
            ("frontend/src/utils/eoqGroups.ts", "ts", "resolveEoqGroup"),
        ],
    ),
    (
        "U-09  CSI mapping that does not erase agency bid numbers",
        "Map descriptions to CSI and USA units (SQFT/TON) while keeping agency Standard Bid Item Numbers on item_code.",
        [
            ("backend/app/services/csi_mapper.py", "py", "looks_like_csi"),
            ("backend/app/services/csi_mapper.py", "py", "format_export_unit"),
            ("backend/app/services/csi_mapper.py", "py", "map_csi"),
        ],
    ),
    (
        "U-10  Design-only civil estimator",
        "When no bid schedule exists, typical-section dimensions produce pavement, prime/tack, and related estimator lines.",
        [
            ("backend/app/services/civil_estimator.py", "py", "extraction_has_bid_schedule"),
            ("backend/app/services/civil_estimator.py", "py", "items_from_design_text"),
        ],
    ),
    (
        "U-11  Plan-label utility parser",
        "Parse callouts such as 8\" WATER MAIN 245 LF into sized utility quantities. Suppress fitting invents when a schedule exists.",
        [
            ("backend/app/services/utility_labels.py", "py", "extract_utility_label_items"),
        ],
    ),
    (
        "U-12  Locked master bid list — evidence-only match",
        "Always use Bid Item List 2026. Match evidenced takeoff only. Unused catalog lines are omitted. Unmatched rows stay Special under the true discipline.",
        [
            ("backend/app/services/bid_service.py", "py", "get_autovad_master_bid_catalog"),
            ("backend/app/services/bid_service.py", "py", "build_eoq_items_from_template"),
            ("backend/app/services/bid_service.py", "py", "_match_line"),
            ("backend/app/services/eoq_service.py", "py", "standard_bid_item_number"),
            ("backend/app/services/processing.py", "py", "_bid_catalog_for_project"),
        ],
    ),
    (
        "U-13  Deterministic EOQ validation",
        "Unit-family sanity, exact-duplicate collapse, and schedule quantity preferred over conflicting plan-derived rows.",
        [
            ("backend/app/services/eoq_validation.py", "py", "_expected_unit_families"),
            ("backend/app/services/eoq_validation.py", "py", "validate_extracted_items"),
        ],
    ),
    (
        "U-14  Gold-set EOQ evaluation / Training Lab",
        "Compare original vs AutoVAD by category and quantity. Gold cases improve engines; they are not hardcoded as product EOQ.",
        [
            ("backend/app/services/eoq_eval.py", "py", "_item_match_score"),
            ("backend/app/services/eoq_eval.py", "py", "compare_eoq"),
        ],
    ),
    (
        "U-15  Engineer-review Excel EOQ workbook",
        "Municipal section headers, Special bid numbers, and Verified vs Engineer Review fills. Alternate prefixes stripped in the description column.",
        [
            ("backend/app/services/eoq_service.py", "py", "display_item_description"),
            ("backend/app/services/eoq_service.py", "py", "standard_bid_item_number"),
        ],
    ),
    (
        "U-16  Plan-page vision scoring for large sets",
        "Score each PDF page for schedule, utility labels, profiles, and sparse-text drawings so large sets keep the useful sheets.",
        [
            ("backend/app/services/pdf_vision.py", "py", "_score_page"),
            ("backend/app/services/pdf_vision.py", "py", "select_vision_page_indexes"),
        ],
    ),
    (
        "U-17  Reconstruct AutoVAD EOQ from a user-portal Excel",
        "Training Lab can skip a second analyze and rebuild pay items from AutoVAD section banners, headers, and Special bid numbers.",
        [
            ("backend/app/services/training_service.py", "py", "parse_autovad_eoq_file"),
            ("backend/app/services/training_service.py", "py", "_section_name_from_row"),
            ("backend/app/services/training_service.py", "py", "_parse_autovad_table"),
        ],
    ),
    (
        "U-18  Any-format original / gold EOQ extract",
        "Original EOQ may be PDF, image, Excel, CSV, or JSON. Graphic sheets are rasterized and read by vision.",
        [
            ("backend/app/services/training_service.py", "py", "parse_expected_eoq_file"),
            ("backend/app/services/training_service.py", "py", "_parse_expected_pdf"),
            ("backend/app/services/training_service.py", "py", "_extract_expected_via_ai"),
        ],
    ),
    (
        "U-19  CAD-or-PDF processing with locked catalog injection",
        "Route CAD to the CAD engine and PDFs to document-AI fusion. Both paths receive the same locked master bid catalog.",
        [
            ("backend/app/services/processing.py", "py", "_bid_catalog_for_project"),
            ("backend/app/services/processing.py", "py", "process_document"),
            ("backend/app/services/processing.py", "py", "_process_cad_as_analysis"),
        ],
    ),
]

# Long fusion/export functions: keep the unique decision body, not every persistence line.
MAX_LINES = {
    "_items_from_document_tables": 90,
    "_finalize_analysis": 130,
    "_focused_reread_schedule_pages_with_vision": 80,
    "consolidate_traffic_control_signs": 120,
    "items_from_design_text": 100,
    "extract_utility_label_items": 110,
    "compare_eoq": 90,
    "validate_extracted_items": 110,
    "select_vision_page_indexes": 80,
    "build_bid_summary_from_detail": 80,
    "RunTakeoff": 90,
    "TryExportCivil": 90,
    "_parse_autovad_table": 90,
    "_parse_expected_pdf": 80,
    "_extract_expected_via_ai": 80,
    "trench_items_from_pipes": 80,
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def extract_python(rel: str, name: str) -> tuple[int, int, str, bool]:
    src = _read(rel)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = int(node.lineno)
            end = int(node.end_lineno or node.lineno)
            lines = src.splitlines()
            body = lines[start - 1 : end]
            truncated = False
            cap = MAX_LINES.get(name)
            if cap and len(body) > cap:
                body = body[:cap] + ["", f"    # ... {len(lines[start - 1 : end]) - cap} more lines omitted (I/O, notes, or persistence). Full function is in the repo / full IP brief."]
                truncated = True
            return start, end, "\n".join(body), truncated
    raise KeyError(f"{rel}::{name}")


def _extract_braced(src: str, needle: re.Pattern[str], name: str) -> tuple[int, int, str, bool]:
    match = needle.search(src)
    if not match:
        raise KeyError(name)
    start_char = match.start()
    start_line = src.count("\n", 0, start_char) + 1
    i = src.find("{", match.end() - 1)
    if i < 0:
        i = src.find("{", match.start())
    if i < 0:
        raise KeyError(f"{name} (no body)")
    depth = 0
    end = i
    for end, ch in enumerate(src[i:], start=i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end += 1
                break
    end_line = src.count("\n", 0, end) + 1
    lines = src.splitlines()
    body = lines[start_line - 1 : end_line]
    truncated = False
    cap = MAX_LINES.get(name)
    if cap and len(body) > cap:
        body = body[:cap] + ["", f"    // ... {len(lines[start_line - 1 : end_line]) - cap} more lines omitted. Full method is in the repo / full IP brief."]
        truncated = True
    return start_line, end_line, "\n".join(body), truncated


def extract_ts(rel: str, name: str) -> tuple[int, int, str, bool]:
    src = _read(rel)
    needle = re.compile(rf"export\s+function\s+{re.escape(name)}\s*\(")
    return _extract_braced(src, needle, name)


def extract_cs(rel: str, name: str) -> tuple[int, int, str, bool]:
    src = _read(rel)
    needle = re.compile(rf"(?:public|static|private|protected|\s)+{re.escape(name)}\s*\(")
    return _extract_braced(src, needle, name)


def add_code(doc, text: str) -> None:
    chunk_size = 3500
    for start in range(0, len(text), chunk_size):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run(text[start : start + chunk_size])
        set_run_font(run, size=8, name="Consolas")


def build() -> Path:
    excerpts: list[tuple[str, str, str, int, int, str, bool, str, str]] = []
    for title, why, symbols in SECTIONS:
        for rel, kind, name in symbols:
            if kind == "py":
                start, end, text, truncated = extract_python(rel, name)
            elif kind == "ts":
                start, end, text, truncated = extract_ts(rel, name)
            else:
                start, end, text, truncated = extract_cs(rel, name)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            excerpts.append((title, why, rel, start, end, name, truncated, text, digest))

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(1.05)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)
    section.different_odd_and_even_pages = True
    apply_header(section)
    apply_footer(section)

    unique_fns = len(excerpts)
    unique_lines = sum(text.count("\n") + 1 for *_, text, _digest in excerpts)

    centered(doc, "CONFIDENTIAL", size=14, bold=True, color=RED)
    centered(doc, "ATTORNEY WORK PRODUCT  ·  UNIQUE CORE CODE ONLY", size=11, bold=True, color=RED)
    centered(doc, "AutoVAD", size=28, bold=True, color=DARK)
    centered(doc, "AI Copilot for Civil Engineers", size=16, color=BLUE)
    centered(doc, "Unique Core Code Pack\nDistinctive takeoff / CAD / EOQ logic", size=14, italic=True)
    centered(
        doc,
        f"Prepared: {date.today().isoformat()}    ·    Unique functions: {unique_fns}    ·    Excerpt lines: {unique_lines:,}",
        size=10,
        color=RGBColor(80, 80, 80),
    )
    para(
        doc,
        "This pack is for patent counsel. It reprints only the distinctive engine functions that implement "
        "AutoVAD’s unique civil-quantity methods. It does not reprint entire source files, login, billing, "
        "or website chrome. Companion full-file dump: AutoVAD_Takeoff_Engines_Confidential_IP_Brief_updated.docx. "
        "This document is not a patent application and is not legal advice.",
    )

    doc.add_heading("1. Confidentiality and handling", level=1)
    para(
        doc,
        "Every page is marked CONFIDENTIAL in red in the header, footer, and as a diagonal watermark. "
        "Counsel, inventors, and authorized reviewers only.",
    )
    bullets(
        doc,
        [
            "Classification: Confidential — trade secret / unpublished unique source.",
            "Suggested legend: CONFIDENTIAL — AutoVAD unique core code — Attorney review only.",
            "Do not email to personal accounts or upload to public AI tools.",
        ],
    )

    doc.add_heading("2. What is in this pack", level=1)
    para(
        doc,
        "Each U-number is a unique AutoVAD method. Under it are the live functions that implement that method, "
        "cut from the current repository. Generic helpers, API routes, and CRUD are omitted. A few long functions "
        "are truncated after the unique decision body; the omitted tail is persistence, notes, or I/O.",
    )
    add_table(
        doc,
        ["Method", "Core functions"],
        [
            [title.split("  ", 1)[0], ", ".join(name for _rel, _k, name in symbols)]
            for title, _why, symbols in SECTIONS
        ],
    )

    doc.add_heading("3. Unique core code", level=1)
    current_title = None
    for title, why, rel, start, end, name, truncated, text, digest in excerpts:
        if title != current_title:
            current_title = title
            doc.add_heading(title, level=2)
            para(doc, why)
        heading = f"{name}  —  {rel}:{start}–{end}"
        if truncated:
            heading += "  (unique body; tail omitted)"
        doc.add_heading(heading, level=3)
        para(doc, f"SHA-256 of excerpt: {digest}", italic=True, size=9, space_after=4)
        add_code(doc, text)

    doc.add_heading("4. Counsel note", level=1)
    bullets(
        doc,
        [
            "Use this pack to identify claim-supporting unique algorithms.",
            "Use the companion full-engine brief if counsel needs complete files and SHA-256 of whole files.",
            "Owner / inventors: to be completed by counsel.",
        ],
    )
    end = doc.add_paragraph()
    end.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = end.add_run("END OF CONFIDENTIAL UNIQUE CORE CODE PACK")
    set_run_font(run, size=11, bold=True, color=RED)

    try:
        doc.save(OUT_PATH)
        return OUT_PATH
    except PermissionError:
        alt = OUT_PATH.with_name(f"{OUT_PATH.stem}_{date.today().isoformat()}.docx")
        doc.save(alt)
        return alt


if __name__ == "__main__":
    print(build())
