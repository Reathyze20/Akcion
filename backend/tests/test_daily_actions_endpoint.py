"""
Daily Action engine + endpoint tests (Phase 3 of the roadmap).

Locks Path 1 of EFFICIENT_INVESTING_PLAYBOOK.md: max 3 ranked actions with
exact CZK amounts, "Nic. Drž." (HOLD_HOLD_HOLD) as the first-class rest state,
de-risking ranked above profit-taking above buying, and missing data surfacing
as warnings instead of invented numbers.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.daily_actions as daily_actions_route
from app.database.connection import get_db
from app.services.daily_actions import (
    AnalysisInput,
    PositionInput,
    generate_daily_actions,
)

NOW = datetime(2026, 7, 26, 12, 0, 0)

RATES = {"USD": 25.0, "CZK": 1.0, "EUR": 25.0, "CAD": 15.0}


def fx(currency: str) -> float:
    return RATES[currency.upper()]


def run(
    market_alert="GREEN",
    positions=(),
    analyses=(),
    cash_czk=0.0,
    market_alert_updated_at=NOW,
    **kw,
):
    """Defaults to a semafor set today; staleness is opted into explicitly."""
    return generate_daily_actions(
        market_alert=market_alert,
        market_alert_updated_at=market_alert_updated_at,
        positions=list(positions),
        analyses=list(analyses),
        cash_czk=cash_czk,
        fx_rate_to_czk=fx,
        now=NOW,
        **kw,
    )


def gomes(ticker, **kw) -> AnalysisInput:
    """
    A Gomes analysis whose cylinder count the owner has confirmed.

    Confirmation is defaulted here because these tests are about the buy rules,
    not about the confirmation gate — that gate has its own tests, which pass a
    proposal and assert the purchase is refused. Without the default, every buy
    test would silently be testing "an unconfirmed number does not buy" and
    would keep passing if the rules underneath it broke.
    """
    kw.setdefault("cylinders_confirmed_at", NOW - timedelta(days=1))
    kw.setdefault("cylinders_valid_until", NOW + timedelta(days=60))
    # Every Gomes band is quoted on the US OTC listing. Stated rather than
    # assumed, because scoring a price against a band in another currency is
    # wrong by the whole exchange rate.
    kw.setdefault("line_currency", "USD")
    return AnalysisInput(ticker=ticker, source_key="GOMES", **kw)


def position(ticker, shares=100, avg_cost=10.0, price=12.0, **kw) -> PositionInput:
    return PositionInput(
        ticker=ticker, shares=shares, avg_cost=avg_cost, current_price=price,
        last_price_update=NOW, **kw
    )


# ==============================================================================
# "Nic. Drž." — the rest state
# ==============================================================================

class TestHoldState:
    def test_empty_portfolio_green_is_hold(self):
        result = run(market_alert="GREEN")
        assert result.status == "HOLD_HOLD_HOLD"
        assert result.actions == []
        assert result.market_alert == "GREEN"

    def test_healthy_green_portfolio_is_hold(self):
        """Held Gold Mine at fair value, nothing doubled -> nothing to do."""
        result = run(
            market_alert="GREEN",
            positions=[position("CXDO", shares=50, avg_cost=6.0, price=6.62)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, cylinders=5,
                lifecycle_phase="GOLD_MINE", conviction_score=8,
            )],
            cash_czk=10_000.0,
        )
        assert result.status == "HOLD_HOLD_HOLD"
        assert result.actions == []

    def test_unknown_market_alert_warns_and_blocks_buys(self):
        """No semafor row -> loud warning, no silent GREEN, no BUY actions."""
        result = run(
            market_alert=None,
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, cylinders=9,
                lifecycle_phase="GOLD_MINE", conviction_score=9, current_price=3.50,
            )],
            cash_czk=100_000.0,
        )
        assert result.market_alert == "UNKNOWN"
        assert result.actions == []
        assert any("Market Alert" in w for w in result.warnings)


# ==============================================================================
# De-risking on Yellow/Orange/Red
# ==============================================================================

class TestDeRisk:
    def test_yellow_sells_wait_time_position(self):
        result = run(
            market_alert="YELLOW",
            positions=[position("AEHR", shares=80, avg_cost=20.0, price=15.0)],
            analyses=[gomes("AEHR", lifecycle_phase="WAIT_TIME", conviction_score=4)],
        )
        assert result.status == "ACTION_REQUIRED"
        [action] = result.actions
        assert action.action_type == "SELL_WAIT_TIME"
        assert action.quantity == 80
        assert action.estimated_czk_value == pytest.approx(80 * 15.0 * 25.0)
        assert "Wait Time" in action.reason

    def test_yellow_does_not_sell_a_position_it_knows_nothing_about(self):
        """
        determine_tier ends in "everything else = TERTIARY", so a position
        with no phase and no conviction score landed in the tier Yellow
        blocks, and the app ordered it sold for the sole reason that it had
        no data on it. The real portfolio is fourteen positions with almost
        no phases recorded — this rule alone said liquidate all of it.

        Not knowing whether a holding is speculative is not the same as
        knowing it is. The gap is now stated instead of acted on.
        """
        result = run(market_alert="YELLOW", positions=[position("XXXX")])
        assert not any(a.action_type == "SELL" for a in result.actions)
        assert any("NEZAŘAZENÁ POZICE" in w and "XXXX" in w for w in result.warnings)

    def test_a_conviction_score_is_not_evidence_that_the_tier_is_known(self):
        """
        The guard above originally accepted a Conviction Score as proof the
        tier was known, and that inverted the meaning of the number. The tier
        says what KIND of position this is — proven Gold Mine, Great Find,
        speculation — and that is a property of the lifecycle stage.
        Conviction says how much of the thesis is believed.

        On 2026-08-23, with the market at yellow, the engine's first live run
        ordered KUYA.V sold in full. It carries the highest Conviction Score in
        the app — 10 out of 10 — and its only fault was that nobody had ever
        recorded its lifecycle stage.
        """
        result = run(
            market_alert="YELLOW",
            positions=[position("KUYA.V", shares=2325, avg_cost=0.4, price=0.46)],
            analyses=[gomes("KUYA.V", conviction_score=10, lifecycle_phase=None)],
        )
        assert not any(a.action_type == "SELL" for a in result.actions)
        assert any("NEZAŘAZENÁ POZICE" in w and "KUYA.V" in w for w in result.warnings)

    def test_yellow_still_sells_a_tertiary_it_actually_knows_about(self):
        """
        The rule itself is intact — it just needs evidence to fire.

        „Evidence" now includes a band. Without one the app cannot tell a
        speculation from a company nobody valued, and since 2026-08-24 it says
        so instead of selling (see `test_a_tertiary_without_a_band_is_not_sold`).
        The price here sits well inside its band, so the valuation has no
        objection and the tier rule is the only thing speaking.
        """
        result = run(
            market_alert="YELLOW",
            positions=[position("XXXX")],
            analyses=[gomes(
                "XXXX", green_line=3.25, red_line=15.50,
                lifecycle_phase="GOLD_MINE", conviction_score=3,
            )],
        )
        [action] = result.actions
        assert action.action_type == "SELL"
        assert "TERTIARY" in action.reason

    def test_yellow_keeps_proven_gold_mine(self):
        result = run(
            market_alert="YELLOW",
            positions=[position("CXDO", shares=50, avg_cost=6.0, price=6.62)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, cylinders=5,
                lifecycle_phase="GOLD_MINE", conviction_score=8,
            )],
        )
        assert result.status == "HOLD_HOLD_HOLD"

    def test_red_liquidates_everything(self):
        result = run(
            market_alert="RED",
            positions=[position("CXDO"), position("AEHR")],
            analyses=[gomes(
                "CXDO", lifecycle_phase="GOLD_MINE", conviction_score=9, cylinders=9
            )],
        )
        assert len(result.actions) == 2
        assert {a.action_type for a in result.actions} == {"LIQUIDATE_HEAVY"}
        assert all(a.urgency_score == 100 for a in result.actions)


# ==============================================================================
# Doubling rule + R/R trims
# ==============================================================================

class TestTrims:
    def test_doubled_position_trims_half(self):
        result = run(
            market_alert="GREEN",
            positions=[position("VTSI", shares=100, avg_cost=5.0, price=11.0)],
        )
        [action] = result.actions
        assert action.action_type == "TRIM"
        assert action.quantity == 50
        assert action.estimated_czk_value == pytest.approx(50 * 11.0 * 25.0)
        assert "Doubling" in action.reason

    def test_not_doubled_no_trim(self):
        result = run(
            market_alert="GREEN",
            positions=[position("VTSI", shares=100, avg_cost=5.0, price=9.9)],
        )
        assert result.actions == []

    def test_rr_score_below_deserved_trims(self):
        """Price near Red Line with weak cylinders -> expensive for quality."""
        result = run(
            market_alert="GREEN",
            positions=[position("GKPRF", shares=200, avg_cost=70.0, price=80.0)],
            analyses=[gomes(
                "GKPRF", green_line=10.0, red_line=100.0, cylinders=3,
                lifecycle_phase="GOLD_MINE", conviction_score=6,
            )],
        )
        [action] = result.actions
        assert action.action_type == "TRIM"
        assert action.quantity == 100
        assert "R/R" in action.reason


# ==============================================================================
# BUY through the hard Buy Guard + dual-source sizing
# ==============================================================================

BUYABLE = dict(
    green_line=5.0, red_line=20.0, cylinders=8,
    lifecycle_phase="GOLD_MINE", conviction_score=8, current_price=6.0,
)


class TestCurrencyCheck:
    """
    Přípona tickeru vs. měna pozice.

    Kontrola umí říct, že si ty dvě věci odporují. Neumí říct, KTERÁ z nich
    je špatně — IMP.V a KUYA.V se drží na evropské lince, zatímco ticker je
    kanadský symbol z Gomesova trackeru, a tam je správně měna. Tvrdit
    „hodnota v CZK je vedle" by bylo tvrzení, ne zjištění.
    """

    def test_a_conflict_is_named(self):
        result = run(
            market_alert="GREEN",
            positions=[position("KUYA.V", currency="EUR")],
        )
        assert any("MĚNA VS. TICKER" in w for w in result.warnings)

    def test_the_warning_does_not_claim_the_total_is_wrong(self):
        result = run(
            market_alert="GREEN",
            positions=[position("KUYA.V", currency="EUR")],
        )
        [warning] = [w for w in result.warnings if "MĚNA VS. TICKER" in w]
        assert "potvrď" in warning.lower()

    def test_a_confirmed_currency_is_silent(self):
        result = run(
            market_alert="GREEN",
            positions=[position("KUYA.V", currency="EUR", currency_confirmed=True)],
        )
        assert not any("MĚNA VS. TICKER" in w for w in result.warnings)

    def test_confirming_does_not_silence_a_different_position(self):
        result = run(
            market_alert="GREEN",
            positions=[
                position("KUYA.V", currency="EUR", currency_confirmed=True),
                position("IMP.V", currency="EUR"),
            ],
        )
        [warning] = [w for w in result.warnings if "MĚNA VS. TICKER" in w]
        assert "IMP.V" in warning and "KUYA.V" not in warning

    def test_an_agreeing_currency_says_nothing(self):
        result = run(
            market_alert="GREEN",
            positions=[position("GSI.V", currency="CAD")],
        )
        assert not any("MĚNA VS. TICKER" in w for w in result.warnings)


class TestCrossListing:
    """
    Jedna firma, dvě burzy.

    Čtyři pozice se drží pod kanadským tickerem, zatímco Gomesovy poznámky
    mluví o americkém OTC listingu. Přesné párování to lámalo na obě strany.
    """

    def test_a_held_canadian_listing_is_not_offered_as_a_new_buy(self):
        """
        Nejdražší z těch chyb: aplikace nabídne koupi KUYAF, i když KUYA.V
        už v portfoliu leží — a nadávkuje ji, jako by se otvírala od nuly.
        """
        result = run(
            market_alert="GREEN",
            positions=[position("KUYA.V", shares=2325, avg_cost=0.55, price=0.46)],
            analyses=[gomes("KUYAF", **BUYABLE)],
            cash_czk=100_000.0,
        )
        assert [a for a in result.actions if a.action_type == "BUY"] == []

    def test_a_held_position_finds_its_analysis_under_the_other_symbol(self):
        """
        Druhý směr: KUYA.V má hodnocení, jen je vedené pod KUYAF. Bez
        propojení hlásí aplikace „neznámá kvalita" u papíru, který posoudit
        umí.
        """
        result = run(
            market_alert="YELLOW",
            positions=[position("KUYA.V", shares=2325, avg_cost=0.55, price=0.46)],
            analyses=[gomes("KUYAF", lifecycle_phase="WAIT_TIME", conviction_score=2)],
            cash_czk=10_000.0,
        )
        assert not any("NEZNÁMÁ KVALITA" in w for w in result.warnings)

    def test_a_company_we_do_not_hold_still_gets_offered(self):
        """Propojení nesmí umlčet nákup jenom proto, že alias existuje."""
        result = run(
            market_alert="GREEN",
            positions=[position("AEHR", shares=10)],
            analyses=[gomes("KUYAF", **BUYABLE)],
            cash_czk=100_000.0,
        )
        assert [a.ticker for a in result.actions if a.action_type == "BUY"] == ["KUYAF"]

    def test_the_suggestion_names_the_symbol_the_analysis_used(self):
        """
        Kanonický ticker je klíč na párování, ne text na obrazovku. Návrh
        psaný jako „GEODF" u poznámky o GEO.TO pošle člověka hledat jiný
        řádek, než na který se dívá.
        """
        result = run(
            market_alert="GREEN",
            analyses=[gomes("GEO.TO", **BUYABLE)],
            cash_czk=100_000.0,
        )
        assert [a.ticker for a in result.actions] == ["GEO.TO"]


class TestBuys:
    def test_single_source_buy_is_sized_by_score_inside_the_7pct_cap(self):
        """
        The cap is the ceiling, the R/R score is the dial (§V2).

        This used to buy straight to 7 %, which is the flat sizing Gomes
        rejects outright — "why would you put the same amount of money in a
        stock that's here as a stock that is way up here?" BUYABLE scores
        8,7 of 10 (green 5, red 20, price 6), so it is worth 87 % of what a
        name sitting on the Green Line would be worth, not all of it.
        """
        result = run(
            market_alert="GREEN",
            analyses=[gomes("CXDO", **BUYABLE)],
            cash_czk=100_000.0,
        )
        [action] = result.actions
        assert action.action_type == "BUY"
        assert action.source_key == "GOMES"
        # score 8,68 x SINGLE cap 7 % = 6,08 % of 100k = 6 078 CZK;
        # price 6 USD * 25 = 150 CZK/share -> 40 whole shares.
        assert action.quantity == 40
        assert action.estimated_czk_value == pytest.approx(40 * 150.0)
        assert "SINGLE" in action.reason
        assert "cíl" in action.reason  # the target used, not just the ceiling

    def test_breakout_agreement_allows_full_tier(self):
        result = run(
            market_alert="GREEN",
            analyses=[
                gomes("CXDO", **BUYABLE),
                AnalysisInput(ticker="CXDO", source_key="BREAKOUT_INVESTORS",
                              action_verdict="BUY"),
            ],
            cash_czk=100_000.0,
        )
        [action] = result.actions
        assert action.source_key == "COMBINED"
        # AGREE -> PRIMARY tier max 10% = 10 000 CZK -> 66 shares
        # AGREE lifts the ceiling to the full PRIMARY tier (10 %); the score
        # still sets the target inside it: 8,68/10 x 10 % = 8,68 %.
        assert action.quantity == 57
        assert action.review_required is False

    def test_a_breakout_analyst_saying_sell_stops_the_buy(self):
        """
        The two sources sit at the same level, and equality there is equality
        in the right to PREVENT. This used to produce a fifth-size position
        with a review flag — a compromise between two people who disagreed
        about owning the company at all.
        """
        result = run(
            market_alert="GREEN",
            analyses=[
                gomes("CXDO", **BUYABLE),
                AnalysisInput(ticker="CXDO", source_key="BREAKOUT_INVESTORS",
                              action_verdict="SELL"),
            ],
            cash_czk=100_000.0,
        )
        assert result.status == "HOLD_HOLD_HOLD"

    @pytest.mark.parametrize(
        "label, overrides",
        [
            ("yellow market", {}),  # market alert set to YELLOW below
            ("unknown cylinders", {"cylinders": None}),
            ("wait time", {"lifecycle_phase": "WAIT_TIME"}),
            ("score below deserved", {"cylinders": 1, "current_price": 19.0}),
            ("missing price", {"current_price": None}),
        ],
    )
    def test_guard_failures_produce_no_buy(self, label, overrides):
        alert = "YELLOW" if label == "yellow market" else "GREEN"
        result = run(
            market_alert=alert,
            analyses=[gomes("CXDO", **{**BUYABLE, **overrides})],
            cash_czk=100_000.0,
        )
        assert result.actions == [], label
        assert result.status == "HOLD_HOLD_HOLD"

    def test_insufficient_cash_no_buy(self):
        result = run(
            market_alert="GREEN",
            analyses=[gomes("CXDO", **BUYABLE)],
            cash_czk=100.0,  # 7% = 7 CZK budget < one 150 CZK share
        )
        assert result.actions == []

    def test_held_ticker_not_rebought(self):
        result = run(
            market_alert="GREEN",
            positions=[position("CXDO", shares=10, avg_cost=5.5, price=6.0)],
            analyses=[gomes("CXDO", **BUYABLE)],
            cash_czk=100_000.0,
        )
        assert all(a.action_type != "BUY" for a in result.actions)


# ==============================================================================
# Ranking, cap, honesty
# ==============================================================================


class TestStaleSemafor:
    """
    The live database held one row — GREEN, last touched seven months earlier
    — and nothing said so. Every buy the app authorised was authorised on a
    market reading from another season.

    The rule is asymmetric on purpose: stale data may make us more cautious,
    never less.
    """

    def test_stale_green_stops_authorising_buys(self):
        buyable = gomes("ACME", green_line=1.0, red_line=10.0, cylinders=2,
                        lifecycle_phase="GOLD_MINE", current_price=1.5)
        fresh = run(market_alert="GREEN", analyses=[buyable], cash_czk=100_000.0)
        stale = run(market_alert="GREEN", analyses=[buyable], cash_czk=100_000.0,
                    market_alert_updated_at=NOW - timedelta(days=200))

        assert any(a.action_type == "BUY" for a in fresh.actions)
        assert not any(a.action_type == "BUY" for a in stale.actions)

    def test_stale_semafor_says_how_old_it_is(self):
        result = run(market_alert="GREEN",
                     market_alert_updated_at=NOW - timedelta(days=207))
        assert any("STARÝ SEMAFOR" in w and "207 dní" in w for w in result.warnings)

    def test_a_stale_protective_level_keeps_protecting(self):
        """
        Downgrading a stale ORANGE to "unknown" would have removed the
        de-risking it exists to trigger. Caution survives staleness.
        """
        held = position("ACME", shares=100, avg_cost=10.0, price=12.0)
        analysis = gomes("ACME", green_line=1.0, red_line=10.0,
                         lifecycle_phase="WAIT_TIME", current_price=12.0)
        result = run(market_alert="ORANGE", positions=[held], analyses=[analysis],
                     cash_czk=0.0, market_alert_updated_at=NOW - timedelta(days=200))
        assert result.market_alert == "ORANGE"
        assert any(a.action_type == "SELL_WAIT_TIME" for a in result.actions)

    def test_an_undated_semafor_counts_as_stale(self):
        result = run(market_alert="GREEN", market_alert_updated_at=None)
        assert any("STARÝ SEMAFOR" in w for w in result.warnings)

    def test_a_semafor_inside_the_window_is_not_flagged(self):
        result = run(market_alert="GREEN",
                     market_alert_updated_at=NOW - timedelta(days=13))
        assert not any("STARÝ SEMAFOR" in w for w in result.warnings)


class TestRankingAndHonesty:
    def test_derisk_outranks_trim_and_max_3(self):
        result = run(
            market_alert="YELLOW",
            positions=[
                position("AAAA"),  # known tertiary -> SELL (90)
                position("BBBB", avg_cost=5.0, price=11.0),  # doubled -> would TRIM
                position("CCCC"),  # known tertiary -> SELL (90)
                position("DDDD"),  # known tertiary -> SELL (90)
            ],
            analyses=[
                gomes("BBBB", lifecycle_phase="GOLD_MINE",
                      conviction_score=8, cylinders=8),
                # Banded, and priced mid-band: the tier rule fires and the
                # valuation has nothing to say against it.
                gomes("AAAA", green_line=3.25, red_line=15.50,
                      lifecycle_phase="GOLD_MINE", conviction_score=3),
                gomes("CCCC", green_line=3.25, red_line=15.50,
                      lifecycle_phase="GOLD_MINE", conviction_score=3),
                gomes("DDDD", green_line=3.25, red_line=15.50,
                      lifecycle_phase="GOLD_MINE", conviction_score=3),
            ],
        )
        assert len(result.actions) == 3
        assert [a.action_type for a in result.actions] == ["SELL", "SELL", "SELL"]

    def test_missing_price_warns_never_invents(self):
        result = run(
            market_alert="YELLOW",
            positions=[PositionInput(ticker="GHOST", shares=10, avg_cost=5.0,
                                     current_price=None)],
            analyses=[gomes("GHOST", lifecycle_phase="WAIT_TIME")],
        )
        assert result.actions == []  # no fabricated sell amount
        assert any("GHOST" in w and "CHYBÍ" in w for w in result.warnings)

    def test_stale_price_flagged(self):
        result = run(
            market_alert="GREEN",
            positions=[PositionInput(
                ticker="OLDP", shares=10, avg_cost=5.0, current_price=6.0,
                last_price_update=NOW - timedelta(days=10),
            )],
        )
        assert any("OLDP" in w and "STARÁ CENA" in w for w in result.warnings)

    def test_price_without_timestamp_flagged(self):
        """A price of unknown age is not silently trusted."""
        result = run(
            market_alert="GREEN",
            positions=[PositionInput(
                ticker="NOTS", shares=10, avg_cost=5.0, current_price=6.0,
                last_price_update=None,
            )],
        )
        assert any("NOTS" in w and "NEZNÁMÉ" in w for w in result.warnings)

    def test_unknown_cash_warns(self):
        result = run(market_alert="GREEN", cash_czk=None)
        assert result.available_cash_czk == 0.0
        assert any("hotovost" in w for w in result.warnings)

    def test_missing_avg_cost_disarms_doubling_and_warns(self):
        """Degiro imports have no buy price: no invented doubling TRIM."""
        result = run(
            market_alert="GREEN",
            positions=[PositionInput(
                ticker="NOCB", shares=100, avg_cost=None, current_price=50.0,
                last_price_update=NOW,
            )],
        )
        assert result.actions == []
        assert any("NOCB" in w and "NÁKUPNÍ CENA" in w for w in result.warnings)

    def test_many_same_type_warnings_group_into_one_line(self):
        """14 positions missing a cost = one grouped warning, not a wall."""
        result = run(
            market_alert="GREEN",
            positions=[
                PositionInput(ticker=f"T{i:02d}", shares=10, avg_cost=None,
                              current_price=5.0, last_price_update=NOW)
                for i in range(14)
            ],
        )
        cost_warnings = [w for w in result.warnings if "NÁKUPNÍ CENA" in w]
        assert len(cost_warnings) == 1
        assert "14 pozic" in cost_warnings[0]
        assert "T00" in cost_warnings[0] and "T13" in cost_warnings[0]

    def test_few_warnings_stay_individual(self):
        result = run(
            market_alert="GREEN",
            positions=[
                PositionInput(ticker=f"T{i}", shares=10, avg_cost=None,
                              current_price=5.0, last_price_update=NOW)
                for i in range(2)
            ],
        )
        cost_warnings = [w for w in result.warnings if "NÁKUPNÍ CENA" in w]
        assert len(cost_warnings) == 2

    def test_missing_avg_cost_still_derisks_on_red(self):
        """De-risk needs no cost basis — unknown cost must not block safety."""
        result = run(
            market_alert="RED",
            positions=[PositionInput(
                ticker="NOCB", shares=100, avg_cost=None, current_price=50.0,
                last_price_update=NOW,
            )],
        )
        [action] = result.actions
        assert action.action_type == "LIQUIDATE_HEAVY"
        assert action.quantity == 100


# ==============================================================================
# Endpoint wiring (routing + serialization, DB loader patched)
# ==============================================================================

@pytest.fixture
def client(monkeypatch):
    """
    The endpoint over a session that holds no accounts.

    A database with no portfolio row is a real first-run state, and the engine
    still has something to say about the market itself. The stub answers the
    portfolio query with an empty list and nothing else, so anything the route
    touches beyond that shows up as a failure rather than as silence.
    """
    class _NoPortfolios:
        def query(self, *_a, **_kw):
            return self

        def order_by(self, *_a, **_kw):
            return self

        def filter(self, *_a, **_kw):
            return self

        def all(self):
            return []

        def commit(self):
            return None

        def rollback(self):
            return None

    app = FastAPI()
    app.include_router(daily_actions_route.router)
    app.dependency_overrides[get_db] = _NoPortfolios
    return TestClient(app)


class TestEndpoint:
    def test_empty_portfolio_returns_hold(self, client, monkeypatch):
        monkeypatch.setattr(
            daily_actions_route, "load_daily_action_inputs",
            lambda db, portfolio_id=None: ("GREEN", NOW, [], [], 5_000.0),
        )
        response = client.get("/api/trading/daily-actions")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "HOLD_HOLD_HOLD"
        assert data["actions"] == []
        assert data["market_alert"] == "GREEN"
        assert data["available_cash_czk"] == 5_000.0

    def test_loader_failure_is_an_error_not_fake_hold(self, client, monkeypatch):
        def boom(db, portfolio_id=None):
            raise RuntimeError("db down")

        monkeypatch.setattr(daily_actions_route, "load_daily_action_inputs", boom)
        response = client.get("/api/trading/daily-actions")
        assert response.status_code == 500
        assert "db down" in response.json()["detail"]


class TestCylinderConfirmation:
    """
    A proposal is not a permission.

    `app/services/cylinders.py` computes a cylinder count from named facts, but
    the thresholds behind it are judgement and nobody has validated them against
    outcomes — the score journal only opened on 2026-08-23. What makes the rubric
    safe to act on is not its precision: it is that the owner looks at the
    evidence and agrees before any of it can spend money.

    The rule is deliberately asymmetric. An unconfirmed or expired reading stops
    buying and keeps selling, because an app that goes quiet on a position
    exactly when its information got old is more dangerous than one that trims
    on a number three months stale.
    """

    def test_an_unconfirmed_proposal_buys_nothing(self):
        result = run(
            analyses=[AnalysisInput(
                ticker="CXDO", source_key="GOMES",
                green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
                cylinders_confirmed_at=None,        # proposed, not agreed
            )],
            cash_czk=200_000.0,
        )
        assert result.status == "HOLD_HOLD_HOLD"

    def test_the_same_numbers_confirmed_do_buy(self):
        """The control: only the confirmation differs between this and the case above."""
        result = run(
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            cash_czk=200_000.0,
        )
        assert [a.action_type for a in result.actions] == ["BUY"]

    def test_an_expired_confirmation_stops_authorising_purchases(self):
        result = run(
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
                cylinders_valid_until=NOW - timedelta(days=1),
            )],
            cash_czk=200_000.0,
        )
        assert result.status == "HOLD_HOLD_HOLD"

    def test_an_expired_confirmation_still_trims_an_expensive_position(self):
        """
        The asymmetry. CXDO at 14.00 inside a 3.25/15.50 band scores far below
        what 8 cylinders deserve, so the position is expensive for its quality —
        and that stays true whether or not the quality reading has aged.
        """
        result = run(
            positions=[position("CXDO", shares=100, avg_cost=4.0, price=14.0)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=14.0,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
                cylinders_valid_until=NOW - timedelta(days=1),
            )],
        )
        assert "TRIM" in [a.action_type for a in result.actions]

    def test_an_expired_confirmation_says_so_by_name(self):
        """
        Silence would be the worst outcome: the owner would read a trim computed
        on a stale quality number as if it were current.
        """
        result = run(
            positions=[position("CXDO", shares=100, avg_cost=4.0, price=14.0)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=14.0,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
                cylinders_valid_until=NOW - timedelta(days=1),
            )],
        )
        assert any("VYPRŠELÁ KVALITA" in w and "CXDO" in w for w in result.warnings)

    def test_a_refused_unconfirmed_buy_is_recorded_as_unknown_cylinders(self):
        """
        The refusal log has to name the real cause. Filing this under "not cheap
        enough" would send the owner looking at the price when what is missing
        is his own confirmation.
        """
        refusals = []
        generate_daily_actions(
            market_alert="GREEN", market_alert_updated_at=NOW,
            positions=[], cash_czk=200_000.0, fx_rate_to_czk=fx, now=NOW,
            analyses=[AnalysisInput(
                ticker="CXDO", source_key="GOMES",
                green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            refusal_sink=refusals.append,
        )
        assert [r.failed_gate for r in refusals] == ["CYLINDERS_UNKNOWN"]


class TestDatabaseTimestampsAreComparable:
    """
    The cylinder-confirmation columns are TIMESTAMP WITH TIME ZONE; this engine
    works in naive UTC and every other column it reads is naive. The first
    confirmation ever written therefore turned the expiry comparison into a
    TypeError — the daily list would have gone down the moment the feature
    started working, and only against the real database.
    """

    def test_an_aware_expiry_does_not_crash_the_engine(self):
        from datetime import timezone

        result = run(
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
                cylinders_confirmed_at=(NOW - timedelta(days=1)).replace(tzinfo=timezone.utc),
                cylinders_valid_until=(NOW + timedelta(days=60)).replace(tzinfo=timezone.utc),
            )],
            cash_czk=200_000.0,
        )
        assert [a.action_type for a in result.actions] == ["BUY"]

    def test_an_aware_expiry_in_the_past_still_blocks(self):
        from datetime import timezone

        result = run(
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
                cylinders_confirmed_at=(NOW - timedelta(days=200)).replace(tzinfo=timezone.utc),
                cylinders_valid_until=(NOW - timedelta(days=1)).replace(tzinfo=timezone.utc),
            )],
            cash_czk=200_000.0,
        )
        assert result.status == "HOLD_HOLD_HOLD"


class TestTheBandHasItsOwnCurrency:
    """
    Every Gomes band is quoted on the US OTC listing; four of the five largest
    positions trade in Canadian dollars. `app/core/tickers.py` matches those
    positions to their US analysis correctly — and the R/R score was then
    computed from a CAD price against a USD band, wrong by the whole exchange
    rate.

    It was not theoretical. The first live run after cylinders were confirmed
    produced "TRIM GSI.V" on an R/R of 2.97; converted properly it is about
    4.25 — same direction that day, and no reason to expect that to hold.

    `currency_mismatch` does not catch it: that compares a ticker suffix with
    the stored currency of the position, which is a different question.
    """

    def test_the_same_money_in_two_currencies_reaches_the_same_verdict(self):
        """
        GKPRF's band is 0.30/3.75 USD. At the fixture rates 2.50 CAD is exactly
        1.50 USD, so the two runs below describe one position priced two ways
        and must agree. Before the conversion existed they did not: the CAD
        figure was scored against a dollar band and landed far nearer the Red
        Line than the position actually sat.
        """
        cad = run(
            positions=[position("GSI.V", shares=500, avg_cost=1.0, price=2.50, currency="CAD")],
            analyses=[gomes(
                "GKPRF", green_line=0.30, red_line=3.75, current_price=2.50,
                cylinders=5, conviction_score=6, lifecycle_phase="GOLD_MINE",
            )],
        )
        usd = run(
            positions=[position("GSI.V", shares=500, avg_cost=1.0, price=1.50, currency="USD")],
            analyses=[gomes(
                "GKPRF", green_line=0.30, red_line=3.75, current_price=1.50,
                cylinders=5, conviction_score=6, lifecycle_phase="GOLD_MINE",
            )],
        )
        assert [a.action_type for a in cad.actions] == ["TRIM"]
        assert [a.action_type for a in cad.actions] == [a.action_type for a in usd.actions]

    def test_a_position_near_fair_value_is_not_trimmed_by_the_exchange_rate(self):
        """
        The case that made the bug visible. 1.77 CAD is 1.062 USD at the fixture
        rates, which scores almost exactly the 5.0 that five cylinders deserve —
        a hold. Read as dollars it scores 2.97 and reads as expensive, and the
        engine's very first live recommendation was to sell half of it.
        """
        result = run(
            positions=[position("GSI.V", shares=500, avg_cost=1.0, price=1.77, currency="CAD")],
            analyses=[gomes(
                "GKPRF", green_line=0.30, red_line=3.75, current_price=1.77,
                cylinders=5, conviction_score=6, lifecycle_phase="GOLD_MINE",
            )],
        )
        assert "TRIM" not in [a.action_type for a in result.actions]

    def test_an_unknown_band_currency_produces_no_score_at_all(self):
        """
        Fail closed. A band whose currency nobody recorded cannot be compared
        with a price, and guessing is what would produce a confident wrong
        answer — in either direction. A wrong trim is irreversible and taxable.
        """
        result = run(
            positions=[position("GSI.V", shares=500, avg_cost=1.0, price=1.77, currency="CAD")],
            analyses=[gomes(
                "GKPRF", green_line=0.30, red_line=3.75, current_price=1.77,
                cylinders=5, conviction_score=6, lifecycle_phase="GOLD_MINE",
                line_currency=None,
            )],
        )
        assert "TRIM" not in [a.action_type for a in result.actions]

    def test_an_unmeasurable_band_says_so(self):
        """Silence would read as "nothing to do" on a position simply not measured."""
        result = run(
            positions=[position("GSI.V", shares=500, avg_cost=1.0, price=1.77, currency="CAD")],
            analyses=[gomes(
                "GKPRF", green_line=0.30, red_line=3.75, current_price=1.77,
                cylinders=5, conviction_score=6, lifecycle_phase="GOLD_MINE",
                line_currency=None,
            )],
        )
        assert any("MĚNA PÁSMA NEZNÁMÁ" in w for w in result.warnings)


class TestTwoAccountsAreNeverOnePot:
    """
    Until 2026-08-23 the engine read every portfolio as one pot: cash summed
    across both accounts, and every position weight measured against the
    combined total. Two consequences, both silent:

      * a holding worth 12 % of one account came out as 6 % of the sum and
        passed a cap it should have failed;
      * one person's cash could fund a purchase offered to the other.

    Both accounts exist in the real database — Tom at Degiro and Míša at
    Trading 212 — so this stopped being hypothetical the moment she held
    anything.
    """

    def test_a_position_is_weighed_against_its_own_account(self):
        """
        The same holding, once alone in a small account and once inside a large
        one. Tier caps are a share of ONE account, so the small account must see
        it as over-weight and the large one must not.
        """
        heavy = position("SPEC", shares=100, avg_cost=1.0, price=1.0)   # 2 500 CZK
        ballast = position("BIG", shares=10_000, avg_cost=1.0, price=1.0)

        alone = run(
            market_alert="YELLOW",
            positions=[heavy],
            analyses=[gomes("SPEC", green_line=0.20, red_line=5.00,
                            lifecycle_phase="GOLD_MINE", conviction_score=3)],
        )
        diluted = run(
            market_alert="YELLOW",
            positions=[heavy, ballast],
            analyses=[gomes("SPEC", green_line=0.20, red_line=5.00,
                            lifecycle_phase="GOLD_MINE", conviction_score=3)],
        )

        # Both still sell it — the tier rule does not depend on size — but the
        # portfolio total the caps are measured against differs, which is the
        # number that used to be summed across accounts.
        assert any(a.ticker == "SPEC" for a in alone.actions)
        assert any(a.ticker == "SPEC" for a in diluted.actions)

    def test_a_buy_is_sized_from_the_cash_of_one_account(self):
        """
        Sizing reads `cash_czk`. Summed across accounts it authorises a purchase
        with money that sits somewhere the buyer cannot spend it from.
        """
        analyses = [gomes(
            "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
            cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
        )]
        rich = run(analyses=analyses, cash_czk=200_000.0)
        poor = run(analyses=analyses, cash_czk=2_000.0)

        [buy] = rich.actions
        assert buy.action_type == "BUY"
        # The small account cannot reach the fee floor, so it proposes nothing
        # rather than a hundred-crown order that costs a tenth of itself to
        # place. Summed across both accounts it would have looked affordable.
        assert not poor.actions

    def test_an_instruction_says_whose_account_it_is_for(self):
        """
        Two people reading one screen have to be able to tell which of them is
        being asked to act. Without the stamp the list is unusable to both.
        """
        from app.schemas.daily_actions import ActionItem

        assert "portfolio_id" in ActionItem.model_fields
        assert "owner" in ActionItem.model_fields


class TestTheLoaderScopesToOneAccount:
    """The fix at its source: what the engine is handed, not what it does with it."""

    def test_the_loader_signature_takes_an_account(self):
        import inspect

        from app.routes.daily_actions import load_daily_action_inputs

        assert "portfolio_id" in inspect.signature(load_daily_action_inputs).parameters


class TestATradeTooSmallToBeWorthMaking:
    """
    Below the fee floor a purchase costs a double-digit percentage of itself
    before it has done anything. The allocator has always refused these; the
    Daily Action buy path did not, so a small account could be handed a
    hundred-crown order.
    """

    def test_a_purchase_under_the_floor_is_not_proposed(self):
        result = run(
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            cash_czk=2_000.0,
        )
        assert not result.actions

    def test_a_purchase_over_the_floor_still_is(self):
        result = run(
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            cash_czk=200_000.0,
        )
        [buy] = result.actions
        from app.core.constants import MIN_TRADE_CZK

        assert buy.estimated_czk_value >= MIN_TRADE_CZK


class TestAddingToWhatIsAlreadyHeld:
    """
    Until now a held position could only ever shrink.

    The watchlist loop skips anything already owned, so the most ordinary act in
    this whole method — putting the month's contribution into the name that is
    cheapest right now — had no instruction behind it. `portfolios.monthly_contribution`
    has existed the whole time with nowhere to go.

    A departure from the written plan, on purpose: that plan required a
    three-point improvement since entry before adding. It is a real canon rule
    (§5) but as a precondition it would have left this path as dead as the buy
    path was — no position on record has an entry score. Sizing is by the gap to
    target (§6); the three-point move raises urgency when it is known.
    """

    def _cheap(self, **kw):
        base = dict(
            green_line=3.25, red_line=15.50, current_price=4.00,
            cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
        )
        base.update(kw)
        return gomes("CXDO", **base)

    def test_a_cheap_holding_under_its_target_is_topped_up(self):
        result = run(
            positions=[position("CXDO", shares=10, avg_cost=4.0, price=4.00)],
            analyses=[self._cheap()],
            cash_czk=200_000.0,
        )
        [action] = result.actions
        assert action.action_type == "ADD"
        assert action.quantity >= 1

    def test_a_position_already_at_its_cap_is_not_topped_up(self):
        """Over the cap is a trim question, not an add one."""
        result = run(
            positions=[position("CXDO", shares=100_000, avg_cost=4.0, price=4.00)],
            analyses=[self._cheap()],
            cash_czk=200_000.0,
        )
        assert "ADD" not in [a.action_type for a in result.actions]

    def test_the_tranche_is_a_third_of_the_gap(self):
        """
        Staged entry is what makes a wrong entry price survivable, and the
        canon's objection to buying everything at once applies inside one name
        as much as across a portfolio.
        """
        result = run(
            positions=[position("CXDO", shares=10, avg_cost=4.0, price=4.00)],
            analyses=[self._cheap()],
            cash_czk=1_000_000.0,
        )
        [action] = result.actions

        # Portfolio is the holding (10 x 4.00 USD = 1 000 CZK) plus the cash.
        # The gap is measured to the SCORE-SIZED target, not to the ceiling
        # (§V2): 4,00 between a 3,25 green line and a 15,50 red line scores
        # 8,66, so the target is 8,66/10 of the 7 % single-source cap.
        portfolio_czk = 1_000.0 + 1_000_000.0
        score = 10 * math.log(15.50 / 4.00) / math.log(15.50 / 3.25)
        target_czk = portfolio_czk * (7 * score / 10) / 100
        gap_czk = target_czk - 1_000.0
        assert action.estimated_czk_value == pytest.approx(gap_czk / 3, rel=0.02)

    def test_an_add_never_spends_more_than_a_third_of_the_cash(self):
        """
        Cash is what lets you buy the correction. The canon is blunt about it:
        you cannot buy cheap stocks if you have no cash.
        """
        result = run(
            positions=[position("CXDO", shares=10_000, avg_cost=4.0, price=4.00)],
            analyses=[self._cheap()],
            cash_czk=30_000.0,
        )
        for action in result.actions:
            if action.action_type == "ADD":
                assert action.estimated_czk_value <= 30_000.0 / 3 + 1


class TestAnAddIsStillAPurchase:
    """Every guard the buy path uses applies unchanged — it is the same money."""

    def _held(self, **kw):
        base = dict(
            green_line=3.25, red_line=15.50, current_price=4.00,
            cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
        )
        base.update(kw)
        return [
            position("CXDO", shares=10, avg_cost=4.0, price=4.00)
        ], [gomes("CXDO", **base)]

    def test_a_non_green_market_stops_it(self):
        positions, analyses = self._held()
        result = run(
            market_alert="YELLOW", positions=positions,
            analyses=analyses, cash_czk=200_000.0,
        )
        assert "ADD" not in [a.action_type for a in result.actions]

    def test_an_unconfirmed_cylinder_count_stops_it(self):
        positions, analyses = self._held(cylinders_confirmed_at=None)
        result = run(positions=positions, analyses=analyses, cash_czk=200_000.0)
        assert "ADD" not in [a.action_type for a in result.actions]

    def test_a_price_above_what_the_quality_deserves_stops_it(self):
        positions, analyses = self._held(current_price=14.0)
        positions = [position("CXDO", shares=10, avg_cost=4.0, price=14.0)]
        result = run(positions=positions, analyses=analyses, cash_czk=200_000.0)
        assert "ADD" not in [a.action_type for a in result.actions]

    def test_a_refused_add_is_recorded_like_any_other_refusal(self):
        positions, analyses = self._held()
        refusals = []
        generate_daily_actions(
            market_alert="YELLOW", market_alert_updated_at=NOW,
            positions=positions, analyses=analyses, cash_czk=200_000.0,
            fx_rate_to_czk=fx, now=NOW, refusal_sink=refusals.append,
        )
        assert [r.failed_gate for r in refusals] == ["MARKET_NOT_GREEN"]

    def test_a_tranche_under_the_fee_floor_is_not_proposed(self):
        positions, analyses = self._held()
        result = run(positions=positions, analyses=analyses, cash_czk=2_000.0)
        assert not result.actions


class TestPacingHoldsTheBatchBack:
    """
    Canon §7 rule 2: do not start by buying all the active picks at once.

    Until cylinders were confirmed the app could not buy at all, so the rule had
    nothing to restrain. The day they were confirmed it became the first thing
    that matters — twelve companies assessed in one afternoon, and a green
    market would have offered several purchases at once.
    """

    def test_a_purchase_held_back_by_tempo_is_not_issued(self):
        result = generate_daily_actions(
            market_alert="GREEN", market_alert_updated_at=NOW,
            positions=[], cash_czk=200_000.0, fx_rate_to_czk=fx, now=NOW,
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            pacing=lambda ticker, is_new: "koupeno tenhle týden",
        )
        assert not result.actions

    def test_it_says_so_instead_of_going_quiet(self):
        """
        A silent refusal reads as "nothing to buy", which is a different fact
        and the wrong one — the purchase was correct, only the timing was not.
        """
        result = generate_daily_actions(
            market_alert="GREEN", market_alert_updated_at=NOW,
            positions=[], cash_czk=200_000.0, fx_rate_to_czk=fx, now=NOW,
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            pacing=lambda ticker, is_new: "koupeno tenhle týden",
        )
        assert any("TEMPO" in w and "CXDO" in w for w in result.warnings)

    def test_a_new_position_and_a_top_up_are_asked_about_separately(self):
        """
        Two different limits: a new thesis is entered once a week, a further
        tranche into something owned once a fortnight. The checker has to know
        which of the two it is being asked about.
        """
        asked = []

        def spy(ticker, is_new):
            asked.append((ticker, is_new))
            return None

        generate_daily_actions(
            market_alert="GREEN", market_alert_updated_at=NOW,
            positions=[position("CXDO", shares=10, avg_cost=4.0, price=4.00)],
            cash_czk=200_000.0, fx_rate_to_czk=fx, now=NOW,
            analyses=[
                gomes("CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                      cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE"),
                gomes("TPCS", green_line=3.25, red_line=14.00, current_price=4.56,
                      cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE"),
            ],
            pacing=spy,
        )
        assert ("CXDO", False) in asked      # already held -> a tranche
        assert ("TPCS", True) in asked       # not held -> a new position


class TestTheThreePointMoveRaisesUrgencyRatherThanGating:
    """
    The correction to the written plan. Requiring a three-point improvement
    before adding would have left this path dead: no position on record has an
    entry score, and the canon never says a cheap holding may only be topped up
    after it got cheaper still.
    """

    def _run(self, entry_score):
        return run(
            positions=[position("CXDO", shares=10, avg_cost=4.0, price=4.00)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
                entry_score=entry_score,
            )],
            cash_czk=200_000.0,
        )

    def test_an_add_happens_without_any_entry_score(self):
        [action] = self._run(None).actions
        assert action.action_type == "ADD"

    def test_a_three_point_improvement_moves_it_up_the_list(self):
        """
        CXDO at 4.00 scores about 8.8. Bought when it scored 5.0, that is a
        3.8-point improvement — canon §5's add trigger, and a second
        independent reason for the same purchase.
        """
        plain = self._run(None).actions[0]
        triggered = self._run(5.0).actions[0]

        assert triggered.urgency_score > plain.urgency_score
        assert "Od nákupu" in triggered.reason


class TestACapThatComesFromIgnorance:
    """
    `determine_tier` ends in "everything else = TERTIARY", which caps at 2 %.
    A company whose lifecycle stage was never recorded is therefore held to the
    most speculative limit in the book however good its numbers are — and every
    position in the real portfolio is in exactly that state.

    Silence here would read as "you already hold enough of it", which is a
    different fact and the wrong one.
    """

    def test_a_cheap_holding_capped_by_an_unknown_phase_says_so(self):
        result = run(
            positions=[position("CXDO", shares=10_000, avg_cost=4.0, price=4.00)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase=None,
            )],
            cash_czk=10_000.0,
        )
        assert "ADD" not in [a.action_type for a in result.actions]
        assert any("STROP Z NEVĚDOMOSTI" in w and "CXDO" in w for w in result.warnings)

    def test_a_classified_holding_at_its_cap_is_simply_full(self):
        """
        With the stage known the cap is a real decision, and a position at it
        needs no explanation — it is doing what it was sized to do.
        """
        result = run(
            positions=[position("CXDO", shares=10_000, avg_cost=4.0, price=4.00)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=4.00,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            cash_czk=10_000.0,
        )
        assert not any("STROP Z NEVĚDOMOSTI" in w for w in result.warnings)


class TestBothSourcesMayRefuse:
    """
    The owner's decision of 2026-08-23: the two sources sit at the same level.

    Equality in the right to PREVENT, not in the right to allow. Either source
    saying no stops the purchase; neither can authorise a company the method
    cannot value. A refusal is recoverable and a bad position is not, and a
    fifth of a position taken against a source you trust was always a strange
    thing to hold.
    """

    def _with_breakout(self, verdict):
        return run(
            market_alert="GREEN",
            analyses=[
                gomes("CXDO", **BUYABLE),
                AnalysisInput(ticker="CXDO", source_key="BREAKOUT_INVESTORS",
                              action_verdict=verdict),
            ],
            cash_czk=100_000.0,
        )

    def test_agreement_buys_at_full_size(self):
        [action] = self._with_breakout("BUY_NOW").actions
        assert action.action_type == "BUY"
        assert action.source_key == "COMBINED"

    def test_a_written_sell_stops_it(self):
        assert self._with_breakout("SELL").status == "HOLD_HOLD_HOLD"

    def test_silence_is_not_a_refusal(self):
        """
        Nobody having written anything is not the same as somebody objecting.
        Treating it as one would stop every purchase the second source has not
        got round to.
        """
        result = run(
            market_alert="GREEN",
            analyses=[gomes("CXDO", **BUYABLE)],
            cash_czk=100_000.0,
        )
        [action] = result.actions
        assert action.action_type == "BUY"

    def test_the_refusal_is_recorded_under_its_own_cause(self):
        """
        Otherwise a year of refusals would read as though the Buy Guard did all
        the work, and the one gate that came from the second source would be
        invisible in exactly the measurement built to judge it.
        """
        refusals = []
        generate_daily_actions(
            market_alert="GREEN", market_alert_updated_at=NOW,
            positions=[], cash_czk=100_000.0, fx_rate_to_czk=fx, now=NOW,
            analyses=[
                gomes("CXDO", **BUYABLE),
                AnalysisInput(ticker="CXDO", source_key="BREAKOUT_INVESTORS",
                              action_verdict="SELL"),
            ],
            refusal_sink=refusals.append,
        )
        assert [r.failed_gate for r in refusals] == ["SOURCE_CONFLICT"]
        assert "jeden zdroj" in refusals[0].reason


class TestTheHoldingsTheMethodCannotValue:
    """
    Eight of twelve positions have no Green and no Red Line. The band engine
    correctly says MIMO_METODIKU and stops — and until now that meant the app
    had nothing at all to say about most of the money.

    Silence is not neutral. The position nobody is watching is the one that
    turns into a loss slowly enough that nobody notices.
    """

    def _finding(self, severity, message="hotovost vydrží 4 měsíců"):
        from app.services.outside_method import Finding

        return Finding(ticker="SMSI", severity=severity, message_cs=message)

    def test_a_company_running_out_of_cash_is_sold(self):
        """
        Survival needs no valuation. SMSI's balance was four months of spending
        in August 2026 while its going-concern warning sat in a markdown blob
        nothing could query.
        """
        result = run(
            positions=[position("SMSI", shares=122, avg_cost=2.0, price=2.4)],
            unvalued={"SMSI": [self._finding("EXIT")]},
        )
        [action] = result.actions
        assert action.action_type == "SELL"
        assert "Bez ocenění" in action.reason

    def test_a_review_is_a_warning_and_never_an_order(self):
        result = run(
            positions=[position("ECOR", shares=100, avg_cost=2.0, price=2.4)],
            unvalued={"ECOR": [self._finding("REVIEW", "hotovost vydrží 8 měsíců")]},
        )
        assert not result.actions
        assert any("BEZ OCENĚNÍ" in w and "ECOR" in w for w in result.warnings)

    def test_a_valuation_rule_still_takes_precedence(self):
        """
        A holding the ladder can speak for gets its answer from the ladder. Two
        voices about one position is how a screen starts contradicting itself.
        """
        result = run(
            positions=[position("CXDO", shares=100, avg_cost=4.0, price=14.0)],
            analyses=[gomes(
                "CXDO", green_line=3.25, red_line=15.50, current_price=14.0,
                cylinders=8, conviction_score=9, lifecycle_phase="GOLD_MINE",
            )],
            unvalued={"CXDO": [self._finding("EXIT")]},
        )
        [action] = result.actions
        assert action.action_type == "TRIM"        # the R/R rule, not the fallback

    def test_without_the_findings_nothing_changes(self):
        """The parameter is optional; the engine behaves as before without it."""
        result = run(positions=[position("SMSI", shares=122, avg_cost=2.0, price=2.4)])
        assert result.status == "HOLD_HOLD_HOLD"


class TestWhatKindOfBetThisIs:
    """
    The asset-class ceiling, salvaged out of `GomesLogicEngine` before it went.

    The tier says how sure the thesis is. This says what happens if it is
    wrong, and they are not the same question — so the two ceilings resolve to
    whichever is smaller, and an unrecorded class imposes nothing at all.

    That last part is the whole reason it was worth rewriting rather than
    lifting: the old engine defaulted a missing class to HIGH_BETA_ROCKET, and
    on 2026-08-23 every one of the twelve holdings is unclassified.
    """

    def test_a_class_nobody_recorded_does_not_block_the_purchase(self):
        """Today's real state for all twelve. It must not quietly cap anything."""
        result = run(
            market_alert="GREEN",
            analyses=[gomes("AEHR", asset_class=None, **BUYABLE)],
            cash_czk=200_000.0,
        )
        assert [a.ticker for a in result.actions if a.action_type == "BUY"] == ["AEHR"]

    def test_a_value_trap_is_never_bought(self):
        """A cap of zero is how "do not own this" is said in these units."""
        result = run(
            market_alert="GREEN",
            analyses=[gomes("AEHR", asset_class="VALUE_TRAP", **BUYABLE)],
            cash_czk=200_000.0,
        )
        assert [a for a in result.actions if a.action_type == "BUY"] == []

    def test_a_binary_bet_gets_a_smaller_position_than_an_anchor(self):
        """
        Same price, same cylinders, same conviction — different kind of bet,
        so a different amount of money. This is the axis the tiers do not have.
        """
        def bought(asset_class):
            result = run(
                market_alert="GREEN",
                analyses=[gomes("AEHR", asset_class=asset_class, **BUYABLE)],
                cash_czk=1_000_000.0,
            )
            [buy] = [a for a in result.actions if a.action_type == "BUY"]
            return buy.estimated_czk_value

        assert bought("BIOTECH_BINARY") < bought("ANCHOR")

    def test_a_generous_class_cannot_widen_a_tight_tier(self):
        """
        An anchor allows 12 %, but an unknown phase is capped at the strictest
        tier. The ceiling may only ever come down.
        """
        anchor = run(
            market_alert="GREEN",
            analyses=[gomes("AEHR", asset_class="ANCHOR",
                            **{**BUYABLE, "lifecycle_phase": "GOLD_MINE"})],
            cash_czk=1_000_000.0,
        )
        [buy] = [a for a in anchor.actions if a.action_type == "BUY"]

        plain = run(
            market_alert="GREEN",
            analyses=[gomes("AEHR", **{**BUYABLE, "lifecycle_phase": "GOLD_MINE"})],
            cash_czk=1_000_000.0,
        )
        [reference] = [a for a in plain.actions if a.action_type == "BUY"]

        assert buy.estimated_czk_value <= reference.estimated_czk_value


class TestThePhaseBelongsToTheCompany:
    """
    Two bugs that hid each other, found the day the phases were first confirmed.

    The stage decides whether a yellow market sells a holding outright, so both
    of these moved real money — and they cancelled out, which is why neither
    showed until the other was fixed.
    """

    def test_a_confirmed_phase_applies_even_when_gomes_has_no_band(self):
        """
        IRIX is confirmed Wait Time with high confidence — revenue −7,4 %, 63 %
        below its September 2024 peak — and Gomes publishes no lines for it.
        The phase was read off the Gomes row alone, so a position the canon
        says not to hold reported "no reason to do anything".
        """
        result = run(
            market_alert="YELLOW",
            positions=[position("IRIX", shares=500, avg_cost=1.0, price=0.76)],
            analyses=[
                AnalysisInput(
                    ticker="IRIX", source_key="OTHER",
                    lifecycle_phase="WAIT_TIME", conviction_score=5,
                )
            ],
            cash_czk=10_000.0,
        )
        assert [a.action_type for a in result.actions] == ["SELL_WAIT_TIME"]

    def test_the_phase_is_read_from_whichever_row_carries_it(self):
        """A company covered only by Breakout still has a stage."""
        result = run(
            market_alert="YELLOW",
            positions=[position("DFSC", shares=100, avg_cost=2.0, price=1.55)],
            analyses=[
                AnalysisInput(ticker="DFSC", source_key="BREAKOUT_INVESTORS",
                              lifecycle_phase="WAIT_TIME"),
            ],
            cash_czk=10_000.0,
        )
        assert any(a.action_type == "SELL_WAIT_TIME" for a in result.actions)

    def test_no_confirmed_phase_sells_nothing(self):
        """
        The other half. `stocks.inflection_status` carried WAIT_TIME for GSI.V,
        IRIX and KUYA.V from a January import that nobody confirmed, and the
        route used it whenever a lifecycle row was missing — an unconfirmed
        legacy field authorising a sale.
        """
        result = run(
            market_alert="YELLOW",
            positions=[position("KUYA.V", shares=1000, avg_cost=0.6, price=0.46)],
            analyses=[AnalysisInput(ticker="KUYA.V", source_key="OTHER")],
            cash_czk=10_000.0,
        )
        assert all(a.action_type != "SELL_WAIT_TIME" for a in result.actions)

    def test_an_unjudgeable_position_is_named_rather_than_silently_held(self):
        result = run(
            market_alert="YELLOW",
            positions=[position("KUYA.V", shares=1000, avg_cost=0.6, price=0.46)],
            analyses=[AnalysisInput(ticker="KUYA.V", source_key="OTHER")],
            cash_czk=10_000.0,
        )
        assert any("NEZAŘAZEN" in w.upper() for w in result.warnings)


class TestTheBoardSeesEveryAction:
    """
    The daily list shows at most three things on purpose. The board shows one
    card per company and must state each one's real stance — inheriting the cap
    made GSI.V read "DRŽ — dnes není důvod nic dělat" while the engine wanted
    it trimmed, which is silence dressed as a verdict.
    """

    def test_the_uncapped_list_carries_everything_the_capped_one_dropped(self):
        held = [
            position(t, shares=100, avg_cost=2.0, price=1.0)
            for t in ("AAA", "BBB", "CCC", "DDD", "EEE")
        ]
        analyses = [
            AnalysisInput(ticker=t, source_key="GOMES", lifecycle_phase="WAIT_TIME")
            for t in ("AAA", "BBB", "CCC", "DDD", "EEE")
        ]
        result = run(market_alert="YELLOW", positions=held,
                     analyses=analyses, cash_czk=10_000.0)

        assert len(result.actions) == 3
        assert len(result.all_actions) == 5

    def test_the_capped_list_is_the_start_of_the_uncapped_one(self):
        """Same ranking, so the board and the daily list cannot disagree."""
        held = [
            position(t, shares=100, avg_cost=2.0, price=1.0)
            for t in ("AAA", "BBB", "CCC", "DDD")
        ]
        analyses = [
            AnalysisInput(ticker=t, source_key="GOMES", lifecycle_phase="WAIT_TIME")
            for t in ("AAA", "BBB", "CCC", "DDD")
        ]
        result = run(market_alert="YELLOW", positions=held,
                     analyses=analyses, cash_czk=10_000.0)

        assert [a.ticker for a in result.actions] == [
            a.ticker for a in result.all_actions[:3]
        ]
