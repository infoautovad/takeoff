"""Combine similar pay items from different locations into one quantity.

Plan sheets often take off the same bid item in more than one place
(Fertilizer 1,189 lb on one sheet and 39 lb on another). Those rows should
become a single EOQ line with the quantities added — without merging true
variants (8\" vs 12\", Type II vs Type III, furnish vs remove, etc.).
"""

from __future__ import annotations

import re
from typing import Any

from app.services.csi_mapper import normalize_unit
from app.services.traffic_control import looks_like_agency_bid_number

_LOCATION_NOISE_RE = re.compile(
    r"\bsta(?:tion)?\.?\s*\d+\+\d+(?:\.\d+)?(?:\s*(?:to|-|through|–|—)\s*"
    r"(?:sta(?:tion)?\.?\s*)?\d+\+\d+(?:\.\d+)?)?|"
    r"\bsheets?\s+[a-z]?\-?\d+[a-z0-9]*|"
    r"\bpages?\s+\d+|"
    r"\bp\.\s*\d+|"
    r"\barea\s+[a-z0-9\-]+|"
    r"\blocation\s+\d+|"
    r"\bfrom\s+sta\b|"
    r"\b(?:left|right)\s+(?:side|end)\b|"
    r"\bprop(?:osed)?\.?\b|"
    r"\bctd\.?\b|\bcontinued\b",
    re.I,
)

_NPK_RE = re.compile(r"\b(\d{1,2}-\d{1,2}-\d{1,2})\b")
_TYPE_RE = re.compile(r"\btype\s*([ivxl]+|\d+)\b", re.I)
_SIZE_RE = re.compile(
    r"(\d{1,2}(?:\.\d+)?)\s*-?\s*(?:inch|in|\"|'')",
    re.I,
)

_MATERIAL_TOKENS = frozenset(
    {"dip", "pvc", "hdpe", "rcp", "cpp", "di", "ci", "hma", "pcc", "copper", "steel"}
)
_REMOVE_HINTS = ("remove", "removal", "salvage", "abandon", "demolish", "demolition")
_WEAK_MODIFIERS = frozenset(
    {
        "commercial",
        "agricultural",
        "chemical",
        "standard",
        "municipal",
        "complete",
        "specified",
        "new",
        "temp",
        "temporary",
        "permanent",
        "lawn",
        "turf",
        "restoration",
        "roadside",
        "native",
        "mix",
        "mixed",
        "material",
        "materials",
        "application",
        "applied",
        "grade",
        "graded",
        "in",
        "place",
        "as",
        "per",
        "plan",
        "plans",
        "detail",
        "typical",
    }
)
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "of",
        "a",
        "an",
        "to",
        "on",
        "or",
        "item",
        "per",
        "at",
        "by",
        "from",
        "incl",
        "including",
        "all",
        "work",
        "provide",
        "sta",
        "station",
        "sheet",
        "page",
        "area",
        "location",
        "side",
        "prop",
        "proposed",
        "ctd",
        "continued",
    }
)
_SYNONYM = {
    "fertilising": "fertiliz",
    "fertilizing": "fertiliz",
    "fertiliser": "fertiliz",
    "fertilizer": "fertiliz",
    "fertilizers": "fertiliz",
    "seeding": "seed",
    "seeds": "seed",
    "mulching": "mulch",
    "watermain": "watermain",
    "watermains": "watermain",
    "temp": "temporary",
    "barricades": "barricade",
    "signs": "sign",
    "pipes": "pipe",
    "valves": "valve",
    "hydrants": "hydrant",
}
_SCHEDULE_HINTS = (
    "quantity sheet",
    "estimate of quantities",
    "bid items",
    "bid item",
    "std bid",
    "standard bid",
    "eoq",
    "pay item",
    "proposal quantity",
    "est. qty",
    "est qty",
    "approx. quantity",
    "approx quantity",
    "for bidding purposes",
    "extracted table total",
    "extracted from quantity table",
    "extracted from eoq",
    "extracted from tabular quantity",
    "eoq schedule",
)


def _norm_token(token: str) -> str:
    t = token.lower().strip()
    if t in _SYNONYM:
        t = _SYNONYM[t]
    if t.startswith("fertiliz"):
        return "fertiliz"
    roman = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}
    if t in roman:
        t = roman[t]
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t


def _tokens(description: str) -> set[str]:
    cleaned = _LOCATION_NOISE_RE.sub(" ", description or "")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower())
    out = set()
    for raw in cleaned.split():
        if len(raw) <= 1 or raw in _STOP:
            continue
        tok = _norm_token(raw)
        if tok and tok not in _STOP:
            out.add(tok)
    return out


def _size_token(description: str) -> str | None:
    m = _SIZE_RE.search(description or "")
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if abs(val - int(val)) < 0.01:
        return str(int(val))
    return f"{val:g}"


def _npk_token(description: str) -> str | None:
    m = _NPK_RE.search(description or "")
    return m.group(1) if m else None


def _type_token(description: str) -> str | None:
    m = _TYPE_RE.search(description or "")
    if not m:
        return None
    raw = m.group(1).lower()
    roman = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
    return roman.get(raw, raw)


def _materials(description: str) -> set[str]:
    toks = _tokens(description)
    return toks & _MATERIAL_TOKENS


def _action(description: str) -> str | None:
    low = (description or "").lower()
    if any(h in low for h in _REMOVE_HINTS):
        return "remove"
    furnish = "furnish" in low
    install = "install" in low
    if furnish and install:
        return "furnish_install"
    if furnish:
        return "furnish"
    if install:
        return "install"
    return None


def _alternate(description: str) -> str | None:
    m = re.search(r"\b(?:alternate|alt\.?)\s*([ab])\b", description or "", re.I)
    return m.group(1).lower() if m else None


def _agency_code(item: dict[str, Any]) -> str:
    raw = str(item.get("item_code") or "").strip()
    if looks_like_agency_bid_number(raw):
        return raw.lower()
    return ""


def _unit_key(item: dict[str, Any]) -> str:
    return normalize_unit(str(item.get("unit") or ""))


def _is_ls(item: dict[str, Any]) -> bool:
    return _unit_key(item) == "ls"


def item_is_schedule(item: dict[str, Any]) -> bool:
    if _agency_code(item):
        return True
    blob = (
        f"{item.get('calculation_method') or ''} "
        f"{item.get('source_reference') or ''} "
        f"{item.get('source') or ''}"
    ).lower()
    return any(h in blob for h in _SCHEDULE_HINTS)


def _qty(item: dict[str, Any]) -> float:
    try:
        return float(item.get("quantity") or 0)
    except (TypeError, ValueError):
        return 0.0


def _near_equal(a: float, b: float, rel: float = 0.08) -> bool:
    mx = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / mx <= rel


def pay_items_similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when two rows are the same pay item taken off in different places."""
    if _unit_key(a) != _unit_key(b):
        return False
    if _unit_key(a) in {"unit", ""}:
        return False

    da = str(a.get("description") or "")
    db = str(b.get("description") or "")
    if not da.strip() or not db.strip():
        return False

    sa, sb = _size_token(da), _size_token(db)
    if sa and sb and sa != sb:
        return False
    na, nb = _npk_token(da), _npk_token(db)
    if na and nb and na != nb:
        return False
    ta, tb = _type_token(da), _type_token(db)
    if ta and tb and ta != tb:
        return False
    ma, mb = _materials(da), _materials(db)
    if ma and mb and ma != mb:
        return False
    aa, ab = _action(da), _action(db)
    if aa and ab and aa != ab:
        return False
    alta, altb = _alternate(da), _alternate(db)
    if alta and altb and alta != altb:
        return False
    ca, cb = _agency_code(a), _agency_code(b)
    if ca and cb and ca != cb:
        return False

    tok_a, tok_b = _tokens(da), _tokens(db)
    if not tok_a or not tok_b:
        return False
    if tok_a == tok_b:
        return True

    extra_a = tok_a - tok_b
    extra_b = tok_b - tok_a
    if tok_a <= tok_b and extra_b <= _WEAK_MODIFIERS:
        return True
    if tok_b <= tok_a and extra_a <= _WEAK_MODIFIERS:
        return True

    inter = len(tok_a & tok_b)
    if inter <= 0:
        return False
    dice = 2.0 * inter / (len(tok_a) + len(tok_b))
    return dice >= 0.86 and not (extra_a - _WEAK_MODIFIERS) and not (extra_b - _WEAK_MODIFIERS)


def _pick_best(items: list[dict[str, Any]]) -> dict[str, Any]:
    def score(item: dict[str, Any]) -> tuple:
        desc = str(item.get("description") or "")
        clean = 0 if _LOCATION_NOISE_RE.search(desc) else 1
        conf = 0.0
        try:
            conf = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        return (
            1 if item_is_schedule(item) else 0,
            1 if _agency_code(item) else 0,
            clean,
            conf,
            -len(desc),
        )

    return dict(max(items, key=score))


def _fmt_qty(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4g}"


def _collapse_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    if len(items) == 1:
        return dict(items[0])

    if any(_is_ls(i) for i in items):
        best = _pick_best(items)
        best["quantity"] = 1.0
        return best

    schedule = [i for i in items if item_is_schedule(i)]
    work = schedule if schedule else list(items)
    qtys = [_qty(i) for i in work]
    total = sum(qtys)
    mx = max(qtys) if qtys else 0.0
    rest = total - mx

    # One row is already the project total of the others — keep that total.
    if len(work) >= 3 and rest > 0 and mx > 0 and abs(mx - rest) / mx <= 0.08:
        keeper = next(i for i in work if _near_equal(_qty(i), mx))
        return dict(keeper)

    # Duplicate extracts of the same quantity (schedule copies / continuation pages).
    refs = {str(i.get("source_reference") or "").strip() for i in work}
    refs.discard("")
    pages = {str(i.get("source_page") or "").strip() for i in work}
    pages.discard("")
    same_ref = bool(refs) and len(refs) == 1 and all(
        str(i.get("source_reference") or "").strip() for i in work
    )
    different_pages = len(pages) > 1
    if len(work) > 1 and all(_near_equal(q, mx) for q in qtys):
        if all(item_is_schedule(i) for i in work) or (same_ref and not different_pages):
            best = _pick_best(work)
            best["quantity"] = mx
            return best

    best = _pick_best(work)
    out = dict(best)
    combined = round(total, 4)
    out["quantity"] = combined
    out["calculation_method"] = (
        f"Combined {len(work)} similar location/takeoff rows: "
        + " + ".join(_fmt_qty(q) for q in qtys)
        + f" = {_fmt_qty(combined)}"
    )
    pages = sorted(
        {
            str(i.get("source_page") or "").strip()
            for i in work
            if str(i.get("source_page") or "").strip()
        }
    )
    refs = []
    for item in work:
        ref = str(item.get("source_reference") or item.get("source") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
        if len(refs) >= 4:
            break
    if pages or refs:
        loc = []
        if pages:
            loc.append("pages " + ", ".join(pages))
        if refs:
            loc.append("; ".join(refs[:3]))
        out["source_reference"] = "Combined locations — " + " · ".join(loc)
    try:
        out["confidence"] = max(float(i.get("confidence") or 0) for i in work)
    except (TypeError, ValueError):
        pass
    return out


def combine_similar_pay_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cluster similar pay items and add location quantities into one row each."""
    rows = [dict(item) for item in items if str(item.get("description") or "").strip()]
    n = len(rows)
    if n <= 1:
        return rows

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if pay_items_similar(rows[i], rows[j]):
                union(i, j)

    groups: dict[int, list[dict[str, Any]]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)

    combined = 0
    out: list[dict[str, Any]] = []
    for group in groups.values():
        collapsed = _collapse_group(group)
        if len(group) > 1:
            combined += 1
        out.append(collapsed)
    # Preserve a stable order: original first-seen group order
    return out
