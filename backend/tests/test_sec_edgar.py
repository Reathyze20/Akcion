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


# ==============================================================================
# The outlook answer cannot be half-parsed
# ==============================================================================

class TestOutlookIsConstrained:
    def test_the_outlook_shape_is_a_model_not_a_free_dict(self):
        """
        VirTra's 10-Q analysis ended mid-string and parsed as nothing, while
        six others in the same batch succeeded. Constraining the response to a
        schema is what stops a long answer failing that way.
        """
        from app.services.sec_fundamentals import Outlook

        fields = Outlook.model_fields
        assert {"guidance", "guidance_direction", "orders_backlog",
                "cylinders_evidence", "risks_new", "summary_cs"} <= set(fields)

    def test_absent_guidance_is_none_not_an_empty_string(self):
        """
        "The company gave no guidance" is a real finding about a quarter. It
        must not be storable as an empty string that reads like a blank field.
        """
        from app.services.sec_fundamentals import Outlook

        outlook = Outlook()
        assert outlook.guidance is None
        assert outlook.guidance_direction == "NONE"
        assert outlook.cylinders_evidence == []

    def test_the_ceiling_leaves_room_for_a_long_filing(self):
        from app.services.sec_fundamentals import OUTLOOK_MAX_TOKENS

        assert OUTLOOK_MAX_TOKENS >= 32000

    def test_the_schema_is_acceptable_to_structured_outputs(self):
        """
        Every object needs additionalProperties:false, and range keywords are
        rejected outright.
        """
        from app.services.llm import harden_schema
        from app.services.sec_fundamentals import Outlook

        schema = harden_schema(Outlook.model_json_schema())
        assert schema["additionalProperties"] is False
        assert "minLength" not in str(schema)


# ==============================================================================
# Two defects an adversarial verification pass found in this module
# ==============================================================================

def _series(points, key="x", label="X", unit="USD"):
    """Build a Series from (start, end, value) triples; None start = instant."""
    from datetime import date as _d
    from app.services.sec_fundamentals import Point, Series

    s = Series(key=key, label_cs=label, unit=unit, tag=key)
    for start, end, value in points:
        p = Point(
            end=_d.fromisoformat(end),
            start=_d.fromisoformat(start) if start else None,
            value=value,
            form="10-Q",
        )
        if p.start is None:
            s.instant.append(p)
        elif 80 <= p.days <= 100:
            s.quarterly.append(p)
        elif 350 <= p.days <= 380:
            s.annual.append(p)
        else:
            s.ytd.append(p)
    for bucket in (s.quarterly, s.annual, s.instant, s.ytd):
        bucket.sort(key=lambda p: p.end, reverse=True)
    return s


class TestRunwayUsesAnAlignedPeriod:
    """
    Smith Micro's runway came out as "~2 months" from a filing that supports
    about 3.6. The balance was 30 June; the only quarterly cash-flow figure in
    XBRL ended 31 March, and the six-month period that actually covered the
    balance was being discarded as non-comparable. Two unrelated numbers
    divided by each other.
    """

    def test_a_six_month_period_covering_the_balance_is_used(self):
        from app.services.sec_fundamentals import _monthly_burn
        from datetime import date

        ocf = _series([
            ("2026-01-01", "2026-06-30", -4_600_000),   # the real one
            ("2026-01-01", "2026-03-31", -3_752_000),   # a quarter, ends early
        ])
        rate, point = _monthly_burn(ocf, date(2026, 6, 30))

        assert point.end == date(2026, 6, 30)
        assert rate == pytest.approx(4_600_000 / (181 / 30.44), rel=0.01)

    def test_a_period_ending_months_earlier_is_refused(self):
        """
        The stale pairing that produced the wrong number. No aligned period
        means no runway, not a runway from whatever is lying around.
        """
        from app.services.sec_fundamentals import _monthly_burn
        from datetime import date

        ocf = _series([("2026-01-01", "2026-03-31", -3_752_000)])
        assert _monthly_burn(ocf, date(2026, 6, 30)) is None

    def test_positive_cash_flow_is_not_a_burn(self):
        from app.services.sec_fundamentals import _monthly_burn
        from datetime import date

        ocf = _series([("2026-01-01", "2026-06-30", 4_600_000)])
        assert _monthly_burn(ocf, date(2026, 6, 30)) is None

    def test_the_shortest_aligned_period_wins(self):
        """A quarter describes the current rate better than a full year."""
        from app.services.sec_fundamentals import _monthly_burn
        from datetime import date

        ocf = _series([
            ("2025-07-01", "2026-06-30", -12_000_000),
            ("2026-04-01", "2026-06-30", -900_000),
        ])
        _, point = _monthly_burn(ocf, date(2026, 6, 30))
        assert point.days < 100


class TestNoComparisonAcrossASplit:
    """
    XBRL carries pre- and post-split share counts in one series without
    restating the old rows. Smith Micro's real data holds 25,500,000 on
    2026-06-03 and 5,100,000 on 2026-06-04 — a 1-for-5 reverse split — and
    comparing across it produced a 71 % "fall" in a company whose share count
    had actually risen.
    """

    #: The real rows, from SEC on 2026-08-22.
    SMSI = [
        (None, "2026-06-30", 5_589_880),
        (None, "2026-06-04", 5_100_000),
        (None, "2026-06-03", 25_500_000),
        (None, "2025-06-30", 19_382_014),
    ]

    def test_a_split_between_two_points_is_detected(self):
        from app.services.sec_fundamentals import _split_between

        shares = _series(self.SMSI)
        newer = shares.instant[0]
        older = shares.instant[-1]
        assert _split_between(shares, newer, older) is True

    def test_a_normal_year_of_dilution_is_not_a_split(self):
        from app.services.sec_fundamentals import _split_between

        shares = _series([
            (None, "2026-06-30", 9_001_540),
            (None, "2025-06-30", 7_466_425),
        ])
        assert _split_between(shares, shares.instant[0], shares.instant[-1]) is False

    def test_the_finding_refuses_the_comparison_and_says_why(self):
        from app.services.sec_fundamentals import Fundamentals, derive_findings

        data = Fundamentals(ticker="SMSI", cik="0000948708")
        data.series["shares_outstanding"] = _series(
            self.SMSI, key="shares_outstanding", label="Počet akcií", unit="shares"
        )
        finding = derive_findings(data)[-1]

        assert "split" in finding
        assert "5,589,880" in finding
        assert "71" not in finding, "the fabricated 71 % fall must be gone"


class TestRedFlagsHaveTheirOwnField:
    """
    The first version of this prompt asked for `cylinders_evidence` and
    `red_flags` with overlapping definitions, and the model filled whichever
    came first — every filing came back with zero red flags while the same
    facts sat in the cylinder list, unranked and unquoted. The two fields now
    partition: negative facts in one, neutral and positive in the other.
    """

    def test_the_model_carries_severity_and_a_quote(self):
        from app.services.sec_fundamentals import RedFlag

        flag = RedFlag()
        assert flag.severity == "MEDIUM"
        assert hasattr(flag, "quote")
        assert hasattr(flag, "category")

    def test_red_flags_are_asked_for_before_the_neutral_facts(self):
        """Ordering is what decides which bucket the model fills."""
        from app.services.sec_fundamentals import OUTLOOK_PROMPT

        assert OUTLOOK_PROMPT.index('"red_flags"') < OUTLOOK_PROMPT.index('"cylinders_evidence"')

    def test_the_prompt_names_the_categories_explicitly(self):
        """A general ask for "risks" misses most of these."""
        from app.services.sec_fundamentals import OUTLOOK_PROMPT

        for needed in ("going concern", "material weakness", "delisting",
                       "koncentrace zákazníků", "Event of Default"):
            assert needed in OUTLOOK_PROMPT, needed

    def test_the_two_fields_are_told_not_to_overlap(self):
        from app.services.sec_fundamentals import OUTLOOK_PROMPT

        assert "jen v jednom" in OUTLOOK_PROMPT

    def test_critical_flags_sort_above_the_rest(self):
        from app.services.sec_sync import format_outlook

        rendered = format_outlook({
            "guidance": None,
            "red_flags": [
                {"severity": "MEDIUM", "category": "x", "fact_cs": "drobnost", "quote": "q"},
                {"severity": "CRITICAL", "category": "going_concern",
                 "fact_cs": "pochybnost o pokracovani", "quote": "q"},
            ],
        })
        assert rendered.index("pochybnost o pokracovani") < rendered.index("drobnost")
        assert "Varovné signály" in rendered


# ==============================================================================
# A 6-K cover page is not the report
# ==============================================================================

RDCM_MANIFEST = """<html><body><pre>
&lt;SEC-HEADER&gt;
COMPANY CONFORMED NAME: RADCOM LTD
&lt;/SEC-HEADER&gt;
&lt;DOCUMENT&gt;
&lt;TYPE&gt;6-K
&lt;SEQUENCE&gt;1
&lt;FILENAME&gt;ea0301737-6k_radcom.htm
&lt;DESCRIPTION&gt;REPORT OF FOREIGN PRIVATE ISSUER
&lt;TEXT&gt;
&lt;/DOCUMENT&gt;
&lt;DOCUMENT&gt;
&lt;TYPE&gt;EX-99.1
&lt;SEQUENCE&gt;2
&lt;FILENAME&gt;ea030173701ex99-1.htm
&lt;DESCRIPTION&gt;PRESS RELEASE REPORTING SECOND QUARTER RESULTS
&lt;TEXT&gt;
&lt;/DOCUMENT&gt;
&lt;DOCUMENT&gt;
&lt;TYPE&gt;GRAPHIC
&lt;SEQUENCE&gt;3
&lt;FILENAME&gt;ea030173701_ex99-1img1.jpg
&lt;DESCRIPTION&gt;GRAPHIC
&lt;TEXT&gt;
&lt;/DOCUMENT&gt;
</pre></body></html>"""

FILING_URL = (
    "https://www.sec.gov/Archives/edgar/data/1016838/"
    "000121390026088035/ea0301737-6k_radcom.htm"
)
ACCESSION = "0001213900-26-088035"
CIK = "0001016838"


def _serving(pages: dict):
    """A client whose every fetch is answered from `pages`, or refused."""
    from unittest.mock import MagicMock

    from app.services.sec_edgar import SecEdgarClient

    client = SecEdgarClient()

    def fake_get(url):
        for fragment, body in pages.items():
            if fragment in url:
                response = MagicMock()
                response.status_code = 200
                response.text = body
                return response
        raise AssertionError(f"nečekaný požadavek: {url}")

    client._get = fake_get
    return client


class TestFilingManifest:
    """
    Which file inside a filing holds the substance is stated by EDGAR itself in
    `-index-headers.html`. Reading the manifest rather than guessing at
    filenames is the difference between working for every filing agent and
    working for the one we happened to look at.
    """

    def _docs(self, text=RDCM_MANIFEST):
        return _serving({"index-headers": text}).fetch_documents(CIK, ACCESSION)

    def test_the_manifest_is_parsed_into_typed_documents(self):
        docs = self._docs()

        assert [d.type for d in docs] == ["6-K", "EX-99.1", "GRAPHIC"]
        assert docs[1].filename == "ea030173701ex99-1.htm"
        assert "SECOND QUARTER" in docs[1].description

    def test_only_ex99_counts_as_substance(self):
        assert [d.type for d in self._docs() if d.is_substantive_exhibit] == ["EX-99.1"]

    def test_an_exhibit_url_points_at_the_raw_file(self):
        assert self._docs()[1].url == (
            "https://www.sec.gov/Archives/edgar/data/1016838/"
            "000121390026088035/ea030173701ex99-1.htm"
        )

    def test_a_manifest_listing_nothing_is_not_an_error(self):
        """
        Empty means we read it and it lists nothing. A failure to read means
        something else entirely, and raises.
        """
        assert self._docs("<html><body><pre>nic tu není</pre></body></html>") == []


class TestWrapperFormsReadTheirExhibits:
    """
    Found 2026-08-23 on RADCOM, 9.9 % of the portfolio: its newest 6-K rendered
    to 1,777 characters of "the following is furnished herewith". The quarter —
    revenue, guidance, the lot — was the 133 kB EX-99.1 beside it. The app read
    the cover page, found nothing, and displayed nothing found.
    """

    COVER = (
        "<html><body>The following is furnished herewith: Exhibit 99.1."
        "</body></html>"
    )
    EXHIBIT = (
        "<html><body>"
        + ("RADCOM reports record second quarter revenue. " * 300)
        + "</body></html>"
    )

    def _read(self, pages, form="6-K"):
        from app.services.sec_sync import read_filing

        return read_filing(
            _serving(pages), url=FILING_URL, form=form, cik=CIK, accession=ACCESSION,
        )

    def test_the_exhibit_is_read_and_not_the_cover_alone(self):
        result = self._read({
            "index-headers": RDCM_MANIFEST,
            "ea0301737-6k_radcom.htm": self.COVER,
            "ea030173701ex99-1.htm": self.EXHIBIT,
        })

        assert "record second quarter revenue" in result.text
        assert result.sources == ["ea0301737-6k_radcom.htm", "ea030173701ex99-1.htm"]
        assert result.thin_note is None

    def test_a_cover_with_no_exhibit_says_so(self):
        """
        RADCOM's 2026-05-27 6-K genuinely carries no attachment. Rendering that
        the same as a quiet quarter is the defect this fix exists for.
        """
        result = self._read({
            "index-headers": RDCM_MANIFEST.replace("EX-99.1", "EX-1.1"),
            "ea0301737-6k_radcom.htm": self.COVER,
        })

        assert result.thin_note is not None
        assert "průvodní stran" in result.thin_note

    def test_a_10q_is_read_as_filed(self):
        """
        A 10-Q is the report. Fetching a manifest for one would be a request per
        filing for nothing — `_serving` refuses any fetch we did not expect.
        """
        report = "<html><body>" + ("Quarterly report body. " * 500) + "</body></html>"
        result = self._read({"ea0301737-6k_radcom.htm": report}, form="10-Q")

        assert result.sources == ["ea0301737-6k_radcom.htm"]
        assert result.thin_note is None

    def test_a_thin_primary_document_reaches_for_exhibits_whatever_the_form(self):
        """The wrapper habit is not confined to the forms that mandate it."""
        result = self._read({
            "index-headers": RDCM_MANIFEST,
            "ea0301737-6k_radcom.htm": self.COVER,
            "ea030173701ex99-1.htm": self.EXHIBIT,
        }, form="10-Q")

        assert "record second quarter revenue" in result.text

    def test_an_unreadable_exhibit_does_not_discard_the_filing(self):
        from app.services.sec_edgar import SecError

        client = _serving({
            "index-headers": RDCM_MANIFEST,
            "ea0301737-6k_radcom.htm": self.COVER,
        })
        served = client._get

        def refuse_the_exhibit(url):
            if "ex99" in url:
                raise SecError("SEC vrátila 503")
            return served(url)

        client._get = refuse_the_exhibit

        from app.services.sec_sync import read_filing

        result = read_filing(
            client, url=FILING_URL, form="6-K", cik=CIK, accession=ACCESSION,
        )
        assert result is not None
        assert result.sources == ["ea0301737-6k_radcom.htm"]
        assert result.thin_note is not None

    def test_an_unreachable_primary_document_returns_nothing(self):
        """Not an empty analysis — nothing, so `analysis` stays NULL."""
        from app.services.sec_edgar import SecEdgarClient, SecError
        from app.services.sec_sync import read_filing

        client = SecEdgarClient()

        def sec_is_down(url):
            raise SecError("SEC vrátila 503")

        client._get = sec_is_down

        assert read_filing(
            client, url=FILING_URL, form="6-K", cik=CIK, accession=ACCESSION,
        ) is None

    def test_the_thin_note_reaches_the_rendered_summary(self):
        from app.services.sec_sync import format_outlook

        rendered = format_outlook(
            {"guidance": None},
            thin_note="Podání má jen průvodní stranu (2385 znaků).",
        )
        assert "průvodní stranu" in rendered
