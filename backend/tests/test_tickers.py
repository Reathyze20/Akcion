"""
One company, several symbols.

The four positions this matters for are held on a Canadian exchange while both
analysis sources name the American OTC listing. Before the alias table, the
Breakout card called `KUYAF` "sledujeme" while the owner held `KUYA.V`, and the
Gomes valuation band came out empty for exactly the names it mattered most for.
"""

from app.core.tickers import canonical_ticker, same_company, variants_of


class TestCanonical:
    def test_canadian_listing_maps_to_the_otc_symbol(self):
        assert canonical_ticker("KUYA.V") == "KUYAF"
        assert canonical_ticker("GSI.V") == "GKPRF"
        assert canonical_ticker("IMP.V") == "ITMSF"
        assert canonical_ticker("DBO.TO") == "DBOXF"

    def test_the_canonical_symbol_maps_to_itself(self):
        assert canonical_ticker("KUYAF") == "KUYAF"

    def test_an_unknown_ticker_is_returned_unchanged(self):
        # Most tickers have one listing. Not being in the table is the normal
        # case, not a failure.
        assert canonical_ticker("AEHR") == "AEHR"

    def test_case_and_whitespace_do_not_matter(self):
        assert canonical_ticker("  kuya.v ") == "KUYAF"

    def test_nothing_in_nothing_out(self):
        assert canonical_ticker(None) == ""
        assert canonical_ticker("") == ""


class TestSameCompany:
    def test_two_listings_of_one_issuer(self):
        assert same_company("KUYA.V", "KUYAF")
        assert same_company("KUYAF", "KUYA.V")

    def test_two_different_issuers(self):
        assert not same_company("KUYA.V", "AEHR")

    def test_an_empty_symbol_matches_nothing(self):
        # Not even another empty one — otherwise a pair of missing tickers
        # would read as a match.
        assert not same_company(None, None)
        assert not same_company("", "KUYAF")


class TestVariants:
    def test_every_listing_comes_back_canonical_first(self):
        assert variants_of("KUYA.V") == ("KUYAF", "KUYA.V")
        assert variants_of("KUYAF") == ("KUYAF", "KUYA.V")

    def test_a_single_listing_ticker_returns_just_itself(self):
        assert variants_of("AEHR") == ("AEHR",)

    def test_nothing_in_empty_out(self):
        assert variants_of(None) == ()


def test_no_symbol_belongs_to_two_companies():
    """
    The table is hand-written, so the one mistake it can make is guarded here.

    A symbol appearing in two groups would silently merge two issuers, and the
    cost of that is a position sized against somebody else's analysis.
    """
    from app.core.tickers import _GROUPS

    seen: dict[str, tuple[str, ...]] = {}
    for group in _GROUPS:
        for symbol in group:
            assert symbol not in seen, (
                f"{symbol} je ve dvou skupinách: {seen.get(symbol)} a {group}"
            )
            seen[symbol] = group
