"""
Finding the balance-sheet lines the downside floor is built from, and storing them.

`margin_of_safety.py` holds the arithmetic and knows nothing about the database.
This is the part that fetches the filings, writes a snapshot, and reads the
latest one back on the request path.

Why a snapshot rather than a live fetch
----------------------------------------
Reading XBRL is an HTTP call per company. Doing it inside a request would make
the screen wait on the SEC's server for twelve round trips, which is the same
reason the cylinder rubric runs from a script. The snapshot table already
existed for exactly this and now carries equity, goodwill and intangibles too.

It also accumulates. A balance sheet stored once a quarter becomes a series, and
a floor that has been falling for three quarters is a different fact from a
floor that is merely low today — the app cannot see that yet and will be able to.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.tickers import canonical_ticker, variants_of
from app.models.fundamental_snapshot import FundamentalSnapshot
from app.services.margin_of_safety import Balance, Reading, read


def _instant(series: Any) -> float | None:
    """
    The most recent point-in-time value of a balance-sheet concept.

    Balance-sheet lines are instants, not periods: "cash on 30 June" rather
    than "cash during the quarter". The XBRL reader keeps those apart already,
    and a fallback to a period value would silently compare a stock with a flow.
    """
    if series is None:
        return None
    points = getattr(series, "instant", None)
    if points:
        return float(points[0].value)
    return None


def balance_from_filings(fundamentals: Any) -> Balance:
    """Everything the floor needs, out of one company's tagged filings."""
    if fundamentals is None:
        return Balance()
    return Balance(
        cash=_instant(fundamentals.get("cash")),
        total_debt=_instant(fundamentals.get("total_debt")),
        equity=_instant(fundamentals.get("stockholders_equity")),
        goodwill=_instant(fundamentals.get("goodwill")),
        intangibles=_instant(fundamentals.get("intangibles")),
        shares=_instant(fundamentals.get("shares_outstanding")),
    )


def store(db: Session, ticker: str, balance: Balance, *, now: datetime | None = None):
    """
    Write one balance-sheet snapshot. Adds to the session without committing.

    Deduplicated on the numbers rather than on the date: filings arrive
    quarterly and this may run daily, so writing a row per run would turn a
    four-point series into three hundred identical ones.
    """
    if not any(
        v is not None
        for v in (balance.cash, balance.equity, balance.shares, balance.total_debt)
    ):
        return None

    key = canonical_ticker(ticker) or ticker.upper()
    latest = (
        db.query(FundamentalSnapshot)
        .filter(FundamentalSnapshot.ticker == key)
        .order_by(desc(FundamentalSnapshot.captured_at))
        .first()
    )
    unchanged = latest is not None and all(
        (getattr(latest, field) or None) == (value or None)
        for field, value in (
            ("total_cash", balance.cash),
            ("total_debt", balance.total_debt),
            ("stockholders_equity", balance.equity),
            ("goodwill", balance.goodwill),
            ("intangibles", balance.intangibles),
            ("shares_outstanding", balance.shares),
        )
    )
    if unchanged:
        return latest

    row = FundamentalSnapshot(
        ticker=key,
        captured_at=now or datetime.now(timezone.utc),
        total_cash=balance.cash,
        total_debt=balance.total_debt,
        stockholders_equity=balance.equity,
        goodwill=balance.goodwill,
        intangibles=balance.intangibles,
        shares_outstanding=balance.shares,
        currency=balance.currency,
    )
    db.add(row)
    return row


def latest_balance(db: Session, ticker: str) -> Balance:
    """
    The most recently stored balance sheet, or an empty one.

    Empty means the floor cannot be computed and the caller says so. It never
    means the floor is zero — a company nobody has read is not a company with
    no assets.
    """
    symbols = list(variants_of(ticker) or (ticker.upper(),))
    key = canonical_ticker(ticker)
    if key and key not in symbols:
        symbols.append(key)

    row = (
        db.query(FundamentalSnapshot)
        .filter(FundamentalSnapshot.ticker.in_(symbols))
        .filter(
            (FundamentalSnapshot.stockholders_equity.isnot(None))
            | (FundamentalSnapshot.total_cash.isnot(None))
        )
        .order_by(desc(FundamentalSnapshot.captured_at))
        .first()
    )
    if row is None:
        return Balance()

    return Balance(
        cash=row.total_cash,
        total_debt=row.total_debt,
        equity=row.stockholders_equity,
        goodwill=row.goodwill,
        intangibles=row.intangibles,
        shares=row.shares_outstanding,
        currency=row.currency,
    )



def balance_from_quote_cache(db: Session, ticker: str, held_currency: str | None) -> Balance:
    """
    Cash, debt and share count from the quote cache, when no filing has them.

    A weaker floor — net cash only, no tangible assets — and the module names
    the layer, so it is worth having: it reaches the four Canadian listings and
    the foreign private issuer, which between them are most of the money and
    tag no `CommonStockSharesOutstanding` this reader can find.

    Currency, and a trap in the data
    ---------------------------------
    The cache holds one row per SYMBOL, and Yahoo labels each with the trading
    currency of that listing while reporting the same absolute figures for
    both: `DBO.TO` (CAD) and `DBOXF` (USD) each carry cash of 17 828 000. One
    of those labels is wrong, and dividing a price in one currency by a floor
    in the other is wrong by the whole exchange rate.

    So the row is chosen by matching the position's own currency, and when no
    row matches, none is used. A floor nobody can place in a currency is not a
    floor.
    """
    from sqlalchemy import text

    if not held_currency:
        return Balance()

    symbols = list(variants_of(ticker) or (ticker.upper(),))
    if ticker.upper() not in symbols:
        symbols.append(ticker.upper())

    row = db.execute(
        text(
            """
            SELECT total_cash, total_debt, shares_outstanding, currency
            FROM yahoo_finance_cache
            WHERE ticker = ANY(:symbols)
              AND upper(currency) = :ccy
              AND shares_outstanding IS NOT NULL
            ORDER BY last_updated DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"symbols": symbols, "ccy": held_currency.upper()},
    ).first()
    if row is None:
        return Balance()

    return Balance(
        cash=row.total_cash,
        total_debt=row.total_debt,
        shares=row.shares_outstanding,
        currency=(row.currency or "").upper() or None,
    )



def _money(value: float | None, frm: str, to: str) -> float | None:
    """One amount restated in another currency, through the engine's own rate."""
    from app.services.currency import CurrencyService
    from app.services.daily_actions import convert_price

    if value is None:
        return None
    return convert_price(value, frm, to, CurrencyService.get_rate_to_czk)


def _converted(balance: Balance, frm: str, to: str) -> Balance | None:
    """
    The same balance sheet restated in another currency, or None with no rate.

    Only the money moves. The share count is a count, not an amount, and
    multiplying it by an exchange rate would be the kind of quiet nonsense that
    produces a floor three quarters too low.
    """
    from app.services.currency import CurrencyService
    from app.services.daily_actions import convert_price

    def money(value: float | None) -> float | None:
        if value is None:
            return None
        return convert_price(value, frm, to, CurrencyService.get_rate_to_czk)

    cash = money(balance.cash)
    equity = money(balance.equity)
    if balance.cash is not None and cash is None:
        return None
    if balance.equity is not None and equity is None:
        return None

    return Balance(
        cash=cash,
        total_debt=money(balance.total_debt),
        equity=equity,
        goodwill=money(balance.goodwill),
        intangibles=money(balance.intangibles),
        shares=balance.shares,
        currency=to,
    )


def safety_readings(
    db: Session,
    positions: list,
    ceilings: dict[str, tuple[float | None, str | None]] | None = None,
) -> dict[str, Reading]:
    """
    The downside picture for every held position, keyed by canonical ticker.

    `ceilings` are the Gomes Red Lines, used only to state the asymmetry — the
    upside is taken as given rather than recomputed, so the two halves of the
    screen cannot drift apart.

    Never raises. This is the answer to "how much can I lose"; failing to
    compute it must not take down the answers the app already has.
    """
    try:
        out: dict[str, Reading] = {}
        for pos in positions:
            ticker = (pos.ticker or "").upper()
            if not ticker:
                continue
            key = canonical_ticker(ticker) or ticker
            balance = latest_balance(db, ticker)

            # The floor is in the currency the filings report in and the price
            # is in the currency the position trades in. Comparing them raw is
            # wrong by the whole exchange rate — the defect that has already
            # cost one wrong recommendation — so a mismatch means no reading.
            held = (getattr(pos, "currency", None) or "").upper()

            # No filing this reader could use — try the quote cache, which
            # reaches the Canadian listings and carries a share count. Weaker
            # (net cash, no tangible assets) and the module says so.
            if not balance.shares:
                balance = balance_from_quote_cache(db, ticker, held)

            # The balance sheet reports in the company's currency and the
            # position trades in the account's. `ITMSF` files in dollars while
            # `IMP.V` is held in euros, so the floor is CONVERTED rather than
            # refused — the same rate the rest of the engine uses. Refusing was
            # the first version and it silently dropped the four largest
            # holdings out of the one reading that is about losing money.
            filed = (balance.currency or "").upper()
            if filed and held and filed != held:
                balance = _converted(balance, filed, held)
                if balance is None:
                    continue

            # The ceiling arrives in the band's currency and the price is in
            # the account's. Converted here for the same reason the floor is:
            # an unconverted Red Line reported IMP.V as 1 513 % of upside.
            ceiling = None
            raw = (ceilings or {}).get(key)
            if raw:
                value, ccy = raw
                ceiling = value
                if value and ccy and held and ccy.upper() != held:
                    ceiling = _money(value, ccy.upper(), held)

            out[key] = read(
                ticker,
                float(pos.current_price) if pos.current_price else None,
                balance,
                ceiling=ceiling,
            )
        return out
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("Ochranné rezervy se nepodařilo spočítat")
        return {}
