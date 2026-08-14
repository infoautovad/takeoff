"""Compare expected vs actual BOQ takeoff for gold-set / regression checks.

Used by tests and `scripts/run_gold_set.py`. No OpenAI/APS required for
pure quantity_engine cases; full PDF cases can feed precomputed actual items.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


CATEGORY_ALIASES = {
    "utilities": "Utilities",
    "utility": "Utilities",
    "drainage": "Drainage",
    "earthwork": "Earthwork",
    "pavement": "Pavement",
    "roadside": "Roadside",
    "structures": "Structures",
    "geometry": "Geometry",
    "bid schedule": "Bid schedule",
    "unmapped takeoff": "Unmapped takeoff",
}


def _norm_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _norm_unit(value: str | None) -> str:
    u = _norm_text(value).replace(".", "")
    aliases = {
        "lf": "lf",
        "lin ft": "lf",
        "linear feet": "lf",
        "linear foot": "lf",
        "m": "m",
        "lm": "m",
        "ea": "ea",
        "each": "ea",
        "nos": "ea",
        "no": "ea",
        "cy": "cy",
        "cu yd": "cy",
        "cuyd": "cy",
        "m3": "m3",
        "cum": "m3",
        "sf": "sf",
        "sq ft": "sf",
        "sy": "sy",
        "sq yd": "sy",
    }
    return aliases.get(u, u or "unit")


def _norm_category(value: str | None) -> str:
    key = _norm_text(value)
    return CATEGORY_ALIASES.get(key, (value or "Other").strip() or "Other")


def _size_token(text: str) -> str | None:
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*-?\s*(?:inch|in|\"|'')", text, re.I)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if abs(val - int(val)) < 0.01:
        return f"{int(val)}-inch"
    return f"{val:g}-inch"


def _tokens(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "of", "a", "an", "to", "in", "on", "or", "type", "size"}
    return {t for t in re.findall(r"[a-z0-9.]+", text.lower()) if len(t) > 1 and t not in stop}


@dataclass
class ExpectedItem:
    description: str
    unit: str
    category: str | None = None
    quantity: float | None = None
    quantity_tolerance: float = 0.05  # relative
    quantity_abs_tolerance: float = 1.0
    item_code: str | None = None
    required: bool = True


@dataclass
class MatchHit:
    expected: dict[str, Any]
    actual: dict[str, Any]
    qty_ok: bool
    qty_delta: float | None
    method: str


@dataclass
class CompareReport:
    expected_count: int = 0
    actual_count: int = 0
    hits: list[MatchHit] = field(default_factory=list)
    misses: list[dict[str, Any]] = field(default_factory=list)
    extras: list[dict[str, Any]] = field(default_factory=list)
    misses_by_category: dict[str, int] = field(default_factory=dict)
    qty_errors: list[dict[str, Any]] = field(default_factory=list)
    unmapped_actual: list[dict[str, Any]] = field(default_factory=list)
    recall: float = 0.0
    precision_proxy: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "hits": [
                {
                    "expected": h.expected,
                    "actual_description": h.actual.get("description"),
                    "qty_ok": h.qty_ok,
                    "qty_delta": h.qty_delta,
                    "method": h.method,
                }
                for h in self.hits
            ],
            "misses": self.misses,
            "extras": [
                {
                    "description": e.get("description"),
                    "unit": e.get("unit"),
                    "category": e.get("category"),
                    "quantity": e.get("quantity"),
                }
                for e in self.extras
            ],
            "misses_by_category": self.misses_by_category,
            "qty_errors": self.qty_errors,
            "unmapped_actual": [
                {"description": u.get("description"), "unit": u.get("unit")}
                for u in self.unmapped_actual
            ],
            "recall": self.recall,
            "precision_proxy": self.precision_proxy,
        }


def parse_expected_items(raw: list[dict[str, Any]] | dict[str, Any]) -> list[ExpectedItem]:
    rows = raw.get("items") if isinstance(raw, dict) else raw
    out: list[ExpectedItem] = []
    for row in rows or []:
        out.append(
            ExpectedItem(
                description=str(row.get("description") or ""),
                unit=str(row.get("unit") or "UNIT"),
                category=row.get("category"),
                quantity=float(row["quantity"]) if row.get("quantity") is not None else None,
                quantity_tolerance=float(row.get("quantity_tolerance", 0.05)),
                quantity_abs_tolerance=float(row.get("quantity_abs_tolerance", 1.0)),
                item_code=row.get("item_code"),
                required=bool(row.get("required", True)),
            )
        )
    return out


def _item_match_score(expected: ExpectedItem, actual: dict[str, Any]) -> tuple[float, str]:
    ed = _norm_text(expected.description)
    ad = _norm_text(str(actual.get("description") or ""))
    eu = _norm_unit(expected.unit)
    au = _norm_unit(str(actual.get("unit") or ""))
    if not ed or not ad:
        return 0.0, "empty"
    if eu != au and eu != "unit" and au != "unit":
        return 0.0, "unit_mismatch"

    e_size = _size_token(ed)
    a_size = _size_token(ad)
    if e_size and a_size and e_size != a_size:
        return 0.0, "size_mismatch"

    if ed == ad:
        return 100.0, "exact"
    if ed in ad or ad in ed:
        return 90.0, "substring"

    et, at = _tokens(ed), _tokens(ad)
    if not et or not at:
        return 0.0, "no_tokens"
    overlap = len(et & at) / max(len(et), 1)
    score = overlap * 100.0
    if e_size and a_size and e_size == a_size:
        score = min(100.0, score + 15.0)
    if score >= 55:
        return score, "token_overlap"
    return 0.0, "no_match"


def _qty_ok(expected: ExpectedItem, actual_qty: float) -> tuple[bool, float | None]:
    if expected.quantity is None:
        return True, None
    delta = abs(actual_qty - expected.quantity)
    rel = delta / max(abs(expected.quantity), 1e-9)
    ok = delta <= expected.quantity_abs_tolerance or rel <= expected.quantity_tolerance
    return ok, delta


def compare_boq(
    expected: list[ExpectedItem] | list[dict[str, Any]] | dict[str, Any],
    actual: list[dict[str, Any]],
) -> CompareReport:
    """Match expected gold items to actual takeoff/BOQ rows; report misses by category."""
    if isinstance(expected, list) and expected and isinstance(expected[0], ExpectedItem):
        exp_items = expected  # type: ignore[assignment]
    else:
        exp_items = parse_expected_items(expected)  # type: ignore[arg-type]
    report = CompareReport(expected_count=len(exp_items), actual_count=len(actual))
    used_actual: set[int] = set()

    for exp in exp_items:
        best_idx = -1
        best_score = 0.0
        best_method = "no_match"
        for idx, act in enumerate(actual):
            if idx in used_actual:
                continue
            score, method = _item_match_score(exp, act)
            if score > best_score:
                best_score = score
                best_idx = idx
                best_method = method
        if best_idx < 0 or best_score < 55:
            if exp.required:
                miss = {
                    "description": exp.description,
                    "unit": exp.unit,
                    "category": _norm_category(exp.category),
                    "quantity": exp.quantity,
                    "item_code": exp.item_code,
                }
                report.misses.append(miss)
                cat = _norm_category(exp.category)
                report.misses_by_category[cat] = report.misses_by_category.get(cat, 0) + 1
            continue

        act = actual[best_idx]
        used_actual.add(best_idx)
        try:
            aqty = float(act.get("quantity") or 0)
        except (TypeError, ValueError):
            aqty = 0.0
        ok, delta = _qty_ok(exp, aqty)
        hit = MatchHit(
            expected=asdict(exp),
            actual=act,
            qty_ok=ok,
            qty_delta=delta,
            method=best_method,
        )
        report.hits.append(hit)
        if not ok:
            report.qty_errors.append(
                {
                    "description": exp.description,
                    "expected_qty": exp.quantity,
                    "actual_qty": aqty,
                    "delta": delta,
                    "unit": exp.unit,
                    "category": _norm_category(exp.category),
                }
            )

    for idx, act in enumerate(actual):
        if idx not in used_actual:
            report.extras.append(act)
        method = str(act.get("bid_match_method") or "")
        if method == "unmapped" or (
            act.get("bid_template_line_id") is None
            and str(act.get("category") or "").lower() == "unmapped takeoff"
        ):
            report.unmapped_actual.append(act)

    required = sum(1 for e in exp_items if e.required) or len(exp_items) or 1
    report.recall = round(len(report.hits) / required, 4)
    report.precision_proxy = round(
        len(report.hits) / max(len(actual), 1),
        4,
    )
    return report


def summarize_report(report: CompareReport) -> str:
    lines = [
        f"Recall: {report.recall:.0%}  ({len(report.hits)}/{report.expected_count} expected)",
        f"Actual rows: {report.actual_count}  |  extras: {len(report.extras)}  |  qty errors: {len(report.qty_errors)}",
    ]
    if report.misses_by_category:
        cats = ", ".join(f"{k}={v}" for k, v in sorted(report.misses_by_category.items()))
        lines.append(f"Misses by category: {cats}")
    for m in report.misses[:12]:
        lines.append(f"  MISS [{m.get('category')}] {m.get('description')} ({m.get('unit')})")
    for q in report.qty_errors[:8]:
        lines.append(
            f"  QTY  {q.get('description')}: expected {q.get('expected_qty')} "
            f"got {q.get('actual_qty')} (delta {q.get('delta')})"
        )
    return "\n".join(lines)
