"""When a Bid Items / EOQ table exists, copy it and do not invent F-sheet extras."""

from app.services.ai_analysis import (
    _CODE_COL_NAMES,
    _DESC_COL_NAMES,
    _QTY_COL_NAMES,
    _analyze_heuristic,
    _finalize_analysis,
    _find_col,
    _is_bid_schedule_table,
    _is_plan_device_table,
)
from app.services.extractors import ExtractedContent
from app.services.civil_estimator import extraction_has_bid_schedule


def _bid_items_table() -> dict:
    return {
        "page": 1,
        "rows": [
            ["Item Number", "Bid Item", "Description", "Units", "Est. Qty"],
            ["1", "9.0010", "Mobilization", "LS", "1"],
            ["2", "634.0110", "Traffic Control", "SqFt", "624"],
            ["3", "634.0120", "Traffic Control, Miscellaneous", "LS", "1"],
            ["4", "634.0285", "Type 3 Barricade, 8' Double Sided", "Each", "13"],
            ["5", "Special", "Winter Maintenance", "LS", "1"],
        ],
    }


def _f3_project_totals_table() -> dict:
    return {
        "page": 9,
        "rows": [
            ["Device", "Itemized", "Project Totals"],
            ["Type III Barricade - 8 Ft. Double Sided", "Each", "10"],
            ["42 in Channelizer", "Each", "8"],
        ],
    }


def test_find_col_prefers_bid_item_and_description():
    header = ["item number", "bid item", "description", "units", "est. qty"]
    assert _find_col(header, list(_DESC_COL_NAMES)) == 2
    assert _find_col(header, list(_CODE_COL_NAMES)) == 1
    assert _find_col(header, list(_QTY_COL_NAMES)) == 4


def test_bid_items_table_is_schedule_not_f_sheet_device_table():
    assert _is_bid_schedule_table(_bid_items_table())
    assert not _is_plan_device_table(_bid_items_table())
    assert _is_plan_device_table(_f3_project_totals_table())
    assert not _is_bid_schedule_table(_f3_project_totals_table())


def test_heuristic_copies_bid_items_and_skips_f3_project_totals():
    content = ExtractedContent(
        text="Bid Items\nITEM NUMBER  BID ITEM  DESCRIPTION  UNITS  EST. QTY",
        tables=[_bid_items_table(), _f3_project_totals_table()],
    )
    result = _analyze_heuristic(filename="plans.pdf", content=content, document_id=1)
    by_desc = {str(i.get("description")): i for i in result["items"]}
    assert by_desc["Traffic Control"]["quantity"] == 624
    assert by_desc["Traffic Control"]["item_code"] == "634.0110"
    assert by_desc["Mobilization"]["item_code"] == "9.0010"
    assert "42 in Channelizer" not in by_desc
    assert not any("Type III Barricade" in d for d in by_desc)


def test_finalize_copies_bid_table_and_drops_f_sheet_invents():
    content = ExtractedContent(
        text="Bid Items table with EST. QTY and BID ITEM columns.",
        tables=[_bid_items_table()],
    )
    result = _finalize_analysis(
        {
            "engine": "openai+vision",
            "summary": "vision mix",
            "items": [
                {
                    "description": "42 in Channelizer",
                    "unit": "Each",
                    "quantity": 8,
                    "item_code": "01 55 26",
                    "confidence": 98,
                    "calculation_method": "Graphic count of channelizer symbols on F-sheets",
                    "source_reference": "Sheets F9-F12 symbols",
                },
                {
                    "description": "Traffic Control",
                    "unit": "SqFt",
                    "quantity": 178.75,
                    "confidence": 98,
                    "calculation_method": "MUTCD 30x30 consolidated ÷144",
                    "source_reference": "F-sheet sign callouts",
                },
                {
                    "description": "Watermain Trench Excavation",
                    "unit": "CuYd",
                    "quantity": 40,
                    "confidence": 93,
                    "entity_type": "ESTIMATOR",
                    "calculation_method": "cover assumed 4', trench width OD+2'",
                },
                {
                    "description": "Remove Fence",
                    "unit": "Ft",
                    "quantity": 120,
                    "calculation_method": "Extracted table total",
                    "source_reference": "Table of Remove Fence",
                },
            ],
        },
        content=content,
    )
    by_desc = {str(i.get("description")): i for i in result["items"]}
    assert by_desc["Traffic Control"]["quantity"] == 624
    assert by_desc["Traffic Control"]["item_code"] == "634.0110"
    assert by_desc["Type 3 Barricade, 8' Double Sided"]["quantity"] == 13
    assert by_desc["Winter Maintenance"]["quantity"] == 1
    assert by_desc["Remove Fence"]["quantity"] == 120
    assert "42 in Channelizer" not in by_desc
    assert "Watermain Trench Excavation" not in by_desc
    assert "Filtered" in (result.get("notes") or result.get("summary") or "")


def test_extraction_has_bid_schedule_detects_eoq_text():
    assert extraction_has_bid_schedule(
        {"texts": [{"text": "See Estimate Of Quantities sheet for pay items"}]}
    )
    assert not extraction_has_bid_schedule({"texts": [{"text": "8\" WM"}]})
