"""CAD engine persistence limits and clipping safeguards."""

from app.services.cad.engine import _clip_rows


def test_clip_rows_zero_limit_keeps_all():
    rows = [{"i": i} for i in range(6)]
    kept, dropped = _clip_rows(rows, 0)
    assert len(kept) == 6
    assert dropped == 0


def test_clip_rows_reports_dropped_count():
    rows = [{"i": i} for i in range(10)]
    kept, dropped = _clip_rows(rows, 4)
    assert len(kept) == 4
    assert dropped == 6
