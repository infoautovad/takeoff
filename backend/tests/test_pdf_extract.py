"""PDF extract/vision helpers — every page is in scope, including 1000-page sets."""

from app.services.extractors import PageText, pages_worth_table_extract
from app.services.pdf_vision import is_large_plan_pdf, select_vision_page_indexes


def test_small_pdf_extracts_tables_on_every_page():
    pages = [PageText(page=i, text="PLAN VIEW") for i in range(1, 6)]
    assert pages_worth_table_extract(pages, page_count=5) == {1, 2, 3, 4, 5}


def test_drawing_pages_are_still_table_extracted():
    pages = [PageText(page=i, text="PLAN VIEW NORTH") for i in range(1, 30)]
    pages[9] = PageText(page=10, text="BID ITEMS  ITEM NUMBER  DESCRIPTION  UNITS  EST. QTY")
    chosen = pages_worth_table_extract(pages, page_count=29)
    assert chosen == {i for i in range(1, 30)}
    assert 10 in chosen
    assert 20 in chosen


def test_thousand_page_set_extracts_every_page_including_late_bid_sheet():
    pages = [PageText(page=i, text="ITEM NUMBER callout") for i in range(1, 1201)]
    pages[899] = PageText(page=900, text="BID ITEMS  EST. QTY  STD BID  DESCRIPTION")
    chosen = pages_worth_table_extract(pages, page_count=1200)
    assert len(chosen) == 1200
    assert 900 in chosen


def test_openai_scan_all_has_no_time_or_page_cap():
    from app.config import Settings

    settings = Settings()
    assert settings.openai_vision_max_seconds == 0
    assert settings.openai_vision_large_max_pages == 0
    assert settings.openai_vision_large_max_seconds == 0
    assert settings.openai_vision_scan_all_pages is True
    assert settings.openai_max_retries <= 2


def test_is_large_plan_pdf_thresholds():
    assert is_large_plan_pdf(1000, 0) is True
    assert is_large_plan_pdf(10, 2 * 1024 * 1024 * 1024) is True
    assert is_large_plan_pdf(12, 5 * 1024 * 1024) is False


def _score_row(index: int, *, schedule=False, utility=False, score=10.0):
    return (score, index, "r", utility or schedule, schedule)


def test_large_document_scan_all_includes_every_page_schedule_first():
    scored = [_score_row(i, score=float(i)) for i in range(200)]
    scored[4] = _score_row(4, schedule=True, score=1)
    scored[90] = _score_row(90, schedule=True, score=1)
    idxs, _forced = select_vision_page_indexes(
        scored,
        page_count=200,
        scan_all_pages=True,
        large_document=True,
        large_max_pages=0,
    )
    assert idxs[:2] == [4, 90]
    assert len(idxs) == 200
    assert set(idxs) == set(range(200))


def test_small_scan_all_keeps_every_page():
    scored = [_score_row(i) for i in range(12)]
    idxs, _forced = select_vision_page_indexes(
        scored,
        page_count=12,
        scan_all_pages=True,
        large_document=False,
    )
    assert len(idxs) == 12
    assert idxs[0] in range(12)
