"""
Vysvětlovač nálezu — jediné placené volání v celé téhle části aplikace.

Bere hotový spis (`find_dossier.Dossier`) a přeloží ho do dvou sloupců: co
mluví pro a co mluví proti. Ke každému bodu přidá pravidlo z kánonu, o které
se opírá, a větu „jak si to příště ověřím sám". To poslední je důvod, proč
funkce existuje — majitel se chce naučit akcie hodnotit, ne jen dostávat
verdikty.

**Co tenhle modul NEDĚLÁ, a je to důležitější než co dělá:**

- nevydá nákupní ani prodejní pokyn. Odpověď nákupní brány je spočítaná a stojí
  na obrazovce nad tímhle textem; model ji komentuje, neopravuje.
- nesepíše „co nevíme". Mezery renderuje aplikace doslova z `dossier.gaps`.
  Uvažování z nepřítomnosti dat je právě ta vada, kvůli které tahle appka
  třikrát vydala sebejistý verdikt na prázdno.
- nezapíše nic do `stock_lifecycle`, `stocks` ani `positions`.

**Ověřování je jádro souboru.** Každý bod musí citovat `fact_id` ze spisu. Bod,
který cituje neexistující fakt, je vymyšlené tvrzení s odkazem na zdroj — tedy
přesně selhání, proti kterému vznikl `claim_extraction.verify_claims()`, jen
s citací místo doslovného citátu. Takový bod se zahodí, spočítá a počet se
ukáže na obrazovce. Tiché zahazování je způsob, jak pojistka přestane být vidět.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Final, Sequence

from pydantic import BaseModel, Field

from app.services import llm
from app.services.find_dossier import (
    DIR_PRO,
    DIR_PROTI,
    GAP_PREFIX,
    Dossier,
    Fact,
)

logger = logging.getLogger(__name__)

SIDE_PRO = "PRO"
SIDE_PROTI = "PROTI"

WEIGHTS: Final[tuple[str, ...]] = ("ROZHODUJICI", "PODSTATNY", "DROBNY")

#: Model pro vysvětlení nálezu — a proč ne ten nejsilnější.
#:
#: Změřeno 24. 8. 2026 na tomtéž spisu (NVEC), kvalita hodnocena vlastními
#: kontrolami aplikace, ne dojmem:
#:
#:   Opus + přemýšlení   1438 in / 4449 out   79 s   6 bodů, 1 zahozen
#:   Opus bez přemýšlení 1438 in / 2880 out   52 s   6 bodů, 0 zahozeno
#:   Sonnet bez přemýšlení 1438 in / 3921 out 53 s   5 bodů, 0 zahozeno
#:   Haiku bez přemýšlení  4068 in / 1105 out 24 s   2 body, 2 zahozeny
#:
#: Haiku propadlo: jeden bod uvedl číslo, které v citovaném faktu nebylo, druhý
#: se opíral o mezeru. Sonnet prošel bez jediného zahozeného bodu a na téhle
#: firmě si všiml prodejů insiderů, které Opus nedal do shrnutí.
#:
#: Sonnet stojí zhruba šestinu toho co dnešní Opus s přemýšlením. Úlohu to
#: unese, protože vstup je strukturovaný spis, výstup je svázaný schématem a
#: každé tvrzení se pak strojově ověřuje — chybu tady chytá aritmetika, ne
#: čtenář. Tam, kde je úsudek modelu produktem (nálezy v podáních u SEC,
#: extrakce tvrzení z přepisu), zůstává Opus.
EXPLAIN_MODEL: Final[str] = llm.MODEL_MID

#: Přemýšlení se účtuje jako výstup a u odpovědi svázané schématem je to z velké
#: části placené rozmýšlení formulací. Vypnuto ušetřilo u Opusu třetinu výstupu
#: a nezhoršilo ani jednu kontrolu.
EXPLAIN_THINKING: Final[bool] = False

#: Nejvýš tolik bodů na stranu. Majitel má na rozhodnutí dvě minuty a jednu
#: obrazovku; desetibodový seznam není podklad, je to esej.
MAX_POINTS_PER_SIDE: Final[int] = 4

#: Kánon v kostce. Model smí odkazovat jen na tyhle klíče — odkaz na sekci,
#: která neexistuje, je ozdoba, ne opora, a `verify_points` ho zahodí.
#:
#: Drží se tady jako konstanta, a ne se nečte z těch dvou markdownů za běhu:
#: dohromady mají přes 600 řádků a model potřebuje pravidla, ne celý dokument.
#: Test hlídá, že každý klíč odpovídá skutečnému nadpisu v `docs/`.
CANON_DIGEST: Final[dict[str, str]] = {
    "§1": (
        "Investujeme, neobchodujeme. Držíme firmu, dokud platí důvod, proč jsme "
        "ji koupili — ne dokud se hýbe graf."
    ),
    "§2": (
        "Semafor řídí, kolik peněz smí být v akciích. Nakupuje se jen v zelené; "
        "v horších stupních se drží hotovost a zajištění."
    ),
    "§3": (
        "Tři fáze: objev (dělá dobré věci, trh to nevidí), čekání (nic se neděje, "
        "kapitál je vázaný) a zlatý důl (trh to konečně ocenil)."
    ),
    "§4a": (
        "R/R skóre je logaritmické: 10·log(červená/cena)/log(červená/zelená). "
        "Na zelené čáře je 10, na červené 0."
    ),
    "§4b": (
        "Zasloužené skóre = 10 − válce. Firma na deset válců si zaslouží dojít "
        "až k červené čáře; slabší firma musí být levnější, aby stála za nákup."
    ),
    "§5": (
        "Zisk se bere na maximech R/R. Kdo zdvojnásobil, prodá polovinu a dál "
        "hraje za peníze trhu. Tři body na škále od vstupu jsou spouštěč."
    ),
    "§6": (
        "Velikost pozice podle tieru: jádro do 10 %, druhá řada do 5 %, "
        "spekulace 1–2 %."
    ),
    "§7": (
        "Zákazy: žádné opce, nekupovat všechny tipy naráz, nakupovat jen "
        "v zelené a jen na atraktivní úrovni."
    ),
    "§V1": (
        "Zlatý důl je absorpční stav. Špatné čtvrtletí je přechodný útlum, ne "
        "návrat do fáze čekání."
    ),
    "§V2": "Velikost pozice je funkce R/R skóre, ne ploché procento na tier.",
    "§V3": (
        "Stupeň semaforu je valuace × znalost příčiny. Horší stupně potřebují "
        "pojmenovanou příčinu, jinak jsou to jen nervy."
    ),
    "§V5": (
        "Nehoň se za tipem, který je od vydání výrazně výš. V aplikaci tahle "
        "kontrola ZATÍM NENÍ — dělá se ručně."
    ),
    "§V6": (
        "Mrtvé peníze: devět měsíců držení a výnos pod deset procent znamená "
        "kapitál na dovolené. V aplikaci tahle kontrola ZATÍM NENÍ."
    ),
}


# ==============================================================================
# Tvar odpovědi
# ==============================================================================

class ExplainedPoint(BaseModel):
    """Jeden bod. Bez citace faktů se zahodí, takže citace není volitelná."""

    side: str = Field(description="PRO nebo PROTI")
    headline_cs: str = Field(description="Jedna věta česky, bez čísel mimo fakta")
    body_cs: str = Field(description="Jedna až tři věty, česky")
    fact_ids: list[str] = Field(
        description=(
            "Id faktů ze spisu, o která se bod opírá. Bod bez nich se zahodí. "
            "Nikdy neuváděj id začínající MEZ- — o mezerách nepíšeš."
        )
    )
    canon_ref: str = Field(description="Klíč z kánonu, např. §4b")
    check_yourself_cs: str = Field(
        description="Kde a jak si tenhle údaj příště ověřím sám. Jedna konkrétní věta."
    )
    weight: str = Field(description="ROZHODUJICI, PODSTATNY nebo DROBNY")


class Explanation(BaseModel):
    """
    Celá odpověď.

    Není tu žádné skóre a žádné pole „verdikt" — a je to konstrukční
    rozhodnutí. Kdyby existovalo, četlo by se jako doporučení a přebilo by
    odpověď nákupní brány, která je jediná spočítaná.
    """

    one_line_cs: str = Field(description="Jedna věta: kde ta firma stojí")
    points: list[ExplainedPoint] = Field(default_factory=list)
    own_reason_cs: str = Field(
        description=(
            "Jak obstála vlastní úvaha majitele proti faktům. Když ji data "
            "nepodporují, řekni to rovně."
        )
    )
    own_reason_verdict: str = Field(
        description="DRZI, NEDRZI nebo NELZE_POSOUDIT"
    )
    lesson_cs: str = Field(
        description="Jedna přenositelná věc, kterou se dá na téhle firmě naučit"
    )


class FindExplainError(RuntimeError):
    """Vysvětlení se nepovedlo. Nikdy se místo něj nevrací prázdný výsledek."""


@dataclass
class DroppedPoint:
    point: ExplainedPoint
    reason_cs: str


@dataclass
class ExplainResult:
    explanation: Explanation
    dropped: list[DroppedPoint] = field(default_factory=list)
    #: Souhrnné věty zadržené kvůli nedoloženému číslu.
    withheld_cs: list[str] = field(default_factory=list)
    model: str = EXPLAIN_MODEL

    @property
    def points_dropped(self) -> int:
        return len(self.dropped)

    @property
    def points_kept(self) -> int:
        return len(self.explanation.points)

    @property
    def anything_withheld(self) -> bool:
        return bool(self.dropped or self.withheld_cs)


# ==============================================================================
# Ověření — jádro modulu
# ==============================================================================

#: Desetinné číslo. Celá čísla se nekontrolují — v textu jich je plno ve
#: významu „tři body", „půl roku" a hlídat je by zahazovalo poctivé věty.
#: Vymyšlená čísla, která tuhle kontrolu vyvolala, byla shodou okolností
#: všechna desetinná: model napsal 77,8 %, kde spis říká 61,8 %.
_DECIMAL = re.compile(r"\d+[.,]\d+")

#: Rok není údaj o firmě.
_YEAR_RANGE = (1900.0, 2100.0)

#: Tolerance na zaokrouhlení. 61,8 a 61,75 je totéž číslo řečené jinak.
_ABS_TOLERANCE = 0.06
_REL_TOLERANCE = 0.005


def _numbers_in(text: str | None) -> list[float]:
    """Desetinná čísla v textu, se srovnanou desetinnou čárkou."""
    if not text:
        return []
    out: list[float] = []
    for raw in _DECIMAL.findall(text):
        try:
            out.append(float(raw.replace(",", ".")))
        except ValueError:
            continue
    return out


def _allowed_numbers(dossier: Dossier, facts: Sequence[Fact]) -> list[float]:
    """Čísla, která smí model použít: z citovaných faktů a ze čtení metodiky."""
    pool: list[float] = []
    for fact in facts:
        pool += _numbers_in(fact.text_cs)
        pool += _numbers_in(fact.quote)
    m = dossier.method
    for value in (
        m.rr_score, m.deserved, m.buy_below, m.sell_above,
        m.green_line, m.red_line, dossier.price,
    ):
        if value is not None:
            pool.append(float(value))
    pool += _numbers_in(m.band_reason_cs)
    pool += _numbers_in(m.if_cylinders_cs)
    return pool


def _is_supported(value: float, pool: Sequence[float]) -> bool:
    if _YEAR_RANGE[0] <= value <= _YEAR_RANGE[1] and float(value).is_integer():
        return True
    for allowed in pool:
        if abs(value - allowed) <= _ABS_TOLERANCE:
            return True
        if allowed and abs(value - allowed) / abs(allowed) <= _REL_TOLERANCE:
            return True
    return False


def unsupported_numbers(text: str, pool: Sequence[float]) -> list[float]:
    """
    Desetinná čísla, která v podkladech nejsou.

    Tohle je číselná obdoba `claim_extraction.verify_claims()`. Tam se ověřuje,
    že doslovný citát opravdu v přepisu je; tady, že číslo opravdu ve spisu je.
    Bez toho stačí modelu citovat platné `fact_id` a napsat u něj libovolné
    číslo — což se při prvním živém běhu skutečně stalo dvakrát.
    """
    return [n for n in _numbers_in(text) if not _is_supported(n, pool)]


def verify_points(
    points: Sequence[ExplainedPoint], dossier: Dossier
) -> tuple[list[ExplainedPoint], list[DroppedPoint]]:
    """
    Nechat jen body, které stojí na faktech, jež spis opravdu obsahuje.

    Pět kontrol, všechny mechanické — ani jedna není úsudek:

      1. `fact_ids` není prázdné. Bod bez citace je názor.
      2. Každé id je ve spisu. Id, které tam není, je vymyšlený fakt oblečený
         do citace.
      3. Žádné id nezačíná na `MEZ-`. Mezery vypisuje aplikace sama; model,
         který usuzuje z nepřítomnosti dat, je přesně to selhání, kvůli kterému
         je celá tahle část postavená tak, jak je.
      4. Bod „pro" cituje aspoň jeden fakt, který kód neoznačil za mluvící
         proti, a naopak. Tohle zastaví větu „hotovost vydrží čtyři měsíce,
         což je dobře".
      5. `canon_ref` je klíč z `CANON_DIGEST`.

    Vrací (ponechané, zahozené s důvodem). Zahozené se nikdy neukládají jako
    platné body — stejná kázeň jako `claim_extraction.verify_claims()`.
    """
    known = dossier.fact_ids()
    by_id: dict[str, Fact] = {f.id: f for f in dossier.facts}

    kept: list[ExplainedPoint] = []
    dropped: list[DroppedPoint] = []

    for point in points:
        side = (point.side or "").strip().upper()
        if side not in (SIDE_PRO, SIDE_PROTI):
            dropped.append(
                DroppedPoint(point, f"Neznámá strana „{point.side}“.")
            )
            continue

        ids = [i.strip() for i in (point.fact_ids or []) if i and i.strip()]
        if not ids:
            dropped.append(
                DroppedPoint(point, "Bod neuvádí žádný fakt, o který se opírá.")
            )
            continue

        gap_ids = [i for i in ids if i.upper().startswith(f"{GAP_PREFIX}-")]
        if gap_ids:
            dropped.append(
                DroppedPoint(
                    point,
                    f"Bod se opírá o mezeru ({', '.join(gap_ids)}), tedy o to, "
                    f"co nevíme.",
                )
            )
            continue

        unknown = [i for i in ids if i not in known]
        if unknown:
            dropped.append(
                DroppedPoint(
                    point,
                    f"Bod cituje fakt, který ve spisu není ({', '.join(unknown)}).",
                )
            )
            continue

        if point.canon_ref not in CANON_DIGEST:
            dropped.append(
                DroppedPoint(
                    point,
                    f"Odkaz na kánon „{point.canon_ref}“ neodpovídá žádné sekci.",
                )
            )
            continue

        # Strana bodu musí mít oporu: aspoň jeden citovaný fakt nesmí mířit
        # opačně, než bod tvrdí. Neutrální fakt oporu poskytuje — kontext do
        # obou stran patří.
        opposite = DIR_PROTI if side == SIDE_PRO else DIR_PRO
        supporting = [i for i in ids if by_id[i].direction != opposite]
        if not supporting:
            dropped.append(
                DroppedPoint(
                    point,
                    f"Bod na straně „{side}“ se opírá výhradně o fakta, která "
                    f"kód označil za mluvící opačně.",
                )
            )
            continue

        cited = [by_id[i] for i in ids]
        pool = _allowed_numbers(dossier, cited)
        invented = unsupported_numbers(
            f"{point.headline_cs} {point.body_cs}", pool
        )
        if invented:
            dropped.append(
                DroppedPoint(
                    point,
                    f"Bod uvádí číslo, které v citovaných faktech není "
                    f"({', '.join(f'{n:g}' for n in invented)}).",
                )
            )
            continue

        kept.append(point)

    return kept, dropped


def _trim_sides(points: Sequence[ExplainedPoint]) -> list[ExplainedPoint]:
    """Nejvýš čtyři body na stranu, nejtěžší první, pořadí jinak zachované."""
    order = {w: i for i, w in enumerate(WEIGHTS)}
    out: list[ExplainedPoint] = []
    for side in (SIDE_PRO, SIDE_PROTI):
        same = [p for p in points if p.side.strip().upper() == side]
        same.sort(key=lambda p: order.get(p.weight, len(WEIGHTS)))
        out.extend(same[:MAX_POINTS_PER_SIDE])
    return out


# ==============================================================================
# Prompt
# ==============================================================================

def build_system_prompt() -> str:
    """
    Systémový pokyn. Konstantní, takže ho `llm.complete` posílá s efemérní
    cache — druhý a další nález ten prefix neplatí znovu.
    """
    canon = "\n".join(f"  {key} — {text}" for key, text in CANON_DIGEST.items())
    return f"""\
Jsi vysvětlovač investičních podkladů pro jednoho člověka, který spravuje
skutečné rodinné peníze. Nejsi analytik a nerozhoduješ. Rozhodnutí už padlo
jinde: nákupní brána je spočítaná a stojí na obrazovce nad tvým textem.

Tvůj úkol je dvojí. Za prvé přeložit podklady do dvou sloupců — co mluví pro
a co mluví proti. Za druhé, a to je důležitější, u každého bodu napsat, jak
si ten údaj příště majitel ověří sám. Chce se na tom naučit akcie hodnotit.

ŽELEZNÁ PRAVIDLA

1. Každý bod cituje `fact_ids` ze spisu. Bod bez nich se zahodí — kontroluje
   to program, ne ty.
2. Nevymýšlej čísla. Číslo, které není doslova mezi fakty, nesmíš napsat —
   ani přepočítané, ani zaokrouhlené jinak. Kontroluje to program a bod
   s nedoloženým číslem zahodí. Potřebuješ-li poměr („skoro polovina",
   „dvojnásobek tržeb"), napiš ho slovy, ne novým číslem.
3. O mezerách nepiš. Vypisuje je aplikace sama a doslova; tvoje verze by je
   změkčila. Id začínající na {GAP_PREFIX}- do bodu nikdy nepatří.
4. Nedělej verdikt. Nepiš „kup", „prodej", „doporučuji", ani žádné skóre.
5. Nepřepisuj čtení metodiky. Pásmo, skóre a brána jsou spočítané; ty je
   vysvětluješ. Větu brány neopakuj — na obrazovce už jednou je.
6. Když pro jednu stranu nemáš ve faktech oporu, nech ji prázdnou. Prázdná
   strana je poctivá odpověď, vycpávka není.
7. K vlastní úvaze majitele se postav rovně. Když ji data nepodporují, napiš
   to. Lichotka je tu k ničemu.

KÁNON — na tyhle sekce se smíš odkazovat, na jiné ne:
{canon}

UČÍCÍ VRSTVA
`check_yourself_cs` je jádro celé funkce. Jmenuj konkrétní místo: položku ve
výkazu, pole na Yahoo, čáru na risk/reward grafu. Jedna věta a musí jít splnit
bez placeného nástroje.

REJSTŘÍK
Česky, profesionálně. Žádný telegrafický styl, žádné emoji, žádná anglická
zkratka bez vysvětlení. Nikdy nevypisuj syrovou hodnotu z databáze — piš
„mimo metodiku", ne MIMO_METODIKU; „žlutá", ne YELLOW. Desetinná čárka.

ROZSAH
Nejvýš {MAX_POINTS_PER_SIDE} body na stranu."""


def _render_facts(facts: Sequence[Fact]) -> str:
    lines = []
    for f in facts:
        mark = {DIR_PRO: "pro", DIR_PROTI: "proti"}.get(f.direction, "kontext")
        lines.append(f"[{f.id}] ({mark}; {f.source}) {f.text_cs}")
    return "\n".join(lines) if lines else "(žádná)"


def build_user_prompt(dossier: Dossier, *, note: str) -> str:
    m = dossier.method
    method_lines = [
        f"pásmo: {m.band} — {m.band_reason_cs}",
        f"R/R skóre: {m.rr_score}   zasloužené: {m.deserved}",
        f"válce potvrzené: {m.cylinders_confirmed}   návrh rubriky: {m.cylinders_proposed}",
        f"fáze (návrh): {m.phase_proposed}",
        f"nákupní brána: {'prošla' if m.gate_passed else 'nepustila'} — {m.gate_reason}",
    ]
    if m.if_cylinders_cs:
        method_lines.append(m.if_cylinders_cs)

    gaps = "\n".join(f"[{g.id}] {g.text_cs}" for g in dossier.gaps) or "(žádné)"

    return f"""\
FIRMA: {dossier.symbol}{f' — {dossier.company_name}' if dossier.company_name else ''}

VLASTNÍ ÚVAHA MAJITELE (proč si té firmy všiml):
{note.strip() or '(nenapsal nic)'}

FAKTA — jen na tahle id se smíš odkazovat:
{_render_facts(dossier.facts)}

MEZERY — NEPIŠ O NICH. Jsou tu, abys věděl, co ve faktech chybí, a nedomýšlel
si to. Odkaz na tahle id bod zneplatní.
{gaps}

ČTENÍ METODIKY — NEOPRAVUJ HO, vysvětli ho:
{chr(10).join(method_lines)}

Napiš dva sloupce bodů, postav se k úvaze majitele a přidej jednu větu, kterou
si z téhle firmy odnese do příštího nálezu."""


# ==============================================================================
# Volání
# ==============================================================================

def explain(
    dossier: Dossier,
    *,
    note: str = "",
    api_key: str | None = None,
    complete_json: Callable[..., dict[str, Any]] | None = None,
) -> ExplainResult:
    """
    Jedno placené volání: ze spisu udělá vysvětlení a ověří ho.

    `complete_json` se dá podstrčit, aby testy nikdy nesáhly na API.

    Raises:
        FindExplainError: když model neodpoví použitelně. Nikdy se místo toho
            nevrací prázdný výsledek — prázdné sloupce by se četly jako
            „nic pro ani proti", což je úplně jiné tvrzení než „nepovedlo se".
    """
    call = complete_json or llm.complete_json

    try:
        payload = call(
            build_user_prompt(dossier, note=note),
            model=EXPLAIN_MODEL,
            thinking=EXPLAIN_THINKING,
            system=build_system_prompt(),
            schema=llm.harden_schema(Explanation.model_json_schema()),
            api_key=api_key,
        )
    except llm.LLMError as exc:
        raise FindExplainError(f"Vysvětlení se nepodařilo získat: {exc}") from exc

    try:
        parsed = Explanation.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — pydantic ValidationError i cokoli jiného
        raise FindExplainError(
            f"Odpověď modelu nemá očekávaný tvar: {exc}"
        ) from exc

    kept, dropped = verify_points(parsed.points, dossier)
    if dropped:
        for item in dropped:
            logger.warning(
                "Bod zahozen (%s): %s", item.reason_cs, item.point.headline_cs
            )

    parsed.points = _trim_sides(kept)
    withheld = _scrub_summaries(parsed, dossier)
    return ExplainResult(
        explanation=parsed,
        dropped=dropped,
        withheld_cs=withheld,
        model=EXPLAIN_MODEL,
    )


#: Co se napíše místo shrnutí, které obsahovalo nedoložené číslo. Věta říká,
#: co se stalo — mlčení by se četlo jako „model nic neřekl".
_WITHHELD_CS = (
    "Shrnutí se nezobrazuje: obsahovalo číslo, které v podkladech není. "
    "Body výš prošly kontrolou a platí."
)


def _scrub_summaries(explanation: "Explanation", dossier: Dossier) -> list[str]:
    """
    Souhrnné věty nemají fact_ids, tak se měří proti celému spisu.

    Nedoložené číslo v nich se nedá „zahodit" jako bod — věta by zmizela beze
    stopy. Nahradí se proto větou, která přizná, co se stalo. Prohlašovat
    vymyšlené procento v závěru je nebezpečnější než v jednom z osmi bodů:
    závěr je to, co si člověk zapamatuje.
    """
    pool = _allowed_numbers(dossier, dossier.facts)
    withheld: list[str] = []
    for field_name in ("one_line_cs", "own_reason_cs", "lesson_cs"):
        text = getattr(explanation, field_name, "") or ""
        bad = unsupported_numbers(text, pool)
        if bad:
            logger.warning(
                "Shrnutí %s zadrženo, nedoložená čísla: %s", field_name, bad
            )
            setattr(explanation, field_name, _WITHHELD_CS)
            withheld.append(field_name)
    return withheld


def canon_text(ref: str) -> str:
    """
    Znění pravidla ke klíči.

    Model dodá odkaz, aplikace dodá slova — kánon se nepřevypravuje modelem.
    """
    return CANON_DIGEST.get(ref, "")
