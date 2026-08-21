"""Gold-set and takeoff regression tests (no live OpenAI/APS)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.eoq_eval import ExpectedItem, compare_eoq, parse_expected_items, summarize_report
from app.services.cad.quantity_engine import build_quantities, extract_size_label, detect_network
from app.services.bid_service import _match_line
from app.services.csi_mapper import normalize_unit

GOLD_ROOT = Path(__file__).parent / "gold_set" / "cases"


def _load_case(case_id: str) -> tuple[dict, dict]:
    case_dir = GOLD_ROOT / case_id
    expected = json.loads((case_dir / "expected_eoq.json").read_text(encoding="utf-8"))
    extraction = json.loads((case_dir / "extraction.json").read_text(encoding="utf-8"))
    return expected, extraction


def test_extract_size_and_network_helpers():
    assert extract_size_label('8" WATER MAIN') == "8-Inch"
    assert extract_size_label("P_WATER_12IN") == "12-Inch"
    assert detect_network("P_SAN", "sanitary sewer") == "sanitary"
    assert detect_network("P_WATER", "watermain") == "water"


def test_gold_sample_utility_quantity_engine():
    expected_raw, extraction = _load_case("sample_utility")
    items = build_quantities(extraction, source_label="sample_utility.dwg")
    report = compare_eoq(expected_raw, items)

    assert report.recall >= 0.85, summarize_report(report)
    assert not report.misses, summarize_report(report)
    assert len(report.qty_errors) == 0, summarize_report(report)


def test_compare_eoq_miss_by_category():
    expected = [
        ExpectedItem(description="8-Inch Water Main", unit="LF", category="Utilities", quantity=100),
        ExpectedItem(description="Earthwork Cut", unit="CY", category="Earthwork", quantity=50),
    ]
    actual = [{"description": "8-Inch Water Main", "unit": "LF", "quantity": 100, "category": "Utilities"}]
    report = compare_eoq(expected, actual)
    assert report.misses_by_category.get("Earthwork") == 1
    assert report.recall == 0.5


def test_bid_match_requires_compatible_unit():
    """Stricter matcher: fuzzy match must not ignore conflicting units."""
    from types import SimpleNamespace

    lines = [
        SimpleNamespace(
            id=1,
            item_code="401-1",
            csi_code=None,
            description="8 Inch Water Main",
            unit="LF",
            line_number=1,
            sort_order=1,
            default_rate=None,
        )
    ]
    hit, score, method = _match_line(
        lines,  # type: ignore[arg-type]
        description="8-Inch Water Main",
        unit="EA",
        csi_code=None,
        item_code=None,
    )
    assert hit is None or method == "unmatched" or score < 55
    hit2, score2, _method2 = _match_line(
        lines,  # type: ignore[arg-type]
        description="8-Inch Water Main",
        unit="LF",
        csi_code=None,
        item_code=None,
    )
    assert hit2 is not None
    assert score2 >= 78


def test_eoq_group_sections():
    from app.services.eoq_groups import group_items, resolve_eoq_group

    assert resolve_eoq_group(description='8" PVC Watermain') == "Watermain"
    assert resolve_eoq_group(description="Remove Concrete Curb and Gutter") == "Removals"
    assert resolve_eoq_group(description="Unclassified Excavation") == "Grading"
    assert resolve_eoq_group(description="Sanitary Sewer Pipe 8 Inch") == "Sanitary Sewer"
    assert resolve_eoq_group(description="Aggregate Base Course") == "Surfacing"
    assert resolve_eoq_group(description="Silt Fence") == "Erosion Control / Restoration"
    assert resolve_eoq_group(description="Mobilization") == "General / Traffic Control"

    rows = [
        {"description": "Mobilization", "category": None},
        {"description": "8-Inch Water Main", "category": "Utilities"},
        {"description": "Remove Curb", "category": None},
    ]
    sections = group_items(
        rows,
        get_description=lambda i: i["description"],
        get_category=lambda i: i.get("category"),
    )
    names = [s[0] for s in sections]
    assert names.index("General / Traffic Control") < names.index("Removals")
    assert names.index("Removals") < names.index("Watermain")


def test_normalize_unit_lf():
    assert normalize_unit("LF") in {"LF", "lf"} or str(normalize_unit("linear feet")).upper() in {"LF", "M"}


def test_parse_expected_items_roundtrip():
    raw = {"items": [{"description": "Valve", "unit": "EA", "quantity": 3}]}
    items = parse_expected_items(raw)
    assert len(items) == 1
    assert items[0].quantity == 3.0
