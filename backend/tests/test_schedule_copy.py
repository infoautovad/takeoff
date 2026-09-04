"""When a Bid Items / EOQ table exists, copy it and do not invent F-sheet extras."""

from app.services.ai_analysis import (
    _CODE_COL_NAMES,
    _DESC_COL_NAMES,
    _QTY_COL_NAMES,
    _analyze_pdf_drawings_with_vision,
    _analyze_heuristic,
    _content_has_eoq_schedule,
    _finalize_analysis,
    _find_col,
    _has_authoritative_schedule,
    _is_bid_schedule_table,
    _items_from_openai_payload,
    _is_plan_device_table,
)
from app.services.extractors import ExtractedContent
from app.services.civil_estimator import extraction_has_bid_schedule
from app.services.eoq_groups import assign_group_category


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
                    "description": "8-Inch Water Main",
                    "unit": "Ft",
                    "quantity": 245,
                    "confidence": 94,
                    "calculation_method": "OpenAI vision — engineering drawing sheet",
                    "source_reference": "Plan/profile sheet",
                },
                {
                    "description": "Fire Hydrant",
                    "unit": "Each",
                    "quantity": 4,
                    "confidence": 91,
                    "calculation_method": "OpenAI vision — engineering drawing sheet",
                },
                {
                    "description": "Concrete Curb and Gutter",
                    "unit": "Ft",
                    "quantity": 620,
                    "confidence": 92,
                    "calculation_method": "OpenAI vision — plan sheet",
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
    assert by_desc["8-Inch Water Main"]["quantity"] == 245
    assert by_desc["Fire Hydrant"]["quantity"] == 4
    assert by_desc["Concrete Curb and Gutter"]["quantity"] == 620
    assert "42 in Channelizer" not in by_desc
    assert "Watermain Trench Excavation" not in by_desc


def test_extraction_has_bid_schedule_detects_eoq_text():
    assert extraction_has_bid_schedule(
        {"texts": [{"text": "See Estimate Of Quantities sheet for pay items"}]}
    )
    assert not extraction_has_bid_schedule({"texts": [{"text": "8\" WM"}]})


def test_f2_itemized_list_is_not_the_bid_schedule():
    """F-sheet device lists must not starve the rest of the bid list."""
    f2 = {
        "page": 8,
        "rows": [
            ["Item Description", "Unit", "Qty"],
            ["TYPE 3 BARRICADES, 8' DOUBLE SIDED", "EA", "12"],
            ["TRAFFIC CONTROL MISCELLANEOUS", "LS", "1"],
            ["Traffic Control", "SQFT", "149"],
        ],
    }
    earthwork = {
        "page": 3,
        "rows": [
            ["Description", "Unit", "Quantity"],
            ["Earthwork Cut", "M3", "50"],
        ],
    }
    assert not _is_bid_schedule_table(f2)
    assert not _is_bid_schedule_table(earthwork)
    content = ExtractedContent(
        text="SHEET F2  ITEMIZED LIST FOR TRAFFIC CONTROL\nITEM DESCRIPTION  UNIT  QTY",
        tables=[f2, earthwork],
    )
    assert not _content_has_eoq_schedule(content)


def test_heuristic_still_takes_off_when_bid_language_but_no_table():
    """Mentioning Bid Items in notes must not suppress plan takeoff if no table copied."""
    from app.services.ai_analysis import _pdf_has_copied_bid_table, _takeoff_is_thin

    content = ExtractedContent(
        text=(
            "See Bid Items sheet. EST. QTY listed separately.\n"
            "Earthwork Cut 50 m3 of excavation along the alignment.\n"
            "Asphalt 80 t on the typical section."
        ),
        tables=[],
        page_count=24,
    )
    assert not _pdf_has_copied_bid_table(content)
    result = _analyze_heuristic(filename="plans.pdf", content=content, document_id=1)
    descs = [str(i.get("description")) for i in result["items"]]
    assert any("Earthwork Cut" in d for d in descs)
    assert _takeoff_is_thin(
        [
            {"description": "Remove Storm Sewer", "quantity": 6},
            {"description": "Install 8 in. C900 PVC Watermain", "quantity": 94},
        ],
        content,
    )


def test_finalize_keeps_core_pay_items_when_only_f2_list_exists():
    """Regression: F2 + vision default method used to drop water/paving/curb (5–10 items)."""
    content = ExtractedContent(
        text="SHEET F2 ITEMIZED LIST FOR TRAFFIC CONTROL. ITEM DESCRIPTION UNIT QTY.",
        tables=[
            {
                "page": 8,
                "rows": [
                    ["Item Description", "Unit", "Qty"],
                    ["TYPE 3 BARRICADES, 8' DOUBLE SIDED", "EA", "12"],
                    ["TRAFFIC CONTROL MISCELLANEOUS", "LS", "1"],
                ],
            }
        ],
    )
    vision_items = [
        {
            "description": "Mobilization",
            "unit": "LS",
            "quantity": 1,
            "confidence": 97,
            "calculation_method": "Standard lump-sum pay item",
            "source_reference": "General items",
        },
        {
            "description": "TYPE 3 BARRICADES, 8' DOUBLE SIDED",
            "unit": "EA",
            "quantity": 12,
            "confidence": 98,
            "calculation_method": "Extracted from Traffic Control bid list",
            "source_reference": "F2, ITEMIZED LIST FOR TRAFFIC CONTROL",
        },
        {
            "description": "8-Inch Water Main",
            "unit": "Ft",
            "quantity": 245,
            "confidence": 94,
            "calculation_method": "OpenAI vision — engineering drawing sheet",
            "source_reference": "Plan sheet P4",
        },
        {
            "description": "Asphalt Concrete Pavement",
            "unit": "Ton",
            "quantity": 180,
            "confidence": 93,
            "calculation_method": "OpenAI vision — engineering drawing sheet",
        },
        {
            "description": "Concrete Curb and Gutter",
            "unit": "Ft",
            "quantity": 620,
            "confidence": 92,
            "calculation_method": "OpenAI vision — engineering drawing sheet",
        },
        {
            "description": "Fire Hydrant",
            "unit": "Each",
            "quantity": 4,
            "confidence": 91,
            "calculation_method": "OpenAI vision — plan sheet",
        },
        {
            "description": "Remove Storm Sewer",
            "unit": "Ft",
            "quantity": 6,
            "calculation_method": "Extracted from explicit plan callout",
            "source_reference": "Plan callout: REMOVE STORM SEWER",
        },
    ]
    assert not _has_authoritative_schedule(content, vision_items)
    result = _finalize_analysis(
        {"engine": "openai+vision", "summary": "vision mix", "items": vision_items},
        content=content,
    )
    by_desc = {str(i.get("description")): i for i in result["items"]}
    assert "8-Inch Water Main" in by_desc
    assert by_desc["8-Inch Water Main"]["quantity"] == 245
    assert "Asphalt Concrete Pavement" in by_desc
    assert "Concrete Curb and Gutter" in by_desc
    assert "Fire Hydrant" in by_desc
    assert "Remove Storm Sewer" in by_desc
    assert "TYPE 3 BARRICADES, 8' DOUBLE SIDED" in by_desc
    assert len(result["items"]) >= 6


def test_strict_schedule_transcription_preserves_blank_cells_and_categories():
    table = {
        "page": 2,
        "rows": [
            ["ITEM NUMBER", "BID ITEM", "DESCRIPTION", "UNITS", "EST. QTY"],
            ["", "", "General", "", ""],
            ["6", "0550", "Tax on City Furnished Materials", "", ""],
            ["", "", "Roadway", "", ""],
            ["7", "201.001", "Unclassified Excavation", "CY", "1200"],
        ],
    }
    content = ExtractedContent(text="Bid Items table", tables=[table])
    result = _analyze_heuristic(filename="plans.pdf", content=content, document_id=1)

    tax = next(i for i in result["items"] if str(i.get("item_code") or "") == "0550")
    excav = next(i for i in result["items"] if "Unclassified Excavation" in str(i.get("description") or ""))

    assert tax["description"] == "Tax on City Furnished Materials"
    assert tax["category"] == "General"
    assert tax.get("raw_unit") == ""
    assert tax.get("raw_quantity") == ""
    assert bool(tax.get("quantity_blank")) is True
    assert float(tax["quantity"]) == 0.0
    assert tax.get("status") == "needs_review"

    assert excav["category"] == "Roadway"
    assert str(excav.get("unit") or "").upper() in {"CY", "CUYD"}
    assert float(excav["quantity"]) == 1200.0


def test_non_standard_grid_headers_are_not_treated_as_bid_schedule():
    table = {
        "page": 4,
        "rows": [
            ["Description", "Unit", "Quantity"],
            ["Company Name", "", ""],
            ["Tax on City Furnished Materials", "", ""],
        ],
    }
    content = ExtractedContent(text="", tables=[table])
    result = _analyze_heuristic(filename="plans.pdf", content=content, document_id=1)
    assert not result["items"]


def test_schedule_header_row_can_appear_after_title_row():
    table = {
        "page": 2,
        "rows": [
            ["General Items", "", "", "", ""],
            ["ITEM NUMBER", "BID ITEM", "DESCRIPTION", "UNITS", "EST. QTY"],
            ["1", "9.0010", "Mobilization", "LS", "1"],
        ],
    }
    content = ExtractedContent(text="Estimate Of Quantities", tables=[table])
    assert _is_bid_schedule_table(table)
    result = _analyze_heuristic(filename="plans.pdf", content=content, document_id=1)
    by_desc = {str(i.get("description")): i for i in result["items"]}
    assert by_desc["Mobilization"]["item_code"] == "9.0010"


def test_category_header_detected_when_label_is_not_in_description_column():
    table = {
        "page": 3,
        "rows": [
            ["ITEM NUMBER", "BID ITEM", "DESCRIPTION", "UNITS", "EST. QTY"],
            ["General Items", "", "", "", ""],
            ["1", "9.0010", "Mobilization", "LS", "1"],
            ["Water Main Items", "", "", "", ""],
            ["2", "9.2000", "Install City Furnished 6 in. C900 DR18 PVC Water Main", "LF", "463"],
        ],
    }
    content = ExtractedContent(text="Estimate Of Quantities", tables=[table])
    result = _analyze_heuristic(filename="plans.pdf", content=content, document_id=1)
    by_desc = {str(i.get("description")): i for i in result["items"]}
    assert by_desc["Mobilization"]["category"] == "General Items"
    assert by_desc["Install City Furnished 6 in. C900 DR18 PVC Water Main"]["category"] == "Water Main Items"


def test_city_furnished_water_items_do_not_stick_to_general_group():
    water = assign_group_category(
        {
            "description": "Install City Furnished 6 in. C900 DR18 PVC Water Main",
            "category": "General",
        }
    )
    tax = assign_group_category(
        {
            "description": "Tax on City Furnished Materials",
            "category": "General",
        }
    )
    assert water["category"] == "Watermain"
    assert tax["category"] == "General"


def test_openai_payload_preserves_blank_schedule_cells():
    rows = _items_from_openai_payload(
        {
            "items": [
                {
                    "row_type": "schedule",
                    "item_number": "2",
                    "item_code": "9.0550",
                    "description": "Tax on City Furnished Materials",
                    "category": "General Items",
                    "unit": "",
                    "quantity": "",
                    "source_page": 1,
                    "source_reference": "Bid Items / EOQ table",
                    "calculation_method": "Extracted from Estimate Of Quantities schedule",
                }
            ]
        },
        filename="scan.pdf",
        document_id=1,
        default_method="OpenAI vision — plan sheet",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.get("table_transcribed") is True
    assert row.get("schedule_authoritative") is True
    assert row.get("item_code") == "9.0550"
    assert row.get("item_number") == "2"
    assert row.get("raw_unit") == ""
    assert row.get("raw_quantity") == ""
    assert row.get("unit_blank") is True
    assert row.get("quantity_blank") is True
    assert float(row.get("quantity") or 0) == 0.0


def test_vision_schedule_mode_suppresses_non_schedule_and_rereads_missing_codes(monkeypatch, tmp_path):
    import fitz

    from app.services.extractors import PageText

    pdf_path = tmp_path / "one_page_schedule.pdf"
    doc = fitz.open()
    try:
        doc.new_page(width=1000, height=700)
        doc.save(pdf_path)
    finally:
        doc.close()

    responses = [
        {
            "summary": "Schedule found on page 1",
            "facts": [{"key": "eoq_table_found", "value": "true", "source_page": 1}],
            "items": [
                {
                    "row_type": "schedule",
                    "item_number": "1",
                    "item_code": "9.0010",
                    "description": "Mobilization",
                    "category": "General Items",
                    "unit": "LS",
                    "quantity": "1",
                    "source_page": 1,
                    "source_reference": "Bid Items / EOQ table",
                    "calculation_method": "Extracted from Estimate Of Quantities schedule",
                },
                {
                    "row_type": "schedule",
                    "item_number": "2",
                    "item_code": "",
                    "description": "Tax on City Furnished Materials",
                    "category": "General Items",
                    "unit": "LS",
                    "quantity": "",
                    "source_page": 1,
                    "source_reference": "Bid Items / EOQ table",
                    "calculation_method": "Extracted from Estimate Of Quantities schedule",
                },
                {
                    "row_type": "other",
                    "description": "Install City Furnished 6 in. C900 DR18 PVC Water Main",
                    "category": "Water Main",
                    "unit": "LF",
                    "quantity": "463",
                    "source_page": 1,
                    "source_reference": "Plan callout",
                    "calculation_method": "Directly extracted from printed callout",
                },
            ],
            "needs_review": True,
        },
        {
            "summary": "Focused schedule reread",
            "facts": [{"key": "eoq_table_found", "value": "true", "source_page": 1}],
            "items": [
                {
                    "row_type": "schedule",
                    "item_number": "1",
                    "item_code": "9.0010",
                    "description": "Mobilization",
                    "category": "General Items",
                    "unit": "LS",
                    "quantity": "1",
                    "source_page": 1,
                    "source_reference": "Bid Items / EOQ table",
                    "calculation_method": "Extracted from Estimate Of Quantities schedule",
                },
                {
                    "row_type": "schedule",
                    "item_number": "2",
                    "item_code": "9.0550",
                    "description": "Tax on City Furnished Materials",
                    "category": "General Items",
                    "unit": "LS",
                    "quantity": "",
                    "source_page": 1,
                    "source_reference": "Bid Items / EOQ table",
                    "calculation_method": "Extracted from Estimate Of Quantities schedule",
                },
            ],
            "needs_review": False,
        },
    ]
    calls: list[list[int]] = []

    def fake_vision_json(system: str, user: str, images: list[dict], temperature: float = 0.1):
        _ = (system, user, temperature)
        calls.append([int(img.get("page") or 0) for img in images])
        idx = min(len(calls) - 1, len(responses) - 1)
        return responses[idx]

    monkeypatch.setattr("app.services.openai_client.ask_openai_vision_json", fake_vision_json)

    content = ExtractedContent(
        text="",
        page_count=1,
        pages=[PageText(page=1, text="Estimate Of Quantities - Sheet B1")],
        tables=[],
    )
    vision = _analyze_pdf_drawings_with_vision(
        filename="one_page_schedule.pdf",
        content=content,
        document_id=99,
        pdf_path=pdf_path,
        max_pages=1,
        dpi=120,
        min_score=18.0,
        force_utility_pages=True,
        scan_all_pages=True,
        batch_pages=1,
    )

    by_desc = {str(i.get("description")): i for i in (vision.get("items") or [])}
    assert vision.get("schedule_mode_active") is True
    assert "Install City Furnished 6 in. C900 DR18 PVC Water Main" not in by_desc
    assert by_desc["Mobilization"]["item_code"] == "9.0010"
    assert by_desc["Tax on City Furnished Materials"]["item_code"] == "9.0550"
    assert by_desc["Tax on City Furnished Materials"].get("quantity_blank") is True
    assert len(calls) >= 2  # initial batch + focused reread


def test_openai_payload_detail_table_row_type_schedule_not_promoted():
    rows = _items_from_openai_payload(
        {
            "items": [
                {
                    "row_type": "schedule",
                    "description": 'Class M6 Concrete — 18" Dia. Outlet, Constant',
                    "category": "Storm Sewer",
                    "unit": "CY",
                    "quantity": "5.5",
                    "source_page": 12,
                    "source_reference": "Estimated Quantities table - 10' Long Inlet",
                    "calculation_method": "Extracted from Estimated Quantities table.",
                }
            ]
        },
        filename="plans.pdf",
        document_id=1,
        default_method="OpenAI vision — plan sheet",
    )
    assert len(rows) == 1
    row = rows[0]
    assert not bool(row.get("table_transcribed"))
    assert not bool(row.get("schedule_authoritative"))


def test_vision_detail_tables_do_not_lock_strict_schedule_mode(monkeypatch, tmp_path):
    import fitz

    from app.services.extractors import PageText

    pdf_path = tmp_path / "detail_tables.pdf"
    doc = fitz.open()
    try:
        doc.new_page(width=1000, height=700)
        doc.save(pdf_path)
    finally:
        doc.close()

    calls: list[list[int]] = []

    def fake_vision_json(system: str, user: str, images: list[dict], temperature: float = 0.1):
        _ = (system, user, temperature)
        calls.append([int(img.get("page") or 0) for img in images])
        return {
            "summary": "Estimated quantities detail table",
            "facts": [{"key": "eoq_table_found", "value": "true", "source_page": 1}],
            "items": [
                {
                    "row_type": "schedule",
                    "description": 'Class M6 Concrete — 18" Dia. Outlet, Constant',
                    "category": "Storm Sewer",
                    "unit": "CY",
                    "quantity": "5.5",
                    "source_page": 1,
                    "source_reference": "Estimated Quantities table - 10' Long Inlet",
                    "calculation_method": "Extracted from Estimated Quantities table.",
                },
                {
                    "row_type": "other",
                    "description": "Install City Furnished 6 in. C900 DR18 PVC Water Main",
                    "category": "Water Main",
                    "unit": "LF",
                    "quantity": "463",
                    "source_page": 1,
                    "source_reference": "Plan callout",
                    "calculation_method": "Directly extracted from printed callout",
                },
            ],
            "needs_review": True,
        }

    monkeypatch.setattr("app.services.openai_client.ask_openai_vision_json", fake_vision_json)

    content = ExtractedContent(
        text="",
        page_count=1,
        pages=[PageText(page=1, text="Plan detail sheet")],
        tables=[],
    )
    vision = _analyze_pdf_drawings_with_vision(
        filename="detail_tables.pdf",
        content=content,
        document_id=99,
        pdf_path=pdf_path,
        max_pages=1,
        dpi=120,
        min_score=18.0,
        force_utility_pages=True,
        scan_all_pages=True,
        batch_pages=1,
    )

    assert vision.get("schedule_mode_active") is False
    by_desc = {str(i.get("description")): i for i in (vision.get("items") or [])}
    assert 'Class M6 Concrete — 18" Dia. Outlet, Constant' in by_desc
    assert "Install City Furnished 6 in. C900 DR18 PVC Water Main" in by_desc
    assert len(calls) == 1  # no focused reread when strict schedule mode does not lock
