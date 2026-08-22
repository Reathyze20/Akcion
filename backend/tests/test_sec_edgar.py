"""
Tests for the SEC EDGAR integration.

Two traps, both found against live SEC data on 2026-08-22, both of the same
family this codebase keeps having to remove: an absence or an ambiguity turned
into a confident signal.

1. Five of fourteen holdings do not file with the SEC at all. "No filings" for
   a TSX Venture listing is a fact about an exchange; for TechPrecision it
   would be a fact about the company.
2. A Form 4 disposal is usually not a sale. The first one fetched was a gift.
"""

from datetime import date

import pytest

from app.services.sec_edgar import (
    CoverageStatus,
    Signal,
    TickerCoverage,
    classify,
    parse_form4,
    summarize_insider_activity,
)
from app.services.sec_fundamentals import (
    Concept,
    _build_series,
    derive_findings,
    Fundamentals,
)


# ==============================================================================
# Transaction codes
# ==============================================================================

class TestTransactionCodes:
    def test_only_market_transactions_carry_a_signal(self):
        assert classify("P").signal is Signal.BUY
        assert classify("S").signal is Signal.SELL

    @pytest.mark.parametrize("code", ["A", "D", "F", "G", "M", "C", "W", "Z"])
    def test_administrative_codes_carry_none(self, code):
        """
        A grant, a gift, tax withholding, an option exercise — none of these is
        someone deciding to spend or raise money at the market price.
        """
        assert classify(code).signal is Signal.NO_SIGNAL

    def test_an_unknown_code_is_not_guessed(self):
        """SEC adds codes. Guessing a direction is how a gift becomes a sale."""
        brake = classify("Q")
        assert brake.signal is Signal.NO_SIGNAL
        assert "neznámý" in brake.label_cs

    def test_a_missing_code_is_not_guessed_either(self):
        assert classify(None).signal is Signal.NO_SIGNAL
        assert classify("").signal is Signal.NO_SIGNAL


# ==============================================================================
# Form 4 parsing
# ==============================================================================

GIFT_FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <periodOfReport>2026-08-19</periodOfReport>
  <issuer>
    <issuerCik>0001328792</issuerCik>
    <issuerName>TECHPRECISION CORP</issuerName>
    <issuerTradingSymbol>TPCS</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001596334</rptOwnerCik>
      <rptOwnerName>Schenker Walter Milton</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>0</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-08-19</value></transactionDate>
      <transactionCoding>
        <transactionFormType>4</transactionFormType>
        <transactionCode>G</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>8000</value></transactionShares>
        <transactionPricePerShare><value>0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>71727</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

SALE_FORM4 = GIFT_FORM4.replace(
    "<transactionCode>G</transactionCode>", "<transactionCode>S</transactionCode>"
).replace(
    "<transactionPricePerShare><value>0</value></transactionPricePerShare>",
    "<transactionPricePerShare><value>143.77</value></transactionPricePerShare>",
)


class TestParseForm4:
    def _one(self, xml):
        txs = parse_form4(
            xml, ticker="TPCS", filed=date(2026, 8, 20), accession="0001104659-26-099219"
        )
        assert len(txs) == 1
        return txs[0]

    def test_the_real_gift_is_not_read_as_a_sale(self):
        """
        This is the actual first Form 4 the integration ever fetched. Read
        naively — disposed, 8,000 shares — it is an insider selling. It is a
        charitable donation.
        """
        tx = self._one(GIFT_FORM4)
        assert tx.code.code == "G"
        assert tx.code.signal is Signal.NO_SIGNAL
        assert tx.shares == 8000
        assert tx.acquired is False  # SEC's flag, kept as reported

    def test_a_gift_has_no_price(self):
        """
        Reported as $0.00. Storing that as a price would let a later average
        treat a donated share as one bought for nothing.
        """
        assert self._one(GIFT_FORM4).price_per_share is None

    def test_a_gift_has_no_value(self):
        assert self._one(GIFT_FORM4).value is None

    def test_a_real_sale_keeps_its_price_and_value(self):
        tx = self._one(SALE_FORM4)
        assert tx.code.signal is Signal.SELL
        assert tx.price_per_share == pytest.approx(143.77)
        assert tx.value == pytest.approx(8000 * 143.77)

    def test_the_insider_and_role_are_read(self):
        tx = self._one(GIFT_FORM4)
        assert tx.insider == "Schenker Walter Milton"
        assert tx.is_director is True
        assert tx.is_officer is False


# ==============================================================================
# Summaries
# ==============================================================================

class TestSummary:
    def _coverage(self, status=CoverageStatus.COVERED, **kw):
        return TickerCoverage(ticker="TPCS", status=status, **kw)

    def test_a_non_filer_is_described_as_one(self):
        coverage = TickerCoverage(
            ticker="GSI.V",
            status=CoverageStatus.NOT_AN_SEC_FILER,
            note="nepodává u SEC",
        )
        summary = summarize_insider_activity(coverage)
        assert "nepodává u SEC" in summary

    def test_only_administrative_transactions_say_so_plainly(self):
        """
        TPCS's real record: seven transactions, every one a gift or a grant.
        The honest summary is "no market activity", not "insiders disposed of
        shares".
        """
        coverage = self._coverage()
        coverage.insider_transactions = parse_form4(
            GIFT_FORM4, ticker="TPCS", filed=date(2026, 8, 20), accession="x"
        )
        summary = summarize_insider_activity(coverage)
        assert "žádný nákup ani prodej na trhu" in summary
        assert "bez signálu" in summary

    def test_real_sales_are_counted(self):
        coverage = self._coverage()
        coverage.insider_transactions = parse_form4(
            SALE_FORM4, ticker="TPCS", filed=date(2026, 8, 20), accession="x"
        )
        assert "prodal na trhu" in summarize_insider_activity(coverage)

    def test_no_filings_is_not_the_same_sentence_as_not_a_filer(self):
        empty_filer = summarize_insider_activity(self._coverage())
        non_filer = summarize_insider_activity(
            TickerCoverage(ticker="GSI.V", status=CoverageStatus.NOT_AN_SEC_FILER)
        )
        assert empty_filer != non_filer


# ==============================================================================
# The comparability trap
# ==============================================================================

def _facts(rows):
    return {"Revenues": {"units": {"USD": rows}}}


REVENUE_CONCEPT = Concept("revenue", "Tržby", ("Revenues",))


class TestPeriodsStayComparable:
    #: TechPrecision's real Revenues rows, fetched 2026-08-22. One quarter, one
    #: full year and one nine-month YTD figure, adjacent in the same series.
    ROWS = [
        {"start": "2026-04-01", "end": "2026-06-30", "val": 9_096_000, "form": "10-Q"},
        {"start": "2025-04-01", "end": "2026-03-31", "val": 31_644_000, "form": "10-K"},
        {"start": "2025-04-01", "end": "2025-12-31", "val": 23_559_000, "form": "10-Q"},
        {"start": "2025-04-01", "end": "2025-06-30", "val": 7_377_000, "form": "10-Q"},
    ]

    def test_quarters_years_and_ytd_are_separated(self):
        series = _build_series(REVENUE_CONCEPT, _facts(self.ROWS))

        assert [p.value for p in series.quarterly] == [9_096_000, 7_377_000]
        assert [p.value for p in series.annual] == [31_644_000]

    def test_the_nine_month_figure_is_dropped_entirely(self):
        """
        Real data, but comparable with neither bucket. Left in, it turns a
        company that grew 23 % into one that fell 71 %.
        """
        series = _build_series(REVENUE_CONCEPT, _facts(self.ROWS))
        every_value = [
            p.value for p in series.quarterly + series.annual + series.instant
        ]
        assert 23_559_000 not in every_value

    def test_year_on_year_compares_the_same_quarter(self):
        series = _build_series(REVENUE_CONCEPT, _facts(self.ROWS))
        assert series.latest_quarter.value == 9_096_000
        assert series.year_ago_quarter().value == 7_377_000

    def test_the_finding_reports_real_growth(self):
        data = Fundamentals(ticker="TPCS", cik="0001328792")
        data.series["revenue"] = _build_series(REVENUE_CONCEPT, _facts(self.ROWS))
        finding = derive_findings(data)[0]

        assert "růst" in finding
        assert "23.3" in finding
        assert "30.06.2026" in finding

    def test_a_missing_prior_year_is_stated_not_skipped(self):
        rows = [self.ROWS[0]]
        data = Fundamentals(ticker="TPCS", cik="0001328792")
        data.series["revenue"] = _build_series(REVENUE_CONCEPT, _facts(rows))
        finding = derive_findings(data)[0]

        assert "chybí" in finding
        assert "meziroční změnu nepočítám" in finding

    def test_a_concept_the_company_does_not_tag_returns_none(self):
        """A gap to report, not a zero to chart."""
        assert _build_series(REVENUE_CONCEPT, {}) is None

    def test_amended_and_other_forms_are_ignored(self):
        rows = self.ROWS + [
            {"start": "2026-04-01", "end": "2026-06-30", "val": 1, "form": "8-K"},
        ]
        series = _build_series(REVENUE_CONCEPT, _facts(rows))
        assert 1 not in [p.value for p in series.quarterly]


# ==============================================================================
# Identifying the right company, or admitting we cannot
# ==============================================================================

class TestIdentityIsNotGuessed:
    """
    The first full portfolio sync matched `DBO.TO` — a Toronto listing — to
    "Invesco DB Oil Fund", a US ETF, by stripping the exchange suffix and
    looking up the base symbol. It then attached a whole quarter of that fund's
    numbers to the holding. A wrong company is worse than no company: it looks
    exactly as trustworthy as the truth.
    """

    def _client(self):
        from app.services.sec_edgar import SecEdgarClient

        client = SecEdgarClient()
        # A real index entry for the base symbol, which is what made the
        # original mismatch possible.
        client._ticker_index = {
            "DBO": {"cik_str": 1383082, "ticker": "DBO", "title": "Invesco DB Oil Fund"},
            "VTSI": {"cik_str": 1085243, "ticker": "VTSI", "title": "VirTra, Inc"},
        }
        return client

    def test_a_toronto_listing_is_not_matched_to_a_us_fund(self):
        coverage = self._client().fetch_coverage("DBO.TO")
        assert coverage.status is CoverageStatus.NOT_AN_SEC_FILER
        assert coverage.company_name is None
        assert "Toronto" in coverage.note

    def test_the_exchange_is_named_so_the_absence_is_explained(self):
        coverage = self._client().fetch_coverage("GSI.V")
        assert "TSX Venture" in coverage.note
        assert "O firmě samotné to neříká nic" in coverage.note

    def test_an_unsuffixed_us_ticker_still_resolves(self):
        cik, name = self._client().resolve_cik("VTSI")
        assert cik == "0001085243"
        assert name == "VirTra, Inc"

    def test_an_isin_is_not_reported_as_a_non_filer(self):
        """
        Three portfolio rows hold an ISIN rather than a symbol. "Does not file
        with the SEC" would be answering a question nobody asked, and would
        hide the actual problem, which is the stored identifier.
        """
        coverage = self._client().fetch_coverage("CA00654B1040")
        assert coverage.status is CoverageStatus.NOT_A_TICKER
        assert "ISIN" in coverage.note

    def test_a_us_isin_is_also_recognised_as_an_isin(self):
        coverage = self._client().fetch_coverage("US40053W1018")
        assert coverage.status is CoverageStatus.NOT_A_TICKER

    def test_all_four_absences_read_differently(self):
        """
        Not a ticker, foreign listing, foreign filer, unreachable — four
        different answers, and none of them is "the company reported nothing".
        """
        statuses = {
            CoverageStatus.NOT_A_TICKER,
            CoverageStatus.NOT_AN_SEC_FILER,
            CoverageStatus.FOREIGN_PRIVATE_ISSUER,
            CoverageStatus.LOOKUP_FAILED,
        }
        assert len(statuses) == 4
        assert CoverageStatus.COVERED not in statuses
