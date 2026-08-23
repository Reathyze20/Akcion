"""
Tests for away mode.

The acceptance criterion in the backlog is precise: a week of the app not
being opened produces at most a handful of messages, and none of them rests on
old data passed off as current. Both halves are testable, and both are here.

The third rule — that a missed buy costs an opportunity while a missed sell
costs money you own — is the one most likely to be "helpfully" relaxed later,
so it gets its own tests too.
"""

from datetime import datetime, timedelta

import pytest

from app.schemas.daily_actions import ActionItem
from app.services.away_mode import (
    ALERT_ESCALATION,
    MAX_ACTIONABLE_AGE,
    MIN_PUSH_INTERVAL,
    AwayState,
    build_digest,
    escalated_alert,
    escalation_note,
)


NOW = datetime(2026, 8, 23, 10, 0)


def action(
    ticker="VTSI",
    action_type="SELL",
    urgency=90,
    quantity=100.0,
    price=4.20,
) -> ActionItem:
    return ActionItem(
        id=f"{ticker}-{action_type}",
        ticker=ticker,
        source_key="GOMES",
        action_type=action_type,
        current_price=price,
        currency="USD",
        quantity=quantity,
        estimated_czk_value=quantity * price * 20.62,
        reason=f"testovací důvod pro {ticker}",
        urgency_score=urgency,
    )


def fresh(hours=2):
    return NOW - timedelta(hours=hours)


# ==============================================================================
# The window
# ==============================================================================

class TestAwayState:
    def test_off_is_off(self):
        assert AwayState(is_away=False).active_at(NOW) is False

    def test_on_with_no_window_stays_on(self):
        assert AwayState(is_away=True).active_at(NOW) is True

    def test_a_window_that_has_passed_turns_itself_off(self):
        """
        A window set before a hospital stay must not silence the app for a year
        because nobody remembered to switch it back.
        """
        state = AwayState(
            is_away=True,
            since=NOW - timedelta(days=30),
            until=NOW - timedelta(days=1),
        )
        assert state.active_at(NOW) is False

    def test_a_window_that_has_not_started_is_not_active(self):
        state = AwayState(is_away=True, since=NOW + timedelta(days=2))
        assert state.active_at(NOW) is False

    def test_days_away_is_none_without_a_start(self):
        assert AwayState(is_away=True).days_away(NOW) is None
        assert AwayState(
            is_away=True, since=NOW - timedelta(days=9)
        ).days_away(NOW) == 9


# ==============================================================================
# The tighter stop is the semafor, one notch early
# ==============================================================================

class TestAlertEscalation:
    """
    An earlier draft of this module invented a price stop five percent above
    the red line. It had the lines backwards: green is where you buy, red is
    where you sell into strength, so a price *below* the red line is the
    ordinary state of a position that has not reached its target. Run against
    the live portfolio it ordered IZEA, VTSI and KUYA.V sold — all three merely
    below their sell targets, one of them 86 % below.

    What replaced it invents nothing: the canon's own blocked-tier table,
    applied to a semafor one step further toward defence.
    """

    def test_green_is_treated_as_yellow(self):
        assert escalated_alert("GREEN") == "YELLOW"

    def test_yellow_is_treated_as_orange(self):
        assert escalated_alert("YELLOW") == "ORANGE"

    def test_orange_is_not_escalated_to_red(self):
        """
        RED means sell almost everything. That is not a decision to take on
        behalf of someone who cannot answer the phone.
        """
        assert escalated_alert("ORANGE") == "ORANGE"

    def test_red_stays_red(self):
        assert escalated_alert("RED") == "RED"

    def test_an_unknown_semafor_is_not_invented_into_one(self):
        """
        The daily engine already warns about a missing semafor. Turning that
        absence into "GREEN, therefore YELLOW" would build an instruction on
        nothing at all.
        """
        assert escalated_alert(None) is None
        assert escalated_alert("") is None

    def test_an_unrecognised_value_passes_through_unchanged(self):
        assert escalated_alert("UNKNOWN") == "UNKNOWN"

    def test_the_note_says_whose_rule_this_is(self):
        note = escalation_note("YELLOW")
        assert "YELLOW" in note and "ORANGE" in note
        assert "rozšíření aplikace" in note
        assert "ne pravidlo kánonu" in note

    def test_no_note_when_nothing_was_escalated(self):
        """Otherwise ORANGE would carry a note claiming a change that did not
        happen."""
        assert escalation_note("ORANGE") is None
        assert escalation_note("RED") is None
        assert escalation_note(None) is None


# ==============================================================================
# A missed buy costs an opportunity; a missed sell costs money you own
# ==============================================================================

class TestOnlyCapitalPreservingActionsTravel:
    def test_a_buy_is_never_pushed(self):
        digest = build_digest(
            [action(action_type="BUY", urgency=60)],
            price_as_of=fresh(), now=NOW,
        )
        assert digest.send is False
        assert "chrání kapitál" in digest.reason

    def test_a_held_buy_is_reported_rather_than_dropped(self):
        digest = build_digest(
            [action(ticker="INFU", action_type="BUY")],
            price_as_of=fresh(), now=NOW,
        )
        assert any("INFU" in line for line in digest.held)

    @pytest.mark.parametrize("kind", [
        "LIQUIDATE_HEAVY", "SELL_WAIT_TIME", "SELL", "TRIM",
    ])
    def test_every_protective_action_may_be_pushed(self, kind):
        digest = build_digest(
            [action(action_type=kind)], price_as_of=fresh(), now=NOW,
        )
        assert digest.send is True


# ==============================================================================
# One message, not a stream
# ==============================================================================

class TestOneMessage:
    def test_only_the_most_urgent_is_sent(self):
        digest = build_digest(
            [
                action(ticker="SMSI", action_type="LIQUIDATE_HEAVY", urgency=100),
                action(ticker="IZEA", action_type="TRIM", urgency=80),
                action(ticker="DAIO", action_type="SELL", urgency=90),
            ],
            price_as_of=fresh(), now=NOW,
        )
        assert digest.send is True
        assert "SMSI" in digest.subject
        assert "IZEA" not in digest.body
        assert len(digest.held) == 2

    def test_the_body_says_how_many_are_waiting(self):
        digest = build_digest(
            [action(ticker="SMSI", urgency=100), action(ticker="IZEA", urgency=80)],
            price_as_of=fresh(), now=NOW,
        )
        assert "Další 1 akce" in digest.body

    def test_a_second_message_waits_a_day(self):
        digest = build_digest(
            [action(urgency=90)],
            price_as_of=fresh(), now=NOW,
            last_push_at=NOW - timedelta(hours=3), last_push_urgency=90,
        )
        assert digest.send is False
        assert "Klid do" in digest.reason

    def test_something_strictly_more_urgent_breaks_the_quiet(self):
        digest = build_digest(
            [action(action_type="LIQUIDATE_HEAVY", urgency=100)],
            price_as_of=fresh(), now=NOW,
            last_push_at=NOW - timedelta(hours=3), last_push_urgency=80,
        )
        assert digest.send is True

    def test_a_marginally_more_urgent_action_does_not(self):
        """
        Without the margin a position drifting between two nearly equal actions
        would push every cycle — exactly the noise away mode exists to stop.
        """
        digest = build_digest(
            [action(urgency=95)],
            price_as_of=fresh(), now=NOW,
            last_push_at=NOW - timedelta(hours=3), last_push_urgency=90,
        )
        assert digest.send is False

    def test_a_week_away_is_a_handful_of_messages(self):
        """
        The backlog's acceptance criterion, run as an arithmetic check: seven
        days of the same standing SELL, checked every thirty minutes.
        """
        sent, last_at, last_urgency = 0, None, 0
        for tick in range(7 * 24 * 2):
            moment = NOW + timedelta(minutes=30 * tick)
            digest = build_digest(
                [action(urgency=90)],
                price_as_of=moment - timedelta(hours=1), now=moment,
                last_push_at=last_at, last_push_urgency=last_urgency,
            )
            if digest.send:
                sent += 1
                last_at, last_urgency = moment, digest.urgency

        assert sent <= 8, f"za týden odešlo {sent} zpráv"
        assert sent >= 7, "a aspoň jednou denně to připomenout má"


# ==============================================================================
# No instruction rests on stale data
# ==============================================================================

class TestStaleDataNeverBecomesAnInstruction:
    def _stale(self):
        return NOW - MAX_ACTIONABLE_AGE - timedelta(hours=1)

    def test_a_stale_urgent_action_sends_a_look_at_the_app_note(self):
        digest = build_digest(
            [action(ticker="SMSI", action_type="LIQUIDATE_HEAVY", urgency=100)],
            price_as_of=self._stale(), now=NOW,
        )
        assert digest.send is True
        assert "Otevři aplikaci" in digest.body

    def test_and_that_note_carries_no_price_or_quantity(self):
        """
        The failure this prevents: a sell order priced off a number that was
        already three days old when it was sent, read a week later.
        """
        digest = build_digest(
            [action(ticker="SMSI", action_type="LIQUIDATE_HEAVY",
                    urgency=100, quantity=1234.0, price=9.99)],
            price_as_of=self._stale(), now=NOW,
        )
        assert "1234" not in digest.body
        assert "9.99" not in digest.body
        assert "Kč" not in digest.body

    def test_the_age_of_the_data_is_stated(self):
        digest = build_digest(
            [action(action_type="LIQUIDATE_HEAVY", urgency=100)],
            price_as_of=NOW - timedelta(days=5), now=NOW,
        )
        assert "5 dní stará" in digest.body

    def test_a_merely_ordinary_action_on_stale_data_says_nothing_at_all(self):
        digest = build_digest(
            [action(action_type="TRIM", urgency=80)],
            price_as_of=self._stale(), now=NOW,
        )
        assert digest.send is False
        assert digest.held

    def test_unknown_data_age_is_treated_as_stale(self):
        """`None` is not "fresh enough" — it is "we do not know"."""
        digest = build_digest(
            [action(action_type="TRIM", urgency=80)],
            price_as_of=None, now=NOW,
        )
        assert digest.send is False

    def test_a_fresh_instruction_does_carry_the_numbers(self):
        digest = build_digest(
            [action(ticker="VTSI", quantity=100.0, price=4.20)],
            price_as_of=fresh(), now=NOW,
        )
        assert "100 ks VTSI" in digest.body
        assert "4.20" in digest.body

    def test_the_stale_notice_is_also_capped_at_one_a_day(self):
        digest = build_digest(
            [action(action_type="LIQUIDATE_HEAVY", urgency=100)],
            price_as_of=self._stale(), now=NOW,
            last_push_at=NOW - timedelta(hours=2), last_push_urgency=100,
        )
        assert digest.send is False


# ==============================================================================
# Nothing decides silently
# ==============================================================================

class TestEveryDigestExplainsItself:
    @pytest.mark.parametrize("actions,as_of", [
        ([], fresh()),
        ([action(action_type="BUY")], fresh()),
        ([action()], None),
        ([action()], fresh()),
    ])
    def test_a_digest_always_says_why(self, actions, as_of):
        digest = build_digest(actions, price_as_of=as_of, now=NOW)
        assert digest.reason

    def test_the_body_declares_that_away_mode_is_on(self):
        """
        Otherwise the absence of buy suggestions reads as "nothing to buy"
        rather than "away mode does not send those".
        """
        digest = build_digest([action()], price_as_of=fresh(), now=NOW)
        assert "Away mode je zapnutý" in digest.body
        assert "o stupeň opatrněji" in digest.body

    def test_the_quiet_period_is_a_day(self):
        assert MIN_PUSH_INTERVAL == timedelta(hours=24)

    def test_away_mode_is_stricter_about_age_than_the_daily_path(self):
        from app.services.daily_actions import STALE_PRICE_AFTER

        assert MAX_ACTIONABLE_AGE < STALE_PRICE_AFTER


# ==============================================================================
# The escalation has to reach the engine, not just exist
# ==============================================================================

class TestEscalationChangesTheOutcome:
    """
    Escalating the semafor is only worth anything if the canon's blocked-tier
    rules then fire on it. This drives `generate_daily_actions` twice with the
    same portfolio and only the semafor differing.
    """

    def _run(self, alert, *, phase, conviction):
        from app.services.daily_actions import (
            AnalysisInput,
            PositionInput,
            generate_daily_actions,
        )

        return generate_daily_actions(
            market_alert=alert,
            market_alert_updated_at=NOW - timedelta(days=1),
            positions=[PositionInput(
                ticker="SPEC",
                shares=100.0,
                avg_cost=5.0,
                currency="USD",
                current_price=6.0,
                last_price_update=NOW - timedelta(hours=2),
            )],
            analyses=[AnalysisInput(
                ticker="SPEC",
                source_key="GOMES",
                green_line=4.0,
                red_line=12.0,
                cylinders=4,
                lifecycle_phase=phase,
                conviction_score=conviction,
                current_price=6.0,
            )],
            cash_czk=10_000.0,
            fx_rate_to_czk=lambda code: 20.62,
            now=NOW,
        )

    def _sells(self, alert, *, phase="GOLD_MINE", conviction=5):
        return [
            a for a in self._run(alert, phase=phase, conviction=conviction).actions
            if a.action_type == "SELL"
        ]

    def test_a_tertiary_position_survives_green(self):
        assert not self._sells("GREEN")

    def test_and_is_sold_once_green_is_read_as_yellow(self):
        """
        The whole mechanism in one assertion: away mode hands the escalated
        semafor to the unchanged engine, and a tier YELLOW blocks is sold.
        """
        assert self._sells(escalated_alert("GREEN"))

    def test_a_secondary_position_survives_yellow(self):
        assert not self._sells("YELLOW", phase="GREAT_FIND", conviction=40)

    def test_and_is_sold_once_yellow_is_read_as_orange(self):
        """The second step matters too — ORANGE blocks SECONDARY, YELLOW does not."""
        assert self._sells(
            escalated_alert("YELLOW"), phase="GREAT_FIND", conviction=40,
        )

    def test_the_engine_never_sees_a_semafor_we_made_up(self):
        """
        Escalation only ever maps one real level to another real level. A
        semafor the engine does not recognise would be rejected, and a
        fabricated one would be worse.
        """
        from app.trading.gomes_logic import MarketAlert

        for source, target in ALERT_ESCALATION.items():
            assert MarketAlert(source)
            assert MarketAlert(target)


# ==============================================================================
# Silence has to be legible
# ==============================================================================

class TestBlindSpots:
    """
    Away mode being quiet because nothing needs doing and away mode being quiet
    because it could not read a single holding produce the same empty inbox.
    Found on the live portfolio 2026-08-23: all fifteen positions lack a phase
    and a conviction score, so the de-risking rules cannot fire on any of them,
    and away mode has nothing it is allowed to say.
    """

    def _spots(self, warnings):
        from app.routes.away import _blind_spots

        return _blind_spots(warnings)

    def test_the_reason_nothing_can_be_judged_outranks_a_missing_cost_basis(self):
        """
        An unranked list truncated to three showed three missing purchase
        prices and dropped the one warning that explains the silence.
        """
        spots = self._spots([
            "⚠️ CHYBÍ NÁKUPNÍ CENA: AAA",
            "⚠️ CHYBÍ NÁKUPNÍ CENA: BBB",
            "⚠️ CHYBÍ NÁKUPNÍ CENA: CCC",
            "⚠️ NEZNÁMÁ KVALITA u 15 pozic — chybí fáze i konvikční skóre",
        ])
        assert "NEZNÁMÁ KVALITA" in spots[0]

    def test_at_most_three_survive(self):
        from app.routes.away import MAX_BLIND_SPOTS

        assert len(self._spots([f"⚠️ CHYBÍ {i}" for i in range(10)])) == MAX_BLIND_SPOTS

    def test_an_ordinary_warning_is_not_a_blind_spot(self):
        """A behaviour brake explains nothing about why away mode is quiet."""
        assert self._spots(["Prodal jsi se ztrátou před dvěma dny"]) == []

    def test_no_warnings_means_no_notes(self):
        assert self._spots([]) == []
