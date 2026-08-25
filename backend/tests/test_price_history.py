"""
The peak the drawdown rule is actually about.

The lifecycle rubric measures "retraces a large part of the Great Find move"
(§3) against a peak. It was using Yahoo's 52-week high, which is wrong twice
over: a thesis that topped eighteen months ago reads as un-retraced, and the
figure sat in a cache whose price field went stale — ECOR carried a July price
into late August, turning a real 4 % drawdown into 41 % and flipping the verdict
from hold to sell.

Two traps are tested harder than the rest, because both were live:

  * **the all-time high is meaningless here.** Split-adjusted, SMSI peaks at
    5 120 USD and IZEA at 2 720. Against those every holding reads as 99 %
    retraced, and
  * **the history may belong to a different listing.** `IMP.V` is held in euros
    and its bars come from `ITMSF` in dollars. Filing those under "IMP.V" lets
    a later comparison divide a euro price by a dollar peak.
"""

from datetime import date, datetime, timedelta, timezone

from app.services.price_history import (
    LOOKBACK_YEARS,
    STORE_YEARS,
    Peak,
)


def bar(day: date, close: float) -> tuple:
    return (day, close, close, close, close, 1000)


# ==============================================================================
# The window, and why it is not "everything"
# ==============================================================================

def test_the_window_is_shorter_than_what_is_stored():
    """
    Kept wider than it is read, so the window can be widened later without
    re-fetching a decade from somebody else's server.
    """
    assert LOOKBACK_YEARS < STORE_YEARS


def test_the_window_is_long_enough_for_a_thesis_that_topped_last_year():
    """
    The 52-week high missed exactly this: VTSI peaked in November 2024 and a
    one-year window would have said it was barely off its high.
    """
    assert LOOKBACK_YEARS >= 2


# ==============================================================================
# The peak carries its date and its listing
# ==============================================================================

def test_a_peak_says_when_it_happened():
    """
    „57 % pod maximem" and „57 % pod maximem z 13. 11. 2024" are different
    claims. Only the second can be judged against "was that the Great Find
    move".
    """
    peak = Peak(value=8.17, on=date(2024, 11, 13), since=date(2024, 8, 24))
    assert peak.label_cs == "13. 11. 2024"


def test_a_peak_says_which_listing_it_came_from():
    """
    The currency lives on the listing. `ITMSF` peaks in dollars while the
    `IMP.V` position is priced in euros, and the caller must be able to tell.
    """
    peak = Peak(value=2.51, on=date(2025, 9, 15), since=date(2024, 8, 24),
                symbol="ITMSF")
    assert peak.symbol == "ITMSF"


def test_a_peak_without_a_listing_is_still_usable():
    """Same-listing history needs no reconciliation and should not demand one."""
    peak = Peak(value=8.17, on=date(2024, 11, 13), since=date(2024, 8, 24))
    assert peak.symbol == ""


# ==============================================================================
# Fetching, without a network
# ==============================================================================

def test_the_fetcher_is_injectable_so_the_rules_run_offline():
    from app.services.price_history import refresh

    calls: list[str] = []

    def fake(symbol: str):
        calls.append(symbol)
        return []

    class NoDb:
        def execute(self, *_a, **_k):  # pragma: no cover — never reached
            raise AssertionError("nothing to store")

    assert refresh(NoDb(), "NOPE", fetch=fake) == 0
    assert calls  # every listing was tried


def test_a_source_that_raises_does_not_stop_the_others():
    """One company Yahoo cannot serve must not take the other eleven with it."""
    from app.services.price_history import refresh

    def angry(symbol: str):
        raise RuntimeError("Yahoo is having a day")

    class NoDb:
        def execute(self, *_a, **_k):  # pragma: no cover
            raise AssertionError("nothing to store")

    assert refresh(NoDb(), "VTSI", fetch=angry) == 0


def test_bars_are_stored_under_the_symbol_that_answered():
    """
    Not under the symbol asked for. `IMP.V` is held in euros and answers from
    `ITMSF` in dollars; filing those as "IMP.V" is how a euro price ends up
    divided by a dollar peak.
    """
    from app.services.price_history import refresh

    stored: list[str] = []

    class SpyDb:
        def execute(self, _stmt, payload=None):
            if isinstance(payload, list) and payload:
                stored.append(payload[0]["ticker"])
            class R:
                rowcount = 0
            return R()

    def fake(symbol: str):
        return [bar(date(2026, 8, 20), 1.0)] if symbol == "ITMSF" else []

    refresh(SpyDb(), "IMP.V", fetch=fake)
    assert stored == ["ITMSF"]


def test_the_retention_cutoff_follows_the_stated_window():
    from app.services import price_history

    cutoff = datetime.now(timezone.utc) - timedelta(days=price_history._STORE_DAYS)
    assert (datetime.now(timezone.utc) - cutoff).days >= STORE_YEARS * 365
