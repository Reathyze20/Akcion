"""
The app may not print a verb over its own contradicting evidence.

Two engines answer different questions about the same company. The band asks
what a price is worth against the company's operational quality; the lifecycle
stage asks what the business is doing. They are allowed to disagree.

Until 2026-08-24 whichever ran first won, in silence. `_derisk_action` ran
first, so on a yellow semafor a Wait-Time stage sold the position no matter
what the band said — and the card underneath went on displaying the band. On
one live morning that produced:

    VTSI  POD ZELENOU — nejlevnější stav, jaký metodika zná  -> PRODAT (-58 %)
    IMP.V NÁKUP — levné vzhledem ke kvalitě, Breakout souhlasí -> PRODAT
    IZEA  NÁKUP — levné vzhledem ke kvalitě                   -> PRODAT

Three of twelve holdings. The owner's reaction was the correct one: „nevím,
jestli tomu věřit". An app that resolves a contradiction by hiding one side has
not earned a verb, so now it hands the disagreement over as a question.

The second half of the same rule: the tier rule may not sell a company nobody
valued. `determine_tier` ends in „everything else = TERTIARY" and yellow blocks
TERTIARY, so a missing Conviction Score alone ordered out DBO.TO at 16,8 % of
the account and RDCM at 8,7 %, both recorded Gold Mines, under the stated
reason „spekulace se v tomto trhu nedrží" — a claim with no evidence behind it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.daily_actions import (
    CONFLICT_ACTION,
    AnalysisInput,
    PositionInput,
    generate_daily_actions,
)

NOW = datetime(2026, 7, 26, 12, 0, 0)
RATES = {"USD": 25.0, "CZK": 1.0, "EUR": 25.0, "CAD": 15.0}


def fx(currency: str) -> float:
    return RATES[currency.upper()]


def run(positions, analyses, market_alert="YELLOW"):
    return generate_daily_actions(
        market_alert=market_alert,
        market_alert_updated_at=NOW,
        positions=list(positions),
        analyses=list(analyses),
        cash_czk=0.0,
        fx_rate_to_czk=fx,
        now=NOW,
    )


def gomes(ticker, **kw) -> AnalysisInput:
    kw.setdefault("cylinders_confirmed_at", NOW - timedelta(days=1))
    kw.setdefault("cylinders_valid_until", NOW + timedelta(days=60))
    kw.setdefault("line_currency", "USD")
    return AnalysisInput(ticker=ticker, source_key="GOMES", **kw)


def position(ticker, shares=100, avg_cost=10.0, price=12.0, **kw) -> PositionInput:
    return PositionInput(
        ticker=ticker, shares=shares, avg_cost=avg_cost, current_price=price,
        last_price_update=NOW, **kw
    )


def wait_time_vtsi():
    """The live case, verbatim: 3,13 against a Green Line of 5,00."""
    return dict(
        positions=[position("VTSI", shares=243, avg_cost=7.47, price=3.13)],
        analyses=[gomes(
            "VTSI", green_line=5.00, red_line=22.50, cylinders=3,
            lifecycle_phase="WAIT_TIME",
        )],
    )


# ==============================================================================
# Wait Time against a band that says the opposite
# ==============================================================================

class TestWaitTimeAgainstACheapBand:
    def test_under_the_green_line_is_a_question_not_a_sell(self):
        [action] = run(**wait_time_vtsi()).actions
        assert action.action_type == CONFLICT_ACTION

    def test_the_question_carries_both_sides(self):
        # Neither side may be dropped: the whole failure was showing one.
        [action] = run(**wait_time_vtsi()).actions
        assert "Wait Time" in action.reason
        assert "zelené čáře" in action.reason
        assert "rozhodne" in action.reason

    def test_nothing_is_placed_on_a_question(self):
        """No limit price and no side means nothing to hand a broker."""
        [action] = run(**wait_time_vtsi()).actions
        assert action.limit_price is None
        assert action.review_required is True

    def test_cheap_for_its_quality_also_objects(self):
        """IZEA, live: R/R 8,79 against a deserved 7,0 — and sold anyway."""
        [action] = run(
            positions=[position("IZEA", shares=125, avg_cost=3.95, price=2.99)],
            analyses=[gomes(
                "IZEA", green_line=2.50, red_line=11.00, cylinders=3,
                lifecycle_phase="WAIT_TIME",
            )],
        ).actions
        assert action.action_type == CONFLICT_ACTION
        assert "levné vzhledem ke kvalitě" in action.reason

    def test_a_wait_time_the_band_does_not_defend_is_still_sold(self):
        """
        The guard is narrow on purpose. Wait Time at a price the method has no
        argument for is exactly what the canon says not to hold, and turning
        every sell into a question would be the same failure pointing the other
        way.
        """
        [action] = run(
            positions=[position("DEAD", shares=100, avg_cost=10.0, price=14.0)],
            analyses=[gomes(
                "DEAD", green_line=3.25, red_line=15.50, cylinders=8,
                lifecycle_phase="WAIT_TIME",
            )],
        ).actions
        assert action.action_type == "SELL_WAIT_TIME"

    def test_no_band_at_all_is_still_sold(self):
        """
        Silence from the valuation is not an objection. IRIX and SMSI have no
        lines and stay sells — the stage is a direct claim about the company,
        and nothing contradicts it.
        """
        [action] = run(
            positions=[position("IRIX", shares=650, avg_cost=1.90, price=0.76)],
            analyses=[gomes("IRIX", lifecycle_phase="WAIT_TIME")],
        ).actions
        assert action.action_type == "SELL_WAIT_TIME"


# ==============================================================================
# A red semafor is about the market, not about this company
# ==============================================================================

class TestRedOutranksTheBand:
    def test_a_cheap_price_does_not_argue_with_red(self):
        [action] = run(market_alert="RED", **wait_time_vtsi()).actions
        assert action.action_type == "LIQUIDATE_HEAVY"


# ==============================================================================
# The tier rule needs a valuation before it may call something speculation
# ==============================================================================

class TestATierRuleWithoutAValuation:
    UNBANDED = dict(
        positions=[position("DBO.TO", shares=1900, avg_cost=0.91, price=1.13)],
        analyses=[gomes("DBO.TO", lifecycle_phase="GOLD_MINE")],
    )

    def test_a_tertiary_without_a_band_is_not_sold(self):
        """DBO.TO, live: 16,8 % of the account, sold for having no score."""
        result = run(**self.UNBANDED)
        assert not any(a.action_type == "SELL" for a in result.actions)

    def test_it_says_so_instead(self):
        result = run(**self.UNBANDED)
        assert any(
            "BEZ ČÁRY, NEPRODÁVÁM" in w and "DBO.TO" in w for w in result.warnings
        )

    def test_a_banded_tertiary_the_band_defends_becomes_a_question(self):
        [action] = run(
            positions=[position("SPEC", shares=100, avg_cost=10.0, price=2.00)],
            analyses=[gomes(
                "SPEC", green_line=5.00, red_line=22.50, cylinders=3,
                lifecycle_phase="GOLD_MINE", conviction_score=3,
            )],
        ).actions
        assert action.action_type == CONFLICT_ACTION
        assert "TERTIARY" in action.reason
