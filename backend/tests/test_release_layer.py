"""
The layer between an audited filing and a trailing aggregate.

Four holdings — 54 % of the portfolio — file in Canada, so the rubric had only
Yahoo's trailing year for them and could see no trend at all. Their own
quarterly releases do carry the year-on-year comparison. What has to hold is
that this new source is believed exactly as far as it deserves: a number nobody
can trace to a sentence never arrives, an amount in an unnamed currency is
never arithmetic, and a company that does not publish its cash flow cannot be
called excellent.
"""

import json

from app.services import release_fundamentals
from app.services.cylinders import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    LAYER_RELEASE,
    LAYER_SEC,
    LAYER_YAHOO,
    RELEASE_CEILING,
    RELEASE_FLOOR,
    QualityInputs,
    propose_cylinders,
)
from datetime import date

from app.services.sec_fundamentals import Fundamentals, Point, Series


def _file(tmp_path, releases):
    path = tmp_path / "company_releases.json"
    path.write_text(json.dumps({"releases": releases}), encoding="utf-8")
    release_fundamentals._load.cache_clear()
    return path


def _release(**over):
    base = {
        "ticker": "GKPRF",
        "company": "Gatekeeper Systems",
        "fiscal_label": "FQ3 2026",
        "period_end": "2026-05-31",
        "published": "2026-07-21",
        "currency": "CAD",
        "source_url": "https://example.com/fq3",
        "readings": {
            "revenue_yoy_pct": {
                "value": 68.0,
                "basis_months": 3,
                "quote": "68% Growth",
            },
            "gross_margin_pct": {
                "value": 53.0,
                "prior": 49.0,
                "basis_months": 3,
                "quote": "53% compared to 49% in the prior year",
            },
            "bottom_line": {
                "value": "PROFIT",
                "basis_months": 3,
                "quote": "$2.4M Adjusted EBITDA",
            },
        },
        "absent": ["provozní cash flow", "počet akcií"],
    }
    base.update(over)
    return base


def _audited():
    """A filing that tags what the rubric reads: growing revenue, wider margin."""
    def _q(end, value):
        return Point(end=end, value=value, form="10-Q",
                     start=date.fromordinal(end.toordinal() - 91))

    def _series(key, quarterly):
        return Series(key=key, label_cs=key, unit="USD", tag=key,
                      quarterly=list(quarterly), instant=[])

    return Fundamentals(
        ticker="GKPRF",
        cik="0000000000",
        series={
            "revenue": _series("revenue", [
                _q(date(2026, 6, 30), 12_000_000),
                _q(date(2025, 6, 30), 10_000_000),
            ]),
            "gross_profit": _series("gross_profit", [
                _q(date(2026, 6, 30), 6_000_000),
                _q(date(2025, 6, 30), 4_500_000),
            ]),
        },
    )


def _inputs(release, **over):
    return QualityInputs(
        ticker="GKPRF", as_of=date(2026, 8, 25), release=release, **over
    )


# ==============================================================================
# Provenance is enforced, not intended
# ==============================================================================

def test_a_number_without_a_quote_never_arrives(tmp_path):
    """
    `price_lines_data.py` was deleted for being numbers in a file with nothing
    behind them. The difference has to be checked, not promised.
    """
    path = _file(
        tmp_path,
        [
            _release(
                readings={
                    "revenue_yoy_pct": {"value": 68.0, "basis_months": 3},
                    "bottom_line": {
                        "value": "PROFIT",
                        "basis_months": 3,
                        "quote": "profit",
                    },
                }
            )
        ],
    )
    release = release_fundamentals.load_all(path=path)["GKPRF"]

    assert "revenue_yoy_pct" not in release.readings
    assert "bottom_line" in release.readings


def test_a_record_without_a_source_url_does_not_exist(tmp_path):
    path = _file(tmp_path, [_release(source_url="")])
    assert release_fundamentals.load_all(path=path) == {}


def test_a_reading_without_a_period_length_is_dropped(tmp_path):
    """A quarter compared against a nine-month span turns growth into collapse."""
    path = _file(
        tmp_path,
        [_release(readings={"revenue_yoy_pct": {"value": 68.0, "quote": "68%"}})],
    )
    assert release_fundamentals.load_all(path=path)["GKPRF"].readings == {}


def test_the_newest_release_wins_whatever_order_it_is_written_in(tmp_path):
    path = _file(
        tmp_path,
        [
            _release(fiscal_label="FQ3 2026", period_end="2026-05-31"),
            _release(fiscal_label="FQ1 2026", period_end="2025-11-30"),
        ],
    )
    assert release_fundamentals.load_all(path=path)["GKPRF"].fiscal_label == "FQ3 2026"


def test_a_holding_is_found_under_the_symbol_it_is_held_as(tmp_path):
    """The file is keyed GKPRF; the position is held as GSI.V."""
    path = _file(tmp_path, [_release()])
    assert release_fundamentals.for_ticker("GSI.V", path=path).ticker == "GKPRF"


# ==============================================================================
# What the release is allowed to conclude
# ==============================================================================

def test_a_release_produces_a_number_where_yahoo_produced_no_trend(tmp_path):
    path = _file(tmp_path, [_release()])
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    assert proposal.layer == LAYER_RELEASE
    assert proposal.cylinders is not None
    assert proposal.confidence == CONFIDENCE_MEDIUM


def test_the_release_layer_is_never_high_confidence(tmp_path):
    """
    It is the company's own selection of its own numbers and it omits the cash
    flow statement. Four readings on the SEC layer would earn HIGH; here they
    must not.
    """
    path = _file(tmp_path, [_release()])
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    assert proposal.confidence != CONFIDENCE_HIGH


def test_a_release_cannot_call_a_company_excellent(tmp_path):
    """
    No operating cash flow and no share count in any release read so far —
    which are the two facts that kill a microcap. A source blind to burn and
    dilution does not get to say ten.
    """
    path = _file(
        tmp_path,
        [
            _release(
                readings={
                    "revenue_yoy_pct": {
                        "value": 400.0,
                        "basis_months": 3,
                        "quote": "quintupled",
                    },
                    "gross_margin_pct": {
                        "value": 80.0,
                        "prior": 40.0,
                        "basis_months": 3,
                        "quote": "80% from 40%",
                    },
                    "bottom_line": {
                        "value": "PROFIT",
                        "basis_months": 3,
                        "quote": "profit",
                    },
                }
            )
        ],
    )
    proposal = propose_cylinders(
        _inputs(release_fundamentals.for_ticker("GKPRF", path=path), analyst_stance="BULLISH")
    )

    assert proposal.cylinders == RELEASE_CEILING
    assert proposal.cylinders < 10


def test_a_release_may_still_report_a_collapse(tmp_path):
    """
    The floor sits below Yahoo's on purpose: a source believed about good news
    has to be allowed to deliver bad. A trailing aggregate smears a collapsed
    quarter; the company's own comparison does not.
    """
    path = _file(
        tmp_path,
        [
            _release(
                readings={
                    "revenue_yoy_pct": {
                        "value": -60.0,
                        "basis_months": 3,
                        "quote": "revenue fell 60%",
                    },
                    "gross_margin_pct": {
                        "value": 12.0,
                        "prior": 40.0,
                        "basis_months": 3,
                        "quote": "12% from 40%",
                    },
                    "bottom_line": {
                        "value": "LOSS",
                        "basis_months": 3,
                        "quote": "net loss",
                    },
                }
            )
        ],
    )
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    assert proposal.cylinders == RELEASE_FLOOR
    assert RELEASE_FLOOR < 3  # below the Yahoo floor, which cannot say this


# ==============================================================================
# What the release is not allowed to hide
# ==============================================================================

def test_what_the_company_did_not_publish_is_named(tmp_path):
    """
    A missing operating cash flow has to appear as a missing operating cash
    flow. Otherwise the runway is simply absent from the screen and reads as a
    company with no survival question.
    """
    path = _file(tmp_path, [_release()])
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    joined = " | ".join(proposal.unknowns)
    assert "provozní cash flow" in joined
    assert "počet akcií" in joined
    assert proposal.runway_months is None


def test_an_unnamed_currency_is_stated_and_the_number_still_stands(tmp_path):
    """
    Three of the four releases write `$` without saying which dollar. Every
    scored reading is a ratio or a sign, so the count survives — but the gap
    has to be on the screen, because the same trap produced a wrong TRIM on
    GSI.V.
    """
    path = _file(tmp_path, [_release(currency=None)])
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    assert proposal.cylinders is not None
    assert any("měna" in u for u in proposal.unknowns)


def test_the_source_url_travels_with_the_verdict(tmp_path):
    path = _file(tmp_path, [_release()])
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    assert any("https://example.com/fq3" in u for u in proposal.unknowns)


def test_a_missing_year_on_year_is_a_stated_gap_not_a_computed_one(tmp_path):
    """
    Intermap published a quarter's revenue and no comparison. Deriving one from
    two absolute numbers means choosing the base, which means choosing the
    answer.
    """
    path = _file(
        tmp_path,
        [
            _release(
                readings={
                    "bottom_line": {
                        "value": "LOSS",
                        "basis_months": 3,
                        "quote": "net loss",
                    }
                }
            )
        ],
    )
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    assert any("meziroční změna tržeb" in u for u in proposal.unknowns)


# ==============================================================================
# Where the layer sits
# ==============================================================================

def test_an_audited_filing_still_wins(tmp_path):
    """A filing that actually says something outranks the company's own release."""
    path = _file(tmp_path, [_release()])
    proposal = propose_cylinders(
        _inputs(
            release_fundamentals.for_ticker("GKPRF", path=path),
            fundamentals=_audited(),
        )
    )
    assert proposal.layer == LAYER_SEC


def test_a_release_beats_a_trailing_aggregate(tmp_path):
    path = _file(tmp_path, [_release()])
    proposal = propose_cylinders(
        _inputs(
            release_fundamentals.for_ticker("GKPRF", path=path),
            yahoo={"profit_margin": -0.9, "total_cash": 1, "total_debt": 9},
        )
    )
    assert proposal.layer == LAYER_RELEASE


def test_a_release_with_nothing_scoreable_does_not_claim_the_layer(tmp_path):
    """
    Intermap's release carries no year-on-year figure, no margin and no clean
    result. An empty release must fall through to Yahoo rather than assert a
    better layer it cannot fill.
    """
    path = _file(tmp_path, [_release(readings={}, ticker="ITMSF")])
    proposal = propose_cylinders(
        QualityInputs(
            ticker="ITMSF",
            as_of=date(2026, 8, 25),
            release=release_fundamentals.for_ticker("ITMSF", path=path),
            yahoo={"profit_margin": -0.2, "total_cash": 9, "total_debt": 1},
        )
    )
    assert proposal.layer == LAYER_YAHOO


# ==============================================================================
# A field list written out by hand
# ==============================================================================

def test_supplying_xbrl_does_not_drop_the_going_concern_warning(monkeypatch):
    """
    `cylinder_intake.propose` rebuilt `QualityInputs` field by field when the
    caller had XBRL, and the list had stopped carrying `filing_findings` /
    `filings_read`. So every SEC filer — the only companies a caller has XBRL
    for — arrived at the rubric with its going-concern warnings erased, and
    `_from_findings` then reported them as never read. SMSI and ECOR, the two
    names that rule was written for, were both affected.
    """
    from app.services import cylinder_intake

    class _Fundamentals:
        def get(self, _key):
            return None

    monkeypatch.setattr(
        cylinder_intake,
        "gather",
        lambda db, ticker, as_of=None: QualityInputs(
            ticker="SMSI",
            as_of=date(2026, 8, 25),
            filings_read=True,
            filing_findings=(("CRITICAL", "Going concern: podstatná nejistota"),),
        ),
    )

    proposal = cylinder_intake.propose(None, "SMSI", fundamentals=_Fundamentals())

    facts = " | ".join(e.fact_cs for e in proposal.evidence)
    assert "Going concern" in facts
    assert not any("nemám je ve strukturované podobě" in u for u in proposal.unknowns)


def test_an_empty_filing_does_not_block_the_release(tmp_path):
    """
    Intermap files with EDGAR and tags none of the concepts this rubric reads,
    so the SEC layer used to claim the slot with nothing in it while the
    company's own release sat unread one line below. The better source must not
    block the usable one.
    """
    class _Empty:
        def get(self, _key):
            return None

    path = _file(tmp_path, [_release()])
    proposal = propose_cylinders(
        _inputs(release_fundamentals.for_ticker("GKPRF", path=path), fundamentals=_Empty())
    )

    assert proposal.layer == LAYER_RELEASE
    assert proposal.cylinders is not None


# ==============================================================================
# Readings only some companies publish
# ==============================================================================

def test_operating_margin_stands_in_when_there_is_no_gross_margin(tmp_path):
    """
    RADCOM publishes only the operating line; the Canadians publish only the
    gross one. One margin reading either way — adding both would count the same
    company's margin move twice.
    """
    path = _file(
        tmp_path,
        [
            _release(
                readings={
                    "revenue_yoy_pct": {
                        "value": -33.4,
                        "basis_months": 3,
                        "quote": "down 33.4%",
                    },
                    "operating_margin_pct": {
                        "value": -31.9,
                        "prior": 9.9,
                        "basis_months": 3,
                        "quote": "(31.9)% of revenue, compared to 9.9%",
                    },
                }
            )
        ],
    )
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    facts = [e.fact_cs for e in proposal.evidence]
    assert any("Provozní marže" in f for f in facts)
    assert not any("Hrubá marže" in f for f in facts)


def test_gross_margin_wins_when_both_are_published(tmp_path):
    path = _file(
        tmp_path,
        [
            _release(
                readings={
                    "gross_margin_pct": {
                        "value": 53.0,
                        "prior": 49.0,
                        "basis_months": 3,
                        "quote": "53% from 49%",
                    },
                    "operating_margin_pct": {
                        "value": 10.0,
                        "prior": 2.0,
                        "basis_months": 3,
                        "quote": "10% from 2%",
                    },
                    "bottom_line": {
                        "value": "PROFIT",
                        "basis_months": 3,
                        "quote": "profit",
                    },
                }
            )
        ],
    )
    proposal = propose_cylinders(_inputs(release_fundamentals.for_ticker("GKPRF", path=path)))

    margins = [e for e in proposal.evidence if "marže" in e.fact_cs]
    assert len(margins) == 1
    assert "Hrubá marže" in margins[0].fact_cs


def test_a_fortress_balance_sheet_offsets_a_bad_quarter(tmp_path):
    """
    A collapsed quarter at a company holding no debt and a hundred million in
    cash is a different fact from the same quarter at one financed by a lender.
    The reading is a comparison, so it survives an unnamed currency.
    """
    def build(balance):
        readings = {
            "revenue_yoy_pct": {
                "value": -33.4,
                "basis_months": 3,
                "quote": "down 33.4%",
            },
            "bottom_line": {"value": "LOSS", "basis_months": 3, "quote": "net loss"},
        }
        if balance:
            readings["balance"] = {
                "value": balance,
                "basis_months": 3,
                "quote": "cash of $109.7 million and no debt",
            }
        return _file(tmp_path, [_release(currency=None, readings=readings)])

    without = propose_cylinders(
        _inputs(release_fundamentals.for_ticker("GKPRF", path=build(None)))
    )
    with_cash = propose_cylinders(
        _inputs(release_fundamentals.for_ticker("GKPRF", path=build("CASH_EXCEEDS_DEBT")))
    )

    assert with_cash.cylinders > without.cylinders
    assert any("Rozvaha" in e.fact_cs for e in with_cash.evidence)


def test_an_unknown_word_value_is_refused_rather_than_scored(tmp_path):
    path = _file(
        tmp_path,
        [
            _release(
                readings={
                    "balance": {
                        "value": "PROBABLY_FINE",
                        "basis_months": 3,
                        "quote": "looks alright",
                    }
                }
            )
        ],
    )
    assert release_fundamentals.load_all(path=path)["GKPRF"].readings == {}
