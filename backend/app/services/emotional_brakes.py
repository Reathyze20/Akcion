"""
Emotional brakes — the reason this app exists.

The methodology says "WE INVEST. WE'RE NOT HERE TO TRADE" and expects a handful
of moves a year. The failure mode it does not cover is the human one: selling
at a loss and buying straight back in to make it up, or trading more the worse
things go. Neither shows up in an R/R score. Both cost real money.

Until the trade ledger existed there was nothing to build this on — exits were
recorded by overwriting `positions.shares_count`, so the app could not know a
loss had ever happened. `services/trade_ledger.py` now keeps an immutable row
per trade, with `realized_pl` and `created_at`, which is exactly what these
checks read.

**These warn. They never block.**

That is deliberate and it is the whole design. Tomáš asked for advice he can
judge, not decisions made for him — a brake that silently refuses a trade is
unjudgeable, because the reasoning never reaches him. So each check returns a
Czech sentence naming what it saw, with the dates and numbers in it, and he
decides. A rule he overrides having read it is working exactly as intended.

Thresholds
----------
Nothing in the Gomes canon or the playbook fixes these numbers — the canon is
about valuation, not psychology. They are set here, conservatively, with the
reasoning attached, and they are constants precisely so they are easy to argue
with and change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.portfolio import InvestmentLog, InvestmentLogType


# ==============================================================================
# Thresholds
# ==============================================================================

#: How long after selling a ticker at a loss a re-entry into that same ticker
#: is worth a second look. Thirty days because the method holds for months —
#: on that horizon, wanting the same company back within a month is far more
#: likely to be about the loss than about the company. Short enough that a
#: genuine change of thesis is not second-guessed forever.
REENTRY_WINDOW: Final[timedelta] = timedelta(days=30)

#: A window in which a burst of trades stands out. The method expects a few
#: moves per year, so several in a single week is a pattern, not a coincidence.
BURST_WINDOW: Final[timedelta] = timedelta(days=7)

#: Trades within BURST_WINDOW that make the burst worth naming. Three is two
#: more than this method normally calls for in a week.
BURST_THRESHOLD: Final[int] = 3

#: A realized loss large enough that the days after it are worth flagging,
#: as a share of the portfolio. Five percent is a bad day, not a catastrophe —
#: which is the point: this is about the state of mind, not about ruin.
SIGNIFICANT_LOSS_PCT: Final[float] = 5.0

#: How long after a significant loss the app keeps mentioning it.
LOSS_COOLDOWN: Final[timedelta] = timedelta(days=3)


@dataclass(frozen=True)
class Brake:
    """One observation about trading behaviour, phrased for a human to judge."""

    kind: str
    message: str
    #: The ticker it concerns, when it concerns one.
    ticker: str | None = None


# ==============================================================================
# Reading the ledger
# ==============================================================================

def trade_day(log: InvestmentLog) -> date:
    """
    When the trade happened, falling back to when it was written down.

    These brakes are about behaviour over time, so they need the day of the
    ACT, not of the bookkeeping — recording an old sale today must not read as
    trading today. NULL falls back rather than dropping the row: a trade whose
    date nobody recorded still happened.
    """
    if log.trade_date is not None:
        return log.trade_date
    return log.created_at.date()


def recent_trades(
    db: Session,
    since: datetime,
    portfolio_id: int | None = None,
) -> list[InvestmentLog]:
    """
    Every recorded BUY/SELL traded since `since`, newest first.

    The two-branch filter is deliberate and is NOT the same as
    `coalesce(trade_date, cast(created_at AS date))`. SQLite applies numeric
    affinity to a CAST it does not recognise, so that expression turns
    '2026-08-23 12:00' into the integer 2026 and silently drops every row with
    no trade date. Postgres gets it right, which is the worst kind of
    difference: the tests would pass and production would be wrong, or the
    reverse. Spelling both branches out behaves the same everywhere.

    Ordering happens in Python for the same reason — NULLS FIRST/LAST is not
    portable either, and the window holds a handful of rows.
    """
    query = db.query(InvestmentLog).filter(
        or_(
            and_(
                InvestmentLog.trade_date.isnot(None),
                InvestmentLog.trade_date >= since.date(),
            ),
            and_(
                InvestmentLog.trade_date.is_(None),
                InvestmentLog.created_at >= since,
            ),
        ),
        InvestmentLog.log_type.in_(
            [InvestmentLogType.BUY, InvestmentLogType.SELL]
        ),
    )
    if portfolio_id is not None:
        query = query.filter(InvestmentLog.portfolio_id == portfolio_id)
    return sorted(query.all(), key=trade_day, reverse=True)


# ==============================================================================
# The checks
# ==============================================================================

def check_reentry(
    db: Session,
    ticker: str,
    *,
    now: datetime | None = None,
    portfolio_id: int | None = None,
) -> Brake | None:
    """
    Was this ticker sold at a loss recently enough for a re-entry to be worth
    a second look?

    Returns None when there is nothing to say — including when the ledger holds
    no sale of it, or the sale's cost basis was unknown. An unknown cost basis
    means we do not know whether it was a loss, and "we do not know" must not
    become "it was fine" or "it was bad".
    """
    now = now or datetime.utcnow()
    ticker = ticker.upper()

    for trade in recent_trades(db, now - REENTRY_WINDOW, portfolio_id):
        if trade.log_type != InvestmentLogType.SELL:
            continue
        if (trade.ticker or "").upper() != ticker:
            continue
        # realized_pl is None when the cost basis was unknown — see
        # trade_ledger's honesty rules. Silence is the honest answer there.
        if trade.realized_pl is None or trade.realized_pl >= 0:
            continue

        days = (now - trade.created_at).days
        return Brake(
            kind="REENTRY_AFTER_LOSS",
            ticker=ticker,
            message=(
                f"🧠 {ticker} jsi prodal se ztrátou {abs(trade.realized_pl):,.0f} "
                f"před {days} dny ({trade.created_at:%d.%m.%Y}). Nákup zpátky "
                f"může být správný — ale zeptej se, jestli se změnila teze, "
                f"nebo jen chceš tu ztrátu zpět."
            ),
        )
    return None


def check_burst(
    db: Session,
    *,
    now: datetime | None = None,
    portfolio_id: int | None = None,
) -> Brake | None:
    """
    Have there been unusually many trades this week?

    The method calls for a handful of moves a year. Several in a week is worth
    naming — not because activity is forbidden, but because it is the shape
    revenge trading takes, and it is invisible from inside.
    """
    now = now or datetime.utcnow()
    trades = recent_trades(db, now - BURST_WINDOW, portfolio_id)

    if len(trades) < BURST_THRESHOLD:
        return None

    tickers = sorted({(t.ticker or "?").upper() for t in trades})
    return Brake(
        kind="TRADE_BURST",
        message=(
            f"🧠 {len(trades)} obchodů za posledních "
            f"{BURST_WINDOW.days} dní ({', '.join(tickers)}). Metoda počítá "
            f"s pár tahy za rok. Není to samo o sobě chyba — jen si ověř, "
            f"že každý z nich měl vlastní důvod."
        ),
    )


def check_recent_loss(
    db: Session,
    portfolio_value_czk: float | None,
    *,
    now: datetime | None = None,
    portfolio_id: int | None = None,
) -> Brake | None:
    """
    Was a significant loss realized in the last few days?

    Not a prohibition on trading — a note that the days right after a loss are
    the ones where decisions tend to get made for the wrong reason.
    """
    now = now or datetime.utcnow()
    if not portfolio_value_czk or portfolio_value_czk <= 0:
        # Without a portfolio value there is no "significant" to measure
        # against. Guessing a threshold would be inventing the finding.
        return None

    for trade in recent_trades(db, now - LOSS_COOLDOWN, portfolio_id):
        if trade.log_type != InvestmentLogType.SELL:
            continue
        if trade.realized_pl is None or trade.realized_pl >= 0:
            continue

        loss_pct = abs(trade.realized_pl) / portfolio_value_czk * 100
        if loss_pct < SIGNIFICANT_LOSS_PCT:
            continue

        days = (now - trade.created_at).days
        when = "dnes" if days == 0 else f"před {days} dny"
        return Brake(
            kind="RECENT_SIGNIFICANT_LOSS",
            ticker=(trade.ticker or "").upper() or None,
            message=(
                f"🧠 {when} jsi realizoval ztrátu {abs(trade.realized_pl):,.0f} Kč "
                f"({loss_pct:.1f} % portfolia) na {trade.ticker}. Další tahy "
                f"tenhle týden si přečti dvakrát — po ztrátě se rozhoduje hůř."
            ),
        )
    return None


def collect_brakes(
    db: Session,
    portfolio_value_czk: float | None = None,
    *,
    now: datetime | None = None,
    portfolio_id: int | None = None,
) -> list[Brake]:
    """
    Every behavioural observation worth surfacing right now.

    Ordered loudest first: a fresh loss colours everything after it, a burst is
    a pattern, and a re-entry only matters once there is a purchase in view.
    """
    now = now or datetime.utcnow()
    found = [
        check_recent_loss(db, portfolio_value_czk, now=now, portfolio_id=portfolio_id),
        check_burst(db, now=now, portfolio_id=portfolio_id),
    ]
    return [brake for brake in found if brake is not None]
