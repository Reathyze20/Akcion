"""
Numbers and dates as Czech writes them.

Why this is a module and not a habit
------------------------------------
Every sentence this app shows is read by two people, one of whom does not know
the methodology and neither of whom reads English. A screen that writes `4.23`
and `3.6 %` next to `1 807,98 Kč` is not merely inconsistent — it reads as
machine output, and machine output is what somebody stops trusting on the day
its advice is uncomfortable.

The rule was already applied at the one place it was first needed, as private
helpers inside `cylinders.py`. It is needed in six more, so it lives here.

The trap this avoids
--------------------
The obvious shortcut — take the finished sentence and replace every `.` with a
`,` — was tried and broke dates: `30. 6. 2026` became `30, 6, 2026`. Formatting
belongs at the point a number becomes text, never as a pass over prose
afterwards.
"""

from __future__ import annotations

from datetime import date, datetime


def n(value: float, places: int = 1) -> str:
    """
    A number in Czech: decimal comma, no thousands separator.

    No thousands separator on purpose — these appear inside sentences, where a
    space-separated group reads as two numbers. Amounts that need grouping are
    formatted on the screen by `lib/format.ts`, which knows the locale.
    """
    return f"{value:.{places}f}".replace(".", ",")


def pct(value: float, places: int = 1) -> str:
    """A percentage, with the space Czech typography puts before the sign."""
    return f"{n(value, places)} %"


def d(value: date | datetime) -> str:
    """A date in Czech: day, month, year, each without a leading zero."""
    return f"{value.day}. {value.month}. {value.year}"


def money(value: float, currency: str | None = None, places: int = 2) -> str:
    """
    A price with its currency, in that order.

    The currency is never dropped. Four of the twelve holdings trade in
    something other than dollars while their bands are quoted in dollars, and
    an unlabelled number in a sentence about two currencies is the shape of the
    mistake that already produced one wrong recommendation.
    """
    text = n(value, places)
    return f"{text} {currency}" if currency else text


def plural(count: float, one: str, few: str, many: str) -> str:
    """
    The right form of a Czech noun for a count.

    Czech declines one, two-to-four, and five-or-more differently. Getting it
    wrong is the difference between a sentence written for somebody and a
    sentence assembled by a machine — "hotovost vydrží 4 měsíců" is the second
    kind, and it appears on the screen these two people are meant to trust.

    Decline against the number as WRITTEN
    -------------------------------------
    Pass the same value that reaches the page. SMSI's runway is 4,4 months and
    prints rounded as "4"; declining against 4,4 took the genitive and produced
    exactly the "4 měsíců" this docstring warns about — a noun agreeing with a
    number the reader cannot see. `months()` below rounds first for that reason.

    A fraction that is actually shown as a fraction takes the genitive, which is
    what Czech does: "4,5 měsíce".
    """
    if count != int(count):
        return many
    whole = abs(int(count))
    if whole == 1:
        return one
    if 2 <= whole <= 4:
        return few
    return many


def months(count: float) -> str:
    """
    `4 měsíce`, `1 měsíc`, `8 měsíců` — the count and its noun, agreeing.

    Rounded before declining, because the rounded figure is the one on screen
    and the noun has to agree with what the reader sees.
    """
    shown = round(count)
    return f"{n(shown, 0)} {plural(shown, 'měsíc', 'měsíce', 'měsíců')}"
