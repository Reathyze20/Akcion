"""
The cylinder rubric — the number that unblocks every buy, or refuses to exist.

`deserved_score = 10 − cylinders` is one half of every purchase decision and
`GomesGatekeeper` refuses outright when cylinders are unknown. They have been
unknown for every company since the app was written, so the buy branch of the
Daily Action engine was unreachable code.

What is tested here is not "the arithmetic adds up". It is the three ways a
quality score can lie:

  * speaking about a company it knows nothing about;
  * reading two incomparable periods as a trend;
  * letting somebody's opinion outweigh what the company actually filed.

The fixtures are the portfolio's own companies, because a test that passes on
invented numbers and fails on SMSI is not a test of anything.
"""

from datetime import date

import pytest

from app.services.cylinders import (
    BASE,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    LAYER_NONE,
    LAYER_SEC,
    LAYER_YAHOO,
    SOFT_CAP,
    QualityInputs,
    propose_cylinders,
)
from app.services.sec_fundamentals import Fundamentals, Point, Series

AS_OF = date(2026, 8, 23)


# ==============================================================================
# Fixture helpers — build XBRL series the way EDGAR actually returns them
# ==============================================================================

def _q(end: date, value: float, days: int = 91) -> Point:
    return Point(end=end, value=value, form="10-Q", start=date.fromordinal(end.toordinal() - days))


def _instant(end: date, value: float) -> Point:
    return Point(end=end, value=value, form="10-Q")


def _series(key: str, *, quarterly=None, instant=None) -> Series:
    return Series(
        key=key, label_cs=key, unit="USD", tag=key,
        quarterly=list(quarterly or []), instant=list(instant or []),
    )


def _fundamentals(**series) -> Fundamentals:
    return Fundamentals(ticker="TEST", cik="0000000000", series=series)


def _healthy() -> Fundamentals:
    """Growing revenue, widening margin, cash-generative, well funded."""
    return _fundamentals(
        revenue=_series("revenue", quarterly=[
            _q(date(2026, 6, 30), 12_000_000),
            _q(date(2025, 6, 30), 10_000_000),
        ]),
        gross_profit=_series("gross_profit", quarterly=[
            _q(date(2026, 6, 30), 6_000_000),      # 50 %
            _q(date(2025, 6, 30), 4_500_000),      # 45 %
        ]),
        operating_cash_flow=_series("operating_cash_flow", quarterly=[
            _q(date(2026, 6, 30), 1_500_000),
        ]),
        cash=_series("cash", instant=[_instant(date(2026, 6, 30), 20_000_000)]),
    )


# ==============================================================================
# It refuses to speak about a company it cannot see
# ==============================================================================

def test_a_company_with_no_data_gets_no_number():
    """
    The defect this whole module exists to avoid. A model asked "how healthy is
    this company" answers fluently every time, including for companies it knows
    nothing about.
    """
    result = propose_cylinders(QualityInputs(ticker="KUYA.V", as_of=AS_OF))

    assert result.cylinders is None
    assert result.deserved_score is None
    assert result.layer == LAYER_NONE
    assert any("nepodává u SEC" in u for u in result.unknowns)
    assert "neposoudím" in result.summary_cs()


def test_an_opinion_alone_is_never_a_number():
    """
    Gomes saying he likes a company is not a measurement of its operations.
    Without hard readings there is no proposal, however emphatic he was.
    """
    result = propose_cylinders(
        QualityInputs(ticker="ITMSF", as_of=AS_OF, analyst_stance="BULLISH")
    )

    assert result.cylinders is None
    assert any("tvrdých údajů" in u for u in result.unknowns)


def test_the_missing_filing_narrative_is_always_declared():
    """
    Going concern, controls not effective and restatements live only inside a
    markdown blob in `sec_filings.analysis`. They do not reach this rubric, and
    a gap that is not named is a gap that gets forgotten.
    """
    result = propose_cylinders(QualityInputs(ticker="SMSI", as_of=AS_OF))
    assert any("going concern" in u for u in result.unknowns)


# ==============================================================================
# Audited numbers move the number, in the direction they should
# ==============================================================================

def test_a_healthy_company_scores_above_the_middle():
    result = propose_cylinders(
        QualityInputs(ticker="CXDO", as_of=AS_OF, fundamentals=_healthy())
    )

    assert result.layer == LAYER_SEC
    assert result.cylinders is not None and result.cylinders > BASE
    assert result.confidence == CONFIDENCE_HIGH        # four separate readings
    assert result.deserved_score == 10.0 - result.cylinders


def test_revenue_collapse_and_a_short_runway_pull_it_down():
    """
    DAIO's shape in August 2026: revenue down about a third, burning cash, and
    a balance that does not last the year.
    """
    data = _fundamentals(
        revenue=_series("revenue", quarterly=[
            _q(date(2026, 6, 30), 6_500_000),
            _q(date(2025, 6, 30), 9_400_000),     # −30.9 %
        ]),
        operating_cash_flow=_series("operating_cash_flow", quarterly=[
            _q(date(2026, 6, 30), -1_200_000),
        ]),
        cash=_series("cash", instant=[_instant(date(2026, 6, 30), 1_500_000)]),
    )

    result = propose_cylinders(
        QualityInputs(ticker="DAIO", as_of=AS_OF, fundamentals=data)
    )

    assert result.cylinders is not None and result.cylinders < BASE
    facts = " ".join(e.fact_cs for e in result.evidence)
    assert "pokles" in facts
    assert "vydrží" in facts


def test_every_point_carries_its_date_and_its_source():
    """
    A finding you cannot date is one you cannot check, and the owner has two
    minutes to judge this number before confirming it.
    """
    result = propose_cylinders(
        QualityInputs(ticker="CXDO", as_of=AS_OF, fundamentals=_healthy())
    )

    for item in result.evidence:
        assert item.fact_cs.strip()
        assert item.source
        assert item.as_of is not None


# ==============================================================================
# The comparability trap
# ==============================================================================

def test_a_quarter_is_never_compared_with_a_nine_month_span():
    """
    TechPrecision's XBRL held a quarter, a full year and a nine-month YTD in
    adjacent rows. Read as a trend, +23 % became −71 %. With no comparable
    quarter available the honest output is a named gap, not a number.
    """
    data = _fundamentals(
        revenue=_series("revenue", quarterly=[_q(date(2026, 6, 30), 9_096_000)]),
        operating_cash_flow=_series("operating_cash_flow", quarterly=[
            _q(date(2026, 6, 30), 500_000),
        ]),
        cash=_series("cash", instant=[_instant(date(2026, 6, 30), 5_000_000)]),
    )

    result = propose_cylinders(
        QualityInputs(ticker="TPCS", as_of=AS_OF, fundamentals=data)
    )

    assert any("meziroční změnu nepočítám" in u for u in result.unknowns)
    assert all("Tržby meziročně" not in e.fact_cs for e in result.evidence)


def test_a_reverse_split_is_not_read_as_a_buyback():
    """
    SMSI's share count fell 71 % in a year — a 1-for-5 reverse split to escape
    a Nasdaq delisting. Read the wrong way it would be the most positive fact
    in the rubric about one of the weakest companies in the portfolio.
    """
    shares = _series("shares_outstanding", instant=[
        _instant(date(2026, 6, 30), 5_589_880),
        _instant(date(2026, 6, 4), 5_600_000),     # the split itself
        _instant(date(2025, 6, 30), 19_300_000),
    ])
    data = _fundamentals(
        revenue=_series("revenue", quarterly=[
            _q(date(2026, 6, 30), 4_000_000),
            _q(date(2025, 6, 30), 5_000_000),
        ]),
        cash=_series("cash", instant=[_instant(date(2026, 6, 30), 2_000_000)]),
        shares_outstanding=shares,
    )

    result = propose_cylinders(
        QualityInputs(ticker="SMSI", as_of=AS_OF, fundamentals=data)
    )

    split_note = [e for e in result.evidence if "split" in e.fact_cs]
    assert split_note, "the split has to be named, not silently skipped"
    assert split_note[0].delta == 0


def test_real_dilution_still_counts_against_the_company():
    shares = _series("shares_outstanding", instant=[
        _instant(date(2026, 6, 30), 14_000_000),   # +40 %
        _instant(date(2025, 6, 30), 10_000_000),
    ])
    data = _fundamentals(
        revenue=_series("revenue", quarterly=[
            _q(date(2026, 6, 30), 5_000_000),
            _q(date(2025, 6, 30), 5_000_000),
        ]),
        cash=_series("cash", instant=[_instant(date(2026, 6, 30), 3_000_000)]),
        shares_outstanding=shares,
    )

    result = propose_cylinders(
        QualityInputs(ticker="DAIO", as_of=AS_OF, fundamentals=data)
    )

    dilution = [e for e in result.evidence if "Počet akcií" in e.fact_cs]
    assert dilution and dilution[0].delta == -1


# ==============================================================================
# The weaker layer, and its limits
# ==============================================================================

def test_yahoo_covers_the_companies_edgar_cannot_see():
    """
    Four of the five largest positions file nowhere EDGAR can reach. Yahoo's
    aggregates are the difference between "we know nothing" and "we know it
    earns money and holds more cash than debt".
    """
    result = propose_cylinders(QualityInputs(
        ticker="KUYA.V", as_of=AS_OF,
        yahoo={"profit_margin": 0.12, "total_cash": 8_000_000, "total_debt": 1_000_000},
    ))

    assert result.layer == LAYER_YAHOO
    assert result.cylinders is not None
    assert any("SEC na tuhle firmu nedosáhne" in u for u in result.unknowns)


def test_the_yahoo_layer_never_reaches_the_ends_of_the_scale():
    """
    Nobody audited these numbers and they cannot express a trend. Ten cylinders
    means "firing on all of them", and a trailing aggregate cannot show that.
    """
    result = propose_cylinders(QualityInputs(
        ticker="GSI.V", as_of=AS_OF,
        yahoo={"profit_margin": 0.40, "total_cash": 50_000_000, "total_debt": 0},
        insider_data_available=True, insider_buys=3,
        analyst_stance="BULLISH",
    ))

    assert result.cylinders <= 7
    assert result.confidence == CONFIDENCE_MEDIUM     # never HIGH on this layer


# ==============================================================================
# The filings outrank the commentary
# ==============================================================================

def test_an_enthusiastic_analyst_cannot_outweigh_the_numbers():
    """
    The canon is a fundamental method: value is in the company, not in who is
    excited about it. A bullish read is worth a point and never more.
    """
    weak = _fundamentals(
        revenue=_series("revenue", quarterly=[
            _q(date(2026, 6, 30), 5_000_000),
            _q(date(2025, 6, 30), 10_000_000),     # −50 %
        ]),
        operating_cash_flow=_series("operating_cash_flow", quarterly=[
            _q(date(2026, 6, 30), -2_000_000),
        ]),
        cash=_series("cash", instant=[_instant(date(2026, 6, 30), 1_000_000)]),
    )

    quiet = propose_cylinders(
        QualityInputs(ticker="ECOR", as_of=AS_OF, fundamentals=weak)
    )
    loud = propose_cylinders(
        QualityInputs(
            ticker="ECOR", as_of=AS_OF, fundamentals=weak, analyst_stance="BULLISH"
        )
    )

    assert loud.cylinders - quiet.cylinders <= SOFT_CAP
    assert loud.cylinders < BASE      # still a weak company, whoever likes it


def test_only_open_market_insider_trades_count():
    """
    The first Form 4 this app ever read was a gift of 8,000 TPCS shares at
    $0.00, flagged as a disposal. `signal` is already restricted to codes P and
    S; what is asserted here is that an absence of data is said out loud rather
    than read as "no insider activity".
    """
    silent = propose_cylinders(
        QualityInputs(ticker="CXDO", as_of=AS_OF, fundamentals=_healthy())
    )
    assert any("insider obchody" in u for u in silent.unknowns)

    known = propose_cylinders(QualityInputs(
        ticker="CXDO", as_of=AS_OF, fundamentals=_healthy(),
        insider_data_available=True,
    ))
    assert all("insider obchody" not in u for u in known.unknowns)
    assert any("neobchodovali" in e.fact_cs for e in known.evidence)


def test_insider_buying_and_selling_move_opposite_ways():
    buying = propose_cylinders(QualityInputs(
        ticker="CXDO", as_of=AS_OF, fundamentals=_healthy(),
        insider_data_available=True, insider_buys=2,
    ))
    selling = propose_cylinders(QualityInputs(
        ticker="CXDO", as_of=AS_OF, fundamentals=_healthy(),
        insider_data_available=True, insider_sells=2,
    ))

    assert buying.cylinders > selling.cylinders


# ==============================================================================
# The scale holds
# ==============================================================================

@pytest.mark.parametrize("stance", [None, "BULLISH", "BEARISH", "NEUTRAL", "nonsense"])
def test_the_result_always_sits_on_the_canon_scale(stance):
    result = propose_cylinders(QualityInputs(
        ticker="CXDO", as_of=AS_OF, fundamentals=_healthy(),
        insider_data_available=True, insider_buys=5, analyst_stance=stance,
    ))
    assert 0 <= result.cylinders <= 10
    assert 0.0 <= result.deserved_score <= 10.0


def test_a_company_burning_multiples_of_its_revenue_is_not_merely_unprofitable():
    """
    KUYA's trailing net margin is −124 %: it spends several times what it earns.
    On the Yahoo layer there is no cash-flow statement and no trend, so the
    magnitude of the loss is the only severity signal available — and scoring it
    the same as −1 % would be the rubric refusing to see a difference the owner
    would spot instantly.
    """
    mild = propose_cylinders(QualityInputs(
        ticker="X", as_of=AS_OF,
        yahoo={"profit_margin": -0.01, "total_cash": 5_000_000, "total_debt": 1_000_000},
    ))
    severe = propose_cylinders(QualityInputs(
        ticker="KUYA.V", as_of=AS_OF,
        yahoo={"profit_margin": -1.243, "total_cash": 5_000_000, "total_debt": 1_000_000},
    ))

    assert severe.cylinders < mild.cylinders


# ==============================================================================
# Writing a confirmation back
# ==============================================================================

def test_the_confirmation_translates_confidence_for_the_column():
    """
    `stock_lifecycle.confidence` is constrained to HIGH / MEDIUM / LOW and is
    shared with the keyword lifecycle classifier. The rubric's labels are Czech
    because the owner reads them.

    Postgres refused the untranslated value outright when the first twelve
    confirmations were written — the schema doing its job. Asserted here so the
    two vocabularies cannot drift apart again.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401
    import app.models.trading  # noqa: F401
    from app.models.base import Base
    from app.models.gomes import StockLifecycleModel
    from app.services.cylinder_intake import confirm

    @compiles(JSONB, "sqlite")
    def _jsonb(type_, compiler, **kw):  # noqa: ARG001
        return "JSON"

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[StockLifecycleModel.__table__])
    db = sessionmaker(bind=engine)()

    proposal = propose_cylinders(
        QualityInputs(ticker="CXDO", as_of=AS_OF, fundamentals=_healthy())
    )
    assert proposal.confidence == CONFIDENCE_HIGH        # Czech, for the screen

    confirm(db, "CXDO", proposal.cylinders, confirmed_by="test", proposal=proposal)
    db.flush()

    row = db.query(StockLifecycleModel).one()
    assert row.confidence == "HIGH"                      # English, for the column
    assert row.cylinders_confirmed_at is not None
    assert row.cylinders_valid_until is not None
    # The evidence travels with the number: without it a confirmation is a
    # digit nobody — including the owner in three months — can judge.
    assert row.phase_signals["evidence"]
    db.close()


# ==============================================================================
# What the filings said about themselves
# ==============================================================================

class TestFilingFindings:
    """
    `analyze_outlook` has always extracted going concern, controls not
    effective and restatements with a severity and a verbatim quote — and
    always rendered them into a markdown blob nothing could query. SMSI and
    ECOR both carry going-concern warnings and both were assessed without
    either one.
    """

    def _inputs(self, **kw):
        base = dict(ticker="SMSI", as_of=AS_OF, fundamentals=_healthy())
        base.update(kw)
        return QualityInputs(**base)

    def test_a_going_concern_costs_two_cylinders(self):
        """
        Nothing else in this rubric moves the number that far, and nothing else
        should: it is the company's own auditors saying the rest of the
        arithmetic may be beside the point.
        """
        clean = propose_cylinders(self._inputs(filings_read=True))
        flagged = propose_cylinders(self._inputs(
            filings_read=True,
            filing_findings=(("CRITICAL", "Podání uvádí pochybnost o trvání firmy"),),
        ))
        assert clean.cylinders - flagged.cylinders == 2

    def test_a_high_finding_costs_one(self):
        clean = propose_cylinders(self._inputs(filings_read=True))
        flagged = propose_cylinders(self._inputs(
            filings_read=True,
            filing_findings=(("HIGH", "Kontroly prohlášeny za neúčinné"),),
        ))
        assert clean.cylinders - flagged.cylinders == 1

    def test_a_medium_finding_is_shown_and_does_not_move_the_number(self):
        """Worth reading, not worth re-scoring the company for."""
        result = propose_cylinders(self._inputs(
            filings_read=True,
            filing_findings=(("MEDIUM", "Nový rizikový faktor o dodavateli"),),
        ))
        finding = [e for e in result.evidence if "dodavateli" in e.fact_cs]
        assert finding and finding[0].delta == 0

    def test_six_warnings_do_not_drive_it_to_zero(self):
        """
        A rubric that can reach the floor on findings alone stops
        distinguishing between bad and catastrophic.
        """
        clean = propose_cylinders(self._inputs(filings_read=True))
        many = propose_cylinders(self._inputs(
            filings_read=True,
            filing_findings=tuple(("CRITICAL", f"nález {i}") for i in range(6)),
        ))
        assert clean.cylinders - many.cylinders == 3

    def test_a_clean_filing_is_recorded_as_read(self):
        """
        "Nothing material was found" is a real finding about a quarter, and
        worth saying out loud beside the ones that were.
        """
        result = propose_cylinders(self._inputs(filings_read=True))
        assert any("žádný materiální nález" in e.fact_cs for e in result.evidence)

    def test_an_unread_filing_is_a_named_gap_not_a_clean_bill(self):
        """
        The trap this nearly walked into. Eight filings were analysed before
        findings were stored structurally, and treating those as read would
        have reported SMSI — whose going concern sits in that very markdown —
        as carrying no material warning at all.
        """
        result = propose_cylinders(self._inputs(filings_read=False))

        assert any("nálezy z textu podání" in u for u in result.unknowns)
        assert not any("žádný materiální nález" in e.fact_cs for e in result.evidence)
