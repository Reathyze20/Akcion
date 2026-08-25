"""
When a company reports next, for the ones nobody else will say.

Two holdings — GKPRF and KUYAF — had no earnings date from anywhere: the
provider does not cover them and neither files with EDGAR, so the fourteen-day
blackout the canon requires had nothing to fire on. Both publish their results
on their own site, on a calendar that has barely moved in years.

What has to hold is that the estimate stays an estimate: never presented as an
announced date, never more precise than the source that produced it, and never
answering with the anniversary of a report the company has already published.
"""

import json
from datetime import date

from app.models.earnings import SOURCE_RELEASE_CADENCE
from app.services import release_fundamentals
from app.services.earnings_calendar import estimate_from_release_history


def _file(tmp_path, publications, *, note="z IR stránky", ticker="GKPRF"):
    path = tmp_path / "company_releases.json"
    path.write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "ticker": ticker,
                        "period_end": "2026-05-31",
                        "published": "2026-07-21",
                        "source_url": "https://example.com/fq3",
                        "readings": {},
                        "publication_history": {
                            "note": note,
                            "publications": publications,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    release_fundamentals._load.cache_clear()
    return path


def _monthly():
    """Gatekeeper's shape: quarters in January, April, July and December."""
    return [
        {"label": "FY2025 Q1", "published": "2025-01"},
        {"label": "FY2025 Q2", "published": "2025-04"},
        {"label": "FY2025 Q3", "published": "2025-07"},
        {"label": "FY2025 Q4", "published": "2025-12"},
        {"label": "FY2026 Q1", "published": "2026-01"},
        {"label": "FY2026 Q2", "published": "2026-04"},
        {"label": "FY2026 Q3", "published": "2026-07"},
    ]


def _daily():
    """Kuya's shape: press releases carrying the exact day."""
    return [
        {"label": "Q2 2025", "published": "2025-09-02"},
        {"label": "Q3 2025", "published": "2025-11-21"},
        {"label": "Q1 2026", "published": "2026-05-27"},
        {"label": "Q2 2026", "published": "2026-08-17"},
    ]


def _estimate(tmp_path, publications, *, today=date(2026, 8, 25), ticker="GKPRF"):
    path = _file(tmp_path, publications, ticker=ticker)
    original = release_fundamentals.DATA_FILE
    release_fundamentals.DATA_FILE = path
    try:
        return estimate_from_release_history(ticker, today=today)
    finally:
        release_fundamentals.DATA_FILE = original
        release_fundamentals._load.cache_clear()


# ==============================================================================
# The pattern that actually holds is the month of the year
# ==============================================================================

def test_the_annual_report_is_not_averaged_into_the_wrong_month(tmp_path):
    """
    Gatekeeper's fourth quarter takes five months and the other three take
    three. A median gap from the July filing lands in October and puts the
    blackout two months early; the month-of-year pattern lands in December.
    """
    guess = _estimate(tmp_path, _monthly())

    assert guess is not None
    assert guess.next_date.month == 12
    assert guess.source == SOURCE_RELEASE_CADENCE
    assert guess.confirmed is False


def test_a_report_already_published_does_not_come_round_again_in_a_fortnight(tmp_path):
    """
    Kuya put out Q2 on 17 August 2026; last year's Q2 landed on 2 September.
    The naive anniversary is two weeks away and describes a report that is
    already out.
    """
    guess = _estimate(tmp_path, _daily(), ticker="KUYAF")

    assert guess is not None
    assert guess.next_date == date(2026, 11, 21)  # Q3, not last year's Q2


# ==============================================================================
# Precision is never invented
# ==============================================================================

def test_a_month_only_source_answers_with_a_whole_month(tmp_path):
    """
    Gatekeeper's IR page dates its statements to the month it uploaded them.
    Answering "15 December" would be a precision nobody has.
    """
    guess = _estimate(tmp_path, _monthly())

    assert guess.next_date == date(2026, 12, 1)
    assert guess.window_end == date(2026, 12, 31)
    assert "v měsíci" in guess.note


def test_a_dated_source_answers_with_a_fortnight(tmp_path):
    guess = _estimate(tmp_path, _daily(), ticker="KUYAF")

    assert (guess.window_end - guess.next_date).days == 14


def test_the_note_says_it_is_not_an_announced_date(tmp_path):
    guess = _estimate(tmp_path, _monthly())

    assert "Není to oznámené datum" in guess.note
    assert "Odhad" in guess.note


# ==============================================================================
# Too little history is not a pattern
# ==============================================================================

def test_two_publications_are_a_coincidence(tmp_path):
    assert _estimate(tmp_path, _monthly()[:2]) is None


def test_a_company_with_no_recorded_history_gets_no_estimate(tmp_path):
    assert _estimate(tmp_path, []) is None


def test_an_unparseable_date_is_dropped_rather_than_guessed(tmp_path):
    """Three entries, one of them junk, is two entries — below the threshold."""
    publications = _monthly()[:3]
    publications[1] = {"label": "FY2025 Q2", "published": "někdy na jaře"}

    assert _estimate(tmp_path, publications) is None
