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


def test_resolve_uses_plan_over_mutcd():
    detail = resolve_sign_area_sqft(
        {"description": "STOP Sign 48x48", "unit": "Each", "quantity": 1},
        allow_online_refresh=False,
    )
    assert detail["size_source"] == "plan_or_dwg_callout"
    assert abs(detail["sqft"] - inches_to_sqft(48, 48)) < 0.001
