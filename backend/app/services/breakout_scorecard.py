"""
Jak si vedou cíle Breakout Investors — jediný zdroj, který jde ověřit.

Proč zrovna oni
---------------
Gomes dává čáru bez data splatnosti; ta se nedá vyvrátit, jen přečíst. Breakout
Investors dávají `upside_ratio` k okamžiku, kdy jsme jejich seznam poprvé viděli,
a z něj se dopočítá cílová cena. To je **padatelná předpověď**: za rok bude
zřejmé, jestli tam ta akcie došla, nebo ne.

Tenhle modul z toho ale **nedělá známku, dokud na ni není čas.** Jejich hlas
dnes v aplikaci žádnou váhu nemá (anonymní počet podpisů není stanovisko) a
tenhle soubor to nemění — jen zapíná hodiny, aby se za rok dalo rozhodnout
podloženě místo dojmem.

Tři pravidla, aby z toho nevznikl předčasný soud
------------------------------------------------
1. **Pod `MIN_HORIZON_DAYS` se úspěšnost nevydá vůbec.** Ne jako nula, ne jako
   „zatím 40 %" — nevydá se. Podíl spočítaný po týdnu měří šum a četl by se
   jako výsledek.
2. **Průměr posunů se nepočítá.** Osmadvacet jmen s rozptylem cílů od 6 % do
   186 % nemá smysluplný průměr; vrací se jednotlivé řádky a medián dnů.
3. **Jméno bez ceny se nezapočítá do jmenovatele.** Chybějící kurz není
   nesplněný cíl.

Startovní čára
--------------
Čte se `price_at_first_seen` / `target_at_first_seen`, ne `price_at_read` /
`implied_target`. Ty druhé přepisuje každý poll — proti nim by se měřilo od
včerejška a odpověď by vždy vyšla „skoro nic se nestalo". Viz
`migrations/add_breakout_first_reading.sql`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import median

from app.core.czech import n as cz_num
from app.core.czech import plural

#: Kolik dní musí uběhnout, než se o jejich trefě dá cokoli říct. Půl roku:
#: jejich cíle jsou implicitně víceměsíční a medián držby nápadu u Gomese je
#: 267 dní. Kratší horizont by měřil náladu trhu, ne jejich úsudek.
MIN_HORIZON_DAYS = 180


@dataclass(frozen=True)
class NameScore:
    """Jedno jméno od jejich prvního čtení po dnešek."""

    symbol: str
    days_watched: int
    price_then: float
    target_then: float
    price_now: float | None

    @property
    def upside_then_pct(self) -> float:
        return (self.target_then / self.price_then - 1.0) * 100.0

    @property
    def move_pct(self) -> float | None:
        """O kolik se kurz od prvního čtení hnul. `None` bez dnešní ceny."""
        if self.price_now is None:
            return None
        return (self.price_now / self.price_then - 1.0) * 100.0

    @property
    def progress_pct(self) -> float | None:
        """
        Kolik z cesty k cíli uběhlo. Záporné číslo = šlo to opačným směrem.

        `None`, když cíl neleží nad cenou — takový řádek nemá cestu, kterou by
        šlo měřit, a dělit nulou nebo záporem by vyrobilo číslo bez významu.
        """
        if self.price_now is None or self.target_then <= self.price_then:
            return None
        return (self.price_now - self.price_then) / (
            self.target_then - self.price_then
        ) * 100.0

    @property
    def reached(self) -> bool | None:
        if self.price_now is None or self.target_then <= self.price_then:
            return None
        return self.price_now >= self.target_then


@dataclass(frozen=True)
class Scorecard:
    names: tuple[NameScore, ...]
    #: Medián dnů, po které jejich cíle sledujeme.
    median_days: int | None
    #: True, dokud je na soud brzy. Pak jsou `reached_total` a spol. None.
    too_early: bool
    measurable: int
    reached_total: int | None
    verdict_cs: str

    def to_dict(self) -> dict:
        return {
            "median_days": self.median_days,
            "too_early": self.too_early,
            "measurable": self.measurable,
            "reached_total": self.reached_total,
            "min_horizon_days": MIN_HORIZON_DAYS,
            "verdict_cs": self.verdict_cs,
            "names": [
                {
                    "symbol": n.symbol,
                    "days_watched": n.days_watched,
                    "price_then": n.price_then,
                    "target_then": n.target_then,
                    "price_now": n.price_now,
                    "upside_then_pct": round(n.upside_then_pct, 1),
                    "move_pct": None if n.move_pct is None else round(n.move_pct, 1),
                    "progress_pct": (
                        None if n.progress_pct is None else round(n.progress_pct, 1)
                    ),
                    "reached": n.reached,
                }
                for n in self.names
            ],
        }


@dataclass(frozen=True)
class Reading:
    """Vstup pro jedno jméno. Čistý údaj, aby se rubrika dala testovat."""

    symbol: str
    first_seen_at: datetime | date | None
    price_at_first_seen: float | None
    target_at_first_seen: float | None
    price_now: float | None


def _as_date(value: datetime | date | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value


def build(readings: list[Reading], *, today: date | None = None) -> Scorecard:
    """
    Vysvědčení jejich cílů — nebo věta, proč se ještě nevydává.

    Nesahá na databázi ani na síť; `readings` dodá volající.
    """
    day = today or datetime.now(timezone.utc).date()

    names: list[NameScore] = []
    for r in readings:
        started = _as_date(r.first_seen_at)
        if (
            started is None
            or not r.price_at_first_seen
            or not r.target_at_first_seen
            or r.price_at_first_seen <= 0
        ):
            # Neúplný řádek se nezapočítá ani do jmenovatele. Chybějící vstup
            # není nesplněný cíl.
            continue
        names.append(
            NameScore(
                symbol=r.symbol,
                days_watched=max(0, (day - started).days),
                price_then=float(r.price_at_first_seen),
                target_then=float(r.target_at_first_seen),
                price_now=None if r.price_now is None else float(r.price_now),
            )
        )

    names.sort(key=lambda n: (-n.days_watched, n.symbol))
    med = int(median(n.days_watched for n in names)) if names else None
    measurable = sum(1 for n in names if n.reached is not None)

    if not names:
        return Scorecard(
            names=(),
            median_days=None,
            too_early=True,
            measurable=0,
            reached_total=None,
            verdict_cs=(
                "Žádné jejich jméno nemá zapsanou cenu a cíl z prvního čtení, "
                "takže není co měřit."
            ),
        )

    too_early = med is None or med < MIN_HORIZON_DAYS
    if too_early:
        chybi = MIN_HORIZON_DAYS - (med or 0)
        return Scorecard(
            names=tuple(names),
            median_days=med,
            too_early=True,
            measurable=measurable,
            reached_total=None,
            verdict_cs=(
                f"Jejich cíle sledujeme {med} {plural(med or 0, 'den', 'dny', 'dní')}. "
                f"Na to, jestli jim vycházejí, je brzy — úspěšnost se vydá až po "
                f"{MIN_HORIZON_DAYS} dnech, tedy zhruba za {chybi} "
                f"{plural(chybi, 'den', 'dny', 'dní')}. Do té doby jsou čísla níž "
                f"jen průběh, ne známka."
            ),
        )

    reached = sum(1 for n in names if n.reached)
    share = 0.0 if measurable == 0 else reached / measurable * 100.0
    return Scorecard(
        names=tuple(names),
        median_days=med,
        too_early=False,
        measurable=measurable,
        reached_total=reached,
        verdict_cs=(
            f"Z {measurable} měřitelných cílů jich {reached} akcie dosáhla "
            f"({cz_num(share, 0)} %). Medián sledování {med} "
            f"{plural(med, 'den', 'dny', 'dní')}."
        ),
    )
