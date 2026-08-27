"""Similar pay items from different locations are combined into one quantity."""

from app.services.ai_analysis import _finalize_analysis
from app.services.extractors import ExtractedContent
from app.services.item_combine import combine_similar_pay_items, pay_items_similar


def test_fertilizer_locations_sum_into_one_item():
    items = [
        {"description": "Fertilizer", "unit": "Lb", "quantity": 1189, "source_page": 8},
        {"description": "Fertilizer", "unit": "lbs", "quantity": 39, "source_page": 14},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 1
    assert abs(float(out[0]["quantity"]) - 1228) < 0.01


def test_commercial_fertilizer_matches_fertilizer():
    items = [
        {"description": "Commercial Fertilizer", "unit": "Lb", "quantity": 1189},
        {"description": "Fertilizer — Area 2", "unit": "Lb", "quantity": 39},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 1
    assert abs(float(out[0]["quantity"]) - 1228) < 0.01


def test_station_suffix_does_not_keep_items_apart():
    items = [
        {"description": "Fertilizer STA 10+00 TO 18+50", "unit": "Lb", "quantity": 1189},
        {"description": "Fertilizer STA 22+00", "unit": "Lb", "quantity": 39},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 1
    assert abs(float(out[0]["quantity"]) - 1228) < 0.01


def test_different_pipe_sizes_stay_separate():
    items = [
        {"description": "8-Inch Water Main", "unit": "Ft", "quantity": 245},
        {"description": "12-Inch Water Main", "unit": "Ft", "quantity": 90},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 2


def test_type_variants_stay_separate():
    items = [
        {"description": "Type 3 Barricade", "unit": "Each", "quantity": 13},
        {"description": "Type 2 Barricade", "unit": "Each", "quantity": 4},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 2


def test_npk_grades_stay_separate():
    items = [
        {"description": "Fertilizer 10-10-10", "unit": "Lb", "quantity": 200},
        {"description": "Fertilizer 20-10-10", "unit": "Lb", "quantity": 50},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 2


def test_seed_and_fertilizer_stay_separate():
    items = [
        {"description": "Seeding", "unit": "Acre", "quantity": 2.1},
        {"description": "Fertilizer", "unit": "Lb", "quantity": 1189},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 2


def test_duplicate_schedule_qty_is_not_double_counted():
    items = [
        {
            "description": "Fertilizer",
            "unit": "Lb",
            "quantity": 1189,
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "Fertilizer",
            "unit": "Lb",
            "quantity": 1189,
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
            "source_reference": "EOQ p.3",
        },
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 1
    assert abs(float(out[0]["quantity"]) - 1189) < 0.01


def test_schedule_total_not_added_to_location_parts():
    items = [
        {
            "description": "Fertilizer",
            "unit": "Lb",
            "quantity": 1228,
            "calculation_method": "Extracted from Bid Items / EOQ table",
        },
        {"description": "Fertilizer", "unit": "Lb", "quantity": 1189},
        {"description": "Fertilizer", "unit": "Lb", "quantity": 39},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 1
    assert abs(float(out[0]["quantity"]) - 1228) < 0.01


def test_hydrant_counts_from_two_sheets_add():
    items = [
        {"description": "Fire Hydrant", "unit": "Each", "quantity": 1, "source_page": 4},
        {"description": "Fire Hydrant", "unit": "Each", "quantity": 1, "source_page": 9},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 1
    assert float(out[0]["quantity"]) == 2


def test_mobilization_ls_stays_one():
    items = [
        {"description": "Mobilization", "unit": "LS", "quantity": 1},
        {"description": "Mobilization", "unit": "LS", "quantity": 1},
    ]
    out = combine_similar_pay_items(items)
    assert len(out) == 1
    assert float(out[0]["quantity"]) == 1


def test_concrete_sidewalk_not_merged_with_curb():
    assert not pay_items_similar(
        {"description": "Concrete Sidewalk", "unit": "SQFT", "quantity": 100},
        {"description": "Concrete Curb and Gutter", "unit": "Ft", "quantity": 80},
    )
    items = [
        {"description": "Concrete Sidewalk", "unit": "SQFT", "quantity": 100},
        {"description": "Concrete Curb and Gutter", "unit": "Ft", "quantity": 80},
    ]
    assert len(combine_similar_pay_items(items)) == 2


def test_finalize_sums_fertilizer_location_rows():
    result = _finalize_analysis(
        {
            "engine": "openai+vision",
            "summary": "plans",
            "items": [
                {
                    "description": "Fertilizer",
                    "unit": "Lb",
                    "quantity": 1189,
                    "calculation_method": "OpenAI vision — engineering drawing sheet",
                    "source_page": 8,
                    "confidence": 88,
                },
                {
                    "description": "Commercial Fertilizer",
                    "unit": "lbs",
                    "quantity": 39,
                    "calculation_method": "OpenAI vision — engineering drawing sheet",
                    "source_page": 14,
                    "confidence": 86,
                },
                {
                    "description": "8-Inch Water Main",
                    "unit": "Ft",
                    "quantity": 245,
                    "calculation_method": "OpenAI vision — engineering drawing sheet",
                    "confidence": 90,
                },
            ],
        },
        content=ExtractedContent(text="Plan sheets, no bid schedule table.", tables=[]),
    )
    by_desc = {str(i.get("description")): i for i in result["items"]}
    fert = next(i for i in result["items"] if "fertiliz" in str(i.get("description") or "").lower())
    assert abs(float(fert["quantity"]) - 1228) < 0.01
    assert len([i for i in result["items"] if "fertiliz" in str(i.get("description") or "").lower()]) == 1
    assert by_desc["8-Inch Water Main"]["quantity"] == 245
    assert "combined" in (result.get("notes") or result.get("summary") or "").lower()
