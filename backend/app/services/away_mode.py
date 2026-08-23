"""
Away mode — what the app does during the weeks you cannot open it.

The ordinary daily-action path assumes someone is reading it. Away mode assumes
nobody is, and that changes three things about what may be sent:

**1. Only what protects capital travels.**
A buy you miss costs an opportunity. A sell you miss costs money you already
own. While away, BUY actions are never pushed — they wait in the app, where
they will still be there when you come back. This is the canon's own ordering
(§2: capital preservation before opportunity), applied to a channel that has to
choose.

**2. Nothing actionable is built on data older than two days.**
The normal path tolerates three days and warns. Away mode will not: a stale
price cannot become an instruction to sell, because by the time you read it the
number it rests on may be a week old and the position may have moved either
way. A stale window produces one message saying the data are stale — which is
itself worth knowing after a week of silence — and no instruction at all.

**3. One message, not a stream.**
The most urgent thing, plus a count of the rest. A second message goes out only
if something strictly more urgent appears; otherwise the channel stays quiet
for a day. A week away is a handful of messages, not two hundred.

**The tighter stop is the semafor, one notch early.**
This method has no price stop. The green line is where you buy and the red line
is where you sell into strength — a price below the red line is the ordinary
state of a position that has not reached its target, not a breach. An earlier
draft of this module read them the other way round and would have ordered three
holdings sold on the first day away mode was switched on.

So away mode does not invent a stop. It moves the semafor one step toward
defence while nobody is watching — GREEN is treated as YELLOW, YELLOW as
ORANGE — and lets the canon's own blocked-tier rules do the de-risking sooner.
ORANGE is not escalated to RED: "sell almost everything" is not a decision to
take on someone's behalf while they cannot answer. The escalation is ours, not
the canon's, and every message that rests on it says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

#: One step toward defence, applied while nobody is watching. Capped below RED
#: on purpose: liquidating a portfolio is not a decision to take for someone
#: who cannot answer the phone.
ALERT_ESCALATION: Final[dict[str, str]] = {
    "GREEN": "YELLOW",
    "YELLOW": "ORANGE",
    "ORANGE": "ORANGE",
    "RED": "RED",
}

#: Beyond this, a price is too old to instruct a trade on. Deliberately tighter
#: than `daily_actions.STALE_PRICE_AFTER` (3 days): that threshold governs what
#: is shown to someone who can look at it and judge, this one governs what is
#: pushed to someone who cannot.
MAX_ACTIONABLE_AGE: Final[timedelta] = timedelta(days=2)

#: The quiet period between pushes. Broken only by escalation, below.
MIN_PUSH_INTERVAL: Final[timedelta] = timedelta(hours=24)

#: A new action interrupts the quiet period only if it is this much more
#: urgent than the last thing sent. Without the margin, a position drifting
#: between two nearly equal actions would push every cycle.
ESCALATION_MARGIN: Final[int] = 10

#: Action types that may be pushed while away. Everything absent from this set
#: is held — including BUY, deliberately.
PUSHABLE_ACTIONS: Final[frozenset[str]] = frozenset({
    "LIQUIDATE_HEAVY",
    "SELL_WAIT_TIME",
    "SELL",
    "TRIM",
})

#: Above this, an action is worth breaking a stale-data silence for — but only
#: to say "look at the app", never to state a price or a quantity.
URGENT_ENOUGH_TO_MENTION_WHILE_STALE: Final[int] = 90


@dataclass(frozen=True)
class AwayState:
    """Whether away mode is on, and for how long."""

    is_away: bool
    since: datetime | None = None
    until: datetime | None = None

    def active_at(self, now: datetime) -> bool:
        """
        On means on. An `until` in the past turns it off by itself, so a window
        set before a hospital stay does not silence the app for a year.
        """
        if not self.is_away:
            return False
        if self.until is not None and now > self.until:
            return False
        if self.since is not None and now < self.since:
            return False
        return True

    def days_away(self, now: datetime) -> int | None:
        return (now - self.since).days if self.since else None


@dataclass(frozen=True)
class Digest:
    """At most one message, and an account of everything not in it."""

    send: bool
    #: Why this was or was not sent, in Czech. Always set — a digest that
    #: decides to stay quiet still has to be able to say why.
    reason: str
    subject: str | None = None
    body: str | None = None
    #: The urgency of what was sent, so the next cycle can tell whether
    #: something new is worth breaking the quiet period for.
    urgency: int = 0
    #: What was held back, in Czech, one line each. Rendered in the app.
    held: list[str] = field(default_factory=list)


# ==============================================================================
# The tighter stop: the semafor, one notch early
# ==============================================================================

def escalated_alert(market_alert: str | None) -> str | None:
    """
    The semafor away mode de-risks against.

    None stays None. An unknown semafor is a gap the daily engine already warns
    about, and inventing GREEN-therefore-YELLOW out of it would be building an
    instruction on nothing.
    """
    if not market_alert:
        return None
    return ALERT_ESCALATION.get(market_alert.upper(), market_alert.upper())


def escalation_note(market_alert: str | None) -> str | None:
    """The Czech line explaining the escalation, marked as our own rule."""
    escalated = escalated_alert(market_alert)
    if escalated is None or escalated == (market_alert or "").upper():
        return None
    return (
        f"Away mode: semafor {market_alert.upper()} se pro odlehčování bere "
        f"jako {escalated} — o stupeň opatrněji, protože u toho nejsi. "
        f"Je to rozšíření aplikace, ne pravidlo kánonu."
    )


# ==============================================================================
# The digest
# ==============================================================================

def data_age(price_as_of: datetime | None, now: datetime) -> timedelta | None:
    """None means we do not know how old the data are — treated as too old."""
    return None if price_as_of is None else now - price_as_of


def build_digest(
    actions: list,
    *,
    price_as_of: datetime | None,
    now: datetime,
    last_push_at: datetime | None = None,
    last_push_urgency: int = 0,
) -> Digest:
    """
    Decide the single message away mode may send this cycle.

    `actions` are `ActionItem`s from `generate_daily_actions`, already ranked.
    `price_as_of` is the oldest price update behind them — the age of the
    weakest input, not the freshest, because a digest is only as current as its
    stalest number.

    Returns a `Digest` that always explains itself, whether or not it sends.
    """
    held: list[str] = []

    pushable = [a for a in actions if a.action_type in PUSHABLE_ACTIONS]
    withheld = [a for a in actions if a.action_type not in PUSHABLE_ACTIONS]
    for action in withheld:
        held.append(
            f"{action.ticker}: {action.action_type} se v away mode neposílá — "
            f"promeškaný nákup stojí příležitost, promeškaný prodej peníze. "
            f"Čeká v aplikaci."
        )

    age = data_age(price_as_of, now)
    stale = age is None or age > MAX_ACTIONABLE_AGE

    if not pushable:
        return Digest(
            send=False,
            reason="Nic k odeslání — žádná akce, která chrání kapitál.",
            held=held,
        )

    top = pushable[0]

    # A stale window may still say that something is happening, but it may not
    # say what to do about it. The whole point of B7's acceptance criterion is
    # that no message is built on old data passed off as current.
    if stale:
        return _stale_digest(top, pushable, age, held, now, last_push_at)

    if last_push_at is not None:
        quiet_until = last_push_at + MIN_PUSH_INTERVAL
        escalated = top.urgency_score >= last_push_urgency + ESCALATION_MARGIN
        if now < quiet_until and not escalated:
            held.append(
                f"{top.ticker}: {top.action_type} zadrženo — poslední zpráva "
                f"šla před {_hours(now - last_push_at)} a tohle není "
                f"naléhavější."
            )
            return Digest(
                send=False,
                reason=(
                    f"Klid do {quiet_until:%d.%m. %H:%M} — nic naléhavějšího "
                    f"než minule."
                ),
                held=held,
            )

    for action in pushable[1:]:
        held.append(
            f"{action.ticker}: {action.action_type} počká — away mode posílá "
            f"jen jednu věc."
        )

    return Digest(
        send=True,
        reason="Nejnaléhavější akce, data jsou čerstvá.",
        subject=f"Akcion: {top.ticker} — {_action_label(top.action_type)}",
        body=_body(top, pushable, age),
        urgency=top.urgency_score,
        held=held,
    )


def _stale_digest(
    top,
    pushable: list,
    age: timedelta | None,
    held: list[str],
    now: datetime,
    last_push_at: datetime | None,
) -> Digest:
    """A message about the data, never an instruction resting on them."""
    for action in pushable:
        held.append(
            f"{action.ticker}: {action.action_type} neposláno — stojí na "
            f"{_age_words(age)} datech."
        )

    if top.urgency_score < URGENT_ENOUGH_TO_MENTION_WHILE_STALE:
        return Digest(
            send=False,
            reason=(
                f"Data jsou {_age_words(age)} a nic není tak naléhavé, aby "
                f"stálo za zprávu postavenou na nich."
            ),
            held=held,
        )

    # Even this goes out at most once a day.
    if last_push_at is not None and now - last_push_at < MIN_PUSH_INTERVAL:
        return Digest(
            send=False,
            reason="Na stará data se upozorňuje nejvýš jednou denně.",
            held=held,
        )

    return Digest(
        send=True,
        reason="Naléhavá akce, ale na starých datech — posílám jen upozornění.",
        subject="Akcion: podívej se do aplikace",
        body=(
            f"Vypadá to na naléhavou akci u {top.ticker}, ale ceny, na kterých "
            f"stojí, jsou {_age_words(age)}. Konkrétní pokyn ti na nich "
            f"nepošlu — mohl by být týden po termínu.\n\n"
            f"Otevři aplikaci, nech si natáhnout ceny a podívej se na "
            f"{top.ticker}."
        ),
        urgency=top.urgency_score,
        held=held,
    )


def _body(top, pushable: list, age: timedelta | None) -> str:
    lines = [
        top.reason,
        "",
        f"{_action_label(top.action_type)}: {top.quantity:g} ks {top.ticker} "
        f"za {top.current_price:.2f} {top.currency} "
        f"(≈ {top.estimated_czk_value:,.0f} Kč)".replace(",", " "),
        "",
        f"Ceny k dispozici: {_age_words(age)}.",
    ]
    others = len(pushable) - 1
    if others > 0:
        lines.append(
            f"Další {others} akce na ochranu kapitálu čekají v aplikaci — "
            f"away mode posílá jen tu nejnaléhavější."
        )
    lines.append(
        "\nAway mode je zapnutý: nákupy se neposílají a semafor se pro "
        "odlehčování bere o stupeň opatrněji."
    )
    return "\n".join(lines)


def _action_label(action_type: str) -> str:
    return {
        "LIQUIDATE_HEAVY": "Prodej téměř vše",
        "SELL_WAIT_TIME": "Prodej (Wait Time)",
        "SELL": "Prodej",
        "TRIM": "Odeber polovinu",
        "BUY": "Nákup",
    }.get(action_type, action_type)


def _age_words(age: timedelta | None) -> str:
    if age is None:
        return "neznámého stáří"
    hours = age.total_seconds() / 3600
    if hours < 1:
        return "z poslední hodiny"
    if hours < 24:
        return f"{int(hours)} h stará"
    return f"{age.days} dní stará"


def _hours(delta: timedelta) -> str:
    hours = int(delta.total_seconds() / 3600)
    return f"{hours} h" if hours else "chvílí"
