"""
The price-reconciliation ladder: can the sheet's price be trusted against the tape?

Everything downstream — the entry profile, the neighbours, any statistic — is
only as good as this answer, so the ladder is tested for two properties that
matter more than its individual rules:

* It is TOTAL. Every input produces exactly one verdict. A row that falls
  through the bottom of a taxonomy silently leaves the sample.
* It does not LAUNDER. A price that disagrees with the tape may only be accepted
  when the tape itself reports the split that explains the disagreement. This is
  the failure most likely to quietly poison every number below it, and the two
  tests for it are the most valuable in the file.

No network. Every case is a hand-built series.
"""

from datetime import date

import pytest

from research.dataset import Entry
from research.prices import Bar, Bars, PriceError
from research.reconcile import (
    FETCH_FAILED,
    MATCHED,
    MATCHED_ADJUSTED,
    MATCHED_RAW,
    MATCHED_VIA_FACTOR,
    MISMATCH_UNEXPLAINED,
    NO_DATA_AT_ALL,
    NO_DATA_BEFORE_ENTRY,
    NO_DATA_DELISTED,
    REASON_CS,
    RENAMED_UNRESOLVED,
    SKIPPED_DUPLICATE,
    SKIPPED_NOT_EQUITY,
    SKIPPED_NO_PRICE,
    reconcile_all,
    reconcile_entry,
)


def bar(day: str, close: float, *, adj: float | None = None,
        spread: float = 0.02, split: float = 0.0) -> Bar:
    """One session, with a small high/low band around the close."""
    return Bar(
        day=date.fromisoformat(day),
        open=close,
        high=close * (1 + spread),
        low=close * (1 - spread),
        close=close,
        adj_close=adj if adj is not None else close,
        volume=100_000,
        split=split,
    )


def series(ticker: str, rows: list[Bar]) -> Bars:
    return Bars(ticker=ticker, rows=tuple(rows))


def entry(
    *,
    row_id: int = 1,
    ticker: str = "ACME",
    price: float | None = 10.0,
    opened: str = "2024-01-10",
    closed: str | None = "2024-06-10",
    instrument: str = "LONG_EQUITY",
    duplicate_of: int | None = None,
) -> Entry:
    return Entry(
        row_id=row_id, company="Acme", ticker=ticker,
        initial_interest=date.fromisoformat(opened),
        pause_interest=date.fromisoformat(closed) if closed else None,
        days_claimed=0, inclination="Long",
        status="CLOSED" if closed else "",
        initial_price=price, final_price=None,
        final_change_pct=None, final_net_change_pct=None,
        peak_return_live_pct_unusable="N/A", latest_notes="", footnote="",
        instrument=instrument,
        exit_kind="DECISION" if closed else "STILL_OPEN",
        exit_reason="UNKNOWN" if closed else "",
        duplicate_of=duplicate_of, label_note="",
    )


HEALTHY = series("ACME", [
    bar("2024-01-08", 9.5),
    bar("2024-01-09", 9.8),
    bar("2024-01-10", 10.0),
    bar("2024-03-01", 12.0),
    bar("2024-06-10", 14.0),
    bar("2024-09-01", 15.0),
])


# ==============================================================================
# The ladder is total
# ==============================================================================

class TestEveryVerdictIsReachable:
    """
    One case per verdict. If a branch stops being reachable, the taxonomy has a
    hole and rows are falling out of the sample through it.
    """

    def test_matched_raw(self):
        v = reconcile_entry(entry(price=10.0), HEALTHY)
        assert v.verdict == MATCHED_RAW
        assert v.bar_date == date(2024, 1, 10)

    def test_matched_adjusted(self):
        """
        The sheet's figure fits the dividend-adjusted series and not the tape.

        A finding, not a clean pass: it means the transcription used a
        currently-displayed number instead of the historical one.
        """
        dividended = series("ACME", [
            bar("2024-01-10", 10.0, adj=9.0),
            bar("2024-06-10", 14.0, adj=12.6),
        ])
        v = reconcile_entry(entry(price=9.0), dividended)
        assert v.verdict == MATCHED_ADJUSTED
        assert "zpětně přepočtené" in v.note

    def test_matched_via_factor(self):
        """
        A 1-for-10 reverse split the tape reports, and a price that fits once it
        is undone.
        """
        split = series("ACME", [
            bar("2024-01-10", 100.0),           # $10.00 as quoted, x10 adjusted
            bar("2024-03-01", 120.0, split=0.1),
            bar("2024-06-10", 140.0),
        ])
        v = reconcile_entry(entry(price=10.0), split)
        assert v.verdict == MATCHED_VIA_FACTOR
        assert v.split_product == pytest.approx(0.1)

    def test_mismatch_unexplained(self):
        v = reconcile_entry(entry(price=3.33), HEALTHY)
        assert v.verdict == MISMATCH_UNEXPLAINED

    def test_no_data_at_all(self):
        v = reconcile_entry(entry(), series("ACME", []))
        assert v.verdict == NO_DATA_AT_ALL

    def test_no_data_delisted(self):
        """Bars that stop before the sheet closed the position."""
        short = series("ACME", [bar("2024-01-10", 10.0), bar("2024-02-01", 11.0)])
        v = reconcile_entry(entry(closed="2024-06-10"), short)
        assert v.verdict == NO_DATA_DELISTED

    def test_no_data_before_entry(self):
        """The symbol did not trade yet — a different fact from delisting."""
        late = series("ACME", [bar("2024-05-01", 10.0), bar("2024-06-10", 11.0)])
        v = reconcile_entry(entry(opened="2024-01-10", closed="2024-06-10"), late)
        assert v.verdict == NO_DATA_BEFORE_ENTRY

    def test_fetch_failed_is_not_a_fact_about_the_company(self):
        v = reconcile_entry(entry(), PriceError("timeout"))
        assert v.verdict == FETCH_FAILED
        assert "o síti" in v.reason_cs

    def test_skipped_not_equity(self):
        v = reconcile_entry(entry(instrument="ETF_HEDGE"), HEALTHY)
        assert v.verdict == SKIPPED_NOT_EQUITY

    def test_skipped_duplicate(self):
        v = reconcile_entry(entry(duplicate_of=9), HEALTHY)
        assert v.verdict == SKIPPED_DUPLICATE

    def test_skipped_no_price(self):
        v = reconcile_entry(entry(price=None), HEALTHY)
        assert v.verdict == SKIPPED_NO_PRICE

    def test_every_verdict_carries_a_czech_reason(self):
        """
        The role `test_czech.py` plays for the app: an absence the owner reads
        has to be a sentence, not an enum.
        """
        assert all(REASON_CS[key].strip() for key in REASON_CS)
        assert all(not REASON_CS[key].endswith("  ") for key in REASON_CS)


# ==============================================================================
# The laundering guard
# ==============================================================================

class TestAFactorNeedsTheTapeToAgree:
    """
    The most important pair of tests here.

    A price ten times off the tape is equally consistent with a 1-for-10 reverse
    split and with a decimal point in the wrong place. Only the first is a
    correction; the second is a wrong number about to become a data point.
    """

    def test_a_tenfold_gap_with_a_reported_split_is_accepted(self):
        with_split = series("ACME", [
            bar("2024-01-10", 100.0),
            bar("2024-03-01", 120.0, split=0.1),
            bar("2024-06-10", 140.0),
        ])
        assert reconcile_entry(entry(price=10.0), with_split).verdict == (
            MATCHED_VIA_FACTOR
        )

    def test_the_same_gap_with_no_reported_split_is_refused(self):
        without_split = series("ACME", [
            bar("2024-01-10", 100.0),
            bar("2024-03-01", 120.0),
            bar("2024-06-10", 140.0),
        ])
        assert reconcile_entry(entry(price=10.0), without_split).verdict == (
            MISMATCH_UNEXPLAINED
        )

    def test_a_gap_no_split_could_produce_is_refused(self):
        """1.37-for-1 is not a thing an exchange reports."""
        odd = series("ACME", [
            bar("2024-01-10", 10.0),
            bar("2024-03-01", 12.0, split=0.1),
            bar("2024-06-10", 14.0),
        ])
        assert reconcile_entry(entry(price=13.7), odd).verdict == (
            MISMATCH_UNEXPLAINED
        )

    def test_two_reverse_splits_compound(self):
        """
        SMSI is why the hand-written list of plausible ratios was thrown out.

        1-for-8 and then 1-for-5 makes a cumulative 0.025, which no list of
        integer reciprocals up to twenty contains. The tape's own events do.
        """
        compounded = series("SMSI", [
            bar("2021-03-12", 266.8),
            bar("2024-05-01", 200.0, split=0.125),
            bar("2026-01-01", 150.0, split=0.2),
            bar("2026-08-01", 100.0),
        ])
        v = reconcile_entry(
            entry(ticker="SMSI", price=6.67, opened="2021-03-12",
                  closed="2024-09-17"),
            compounded,
        )
        assert v.verdict == MATCHED_VIA_FACTOR
        assert v.split_product == pytest.approx(0.025)


# ==============================================================================
# Tolerance and bar choice
# ==============================================================================

class TestToleranceAndBarChoice:

    def test_inside_the_days_range_passes(self):
        assert reconcile_entry(entry(price=10.15), HEALTHY).verdict in MATCHED

    def test_five_percent_outside_fails(self):
        assert reconcile_entry(entry(price=10.6), HEALTHY).verdict == (
            MISMATCH_UNEXPLAINED
        )

    def test_the_previous_session_also_counts(self):
        """
        Mark writes ideas up in the evening, so the price he noted may be the
        prior close. Both sessions are candidates; neither is preferred.

        The price here fits only 9 January's range, not 10 January's, so a
        ladder that looked at the entry day alone would call it a mismatch.
        """
        gapped = series("ACME", [
            bar("2024-01-09", 7.0, spread=0.01),
            bar("2024-01-10", 10.0, spread=0.01),
            bar("2024-06-10", 14.0),
        ])
        v = reconcile_entry(entry(price=7.0), gapped)
        assert v.verdict == MATCHED_RAW
        assert v.bar_date == date(2024, 1, 9)

    def test_a_shut_market_on_the_entry_date_moves_forward(self):
        """The sheet's date is a day somebody wrote something down."""
        gapped = series("ACME", [bar("2024-01-15", 10.0), bar("2024-06-10", 14.0)])
        v = reconcile_entry(entry(price=10.0, opened="2024-01-13"), gapped)
        assert v.bar_date == date(2024, 1, 15)

    def test_an_empty_frame_is_never_a_match_and_never_a_zero(self):
        v = reconcile_entry(entry(), series("ACME", []))
        assert v.verdict not in MATCHED
        assert v.raw_close is None
        assert v.factor is None


# ==============================================================================
# Renames
# ==============================================================================

class TestRenames:

    def test_an_unknown_dead_symbol_is_work_left_to_do(self, monkeypatch):
        """
        `RENAMED_UNRESOLVED` is a queue, not a result. Collapsing it into
        "delisted" would declare the hand-work finished before it was.
        """
        import research.reconcile as rc
        monkeypatch.setattr(rc, "load_renames", lambda: {})
        verdicts = rc.reconcile_all([entry(ticker="GONE")], {"GONE": series("GONE", [])})
        assert verdicts[0].verdict == RENAMED_UNRESOLVED

    def test_a_looked_at_dead_symbol_is_a_confirmed_absence(self, monkeypatch):
        import research.reconcile as rc
        monkeypatch.setattr(
            rc, "load_renames",
            lambda: {
                "GONE": rc.Rename("GONE", "", date(2022, 1, 1), "ACQUIRED", "koupena")
            },
        )
        verdicts = rc.reconcile_all([entry(ticker="GONE")], {"GONE": series("GONE", [])})
        assert verdicts[0].verdict == NO_DATA_DELISTED
        assert "koupena" in verdicts[0].note

    def test_a_successor_is_used_when_it_has_data(self, monkeypatch):
        import research.reconcile as rc
        monkeypatch.setattr(
            rc, "load_renames",
            lambda: {
                "OLD": rc.Rename("OLD", "NEW", date(2021, 4, 19), "RENAME", "prejmenovano")
            },
        )
        verdicts = rc.reconcile_all(
            [entry(ticker="OLD", price=10.0)],
            {"OLD": series("OLD", []), "NEW": HEALTHY},
        )
        assert verdicts[0].verdict == MATCHED_RAW
        assert verdicts[0].resolved_ticker == "ACME"

    def test_the_lookup_runs_one_way_only(self, monkeypatch):
        """
        A query for the successor must never claim to be the predecessor.

        Two-way would make a 2015 USAT row and a 2026 CTLP position the same
        thing — the exact error that keeps this table out of
        `app/core/tickers.py`.
        """
        import research.reconcile as rc
        monkeypatch.setattr(
            rc, "load_renames",
            lambda: {"OLD": rc.Rename("OLD", "NEW", None, "RENAME", "x")},
        )
        verdicts = rc.reconcile_all(
            [entry(ticker="NEW")], {"NEW": series("NEW", []), "OLD": HEALTHY}
        )
        assert verdicts[0].verdict == RENAMED_UNRESOLVED


# ==============================================================================
# Against the app
# ==============================================================================

def test_the_first_bar_rule_matches_the_live_evaluator():
    """
    `Bars.on_or_after` and `score_outcomes._first_bar_from` have to agree.

    They are the same idea in two places, and the premise of comparing the app
    against the sheet is that "the session for this date" means one thing.
    """
    from decimal import Decimal

    from app.services.score_outcomes import _first_bar_from

    days = ["2024-01-08", "2024-01-09", "2024-01-10", "2024-03-01"]
    mine = series("ACME", [bar(d, 10.0) for d in days])
    # The app's Bar is `tuple[date, Decimal]`, not a class — hence the pair.
    theirs = [(date.fromisoformat(d), Decimal("10")) for d in days]

    for probe in ("2024-01-07", "2024-01-09", "2024-01-11", "2024-05-01"):
        when = date.fromisoformat(probe)
        ours = mine.on_or_after(when)
        app = _first_bar_from(theirs, when)
        assert (ours.day if ours else None) == (app[0] if app else None)
