"""
Degiro transaction export → real cost basis and real history.

Why transactions and not the positions export
---------------------------------------------
Degiro's positions export says how many shares you hold and nothing
trustworthy about what you paid. That is why 12 of the owner's 14 positions
carry `avg_cost = NULL` and the app has to answer "⚠️ chybí nákupní cena"
instead of advising: with no cost basis there is no P/L, no doubling rule,
and no 3-point trim trigger.

The transaction export carries every buy and sell with its price, date, fees
and currency. From it the app can derive:
  * a genuine weighted average cost per instrument,
  * realized P/L on everything already sold,
  * a full history that feeds the trade ledger (services/trade_ledger.py).

Format notes (Czech locale export, verified against a real 442-row file
spanning 2022-02 to 2026-08)
----------------------------------------------------------------------
  * dates are DD-MM-YYYY, times HH:MM
  * numbers use a decimal comma and a dot as thousands separator: "1.234,56"
  * `Počet` is SIGNED — positive is a buy, negative is a sell
  * `Cena` is always positive; direction lives in the sign of `Počet`
  * two header cells are EMPTY: they hold the currency for `Cena` and for
    `Hodnota v domácí měně`, so columns must be read positionally, not by name
  * fee columns are negative; they are normalised to a positive magnitude here
  * `ID objednávky` is NOT unique — one order executes in several fills that
    share it, and the minute-resolution timestamp cannot separate them, so
    identical fills are numbered (`fill_seq`) instead of being deduplicated
    away

The export identifies instruments by ISIN and product name only — no ticker.
Resolution is a separate concern (services/instrument_resolver.py); this
module deliberately keeps both fields untouched so the resolver has the best
possible evidence.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime

from loguru import logger

# Positional layout of the Czech export. Named headers are unreliable — two
# of them are empty strings — so the mapping is pinned here and validated.
COL_DATE = 0
COL_TIME = 1
COL_PRODUCT = 2
COL_ISIN = 3
COL_EXCHANGE = 4
COL_VENUE = 5
COL_QUANTITY = 6
COL_PRICE = 7
COL_PRICE_CCY = 8
COL_LOCAL_VALUE = 9
COL_LOCAL_CCY = 10
COL_VALUE_EUR = 11
COL_FX_RATE = 12
COL_AUTOFX_FEE = 13
COL_TX_FEE = 14
COL_TOTAL_EUR = 15
COL_ORDER_ID = 16

EXPECTED_MIN_COLUMNS = 16


class DegiroImportError(ValueError):
    """The file is not a Degiro transaction export we can read."""


def parse_czech_number(raw: str | None) -> float | None:
    """
    "2,9600" -> 2.96 · "-1.234,56" -> -1234.56 · "" -> None

    Returns None rather than 0.0 for anything unparseable. A fee that failed
    to parse must not silently become "no fee".
    """
    if raw is None:
        return None
    s = raw.strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    # Thousands separator is '.', decimal separator is ','.
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_czech_datetime(date_raw: str, time_raw: str | None) -> datetime | None:
    """DD-MM-YYYY + optional HH:MM."""
    d = (date_raw or "").strip()
    if not d:
        return None
    t = (time_raw or "").strip()
    for fmt, value in (("%d-%m-%Y %H:%M", f"{d} {t}"), ("%d-%m-%Y", d)):
        if fmt.endswith("%H:%M") and not t:
            continue
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class DegiroTransaction:
    """One executed order, exactly as the broker recorded it."""

    executed_at: datetime
    product_name: str
    isin: str
    quantity: float          # signed: > 0 bought, < 0 sold
    price: float             # per share, in `currency`, always positive
    currency: str
    local_value: float | None   # signed: negative when money went out
    value_eur: float | None
    fx_rate: float | None
    fees_eur: float             # positive magnitude, autoFX + transaction
    total_eur: float | None
    order_id: str | None
    exchange: str | None = None
    #: Which occurrence this is among byte-identical fills in the same import.
    #: One order routinely executes as several fills that are indistinguishable
    #: in the export — the timestamp only has minute resolution. A real file
    #: contains a 700-share sell as seven identical -100 @ 3.14 rows. Numbering
    #: them keeps every share while still letting a repeated import collapse.
    fill_seq: int = 0

    @property
    def is_buy(self) -> bool:
        return self.quantity > 0

    @property
    def side(self) -> str:
        return "BUY" if self.is_buy else "SELL"

    @property
    def abs_quantity(self) -> float:
        return abs(self.quantity)

    @property
    def gross_local(self) -> float:
        """Trade value in the instrument's own currency, unsigned."""
        return self.abs_quantity * self.price


def parse_transactions(content: str) -> list[DegiroTransaction]:
    """
    Parse a Degiro transaction CSV.

    Rows that cannot be read as a trade are skipped with a warning rather than
    guessed at — a mis-parsed price would corrupt the cost basis of a real
    position. Raises only when the file as a whole is not this export.
    """
    if not content.strip():
        raise DegiroImportError("Soubor je prázdný.")

    rows = list(csv.reader(io.StringIO(content.lstrip("﻿"))))
    if len(rows) < 2:
        raise DegiroImportError("Soubor neobsahuje žádné transakce.")

    header = rows[0]
    if len(header) < EXPECTED_MIN_COLUMNS:
        raise DegiroImportError(
            f"Nečekaný formát: {len(header)} sloupců, očekáváno alespoň "
            f"{EXPECTED_MIN_COLUMNS}. Jde opravdu o export transakcí "
            f"(Účet → Transakce), ne o export portfolia?"
        )

    out: list[DegiroTransaction] = []
    skipped = 0

    for line_no, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < EXPECTED_MIN_COLUMNS:
            skipped += 1
            continue

        quantity = parse_czech_number(row[COL_QUANTITY])
        price = parse_czech_number(row[COL_PRICE])
        executed_at = parse_czech_datetime(row[COL_DATE], row[COL_TIME])

        if quantity is None or quantity == 0 or price is None or price <= 0:
            # Cash movements, dividends and corporate-action lines share this
            # export in some Degiro variants; they are not trades.
            skipped += 1
            continue
        if executed_at is None:
            logger.warning("Degiro row {}: unreadable date, skipped", line_no)
            skipped += 1
            continue

        isin = (row[COL_ISIN] or "").strip().upper()
        if not isin:
            skipped += 1
            continue

        autofx = parse_czech_number(row[COL_AUTOFX_FEE]) or 0.0
        tx_fee = parse_czech_number(row[COL_TX_FEE]) or 0.0

        out.append(
            DegiroTransaction(
                executed_at=executed_at,
                product_name=(row[COL_PRODUCT] or "").strip()[:200],
                isin=isin,
                quantity=quantity,
                price=price,
                currency=(row[COL_PRICE_CCY] or "").strip().upper()[:3] or "EUR",
                local_value=parse_czech_number(row[COL_LOCAL_VALUE]),
                value_eur=parse_czech_number(row[COL_VALUE_EUR]),
                fx_rate=parse_czech_number(row[COL_FX_RATE]),
                # Export writes fees as negative; magnitude is what callers want.
                fees_eur=abs(autofx) + abs(tx_fee),
                total_eur=parse_czech_number(row[COL_TOTAL_EUR]),
                order_id=(row[COL_ORDER_ID] or "").strip() or None,
                exchange=(row[COL_EXCHANGE] or "").strip() or None,
            )
        )

    if not out:
        raise DegiroImportError(
            "V souboru nebyla nalezena žádná čitelná transakce."
        )

    # Number identical fills so none of them can be mistaken for a duplicate.
    counts: dict[tuple, int] = defaultdict(int)
    numbered: list[DegiroTransaction] = []
    for tx in out:
        key = (tx.order_id, tx.executed_at, tx.isin, tx.quantity, tx.price)
        counts[key] += 1
        numbered.append(replace(tx, fill_seq=counts[key]))
    out = numbered

    logger.info("Degiro export parsed: {} trades, {} rows skipped", len(out), skipped)
    return out


def deduplicate(transactions: list[DegiroTransaction]) -> list[DegiroTransaction]:
    """
    Drop rows that are genuinely the same fill seen twice.

    Re-importing an overlapping export is the normal case — the owner exports
    "everything" each time — and double-counting a buy would silently halve
    the recorded average cost.

    The key is the whole fill, NOT the order id alone. One order routinely
    executes in several fills that share an id: a real export contains an
    ADCORE sell of 2000 @ 0.14 and 500 @ 0.15 one minute apart under one id.
    Keying on the id would delete 500 real shares and leave the wrong average
    price behind, with nothing to show it happened.
    """
    seen: set[tuple] = set()
    out: list[DegiroTransaction] = []
    for tx in transactions:
        key = (
            tx.order_id, tx.executed_at, tx.isin,
            tx.quantity, tx.price, tx.fill_seq,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(tx)
    return out


@dataclass
class DerivedPosition:
    """Holding rebuilt from the trade history of one instrument."""

    isin: str
    product_name: str
    currency: str
    shares: float = 0.0
    avg_cost: float | None = None
    realized_pl: float = 0.0
    total_fees_eur: float = 0.0
    buys: int = 0
    sells: int = 0
    first_trade: datetime | None = None
    last_trade: datetime | None = None
    #: Set when a sell exceeded the shares the history accounts for. Almost
    #: always a corporate action (split, reverse split, ticker change) that
    #: the transaction export does not contain — e.g. SMSI's 1:5 reverse
    #: split. Flagged loudly instead of being absorbed into the numbers.
    inconsistent: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.shares > 1e-9


def derive_positions(
    transactions: list[DegiroTransaction],
) -> dict[str, DerivedPosition]:
    """
    Replay the trade history into holdings, average cost and realized P/L.

    Uses the weighted-average method, matching how `positions.avg_cost` is
    defined elsewhere in the app (see services/trade_ledger.py).

    Realized P/L is computed in the instrument's own currency, never converted
    — mixing six currencies into one number without a dated FX rate would
    produce a confident, wrong figure.
    """
    by_isin: dict[str, DerivedPosition] = {}

    for tx in sorted(transactions, key=lambda t: t.executed_at):
        pos = by_isin.get(tx.isin)
        if pos is None:
            pos = DerivedPosition(
                isin=tx.isin, product_name=tx.product_name, currency=tx.currency
            )
            by_isin[tx.isin] = pos

        pos.first_trade = pos.first_trade or tx.executed_at
        pos.last_trade = tx.executed_at
        pos.total_fees_eur += tx.fees_eur

        if tx.is_buy:
            pos.buys += 1
            new_shares = pos.shares + tx.abs_quantity
            if pos.avg_cost is None or pos.shares <= 0:
                pos.avg_cost = tx.price
            else:
                pos.avg_cost = (
                    pos.shares * pos.avg_cost + tx.abs_quantity * tx.price
                ) / new_shares
            pos.shares = new_shares
        else:
            pos.sells += 1
            sold = tx.abs_quantity
            if sold - pos.shares > 1e-6:
                pos.inconsistent = True
                pos.notes.append(
                    f"{tx.executed_at:%d.%m.%Y}: prodej {sold:g} ks, ale historie "
                    f"eviduje jen {pos.shares:g} — nejspíš split nebo změna tickeru"
                )
            if pos.avg_cost is not None:
                pos.realized_pl += (tx.price - pos.avg_cost) * min(sold, pos.shares)
            pos.shares = max(0.0, pos.shares - sold)
            if pos.shares <= 1e-9:
                # Position closed. Average cost of zero shares is meaningless;
                # keep it None so a later re-entry starts clean.
                pos.avg_cost = None

    return by_isin


def summarize(positions: dict[str, DerivedPosition]) -> dict[str, int | float]:
    """Headline numbers for an import preview."""
    open_positions = [p for p in positions.values() if p.is_open]
    return {
        "instruments": len(positions),
        "open_positions": len(open_positions),
        "closed_positions": len(positions) - len(open_positions),
        "inconsistent": sum(1 for p in positions.values() if p.inconsistent),
        "total_fees_eur": round(sum(p.total_fees_eur for p in positions.values()), 2),
    }
