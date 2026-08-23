"""
Tests for cash and hedge as real instruments.

The interesting finding is not the arithmetic. Modelling BOXX and RWM properly
surfaced that both are US-domiciled ETFs and this portfolio is held through EU
retail brokers, which under PRIIPs generally cannot sell them. A plan that says
"put 40 % into RWM" is a plan for a button that is not there, and the canon has
its own answer for exactly that case.

So most of what is pinned here is about refusing to state a target that cannot
be filled, and about not overstating the certainty either way — nothing in this
code has seen the user's actual broker.
"""

import pytest

from app.services.cash_hedge import (
    BOXX,
    CANON_GIVES_A_NUMBER,
    CANON_INSTRUMENTS,
    RWM,
    UCITS_INVERSE_EXAMPLE,
    Availability,
    HedgeError,
    Role,
    build_plan,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_cache()
    yield
    reset_cache()


def czk(code: str) -> float:
    return {"USD": 20.62, "GBp": 0.2815, "EUR": 24.12, "CZK": 1.0}[code]


@pytest.fixture
def priced(monkeypatch):
    """Fixed prices, so a target in shares is checkable arithmetic."""
    monkeypatch.setattr(
        "app.services.cash_hedge.price_of",
        lambda ticker: {"BOXX": 117.96, "RWM": 13.39}.get(ticker),
    )


# ==============================================================================
# The instruments are real
# ==============================================================================

class TestInstruments:
    def test_the_canon_names_a_cash_park_and_a_hedge(self):
        assert BOXX.role is Role.CASH_PARK
        assert RWM.role is Role.HEDGE
        assert set(CANON_INSTRUMENTS) == {BOXX, RWM}

    def test_both_are_us_funds(self):
        """Verified against live quote data 2026-08-23. This is the whole point."""
        assert BOXX.domicile == "US" and BOXX.exchange == "Cboe US"
        assert RWM.domicile == "US" and RWM.exchange == "NYSE Arca"
        assert not BOXX.ucits and not RWM.ucits

    def test_a_us_fund_is_likely_blocked_for_eu_retail(self):
        assert BOXX.availability is Availability.LIKELY_BLOCKED_EU_RETAIL
        assert RWM.availability is Availability.LIKELY_BLOCKED_EU_RETAIL

    def test_a_ucits_fund_is_likely_fine(self):
        assert UCITS_INVERSE_EXAMPLE.availability is Availability.LIKELY_AVAILABLE

    def test_likely_is_the_word_because_no_broker_was_asked(self):
        """
        Nothing here has seen the user's account. "Unavailable" would be a claim
        about a product list this code has never read.
        """
        assert "LIKELY" in Availability.LIKELY_BLOCKED_EU_RETAIL.value

    def test_the_ucits_example_is_not_offered_as_a_substitute(self):
        """
        Different index, daily reset. Naming it as an equivalent would be worse
        than not naming it at all.
        """
        assert "Není to náhrada" in UCITS_INVERSE_EXAMPLE.note_cs
        assert "denně" in UCITS_INVERSE_EXAMPLE.note_cs
        assert UCITS_INVERSE_EXAMPLE not in CANON_INSTRUMENTS


# ==============================================================================
# The plan is executable, or says why not
# ==============================================================================

class TestPlan:
    def test_green_wants_no_hedge_and_no_cash_park(self, priced):
        plan = build_plan("GREEN", 231_486.0, fx_rate_to_czk=czk)

        assert plan.hedge_pct == 0.0
        assert all(leg.target_czk == 0.0 for leg in plan.legs)

    def test_amounts_become_share_counts(self, priced):
        plan = build_plan("YELLOW", 100_000.0, fx_rate_to_czk=czk)
        hedge = next(leg for leg in plan.legs if leg.instrument is RWM)

        # 10 % of 100,000 CZK at 13.39 USD × 20.62
        assert hedge.target_czk == pytest.approx(10_000.0)
        assert hedge.shares == pytest.approx(10_000 / (13.39 * 20.62), rel=1e-6)

    def test_an_unset_semafor_does_not_default_to_green(self):
        """
        Planning for GREEN because nobody set the field is how a portfolio ends
        up unhedged by accident.
        """
        with pytest.raises(HedgeError, match="Semafor není nastavený"):
            build_plan(None, 100_000.0, fx_rate_to_czk=czk)

    def test_an_unknown_semafor_is_refused(self):
        with pytest.raises(HedgeError, match="Neznámý semafor"):
            build_plan("PUCE", 100_000.0, fx_rate_to_czk=czk)

    def test_a_missing_price_leaves_the_share_count_empty(self, monkeypatch):
        monkeypatch.setattr("app.services.cash_hedge.price_of", lambda t: None)
        plan = build_plan("ORANGE", 100_000.0, fx_rate_to_czk=czk)

        assert all(leg.shares is None for leg in plan.legs)
        assert any("cenu se nepodařilo" in gap for gap in plan.gaps)

    def test_an_unconvertible_currency_is_a_gap_not_a_number(self, priced):
        from app.services.currency import CurrencyError

        def refuse(code):
            raise CurrencyError(f"Neznámá měna {code}")

        plan = build_plan("ORANGE", 100_000.0, fx_rate_to_czk=refuse)

        assert all(leg.shares is None for leg in plan.legs)
        assert plan.gaps


# ==============================================================================
# The blocker, and the canon's own fallback
# ==============================================================================

class TestBlockedInEurope:
    def test_a_defensive_alert_reports_the_blocker(self, priced):
        plan = build_plan("ORANGE", 231_486.0, fx_rate_to_czk=czk)

        assert all(leg.blocker_cs for leg in plan.legs)
        assert "PRIIPs" in plan.legs[0].blocker_cs

    def test_the_fallback_is_the_canons_own_line(self, priced):
        plan = build_plan("ORANGE", 231_486.0, fx_rate_to_czk=czk)

        assert plan.fallback_cs is not None
        assert "víc cashe místo hedge" in plan.fallback_cs
        assert "extra vybíravý" in plan.fallback_cs

    def test_the_fallback_names_the_whole_defensive_share(self, priced):
        """35 % cash + 40 % hedge in ORANGE — the fallback covers both."""
        plan = build_plan("ORANGE", 100_000.0, fx_rate_to_czk=czk)

        assert "75 %" in plan.fallback_cs

    def test_green_has_nothing_to_block(self, priced):
        """A target of zero cannot be unfillable."""
        assert build_plan("GREEN", 100_000.0, fx_rate_to_czk=czk).fallback_cs is None

    def test_the_blocker_tells_the_user_to_check(self, priced):
        plan = build_plan("YELLOW", 100_000.0, fx_rate_to_czk=czk)

        assert "ověř" in plan.legs[0].blocker_cs.lower()


# ==============================================================================
# Whose number is it
# ==============================================================================

class TestCanonVersusInterpretation:
    def test_yellow_is_quoted_from_the_canon(self, priced):
        plan = build_plan("YELLOW", 100_000.0, fx_rate_to_czk=czk)

        assert plan.interpreted is False
        assert "20-30" in plan.canon_text

    def test_orange_and_red_are_the_apps_reading(self, priced):
        """
        The canon gives ORANGE a sentence, not a percentage. Rendering 25/35/40
        as though Gomes said it would be putting words in his mouth.
        """
        for alert in ("ORANGE", "RED"):
            plan = build_plan(alert, 100_000.0, fx_rate_to_czk=czk)
            assert plan.interpreted is True

    def test_the_orange_text_is_the_sentence_he_did_say(self, priced):
        plan = build_plan("ORANGE", 100_000.0, fx_rate_to_czk=czk)

        assert "ALL of my cash in RWM" in plan.canon_text

    def test_every_alert_carries_its_canon_text(self, priced):
        for alert in ("GREEN", "YELLOW", "ORANGE", "RED"):
            assert build_plan(alert, 100_000.0, fx_rate_to_czk=czk).canon_text

    def test_only_green_and_yellow_claim_a_canonical_number(self):
        assert CANON_GIVES_A_NUMBER == {"GREEN", "YELLOW"}
