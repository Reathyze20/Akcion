"""
Any pasted source → structured, attributed, verifiable claims.

The owner pastes whatever he can get his hands on: a day's WhatsApp excerpt
from the Breakout Investors group, a Mark Gomes video transcript, a company
earnings call, a news article. This turns that into rows the rest of the app
can reason over.

Why source type matters
-----------------------
These are not equally strong evidence and must never be flattened into one
"the AI says". An earnings call is the company stating its own numbers — a
primary source, and the direct input to canon gates like "cash runway under
6 months blocks a buy". A Gomes video is the analyst the whole method is
built on. A group member's message is peer commentary. `source_key` carries
that distinction into the dual-source position cap in core/sources.py
(AGREE <=15% / SINGLE <=7% / CONFLICT <=5%).

The anti-hallucination guard
----------------------------
Every claim must carry the verbatim text it came from, and `verify_claims`
checks that string actually occurs in the submitted source. Claims that fail
are dropped, not stored. This is deliberately enforced in code rather than in
the prompt: a prompt is an instruction a model may drift from, a substring
check is arithmetic. The failure this prevents — a confident, well-formatted
claim that a company announced something it never announced — is exactly the
kind that would cost real money.

Sentiment can never create a buy
--------------------------------
Extraction records what was said and how strongly. It does not produce
verdicts. A BUY still requires the canon gates (Green market, R/R score above
deserved, known cylinders, not Wait-Time) evaluated by GomesGatekeeper. An
enthusiastic message moves nothing on its own — see docs/GOMES_METHODOLOGY_CANON.md §7.
"""

from __future__ import annotations

import re
from enum import Enum

from loguru import logger
from pydantic import BaseModel, Field

from app.core.sources import InvestmentSource


class SourceType(str, Enum):
    """What kind of document was pasted."""

    WHATSAPP_GROUP = "WHATSAPP_GROUP"
    GOMES_VIDEO = "GOMES_VIDEO"
    EARNINGS_CALL = "EARNINGS_CALL"
    NEWS = "NEWS"
    OTHER = "OTHER"


class ClaimType(str, Enum):
    """
    What kind of statement this is.

    Only FACT (and the structured RR_LINES / TRADE_DISCLOSURE / MARKET_ALERT
    variants) may move a thesis. OPINION is recorded for context and for
    cross-source agreement, never as evidence about the business.
    """

    FACT = "FACT"                        # a checkable statement about the business
    OPINION = "OPINION"                  # a view, a conviction, a price feeling
    TRADE_DISCLOSURE = "TRADE_DISCLOSURE"  # "I publicly closed it out at $6.61"
    RR_LINES = "RR_LINES"                # stated green/red/grey levels or cylinders
    MARKET_ALERT = "MARKET_ALERT"        # a statement about the overall market light


class ThesisImpact(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    BREAKS = "BREAKS"        # a disqualifying event — dilution, going concern, ...
    NEUTRAL = "NEUTRAL"


class ExtractedNumber(BaseModel):
    """A figure stated in the source, kept with its units and its wording."""

    label: str = Field(description="What it measures, e.g. 'revenue H1', 'cash', 'gross margin'")
    value: float
    unit: str | None = Field(default=None, description="USD, %, months, shares, ...")
    period: str | None = Field(default=None, description="Q2 2026, H1, FY25, ... if stated")


class ExtractedClaim(BaseModel):
    """One statement about one ticker, traceable to the exact text it came from."""

    ticker: str = Field(description="Ticker as written in the source, e.g. DBOXF")
    company_hint: str | None = Field(
        default=None,
        description="Company name if stated — used to reconcile DBOX/DBOXF/DBO.TO to one company",
    )
    speaker: str = Field(description="Who said it, as the source names them. Never a phone number.")
    claim_type: ClaimType
    stance: str = Field(description="BULLISH, BEARISH or NEUTRAL")
    thesis_impact: ThesisImpact
    summary: str = Field(description="One sentence, in Czech, stating what was claimed")
    verbatim_quote: str = Field(
        description=(
            "The EXACT text from the source this claim is drawn from, copied "
            "character for character. Never paraphrased. A claim whose quote "
            "does not occur in the source is discarded."
        )
    )
    numbers: list[ExtractedNumber] = Field(default_factory=list)
    price_mentioned: float | None = Field(
        default=None, description="A specific price level stated, if any"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="0-1, how unambiguous the claim is")


class ExtractionResult(BaseModel):
    """Everything worth keeping from one pasted document."""

    claims: list[ExtractedClaim] = Field(default_factory=list)
    detected_tickers: list[str] = Field(default_factory=list)
    discarded_as_noise: int = Field(
        default=0, description="Messages/passages judged to carry no investment content"
    )
    notes: str | None = Field(default=None, description="Anything the owner should know about this source")


# ==============================================================================
# Speaker -> source authority
# ==============================================================================

def resolve_source_key(speaker: str | None, source_type: SourceType) -> str:
    """
    Map a speaker to the authority their claim carries.

    An earnings call is the company speaking about itself — a primary source
    that outranks any commentary, whoever is at the microphone. In the group
    chat Mark Gomes posts alongside everyone else, so the same paste yields
    both GOMES and BREAKOUT_INVESTORS rows; that is what makes cross-source
    agreement computable from a single document.
    """
    if source_type is SourceType.EARNINGS_CALL:
        return "COMPANY"
    if source_type is SourceType.NEWS:
        return "MEDIA"
    if source_type is SourceType.GOMES_VIDEO:
        return InvestmentSource.GOMES.value

    s = (speaker or "").strip().lower()
    if "gomes" in s or "money mark" in s:
        return InvestmentSource.GOMES.value
    if source_type is SourceType.WHATSAPP_GROUP:
        return InvestmentSource.BREAKOUT_INVESTORS.value
    return InvestmentSource.OTHER.value


# ==============================================================================
# The guard
# ==============================================================================

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Collapse whitespace so a quote survives copy/line-wrap differences."""
    return _WS.sub(" ", text).strip().lower()


def verify_claims(
    claims: list[ExtractedClaim], source_text: str
) -> tuple[list[ExtractedClaim], list[ExtractedClaim]]:
    """
    Keep only claims whose verbatim quote actually occurs in the source.

    Whitespace is normalized on both sides — a quote that differs only by a
    line break is the same quote — but the words themselves must be present,
    in order. Nothing else is forgiven.

    Returns:
        (verified, rejected)
    """
    haystack = _normalize(source_text)
    verified: list[ExtractedClaim] = []
    rejected: list[ExtractedClaim] = []

    for claim in claims:
        quote = _normalize(claim.verbatim_quote)
        if quote and quote in haystack:
            verified.append(claim)
        else:
            rejected.append(claim)
            logger.warning(
                "Claim rejected — quote not found in source: {} / {!r}",
                claim.ticker, claim.verbatim_quote[:80],
            )

    return verified, rejected


# ==============================================================================
# Prompting
# ==============================================================================

_BASE_RULES = """\
Jsi extrakční vrstva investiční aplikace, která spravuje SKUTEČNÉ rodinné peníze.
Tvým úkolem NENÍ radit, co koupit nebo prodat. Tvým úkolem je přesně zaznamenat,
co ve zdroji zaznělo, komu to patří a jestli je to fakt nebo názor.

ŽELEZNÁ PRAVIDLA:

1. DOSLOVNÝ CITÁT. Ke každému tvrzení uveď `verbatim_quote` — přesný text ze
   zdroje, znak po znaku. Nikdy neparafrázuj. Tvrzení, jehož citát se ve zdroji
   nenajde, se zahodí (kontroluje se programově, ne tebou).

2. FAKT vs. NÁZOR. Toto je nejdůležitější rozlišení.
   - FACT = ověřitelné tvrzení o podnikání. "tržby vzrostly o 88 % na 261 M$",
     "drží přes 1 mld. $ v hotovosti", "CEO odstoupil", "oznámili ředící emisi".
   - OPINION = postoj, přesvědčení, pocit z ceny. "way too cheap right here",
     "my conviction is high", "looking good".
   Když si nejsi jistý, je to OPINION.

3. NEVYMÝŠLEJ SI. Když ve zdroji číslo není, pole nech prázdné. Nikdy nedopočítávej
   ani neodhaduj. Chybějící údaj je v pořádku; vymyšlený údaj stojí peníze.

4. ŠUM ZAHOĎ. Vtipy, pozdravy, off-topic bavení, reakce. Spočítej je do
   `discarded_as_noise`, ale nedělej z nich tvrzení.

5. NEDĚLEJ VERDIKTY. Nepiš, že se má nakupovat nebo prodávat. Rozhodovací pravidla
   běží jinde a mají vlastní pojistky. Ty jen zaznamenáváš, co kdo řekl.

6. `summary` piš ČESKY, jednou větou. `verbatim_quote` nech v původním jazyce.

7. thesis_impact = BREAKS jen u skutečně diskvalifikujících událostí: ředící emise,
   pochybnost o pokračování firmy (going concern), delisting, odchod auditora,
   ztráta klíčového kontraktu, rozpad hlavní teze. Ne u špatného čtvrtletí.
"""

_PER_SOURCE: dict[SourceType, str] = {
    SourceType.WHATSAPP_GROUP: """\
ZDROJ: výřez ze skupinového chatu Breakout Investors. Text už je předzpracovaný —
je rozsekaný na zprávy s uvedeným mluvčím a datem.

- Mark Gomes ("Money Mark Gomes") v té skupině píše osobně. Jeho tvrzení mají
  nejvyšší váhu ze všech účastníků — označ mluvčího přesně.
- Když Gomes zmíní vlastní obchod ("I publicly closed it out at $6.61",
  "I'm still there with my trade"), je to claim_type=TRADE_DISCLOSURE. To je
  nejcennější typ záznamu v celém chatu — vytáhni cenu do `price_mentioned`.
- Většina zpráv jsou názory a bavení. To je normální. Radši vytáhni pět
  skutečných tvrzení než třicet domnělých.
- Jeden ticker může mít víc zápisů (DBOX / DBOXF / DBO.TO). Zapiš ho tak, jak byl
  napsaný, a firmu doplň do `company_hint`.
""",
    SourceType.GOMES_VIDEO: """\
ZDROJ: přepis videa / streamu Marka Gomese. Vše je jeho, mluvčí = "Mark Gomes".

- Prioritně hledej: konkrétní cenové úrovně (green/red/grey line), počet válců
  (cylinders, 0-10), stav semaforu trhu, nové picky a jejich zařazení.
- Cenové úrovně a válce → claim_type=RR_LINES, čísla do `numbers`.
- Výrok o celkovém trhu ("market is expensive here", "green light") →
  claim_type=MARKET_ALERT.
- Přepisy z videa mívají chyby v přepisu tickerů a čísel. Když je ticker
  zjevně přepsaný špatně, dej nejbližší smysluplný a sniž `confidence`.
""",
    SourceType.EARNINGS_CALL: """\
ZDROJ: přepis výsledkové konference. Toto je PRIMÁRNÍ ZDROJ — firma mluví sama
o sobě. Drtivá většina je zde FACT, ne OPINION.

- Vytáhni tvrdá čísla do `numbers`: tržby, marže, hotovost, spalování hotovosti,
  cash runway, výhled, backlog, počet akcií.
- Cash runway je zvlášť důležitý: kánon blokuje nákup pod 6 měsíců. Když padne
  údaj o hotovosti a spalování, zaznamenej obojí.
- Výhled vedení (guidance) je FACT o tom, co firma řekla — i když je to predikce.
- Ředící emise, going concern, změny v auditu → thesis_impact=BREAKS.
- Mluvčí = jméno vedoucího pracovníka, nebo "Company" u připravené části.
""",
    SourceType.NEWS: """\
ZDROJ: zpravodajský článek. Odděl, co je oznámená událost (FACT), od komentáře
novináře nebo analytika (OPINION).

- Firemní události — splity, reverzní splity, změny tickeru, akvizice, kontrakty,
  regulatorní rozhodnutí — vytáhni vždy, i když nemají čísla.
- Cenové cíle analytiků jsou OPINION, ne FACT.
""",
    SourceType.OTHER: """\
ZDROJ: neurčený. Postupuj konzervativně — když si nejsi jistý povahou tvrzení,
označ ho jako OPINION a sniž `confidence`.
""",
}


def build_prompt(source_type: SourceType, today_iso: str) -> str:
    """Assemble the system prompt for one source type."""
    return (
        f"{_BASE_RULES}\n"
        f"{_PER_SOURCE.get(source_type, _PER_SOURCE[SourceType.OTHER])}\n"
        f"Dnešní datum je {today_iso}. Když zdroj uvádí relativní čas "
        f"('minulý týden', 'včera'), vztahuj ho k tomuto datu."
    )
