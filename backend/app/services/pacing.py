"""
How fast the app is allowed to put money to work.

The canon is explicit about this and it is the rule most people break:

    "Nezačínej nákupem VŠECH aktivních picků naráz. Většina lidí začne, když je
     trh 'hot' → nebezpečné."   — GOMES_METHODOLOGY_CANON.md §7, rule 2

Until cylinders were confirmed the app could not buy at all, so the rule had
nothing to restrain. The day they were confirmed it became the first thing that
matters: twelve companies were assessed in one afternoon, and a green market
would have offered several purchases at once — every one of them individually
correct, and the batch of them a bet placed in a single afternoon on a single
reading of a single day.

Not the same thing as the emotional brakes
------------------------------------------
`emotional_brakes` observes what the owner did and warns; it never blocks.
This module blocks. The difference is who is being restrained: the brakes are
about his behaviour, pacing is about the app's. An engine that hands out five
correct purchases at once has followed every valuation rule and still
concentrated the timing risk of all five into one day.

Three limits, each a different failure
--------------------------------------
* One NEW position a week. A new name is a new thesis, and theses should be
  entered one at a time so a mistake in the method shows up before it has been
  repeated five times.
* One tranche per company a fortnight. Adding to what you already hold is the
  safer of the two, but doing it weekly turns a staged entry into a lump sum
  with extra steps.
* Never more than a third of free cash in one day. This one is not a block but
  a size cap, and it lives in the sizing arithmetic — the canon's reason is
  that cash is what lets you buy the correction, and you cannot buy cheap
  stocks if you have no cash.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Final

from loguru import logger
from sqlalchemy.orm import Session

from app.core.tickers import canonical_ticker
from app.models.portfolio import InvestmentLogType
from app.services.emotional_brakes import recent_trades, trade_day

#: A new thesis a week. Slow enough that a flaw in the method surfaces before
#: it has been repeated across the portfolio.
NEW_POSITION_INTERVAL: Final[timedelta] = timedelta(days=7)

#: A tranche per company per fortnight. Three tranches then span six weeks,
#: which is long enough for a staged entry to actually be staged.
TRANCHE_INTERVAL: Final[timedelta] = timedelta(days=14)


def check_pacing(
    db: Session,
    ticker: str,
    *,
    is_new_position: bool,
    now: datetime | None = None,
    portfolio_id: int | None = None,
) -> str | None:
    """
    A Czech reason to hold off, or None if the purchase may proceed.

    Blocking, unlike the emotional brakes — but it says when the limit lifts,
    because a refusal the owner cannot plan around just gets overridden.

    Never raises: a pacing check that cannot read the ledger must not take the
    day's actions down with it. It fails OPEN, and that is the right direction:
    the purchase still has to pass the Buy Guard, the market alert and the
    position caps, so the worst case is one trade sooner than intended rather
    than one trade that should never have happened.
    """
    moment = now or datetime.utcnow()
    window = NEW_POSITION_INTERVAL if is_new_position else TRANCHE_INTERVAL

    try:
        trades = recent_trades(db, moment - window, portfolio_id)
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Kontrolu tempa nákupů se nepodařilo provést")
        return None

    buys = [t for t in trades if t.log_type == InvestmentLogType.BUY]
    if not buys:
        return None

    if is_new_position:
        last = max(buys, key=trade_day)
        lifts = trade_day(last) + NEW_POSITION_INTERVAL
        return (
            f"Nová pozice tenhle týden už byla ({last.ticker}, "
            f"{trade_day(last):%d.%m.}) — kánon říká nezačínat nákupem všeho "
            f"naráz. Další nová pozice od {lifts:%d.%m.}"
        )

    key = canonical_ticker(ticker)
    same = [t for t in buys if canonical_ticker(t.ticker or "") == key]
    if not same:
        return None

    last = max(same, key=trade_day)
    lifts = trade_day(last) + TRANCHE_INTERVAL
    return (
        f"Do {ticker} se dokupovalo {trade_day(last):%d.%m.} — další dávka "
        f"až od {lifts:%d.%m.}, aby ze tří dávek nebyla jedna"
    )


def pacing_check(
    db: Session,
    *,
    now: datetime | None = None,
    portfolio_id: int | None = None,
) -> Callable[[str, bool], str | None]:
    """A checker bound to one account, shaped for the Daily Action engine."""

    def check(ticker: str, is_new_position: bool) -> str | None:
        return check_pacing(
            db, ticker,
            is_new_position=is_new_position,
            now=now,
            portfolio_id=portfolio_id,
        )

    return check
