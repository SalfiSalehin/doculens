"""Money/date parsing and arithmetic checks for extracted receipts.

Conventions (documented in docs/DECISIONS.md):
* A single separator followed by exactly 3 digits is a thousands separator
  ("25.000" -> 25000, common in CORD/Indonesian receipts). 1-2 digits -> decimal.
* When both "." and "," appear, the last one is the decimal separator.
* Dates are parsed day-first (SROIE is Malaysian, CORD is Indonesian).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

Status = Literal["pass", "fail", "skipped"]

DEFAULT_ABS_TOL = Decimal("0.02")

_CURRENCY_RE = re.compile(r"(?i)(rp|rm|usd|idr|myr|sgd|eur|gbp|bdt|tk|[$€£¥৳])")
_NUMBER_CHARS_RE = re.compile(r"^[0-9.,]+$")


# --------------------------------------------------------------------------- money


def parse_money(text: str | int | float | Decimal | None) -> Decimal | None:
    """Parse a money string into a Decimal. Returns None if it is not a clean amount."""
    if text is None:
        return None
    if isinstance(text, Decimal):
        return text
    if isinstance(text, int | float):
        return Decimal(str(text))

    s = _CURRENCY_RE.sub("", str(text)).replace(" ", "").replace("\u00a0", "").strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.startswith("-"):
        negative, s = True, s[1:]
    elif s.endswith("-"):  # "12.50-" is used for discounts on some receipts
        negative, s = True, s[:-1]
    if not s or not _NUMBER_CHARS_RE.match(s) or not any(c.isdigit() for c in s):
        return None

    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        int_part, _, frac = s.rpartition(dec)
        if dec in int_part or not _valid_grouping(int_part, thou):
            return None
        normalized = int_part.replace(thou, "") + "." + frac
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        parts = s.split(sep)
        if len(parts) > 2:
            if not _valid_grouping(s, sep):
                return None
            normalized = s.replace(sep, "")
        else:
            left, right = parts
            if len(right) == 3 and left:
                normalized = left + right  # thousands
            elif 1 <= len(right) <= 2:
                normalized = (left or "0") + "." + right
            else:
                return None
    else:
        normalized = s

    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    return -value if negative else value


def _valid_grouping(int_part: str, sep: str) -> bool:
    if sep not in int_part:
        return int_part.isdigit()
    groups = int_part.split(sep)
    return (
        groups[0].isdigit()
        and 1 <= len(groups[0]) <= 3
        and all(len(g) == 3 and g.isdigit() for g in groups[1:])
    )


def _close(a: Decimal, b: Decimal, abs_tol: Decimal) -> bool:
    return abs(a - b) <= abs_tol


# --------------------------------------------------------------------------- checks


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    message: str
    expected: Decimal | None = None
    actual: Decimal | None = None

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass(frozen=True)
class LineItem:
    name: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


def check_totals(
    subtotal: Decimal | None,
    tax: Decimal | None,
    total: Decimal | None,
    *,
    discount: Decimal | None = None,
    service: Decimal | None = None,
    abs_tol: Decimal = DEFAULT_ABS_TOL,
) -> CheckResult:
    """subtotal + tax + service - discount == total (within tolerance)."""
    if subtotal is None or total is None:
        return CheckResult("totals", "skipped", "Subtotal or total missing.")
    expected = subtotal + (tax or 0) + (service or 0) - abs(discount or 0)
    if _close(expected, total, abs_tol):
        return CheckResult("totals", "pass", "Totals add up.", expected, total)
    return CheckResult(
        "totals", "fail", f"Expected total {expected}, found {total}.", expected, total
    )


def check_line_items(
    items: list[LineItem],
    subtotal: Decimal | None,
    *,
    abs_tol: Decimal = DEFAULT_ABS_TOL,
) -> list[CheckResult]:
    """Each qty * unit_price == amount, and sum(amounts) == subtotal."""
    results: list[CheckResult] = []
    for i, item in enumerate(items):
        name = f"line_item[{i}]"
        if item.quantity is None or item.unit_price is None or item.amount is None:
            results.append(CheckResult(name, "skipped", "Quantity, unit price or amount missing."))
            continue
        expected = item.quantity * item.unit_price
        if _close(expected, item.amount, abs_tol):
            results.append(CheckResult(name, "pass", "Line adds up.", expected, item.amount))
        else:
            results.append(
                CheckResult(
                    name,
                    "fail",
                    f"Expected {expected}, found {item.amount}.",
                    expected,
                    item.amount,
                )
            )

    amounts = [it.amount for it in items]
    if not items or subtotal is None or any(a is None for a in amounts):
        results.append(CheckResult("line_items_sum", "skipped", "Items or subtotal missing."))
    else:
        total = sum(amounts, Decimal(0))  # type: ignore[arg-type]
        # Tolerance grows with item count because each line may be rounded.
        tol = abs_tol * max(1, len(items))
        if _close(total, subtotal, tol):
            results.append(
                CheckResult("line_items_sum", "pass", "Items sum to subtotal.", total, subtotal)
            )
        else:
            results.append(
                CheckResult(
                    "line_items_sum",
                    "fail",
                    f"Items sum to {total}, subtotal is {subtotal}.",
                    total,
                    subtotal,
                )
            )
    return results


# --------------------------------------------------------------------------- dates

_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%b-%y", "%d %b %y",
    "%b %d, %Y", "%B %d, %Y", "%b %d %Y",
)  # fmt: skip


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    s = re.sub(r"\s+", " ", str(text).strip().rstrip(".,"))
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()  # noqa: DTZ007 - naive date is intended
        except ValueError:
            continue
    return None


def check_date(
    text: str | None,
    *,
    today: date | None = None,
    earliest: date = date(1990, 1, 1),
) -> CheckResult:
    if not text:
        return CheckResult("date", "skipped", "Date missing.")
    parsed = parse_date(text)
    if parsed is None:
        return CheckResult("date", "fail", f"Could not parse date {text!r}.")
    today = today or date.today()
    if parsed > today + timedelta(days=1):
        return CheckResult("date", "fail", f"Date {parsed.isoformat()} is in the future.")
    if parsed < earliest:
        return CheckResult("date", "fail", f"Date {parsed.isoformat()} is implausibly old.")
    return CheckResult("date", "pass", f"Valid date {parsed.isoformat()}.")
