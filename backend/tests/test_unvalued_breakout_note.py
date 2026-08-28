"""
The second opinion on the holdings the method cannot value.

Eight of twelve holdings have no Green and no Red Line, and until Breakout was
wired in the app said nothing at all about most of the money. Six of those eight
are on Breakout's list, so for most of that silence there is now a number from
somebody outside.

What is tested is that the number stays in its place. It is a target derived
from a downloaded ratio, not a valuation, and it has no floor — so it must
never become a band, never become a purchase, and never be compared against a
price in a different currency.
"""

from dataclasses import dataclass

from app.core.tickers import canonical_ticker
from app.services.breakout_band import WatchlistRow, build_view
from app.services.outside_method import SEVERITY_NOTE
from app.services.unvalued_lookup import _breakout_note, _podpisy


@dataclass
class FakePosition:
    ticker: str
    current_price: float | None
    currency: str | None


def view_for(symbol, target, endorsements=3):
    return build_view(
        WatchlistRow(symbol=symbol, implied_target=target, endorsements=endorsements)
    )


def note_for(ticker, price, currency, target, endorsements=3):
    # Keyed by canonical ticker, exactly as `breakout_views` keys it — KUYA.V
    # and KUYAF are one company, and a lookup on the raw symbol silently finds
    # nothing for the four dual-listed holdings.
    return _breakout_note(
        FakePosition(ticker, price, currency),
        ticker,
        {canonical_ticker(ticker): view_for(ticker, target, endorsements)},
    )


# ==============================================================================
# It stays a note
# ==============================================================================

def test_their_target_is_a_note_and_never_an_instruction():
    """
    A target with no floor cannot say "cheap". Anything stronger than a NOTE
    would let a downloaded ratio act like a valuation.
    """
    [finding] = note_for("DAIO", 2.97, "USD", 6.50)
    assert finding.severity == SEVERITY_NOTE
    assert not finding.is_exit


def test_the_note_says_it_is_derived_and_not_a_valuation():
    [finding] = note_for("DAIO", 2.97, "USD", 6.50)
    assert "staženého seznamu" in finding.message_cs
    assert "ne\nocenění" in finding.message_cs or "ne ocenění" in finding.message_cs


def test_the_note_says_why_there_is_no_band():
    [finding] = note_for("DAIO", 2.97, "USD", 6.50)
    assert "spodní hranici nemají" in finding.message_cs
    assert "nákup nedělám" in finding.message_cs


def test_a_company_they_do_not_cover_gets_no_note():
    assert _breakout_note(FakePosition("ECOR", 10.52, "USD"), "ECOR", {}) == []


# ==============================================================================
# The currency trap
# ==============================================================================

def test_a_canadian_price_is_not_compared_to_a_dollar_target_raw():
    """
    DBO.TO trades in Canadian dollars against a target quoted on the US
    listing. The raw comparison is wrong by the whole exchange rate — the same
    defect that produced a wrong TRIM on GSI.V.
    """
    [cad] = note_for("DBO.TO", 1.13, "CAD", 1.57)
    [usd] = note_for("DBO.TO", 1.13, "USD", 1.57)
    assert cad.message_cs != usd.message_cs


def test_a_euro_holding_is_converted_before_the_percentage():
    """KUYA.V is held in euros; 311 % raw is 252 % once the rate is applied."""
    [eur] = note_for("KUYA.V", 0.459, "EUR", 1.89)
    assert "252 %" in eur.message_cs


def test_the_direction_is_named_when_price_is_above_their_target():
    [finding] = note_for("XYZ", 10.00, "USD", 5.00)
    assert "POD dnešní cenou" in finding.message_cs


# ==============================================================================
# Czech that reads as written rather than generated
# ==============================================================================

def test_counts_are_declined():
    assert _podpisy(1) == "podpis"
    assert _podpisy(3) == "podpisy"
    assert _podpisy(6) == "podpisů"


def test_the_note_uses_the_declined_form():
    [three] = note_for("DAIO", 2.97, "USD", 6.50, endorsements=3)
    [six] = note_for("DAIO", 2.97, "USD", 6.50, endorsements=6)
    assert "3 podpisy" in three.message_cs
    assert "6 podpisů" in six.message_cs


def test_no_price_means_no_note_rather_than_a_wrong_one():
    assert note_for("DAIO", None, "USD", 6.50) == []
