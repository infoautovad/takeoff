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
    assert resolve_eoq_group(description="Temporary Mailbox") == "Traffic Control"
    assert resolve_eoq_group(description="Type 3 Barricade, 8' Double Sided") == "Traffic Control"
    assert resolve_eoq_group(description="Mobilization") == "General"
    assert resolve_eoq_group(description="Winter Maintenance") == "General"
    assert resolve_eoq_group(description="Dam Embankment Fill") == "Dams & Reservoirs"
    assert resolve_eoq_group(description="Brickwork") == "Building"

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
    assert names.index("General") < names.index("Removals")
    assert names.index("Removals") < names.index("Watermain")


def test_ensure_mobilization_item_always_one_ls_under_general():
    from app.services.eoq_groups import group_items, looks_like_mobilization, resolve_eoq_group
    from app.services.eoq_service import ensure_mobilization_item

    assert looks_like_mobilization("Mobilization")
    assert not looks_like_mobilization("Demobilization")

    out = ensure_mobilization_item(
        [{"description": "8-Inch Water Main", "unit": "LF", "quantity": 100}]
    )
    mob = [i for i in out if i["description"] == "Mobilization"]
    assert len(mob) == 1
    assert mob[0]["unit"] == "LS"
    assert float(mob[0]["quantity"]) == 1
    assert resolve_eoq_group(description=mob[0]["description"], category=mob[0].get("category")) == "General"
    assert out[0]["description"] == "Mobilization"

    mixed = ensure_mobilization_item(
        [
            {"description": "Traffic Control", "unit": "SQFT", "quantity": 624},
            {"description": "8-Inch Water Main", "unit": "LF", "quantity": 100},
        ]
    )
    sections = group_items(
        mixed,
        get_description=lambda i: i["description"],
        get_category=lambda i: i.get("category"),
        repeat_mobilization=True,
    )
    by_name = {name: rows for name, rows in sections}
    assert "General" in by_name and "Traffic Control" in by_name
    assert any(i["description"] == "Mobilization" for i in by_name["General"])
    assert any(i["description"] == "Mobilization" for i in by_name["Traffic Control"])
    assert any(i["description"] == "Traffic Control" for i in by_name["Traffic Control"])


def test_ensure_mobilization_collapses_extracted_row_to_one_ls():
    from app.services.eoq_service import ensure_mobilization_item

    out = ensure_mobilization_item(
        [
            {
                "description": "Mobilization",
                "unit": "LS",
                "quantity": 3,
                "item_code": "9.0010",
            },
            {"description": "HMA", "unit": "TON", "quantity": 12},
        ]
    )
    mobs = [i for i in out if "mobilization" in str(i["description"]).lower()]
    assert len(mobs) == 1
    assert mobs[0]["quantity"] == 1
    assert mobs[0]["unit"] == "LS"
    assert mobs[0]["item_code"] == "9.0010"


def test_normalize_unit_lf():
    assert normalize_unit("LF") in {"LF", "lf"} or str(normalize_unit("linear feet")).upper() in {"LF", "M"}


def test_format_export_unit_sqft_and_ton():
    from app.services.csi_mapper import format_export_unit
    from app.schemas.eoq import EOQItemOut
    from app.models.eoq import EOQItemStatus
    from datetime import datetime, timezone

    assert format_export_unit("sf") == "SQFT"
    assert format_export_unit("SF") == "SQFT"
    assert format_export_unit("SqFt") == "SQFT"
    assert format_export_unit("t") == "TON"
    assert format_export_unit("T") == "TON"
    assert format_export_unit("ton") == "TON"
    assert format_export_unit("LF") == "LF"

    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        eoq_id=1,
        item_number="1",
        item_code=None,
        description="Traffic Control",
        category=None,
        quantity=1,
        rate=None,
        amount=None,
        source_document_id=None,
        source_page=None,
        source_reference=None,
        calculation_method=None,
        confidence=None,
        status=EOQItemStatus.NEEDS_REVIEW,
        created_at=now,
        updated_at=now,
    )
    assert EOQItemOut.model_validate({**base, "unit": "SF"}).unit == "SQFT"
    assert EOQItemOut.model_validate({**base, "unit": "T"}).unit == "TON"


def test_parse_expected_items_roundtrip():
    raw = {"items": [{"description": "Valve", "unit": "EA", "quantity": 3}]}
    items = parse_expected_items(raw)
    assert len(items) == 1
    assert items[0].quantity == 3.0
