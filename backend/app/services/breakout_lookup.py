"""
Gather Breakout's side out of the database and hand it to the engine.

`breakout_band.py` holds the rules and knows nothing about SQLAlchemy. This
module does the fetching: the polled watchlist, plus whatever the named
analysts on `analyst_roster` have actually written, joined per company.

Why the roster is consulted here and not trusted from the row
-------------------------------------------------------------
`ticker_mentions.source_key` is stamped when a claim is stored, and the roster
can change afterwards — somebody is added, somebody is deactivated. Reading the
stored key alone would let a deactivated analyst keep voting forever. So the
speaker is re-checked against today's roster and a claim from somebody no longer
on it is dropped, which is the point of being able to deactivate anybody.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource, normalize_source
from app.core.tickers import canonical_ticker
from app.models.analysis import TickerMention
from app.services.analyst_roster import load as load_roster
from app.services.breakout_band import AnalystWord, BreakoutView, WatchlistRow, build_view

#: The day the watchlist poller started. A name whose `first_seen_at` is later
#: than this was genuinely watched being added, so its `price_at_read` is the
#: price at the moment of the addition and can anchor a green line. For the 28
#: names already on the list that day, the read price is just whatever it cost
#: on a Sunday and anchors nothing.
POLLING_STARTED = date(2026, 8, 23)


def _f(value) -> float | None:
    """Numeric or Decimal to float, keeping None as None."""
    return None if value is None else float(value)


def load_watchlist(db: Session) -> dict[str, WatchlistRow]:
    """Their published list, keyed by canonical ticker."""
    rows = db.execute(
        text(
            """
            SELECT symbol, company_name, endorsements, upside_ratio,
                   price_at_read, implied_target, first_seen_at, added_at
            FROM breakout_watchlist
            """
        )
    ).mappings().all()

    out: dict[str, WatchlistRow] = {}
    for r in rows:
        first_seen = r["first_seen_at"]
        out[canonical_ticker(r["symbol"])] = WatchlistRow(
            symbol=r["symbol"],
            company_name=r["company_name"],
            endorsements=int(r["endorsements"] or 0),
            upside_ratio=_f(r["upside_ratio"]),
            price_at_read=_f(r["price_at_read"]),
            implied_target=_f(r["implied_target"]),
            first_seen_at=first_seen,
            added_at=r["added_at"],
            seen_added=bool(first_seen and first_seen.date() > POLLING_STARTED),
        )
    return out


def load_analyst_words(db: Session) -> dict[str, list[AnalystWord]]:
    """
    What the named analysts wrote, keyed by canonical ticker.

    Only claims whose speaker is on today's roster under BREAKOUT_INVESTORS
    survive. A claim carrying no verdict and no number still costs nothing to
    keep and is dropped here, because it cannot move a band or a stance — it is
    context, and context is read on the company's own page.
    """
    roster = load_roster(db)
    rows = db.execute(
        text(
            """
            SELECT ticker, speaker, mention_date, action_mentioned, price_target
            FROM ticker_mentions
            WHERE is_current IS TRUE
              AND speaker IS NOT NULL
              AND (action_mentioned IS NOT NULL OR price_target IS NOT NULL)
            """
        )
    ).mappings().all()

    out: dict[str, list[AnalystWord]] = {}
    for r in rows:
        if normalize_source(r["speaker"], roster=roster) != InvestmentSource.BREAKOUT_INVESTORS.value:
            continue
        out.setdefault(canonical_ticker(r["ticker"]), []).append(
            AnalystWord(
                analyst=r["speaker"],
                said_on=r["mention_date"],
                target=_f(r["price_target"]),
                verdict=r["action_mentioned"],
            )
        )
    return out


@dataclass(frozen=True)
class AnalystNote:
    """Co jmenovaný analytik napsal, doslova."""

    analyst: str
    said_on: date | None
    quote: str
    #: FACT / OPINION, jak to označila extrakce. Může chybět.
    claim_type: str | None = None
    verdict: str | None = None
    target: float | None = None


def load_analyst_notes(db: Session) -> dict[str, list[AnalystNote]]:
    """
    Doslovná tvrzení jmenovaných analytiků BI, keyed by canonical ticker.

    Proč vedle `load_analyst_words()` a ne místo ní
    ------------------------------------------------
    Ta druhá slouží stavbě pásma a zahazuje tvrzení bez verdiktu a bez čísla —
    tam je to správně, kontext pásmem nehne. Jenže z jedenácti věcí, které
    Robert Mock napsal o DFSC, jich devět nemá ani verdikt, ani cíl: „Bliss
    will be produced using outsourced manufacturing", „General Dynamics owns
    the major contract". Pro pásmo to je šum, pro spis nálezu je to **to
    jediné cenné, co od Breakoutu vůbec máme** — jméno pod tvrzením a doslovný
    citát, na rozdíl od seškrábaného počtu podpisů.

    **Nefiltruje se na `is_current`, a je to schválně.** Ten sloupec zapisují
    dvě různá místa opačně (backfill přepisů `False`, extrakce z WhatsAppu
    `True`), takže je to příznak toho, kudy řádek přišel, ne jestli platí.
    Filtrovat na něj znamená vybírat podle cesty a dostat prázdno, až se ta
    cesta změní. Podmínkou je to, na čem tady doopravdy záleží: je pod tím
    podepsaný člověk z aktuálního seznamu a je k tomu citát.
    """
    roster = load_roster(db)
    # Přes ORM, ne přes `text()`. Ta funkce vedle používá syrové SQL z jediného
    # důvodu: `speaker`, `source_key` a `claim_type` byly v databázi a na modelu
    # chyběly, takže je ORM neviděl. To je teď spravené — a syrový dotaz by
    # navíc na SQLite vracel datum jako řetězec, což by se projevilo až v testu
    # jako `'str' object has no attribute 'day'`.
    rows = (
        db.query(TickerMention)
        .filter(TickerMention.speaker.isnot(None))
        .filter(TickerMention.context_snippet.isnot(None))
        .order_by(desc(TickerMention.mention_date), TickerMention.id)
        .all()
    )

    out: dict[str, list[AnalystNote]] = {}
    for row in rows:
        if (
            normalize_source(row.speaker, roster=roster)
            != InvestmentSource.BREAKOUT_INVESTORS.value
        ):
            continue
        out.setdefault(canonical_ticker(row.ticker), []).append(
            AnalystNote(
                analyst=row.speaker,
                said_on=row.mention_date,
                quote=row.context_snippet,
                claim_type=row.claim_type,
                verdict=row.action_mentioned,
                target=_f(row.price_target),
            )
        )
    return out


def breakout_views(db: Session) -> dict[str, BreakoutView]:
    """
    Breakout's position on every company they cover, keyed by canonical ticker.

    Companies where they have nothing are absent rather than present-and-empty:
    an absent key means "they have not spoken", which the caller must not read
    as agreement.
    """
    watchlist = load_watchlist(db)
    words = load_analyst_words(db)

    views: dict[str, BreakoutView] = {}
    for ticker, row in watchlist.items():
        view = build_view(row, words.get(ticker))
        if view is not None:
            views[ticker] = view
    return views
