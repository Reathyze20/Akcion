"""
One card per company, answering "co s tímhle" for two people at once.

What this is for
----------------
    „Budu já a moje přítelkyně vědět, kdy do čeho investovat, co kdy prodat.
     Abychom prostě věděli."

Everything the app computes already exists in pieces: the band and its two limit
prices in `ladder_view`, the per-account instruction in `daily_actions`, the
second opinion in `breakout_band`. Each piece has its own endpoint and its own
screen, so answering "what do we do about CXDO" means reading three of them and
doing the joining in your head.

This does the joining once, on the server, and hands back one card:

    CXDO · Crexendo
    Pásmo      NÁKUP        R/R 6,1 proti zaslouženým 4,0
    Gomes      kupovat do 6,90 $ · držet · odebírat od 11,40 $
    Breakout   souhlasí — jejich cíl 14,00 $ (5 podpisů)
      Tomáš    KOUPIT 180 ks limitem 6,90 $ ≈ 28 400 Kč · platí do 6. 9.
      Míša     DRŽ — má 11 % účtu, strop je 10 %

Why the owners are rows inside one card
---------------------------------------
The band is a fact about the company and is computed once. What either person
should DO depends on their own cost basis, weight and cash, so it is computed
once per account and never against the sum — two accounts summed into one that
nobody holds was a live bug, and it mis-sized the caps for both.

Putting the two instructions under one band is also the only way the screen can
show them differing without looking broken. The same stock genuinely produces
"prodej půlku" for the person who is up 120 % and "drž" for the person who is up
10 %, and that is the method working rather than a contradiction.

Silence is a state, not an absence
----------------------------------
An owner with no action gets a row saying so. A blank where an instruction
should be reads as "the app has not looked at this", which for someone opening
the screen after three weeks away is the one impression that must never be
wrong.
"""

from __future__ import annotations

from app.core.czech import n as cz

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from loguru import logger
from sqlalchemy.orm import Session

from app.core.tickers import canonical_ticker
from app.models.portfolio import Portfolio, Position
from app.services.breakout_band import BreakoutView, compare_to_gomes, headroom_to_target
from app.services.breakout_lookup import breakout_views
from app.services.daily_actions import UNVALUED_MARKER, convert_price
from app.services.ladder_view import LadderRow, portfolio_ladder
from app.services.margin_of_safety_lookup import safety_readings
from app.trading.gomes_logic import Band

#: How the two sources line up on one company. Deliberately coarse: the screen
#: has room for one word, and a finer scale would imply a precision the inputs
#: do not have.
AGREE = "SOUHLASI"
DISAGREE = "NESOUHLASI"
SILENT = "MLCI"

#: A Breakout target within this of today's price is neither agreement nor
#: dissent — it is them saying the price is about right.
FAIR_VALUE_BAND_PCT = 10.0

#: Bands that mean the app has no valuation at all, so no hold/sell rule could
#: run. Kept apart from a real verdict: not looking is not the same as looking
#: and finding nothing.
_UNVALUED_BANDS = {Band.MIMO_METODIKU.value, Band.NEZNAME.value}

#: Bands in which the app would buy, used only to decide whether Breakout's
#: view counts as confirming or contradicting.
_CHEAP_BANDS = {Band.POD_ZELENOU, Band.NAKUP}
_EXPENSIVE_BANDS = {Band.PREPLACENO, Band.NAD_CERVENOU}


@dataclass
class OwnerLine:
    """What one person should do about one company, and why."""

    owner: str
    portfolio_id: int
    #: KOUPIT / PRODAT / ODEBRAT / DRŽ / NEMÁ — already in Czech, because this
    #: string is read by somebody who does not know the enum.
    instruction_cs: str
    detail_cs: str
    action_type: str | None = None
    quantity: int | None = None
    limit_price: float | None = None
    limit_currency: str | None = None
    estimated_czk: float | None = None
    valid_until: datetime | None = None
    urgency: int = 0
    #: Their weight in their own account, never in the sum of both.
    weight_pct: float | None = None
    holds: bool = False


@dataclass
class BreakoutLine:
    """The second source's position on one company, in one sentence."""

    stance: str  # AGREE | DISAGREE | SILENT
    summary_cs: str
    target: float | None = None
    endorsements: int = 0
    #: Set only when a named analyst wrote something, never from the feed.
    analyst: str | None = None
    verdict: str | None = None
    notes_cs: list[str] = field(default_factory=list)


@dataclass
class SafetyLine:
    """
    How far the price can fall before something real stops it.

    The one reading on the card that measures downward. Everything else — the
    band, the R/R score, Breakout's target — counts the distance to a ceiling.
    """

    floor: float | None = None
    #: TANGIBLE_BOOK is worth more than NET_CASH and the card says which.
    layer: str = "NONE"
    downside_pct: float | None = None
    upside_pct: float | None = None
    asymmetry: float | None = None
    below_floor: bool = False
    notes_cs: list[str] = field(default_factory=list)


@dataclass
class BoardCard:
    """One company, everything both people need, in reading order."""

    ticker: str
    company_name: str | None
    band: str
    band_label_cs: str
    band_reason_cs: str
    rr_score: float | None = None
    deserved: float | None = None
    buy_below: float | None = None
    sell_above: float | None = None
    take_profit_above: float | None = None
    add_below: float | None = None
    line_currency: str | None = None
    trigger: str = "ZADNY"
    trigger_reason: str = ""
    quality_expired: bool = False
    breakout: BreakoutLine | None = None
    #: The downside, from the balance sheet. None when no floor is computable —
    #: which is not the same as no downside, and the note says so.
    safety: SafetyLine | None = None
    #: What the app can say about THIS company — short cash, a deep drawdown,
    #: a weight nobody can justify. Kept on the card rather than in a block
    #: above twelve of them, where each line duplicated its own card.
    notes_cs: list[str] = field(default_factory=list)
    owners: list[OwnerLine] = field(default_factory=list)
    #: Sorts the board: whatever needs doing today, first.
    urgency: int = 0


#: Czech names for the bands. The screen never shows a raw enum.
BAND_LABELS_CS: dict[str, str] = {
    "POD_ZELENOU": "POD ZELENOU",
    "NAKUP": "NÁKUP",
    "DRZET": "DRŽET",
    "PREPLACENO": "PŘEPLACENO",
    "NAD_CERVENOU": "NAD ČERVENOU",
    "NEZNAME": "NEZNÁMÉ",
    "MIMO_METODIKU": "MIMO METODIKU",
}

#: Action type to the word a person reads. `daily_actions` speaks in enums.
_INSTRUCTION_CS: dict[str, str] = {
    # Not a verb, because the app has not decided and must not look as if it
    # had. The card's own band line and the reason underneath carry both sides.
    "ROZPOR": "ROZHODNI TY",
    "BUY": "KOUPIT",
    "ADD": "PŘIKOUPIT",
    "TRIM": "ODEBRAT",
    "SELL": "PRODAT",
    "SELL_WAIT_TIME": "PRODAT",
    "LIQUIDATE_HEAVY": "PRODAT VŠE",
}


def build_board(
    db: Session,
    *,
    fx_rate_to_czk: Callable[[str], float],
    actions_for_portfolio: Callable[[Session, Portfolio], object],
    now: datetime | None = None,
) -> tuple[list[BoardCard], list[str]]:
    """
    Every company either person holds, as one card each, most urgent first.

    Returns the cards and the warnings that belong to the PORTFOLIO rather
    than to any one company. The split matters: a per-ticker line shown above
    twelve cards is a wall, and it repeats what its own card already says.

    `actions_for_portfolio` is injected rather than imported so this composes
    the daily engine without depending on the route that currently owns it.
    """
    moment = now or datetime.utcnow()

    ladder = portfolio_ladder(db, fx_rate_to_czk=fx_rate_to_czk, now=moment)
    views = breakout_views(db)
    portfolios = db.query(Portfolio).all()

    # One engine run per account. Never over the sum: a position that is 12 % of
    # her account is 6 % of the total, and would pass a cap it was meant to fail.
    actions_by_owner: dict[int, list] = {}
    actions_by_owner_results: list = []
    for portfolio in portfolios:
        try:
            result = actions_for_portfolio(db, portfolio)
            # Uncapped: the daily list shows three, the board shows every
            # company, and reading the capped list made a company the
            # engine wanted trimmed report "no reason to do anything".
            actions_by_owner[portfolio.id] = list(
                getattr(result, "all_actions", None)
                or getattr(result, "actions", [])
            )
            actions_by_owner_results.append(result)
        except Exception:  # noqa: BLE001 — one broken account, not a blank board
            logger.exception("Pokyny pro portfolio {} se nepodařilo spočítat", portfolio.id)
            actions_by_owner[portfolio.id] = []

    positions = db.query(Position).filter(Position.shares_count > 0).all()

    # The downside floor, keyed by company. The ceiling handed in is the Gomes
    # Red Line already on the ladder — taken as given rather than recomputed,
    # so the two halves of the asymmetry cannot drift apart.
    # Carried WITH its currency. The Red Line is quoted on the US listing and
    # `IMP.V` is priced in euros; handing the raw number over produced an
    # upside of 1 513 %, which is the exchange rate wearing a percentage sign.
    ceilings = {
        canonical_ticker(r.ticker) or r.ticker.upper(): (r.red_line, r.line_currency)
        for r in ladder
        if r.red_line
    }
    safety = safety_readings(db, positions, ceilings)

    portfolio_warnings, notes_by_ticker = _split_warnings(
        _all_warnings(actions_by_owner_results)
    )

    cards: list[BoardCard] = []
    for row in ladder:
        try:
            card = _card_for(
                row, views, portfolios, actions_by_owner, positions, fx_rate_to_czk
            )
            card.notes_cs = notes_by_ticker.get(
                canonical_ticker(row.ticker) or row.ticker.upper(), []
            )
            card.safety = _safety_line(
                safety.get(canonical_ticker(row.ticker) or row.ticker.upper())
            )
            cards.append(card)
        except Exception:  # noqa: BLE001
            logger.exception("Karta pro {} se nepodařilo sestavit", row.ticker)

    cards.sort(key=lambda c: (-c.urgency, c.ticker))
    return cards, portfolio_warnings


def _card_for(
    row: LadderRow,
    views: dict[str, BreakoutView],
    portfolios: list[Portfolio],
    actions_by_owner: dict[int, list],
    positions: list[Position],
    fx_rate_to_czk: Callable[[str], float],
) -> BoardCard:
    key = canonical_ticker(row.ticker) or row.ticker.upper()
    reading = row.reading
    band_value = reading.band.value if hasattr(reading.band, "value") else str(reading.band)

    card = BoardCard(
        ticker=row.ticker,
        company_name=row.company_name,
        band=band_value,
        band_label_cs=BAND_LABELS_CS.get(band_value, band_value),
        band_reason_cs=reading.reason_cs,
        rr_score=reading.rr_score,
        deserved=reading.deserved,
        buy_below=reading.buy_below,
        sell_above=reading.sell_above,
        take_profit_above=reading.take_profit_above,
        add_below=reading.add_below,
        line_currency=row.line_currency,
        trigger=row.trigger.value if hasattr(row.trigger, "value") else str(row.trigger),
        trigger_reason=row.trigger_reason,
        quality_expired=row.quality_expired,
    )

    card.breakout = _breakout_line(
        views.get(key), reading, row.red_line, positions, key, fx_rate_to_czk
    )
    card.owners = _owner_lines(
        key, portfolios, actions_by_owner, positions, band=band_value
    )
    card.urgency = max((o.urgency for o in card.owners), default=0)
    return card



def _safety_line(reading) -> SafetyLine | None:
    """The downside reading, flattened for the screen. None when there is none."""
    if reading is None:
        return None
    support = reading.support
    return SafetyLine(
        floor=support.floor_per_share if support and support.known else None,
        layer=support.layer if support else "NONE",
        downside_pct=reading.downside_pct,
        upside_pct=reading.upside_pct,
        asymmetry=reading.asymmetry,
        below_floor=reading.below_its_floor,
        notes_cs=reading.notes_cs(),
    )


def _breakout_line(
    view: BreakoutView | None,
    reading,
    gomes_red: float | None,
    positions: list[Position],
    key: str,
    fx_rate_to_czk: Callable[[str], float],
) -> BreakoutLine | None:
    """
    Whether the other source confirms or contradicts, in one sentence.

    Their target alone is not a band, so "agreement" here is coarser than the
    dual-source matrix the buy path uses: it asks only whether they see the
    same direction. That is honest about what a target without a floor can say,
    and it is what somebody reading the card actually wants to know.

    A named analyst's verdict outranks the arithmetic. A person writing "sell"
    is a stance; a ratio pointing downward is a calculation.
    """
    if view is None:
        return None

    stance = SILENT
    parts: list[str] = []

    if view.verdict_is_bearish:
        stance = DISAGREE
        parts.append(f"{view.attributed_to} napsal „{view.action_verdict}“")
    elif view.verdict_is_bullish:
        parts.append(f"{view.attributed_to} napsal „{view.action_verdict}“")
        stance = AGREE

    headroom = None
    if view.red_line is not None:
        pos = next((p for p in positions if canonical_ticker(p.ticker) == key), None)
        if pos is not None:
            def convert(price: float, frm: str, to: str) -> float | None:
                return convert_price(price, frm, to, fx_rate_to_czk)

            headroom, warning = headroom_to_target(
                view, float(pos.current_price or 0) or None,
                (pos.currency or "").upper() or None, convert,
            )
            if warning:
                parts.append(warning)

    if headroom is not None:
        if headroom > FAIR_VALUE_BAND_PCT:
            parts.append(
                f"jejich cíl {cz(view.red_line, 2)} USD je {cz(headroom, 0)} % nad cenou"
            )
        elif headroom < -FAIR_VALUE_BAND_PCT:
            parts.append(
                f"jejich cíl {cz(view.red_line, 2)} USD leží {cz(abs(headroom), 0)} % "
                f"POD dnešní cenou"
            )
        else:
            parts.append(f"cíl {cz(view.red_line, 2)} USD je zhruba na dnešní ceně")

        # Do the two sources point the same way? Only asked when the analyst
        # has not already answered it in words — a person's verdict outranks
        # arithmetic over a ratio.
        if stance == SILENT:
            stance = _directional_stance(headroom, reading.band)

    gomes_note = compare_to_gomes(view, gomes_red)
    if gomes_note:
        parts.append(gomes_note)

    if not parts:
        parts.append("nic k téhle firmě neřekli")

    return BreakoutLine(
        stance=stance,
        summary_cs=" · ".join(parts),
        target=view.red_line,
        endorsements=view.endorsements,
        analyst=view.attributed_to,
        verdict=view.action_verdict,
        notes_cs=list(view.notes_cs),
    )


def _directional_stance(headroom_pct: float, band) -> str:
    """
    Do the two sources point the same way about this company?

    A coarse question deliberately, because their input is coarse: a target with
    no floor can say "there is room" or "there is not", and nothing finer.

    The case that matters is the mixed one. Breakout seeing 57 % of upside on a
    company Gomes calls PŘEPLACENO is not silence — it is the two of them
    disagreeing, and reading it as silence would let the screen show a
    contradiction as consensus. The band earns the benefit of the doubt on a
    purchase either way, because only Gomes has a real valuation; this only
    decides which word the card prints.
    """
    if band not in _CHEAP_BANDS and band not in _EXPENSIVE_BANDS:
        # MIMO METODIKU, NEZNÁMÉ — there is no Gomes direction to agree with.
        return SILENT

    breakout_sees_upside = headroom_pct > FAIR_VALUE_BAND_PCT
    breakout_sees_downside = headroom_pct < -FAIR_VALUE_BAND_PCT
    if not (breakout_sees_upside or breakout_sees_downside):
        return SILENT

    gomes_says_cheap = band in _CHEAP_BANDS
    return AGREE if breakout_sees_upside == gomes_says_cheap else DISAGREE


def _owner_lines(
    key: str,
    portfolios: list[Portfolio],
    actions_by_owner: dict[int, list],
    positions: list[Position],
    *,
    band: str | None = None,
) -> list[OwnerLine]:
    """
    One row per account, whether or not there is anything to do.

    An owner with no instruction still gets a row. A blank reads as "the app has
    not looked", and for somebody opening the screen after three weeks away that
    is the one impression that must never be wrong.
    """
    lines: list[OwnerLine] = []

    for portfolio in portfolios:
        held = [
            p for p in positions
            if p.portfolio_id == portfolio.id and canonical_ticker(p.ticker) == key
        ]
        action = next(
            (
                a for a in actions_by_owner.get(portfolio.id, [])
                if canonical_ticker(a.ticker) == key
            ),
            None,
        )
        owner = portfolio.owner or portfolio.name or f"Účet {portfolio.id}"

        if action is not None:
            lines.append(
                OwnerLine(
                    owner=owner,
                    portfolio_id=portfolio.id,
                    instruction_cs=_INSTRUCTION_CS.get(action.action_type, action.action_type),
                    detail_cs=action.reason,
                    action_type=action.action_type,
                    quantity=action.quantity,
                    limit_price=action.limit_price,
                    limit_currency=action.limit_currency,
                    estimated_czk=action.estimated_czk_value,
                    valid_until=action.valid_until,
                    urgency=int(action.urgency_score or 0),
                    weight_pct=_weight_pct(held, portfolio, positions),
                    holds=bool(held),
                )
            )
            continue

        if held:
            weight = _weight_pct(held, portfolio, positions)
            where = f" — drží {cz(weight, 1)} % svého účtu" if weight is not None else ""

            # „Dnes není důvod nic dělat" is a finding, and it is only true when
            # the app looked. Without a Green or Red Line it did not look: no
            # rule that decides between holding and selling can run at all. On
            # 2026-08-24 seven of twelve cards read that way, DBO.TO at 16,8 %
            # of the account among them — silence wearing the face of an
            # all-clear, which is the single impression this screen must never
            # give.
            if band in _UNVALUED_BANDS:
                lines.append(
                    OwnerLine(
                        owner=owner,
                        portfolio_id=portfolio.id,
                        instruction_cs="DRŽÍŠ — NEVÍM",
                        detail_cs=(
                            f"Nemám pro tuhle firmu ocenění, takže se k držení "
                            f"ani prodeji nevyjadřuju{where}. Není to klid, je "
                            f"to prázdné místo."
                        ),
                        weight_pct=weight,
                        holds=True,
                    )
                )
                continue

            lines.append(
                OwnerLine(
                    owner=owner,
                    portfolio_id=portfolio.id,
                    instruction_cs="DRŽ",
                    detail_cs=f"Dnes není důvod nic dělat{where}.",
                    weight_pct=weight,
                    holds=True,
                )
            )
        else:
            lines.append(
                OwnerLine(
                    owner=owner,
                    portfolio_id=portfolio.id,
                    instruction_cs="NEMÁ",
                    detail_cs="Tuhle firmu na svém účtu nedrží.",
                    holds=False,
                )
            )

    return lines


def _weight_pct(
    held: list[Position], portfolio: Portfolio, positions: list[Position]
) -> float | None:
    """
    The position's share of ITS OWN account.

    Measured against the account that holds it, never against both summed —
    that sum is an account nobody has, and measuring caps against it let a
    position that was 12 % of one account read as 6 % and pass.
    """
    if not held:
        return None

    def value(p: Position) -> float:
        if p.current_price is None or not p.shares_count:
            return 0.0
        return float(p.current_price) * float(p.shares_count)

    mine = sum(value(p) for p in held)
    account = sum(value(p) for p in positions if p.portfolio_id == portfolio.id)
    account += float(portfolio.cash_balance or 0.0)
    return (mine / account * 100.0) if account else None


def _all_warnings(results: list) -> list[str]:
    """
    Every warning the engine raised, once each.

    Both accounts run the same portfolio-level checks, so the semafor and the
    concentration reading arrive twice. Deduplicated in first-seen order rather
    than through a set, because the order carries meaning — the concentration
    line is placed first on purpose, since it changes how the rest read.
    """
    seen: set[str] = set()
    out: list[str] = []
    for result in results:
        for warning in getattr(result, "warnings", []) or []:
            if warning not in seen:
                seen.add(warning)
                out.append(warning)
    return out


def _split_warnings(warnings: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """
    Separate what belongs to the portfolio from what belongs to one company.

    Fifteen per-ticker lines stacked above twelve cards is the wall that makes
    a screen unreadable, and each of them repeats what its own card already
    says. The engine marks those lines itself, so this reads a marker rather
    than parsing meaning back out of prose.
    """
    portfolio: list[str] = []
    per_ticker: dict[str, list[str]] = {}

    for warning in warnings:
        if UNVALUED_MARKER not in warning:
            portfolio.append(warning)
            continue

        # "⚠️ BEZ OCENĚNÍ: DBO.TO — drží 19,6 % portfolia…"
        tail = warning.split(UNVALUED_MARKER, 1)[1].strip()
        ticker, _, message = tail.partition("—")
        key = canonical_ticker(ticker.strip()) or ticker.strip().upper()
        if not key:
            portfolio.append(warning)
            continue
        per_ticker.setdefault(key, []).append(message.strip() or tail)

    return portfolio, per_ticker
