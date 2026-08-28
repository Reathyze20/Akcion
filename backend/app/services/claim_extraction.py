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
from collections.abc import Mapping
from enum import Enum

from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from app.core.sources import normalize_source, InvestmentSource
from app.services import llm


class ClaimExtractionError(RuntimeError):
    """Extraction could not complete. Never confused with 'nothing found'."""


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

def resolve_source_key(
    speaker: str | None,
    source_type: SourceType,
    roster: Mapping[str, str] | None = None,
) -> str:
    """
    Map a speaker to the authority their claim carries.

    An earnings call is the company speaking about itself — a primary source
    that outranks any commentary, whoever is at the microphone. In the group
    chat Mark Gomes posts alongside everyone else, so the same paste yields
    both GOMES and BREAKOUT_INVESTORS rows; that is what makes cross-source
    agreement computable from a single document.

    The group is where this used to go wrong. Every speaker in it was mapped to
    BREAKOUT_INVESTORS — around a hundred and thirty people, any one of whom
    then carried the authority of the research desk. Attribution now comes from
    `analyst_roster`, and an unlisted speaker keeps their name on the record
    and counts toward nothing.
    """
    if source_type is SourceType.EARNINGS_CALL:
        return "COMPANY"
    if source_type is SourceType.NEWS:
        return "MEDIA"
    if source_type is SourceType.GOMES_VIDEO:
        return InvestmentSource.GOMES.value

    return normalize_source(speaker, roster)


# ==============================================================================
# The guard
# ==============================================================================

_WS = re.compile(r"\s+")


#: Timestamp markers a transcript tool injects into the middle of speech:
#: "(1:35:22)", "(46:56)", "[00:12]". They are not words anyone said, and the
#: model elides them when quoting a sentence they cut in half. Stripped from
#: BOTH the source and the quote, so the guard compares speech to speech.
_TIMESTAMP = re.compile(r"[\(\[]\d{1,2}:\d{2}(?::\d{2})?[\)\]]")


def _normalize(text: str) -> str:
    """
    Reduce text to the words that were actually spoken.

    Two artifacts are removed, and only these two: transcript timestamps, and
    whitespace differences from line wrapping. Everything else — every word,
    number and their order — must still match, which is what makes
    `verify_claims` a real check rather than a fuzzy one.
    """
    return _WS.sub(" ", _TIMESTAMP.sub(" ", text)).strip().lower()


def verify_claims(
    claims: list[ExtractedClaim], source_text: str
) -> tuple[list[ExtractedClaim], list[ExtractedClaim]]:
    """
    Keep only claims whose verbatim quote actually occurs in the source.

    Whitespace and transcript timestamps are normalized away on both sides —
    a quote that differs only by a line break, or by a "(1:35:22)" the
    transcript tool dropped mid-sentence, is the same quote. The words
    themselves must be present, in order. Ellipsis ('...' or '…') may be
    used to bridge non-contiguous fragments spoken within the same thought,
    and all fragments must be present in source in sequential order.

    Returns:
        (verified, rejected)
    """
    haystack = _normalize(source_text)
    verified: list[ExtractedClaim] = []
    rejected: list[ExtractedClaim] = []

    for claim in claims:
        quote_text = claim.verbatim_quote
        # Split on ellipsis (... or …)
        parts = [p.strip() for p in re.split(r"\.{2,}|\u2026", quote_text) if p.strip()]

        if not parts:
            rejected.append(claim)
            continue

        cur_pos = 0
        matched = True
        for part in parts:
            norm_part = _normalize(part)
            if not norm_part:
                continue
            idx = haystack.find(norm_part, cur_pos)
            if idx == -1:
                matched = False
                break
            cur_pos = idx + len(norm_part)

        if matched and cur_pos > 0:
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

# ==============================================================================
# The model call
# ==============================================================================

#: A two-hour Stock Talk Live transcript produced 13,942 output tokens on the
#: first real run — close enough to a 16k ceiling that it truncated
#: intermittently, and a truncated structured output does not parse at all.
#: The ceiling is not a budget: the model stops when it has extracted
#: everything, so a generous limit costs nothing on shorter sources.
MAX_OUTPUT_TOKENS = 64000


#: Validation keywords structured outputs rejects. Dropping them costs
#: nothing: the same constraints still run on our side in
#: `ExtractionResult.model_validate_json`, so an out-of-range value is caught
#: after the call instead of being described before it.
_UNSUPPORTED_SCHEMA_KEYWORDS = (
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "minLength", "maxLength", "pattern", "format",
    "minItems", "maxItems", "uniqueItems",
)


def _harden_schema(node: object) -> object:
    """
    Make a Pydantic JSON schema acceptable to structured outputs.

    Two things the generated schema does not do on its own: every object must
    set `additionalProperties: false`, and range/length keywords are rejected
    outright.

    `required` is deliberately left as Pydantic wrote it. Forcing every
    property into it made the model emit an explicit null for each optional
    field of each claim, which on a two-hour transcript overran a 32k output
    ceiling and truncated the whole answer. Optional stays optional.
    """
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
        for keyword in _UNSUPPORTED_SCHEMA_KEYWORDS:
            node.pop(keyword, None)
        for value in node.values():
            _harden_schema(value)
    elif isinstance(node, list):
        for item in node:
            _harden_schema(item)
    return node


def extract_claims(
    text: str,
    *,
    source_type: SourceType,
    today_iso: str,
    api_key: str,
    model: str | None = None,
) -> ExtractionResult:
    """
    Run one document through the model and return only verified claims.

    The verbatim guard runs after the model, in `verify_claims`, and anything
    whose quote is not in `text` is dropped before this returns. A caller
    therefore cannot accidentally store an unverified claim.

    Raises:
        ClaimExtractionError: on a refusal, a transport failure, or output
            that does not validate. Never returns a partial result silently —
            "nothing was found" and "the call failed" must stay distinct.
    """
    if not text.strip():
        raise ClaimExtractionError("Zdrojový text je prázdný.")
    if not api_key:
        raise ClaimExtractionError("Chybí ANTHROPIC_API_KEY v backend/.env")

    import anthropic

    # The model name has one home, `services.llm.MODEL`. Keeping a second
    # copy here is how the analysis path ended up calling a model that had
    # been retired for twelve weeks.
    model = model or llm.MODEL

    client = anthropic.Anthropic(api_key=api_key)
    system = build_prompt(source_type, today_iso)

    schema = llm.harden_schema(ExtractionResult.model_json_schema())

    try:
        # Streaming is mandatory at this ceiling — the SDK refuses a
        # non-streaming request that could exceed ten minutes, and a real
        # two-hour transcript needs the room. `output_config.format`
        # constrains the response to the schema; validation still happens
        # here, because a constrained response is not the same as a checked one.
        with client.messages.stream(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": text}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIError as exc:
        raise ClaimExtractionError(f"Volání Claude selhalo: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        detail = getattr(response, "stop_details", None)
        raise ClaimExtractionError(
            f"Claude odmítl zpracovat tento text "
            f"({getattr(detail, 'category', 'bez důvodu')})."
        )

    usage = getattr(response, "usage", None)
    out_tokens = getattr(usage, "output_tokens", "?") if usage else "?"

    if getattr(response, "stop_reason", None) == "max_tokens":
        raise ClaimExtractionError(
            f"Odpověď se nevešla do limitu ({out_tokens} z {MAX_OUTPUT_TOKENS} "
            f"tokenů), takže ji nelze přečíst. Pošli zdroj po částech."
        )

    payload = next(
        (b.text for b in response.content if getattr(b, "type", None) == "text"), None
    )
    if not payload:
        raise ClaimExtractionError(
            f"Claude nevrátil žádný text (stop_reason="
            f"{getattr(response, 'stop_reason', None)}, {out_tokens} tokenů)."
        )

    try:
        result = ExtractionResult.model_validate_json(payload)
    except ValidationError as exc:
        raise ClaimExtractionError(
            f"Odpověď neodpovídá očekávanému tvaru: {exc}"
        ) from exc

    verified, rejected = verify_claims(result.claims, text)
    if rejected:
        logger.warning(
            "{} claim(s) rejected — quote not found in source", len(rejected)
        )

    logger.info(
        "Extraction: {} claims kept, {} rejected, {} in / {} out tokens",
        len(verified), len(rejected),
        getattr(usage, "input_tokens", "?") if usage else "?", out_tokens,
    )

    return ExtractionResult(
        claims=verified,
        detected_tickers=sorted({c.ticker for c in verified}),
        discarded_as_noise=result.discarded_as_noise,
        notes=result.notes,
    )
