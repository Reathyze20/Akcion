"""
One company, several symbols.

Four of this portfolio's positions are held on a Canadian exchange while every
analysis of them — Mark Gomes' and the Breakout Investors watchlist alike —
names the American OTC listing. Nothing in the app connected the two, so
`KUYA.V` and `KUYAF` were two companies as far as the code was concerned: the
Breakout card called a position we hold "sledujeme", and a ticker could carry
two `stocks` rows with two different Conviction Scores.

Matching by company name was the obvious alternative and is rejected here.
"Kuya Silver Corp" and "Kuya Silver Corporation" do match, but so would two
genuinely different issuers with similar names, and the cost of a wrong match
is a position sized against somebody else's analysis. The table below is
explicit, short, and carries the evidence for every line, so it can be checked
by eye.

Aliasing is for MATCHING only. Nothing here rewrites what is shown: a position
bought as `KUYA.V` is displayed as `KUYA.V`, because that is what the broker
statement says and what the owner would search for.
"""

from __future__ import annotations

#: Each group is one company. The first entry is the canonical form — the US
#: OTC symbol wherever one exists, because that is the symbol both analysis
#: sources use, and the join we care about is position -> analysis.
#:
#: Evidence for each group is the pair of company names the two sides store.
_GROUPS: tuple[tuple[str, ...], ...] = (
    # "D-Box Technologies Inc Class A" (Trading 212)  /  D-BOX on the OTC
    ("DBOXF", "DBO.TO"),
    # "Gatekeeper Systems Inc" (broker)  /  "Gatekeeper Systems Inc." (theirs)
    ("GKPRF", "GSI.V"),
    # "Intermap Technologies Corp Class A"  /  "INTERMAP TECHNOLOGIES CORP"
    ("ITMSF", "IMP.V"),
    # "Kuya Silver Corp"  /  "Kuya Silver Corporation"
    ("KUYAF", "KUYA.V"),
    # "Geodrill" (our stocks row)  /  "Geodrill Ltd" (theirs)
    ("GEODF", "GEO.TO"),
    # "Kraken Robotics" — two rows in our own stocks table, no third party
    ("KRKNF", "KRKN"),
    # "ADCORE INC" arrives from the broker as an ISIN, not a ticker; theirs is
    # "Adcore Inc". Listed here because the identity problem is the same one,
    # even though the second form is an ISIN.
    ("ADCOF", "CA00654B1040"),
)

#: variant -> canonical. Built once; every lookup is a dict hit.
_CANONICAL: dict[str, str] = {
    variant: group[0] for group in _GROUPS for variant in group
}


def canonical_ticker(ticker: str | None) -> str:
    """
    The symbol used for matching. Unknown symbols are returned unchanged.

    Case- and whitespace-insensitive, so a broker's `kuya.v` and a source's
    `KUYA.V` land on the same key.
    """
    if not ticker:
        return ""
    key = ticker.strip().upper()
    return _CANONICAL.get(key, key)


def same_company(left: str | None, right: str | None) -> bool:
    """Whether two symbols name the same issuer."""
    canonical = canonical_ticker(left)
    return bool(canonical) and canonical == canonical_ticker(right)


def variants_of(ticker: str | None) -> tuple[str, ...]:
    """
    Every symbol known for this company, canonical first.

    A single-element tuple for anything not in the table — which is the honest
    answer, not a failure: most tickers have exactly one listing here.
    """
    canonical = canonical_ticker(ticker)
    if not canonical:
        return ()
    for group in _GROUPS:
        if canonical == group[0]:
            return group
    return (canonical,)
