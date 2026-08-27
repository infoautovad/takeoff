"""Detect work that is incidental to a bid item and must not be taken off.

Municipal plans routinely note bedding, trench, fittings, tracer wire, etc. as
incidental to a parent pay item. Those notes must not become extra EOQ rows
and must not be added into the parent quantity.
"""

from __future__ import annotations

import re
from typing import Any

# Pay items that happen to contain the word "incidental" but are bid rows.
_KEEP_PAY_ITEM_RE = re.compile(
    r"incidental\s+construction|"
    r"contract\s+incidentals?|"
    r"miscellaneous\s+incidentals?|"
    r"^incidentals?\s*$",
    re.I,
)

# Child work pointed at a parent bid item.
_INCIDENTAL_TO_RE = re.compile(
    r"\bincidental(?:ly)?\s+to\b|"
    r"\bsubsidiary\s+to\b|"
    r"\bpaid\s+(?:for\s+)?(?:under|as\s+part\s+of)\b|"
    r"\bincluded\s+in\s+(?:the\s+)?(?:bid|pay|contract|parent)\s+items?\b|"
    r"\bconsidered\s+(?:incidental|included)\b",
    re.I,
)

_NO_SEPARATE_PAY_RE = re.compile(
    r"\bno\s+separate\s+(?:pay(?:ment|s|item)?|measurement|compensation|bid)\b|"
    r"\bnot\s+(?:a\s+)?(?:separate\s+)?pay\s+items?\b|"
    r"\bno\s+additional\s+(?:payment|compensation|pay)\b|"
    r"\bdo\s+not\s+(?:include|pay|measure)\s+(?:as\s+)?(?:a\s+)?separate\b",
    re.I,
)

_INCIDENTAL_MARK_RE = re.compile(
    r"\(\s*incidental(?:ly)?\s*\)|"
    r"\bincidental(?:ly)?\b|"
    r"\bincidentals\b",
    re.I,
)

_UNIT_INCIDENTAL_RE = re.compile(
    r"^(?:inc|incidental|incidentals|nsp|incl|included|n/?a)$",
    re.I,
)

# Customarily incidental to pipe / pavement unless listed as its own schedule row.
_DEFAULT_EXTRA_RE = re.compile(
    r"\b(?:"
    r"trench\s+excavation|"
    r"(?:pipe|sand|gravel|granular)?\s*bedding|"
    r"haunch(?:ing|es)?|"
    r"pipe(?:\s+zone)?\s+backfill|"
    r"trench\s+backfill|"
    r"tracer\s+wires?|"
    r"locate\s+wires?|"
    r"(?:warning|marking|detectable)\s+tapes?|"
    r"poly(?:ethylene)?\s*(?:wrap|encasement)|"
    r"polywrap|"
    r"thrust\s+blocks?|"
    r"sheeting|"
    r"shoring|"
    r"trench\s+box(?:es)?|"
    r"hydrostatic\s+tests?|"
    r"disinfection|"
    r"chlorination|"
    r"flushing|"
    r"pipe\s+(?:lubricants?|gaskets?)"
    r")\b",
    re.I,
)

_FITTING_RE = re.compile(
    r"\b(?:fittings?|bends?|elbows?|tees?|reducers?|plugs?|couplings?|"
    r"(?:long\s+)?sleeves?|cross(?:es)?|caps?|wye[s]?|wyes)\b",
    re.I,
)

_QTY_INFLATED_RE = re.compile(
    r"(?:"
    r"(?:plus|added|add(?:ing)?|including|include[sd]?|and)\s+"
    r"(?:incidental|\d+\s+(?:fittings?|bends?|elbows?|tees?|bedding)|"
    r"fittings?|bedding|backfill|trench|tracer)|"
    r"including\s+incidentals?|"
    r"pipe\s+(?:lf|ft|length)\s+plus|"
    r"added\s+to\s+(?:the\s+)?(?:pipe|parent|bid\s+item)|"
    r"rolled\s+(?:in|into)"
    r")",
    re.I,
)

_TRENCH_INCIDENTAL_NOTES_RE = re.compile(
    r"(?:trench|bedding|backfill|haunch).{0,60}incidental|"
    r"incidental.{0,60}(?:trench|bedding|backfill|haunch)|"
    r"incidental(?:ly)?\s+to.{0,40}(?:pipe|watermain|water\s*main|sewer)",
    re.I,
)

_PARENT_PAY_RE = re.compile(
    r"\b(?:"
    r"water\s*mains?|watermains?|"
    r"sanitary|storm|"
    r"sewer\s+pipe|"
    r"pavement|asphalt|hma|curb|gutter|sidewalk|"
    r"mobilization|traffic\s+control|"
    r"riprap|embankment|spillway"
    r")\b",
    re.I,
)


def item_evidence_text(item: dict[str, Any]) -> str:
    return (
        f"{item.get('description') or ''} "
        f"{item.get('calculation_method') or ''} "
        f"{item.get('source_reference') or ''} "
        f"{item.get('source') or ''}"
    )


def is_kept_incidental_pay_item(description: str | None) -> bool:
    text = str(description or "").strip()
    return bool(text and _KEEP_PAY_ITEM_RE.search(text))


def unit_is_incidental(unit: str | None) -> bool:
    raw = re.sub(r"\s+", " ", str(unit or "").strip())
    return bool(raw and _UNIT_INCIDENTAL_RE.match(raw))


def has_incidental_language(text: str | None) -> bool:
    blob = str(text or "")
    if not blob.strip():
        return False
    return bool(
        _INCIDENTAL_TO_RE.search(blob)
        or _NO_SEPARATE_PAY_RE.search(blob)
        or _INCIDENTAL_MARK_RE.search(blob)
    )


def description_is_incidental_child(text: str | None) -> bool:
    """True when the text describes work that is not separately paid."""
    blob = str(text or "")
    if not blob.strip() or is_kept_incidental_pay_item(blob):
        return False
    if _INCIDENTAL_TO_RE.search(blob) or _NO_SEPARATE_PAY_RE.search(blob):
        return True
    if re.search(r"\(\s*incidental(?:ly)?\s*\)", blob, re.I):
        return True
    return False


def is_default_incidental_extra(description: str | None) -> bool:
    text = str(description or "")
    if not text.strip() or is_kept_incidental_pay_item(text):
        return False
    return bool(_DEFAULT_EXTRA_RE.search(text))


def is_fitting_like(description: str | None) -> bool:
    text = str(description or "")
    if not text.strip():
        return False
    if re.search(r"\b(?:valve|hydrant|manhole|inlet|catch\s*basin)\b", text, re.I):
        return False
    return bool(_FITTING_RE.search(text))


def quantity_inflated_by_incidentals(text: str | None) -> bool:
    return bool(_QTY_INFLATED_RE.search(str(text or "")))


def cad_notes_make_trench_incidental(text: str | None) -> bool:
    return bool(_TRENCH_INCIDENTAL_NOTES_RE.search(str(text or "")))


def clause_around(text: str, index: int) -> tuple[str, int]:
    """Return the clause containing index and its start offset in text."""
    if not text:
        return "", 0
    index = max(0, min(index, len(text)))
    start = 0
    end = len(text)
    for match in re.finditer(r"[\n;]|(?<!\d)\.(?!\d)\s+", text):
        if match.end() <= index:
            start = match.end()
        elif match.start() > index:
            end = match.start()
            break
    return text[start:end].strip(), start


def skip_text_extraction(
    description: str,
    line: str,
    *,
    match_start: int = 0,
) -> bool:
    """True when a regex/label hit is incidental work or only names the parent item."""
    if is_kept_incidental_pay_item(description):
        return False
    if description_is_incidental_child(description):
        return True
    if is_default_incidental_extra(description):
        return True
    inc_to = _INCIDENTAL_TO_RE.search(line)
    if inc_to and match_start >= inc_to.start():
        return True
    if has_incidental_language(line) and (
        is_fitting_like(description) or not _PARENT_PAY_RE.search(description)
    ):
        # Subject of an incidental note (excavation, collars, …) — not a parent pay item.
        if inc_to and match_start < inc_to.start():
            return True
        if not inc_to:
            return True
    return False


def extraction_should_skip(description: str, full_text: str, match_start: int) -> bool:
    clause, clause_start = clause_around(full_text, match_start)
    return skip_text_extraction(
        description,
        clause or full_text,
        match_start=max(0, match_start - clause_start),
    )


def should_drop_incidental_item(
    item: dict[str, Any],
    *,
    scheduled: bool = False,
    drop_default_extras: bool = True,
) -> bool:
    """Drop incidental children. Never use this to add their qty onto a parent."""
    desc = str(item.get("description") or "")
    if is_kept_incidental_pay_item(desc):
        return False
    if unit_is_incidental(item.get("unit")):
        return True
    if description_is_incidental_child(desc):
        return True
    evidence = item_evidence_text(item)
    if description_is_incidental_child(evidence) and not scheduled:
        return True
    if drop_default_extras and not scheduled and is_default_incidental_extra(desc):
        return True
    if not scheduled and is_fitting_like(desc) and has_incidental_language(evidence):
        return True
    return False
