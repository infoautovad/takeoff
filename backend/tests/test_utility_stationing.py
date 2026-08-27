"""Tests for centerline utility stationing + bid-summary Excel sheets."""

from io import BytesIO

from openpyxl import load_workbook

from app.services.cad.utility_stationing import (
    build_bid_summary_from_detail,
    build_utilities_detail,
    feet_to_station,
    format_offset,
    station_to_feet,
)


def test_station_roundtrip():
    assert station_to_feet("10+50") == 1050.0
    assert feet_to_station(1050) == "10+50"


def test_p_cl_name_detection_and_hydration():
    from app.services.cad.utility_stationing import _is_centerline_name, build_utilities_detail

    assert _is_centerline_name("P_CL 50th Street")
    assert _is_centerline_name("P_WATER") is False

    # Alignment name without points + polyline on same layer WITH points
    cl_pts = [[0, 0], [400, 0]]
    pipe_pts = [[50, 15], [200, 15]]
    extraction = {
        "alignments": [{"name": "P_CL 50th Street", "layer": "P_CL 50th Street", "length": 400}],
        "polylines": [
            {"layer": "P_CL 50th Street", "points": cl_pts, "length": 400},
            {"layer": "P_WATER", "name": "8in", "points": pipe_pts, "length": 150},
        ],
        "pipes": [],
        "blocks": [],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    assert detail["alignment"]["has_geometry"]
    water = [s for s in detail["segments"] if "Water" in str(s.get("utility"))]
    assert water
    assert water[0]["from_station"]
    assert water[0]["to_station"]
    assert water[0]["side"] in {"LT", "RT", "CL"}
    assert water[0]["offset"]


def test_pipe_station_attributes_without_xy():
    extraction = {
        "alignments": [{"name": "P_CL 50th Street", "length": 2000, "sta_start": "0+00"}],
        "polylines": [],
        "pipes": [
            {
                "name": "WM-1",
                "layer": "P_WATER",
                "length": 250,
                "diameter": 8,
                "network": "water",
                "sta_start": "10+00",
                "sta_end": "12+50",
                "side": "LT",
                "offset": 15.0,
            }
        ],
        "blocks": [],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    segs = detail["segments"]
    assert segs
    assert segs[0]["from_station"] in {"10+00", "10+00.00"}
    assert segs[0]["to_station"] in {"12+50", "12+50.00"}
    assert segs[0]["side"] == "LT"
    assert "15.0" in str(segs[0]["offset"])


def test_offset_label_lt_rt():
    assert format_offset(18.5, "LT") == "18.5' LT"
    assert format_offset(19.2, "Right") == "19.2' RT"


def test_text_station_segments():
    extraction = {
        "texts": [
            {"layer": "NOTES", "text": '8" WATER MAIN STA 10+00 TO 12+50'},
            {"layer": "NOTES", "text": '12" SANITARY SEWER STA 5+00 TO 7+25'},
        ],
        "polylines": [],
        "pipes": [],
        "blocks": [],
        "alignments": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    assert detail["summary"]["segment_count"] >= 2
    utilities = {s["utility"] for s in detail["segments"]}
    assert "Water Main" in utilities
    assert "Sanitary Sewer" in utilities
    water = next(s for s in detail["segments"] if "Water" in s["utility"])
    assert water["quantity_lf"] == 250.0


def test_fitting_station_side_offset_from_insert():
    extraction = {
        "alignments": [
            {"name": "P_CL 50th Street", "points": [[0, 0], [500, 0]], "length": 500, "sta_start": "0+00"}
        ],
        "polylines": [
            {"layer": "P_WATER", "name": '8"', "points": [[50, 18], [200, 18]], "length": 150},
        ],
        "pipes": [],
        "blocks": [
            {
                "name": "TEE_8x8",
                "layer": "P_WATER",
                "type": "Fitting",
                "insert": [100, 18],
            },
            {
                "name": "GV-8",
                "layer": "P_WATER",
                "type": "Valve",
                "station": "2+50",
                "side": "LT",
                "offset": 15.0,
            },
        ],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    conns = detail["connections"]
    assert conns
    tee = next(c for c in conns if "Tee" in str(c.get("type")) or "tee" in str(c.get("name")).lower())
    assert tee["station"]
    assert tee["side"] in {"LT", "RT", "CL"}
    assert tee["offset"]
    valve = next(c for c in conns if "Valve" in str(c.get("type")))
    assert valve["station"] in {"2+50", "2+50.00"}
    assert valve["side"] == "LT"
    assert "15" in str(valve["offset"])


def test_fitting_side_inferred_from_pipe_run():
    extraction = {
        "alignments": [
            {"name": "P_CL 50th Street", "points": [[0, 0], [400, 0]], "length": 400, "sta_start": 0}
        ],
        "polylines": [
            {"layer": "P_WATER", "name": "8in", "points": [[0, 12], [300, 12]], "length": 300},
        ],
        "pipes": [],
        "blocks": [
            {
                "name": "BEND45",
                "layer": "P_WATER",
                "type": "Bend",
                "station": "1+50",
                # no insert / side / offset — should infer from water run
            }
        ],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    bend = next(c for c in detail["connections"] if "Bend" in str(c.get("type")))
    assert bend["station"]
    assert bend["side"] in {"LT", "RT", "CL"}
    assert bend["offset"]


def test_cl_projection_lt_rt_and_nonparallel():
    # Centerline along +X
    alignment_pts = [[0, 0], [500, 0]]
    # Parallel pipe on +Y (LT when traveling +X)
    parallel = [[100, 10], [200, 10]]
    # Non-parallel: offset shrinks
    skewed = [[300, 22], [380, 6]]
    extraction = {
        "texts": [],
        "alignments": [
            {
                "name": "6TH STREET CL",
                "points": alignment_pts,
                "length": 500,
                "sta_start": "0+00",
            }
        ],
        "polylines": [
            {"layer": "STORM_12", "name": "12in Storm", "points": parallel, "length": 0},
            {"layer": "STORM_12", "name": "12in Storm skew", "points": skewed, "length": 0},
            {
                "layer": "WATER_MAIN",
                "name": "8in WM",
                "points": [[100, 10], [200, 10], [200, 40], [300, 40]],
                "length": 0,
            },
        ],
        "pipes": [],
        "blocks": [
            {
                "name": "BEND_12_45",
                "layer": "STORM_FITTINGS",
                "type": "Bend",
                "insert": [200, 10],
                "size": '12"',
            }
        ],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    assert detail["alignment"]["is_centerline"] or "CL" in str(detail["alignment"]["name"])
    assert detail["summary"]["segment_count"] >= 2

    parallel_rows = [s for s in detail["segments"] if s.get("from_station") and not s.get("nonparallel")]
    assert parallel_rows
    assert parallel_rows[0]["side"] in {"LT", "RT", "CL"}

    skew_rows = [s for s in detail["segments"] if s.get("nonparallel")]
    assert skew_rows
    assert skew_rows[0]["from_offset"]
    assert skew_rows[0]["to_offset"]

    assert detail["summary"]["connection_count"] >= 1
    assert detail["bid_summary"]
    # Bid summary LF should equal sum of segment LF for storm/water
    total_detail = sum(float(s["quantity_lf"]) for s in detail["segments"])
    total_summary_lf = sum(
        float(b["quantity"]) for b in detail["bid_summary"] if str(b.get("unit")).upper() == "LF"
    )
    assert abs(total_detail - total_summary_lf) < 0.2


def test_bid_summary_from_detail_rollup():
    segments = [
        {"item": "Storm Sewer", "utility": "Storm Sewer", "size": '12"', "quantity_lf": 250},
        {"item": "Storm Sewer", "utility": "Storm Sewer", "size": '12"', "quantity_lf": 235},
        {"item": "Storm Sewer", "utility": "Storm Sewer", "size": '12"', "quantity_lf": 275},
    ]
    connections = [
        {"type": "Bend", "angle": "45°", "size": '12"', "utility": "Storm Sewer", "quantity": 1},
        {"type": "Bend", "angle": "45°", "size": '12"', "utility": "Storm Sewer", "quantity": 1},
        {"type": "Bend", "angle": "22.5°", "size": '12"', "utility": "Storm Sewer", "quantity": 1},
        {"type": "Manhole", "size": "", "utility": "Storm Sewer", "quantity": 1},
    ]
    summary = build_bid_summary_from_detail(segments, connections)
    storm = next(r for r in summary if r["unit"] == "LF" and "Storm" in r["description"])
    assert abs(float(storm["quantity"]) - 760) < 0.01
    bends_45 = next(r for r in summary if r["unit"] == "EA" and "45" in r["description"])
    assert float(bends_45["quantity"]) == 2


def test_excel_civil_sheets():
    from app.models.eoq import EOQ, EOQItem, EOQItemStatus, EOQStatus
    from app.services.eoq_service import export_eoq_excel

    eoq = EOQ(
        id=1,
        project_id=1,
        title="Test EOQ",
        version=1,
        status=EOQStatus.AI_GENERATED,
        currency="USD",
        notes="",
    )
    eoq.items = [
        EOQItem(
            id=1,
            eoq_id=1,
            item_number="1",
            description='12" Storm Sewer',
            unit="LF",
            quantity=760,
            status=EOQItemStatus.NEEDS_REVIEW,
            confidence=90,
        )
    ]
    detail = {
        "alignment": {"name": "CL — 6TH STREET", "is_centerline": True},
        "alignments": [{"name": "CL — 6TH STREET"}],
        "segments": [
            {
                "item": "Storm Sewer",
                "size": '12"',
                "from_station": "10+25",
                "to_station": "12+75",
                "side": "RT",
                "offset": "18.5' RT",
                "from_offset": "",
                "to_offset": "",
                "length": 250,
                "quantity_lf": 250,
                "nonparallel": False,
                "alignment": "CL — 6TH STREET",
                "layer": "STORM",
                "source": "test",
            },
            {
                "item": "Storm Sewer",
                "size": '12"',
                "from_station": "14+25",
                "to_station": "15+05",
                "side": "RT",
                "offset": "",
                "from_offset": "22.0' RT",
                "to_offset": "6.0' RT",
                "length": 82,
                "quantity_lf": 82,
                "nonparallel": True,
                "alignment": "CL — 6TH STREET",
                "layer": "STORM",
                "source": "test",
            },
        ],
        "connections": [
            {
                "type": "Bend",
                "size": '12"',
                "station": "12+75",
                "side": "RT",
                "offset": "18.5' RT",
                "angle": "45°",
                "connects_to": '12" Storm Sewer',
                "utility": "Storm Sewer",
                "quantity": 1,
                "alignment": "CL — 6TH STREET",
                "layer": "FITTINGS",
                "source": "test",
            }
        ],
        "bid_summary": [],
        "qa_flags": [
            {
                "severity": "medium",
                "issue": "centerline_proxy",
                "message": "check CL",
                "object": "CL",
                "station": "",
                "suggestion": "verify",
            }
        ],
    }
    content = export_eoq_excel(eoq, utilities_detail=detail)
    wb = load_workbook(BytesIO(content))
    assert "Estimate Of Quantities" in wb.sheetnames
    assert "Bid Quantity Summary" in wb.sheetnames
    assert "Linear Quantity Breakdown" in wb.sheetnames
    assert "Fittings Bends Connections" in wb.sheetnames
    assert "Quantity QAQC" in wb.sheetnames
    # Summary rolled from detail on export merge path — here we pass bid_summary empty
    # so export rebuilds via load path only; direct export uses provided detail as-is
    # Linear sheet should show storm row
    assert wb["Linear Quantity Breakdown"]["A2"].value == "Storm Sewer"
    assert wb["Linear Quantity Breakdown"]["E2"].value == "RT"
    assert wb["Fittings Bends Connections"]["A2"].value == "Bend"
    assert wb["Fittings Bends Connections"]["F2"].value == "45°"


def test_excel_status_colors_come_from_conditional_formatting():
    """Dropdown Verified ↔ Engineer Review must change fill and font, not only text color."""
    from app.models.eoq import EOQ, EOQItem, EOQItemStatus, EOQStatus
    from app.services.eoq_service import EOQ_EXPORT_HEADERS, export_eoq_excel

    eoq = EOQ(
        id=1,
        project_id=1,
        title="Status CF",
        version=1,
        status=EOQStatus.AI_GENERATED,
        currency="USD",
        notes="",
    )
    eoq.items = [
        EOQItem(
            id=1,
            eoq_id=1,
            item_number="1",
            description="Needs review row",
            unit="LS",
            quantity=1,
            status=EOQItemStatus.NEEDS_REVIEW,
            confidence=80,
        ),
        EOQItem(
            id=2,
            eoq_id=1,
            item_number="2",
            description="Verified row",
            unit="LS",
            quantity=1,
            status=EOQItemStatus.VERIFIED,
            confidence=99,
        ),
    ]
    wb = load_workbook(BytesIO(export_eoq_excel(eoq)))
    ws = wb["Estimate Of Quantities"]
    status_col = EOQ_EXPORT_HEADERS.index("Status") + 1
    statuses = []
    for row in ws.iter_rows(min_row=3, min_col=status_col, max_col=status_col):
        cell = row[0]
        if cell.value in {"Verified", "Engineer Review"}:
            statuses.append(cell.value)
            assert cell.fill.patternType is None, "baked-in fill blocks Excel from swapping the box color"
    assert "Verified" in statuses
    assert "Engineer Review" in statuses

    rules = [rule for rules in ws.conditional_formatting._cf_rules.values() for rule in rules]
    assert len(rules) >= 2
    assert all(rule.dxf is not None and rule.dxf.fill is not None for rule in rules)
    assert all(rule.dxf is not None and rule.dxf.font is not None for rule in rules)


def test_excel_unit_column_shows_sqft_and_ton():
    from app.models.eoq import EOQ, EOQItem, EOQItemStatus, EOQStatus
    from app.services.eoq_service import EOQ_EXPORT_HEADERS, export_eoq_excel

    eoq = EOQ(
        id=1,
        project_id=1,
        title="Units",
        version=1,
        status=EOQStatus.AI_GENERATED,
        currency="USD",
        notes="",
    )
    eoq.items = [
        EOQItem(
            id=1,
            eoq_id=1,
            item_number="1",
            description="Traffic Control",
            unit="SF",
            quantity=624,
            status=EOQItemStatus.NEEDS_REVIEW,
            confidence=90,
        ),
        EOQItem(
            id=2,
            eoq_id=1,
            item_number="2",
            description="HMA Pavement",
            unit="T",
            quantity=12,
            status=EOQItemStatus.NEEDS_REVIEW,
            confidence=90,
        ),
        EOQItem(
            id=3,
            eoq_id=1,
            item_number="3",
            description="Water Main",
            unit="LF",
            quantity=100,
            status=EOQItemStatus.NEEDS_REVIEW,
            confidence=90,
        ),
    ]
    wb = load_workbook(BytesIO(export_eoq_excel(eoq)))
    ws = wb["Estimate Of Quantities"]
    unit_col = EOQ_EXPORT_HEADERS.index("Unit") + 1
    desc_col = EOQ_EXPORT_HEADERS.index("Item Description") + 1
    by_desc = {}
    for row in ws.iter_rows(min_row=3, max_col=max(unit_col, desc_col)):
        desc = row[desc_col - 1].value
        if desc in {"Traffic Control", "HMA Pavement", "Water Main"}:
            by_desc[desc] = row[unit_col - 1].value
    assert by_desc["Traffic Control"] == "SQFT"
    assert by_desc["HMA Pavement"] == "TON"
    assert by_desc["Water Main"] == "LF"


def test_civil_raw_station_and_signed_offset():
    from app.services.cad.civil_location import (
        coerce_station,
        civil_signed_offset,
        location_from_property_bag,
        parse_station_offset_text,
    )

    assert coerce_station(548.11) == "5+48.11"
    assert coerce_station("raw 50.27") == ""  # not a bare number / plus-station
    assert coerce_station("50.27") == "0+50.27"
    side, off = civil_signed_offset(-15.2)
    assert side == "LT" and off == 15.2
    side, off = civil_signed_offset(12.0)
    assert side == "RT" and off == 12.0

    parsed = parse_station_offset_text("8\" GATE VALVE STA 6+19.26 12.5' LT")
    assert parsed["station"] == "6+19.26"
    assert parsed["side"] == "LT"
    assert parsed["offset_ft"] == 12.5

    bag = location_from_property_bag(
        {
            "rawStation": 619.26,
            "Offset": -12.5,
            "Easting": 5000.0,
            "Northing": 2000.0,
        }
    )
    assert bag["station"] == "6+19.26"
    assert bag["side"] == "LT"
    assert bag["offset_ft"] == 12.5
    assert bag["insert"] == [5000.0, 2000.0]


def test_fitting_from_block_attributes_and_sheet_label():
    extraction = {
        "alignments": [
            {"name": "P_CL 50th Street", "points": [[0, 0], [800, 0]], "length": 800, "sta_start": "0+00"}
        ],
        "polylines": [],
        "pipes": [],
        "blocks": [
            {
                "name": "GV",
                "layer": "P_WATER",
                "type": "Valve",
                "attributes": {"STA": "5+48.11", "SIDE": "RT", "OFFSET": "8.2"},
            },
            {
                "name": "TEE",
                "layer": "P_WATER",
                "type": "Tee",
            },
        ],
        "texts": [
            {
                "layer": "ANNOTATION",
                "text": "8\" TEE STA 2+50.00 15.0' LT",
                "space": "paper",
            }
        ],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    valve = next(c for c in detail["connections"] if "Valve" in str(c.get("type")))
    assert valve["station"] in {"5+48.11", "5+48"}
    assert valve["side"] == "RT"
    assert "8.2" in str(valve["offset"])
    tee = next(c for c in detail["connections"] if "Tee" in str(c.get("type")))
    assert tee["station"]
    assert tee["side"] == "LT"
    assert tee["offset"]


def test_fitting_stationoffset_from_insert_xy():
    """Civil Alignment.StationOffset on insert coordinates."""
    extraction = {
        "alignments": [
            {"name": "P_CL 50th Street", "points": [[0, 0], [1000, 0]], "length": 1000, "sta_start": 0}
        ],
        "polylines": [],
        "pipes": [],
        "blocks": [
            {
                "name": "BEND_45",
                "layer": "0",
                "type": "Bend / Elbow",
                "insert": [548.11, -8.2],
            }
        ],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    bend = next(c for c in detail["connections"] if "Bend" in str(c.get("type")))
    assert bend["station"] == "5+48.11"
    assert bend["side"] == "RT"
    assert "8.2" in str(bend["offset"])


def test_linear_from_civil_start_station_and_length():
    extraction = {
        "alignments": [{"name": "P_CL 50th Street", "length": 2000, "sta_start": "0+00"}],
        "polylines": [],
        "pipes": [
            {
                "name": "WM-1",
                "layer": "P_WATER",
                "length": 190.81,
                "diameter": 8,
                "network": "water",
                "sta_start": "1+78.35",
            }
        ],
        "blocks": [],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    water = next(s for s in detail["segments"] if "Water" in str(s.get("utility")))
    assert water["from_station"]
    assert water["to_station"]
    assert station_to_feet(water["from_station"]) == station_to_feet("1+78.35")
    span = abs(station_to_feet(water["to_station"]) - station_to_feet(water["from_station"]))
    assert abs(span - 190.81) < 0.2


def test_linear_from_start_end_structures():
    extraction = {
        "alignments": [{"name": "P_CL 50th Street", "length": 2000}],
        "polylines": [],
        "pipes": [
            {
                "name": "STM-12",
                "layer": "0",
                "length": 250,
                "diameter": 12,
                "network": "storm",
                "start_structure": "CB-1",
                "end_structure": "MH-2",
            }
        ],
        "blocks": [
            {"name": "CB-1", "layer": "P_STORM", "type": "Inlet", "station": "2+00", "side": "LT", "offset": 12},
            {"name": "MH-2", "layer": "P_STORM", "type": "Manhole", "station": "4+50", "side": "LT", "offset": 12},
        ],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    storm = next(s for s in detail["segments"] if "Storm" in str(s.get("utility")))
    assert storm["from_station"] in {"2+00", "2+00.00"}
    assert storm["to_station"] in {"4+50", "4+50.00"}
    assert storm["side"] == "LT"
    assert "12" in str(storm["offset"])


def test_linear_from_fitting_station_span():
    """APS pipe has length only — pair fittings whose station delta ≈ length."""
    extraction = {
        "alignments": [
            {"name": "P_CL 50th Street", "points": [[0, 0], [1000, 0]], "length": 1000, "sta_start": 0}
        ],
        "polylines": [
            {"layer": "P_WATER", "name": "8in", "length": 200, "points": []},
        ],
        "pipes": [],
        "blocks": [
            {"name": "TEE", "layer": "P_WATER", "type": "Tee", "station": "1+00", "side": "LT", "offset": 15},
            {"name": "GV", "layer": "P_WATER", "type": "Valve", "station": "3+00", "side": "LT", "offset": 15},
        ],
        "texts": [],
        "lines": [],
    }
    detail = build_utilities_detail(extraction)
    water = next(s for s in detail["segments"] if "Water" in str(s.get("utility")))
    assert water["from_station"]
    assert water["to_station"]
    assert water["side"] == "LT"
    assert water["offset"]


def test_aps_style_xy_and_x_y_keys():
    from app.services.cad.civil_location import point_from_property_bag, useful_property_attr

    assert useful_property_attr("X")
    assert useful_property_attr("Side")
    assert useful_property_attr("Insert X")
    pt = point_from_property_bag({"X": 100.5, "Y": 20.0})
    assert pt == [100.5, 20.0]
    pt = point_from_property_bag({"Position": "5123.4, 6789.1, 12.0"})
    assert pt[0] == 5123.4 and pt[1] == 6789.1
