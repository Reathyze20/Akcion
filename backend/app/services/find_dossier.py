"""
Spis k vlastnímu nálezu — všechno, co aplikace o té firmě ví, jako fakta a mezery.

Dvě funkce a mezi nimi ostrá hranice:

  enrich(db, ticker)   sáhne na síť (Yahoo, EDGAR, Finnhub) a naplní cache.
                       Zdarma — žádný jazykový model. Zapisuje výhradně do
                       cache a pokrývacích tabulek.
  build(db, ticker)    NESÁHNE na síť. Složí spis z toho, co databáze už drží.

To rozdělení je opsané z `cylinder_intake.gather()`, jehož docstring říká
„Never fetches from the network" — a je to i důvod, proč tenhle soubor vznikl:
u čerstvého nálezu databáze neví nic, takže bez `enrich()` by každý nový nápad
skončil spisem samých mezer.

**Směr (`Fact.direction`) určuje kód, nikdy model.** Fakt je označený za mluvící
pro nebo proti podle pravidla, které ho vyrobilo — záporná delta u válců mluví
proti, nález z podání u SEC mluví proti, zisková marže mluví pro. Vysvětlovač
smí fakta jen citovat; kdyby si směr určoval sám, mohl by napsat „hotovost
vydrží čtyři měsíce, což je dobře".

**Mezery mají vlastní jmenný prostor `MEZ-`.** Fakt nikdy nezačíná na `MEZ-`,
takže `find_explainer.verify_points()` umí strojově poznat bod, který se opírá
o nepřítomnost dat. Uvažování z chybějícího vstupu je přesně ta vada, kvůli
které tahle aplikace už třikrát vydala sebejistý verdikt na prázdno.

**Pásmo se čte z POTVRZENÝCH válců.** U nálezu žádné potvrzené nejsou, takže
pásmo vyjde „neznámé" — a to je pravda, ne porucha. Návrh rubriky se ukazuje
vedle jako podmíněná věta („kdyby válce byly 6…"), aby majitel dostal konkrétní
číslo, ale nikdy ne jako potvrzený údaj. Nic v tomhle souboru nezapisuje do
`stock_lifecycle` ani do `stocks`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Sequence

from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.core.czech import d as cz_date
from app.core.czech import n as cz_num
from app.core.sources import InvestmentSource, verdict_stance
from app.core.tickers import canonical_ticker, variants_of
from app.models.analysis import AnalystTranscript, TickerMention
from app.models.breakout import BreakoutWatchEntry
from app.models.gomes import StockLifecycleModel
from app.models.portfolio import MarketStatus
from app.models.sec import SecCoverage
from app.models.sec_finding import SecFinding
from app.models.stock import Stock
from app.services import cylinder_intake, lifecycle_intake
from app.trading.gomes_logic import GomesGatekeeper, ZoneLadder

logger = logging.getLogger(__name__)

# ==============================================================================
# Slovník spisu
# ==============================================================================

LAYER_GOMES = "GOMES"
LAYER_BREAKOUT = "BREAKOUT"
LAYER_FUNDAMENTY = "FUNDAMENTY"
LAYER_METODIKA = "METODIKA"
LAYER_VLASTNI = "VLASTNI"
LAYER_TRH = "TRH"

#: Prefix, který smí nést jen mezera. Na tomhle stojí kontrola ve vysvětlovači.
GAP_PREFIX = "MEZ"

DIR_PRO = "PRO"
DIR_PROTI = "PROTI"
DIR_NEUTRAL = "NEUTRAL"

#: Kolik Gomesových výroků se do spisu vejde. Osm je zhruba rok jeho pokrytí
#: jednoho jména; víc už majitel čte jako archiv, ne jako podklad.
MAX_GOMES_MENTIONS = 8

#: Po téhle době je stupeň semaforu starý. Stejná hodnota jako v Daily Action
#: (`daily_actions.STALE_ALERT_AFTER`) — dvě různá čísla by znamenala, že tatáž
#: zelená autorizuje na jedné obrazovce a na druhé ne.
STALE_ALERT_AFTER = timedelta(days=14)

#: Za jak dlouho je kurz starý. Den, protože pásmo se počítá z ceny.
STALE_PRICE_AFTER = timedelta(days=1)

#: Pod kolika měsíci hotovosti je runway fakt mluvící proti. Shodné s
#: `lifecycle_rubric.RUNWAY_TIGHT_MONTHS`.
RUNWAY_TIGHT_MONTHS = 12

#: Od kolika dnů je nejnovější čtvrtletí ve výkazech tak staré, že se z něj
#: nesmí mluvit o dnešku. Devět měsíců: firma podává čtvrtletně, takže dvě
#: zmeškaná období znamenají, že se koncept přestal tagovat a série uvízla.
STALE_FILING_DAYS = 275


@dataclass(frozen=True)
class Fact:
    """Jeden údaj, hotová česká věta a odkud pochází."""

    id: str
    layer: str
    text_cs: str
    source: str
    as_of: date | None = None
    #: Doslovný citát, když to někdo řekl nebo napsal. Jinak None.
    quote: str | None = None
    #: PRO / PROTI / NEUTRAL — určuje pravidlo, které fakt vyrobilo.
    direction: str = DIR_NEUTRAL


@dataclass(frozen=True)
class Gap:
    """Pojmenovaná nepřítomnost. Nikdy se nedoplňuje výchozí hodnotou."""

    id: str
    layer: str
    text_cs: str
    #: Co s tím jde udělat, když to jde. None = ten údaj prostě neexistuje.
    fixable_cs: str | None = None


@dataclass(frozen=True)
class MethodReading:
    """Čtení metodiky. Deterministické, spočítané, ne vyprávěné."""

    band: str
    band_reason_cs: str
    rr_score: float | None = None
    deserved: float | None = None
    buy_below: float | None = None
    sell_above: float | None = None
    green_line: float | None = None
    red_line: float | None = None
    line_currency: str | None = None

    cylinders_confirmed: int | None = None
    cylinders_proposed: int | None = None
    #: Podmíněné čtení s navrženými válci. Věta, ne verdikt.
    if_cylinders_cs: str | None = None

    phase_proposed: str | None = None
    phase_rough_patch: bool = False

    market_alert: str | None = None
    market_alert_stale: bool = True

    gate_passed: bool | None = None
    gate_code: str | None = None
    gate_reason: str | None = None


@dataclass(frozen=True)
class Dossier:
    ticker: str
    symbol: str
    company_name: str | None
    as_of: datetime

    price: float | None
    price_currency: str | None
    price_is_stale: bool

    facts: tuple[Fact, ...]
    gaps: tuple[Gap, ...]
    method: MethodReading

    def fact_ids(self) -> frozenset[str]:
        return frozenset(f.id for f in self.facts)

    def fact(self, fid: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fid), None)

    def facts_by_direction(self, direction: str) -> tuple[Fact, ...]:
        return tuple(f for f in self.facts if f.direction == direction)


class _Ids:
    """Rozdává id v jednom průchodu, aby byla stabilní a nekolidovala."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}-{self._counters[prefix]}"


_PREFIX = {
    LAYER_GOMES: "GOMES",
    LAYER_BREAKOUT: "BREAK",
    LAYER_FUNDAMENTY: "FUND",
    LAYER_METODIKA: "METOD",
    LAYER_VLASTNI: "VLAST",
    LAYER_TRH: "TRH",
}


def _aware(stamp: datetime | None) -> datetime | None:
    """Naivní razítko z databáze srovnané na UTC, aby se dalo odečítat."""
    if stamp is None:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


# ==============================================================================
# Vrstva: co o firmě řekl Mark Gomes
# ==============================================================================

def _gomes_mentions(
    db: Session, symbols: tuple[str, ...]
) -> list[tuple[TickerMention, AnalystTranscript]]:
    """
    Gomesovy výroky o firmě, nejnovější první.

    **Nefiltruje se na `is_current`, a je to schválně.** Sloupec zapisují dvě
    různá místa opačně: `scripts/backfill_transcripts.py:288` ukládá skutečné
    výroky s doslovným citátem jako `is_current=False`, kdežto
    `routes/gomes.py:723` zapisuje `is_current=True` na holé nálezy tickeru
    v textu — bez citátu, bez shrnutí, se sentimentem natvrdo NEUTRAL. Filtr
    na `is_current` by tedy vrátil prázdné řádky a skutečná tvrzení schoval.
    (Tahle past dnes tiše vyprazdňuje i `breakout_lookup.load_analyst_words`
    a `lifecycle_intake._analyst_stance`.)
    """
    rows = (
        db.query(TickerMention, AnalystTranscript)
        .join(AnalystTranscript, TickerMention.transcript_id == AnalystTranscript.id)
        .filter(TickerMention.ticker.in_(symbols))
        .filter(AnalystTranscript.source_name == "Mark Gomes")
        .order_by(desc(TickerMention.mention_date))
        .limit(MAX_GOMES_MENTIONS * 3)
        .all()
    )
    # Zmínka bez citátu i bez shrnutí nenese nic, co by kdo řekl. Udělat z ní
    # fakt by bylo vymýšlení s odkazem na zdroj.
    usable = [(m, t) for m, t in rows if m.context_snippet or m.key_points]
    return usable[:MAX_GOMES_MENTIONS]


def _mention_direction(mention: TickerMention) -> str:
    stance = verdict_stance(mention.action_mentioned)
    if stance == "NEUTRAL":
        stance = (mention.sentiment or "NEUTRAL").upper()
    if stance.endswith("BULLISH"):
        return DIR_PRO
    if stance.endswith("BEARISH"):
        return DIR_PROTI
    return DIR_NEUTRAL


def _gomes_layer(
    db: Session, symbols: tuple[str, ...], ids: _Ids, today: date
) -> tuple[list[Fact], list[Gap]]:
    facts: list[Fact] = []
    gaps: list[Gap] = []

    for mention, _transcript in _gomes_mentions(db, symbols):
        said = mention.mention_date
        age = (today - said).days if said else None

        summary = ""
        if mention.key_points:
            points = [str(p) for p in mention.key_points if p]
            summary = " ".join(points[:2])
        if not summary and mention.context_snippet:
            summary = mention.context_snippet[:240]

        line = f"Mark Gomes {cz_date(said)}: {summary}".strip()
        if mention.price_target:
            line += f" Zmíněný cíl {cz_num(float(mention.price_target), 2)}."
        # Stáří patří rovnou do věty. Bez něj se dva roky starý výrok čte jako
        # dnešní názor — a váha zmínky klesá s poločasem zhruba třiceti dnů.
        if age is not None and age > 60:
            line += f" (řečeno před {age} dny, váha {cz_num(mention.weight, 2)})"

        facts.append(
            Fact(
                id=ids.next(_PREFIX[LAYER_GOMES]),
                layer=LAYER_GOMES,
                text_cs=line,
                source=f"Mark Gomes, {cz_date(said)}",
                as_of=said,
                quote=mention.context_snippet,
                direction=_mention_direction(mention),
            )
        )

    if not facts:
        total = (
            db.query(AnalystTranscript)
            .filter(AnalystTranscript.source_name == "Mark Gomes")
            .count()
        )
        newest = (
            db.query(AnalystTranscript.date)
            .filter(AnalystTranscript.source_name == "Mark Gomes")
            .order_by(desc(AnalystTranscript.date))
            .first()
        )
        if total and newest and newest[0]:
            detail = (
                f"Máme {total} jeho přepisů, nejnovější z {cz_date(newest[0])}, "
                f"a v žádném o téhle firmě nemluví."
            )
        elif total:
            detail = f"Máme {total} jeho přepisů a v žádném o téhle firmě nemluví."
        else:
            detail = "Nemáme od něj zatím žádný přepis, ze kterého by šlo číst."
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_GOMES,
                text_cs=f"Mark Gomes tuhle firmu nezmínil. {detail}",
                fixable_cs=None if total else "Načíst přepisy",
            )
        )

    return facts, gaps


# ==============================================================================
# Vrstva: Breakout Investors — ukazuje se, neposlouchá se
# ==============================================================================

def _breakout_layer(
    db: Session, symbols: tuple[str, ...], ids: _Ids
) -> tuple[list[Fact], list[Gap]]:
    """
    Co o firmě říká druhý zdroj.

    **Každý fakt odsud je NEUTRAL, bez výjimky.** Rozhodnutí majitele
    z 23. 8. 2026 (viz `models/breakout.py:21-24`) je, že se tenhle zdroj
    ukazuje a neposlouchá: seškrábaný počet podpisů bez jmenovaného autora
    není stanovisko. Kdyby směl nést směr, protlačil by bod na stranu „pro"
    silou davu, který se pod nic nepodepsal.
    """
    facts: list[Fact] = []
    gaps: list[Gap] = []

    entry = (
        db.query(BreakoutWatchEntry)
        .filter(BreakoutWatchEntry.symbol.in_(symbols))
        .first()
    )
    if entry is None:
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_BREAKOUT,
                text_cs=(
                    "Na watchlistu Breakout Investors tahle firma není. "
                    "To o ní nic neříká — je to jen jejich výběr."
                ),
            )
        )
        return facts, gaps

    parts = [
        f"Breakout Investors ji drží na watchlistu, {entry.endorsements} podpisů"
    ]
    if entry.upside_ratio is not None:
        parts.append(
            f"očekávaný růst {cz_num(float(entry.upside_ratio) * 100, 0)} %"
        )
    if entry.implied_target is not None:
        parts.append(f"dopočtený cíl {cz_num(float(entry.implied_target), 2)}")

    facts.append(
        Fact(
            id=ids.next(_PREFIX[LAYER_BREAKOUT]),
            layer=LAYER_BREAKOUT,
            text_cs=(
                ", ".join(parts)
                + ". Je to druhý zdroj — ukazuje se, o velikosti pozice nerozhoduje."
            ),
            source="Breakout Investors (watchlist)",
            as_of=entry.last_seen_at.date() if entry.last_seen_at else None,
            direction=DIR_NEUTRAL,
        )
    )
    return facts, gaps


# ==============================================================================
# Vrstva: fundamenty
# ==============================================================================

#: Čtyři různé důvody, proč u firmy nejsou americké výkazy. Jen tři z nich
#: říkají něco o firmě; `LOOKUP_FAILED` je fakt o nás.
_COVERAGE_CS = {
    "NOT_AN_SEC_FILER": (
        "U SEC tahle firma nepodává — je to zahraniční listing, který se hlásí "
        "jinde. O firmě to neříká nic, jen to, že se audituje mimo americký rejstřík."
    ),
    "FOREIGN_PRIVATE_ISSUER": (
        "Firma u SEC podává, ale na zahraničním rozvrhu (20-F a 6-K), ne čtvrtletní "
        "10-Q. Čtvrtletní čísla proto nebudou, aniž by firma cokoli zamlčovala."
    ),
    "NOT_A_TICKER": (
        "Zadaný identifikátor vypadá jako ISIN, ne jako burzovní symbol. U SEC ho "
        "dohledat nelze — doplň symbol, pod kterým se s papírem obchoduje."
    ),
    "LOOKUP_FAILED": (
        "SEC se nepodařilo dosáhnout. To je fakt o nás, ne o firmě — po dalším "
        "pokusu může být pokrytí normální."
    ),
}


def _filing_staleness(fundamentals: Any | None, today: date) -> tuple[date, int] | None:
    """
    Jak staré je nejnovější čtvrtletí, ze kterého se počítají meziroční čísla.

    Existuje kvůli AST SpaceMobile: firma přestala tagovat tržby pod konceptem,
    který aplikace čte, takže série uvízla na čtvrtletí do 31. 3. 2023. Spis
    pak s naprostou jistotou tvrdil „tržby meziročně 0,0 % — pohyb sem tam,
    ještě to nikam nevystřelilo" u firmy, které mezitím tržby vyrostly na
    115 mil. za dvanáct měsíců. Rubrika fáze to číslo použila k zařazení.

    Tři roky staré číslo není chybějící údaj a nevypadá jako chyba — a právě
    proto je nebezpečnější než mezera.
    """
    if fundamentals is None:
        return None
    series = None
    try:
        series = fundamentals.get("revenue")
    except Exception:  # noqa: BLE001
        return None
    point = getattr(series, "latest_quarter", None) if series is not None else None
    if point is None or not getattr(point, "end", None):
        return None
    age = (today - point.end).days
    return (point.end, age) if age > STALE_FILING_DAYS else None

def _yahoo_row(db: Session, symbols: tuple[str, ...]) -> dict[str, Any] | None:
    """Poslední řádek cache kurzů. Malý SELECT, aby `build()` zůstal bez sítě."""
    try:
        row = (
            db.execute(
                text(
                    """
                    SELECT ticker, current_price, currency, company_name,
                           market_cap, revenue_ttm, net_income_ttm,
                           operating_margin, profit_margin, total_cash,
                           total_debt, market_data_updated, last_updated
                      FROM yahoo_finance_cache
                     WHERE ticker = ANY(:symbols)
                     ORDER BY last_updated DESC NULLS LAST
                     LIMIT 1
                    """
                ),
                {"symbols": list(symbols)},
            )
            .mappings()
            .first()
        )
    except Exception:  # noqa: BLE001 — chybějící cache není důvod shodit spis
        logger.warning("Cache kurzů se nepodařilo přečíst", exc_info=True)
        return None
    return dict(row) if row else None


def _has_market_data(yahoo: dict[str, Any] | None) -> bool:
    """
    Jestli o tom symbolu trh vůbec něco ví.

    Neúspěšné stažení po sobě nechá řádek v cache, takže „řádek existuje"
    neznamená „firma existuje". Rozhoduje kurz nebo jméno.
    """
    return bool(yahoo) and bool(yahoo.get("current_price") or yahoo.get("company_name"))


def _millions(value: Any) -> str:
    return cz_num(float(value) / 1e6, 1)


def _fundamentals_layer(
    db: Session,
    symbols: tuple[str, ...],
    yahoo: dict[str, Any] | None,
    fundamentals: Any | None,
    finnhub: Any | None,
    ids: _Ids,
    today: date | None = None,
) -> tuple[list[Fact], list[Gap]]:
    facts: list[Fact] = []
    gaps: list[Gap] = []

    stale = _filing_staleness(fundamentals, today or datetime.now(timezone.utc).date())
    if stale:
        end, age = stale
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_FUNDAMENTY,
                text_cs=(
                    f"Nejnovější čtvrtletí, které umíme z výkazů přečíst, končí "
                    f"{cz_date(end)} — je staré {age // 30} měsíců. Firma nejspíš "
                    f"přestala tagovat tržby pod položkou, kterou čteme. Meziroční "
                    f"čísla níž tedy nepopisují dnešek a nesmí se podle nich soudit."
                ),
                fixable_cs="Doplnit data",
            )
        )

    coverage = db.query(SecCoverage).filter(SecCoverage.ticker.in_(symbols)).first()
    if coverage is None:
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_FUNDAMENTY,
                text_cs="U SEC jsme se na tuhle firmu ještě nedívali.",
                fixable_cs="Doplnit data",
            )
        )
    elif coverage.status != "COVERED":
        # Symbol, pod kterým se ani neobchoduje, není zahraniční listing.
        # `NOT_AN_SEC_FILER` je u překlepu pravda o rejstříku, ne o firmě, a
        # věta „je to zahraniční listing" by z něj udělala existující podnik.
        if not _has_market_data(yahoo) and coverage.status == "NOT_AN_SEC_FILER":
            text_cs = (
                "Tenhle symbol se nepodařilo dohledat ani na burze, ani u SEC. "
                "Nejspíš je v něm překlep."
            )
        else:
            text_cs = _COVERAGE_CS.get(
                coverage.status,
                f"SEC hlásí stav {coverage.status}, který neumíme přeložit.",
            )
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_FUNDAMENTY,
                text_cs=text_cs,
                fixable_cs=(
                    "Doplnit data" if coverage.status == "LOOKUP_FAILED" else None
                ),
            )
        )

    # Nálezy z podání jsou nejsilnější „proti", jaké máme — nese je doslovný
    # citát z regulatorního dokumentu, ne něčí názor.
    for finding in (
        db.query(SecFinding)
        .filter(SecFinding.ticker.in_(symbols))
        .order_by(desc(SecFinding.id))
        .limit(5)
        .all()
    ):
        facts.append(
            Fact(
                id=ids.next(_PREFIX[LAYER_FUNDAMENTY]),
                layer=LAYER_FUNDAMENTY,
                text_cs=f"Z podání u SEC: {finding.fact_cs}",
                source="SEC — vlastní podání firmy",
                quote=finding.quote,
                direction=DIR_PROTI,
            )
        )

    if fundamentals is not None:
        for sentence in list(getattr(fundamentals, "findings", None) or [])[:10]:
            facts.append(
                Fact(
                    id=ids.next(_PREFIX[LAYER_FUNDAMENTY]),
                    layer=LAYER_FUNDAMENTY,
                    text_cs=str(sentence),
                    source="SEC XBRL",
                    direction=DIR_NEUTRAL,
                )
            )
        for sentence in list(getattr(fundamentals, "gaps", None) or [])[:10]:
            gaps.append(
                Gap(
                    id=ids.next(GAP_PREFIX),
                    layer=LAYER_FUNDAMENTY,
                    text_cs=str(sentence),
                )
            )

    if finnhub is not None and getattr(finnhub, "has_anything", False):
        bits = []
        if finnhub.revenue_yoy_pct is not None:
            bits.append(f"tržby meziročně {cz_num(finnhub.revenue_yoy_pct, 1)} %")
        if finnhub.gross_margin_pct is not None:
            bits.append(f"hrubá marže {cz_num(finnhub.gross_margin_pct, 1)} %")
        if finnhub.net_margin_pct is not None:
            bits.append(f"čistá marže {cz_num(finnhub.net_margin_pct, 1)} %")
        if bits:
            profitable = finnhub.is_profitable
            facts.append(
                Fact(
                    id=ids.next(_PREFIX[LAYER_FUNDAMENTY]),
                    layer=LAYER_FUNDAMENTY,
                    text_cs="Finnhub: " + ", ".join(bits) + ".",
                    source="Finnhub",
                    direction=(
                        DIR_NEUTRAL
                        if profitable is None
                        else DIR_PRO
                        if profitable
                        else DIR_PROTI
                    ),
                )
            )

    if _has_market_data(yahoo):
        bits = []
        if yahoo.get("market_cap"):
            bits.append(f"tržní kapitalizace {_millions(yahoo['market_cap'])} mil.")
        if yahoo.get("revenue_ttm"):
            bits.append(f"tržby za 12 měsíců {_millions(yahoo['revenue_ttm'])} mil.")
        if yahoo.get("total_cash") is not None:
            bits.append(f"hotovost {_millions(yahoo['total_cash'])} mil.")
        if yahoo.get("total_debt") is not None:
            bits.append(f"dluh {_millions(yahoo['total_debt'])} mil.")
        if bits:
            facts.append(
                Fact(
                    id=ids.next(_PREFIX[LAYER_FUNDAMENTY]),
                    layer=LAYER_FUNDAMENTY,
                    text_cs="Yahoo: " + ", ".join(bits) + ".",
                    source="Yahoo Finance (neauditované)",
                    direction=DIR_NEUTRAL,
                )
            )
    else:
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_FUNDAMENTY,
                text_cs="Nemáme ani základní tržní údaje — kurz, kapitalizaci, marže.",
                fixable_cs="Doplnit data",
            )
        )

    return facts, gaps


# ==============================================================================
# Vrstva: metodika
# ==============================================================================

#: Věty obou rubrik o meziročním růstu tržeb. Rubrika válců počítá čtvrtletí
#: proti témuž čtvrtletí loni z XBRL, rubrika fáze trailing dvanáct měsíců —
#: takže obě řeknou „tržby meziročně X %" a X se liší. U CVD Equipment to bylo
#: -61,8 % proti -77,8 % v jednom spisu, obojí bez uvedení období.
_REVENUE_SENTENCE = re.compile(r"tržby\s+meziročně", re.IGNORECASE)
_PERCENT = re.compile(r"(-?\d+[.,]\d+)\s*%")

#: Od kolika procentních bodů je rozdíl mezi dvěma čteními spor, ne zaokrouhlení.
REVENUE_DISAGREEMENT_PP = 5.0


#: Znaménko nese někdy slovo, ne minus: „pokles o 61,8 %" je záporné číslo
#: napsané kladně. Bez tohohle by se -77,8 % a „pokles o 61,8 %" porovnaly
#: jako rozdíl 139 bodů a věta o sporu by tvrdila, že jedno čtení roste.
_DECLINE_WORDS = ("pokles", "propad", "klesl", "spadl", "níž")


def _revenue_readings(facts: Sequence[Fact]) -> list[tuple[float, Fact]]:
    out: list[tuple[float, Fact]] = []
    for fact in facts:
        text = fact.text_cs
        if not _REVENUE_SENTENCE.search(text):
            continue
        m = _PERCENT.search(text)
        if not m:
            continue
        try:
            value = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        lowered = text.lower()
        if value > 0 and any(word in lowered for word in _DECLINE_WORDS):
            value = -value
        out.append((value, fact))
    return out


def _revenue_conflict(facts: Sequence[Fact]) -> str | None:
    """
    Dvě neslučitelná čtení téhož údaje pojmenovat, ne nechat vedle sebe.

    Dva různé procentní údaje se stejným úvodem „tržby meziročně" jsou pro
    čtenáře jedna věc řečená dvakrát špatně. Vybrat jeden a druhý zahodit by
    znamenalo rozhodnout za majitele, který zdroj platí; nechat oba bez
    varování znamená, že si vybere kdokoli, kdo to čte — včetně modelu.
    """
    readings = _revenue_readings(facts)
    if len(readings) < 2:
        return None
    lo = min(readings, key=lambda r: r[0])
    hi = max(readings, key=lambda r: r[0])
    if abs(hi[0] - lo[0]) < REVENUE_DISAGREEMENT_PP:
        return None
    return (
        f"Meziroční růst tržeb máme spočítaný dvakrát a čísla se neshodnou: "
        f"{cz_num(lo[0], 1)} % ({lo[1].source}) proti {cz_num(hi[0], 1)} % "
        f"({hi[1].source}). Měří jiné období — čtvrtletí proti čtvrtletí "
        f"a posledních dvanáct měsíců. Vezmi to z výkazů, ne ze souhrnu."
    )


def _confirmed_cylinders(
    lifecycle: StockLifecycleModel | None,
) -> tuple[int | None, datetime | None]:
    """
    Válce, které potvrdil člověk.

    Návrh potvrzením není: `cylinders_confirmed_at IS NULL` znamená, že číslo
    v řádku nikdo neodsouhlasil, a takové číslo nesmí vyrobit obchodovatelné
    pásmo. Stejné pravidlo jako `ladder_view._confirmed_cylinders`.
    """
    if lifecycle is None or lifecycle.cylinders_confirmed_at is None:
        return None, None
    return lifecycle.cylinders_count, _aware(lifecycle.cylinders_confirmed_at)


def _price_in_line_currency(
    price: float | None,
    price_currency: str | None,
    line_currency: str | None,
    fx_rate_to_czk: Callable[[str], float] | None,
) -> tuple[float | None, str | None]:
    """
    Cena přepočtená do měny čar. Vrací (cena, důvod selhání).

    Čtyři z pěti největších pozic obchodují v kanadských dolarech proti pásmu
    kótovanému na americkém listingu. Nepřepočítat je znamená spočítat skóre
    v cizích penězích — chyba o celý kurz.
    """
    if price is None or not line_currency or not price_currency:
        return price, None
    if price_currency.upper() == line_currency.upper():
        return price, None
    if fx_rate_to_czk is None:
        return None, (
            f"Kurz {price_currency} na {line_currency} nemáme čím přepočítat, "
            f"takže cenu nelze porovnat s čárami. Raději žádné skóre než skóre "
            f"v cizí měně."
        )
    try:
        converted = (
            price * fx_rate_to_czk(price_currency) / fx_rate_to_czk(line_currency)
        )
    except Exception:  # noqa: BLE001 — chybějící kurz = žádné skóre
        return None, (
            f"Kurz {price_currency} na {line_currency} neznáme, takže cenu nelze "
            f"porovnat s čárami. Raději žádné skóre než skóre v cizí měně."
        )
    return converted, None


def _method_layer(
    db: Session,
    ticker: str,
    symbols: tuple[str, ...],
    price: float | None,
    price_currency: str | None,
    fundamentals: Any | None,
    ids: _Ids,
    now: datetime,
    fx_rate_to_czk: Callable[[str], float] | None,
) -> tuple[list[Fact], list[Gap], MethodReading]:
    facts: list[Fact] = []
    gaps: list[Gap] = []

    band_row = (
        db.query(Stock)
        .filter(Stock.ticker.in_(symbols))
        .filter(Stock.source_key == InvestmentSource.GOMES.value)
        .filter(Stock.green_line.isnot(None))
        .order_by(desc(Stock.created_at))
        .first()
    )
    green = float(band_row.green_line) if band_row and band_row.green_line else None
    red = float(band_row.red_line) if band_row and band_row.red_line else None
    line_currency = band_row.line_currency if band_row else None

    if green is None or red is None:
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_METODIKA,
                text_cs=(
                    "Mark Gomes pro tuhle firmu nevydal zelenou a červenou čáru. "
                    "Bez nich metodika neumí spočítat pásmo ani limitní ceny — "
                    "je to mimo metodiku, ne špatná firma."
                ),
            )
        )
    else:
        facts.append(
            Fact(
                id=ids.next(_PREFIX[LAYER_METODIKA]),
                layer=LAYER_METODIKA,
                text_cs=(
                    f"Gomesovo pásmo: zelená {cz_num(green, 2)}, červená "
                    f"{cz_num(red, 2)} {line_currency or ''}".rstrip() + "."
                ),
                source="Mark Gomes — risk/reward tracker",
                direction=DIR_NEUTRAL,
            )
        )

    lifecycle_row = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker.in_(symbols))
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )
    confirmed, confirmed_at = _confirmed_cylinders(lifecycle_row)

    price_for_band, fx_problem = _price_in_line_currency(
        price, price_currency, line_currency, fx_rate_to_czk
    )
    if fx_problem:
        gaps.append(
            Gap(id=ids.next(GAP_PREFIX), layer=LAYER_METODIKA, text_cs=fx_problem)
        )

    reading = ZoneLadder.read(price_for_band, green, red, confirmed)

    cyl_proposal = None
    try:
        cyl_proposal = cylinder_intake.propose(db, ticker, fundamentals=fundamentals)
    except Exception:  # noqa: BLE001 — návrh je doplněk, ne podmínka spisu
        logger.warning("Návrh válců pro %s selhal", ticker, exc_info=True)

    if cyl_proposal is not None:
        for ev in cyl_proposal.evidence:
            facts.append(
                Fact(
                    id=ids.next(_PREFIX[LAYER_METODIKA]),
                    layer=LAYER_METODIKA,
                    text_cs=ev.fact_cs,
                    source=f"rubrika válců ({ev.source})",
                    as_of=ev.as_of,
                    direction=(
                        DIR_PRO
                        if ev.delta > 0
                        else DIR_PROTI
                        if ev.delta < 0
                        else DIR_NEUTRAL
                    ),
                )
            )
        for unknown in cyl_proposal.unknowns:
            gaps.append(
                Gap(id=ids.next(GAP_PREFIX), layer=LAYER_METODIKA, text_cs=unknown)
            )
        if cyl_proposal.runway_months is not None:
            facts.append(
                Fact(
                    id=ids.next(_PREFIX[LAYER_METODIKA]),
                    layer=LAYER_METODIKA,
                    text_cs=(
                        f"Hotovost vydrží zhruba "
                        f"{cz_num(cyl_proposal.runway_months, 0)} měsíců při "
                        f"současném tempu pálení."
                    ),
                    source="rubrika válců",
                    as_of=cyl_proposal.runway_as_of,
                    direction=(
                        DIR_PROTI
                        if cyl_proposal.runway_months < RUNWAY_TIGHT_MONTHS
                        else DIR_PRO
                    ),
                )
            )

    life_proposal = None
    try:
        life_proposal = lifecycle_intake.propose(db, ticker, fundamentals=fundamentals)
    except Exception:  # noqa: BLE001 — propose() nemá vyhazovat, ale spis to nesmí shodit
        logger.warning("Návrh fáze pro %s selhal", ticker, exc_info=True)

    if life_proposal is not None:
        for signal in life_proposal.signals:
            facts.append(
                Fact(
                    id=ids.next(_PREFIX[LAYER_METODIKA]),
                    layer=LAYER_METODIKA,
                    text_cs=signal.fact_cs,
                    source=f"rubrika fáze ({signal.source})",
                    as_of=signal.as_of,
                    direction=DIR_NEUTRAL,
                )
            )
        for unknown in life_proposal.unknowns:
            gaps.append(
                Gap(id=ids.next(GAP_PREFIX), layer=LAYER_METODIKA, text_cs=unknown)
            )
        if life_proposal.ratchet_note_cs:
            facts.append(
                Fact(
                    id=ids.next(_PREFIX[LAYER_METODIKA]),
                    layer=LAYER_METODIKA,
                    text_cs=life_proposal.ratchet_note_cs,
                    source="rubrika fáze (západka)",
                    direction=DIR_NEUTRAL,
                )
            )

    if confirmed is None:
        gaps.append(
            Gap(
                id=ids.next(GAP_PREFIX),
                layer=LAYER_METODIKA,
                text_cs=(
                    "Válce (0–10) u téhle firmy nikdo nepotvrdil. Je to jediný "
                    "vstup metodiky, který nestojí na žádném webu — je to úsudek "
                    "o kvalitě firmy. Bez něj nákupní brána nákup nepustí."
                ),
            )
        )

    # Podmíněné čtení: konkrétní číslo, po kterém majitel volá, aniž by se
    # z návrhu stal potvrzený údaj.
    #
    # Vydá se jen tehdy, když něco přidá — tedy když válce nikdo nepotvrdil
    # (a skutečné pásmo je proto neznámé), nebo když by se s návrhem pásmo
    # změnilo. Věta „kdyby válce byly 6, pásmo by bylo stejné jako teď" je
    # šum a majitel si výslovně stěžoval, že jich je v aplikaci moc.
    if_cylinders_cs = None
    proposed = cyl_proposal.cylinders if cyl_proposal else None
    if (
        proposed is not None
        and proposed != confirmed
        and green is not None
        and red is not None
        and price_for_band
    ):
        hypo = ZoneLadder.read(price_for_band, green, red, proposed)
        tells_something = confirmed is None or hypo.band is not reading.band
        if hypo.buy_below is not None and tells_something:
            if_cylinders_cs = (
                f"Kdyby válce byly {proposed} (návrh rubriky, nepotvrzeno), pásmo "
                f"by bylo „{hypo.band.value}“ a kupovalo by se pod "
                f"{cz_num(hypo.buy_below, 2)} {line_currency or ''}".rstrip() + "."
            )

    conflict = _revenue_conflict(facts)
    if conflict:
        gaps.append(
            Gap(id=ids.next(GAP_PREFIX), layer=LAYER_METODIKA, text_cs=conflict)
        )

    status_row = db.query(MarketStatus).first()
    market_alert = status_row.status.value if status_row else None
    alert_updated = _aware(status_row.last_updated if status_row else None)
    alert_stale = (
        True if alert_updated is None else (now - alert_updated) > STALE_ALERT_AFTER
    )

    gate_passed: bool | None = None
    gate_code: str | None = None
    gate_reason: str | None = None
    try:
        allowed, gate, reason = GomesGatekeeper.check_buy_guard(
            market_alert=market_alert,
            rr_score=reading.rr_score,
            deserved_score=reading.deserved,
            cylinders=confirmed,
            lifecycle_stage=life_proposal.effective_phase if life_proposal else None,
            rough_patch=bool(life_proposal.rough_patch) if life_proposal else False,
            cylinders_confirmed_at=confirmed_at,
        )
        gate_passed, gate_code, gate_reason = allowed, gate.value, reason
    except Exception:  # noqa: BLE001
        logger.warning("Nákupní brána pro %s selhala", ticker, exc_info=True)

    method = MethodReading(
        band=reading.band.value,
        band_reason_cs=reading.reason_cs,
        rr_score=reading.rr_score,
        deserved=reading.deserved,
        buy_below=reading.buy_below,
        sell_above=reading.sell_above,
        green_line=green,
        red_line=red,
        line_currency=line_currency,
        cylinders_confirmed=confirmed,
        cylinders_proposed=proposed,
        if_cylinders_cs=if_cylinders_cs,
        phase_proposed=life_proposal.effective_phase if life_proposal else None,
        phase_rough_patch=bool(life_proposal.rough_patch) if life_proposal else False,
        market_alert=market_alert,
        market_alert_stale=alert_stale,
        gate_passed=gate_passed,
        gate_code=gate_code,
        gate_reason=gate_reason,
    )
    return facts, gaps, method


# ==============================================================================
# Sestavení spisu
# ==============================================================================

def build(
    db: Session,
    ticker: str,
    *,
    symbol: str | None = None,
    note: str | None = None,
    fundamentals: Any | None = None,
    finnhub: Any | None = None,
    now: datetime | None = None,
    fx_rate_to_czk: Callable[[str], float] | None = None,
) -> Dossier:
    """
    Spis k jedné firmě z toho, co databáze už drží.

    **Nesahá na síť.** Firma, o které nikdo nikdy neslyšel, dá spis samých
    mezer — a to je skutečná odpověď, ne porucha. Síť obstarává `enrich()`,
    stejně jako u `cylinder_intake.propose(db, ticker, fundamentals=...)`.
    """
    moment = now or datetime.now(timezone.utc)
    today = moment.date()
    canonical = canonical_ticker(ticker)
    symbols = variants_of(ticker) or (ticker.upper(),)
    ids = _Ids()

    facts: list[Fact] = []
    gaps: list[Gap] = []

    # Vlastní úvaha jde do spisu první. Je to vstup, ne popisek — vysvětlovač
    # se k ní musí postavit, a na tom stojí celé to učení.
    if note and note.strip():
        facts.append(
            Fact(
                id=ids.next(_PREFIX[LAYER_VLASTNI]),
                layer=LAYER_VLASTNI,
                text_cs=f"Vlastní úvaha majitele: {note.strip()}",
                source="majitel",
                as_of=today,
                quote=note.strip(),
                direction=DIR_NEUTRAL,
            )
        )

    yahoo = _yahoo_row(db, symbols)
    price: float | None = None
    price_currency: str | None = None
    company_name: str | None = None
    price_is_stale = True

    if yahoo:
        price = float(yahoo["current_price"]) if yahoo.get("current_price") else None
        price_currency = yahoo.get("currency")
        company_name = yahoo.get("company_name")
        stamp = _aware(yahoo.get("market_data_updated") or yahoo.get("last_updated"))
        if stamp is not None:
            price_is_stale = (moment - stamp) > STALE_PRICE_AFTER
            if price is not None:
                facts.append(
                    Fact(
                        id=ids.next(_PREFIX[LAYER_TRH]),
                        layer=LAYER_TRH,
                        text_cs=(
                            f"Kurz {cz_num(price, 2)} {price_currency or ''} "
                            f"k {cz_date(stamp)}.".replace("  ", " ")
                        ),
                        source="Yahoo Finance",
                        as_of=stamp.date(),
                        direction=DIR_NEUTRAL,
                    )
                )
        if price_is_stale and price is not None:
            gaps.append(
                Gap(
                    id=ids.next(GAP_PREFIX),
                    layer=LAYER_TRH,
                    text_cs=(
                        "Kurz je starší než den — pásmo i limitní ceny z něj "
                        "spočítané jsou orientační."
                    ),
                    fixable_cs="Doplnit data",
                )
            )

    for layer_facts, layer_gaps in (
        _gomes_layer(db, symbols, ids, today),
        _breakout_layer(db, symbols, ids),
        _fundamentals_layer(db, symbols, yahoo, fundamentals, finnhub, ids, today),
    ):
        facts += layer_facts
        gaps += layer_gaps

    m_facts, m_gaps, method = _method_layer(
        db,
        canonical,
        symbols,
        price,
        price_currency,
        fundamentals,
        ids,
        moment,
        fx_rate_to_czk,
    )
    facts += m_facts
    gaps += m_gaps

    return Dossier(
        ticker=canonical,
        symbol=(symbol or ticker).upper(),
        company_name=company_name,
        as_of=moment,
        price=price,
        price_currency=price_currency,
        price_is_stale=price_is_stale,
        facts=tuple(facts),
        gaps=tuple(gaps),
        method=method,
    )


# ==============================================================================
# Načtení uloženého spisu
# ==============================================================================

def from_payload(payload: dict[str, Any]) -> Dossier:
    """
    Spis zpátky z JSONB, jak byl uložen k posudku.

    Existuje kvůli konkrétní chybě: vysvětlovač si spis skládal znovu, místo
    aby použil ten uložený — a protože se skládal bez výkazů, které měl sběr
    v ruce jen při zakládání, vysvětloval jinou sadu faktů, než jakou měl
    majitel na obrazovce. Model pak uvedl číslo, které v zobrazeném spisu
    nebylo, a kontrola citací ho přesto pustila, protože ve svém spisu ho
    měl. Vysvětlovat se smí jen to, co je zapsané.
    """
    method = payload.get("method") or {}
    return Dossier(
        ticker=payload.get("ticker", ""),
        symbol=payload.get("symbol", ""),
        company_name=payload.get("company_name"),
        as_of=_parse_dt(payload.get("as_of")) or datetime.now(timezone.utc),
        price=payload.get("price"),
        price_currency=payload.get("price_currency"),
        price_is_stale=bool(payload.get("price_is_stale", True)),
        facts=tuple(
            Fact(
                id=f["id"],
                layer=f.get("layer", ""),
                text_cs=f.get("text_cs", ""),
                source=f.get("source", ""),
                as_of=_parse_date(f.get("as_of")),
                quote=f.get("quote"),
                direction=f.get("direction", DIR_NEUTRAL),
            )
            for f in payload.get("facts", [])
        ),
        gaps=tuple(
            Gap(
                id=g["id"],
                layer=g.get("layer", ""),
                text_cs=g.get("text_cs", ""),
                fixable_cs=g.get("fixable_cs"),
            )
            for g in payload.get("gaps", [])
        ),
        method=MethodReading(
            band=method.get("band", "NEZNAME"),
            band_reason_cs=method.get("band_reason_cs", ""),
            rr_score=method.get("rr_score"),
            deserved=method.get("deserved"),
            buy_below=method.get("buy_below"),
            sell_above=method.get("sell_above"),
            green_line=method.get("green_line"),
            red_line=method.get("red_line"),
            line_currency=method.get("line_currency"),
            cylinders_confirmed=method.get("cylinders_confirmed"),
            cylinders_proposed=method.get("cylinders_proposed"),
            if_cylinders_cs=method.get("if_cylinders_cs"),
            phase_proposed=method.get("phase_proposed"),
            phase_rough_patch=bool(method.get("phase_rough_patch", False)),
            market_alert=method.get("market_alert"),
            market_alert_stale=bool(method.get("market_alert_stale", True)),
            gate_passed=method.get("gate_passed"),
            gate_code=method.get("gate_code"),
            gate_reason=method.get("gate_reason_cs") or method.get("gate_reason"),
        ),
    )


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


# ==============================================================================
# Sběr ze sítě — zdarma, ale pomalý
# ==============================================================================

def _cik_for(db: Session, symbol: str) -> str | None:
    """CIK z právě zapsaného řádku pokrytí."""
    row = (
        db.query(SecCoverage)
        .filter(SecCoverage.ticker.in_(variants_of(symbol) or (symbol.upper(),)))
        .first()
    )
    return row.cik if row else None


@dataclass
class Enriched:
    """Co se povedlo posbírat a co ne. Selhání se pojmenuje, netiší se."""

    fundamentals: Any | None = None
    finnhub: Any | None = None
    #: Jestli se pod tím symbolem vůbec něco obchoduje. False u překlepu.
    company_found: bool = False
    notes_cs: list[str] = field(default_factory=list)
    errors_cs: list[str] = field(default_factory=list)


def enrich(db: Session, ticker: str) -> Enriched:
    """
    Dotáhnout veřejná data pro ticker, o kterém aplikace zatím nic neví.

    Zdarma — **žádný jazykový model**. `sec_fundamentals.analyze_outlook()` se
    tady záměrně nevolá: je to placené čtení prózy z výkazu a tahle funkce běží
    bez tlačítka. Číselná vrstva z XBRL stačí a nic nestojí.

    Zapisuje jen do cache a pokrývacích tabulek (`yahoo_finance_cache`,
    `sec_coverage`, `sec_filings`, `insider_transactions`). Do žádné z tabulek,
    které krmí nákupní bránu, nesahá.

    Každý zdroj má vlastní `try` — jeden nedostupný web nesmí zastavit ostatní.
    """
    out = Enriched()
    symbol = ticker.upper().strip()

    try:
        from app.services.yahoo_cache import YahooFinanceCache

        data = YahooFinanceCache(db).get_stock_data(symbol, data_types=["all"])
        # Prázdný slovník i slovník bez kurzu a bez jména znamenají totéž:
        # pod tímhle symbolem se neobchoduje. Hlásit „načteno" jen proto, že
        # se vrátil objekt, je přesně to tiché úspěšné selhání, kvůli kterému
        # se překlep v tickeru tvářil jako existující firma.
        usable = bool(data) and bool(
            data.get("current_price") or data.get("company_name")
        )
        if usable:
            out.notes_cs.append("Tržní údaje z Yahoo načteny.")
            out.company_found = True
        else:
            out.errors_cs.append(
                f"Yahoo o symbolu {symbol} nic nevrátil — buď je v symbolu překlep, "
                f"nebo se pod ním neobchoduje."
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Yahoo pro %s selhalo", symbol, exc_info=True)
        out.errors_cs.append(f"Yahoo se nepodařilo načíst: {exc}")

    try:
        from app.services.sec_edgar import CoverageStatus, SecEdgarClient
        from app.services.sec_fundamentals import fetch_fundamentals
        from app.services.sec_sync import sync_ticker

        client = SecEdgarClient()

        # Přes `sync_ticker`, a ne přes holé `fetch_coverage`: ono to totiž
        # ZAPÍŠE řádek do `sec_coverage`. Bez toho zbytek aplikace o firmě dál
        # neví — `cylinder_intake.is_sec_covered()` se ptá téhle tabulky — a spis
        # by v jedné větě hlásil „výkazy načteny" a ve druhé „SEC na tuhle firmu
        # nedosáhne". Dvě protichůdná tvrzení, z nichž jedno je nepravdivé, je
        # přesně to, čemu se tady celou dobu vyhýbáme.
        #
        # `with_outlook=False` je natvrdo: čtení prózy z podání je placené volání
        # a tahle funkce běží bez tlačítka.
        report = sync_ticker(db, symbol, client=client, with_outlook=False, max_filings=2)
        status = report.status

        cik = _cik_for(db, symbol) if status == CoverageStatus.COVERED.value else None
        if cik:
            # Druhé čtení XBRL kvůli objektu `Fundamentals`, který `sync_ticker`
            # nevrací. SEC je zdarma a drží odstup 0,12 s — stojí to zlomek
            # vteřiny a nemusí se sahat do cizích privátních funkcí.
            out.fundamentals = fetch_fundamentals(symbol, cik, client=client)
            out.notes_cs.append("Výkazy z SEC XBRL načteny.")
        elif out.company_found:
            out.notes_cs.append(_COVERAGE_CS.get(status, f"SEC hlásí stav {status}."))
        else:
            # Symbol, pod kterým se nic neobchoduje, není zahraniční listing.
            # `NOT_AN_SEC_FILER` je u něj pravda o rejstříku, ne o firmě —
            # a vypsat ji jako větu o firmě znamená odpovědět na otázku, kterou
            # nikdo nepoložil.
            out.errors_cs.append(
                f"Symbol {symbol} se nepodařilo dohledat ani na burze, ani u SEC. "
                f"Zkontroluj, jestli v něm není překlep."
            )
        if report.error:
            out.errors_cs.append(report.error)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SEC pro %s selhalo", symbol, exc_info=True)
        out.errors_cs.append(f"SEC se nepodařilo načíst: {exc}")

    # Finnhub až když SEC nic nedal — je to slabší, neauditovaná vrstva, která
    # existuje kvůli kanadským jménům, na které EDGAR nevidí.
    if out.fundamentals is None:
        try:
            from app.services import finnhub_metrics

            out.finnhub = finnhub_metrics.fetch(symbol)
            if out.finnhub is not None and out.finnhub.has_anything:
                out.notes_cs.append("Doplňkové metriky z Finnhubu načteny.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Finnhub pro %s selhal", symbol, exc_info=True)
            out.errors_cs.append(f"Finnhub se nepodařilo načíst: {exc}")

    return out
