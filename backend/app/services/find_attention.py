"""
Skóre pozornosti — kolik práce si vlastní nález zaslouží.

Proč to smí existovat, když `Explanation` skóre výslovně nemá
--------------------------------------------------------------
Vysvětlovač skóre nemá a mít nesmí, protože by ho psal model a četlo by se
jako doporučení. Tohle skóre odpovídá na **jinou otázku** než nákupní brána
a počítá ho kód:

    brána  → „smím to koupit?"       spočítaná, kanonická, dvouhodnotová
    skóre  → „mám tomu věnovat čas?"  pořadí mezi vlastními nápady

Ta otázka v aplikaci chyběla a nešla nahradit. U vlastního nálezu je pásmo
z definice `MIMO_METODIKU` (Gomes pro tu firmu nevydal čáry) a brána se
zastaví na semaforu dřív, než se podívá na firmu — takže obě věty, které stůl
ukazuje největším písmem, jsou u všech nálezů stejné. Dvanáct nápadů pak není
podle čeho seřadit.

Body a strop
------------
Vrací se dvojice `X / Y`: získané body a **dosažitelný strop**. Strop pod 100
znamená „tolik bodů o téhle firmě získat nejde, dokud nevíš tohle". Tím se
oddělí *slabá firma* (X nízké, Y vysoké) od *neprozkoumané firmy* (Y nízké) —
což dnes obojí splyne do „mimo metodiku" a čte se jako odmítnutí.

Šest pravidel, na kterých to stojí
----------------------------------
1. Skóre počítá kód, ne model. Vysvětlovač ho smí citovat, ne vyrobit.
2. Nikdy nestojí nad větou brány. Brána zůstává nadpis.
3. **Chybějící vstup nesnižuje skóre, snižuje strop** — a strop je vidět vždy.
   Přesně proti té vadě, kvůli které tahle aplikace vydala sebejistý verdikt
   na prázdno už poněkolikáté.
4. **Známá nepřítomnost je nula při plném stropu.** „Máme 61 přepisů a v žádném
   o ní nemluví" je odpověď → 0 bodů, strop zůstává. „Nemáme přepisy" je mezera
   → strop dolů. Tenhle rozdíl je celý rozdíl mezi skóre a hádáním.
5. Ukládá se s posudkem, append-only, a nepřepočítává se zpětně.
6. Nikdy se neukazuje bez věty, co ho drží nejvíc dole.

Čistá funkce spisu
------------------
`score()` nesahá na databázi ani na síť — bere `Dossier` (včetně jeho
`Signals`) a nic víc. Proto se dá spočítat i ze **starého uloženého** posudku
a proto se dá testovat na pevných číslech. Kdyby si chodila pro dnešní návrh
válců, znamenalo by to, že loňské čtení dostane dnešní data.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.czech import n as cz_num
from app.services.find_dossier import RUNWAY_TIGHT_MONTHS, Dossier

# ==============================================================================
# Váhy. Jsou to investiční rozhodnutí, ne konstanty — proto na jednom místě.
# ==============================================================================

KEY_OCENENI = "OCENENI"
KEY_PROVOZ = "PROVOZ"
KEY_KRYTI = "KRYTI"
KEY_NALEHAVOST = "NALEHAVOST"
KEY_TEZE = "TEZE"

MAX_OCENENI = 30.0
MAX_PROVOZ = 25.0
MAX_KRYTI = 15.0
MAX_NALEHAVOST = 15.0
MAX_TEZE = 15.0

TOTAL = MAX_OCENENI + MAX_PROVOZ + MAX_KRYTI + MAX_NALEHAVOST + MAX_TEZE

#: Kolik bodů dá ocenění přesně na zaslouženém skóre. Míň než polovina
#: záměrně: kánon kupuje až NAD zaslouženým, rovnost není příležitost.
OCENENI_AT_PAR = 12.0
#: O kolik bodů R/R nad zasloužené je plný počet. Tři je kanonický posun (§5).
OCENENI_FULL_GAP = 3.0
#: Strop ocenění, když je kurz starší než den. Pásmo se počítá z ceny a
#: z včerejší ceny se plné ocenění číst nedá.
OCENENI_STALE_CEILING = 20.0

#: Strop provozu, když rubrika válců číslo nevydala. Zbylých 15 bodů stojí na
#: čísle, které neexistuje; těch 10 stojí na důkazech, které existují.
PROVOZ_CEILING_WITHOUT_NUMBER = 10.0
#: Součet delt, při kterém je provoz plný, resp. nulový.
PROVOZ_FULL_DELTA = 4.0

#: Dva stropy krátké hotovosti. Runway je jediné pravidlo, které funguje i
#: u firmy, kterou metodika ocenit neumí — proto strhává, ne jen komentuje.
RUNWAY_CRITICAL_MONTHS = 6
RUNWAY_TIGHT_CAP = 0.40
RUNWAY_CRITICAL_CAP = 0.15

#: Naléhavost po dílech. Součet je `MAX_NALEHAVOST`.
NALEH_EARNINGS = 6.0
NALEH_INSIDER = 5.0
NALEH_FILING = 2.0
NALEH_MENTION = 2.0
#: Do kolika dnů je výsledkovka „teď". Měsíc: dřív se na ni nedá připravit.
EARNINGS_SOON_DAYS = 30
#: Do kolika dnů je Gomesova zmínka čerstvá zpráva, ne archiv.
MENTION_FRESH_DAYS = 30

#: Krytí po dílech. Součet je `MAX_KRYTI`.
#: Kadence nese většinu, protože je to jediná polovina, kterou pohání zdroj,
#: který metodika poslouchá. Shoda je bonus, ne stanovisko.
MAX_KADENCE = 10.0
#: Pět bodů za druhý zdroj, rozdělených podle toho, co za tím stojí.
#: Tři za to, že se na firmu dívají oba nezávisle; dva navíc, když je pod
#: tvrzením podepsaný člověk. Anonymní seznam sám nedá ani bod — od toho je
#: podmínka na `second_source_agrees`, která vyžaduje Gomesovo pokrytí.
SHODA_OBA_ZDROJE = 3.0
SHODA_JMENOVANY = 2.0
MAX_SHODA = SHODA_OBA_ZDROJE + SHODA_JMENOVANY
#: Kolik epizod za čtvrtletí je plná kadence. Šest: nejvíc, co kdy které jméno
#: mělo, je devět, a šest už znamená „vrací se k tomu skoro obden".
CADENCE_FULL_EPISODES = 6

TEZE_HOLDS = 15.0
TEZE_UNDECIDED = 5.0

#: Pod tímhle stropem se firma nedá s ničím srovnat a skóre se tak i popíše.
CEILING_TOO_LOW = 40.0
#: Od jakého podílu ze stropu to stojí za práci.
WORTH_WORK_RATIO = 0.60
QUIET_RATIO = 0.30
#: Nad tímhle stropem je „stojí za práci" tvrzení o firmě, ne o třech údajích.
CEILING_SOLID = 60.0

# Akce musí existovat na obrazovce, jinak je páka lež.
ACTION_REFRESH = "DOPLNIT_DATA"
ACTION_CONFIRM_CYLINDERS = "POTVRDIT_VALCE"
ACTION_EXPLAIN = "VYSVETLIT"


# ==============================================================================
# Tvar výsledku
# ==============================================================================

@dataclass(frozen=True)
class Pillar:
    """Jeden díl skóre: co se získalo, co ještě jde získat a co už ne."""

    key: str
    label_cs: str
    points: float
    #: Kolik jde v tomhle dílu vůbec získat při dnešní znalosti.
    ceiling: float
    #: Kolik by šlo získat, kdyby se vědělo všechno.
    max_points: float
    reason_cs: str
    #: Co chybí. `None` = nechybí nic, díl je plně dosažitelný.
    missing_cs: str | None = None
    #: Co s tím jde udělat. Musí odpovídat tlačítku, které na obrazovce je.
    action: str | None = None

    @property
    def unreachable(self) -> float:
        return max(0.0, self.max_points - self.ceiling)


@dataclass(frozen=True)
class Attention:
    points: float
    ceiling: float
    pillars: tuple[Pillar, ...] = ()
    verdict_cs: str = ""
    #: Věta „co by tím nejvíc pohnulo". Nikdy se skóre neukazuje bez ní.
    lever_cs: str | None = None
    lever_action: str | None = None
    #: Podmíněné čtení s navrženými válci. Věta, ne slib.
    if_cylinders_cs: str | None = None

    @property
    def ratio(self) -> float | None:
        """Podíl ze stropu. `None` při nulovém stropu — ne nula."""
        return None if self.ceiling <= 0 else self.points / self.ceiling

    def to_dict(self) -> dict:
        return {
            "points": round(self.points, 1),
            "ceiling": round(self.ceiling, 1),
            "total": TOTAL,
            "verdict_cs": self.verdict_cs,
            "lever_cs": self.lever_cs,
            "lever_action": self.lever_action,
            "if_cylinders_cs": self.if_cylinders_cs,
            "pillars": [
                {
                    "key": p.key,
                    "label_cs": p.label_cs,
                    "points": round(p.points, 1),
                    "ceiling": round(p.ceiling, 1),
                    "max_points": p.max_points,
                    "reason_cs": p.reason_cs,
                    "missing_cs": p.missing_cs,
                    "action": p.action,
                }
                for p in self.pillars
            ],
        }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ==============================================================================
# Pilíře
# ==============================================================================

def _oceneni(d: Dossier, *, cylinders: int | None, deserved: float | None) -> Pillar:
    """
    Jak levná je firma proti tomu, co si za svou kvalitu zaslouží (§4b).

    Potřebuje obojí — čáry i **potvrzené** válce. Návrh rubriky sem nesmí:
    zasloužené skóre spočítané z nepotvrzeného čísla je přesně ten sebejistý
    verdikt na prázdno, kterému se celá tahle část vyhýbá. Návrh se ukáže
    vedle, jako podmíněná věta.
    """
    m = d.method
    kw = dict(key=KEY_OCENENI, label_cs="Ocenění", max_points=MAX_OCENENI)

    if m.green_line is None or m.red_line is None:
        return Pillar(
            **kw,
            points=0.0,
            ceiling=0.0,
            reason_cs="Bez Gomesových čar se pásmo spočítat nedá.",
            missing_cs="Mark Gomes pro tuhle firmu nevydal zelenou a červenou čáru.",
        )
    if cylinders is None or deserved is None:
        return Pillar(
            **kw,
            points=0.0,
            ceiling=0.0,
            reason_cs="Čáry máme, ale bez válců není proti čemu skóre měřit.",
            missing_cs="Válce (0–10) u téhle firmy nikdo nepotvrdil.",
            action=ACTION_CONFIRM_CYLINDERS,
        )
    if m.rr_score is None:
        return Pillar(
            **kw,
            points=0.0,
            ceiling=0.0,
            reason_cs="Čáry i válce máme, ale chybí použitelný kurz.",
            missing_cs="Bez kurzu se R/R skóre nespočítá.",
            action=ACTION_REFRESH,
        )

    ceiling = OCENENI_STALE_CEILING if d.price_is_stale else MAX_OCENENI
    gap = m.rr_score - deserved
    raw = OCENENI_AT_PAR + (MAX_OCENENI - OCENENI_AT_PAR) * (gap / OCENENI_FULL_GAP)
    points = _clamp(raw, 0.0, ceiling)

    if gap > 0:
        note = f"o {cz_num(gap, 2)} bodu levnější, než si zaslouží"
    elif gap < 0:
        note = f"o {cz_num(abs(gap), 2)} bodu dražší, než si zaslouží"
    else:
        note = "přesně na zaslouženém, a kánon kupuje až nad ním"

    return Pillar(
        **kw,
        points=points,
        ceiling=ceiling,
        reason_cs=(
            f"R/R {cz_num(m.rr_score, 2)} proti zaslouženému "
            f"{cz_num(deserved, 1)} při {cylinders}/10 válcích — {note}."
        ),
        missing_cs=(
            "Kurz není čerstvý, a z včerejší ceny se plné ocenění číst nedá."
            if d.price_is_stale
            else None
        ),
        action=ACTION_REFRESH if d.price_is_stale else None,
    )


def _provoz(d: Dossier) -> Pillar:
    """
    Co firma vykázala, vážené podle toho, jestli to někdo podepsal.

    Tvrdý důkaz (`Evidence.is_hard` — XBRL, podání, Form 4, vlastní zpráva)
    jde plnou vahou, měkký poloviční. Krátká hotovost strop nesnižuje, ale
    body ano: je to jediné pravidlo, které platí i u firmy, kterou metodika
    ocenit neumí, a firma se sedmiměsíční hotovostí nemá stát v pořadí výš
    jen proto, že jinak vypadá slušně.
    """
    sig = d.signals
    kw = dict(key=KEY_PROVOZ, label_cs="Provoz", max_points=MAX_PROVOZ)

    if sig.cylinder_evidence_count == 0:
        return Pillar(
            **kw,
            points=0.0,
            ceiling=0.0,
            reason_cs="Rubrika válců nemá o firmě jediný údaj.",
            missing_cs="O provozu firmy nevíme nic — chybí výkazy.",
            action=ACTION_REFRESH,
        )

    has_number = d.method.cylinders_proposed is not None
    ceiling = MAX_PROVOZ if has_number else PROVOZ_CEILING_WITHOUT_NUMBER

    raw = sig.cylinder_hard_delta + 0.5 * sig.cylinder_soft_delta
    points = ceiling * _clamp(
        (raw + PROVOZ_FULL_DELTA) / (2 * PROVOZ_FULL_DELTA), 0.0, 1.0
    )

    runway_note = ""
    if sig.runway_months is not None:
        if sig.runway_months < RUNWAY_CRITICAL_MONTHS:
            points = min(points, ceiling * RUNWAY_CRITICAL_CAP)
            runway_note = (
                f" Hotovost na {cz_num(sig.runway_months, 0)} měsíců drží tenhle "
                f"díl dole bez ohledu na zbytek."
            )
        elif sig.runway_months < RUNWAY_TIGHT_MONTHS:
            points = min(points, ceiling * RUNWAY_TIGHT_CAP)
            runway_note = (
                f" Hotovost na {cz_num(sig.runway_months, 0)} měsíců drží tenhle "
                f"díl dole."
            )

    return Pillar(
        **kw,
        points=points,
        ceiling=ceiling,
        reason_cs=(
            f"{sig.cylinder_evidence_count} údajů z rubriky válců, z toho posun "
            f"{cz_num(sig.cylinder_hard_delta, 0)} z vykázaných čísel a "
            f"{cz_num(sig.cylinder_soft_delta, 0)} z měkkých zdrojů." + runway_note
        ),
        missing_cs=(
            None
            if has_number
            else "Rubrika válců z těch údajů číslo nesestavila — chybí jí vstupy."
        ),
    )


def _kryti(d: Dossier) -> Pillar:
    """
    Čím se Gomes právě zabývá, a jestli se na firmu dívá i druhý zdroj.

    **Měří se kadence, ne sentiment, a je to změřené rozhodnutí.** Pole
    `sentiment` je na 366 zmínkách 311× BULLISH, 45× NEUTRAL a 10× BEARISH,
    a z těch deseti jsou skutečně kritické dvě — zbytek jsou útržky
    z WhatsApp vlákna („So this was conducted right before the latest raise,
    correct? Correct") označené jako medvědí. Pole, které v 85 % říká totéž
    a ve zbytku se mýlí, neměří nic; `conviction_level` je na tom stejně
    (361× HIGH z 366). Kadence naproti tomu kolísá od 37 epizod po jednu
    a dá se ověřit spočítáním.

    **Ticho je zpráva, ne mezera.** Dvacet epizod o VTSI a půl roku nic je
    jiný stav než firma, o které nikdy nemluvil, a čte se jinak. Strop
    zůstává plný — ta odpověď zazněla.

    Breakout Investors sami o sobě nepřidají ani bod: seškrábaný počet
    podpisů bez jmenovaného autora není stanovisko. Body dá jen SHODA, tedy
    že se na firmu dívají oba zdroje nezávisle — což je přesně ten rozdíl,
    se kterým už počítá matice stropu pozic (dva zdroje 15 %, jeden 7 %).
    """
    sig = d.signals
    kw = dict(key=KEY_KRYTI, label_cs="Nezávislé krytí", max_points=MAX_KRYTI)

    if sig.gomes_transcripts_total == 0:
        return Pillar(
            **kw,
            points=0.0,
            ceiling=0.0,
            reason_cs="Nemáme od Marka Gomese jediný přepis, ze kterého by šlo číst.",
            missing_cs="Chybí přepisy — o krytí nevíme ani to, jestli chybí.",
        )

    said: list[str] = []
    points = 0.0

    if sig.gomes_episodes_total == 0:
        said.append(
            f"Máme {sig.gomes_transcripts_total} jeho přepisů a v žádném o téhle "
            f"firmě nemluví — to je odpověď, ne mezera"
        )
    elif sig.gomes_episodes_recent == 0:
        age = sig.gomes_newest_age_days
        aged = f"naposledy před {age} dny" if age is not None else "a přestal"
        said.append(
            f"Mluvil o ní v {sig.gomes_episodes_total} epizodách, {aged}. "
            f"Za poslední čtvrtletí ani jednou — ticho po pokrytí je taky zpráva"
        )
    else:
        points += MAX_KADENCE * _clamp(
            sig.gomes_episodes_recent / CADENCE_FULL_EPISODES, 0.0, 1.0
        )
        said.append(
            f"Za poslední čtvrtletí o ní mluvil v {sig.gomes_episodes_recent} "
            f"epizodách z {sig.gomes_episodes_total} celkem"
        )

    if sig.second_source_agrees:
        points += SHODA_OBA_ZDROJE
        said.append(
            f"dívají se na ni oba zdroje nezávisle (BI ji drží "
            f"s {sig.bi_endorsements} podpisy)"
        )
    elif sig.bi_on_watchlist:
        said.append(
            "je na watchlistu Breakout Investors, ale Gomes o ní nemluví — "
            "jeden zdroj, ne dva"
        )

    # Podepsané tvrzení je jiná váha než počet podpisů, a je to jediné místo,
    # kde Breakout skóre zvedne sám o sobě. Anonymní hlasování nikdy — pod
    # jménem stojí člověk ze seznamu, pod počtem podpisů nikdo.
    if sig.bi_named_claims:
        points += SHODA_JMENOVANY
        said.append(
            f"a napsal o ní jmenovaný analytik BI "
            f"({sig.bi_named_claims}× doslova, citáty jsou v podkladech)"
        )

    return Pillar(
        **kw,
        points=points,
        ceiling=MAX_KRYTI,
        reason_cs=". ".join(part[0].upper() + part[1:] for part in said if part) + ".",
    )


def _nalehavost(d: Dossier) -> Pillar:
    """
    Proč zrovna teď, a ne za tři měsíce.

    Bez data výsledků se strop snižuje: „nevíme kdy" není totéž co „daleko",
    a kdyby to skóre počítalo jako daleko, tichá mezera by vypadala jako klid.
    """
    sig = d.signals
    kw = dict(key=KEY_NALEHAVOST, label_cs="Naléhavost", max_points=MAX_NALEHAVOST)

    ceiling = MAX_NALEHAVOST
    points = 0.0
    said: list[str] = []

    if sig.earnings_known and sig.earnings_days is not None:
        if 0 <= sig.earnings_days <= EARNINGS_SOON_DAYS:
            points += NALEH_EARNINGS
            said.append(
                f"výsledky za {sig.earnings_days} dní"
                + ("" if sig.earnings_confirmed else " (odhad)")
            )
        else:
            said.append(f"výsledky až za {sig.earnings_days} dní")
    else:
        ceiling -= NALEH_EARNINGS

    if sig.insider_buy_recent:
        points += NALEH_INSIDER
        said.append("insider nedávno nakupoval")
    if sig.filings_fresh:
        points += NALEH_FILING
        said.append("výkazy jsou čerstvé")
    if (
        sig.gomes_newest_age_days is not None
        and sig.gomes_newest_age_days <= MENTION_FRESH_DAYS
    ):
        points += NALEH_MENTION
        said.append("Gomes o ní mluvil tento měsíc")

    return Pillar(
        **kw,
        points=min(points, ceiling),
        ceiling=ceiling,
        reason_cs=(
            ", ".join(said).capitalize() + "." if said else "Nic, co by tlačilo na čas."
        ),
        missing_cs=(
            None
            if sig.earnings_known
            else "Nevíme, kdy firma vykáže — a to není totéž co „vykáže daleko“."
        ),
    )


def _teze(verdict: str | None) -> Pillar:
    """
    Jak obstála tvoje vlastní věta proti faktům.

    Bez vysvětlení se strop snižuje o celý díl. Je to zároveň jediná páka
    v téhle rubrice, která stojí peníze, takže to musí být napsané u ní.
    """
    kw = dict(key=KEY_TEZE, label_cs="Tvoje teze", max_points=MAX_TEZE)

    if not verdict:
        return Pillar(
            **kw,
            points=0.0,
            ceiling=0.0,
            reason_cs="Nález ještě nemá vysvětlení, takže úvaha nebyla porovnaná.",
            missing_cs="Vysvětlení chybí — je to jediné placené volání v Nálezech.",
            action=ACTION_EXPLAIN,
        )
    if verdict == "DRZI":
        return Pillar(
            **kw,
            points=TEZE_HOLDS,
            ceiling=MAX_TEZE,
            reason_cs="Tvoje úvaha proti faktům obstála.",
        )
    if verdict == "NEDRZI":
        return Pillar(
            **kw,
            points=0.0,
            ceiling=MAX_TEZE,
            reason_cs="Fakta tvoji úvahu nepodpořila. Nula proto, že odpověď zazněla.",
        )
    return Pillar(
        **kw,
        points=TEZE_UNDECIDED,
        ceiling=MAX_TEZE,
        reason_cs="Tvoji úvahu nešlo z dostupných faktů posoudit.",
    )


# ==============================================================================
# Skóre
# ==============================================================================

def _verdict(points: float, ceiling: float) -> str:
    if ceiling < CEILING_TOO_LOW:
        return (
            "Aplikace o téhle firmě neví dost na to, aby ji uměla s čímkoli "
            "srovnat. Nízké skóre tady není soud o firmě."
        )
    ratio = 0.0 if ceiling <= 0 else points / ceiling
    if ratio >= WORTH_WORK_RATIO and ceiling >= CEILING_SOLID:
        return "Stojí za práci teď."
    if ratio >= WORTH_WORK_RATIO:
        return "To málo, co víme, sedí. Doplň, co chybí, a půjde to srovnat."
    if ratio >= QUIET_RATIO:
        return "Zatím nic naléhavého."
    return "Zatím nic, co by za práci stálo."


def _lever(pillars: tuple[Pillar, ...]) -> tuple[str | None, str | None]:
    """
    Co by skóre nejvíc pohnulo: díl s největším nedosažitelným kusem.

    Vrací se i tehdy, když na to tlačítko není — pak je to věta „tohle už
    nezískáš", a ta je stejně cenná jako úkol, protože zastaví hledání.
    """
    blocked = [p for p in pillars if p.unreachable > 0 and p.missing_cs]
    if not blocked:
        return None, None
    worst = max(blocked, key=lambda p: p.unreachable)
    return (
        f"{worst.missing_cs} Je v tom {cz_num(worst.unreachable, 0)} bodů, "
        f"které se jinak získat nedají.",
        worst.action,
    )


#: Co se ukáže u posudku, který vznikl dřív, než rubrika existovala.
NOT_SCORED_CS = (
    "Tenhle posudek je z doby před skóre a nemá zapsané vstupy, ze kterých se "
    "počítá. Spočítat ho z dnešních dat by znamenalo dát staršímu čtení dnešní "
    "čísla, takže se nepočítá vůbec."
)
NOT_SCORED_LEVER_CS = (
    "Dotáhni data — nový posudek už skóre ponese. Starý se zpětně nepřepisuje."
)


def not_scored() -> Attention:
    """
    Odpověď „tenhle posudek skóre nemá", jako objekt.

    Existuje kvůli řádkům zapsaným dřív, než rubrika vznikla. Kdyby se u nich
    prostě nic nevykreslilo, obrazovka by mlčela a majitel by nevěděl, jestli
    skóre chybí, nebo je nulové. Tohle není skóre spočítané zpětně — je to
    věta, proč spočítané není, plus jediné tlačítko, které s tím něco udělá.
    """
    return Attention(
        points=0.0,
        ceiling=0.0,
        verdict_cs=NOT_SCORED_CS,
        lever_cs=NOT_SCORED_LEVER_CS,
        lever_action=ACTION_REFRESH,
    )


def score(dossier: Dossier, *, own_reason_verdict: str | None = None) -> Attention:
    """
    Skóre pozornosti k jednomu spisu.

    `own_reason_verdict` je z vysvětlení, které vzniká až po spisu — proto je
    to argument, a ne další pole `Signals`. Dokud se nález nenechá vysvětlit,
    je `None` a ten díl je nedosažitelný.

    **Posudek bez zapsaných signálů se neskóruje.** Prázdné `Signals` neznamená
    „nula ze všeho": u prvního nálezu by rubrika napsala „nemáme od Gomese
    jediný přepis" u firmy, jejíž vlastní spis o dva odstavce výš hlásí, že
    jich máme 61. Chybějící vstup se nesmí stát tvrzením — ani tady, kde by to
    bylo jen o skóre.
    """
    if not dossier.signals.recorded:
        return not_scored()

    m = dossier.method
    pillars = (
        _oceneni(dossier, cylinders=m.cylinders_confirmed, deserved=m.deserved),
        _provoz(dossier),
        _kryti(dossier),
        _nalehavost(dossier),
        _teze(own_reason_verdict),
    )
    points = sum(p.points for p in pillars)
    ceiling = sum(p.ceiling for p in pillars)
    lever_cs, lever_action = _lever(pillars)

    return Attention(
        points=points,
        ceiling=ceiling,
        pillars=pillars,
        verdict_cs=_verdict(points, ceiling),
        lever_cs=lever_cs,
        lever_action=lever_action,
        if_cylinders_cs=_if_cylinders(dossier, pillars),
    )


def _if_cylinders(dossier: Dossier, pillars: tuple[Pillar, ...]) -> str | None:
    """
    Kolik by to bylo, kdyby se návrh rubriky potvrdil.

    Stejná kázeň jako u pásma ve spisu: konkrétní číslo, po kterém majitel
    volá, ale nikdy ne jako potvrzený údaj. Vydá se jen tehdy, když je co
    dopočítat — věta „bylo by to stejně" je šum.
    """
    m = dossier.method
    proposed = m.cylinders_proposed
    if m.cylinders_confirmed is not None or proposed is None:
        return None
    if m.green_line is None or m.red_line is None or m.rr_score is None:
        return None

    hypo = _oceneni(dossier, cylinders=proposed, deserved=10.0 - proposed)
    if hypo.ceiling <= 0:
        return None

    rest_points = sum(p.points for p in pillars if p.key != KEY_OCENENI)
    rest_ceiling = sum(p.ceiling for p in pillars if p.key != KEY_OCENENI)
    return (
        f"Kdyby se válce potvrdily na {proposed} (návrh rubriky, nepotvrzeno), "
        f"bylo by to {cz_num(rest_points + hypo.points, 0)} "
        f"z {cz_num(rest_ceiling + hypo.ceiling, 0)}."
    )
