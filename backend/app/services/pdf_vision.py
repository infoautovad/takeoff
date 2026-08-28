"""Render PDF plan sheets for OpenAI vision takeoff.

Engineering PDFs are often drawing-heavy with little extractable text.
PyMuPDF renders pages so vision models can read plans, details,
profiles, and callouts — not just text/tables.

Default: every page is vision-scanned in batches (including 1000-page / 1GB
sets). Bid/qty sheets go first. Batch size is RAM/OpenAI chunking only — not a
page cap. Completeness over speed.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import fitz

DRAWING_KEYWORDS = re.compile(
    r"\b(plan|profile|section|detail|typical|cross[\s-]?section|alignment|"
    r"pavement|utility|sewer|water|watermain|water\s*main|\bwm\b|storm|grading|earthwork|quantity|"
    r"schedule|laying|station|curb|gutter|manhole|pipe|valve|hydrant|inlet|"
    r"summary|bid\s*item|pay\s*item|tabulation)\b",
    re.I,
)

UTILITY_LABEL_HINTS = re.compile(
    r"(\d{1,2}\s*(?:\"|''|in)\s*(?:water|wm|sanitary|storm)|"
    r"water\s*mains?|watermains?|\bwm\b|prop(?:osed)?\.?\s*wm|"
    r"gate\s*valve|fire\s*hydrant|dip\s+wm|pvc\s+wm|"
    r"sanitary\s*sewer|storm\s*drain|manhole|catch\s*basin)",
    re.I,
)

SCHEDULE_HINTS = re.compile(
    r"\b(bid\s*items?|pay\s*item|estimate\s+of\s+quantit|est\.?\s*qty|std\s*bid|"
    r"approx\.?\s*quantity|summary\s*of\s*quantit|"
    r"pipe\s*schedule|structure\s*schedule|tabulation)\b",
    re.I,
)

PROFILE_HINTS = re.compile(r"\b(profile|sta\.?|stationing|invert|grade\s*line)\b", re.I)

# Large files use smaller vision batches for RAM. Page count is never capped when scan_all is on.
LARGE_PAGE_THRESHOLD = 80
LARGE_FILE_MB = 80
LARGE_VISION_MAX_PAGES = 0


def is_large_plan_pdf(
    page_count: int,
    file_bytes: int = 0,
    *,
    page_threshold: int = LARGE_PAGE_THRESHOLD,
    file_mb: int = LARGE_FILE_MB,
) -> bool:
    if page_count >= max(1, page_threshold):
        return True
    return file_bytes >= max(1, file_mb) * 1024 * 1024


def select_vision_page_indexes(
    scored: list[tuple[float, int, str, bool, bool]],
    *,
    page_count: int,
    scan_all_pages: bool,
    large_document: bool,
    max_pages: int = 0,
    large_max_pages: int = LARGE_VISION_MAX_PAGES,
    min_score: float = 18.0,
    force_utility_pages: bool = True,
) -> tuple[list[int], list[int]]:
    """Pick 0-based page indexes for vision.

    When scan_all is true, every page is included (bid/qty sheets first), including
    1000-page jobs. large_document does not drop pages — it only affects batch RAM.
    """
    if page_count <= 0 or not scored:
        return [], []

    if scan_all_pages:
        chosen_idxs = sorted(
            range(min(page_count, len(scored))),
            key=lambda i: (0 if scored[i][4] else 1, i),
        )
        if max_pages and max_pages > 0:
            chosen_idxs = chosen_idxs[:max_pages]
        return chosen_idxs, []

    cap = max_pages if max_pages and max_pages > 0 else 24
    if large_document and large_max_pages and large_max_pages > 0:
        cap = large_max_pages if not (max_pages and max_pages > 0) else min(cap, large_max_pages)
    scored_sorted = sorted(scored, key=lambda row: (-row[0], row[1]))
    limit = max(1, min(cap, page_count))
    eligible = [row for row in scored_sorted if row[0] >= min_score] or scored_sorted[:]
    chosen_map: dict[int, tuple[float, int, str, bool, bool]] = {
        row[1]: row for row in eligible[:limit]
    }
    forced = []
    if force_utility_pages:
        for row in scored_sorted:
            if not row[3] or row[1] in chosen_map:
                continue
            if len(chosen_map) < limit:
                chosen_map[row[1]] = row
                forced.append(row[1] + 1)
                continue
            replaceable = sorted(
                (r for r in chosen_map.values() if not r[3]),
                key=lambda r: (r[0], -r[1]),
            )
            if not replaceable:
                break
            victim = replaceable[0]
            del chosen_map[victim[1]]
            chosen_map[row[1]] = row
            forced.append(row[1] + 1)
    return sorted(chosen_map.keys()), forced


@dataclass
class PageImage:
    page: int
    png_b64: str
    width: int
    height: int
    reason: str


@dataclass
class VisionPagePlan:
    """Which pages will be scanned (does not hold image bytes)."""

    page_count: int
    selected_pages: list[int] = field(default_factory=list)  # 1-based
    skipped_pages: list[int] = field(default_factory=list)
    truncated: bool = False
    forced_utility_pages: list[int] = field(default_factory=list)
    scan_all: bool = True
    batch_size: int = 8
    reasons: dict[int, str] = field(default_factory=dict)  # 1-based page -> reason
    large_document: bool = False


@dataclass
class VisionPageSelection:
    """Legacy-compatible selection that may include rendered images."""

    images: list[PageImage]
    page_count: int
    selected_pages: list[int] = field(default_factory=list)
    skipped_pages: list[int] = field(default_factory=list)
    truncated: bool = False
    forced_utility_pages: list[int] = field(default_factory=list)
    scan_all: bool = False
    batch_size: int = 0


def plan_pdf_vision_pages(
    path: Path,
    *,
    max_pages: int = 0,
    min_score: float = 18.0,
    force_utility_pages: bool = True,
    scan_all_pages: bool = True,
    batch_pages: int = 8,
    page_texts: list | None = None,
    file_bytes: int = 0,
    large_page_threshold: int = LARGE_PAGE_THRESHOLD,
    large_file_mb: int = LARGE_FILE_MB,
    large_max_pages: int = LARGE_VISION_MAX_PAGES,
) -> VisionPagePlan:
    """Decide which pages to vision-scan.

    Small PDFs can scan every page. Sets with 80+ pages or 80MB+ (including
    1000-page / 1GB jobs) always use bid/qty-first selection with a page cap.
    """
    batch_pages = max(1, batch_pages)
    text_by_page: dict[int, str] = {}
    if page_texts:
        for item in page_texts:
            page_no = getattr(item, "page", None)
            text = getattr(item, "text", None)
            if page_no is None and isinstance(item, dict):
                page_no = item.get("page")
                text = item.get("text")
            if page_no:
                text_by_page[int(page_no)] = text or ""

    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:
        pass

    with fitz.open(path) as doc:
        page_count = doc.page_count
        if page_count == 0:
            return VisionPagePlan(page_count=0, batch_size=batch_pages, scan_all=scan_all_pages)

        if not file_bytes:
            try:
                file_bytes = path.stat().st_size
            except OSError:
                file_bytes = 0
        large = is_large_plan_pdf(
            page_count,
            file_bytes,
            page_threshold=large_page_threshold,
            file_mb=large_file_mb,
        )

        scored: list[tuple[float, int, str, bool, bool]] = []
        for i in range(page_count):
            text = text_by_page.get(i + 1)
            if text is None:
                try:
                    text = doc.load_page(i).get_text("text") or ""
                except Exception:
                    text = ""
            score, reason = _score_page(text=text, page_index=i, page_count=page_count)
            has_utility = bool(UTILITY_LABEL_HINTS.search(text)) or bool(SCHEDULE_HINTS.search(text))
            has_schedule = bool(SCHEDULE_HINTS.search(text))
            scored.append((score, i, reason, has_utility, has_schedule))

        reasons = {i + 1: reason for _s, i, reason, _u, _sch in scored}
        chosen_idxs, forced = select_vision_page_indexes(
            scored,
            page_count=page_count,
            scan_all_pages=scan_all_pages,
            large_document=large,
            max_pages=max_pages,
            large_max_pages=large_max_pages,
            min_score=min_score,
            force_utility_pages=force_utility_pages,
        )

        selected_pages = [i + 1 for i in chosen_idxs]
        skipped_pages = [i + 1 for i in range(page_count) if (i + 1) not in selected_pages]
        return VisionPagePlan(
            page_count=page_count,
            selected_pages=selected_pages,
            skipped_pages=skipped_pages,
            truncated=len(skipped_pages) > 0,
            forced_utility_pages=forced,
            scan_all=scan_all_pages and not bool(skipped_pages),
            batch_size=batch_pages,
            reasons=reasons,
            large_document=large,
        )


def iter_rendered_pdf_batches(
    path: Path,
    plan: VisionPagePlan,
    *,
    dpi: int = 150,
    batch_pages: int | None = None,
    max_edge: int | None = None,
) -> Iterator[list[PageImage]]:
    """Render selected pages in batches so large PDFs are not held fully in memory."""
    size = max(1, batch_pages or plan.batch_size or 8)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pages = plan.selected_pages
    edge = max_edge if max_edge and max_edge > 0 else 1800
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:
        pass
    with fitz.open(path) as doc:
        for start in range(0, len(pages), size):
            chunk: list[PageImage] = []
            for page_no in pages[start : start + size]:
                idx = page_no - 1
                try:
                    page = doc.load_page(idx)
                    try:
                        pix = page.get_pixmap(matrix=matrix, alpha=False, annots=False)
                    except TypeError:
                        pix = page.get_pixmap(matrix=matrix, alpha=False)
                    if pix.width > edge:
                        scale = edge / pix.width
                        shrink = fitz.Matrix(zoom * scale, zoom * scale)
                        try:
                            pix = page.get_pixmap(matrix=shrink, alpha=False, annots=False)
                        except TypeError:
                            pix = page.get_pixmap(matrix=shrink, alpha=False)
                    png_b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
                    width, height = pix.width, pix.height
                    del pix
                except Exception:
                    continue
                chunk.append(
                    PageImage(
                        page=page_no,
                        png_b64=png_b64,
                        width=width,
                        height=height,
                        reason=plan.reasons.get(page_no, "full scan"),
                    )
                )
            if chunk:
                yield chunk


def select_and_render_pdf_pages(
    path: Path,
    *,
    max_pages: int = 0,
    dpi: int = 150,
    min_score: float = 18.0,
    force_utility_pages: bool = True,
    scan_all_pages: bool = True,
    batch_pages: int = 8,
) -> VisionPageSelection:
    """Compatibility helper: plan + render all selected pages (prefer iter_rendered_pdf_batches)."""
    plan = plan_pdf_vision_pages(
        path,
        max_pages=max_pages,
        min_score=min_score,
        force_utility_pages=force_utility_pages,
        scan_all_pages=scan_all_pages,
        batch_pages=batch_pages,
    )
    images: list[PageImage] = []
    for batch in iter_rendered_pdf_batches(path, plan, dpi=dpi, batch_pages=batch_pages):
        images.extend(batch)
    return VisionPageSelection(
        images=images,
        page_count=plan.page_count,
        selected_pages=plan.selected_pages,
        skipped_pages=plan.skipped_pages,
        truncated=plan.truncated,
        forced_utility_pages=plan.forced_utility_pages,
        scan_all=plan.scan_all,
        batch_size=plan.batch_size,
    )


def _score_page(*, text: str, page_index: int, page_count: int) -> tuple[float, str]:
    """Higher score = more likely a useful engineering drawing / qty sheet."""
    stripped = text.strip()
    char_count = len(stripped)
    reasons: list[str] = []
    score = 0.0

    if char_count < 80:
        score += 40
        reasons.append("sparse-text drawing")
    elif char_count < 400:
        score += 28
        reasons.append("light-text sheet")
    elif char_count < 1200:
        score += 12
        reasons.append("mixed sheet")
    else:
        score += 4
        reasons.append("text-heavy")

    if DRAWING_KEYWORDS.search(stripped):
        score += 22
        reasons.append("civil keywords")

    if page_index == 0:
        score += 10
        reasons.append("title/cover")

    if page_count > 8 and 0.15 <= (page_index / max(page_count - 1, 1)) <= 0.9:
        score += 6

    if SCHEDULE_HINTS.search(stripped):
        score += 28
        reasons.append("schedule/qty sheet")

    if PROFILE_HINTS.search(stripped):
        score += 16
        reasons.append("profile/stationing")

    if re.search(r"\b(cu\.?\s*yd|sq\.?\s*yd|linear\s*feet|l\.?f\.?)\b", stripped, re.I):
        score += 12
        reasons.append("unit signals")

    utility_hits = len(UTILITY_LABEL_HINTS.findall(stripped))
    if utility_hits:
        score += min(40, 16 + utility_hits * 4)
        reasons.append(f"utility labels×{utility_hits}")

    return score, ", ".join(reasons) or "selected"
