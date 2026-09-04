"""Civil estimator: typical sections, trench CY, merge, CAD expansion, label-only AI."""

from __future__ import annotations

from app.services.cad.quantity_engine import build_quantities
from app.services.civil_estimator import (
    detect_project_types,
    expand_cad_takeoff,
    items_from_design_text,
    merge_estimator_items,
    trench_items_from_pipes,
)
from app.services.openai_client import apply_cad_label_enrichment


def test_detect_project_types_road_dam_building():
    assert "road" in detect_project_types("typical section asphalt highway")
    assert "dam" in detect_project_types("earthfill dam spillway")
    assert "reservoir" in detect_project_types("reservoir lining geomembrane")
    assert "building" in detect_project_types("residential house floor plan")
    assert detect_project_types("random notes") == ["civil"]


def test_typical_section_pavement_cy_and_hma_tons():
    text = (
        "Road width 24 ft. Length 1000 ft. Typical section: "
        "HMA 3 in, aggregate base 8 in, prime coat and tack coat. Shoulder 4 ft."
    )
    items = items_from_design_text(text, filename="TS.pdf")
    by_desc = {i["description"]: i for i in items}
    hma = by_desc["Hot Mix Asphalt"]
    # 24 * (3/12) * 1000 / 27 = 222.22 CY
    assert abs(hma["quantity"] - 222.22) < 0.05
    assert hma["unit"] == "CY"
    tons = by_desc["Hot Mix Asphalt (HMA tons)"]
    assert tons["unit"] == "TON"
    assert abs(tons["quantity"] - 222.22 * 145 / 2000) < 0.05
    assert "Prime Coat" in by_desc
    assert by_desc["Prime Coat"]["unit"] == "SY"
    assert "Shoulder Area" in by_desc


def test_building_and_dam_text_quantities():
    text = (
        "Brickwork 120 cy. Doors 12 ea. Windows 8 each. "
        "Dam embankment 50000 cy. Spillway 800 cy. Reservoir lining 12000 sf."
    )
    items = items_from_design_text(text, filename="design.pdf")
    by_desc = {i["description"]: i for i in items}
    assert by_desc["Brickwork"]["quantity"] == 120
    assert by_desc["Doors"]["quantity"] == 12
    assert by_desc["Windows"]["quantity"] == 8
    assert by_desc["Dam Embankment Fill"]["quantity"] == 50000
    assert by_desc["Spillway Concrete"]["quantity"] == 800
    assert by_desc["Reservoir Lining"]["quantity"] == 12000


def test_trench_from_pipes_uses_cover_and_od():
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
        "polylines": [
            {"layer": "P_WATER", "length": 9999, "name": "should-not-double"},
        ],
    }
    items = trench_items_from_pipes(extraction)
    by_desc = {i["description"]: i for i in items}
    excav = by_desc["Watermain Trench Excavation"]
    od = 8 / 12.0
    width = max(od + 2.0, 2.5)
    depth = 4.0 + od + 0.5
    expected = width * depth * 270 / 27.0
    assert abs(excav["quantity"] - expected) < 0.05
    assert "cover assumed 4" in excav["calculation_method"].lower()
    # Polylines ignored when pipes exist — quantity is for 270 LF not 9999
    assert excav["quantity"] < 200


def test_merge_estimator_items_skips_duplicate_description_unit():
    base = [{"description": "8-Inch Water Main", "unit": "LF", "quantity": 500}]
    extra = [
        {"description": "8-Inch Water Main", "unit": "LF", "quantity": 12},
        {"description": "Watermain Trench Excavation", "unit": "CY", "quantity": 40},
    ]
    out = merge_estimator_items(base, extra)
    mains = [i for i in out if i["description"] == "8-Inch Water Main"]
    assert len(mains) == 1
    assert mains[0]["quantity"] == 500
    assert any(i["description"] == "Watermain Trench Excavation" for i in out)


def test_expand_cad_takeoff_keeps_pipe_lengths():
    extraction = {
        "pipes": [
            {
                "name": "WM-8",
                "layer": "P_WATER",
                "length": 500,
                "diameter": 8,
                "network": "water",
            }
        ],
        "polylines": [{"layer": "CURB", "length": 120}],
        "blocks": [{"name": "A-DOOR-1", "layer": "A-DOOR", "type": "door"}],
        "texts": [],
        "hatches": [],
        "lines": [],
        "surfaces": [],
        "volumes": [],
        "alignments": [],
    }
    base = [{"description": "8-Inch Water Main", "unit": "LF", "quantity": 500, "category": "Utilities"}]
    out = expand_cad_takeoff(extraction, base)
    main = next(i for i in out if i["description"] == "8-Inch Water Main")
    assert main["quantity"] == 500
    assert any("Trench Excavation" in str(i.get("description")) for i in out)
    assert any(i["description"] == "Concrete Curb and Gutter" and abs(i["quantity"] - 120) < 0.01 for i in out)


def test_build_quantities_gold_pipes_plus_trench():
    extraction = {
        "format": "synthetic",
        "units": "ft",
        "pipes": [
            {"name": "WM-8", "layer": "P_WATER", "length": 500, "diameter": 8, "network": "water"},
        ],
        "blocks": [],
        "surfaces": [],
        "lines": [],
        "polylines": [],
        "hatches": [],
        "alignments": [],
        "volumes": [],
        "texts": [],
    }
    items = build_quantities(extraction, source_label="t.dwg")
    main = next(i for i in items if "8-Inch Water Main" in str(i.get("description")) and str(i.get("unit")).upper() in {"LF", "FT"})
    assert abs(float(main["quantity"]) - 500) < 0.05
    assert any("Trench Excavation" in str(i.get("description")) for i in items)


def test_build_quantities_metric_units_convert_to_feet():
    extraction = {
        "format": "synthetic",
        "units": "m",
        "pipes": [
            {"name": "WM-8", "layer": "P_WATER", "length": 100, "diameter": 8, "network": "water"},
        ],
        "blocks": [],
        "surfaces": [],
        "lines": [],
        "polylines": [],
        "hatches": [],
        "alignments": [],
        "volumes": [],
        "texts": [],
    }
    items = build_quantities(extraction, source_label="metric.dwg")
    main = next(i for i in items if "8-Inch Water Main" in str(i.get("description")))
    assert abs(float(main["quantity"]) - 328.08) < 0.25
    assert "assumed feet" not in str(main.get("calculation_method") or "").lower()


def test_build_quantities_unitless_marks_scale_assumption_for_review():
    extraction = {
        "format": "synthetic",
        "units": "0",
        "pipes": [
            {"name": "WM-8", "layer": "P_WATER", "length": 100, "diameter": 8, "network": "water"},
        ],
        "blocks": [],
        "surfaces": [],
        "lines": [],
        "polylines": [],
        "hatches": [],
        "alignments": [],
        "volumes": [],
        "texts": [],
    }
    items = build_quantities(extraction, source_label="unitless.dwg")
    main = next(i for i in items if "8-Inch Water Main" in str(i.get("description")))
    assert "assumed feet" in str(main.get("calculation_method") or "").lower()
    assert float(main.get("confidence") or 0) <= 84.0
    assert bool(main.get("needs_review")) is True


def test_apply_cad_label_enrichment_never_changes_qty_or_count():
    original = [
        {"description": "Utility Pipe", "unit": "LF", "quantity": 500.0, "category": "Utilities", "confidence": 80},
        {"description": "Valve", "unit": "EA", "quantity": 2.0, "category": "Utilities", "confidence": 80},
    ]
    refined = [
        {"description": "8-Inch Water Main", "category": "Watermain", "quantity": 1, "unit": "EA", "confidence": 99},
        {"description": "Water Valve", "category": "Watermain", "quantity": 99, "unit": "LS"},
        {"description": "Invented Extra", "quantity": 7, "unit": "EA"},
    ]
    out = apply_cad_label_enrichment(original, refined)
    assert len(out) == 2
    assert out[0]["quantity"] == 500.0
    assert out[0]["unit"] == "LF"
    assert out[0]["description"] == "8-Inch Water Main"
    assert out[1]["quantity"] == 2.0
    assert out[1]["unit"] == "EA"
    assert out[1]["description"] == "Water Valve"


def test_apply_cad_label_enrichment_short_refined_keeps_tail():
    original = [
        {"description": "A", "unit": "LF", "quantity": 10.0},
        {"description": "B", "unit": "EA", "quantity": 3.0},
    ]
    out = apply_cad_label_enrichment(original, [{"description": "Renamed A"}])
    assert len(out) == 2
    assert out[0]["description"] == "Renamed A"
    assert out[1]["description"] == "B"
    assert out[1]["quantity"] == 3.0
