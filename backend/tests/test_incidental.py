"""Incidental-to-bid-item work is not a separate quantity and is not added to the parent."""

from app.services.ai_analysis import (
    _analyze_heuristic,
    _finalize_analysis,
    _prefer_schedule_quantity,
)
from app.services.civil_estimator import expand_cad_takeoff, items_from_design_text
from app.services.extractors import ExtractedContent
from app.services.incidental import (
    should_drop_incidental_item,
    skip_text_extraction,
)
from app.services.utility_labels import extract_utility_label_items


def _bid_table(*rows: list[str]) -> dict:
    header = ["Item Number", "Bid Item", "Description", "Units", "Est. Qty"]
    return {"page": 1, "rows": [header, *rows]}


def test_drop_incidental_child_but_keep_named_pay_item():
    assert should_drop_incidental_item(
        {
            "description": "Sand Bedding (incidental to watermain)",
            "unit": "CY",
            "quantity": 12,
        }
    )
    assert should_drop_incidental_item(
        {
            "description": "8-Inch 45 Degree Bend",
            "unit": "Each",
            "quantity": 6,
            "calculation_method": "Fittings incidental to water main",
        }
    )
    assert not should_drop_incidental_item(
        {
            "description": "Incidental Construction",
            "unit": "LS",
            "quantity": 1,
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        scheduled=True,
    )
    assert not should_drop_incidental_item(
        {
            "description": "Pipe Bedding",
            "unit": "CY",
            "quantity": 40,
            "item_code": "601.0200",
            "calculation_method": "Extracted from Bid Items / EOQ table",
        },
        scheduled=True,
        drop_default_extras=True,
    )


def test_skip_label_parent_name_and_incidental_fittings():
    assert skip_text_extraction(
        "8-Inch Water Main",
        'Fittings incidental to 8" WATER MAIN',
        match_start=len("Fittings incidental to "),
    )
    assert skip_text_extraction(
        "Water Valve",
        '6" GATE VALVE incidental to water main',
        match_start=0,
    )
    assert not skip_text_extraction(
        "8-Inch Water Main",
        '8" WATER MAIN 245 LF, bedding incidental to watermain',
        match_start=0,
    )


def test_utility_labels_do_not_take_off_incidental_work():
    text = (
        '8" WATER MAIN 245 LF\n'
        "Sand bedding incidental to watermain\n"
        '6" GATE VALVE incidental to water main\n'
        "Fittings incidental to 8\" WATER MAIN\n"
    )
    items = extract_utility_label_items(text, filename="plan.pdf", document_id=1)
    by_desc = {str(i["description"]): i for i in items}
    assert by_desc["8-Inch Water Main"]["quantity"] == 245
    assert not any("valve" in d.lower() for d in by_desc)
    assert not any("bedding" in d.lower() for d in by_desc)
    assert not any("bend" in d.lower() or "fitting" in d.lower() for d in by_desc)


def test_heuristic_skips_incidental_excavation_quantity():
    content = ExtractedContent(
        text="Excavation 12 cy incidental to pipe. Bituminous Concrete 50 cy.",
        tables=[],
    )
    result = _analyze_heuristic(filename="notes.pdf", content=content, document_id=1)
    by_desc = {str(i["description"]): i for i in result["items"]}
    assert "Earthwork Cut" not in by_desc
    assert by_desc["Bituminous Concrete"]["quantity"] == 50


def test_finalize_omits_incidentals_and_does_not_inflate_parent():
    content = ExtractedContent(
        text="Bid Items table with EST. QTY and BID ITEM columns.",
        tables=[
            _bid_table(
                ["1", "601.0100", "8-Inch Water Main", "Ft", "245"],
                ["2", "9.0010", "Incidental Construction", "LS", "1"],
            )
        ],
    )
    result = _finalize_analysis(
        {
            "engine": "openai+vision",
            "summary": "drawings",
            "items": [
                {
                    "description": "Sand Bedding",
                    "unit": "CuYd",
                    "quantity": 18,
                    "calculation_method": "Typical section — incidental to watermain",
                    "source_reference": "Detail 3",
                    "confidence": 90,
                },
                {
                    "description": "8-Inch 45 Degree Bend",
                    "unit": "Each",
                    "quantity": 6,
                    "calculation_method": "Fittings incidental to water main",
                    "confidence": 88,
                },
                {
                    "description": "Tracer Wire",
                    "unit": "Ft",
                    "quantity": 245,
                    "calculation_method": "OpenAI vision — engineering drawing sheet",
                    "confidence": 85,
                },
                {
                    "description": "8-Inch Water Main",
                    "unit": "Ft",
                    "quantity": 251,
                    "calculation_method": "Pipe LF plus 6 incidental fittings",
                    "source_reference": "Plan labels",
                    "confidence": 92,
                },
            ],
        },
        content=content,
    )
    by_desc = {str(i.get("description")): i for i in result["items"]}
    assert by_desc["8-Inch Water Main"]["quantity"] == 245
    assert by_desc["Incidental Construction"]["quantity"] == 1
    assert "Sand Bedding" not in by_desc
    assert not any("bend" in d.lower() for d in by_desc)
    assert "Tracer Wire" not in by_desc
    assert "incidental" in (result.get("notes") or result.get("summary") or "").lower()


def test_schedule_pipe_bedding_is_kept_when_it_is_a_bid_row():
    content = ExtractedContent(
        text="Bid Items EST. QTY BID ITEM",
        tables=[_bid_table(["1", "601.0200", "Pipe Bedding", "CY", "40"])],
    )
    result = _finalize_analysis({"items": []}, content=content)
    by_desc = {str(i.get("description")): i for i in result["items"]}
    assert by_desc["Pipe Bedding"]["quantity"] == 40


def test_prefer_schedule_does_not_take_incidental_inflated_qty():
    existing = {
        "description": "8-Inch Water Main",
        "unit": "Ft",
        "quantity": 245,
        "calculation_method": "Extracted from Estimate Of Quantities schedule",
        "confidence": 95,
    }
    candidate = {
        "description": "8-Inch Water Main",
        "unit": "Ft",
        "quantity": 251,
        "calculation_method": "Pipe LF plus 6 incidental fittings",
        "confidence": 97,
    }
    picked = _prefer_schedule_quantity(existing, candidate)
    assert picked["quantity"] == 245


def test_design_text_skips_incidental_excavation():
    items = items_from_design_text(
        "Dam excavation 500 cy incidental to embankment. Dam embankment 50000 cy.",
        filename="notes.pdf",
    )
    by_desc = {i["description"]: i for i in items}
    assert "Dam Excavation" not in by_desc
    assert by_desc["Dam Embankment Fill"]["quantity"] == 50000


def test_cad_trench_extras_skipped_when_notes_say_incidental():
    extraction = {
        "pipes": [
            {
                "name": "8-Inch Water Main",
                "layer": "P_WATER",
                "length": 270,
                "diameter": 8,
                "network": "water",
            }
        ],
        "polylines": [],
        "lines": [],
        "blocks": [],
        "texts": [
            {"text": "Trench excavation, bedding, and backfill shall be incidental to the pipe."}
        ],
        "hatches": [],
        "surfaces": [],
        "volumes": [],
        "alignments": [],
    }
    base = [{"description": "8-Inch Water Main", "unit": "LF", "quantity": 270, "category": "Utilities"}]
    out = expand_cad_takeoff(extraction, base)
    assert not any("Trench Excavation" in str(i.get("description")) for i in out)
    assert not any("Bedding" in str(i.get("description")) for i in out)
    main = next(i for i in out if i["description"] == "8-Inch Water Main")
    assert main["quantity"] == 270
