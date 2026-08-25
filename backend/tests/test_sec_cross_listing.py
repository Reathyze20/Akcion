"""
The company files with the SEC; the app was asking under the wrong symbol.

`IMP.V` was recorded as NOT_AN_SEC_FILER because a foreign exchange suffix
settled the question without a lookup. That short-circuit is right in spirit —
stripping ".V" off `GSI.V` and asking EDGAR for `GSI` matches an unrelated US
company — but it also skipped the curated cross-listing map, and Intermap
Technologies files under CIK 0001285170 as `ITMSF`.

One of twelve holdings therefore sat in the unassessable pile with audited
quarterly filings available the whole time.
"""

from app.services.sec_edgar import CoverageStatus, SecEdgarClient


class Stub(SecEdgarClient):
    """A client that answers from a dict instead of from EDGAR."""

    def __init__(self, index: dict[str, tuple[str, str]]):
        super().__init__()
        self._index = index

    def resolve_cik(self, ticker: str):
        hit = self._index.get(ticker.upper())
        return hit if hit else (None, None)


INTERMAP = {"ITMSF": ("0001285170", "INTERMAP TECHNOLOGIES CORP")}


# ==============================================================================
# The curated map is consulted; a suffix strip never is
# ==============================================================================

def test_a_canadian_listing_is_covered_through_its_us_twin():
    coverage = Stub(INTERMAP).fetch_coverage("IMP.V")
    assert coverage.status is CoverageStatus.COVERED
    assert coverage.cik == "0001285170"


def test_the_note_says_which_symbol_actually_files():
    """
    Somebody reading this later has to be able to check it. "Covered" with no
    symbol is a claim they cannot verify.
    """
    coverage = Stub(INTERMAP).fetch_coverage("IMP.V")
    assert "ITMSF" in coverage.note


def test_a_company_with_no_us_filer_stays_uncovered():
    coverage = Stub({}).fetch_coverage("GSI.V")
    assert coverage.status is CoverageStatus.NOT_AN_SEC_FILER


def test_the_uncovered_note_still_says_nothing_about_the_company():
    """
    "Not an SEC filer" is a fact about where it files, never about whether it
    is any good — the distinction this codebase keeps having to restate.
    """
    coverage = Stub({}).fetch_coverage("GSI.V")
    assert "O firmě samotné to neříká nic" in coverage.note


def test_the_base_symbol_is_never_tried_on_its_own():
    """
    The guard the original short-circuit existed to provide. `GSI` is a real
    US ticker belonging to a different business; matching it would attach
    another company's filings to this holding.
    """
    asked: list[str] = []

    class Watcher(Stub):
        def resolve_cik(self, ticker: str):
            asked.append(ticker.upper())
            return super().resolve_cik(ticker)

    Watcher({"GSI": ("0000000001", "SOMEBODY ELSE")}).fetch_coverage("GSI.V")
    assert "GSI" not in asked


def test_a_registry_outage_records_no_verdict():
    """
    An unreachable EDGAR must not be written down as "does not file". That is
    the difference between a fact and a failed request.
    """
    from app.services.sec_edgar import SecError

    class Broken(Stub):
        def resolve_cik(self, ticker: str):
            raise SecError("EDGAR je dole")

    coverage = Broken({}).fetch_coverage("IMP.V")
    assert coverage.status is not CoverageStatus.COVERED
