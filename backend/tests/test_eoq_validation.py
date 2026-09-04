"""Deterministic EOQ validation rules before persistence."""

from app.services.eoq_validation import validate_extracted_items


def test_schedule_priority_keeps_authoritative_quantity():
    rows = [
        {
            "description": "Traffic Control",
            "unit": "SqFt",
            "quantity": 624,
            "item_code": "634.0110",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
            "source_reference": "Bid Items table p.3",
            "confidence": 99,
        },
        {
            "description": "Traffic Control",
            "unit": "SqFt",
            "quantity": 710,
            "calculation_method": "Graphic count from drawing symbols",
            "source_reference": "Sheet F9",
            "confidence": 82,
        },
    ]
    validated, notes = validate_extracted_items(rows)
    assert len(validated) == 1
    assert abs(float(validated[0]["quantity"]) - 624.0) < 0.001
    assert any("schedule-priority" in n.lower() for n in notes)


def test_same_source_conflict_keeps_highest_confidence_row():
    rows = [
        {
            "description": "8-Inch Water Main",
            "unit": "LF",
            "quantity": 100,
            "source_document_id": 1,
            "source_page": 7,
            "source_reference": "Sheet C4 callout",
            "confidence": 84,
        },
        {
            "description": "8-Inch Water Main",
            "unit": "LF",
            "quantity": 120,
            "source_document_id": 1,
            "source_page": 7,
            "source_reference": "Sheet C4 callout",
            "confidence": 91,
        },
    ]
    validated, _notes = validate_extracted_items(rows)
    assert len(validated) == 1
    assert abs(float(validated[0]["quantity"]) - 120.0) < 0.001
    assert bool(validated[0].get("validation_needs_review")) is True
    assert float(validated[0]["confidence"]) <= 88.0


def test_unit_sanity_marks_suspicious_units_for_review():
    rows = [
        {
            "description": "Fire Hydrant",
            "unit": "LF",
            "quantity": 3,
            "confidence": 97,
            "source_reference": "Sheet U6",
        }
    ]
    validated, notes = validate_extracted_items(rows)
    assert len(validated) == 1
    assert bool(validated[0].get("validation_needs_review")) is True
    assert float(validated[0]["confidence"]) <= 85.0
    assert any("unit-sanity mismatch" in n.lower() for n in notes)


def test_non_positive_non_schedule_rows_are_dropped():
    rows = [
        {"description": "Storm Sewer", "unit": "LF", "quantity": 0, "source_reference": "Sheet C7"},
        {"description": "Sanitary Sewer", "unit": "LF", "quantity": -2, "source_reference": "Sheet C8"},
    ]
    validated, notes = validate_extracted_items(rows)
    assert validated == []
    assert any("non-positive quantity" in n.lower() for n in notes)


def test_location_rows_from_different_sources_are_kept():
    rows = [
        {
            "description": "Fertilizer",
            "unit": "Lb",
            "quantity": 1189,
            "source_page": 8,
            "source_reference": "Sheet E8",
        },
        {
            "description": "Fertilizer",
            "unit": "Lb",
            "quantity": 39,
            "source_page": 14,
            "source_reference": "Sheet E14",
        },
    ]
    validated, _notes = validate_extracted_items(rows)
    assert len(validated) == 2
