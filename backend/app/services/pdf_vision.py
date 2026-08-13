"""Render PDF plan sheets for OpenAI vision takeoff.

Engineering PDFs are often drawing-heavy with little extractable text.
PyMuPDF renders selected pages so vision models can read plans, details,
profiles, and callouts — not just text/tables.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path

import fitz

DRAWING_KEYWORDS = re.compile(
    r"\b(plan|profile|section|detail|typical|cross[\s-]?section|alignment|"
    r"pavement|utility|sewer|water|watermain|water\s*main|\bwm\b|storm|grading|earthwork|quantity|"
    r"schedule|laying|station|curb|gutter|manhole|pipe|valve|hydrant|inlet)\b",
    re.I,
)

UTILITY_LABEL_HINTS = re.compile(
    r"(\d{1,2}\s*(?:\"|''|in)\s*(?:water|wm|sanitary|storm)|"
    r"water\s*mains?|watermains?|\bwm\b|prop(?:osed)?\.?\s*wm|"
    r"gate\s*valve|fire\s*hydrant|dip\s+wm|pvc\s+wm)",
    re.I,
)


@dataclass
class PageImage:
    page: int
    png_b64: str
    width: int
    height: int
    reason: str


def select_and_render_pdf_pages(
    path: Path,
    *,
    max_pages: int = 10,
    dpi: int = 140,
) -> list[PageImage]:
    """Pick the most useful plan sheets and render them as PNG for vision."""
    if max_pages <= 0:
        return []

    with fitz.open(path) as doc:
        page_count = doc.page_count
        if page_count == 0:
            return []

        scored: list[tuple[float, int, str, str]] = []
        for i in range(page_count):
            page = doc.load_page(i)
            text = page.get_text("text") or ""
            score, reason = _score_page(text=text, page_index=i, page_count=page_count)
            scored.append((score, i, reason, text))

        scored.sort(key=lambda row: (-row[0], row[1]))
        chosen = scored[: max(1, min(max_pages, page_count))]
        chosen.sort(key=lambda row: row[1])  # render in page order

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        images: list[PageImage] = []
        for _score, idx, reason, _text in chosen:
            page = doc.load_page(idx)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            # Cap very large rasters for API size
            if pix.width > 1800:
                scale = 1800 / pix.width
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom * scale, zoom * scale), alpha=False)
            png_b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
            images.append(
                PageImage(
                    page=idx + 1,
                    png_b64=png_b64,
                    width=pix.width,
                    height=pix.height,
                    reason=reason,
                )
            )
        return images


def _score_page(*, text: str, page_index: int, page_count: int) -> tuple[float, str]:
    """Higher score = more likely a useful engineering drawing / qty sheet."""
    stripped = text.strip()
    char_count = len(stripped)
    reasons: list[str] = []
    score = 0.0

    # Drawing-heavy pages often have sparse text
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

    # Cover / title / index often useful
    if page_index == 0:
        score += 10
        reasons.append("title/cover")

    # Prefer middle sheets in large plan sets (less TOC, more work)
    if page_count > 8 and 0.15 <= (page_index / max(page_count - 1, 1)) <= 0.9:
        score += 6

    # Quantity / schedule tables still matter
    if re.search(r"\b(qty|quantity|estimate|bid item|unit|cu\.?\s*yd|sq\.?\s*yd)\b", stripped, re.I):
        score += 18
        reasons.append("quantity signals")

    # Water main / utility callout labels — critical for BOQ
    utility_hits = len(UTILITY_LABEL_HINTS.findall(stripped))
    if utility_hits:
        score += min(36, 14 + utility_hits * 4)
        reasons.append(f"utility labels×{utility_hits}")

    return score, ", ".join(reasons) or "selected"
