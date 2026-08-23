"""
Daily Action engine + endpoint tests (Phase 3 of the roadmap).

Locks Path 1 of EFFICIENT_INVESTING_PLAYBOOK.md: max 3 ranked actions with
exact CZK amounts, "Nic. Drž." (HOLD_HOLD_HOLD) as the first-class rest state,
de-risking ranked above profit-taking above buying, and missing data surfacing
as warnings instead of invented numbers.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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

RATES = {"USD": 25.0, "CZK": 1.0, "EUR": 25.0}


def fx(currency: str) -> float:
    return RATES[currency.upper()]


def run(
    market_alert="GREEN",
    positions=(),
    analyses=(),
    cash_czk=0.0,
    market_alert_updated_at=NOW,
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
    )


def gomes(ticker, **kw) -> AnalysisInput:
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
        assert any("NEZNÁMÁ KVALITA" in w and "XXXX" in w for w in result.warnings)

    def test_yellow_still_sells_a_tertiary_it_actually_knows_about(self):
        """The rule itself is intact — it just needs evidence to fire."""
        result = run(
            market_alert="YELLOW",
            positions=[position("XXXX")],
            analyses=[gomes("XXXX", lifecycle_phase="GOLD_MINE", conviction_score=3)],
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


class TestBuys:
    def test_single_source_buy_sized_at_7pct(self):
        result = run(
            market_alert="GREEN",
            analyses=[gomes("CXDO", **BUYABLE)],
            cash_czk=100_000.0,
        )
        [action] = result.actions
        assert action.action_type == "BUY"
        assert action.source_key == "GOMES"
        # SINGLE cap 7% of 100k = 7000 CZK; price 6 USD * 25 = 150 CZK/share
        assert action.quantity == 46
        assert action.estimated_czk_value == pytest.approx(46 * 150.0)
        assert "SINGLE" in action.reason

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
        assert action.quantity == 66
        assert action.review_required is False

    def test_breakout_conflict_caps_and_flags_review(self):
        result = run(
            market_alert="GREEN",
            analyses=[
                gomes("CXDO", **BUYABLE),
                AnalysisInput(ticker="CXDO", source_key="BREAKOUT_INVESTORS",
                              action_verdict="SELL"),
            ],
            cash_czk=100_000.0,
        )
        [action] = result.actions
        assert action.review_required is True
        assert "REVIEW_REQUIRED" in action.reason
        # CONFLICT cap 5% = 5000 CZK -> 33 shares
        assert action.quantity == 33

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
                gomes("AAAA", lifecycle_phase="GOLD_MINE", conviction_score=3),
                gomes("CCCC", lifecycle_phase="GOLD_MINE", conviction_score=3),
                gomes("DDDD", lifecycle_phase="GOLD_MINE", conviction_score=3),
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
    app = FastAPI()
    app.include_router(daily_actions_route.router)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


class TestEndpoint:
    def test_empty_portfolio_returns_hold(self, client, monkeypatch):
        monkeypatch.setattr(
            daily_actions_route, "load_daily_action_inputs",
            lambda db: ("GREEN", NOW, [], [], 5_000.0),
        )
        response = client.get("/api/trading/daily-actions")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "HOLD_HOLD_HOLD"
        assert data["actions"] == []
        assert data["market_alert"] == "GREEN"
        assert data["available_cash_czk"] == 5_000.0

    def test_loader_failure_is_an_error_not_fake_hold(self, client, monkeypatch):
        def boom(db):
            raise RuntimeError("db down")

        monkeypatch.setattr(daily_actions_route, "load_daily_action_inputs", boom)
        response = client.get("/api/trading/daily-actions")
        assert response.status_code == 500
        assert "db down" in response.json()["detail"]
