"""Traffic Control sign rollup + MUTCD size helpers."""

from app.services.traffic_control import (
    consolidate_traffic_control_signs,
    inches_to_sqft,
    is_traffic_sign_item,
    lookup_mutcd_size,
    parse_sign_size_inches,
    resolve_sign_area_sqft,
)


def test_parse_plan_size_inches():
    assert parse_sign_size_inches('STOP 30" x 30"') == (30.0, 30.0)
    assert parse_sign_size_inches("Speed Limit 24x30") == (24.0, 30.0)
    assert parse_sign_size_inches("panel 2 ft x 2.5 ft") == (24.0, 30.0)
    assert parse_sign_size_inches("48-Inch x 30-Inch") == (48.0, 30.0)
    assert parse_sign_size_inches("48 Inch x 30 Inch") == (48.0, 30.0)
    assert inches_to_sqft(48, 30) == 10.0


def test_forty_eight_by_thirty_rolls_to_sqft():
    """MUTCD face is inches; USA Traffic Control pay quantity is SqFt."""
    items = [
        {
            "description": "48-Inch x 30-Inch Warning Sign",
            "unit": "Each",
            "quantity": 1,
            "category": "Traffic Control",
        }
    ]
    out, meta = consolidate_traffic_control_signs(items, allow_online_refresh=False)
    traffic = [i for i in out if str(i.get("description")).lower() == "traffic control"]
    assert len(traffic) == 1
    assert traffic[0]["unit"] == "SqFt"
    assert abs(float(traffic[0]["quantity"]) - 10.0) < 0.01
    assert "÷144" in str(traffic[0].get("calculation_method") or "")


def test_mutcd_stop_default():
    hit = lookup_mutcd_size(description="STOP sign")
    assert hit is not None
    assert hit["code"] == "R1-1"
    assert hit["width_in"] == 30
    assert inches_to_sqft(30, 30) == 6.25


def test_consolidate_signs_to_one_sqft_item():
    items = [
        {"description": "8-Inch Water Main", "unit": "Ft", "quantity": 100, "category": "Watermain"},
        {"description": "STOP Sign R1-1", "unit": "Each", "quantity": 2, "category": "Signing"},
        {"description": "Speed Limit 25", "unit": "Each", "quantity": 1, "category": "Signing"},
        {"description": "W20-1 Road Work Ahead 36x36", "unit": "Each", "quantity": 1, "category": "Signing"},
    ]
    out, meta = consolidate_traffic_control_signs(items, allow_online_refresh=False)
    assert meta["sign_rows"] == 3
    traffic = [i for i in out if str(i.get("description")).lower() == "traffic control"]
    assert len(traffic) == 1
    assert str(traffic[0]["unit"]).lower() in {"sqft", "sf"}
    # 2×(30×30) + 1×(24×30) + 1×(36×36) = 12.5 + 5 + 9 = 26.5
    assert abs(float(traffic[0]["quantity"]) - 26.5) < 0.05
    assert all(not is_traffic_sign_item(i) or i["description"] == "Traffic Control" for i in out)
    assert any(i["description"] == "8-Inch Water Main" for i in out)


def test_schedule_traffic_control_keeps_bid_rows_not_plan_invents():
    """Bid-schedule Traffic Control section wins over F-sheet devices and MUTCD 30×30."""
    items = [
        {
            "description": "Traffic Control",
            "unit": "SqFt",
            "quantity": 624,
            "item_code": "634.0110",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
            "source_reference": "Bid Items table, Traffic Control section",
        },
        {
            "description": "Traffic Control, Miscellaneous",
            "unit": "LS",
            "quantity": 1,
            "item_code": "634.0120",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "Type 3 Barricade, 8' Double Sided",
            "unit": "Each",
            "quantity": 13,
            "item_code": "634.0285",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "Temporary Business Sign",
            "unit": "Each",
            "quantity": 2,
            "item_code": "634.1050",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "Contractor Furnished Portable Changeable Message Sign",
            "unit": "Each",
            "quantity": 2,
            "item_code": "634.1215",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "Temporary Mailbox",
            "unit": "Each",
            "quantity": 17,
            "item_code": "999.0023",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "Temporary Gravel Access",
            "unit": "LS",
            "quantity": 1,
            "item_code": "Special",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "Winter Maintenance",
            "unit": "LS",
            "quantity": 1,
            "item_code": "Special",
            "calculation_method": "Extracted from Estimate Of Quantities schedule",
        },
        {
            "description": "42 in Channelizer",
            "unit": "EA",
            "quantity": 8,
            "calculation_method": "Graphic count of channelizer symbols on F-sheets",
            "source_reference": "Sheets F9-F12 symbols",
        },
        {
            "description": "STOP Sign R1-1",
            "unit": "Each",
            "quantity": 4,
            "calculation_method": "Plan label MUTCD",
        },
        {
            "description": "Type III Barricade - 8 Ft. Double Sided",
            "unit": "EA",
            "quantity": 10,
            "calculation_method": "Extracted from table cell: Project Total = 10.",
            "source_reference": "Sheet F3, traffic-control itemized table, Project Totals column",
        },
        {
            "description": "Temporary Gravel Access, 6 in Thick",
            "unit": "SY",
            "quantity": 2100,
            "calculation_method": "Measured from F8 station limits",
        },
        {
            "description": "48-Inch x 30-Inch Warning Sign",
            "unit": "Each",
            "quantity": 1,
            "category": "Traffic Control",
        },
    ]
    out, meta = consolidate_traffic_control_signs(
        items, allow_online_refresh=False, schedule_present=True
    )
    by_desc = {str(i.get("description")): i for i in out}
    assert by_desc["Traffic Control"]["quantity"] == 624
    assert by_desc["Traffic Control"]["unit"] == "SqFt"
    assert by_desc["Traffic Control"]["item_code"] == "634.0110"
    assert by_desc["Traffic Control, Miscellaneous"]["unit"].lower() in {"ls"}
    assert by_desc["Type 3 Barricade, 8' Double Sided"]["quantity"] == 13
    assert by_desc["Temporary Business Sign"]["quantity"] == 2
    assert by_desc["Temporary Business Sign"]["unit"].lower() in {"each", "ea"}
    assert by_desc["Contractor Furnished Portable Changeable Message Sign"]["quantity"] == 2
    assert by_desc["Temporary Mailbox"]["quantity"] == 17
    assert by_desc["Temporary Gravel Access"]["unit"].lower() in {"ls"}
    assert by_desc["Winter Maintenance"]["quantity"] == 1
    assert "42 in Channelizer" not in by_desc
    assert "STOP Sign R1-1" not in by_desc
    assert "48-Inch x 30-Inch Warning Sign" not in by_desc
    assert "Temporary Gravel Access, 6 in Thick" not in by_desc
    assert not any("Type III Barricade" in d for d in by_desc)
    assert meta["dropped_plan_signs"] >= 2


def test_business_sign_and_pcms_are_not_rolled_into_sqft():
    assert not is_traffic_sign_item(
        {"description": "Temporary Business Sign", "unit": "Each", "quantity": 2}
    )
    assert not is_traffic_sign_item(
        {
            "description": "Contractor Furnished Portable Changeable Message Sign",
            "unit": "Each",
            "quantity": 2,
        }
    )
    detail = resolve_sign_area_sqft(
        {"description": "STOP Sign 48x48", "unit": "Each", "quantity": 1},
        allow_online_refresh=False,
    )
    assert detail["size_source"] == "plan_or_dwg_callout"
    assert abs(detail["sqft"] - inches_to_sqft(48, 48)) < 0.001
