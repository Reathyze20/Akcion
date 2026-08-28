"""
The whole portfolio on one ladder — a band and two prices per company.

What this is for
----------------
"Abychom prostě věděli." Two people need to look at one screen and know what to
do with each holding, without reading a methodology first. The answer per
company is three lines:

    CXDO   PŘEPLACENO    kupovat do 5,61 $ · odebírat od 6,56 $

The two prices are the point. A verdict is only useful on a day the app gets
opened; a pair of limit prices can be placed at the broker once and left. They
come from the Green and Red Lines rather than from today's quote, so a stale
price does not corrupt them — it only removes the app's ability to say which
band the stock is in right now.

What it deliberately does not do
--------------------------------
No trading, no sizing, no per-account arithmetic. The band is a property of the
COMPANY and is computed once; what either owner should do about it depends on
his own cost basis, weight and cash, and that belongs to the Daily Action
engine. Keeping them apart is what stops one person's position from silently
changing the other's reading of the same stock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource
from app.core.tickers import canonical_ticker, variants_of
from app.models.gomes import StockLifecycleModel
from app.models.portfolio import InvestmentLog, InvestmentLogType, Position
from app.models.stock import Stock
from app.services.daily_actions import price_in_band_currency
from app.trading.gomes_logic import Band, LadderReading, Trigger, ZoneLadder


@dataclass(frozen=True)
class LadderRow:
    """One company, as it appears on the ladder."""

    ticker: str
    company_name: str | None
    reading: LadderReading
    trigger: Trigger
    trigger_reason: str
    #: The currency the two limit prices are quoted in — the band's, which is
    #: not always the currency the position is held in.
    line_currency: str | None
    #: Whether the quality reading behind the band is still in date. An expired
    #: one still describes the position; it just may no longer buy.
    quality_expired: bool = False
    #: The Gomes lines themselves, in `line_currency`. Carried because anything
    #: comparing a second source against this band needs the ceiling, and
    #: re-reading it from the database would be a second query returning a
    #: number this row already had.
    green_line: float | None = None
    red_line: float | None = None
    held: bool = True

    @property
    def sort_key(self) -> tuple[int, str]:
        """Cheapest first — that is where money would go, so that is what leads."""
        order = {
            Band.POD_ZELENOU: 0,
            Band.NAKUP: 1,
            Band.DRZET: 2,
            Band.PREPLACENO: 3,
            Band.NAD_CERVENOU: 4,
            Band.NEZNAME: 5,
            Band.MIMO_METODIKU: 6,
        }
        return order.get(self.reading.band, 9), self.ticker


def portfolio_ladder(
    db: Session,
    *,
    fx_rate_to_czk: Callable[[str], float],
    now: datetime | None = None,
) -> list[LadderRow]:
    """
    Every held position, placed on the ladder.

    One row per company, not per account: two people holding the same stock see
    the same band and the same two prices, because those are facts about the
    company rather than about either portfolio.
    """
    moment = now or datetime.utcnow()

    positions = db.query(Position).filter(Position.shares_count > 0).all()
    # A company held twice — once per account, or once per listing — is still
    # one company. Keyed canonically so KUYA.V and KUYAF do not become two rows
    # with two different answers.
    by_company: dict[str, Position] = {}
    for pos in positions:
        by_company.setdefault(canonical_ticker(pos.ticker) or pos.ticker.upper(), pos)

    rows: list[LadderRow] = []
    for key, pos in by_company.items():
        try:
            rows.append(_row_for(db, key, pos, fx_rate_to_czk, moment))
        except Exception:  # noqa: BLE001 — one unreadable company, not a blank screen
            logger.exception("Řádek žebříku pro {} se nepodařilo sestavit", key)

    return sorted(rows, key=lambda r: r.sort_key)


def _row_for(
    db: Session,
    key: str,
    pos: Position,
    fx_rate_to_czk: Callable[[str], float],
    moment: datetime,
) -> LadderRow:
    symbols = variants_of(key) or (key,)

    band_row = (
        db.query(Stock)
        .filter(Stock.ticker.in_(symbols))
        .filter(Stock.source_key == InvestmentSource.GOMES.value)
        .filter(Stock.green_line.isnot(None))
        .order_by(desc(Stock.created_at))
        .first()
    )
    lifecycle = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker.in_(symbols))
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )

    # A band from another source is not a Gomes band and must not be scored as
    # one — the whole point of keeping the sources apart is that agreement
    # between them means something. But "we have no band" and "the only band we
    # have came from somewhere else" are different facts, and saying the first
    # when the second is true sends the owner looking for data he already has.
    other_band = None
    if band_row is None:
        other_band = (
            db.query(Stock)
            .filter(Stock.ticker.in_(symbols))
            .filter(Stock.green_line.isnot(None))
            .order_by(desc(Stock.created_at))
            .first()
        )

    line_currency = band_row.line_currency if band_row else None
    green = float(band_row.green_line) if band_row and band_row.green_line else None
    red = float(band_row.red_line) if band_row and band_row.red_line else None

    # The price has to be restated in the band's own money before it is scored.
    # Four of the five largest positions trade in Canadian dollars against a
    # band quoted on the US listing.
    price = price_in_band_currency(
        float(pos.current_price) if pos.current_price else None,
        pos.currency,
        line_currency,
        fx_rate_to_czk,
    )

    cylinders, expired = _confirmed_cylinders(lifecycle, moment)
    entry_score = _entry_score(db, symbols)

    reading = ZoneLadder.read(
        price, green, red, cylinders, entry_score=entry_score
    )
    if reading.band is Band.MIMO_METODIKU and other_band is not None:
        reading = LadderReading(
            band=Band.MIMO_METODIKU,
            reason_cs=(
                f"Od Gomese pásmo nemám. Existuje ale zadané odjinud "
                f"({other_band.source_key or 'neznámý zdroj'}: "
                f"{float(other_band.green_line):g}–"
                f"{float(other_band.red_line):g}) — to se nemíchá "
                f"s Gomesovým oceněním, posuď ho zvlášť"
            ),
        )

    trigger, trigger_reason = ZoneLadder.trigger(reading.rr_score, entry_score)

    return LadderRow(
        ticker=pos.ticker.upper(),
        company_name=pos.company_name,
        reading=reading,
        trigger=trigger,
        trigger_reason=trigger_reason,
        line_currency=line_currency,
        quality_expired=expired,
        green_line=green,
        red_line=red,
    )


def _confirmed_cylinders(
    lifecycle: StockLifecycleModel | None, moment: datetime
) -> tuple[int | None, bool]:
    """
    The cylinder count and whether it is still in date.

    An expired confirmation is still returned. The band it produces describes
    the position perfectly well and is what the selling rules read; what expiry
    removes is permission to buy, and that decision belongs to the Daily Action
    engine rather than to a view.
    """
    if lifecycle is None or lifecycle.cylinders_count is None:
        return None, False
    if lifecycle.cylinders_confirmed_at is None:
        return None, False        # a proposal is not a confirmation

    valid_until = lifecycle.cylinders_valid_until
    if valid_until is None:
        return lifecycle.cylinders_count, False

    if valid_until.tzinfo is not None:
        valid_until = valid_until.replace(tzinfo=None)
    reference = moment.replace(tzinfo=None) if moment.tzinfo else moment
    return lifecycle.cylinders_count, valid_until < reference


def _entry_score(db: Session, symbols: tuple[str, ...]) -> float | None:
    """
    The R/R score recorded when the position was opened, if it ever was.

    None for every position bought before this column existed, which today is
    all of them. The three-point rule then stays silent rather than measuring a
    move from a starting point that was never observed.
    """
    row = (
        db.query(InvestmentLog)
        .filter(InvestmentLog.ticker.in_(symbols))
        .filter(InvestmentLog.log_type == InvestmentLogType.BUY)
        .filter(InvestmentLog.rr_score_at_entry.isnot(None))
        .order_by(desc(InvestmentLog.created_at))
        .first()
    )
    return float(row.rr_score_at_entry) if row else None
