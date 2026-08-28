"""
Gemini 3.7 Flash Intake Service

Blesková extrakce investičních tezí, cenových linií (Green/Red/Grey) a stavu válců
z videí Marka Gomese, transkriptů a zpráv z Breakout Investors.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from pydantic import BaseModel, Field

from app.config.settings import Settings
from app.core.tickers import canonical_ticker
from app.core.sources import InvestmentSource

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_FALLBACK_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


class IntakeAnalysisResult(BaseModel):
    ticker: str = Field(..., description="Canonical ticker symbol (e.g. GKPRF, KUYAF, VTSI)")
    original_ticker: str | None = Field(None, description="Original ticker as mentioned (e.g. GSI.V, KUYA.V)")
    company_name: str = Field(..., description="Company name")
    source_type: str = Field("GOMES_VIDEO", description="GOMES_VIDEO | BREAKOUT_INVESTORS | OTHER")
    speaker: str = Field("Mark Gomes", description="Speaker name")
    
    # Valuation & lines
    green_line: float | None = Field(None, description="Green Line / Low DCF target")
    red_line: float | None = Field(None, description="Red Line / High DCF target")
    grey_line: float | None = Field(None, description="Grey Line / Middle reference")
    cylinders: int | None = Field(None, description="Operational cylinders (0-10)")
    
    # Methodology parameters
    lifecycle_phase: str = Field("UNKNOWN", description="GREAT_FIND | WAIT_TIME | GOLD_MINE | UNKNOWN")
    conviction_score: int | None = Field(None, description="Gomes Conviction Score (1-10)")
    
    # Thesis details
    primary_catalyst: str | None = Field(None, description="Short primary catalyst")
    milestones: list[str] = Field(default_factory=list, description="Expected milestones")
    red_flags: list[str] = Field(default_factory=list, description="Risks, dilution, delays")
    verbatim_quote: str | None = Field(None, description="Exact quotation from text")
    summary_cz: str = Field(..., description="Stručné shrnutí v češtině (2-3 věty)")
    recommended_action: str = Field("WATCH", description="BUY | WAIT | SELL | WATCH | RESEARCH")


def extract_youtube_video_id(url_or_id: str) -> str | None:
    """Extrahuje YouTube video ID z URL nebo vrátí ID."""
    if not url_or_id:
        return None
    url_or_id = url_or_id.strip()
    if len(url_or_id) == 11 and not ("/" in url_or_id or "?" in url_or_id):
        return url_or_id
    
    try:
        parsed = urlparse(url_or_id)
        if parsed.hostname in ("www.youtube.com", "youtube.com"):
            if parsed.path == "/watch":
                return parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/live/"):
                return parsed.path.split("/")[2]
        elif parsed.hostname == "youtu.be":
            return parsed.path.lstrip("/")
    except Exception as e:
        logger.warning(f"Failed to parse YouTube URL {url_or_id}: {e}")
    return None


def fetch_youtube_transcript(video_id: str) -> str | None:
    """Stáhne transkript z YouTube pomocí youtube_transcript_api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US', 'cs'])
        text = " ".join(item['text'] for item in transcript_list)
        return text
    except Exception as e:
        logger.warning(f"Failed to download transcript for {video_id}: {e}")
        return None


def call_gemini_api(prompt: str, system_instruction: str | None = None) -> dict[str, Any]:
    """Zavolá Gemini API pro strukturovanou JSON odpověď."""
    api_key = Settings().gemini_api_key
    if not api_key:
        raise RuntimeError("Chybí GEMINI_API_KEY v konfiguraci / .env")

    headers = {"Content-Type": "application/json"}
    
    contents = []
    if system_instruction:
        contents.append({
            "role": "user",
            "parts": [{"text": f"SYSTEM INSTRUCTION:\n{system_instruction}\n\nUSER PROMPT:\n{prompt}"}]
        })
    else:
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

    payload = {
        "contents": contents,
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        }
    }

    # Zkusit primární model (gemini-2.5-flash) a případně fallback
    for url in (GEMINI_API_URL, GEMINI_FALLBACK_URL):
        try:
            resp = requests.post(f"{url}?key={api_key}", headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            else:
                logger.warning(f"Gemini API returned {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Gemini API call to {url} failed: {e}")

    raise RuntimeError("Volání Gemini API selhalo. Zkontroluj klíč nebo internetové připojení.")


SYSTEM_PROMPT = """
Jsi specializovaný analytik pro metodiku Marka Gomese (Get Rich on Stocks) a komunitu Breakout Investors.
Tvým úkolem je extrahovat z dodaného textu, transkriptu nebo analýzy strukturovaná data.

PRAVIDLA METODIKY:
1. NIKDY nevymýšlej čísla! Pokud Mark Gomes nebo autor explicitně neuvedl Green Line (Low), Red Line (High) nebo počet válců, vrať null!
2. Rozlišuj stádia:
   - GREAT_FIND: Nově objevená firma, začátek příběhu.
   - WAIT_TIME: Po počátečním hypu, fáze stagnace / čekání na tržby, vyhnout se nákupu.
   - GOLD_MINE: Provozní zralost, stabilní růst / plný rozběh (10 válců).
3. Válce (Cylinders 0-10): 10 = 'firing on all cylinders' (vše šlape), sníženo o zpoždění, žaloby, odchody vedení.
4. Ticker uveď primárně v US OTC podobě (canonical, např. GKPRF místo GSI.V, KUYAF místo KUYA.V), původní ticker dej do original_ticker.
5. Vytvoř výstižné shrnutí v češtině (2-3 věty) do summary_cz.

Vrať JSON odpovídající schématu:
{
  "ticker": "GKPRF",
  "original_ticker": "GSI.V",
  "company_name": "Gatekeeper Systems",
  "source_type": "GOMES_VIDEO",
  "speaker": "Mark Gomes",
  "green_line": 0.30,
  "red_line": 3.75,
  "grey_line": null,
  "cylinders": 8,
  "lifecycle_phase": "GOLD_MINE",
  "conviction_score": 8,
  "primary_catalyst": "Školní autobusy a AI kamerové kontrakty",
  "milestones": ["Nový kontrakt s velkým školním distriktem", "Q3 ziskovost"],
  "red_flags": [],
  "verbatim_quote": "přesná citace z textu",
  "summary_cz": "Gatekeeper má silné momentum díky novým zakázkám na AI kamery. Válce jedou na 8/10 a firma generuje zisk.",
  "recommended_action": "BUY"
}
"""


def analyze_intake_content(
    text: str | None = None,
    url: str | None = None,
    source_type: str = "GOMES_VIDEO"
) -> IntakeAnalysisResult:
    """Analyzuje text nebo YouTube URL pomocí Gemini Flash."""
    content_to_analyze = ""
    
    if url:
        yt_id = extract_youtube_video_id(url)
        if yt_id:
            transcript = fetch_youtube_transcript(yt_id)
            if transcript:
                content_to_analyze = f"YOUTUBE TRANSCRIPT (Video ID: {yt_id}):\n{transcript[:15000]}"
            else:
                raise ValueError(f"Nepodařilo se stáhnout automatický transkript z YouTube pro video {yt_id}. Zkopíruj text ručně.")
    
    if not content_to_analyze and text:
        content_to_analyze = text.strip()

    if not content_to_analyze:
        raise ValueError("Chybí vstupní text nebo platný odkaz na video.")

    user_prompt = f"SOURCE TYPE: {source_type}\n\nCONTENT TO ANALYZE:\n{content_to_analyze}"
    
    raw_json = call_gemini_api(user_prompt, system_instruction=SYSTEM_PROMPT)
    
    # Normalizace tickeru
    ticker = raw_json.get("ticker", "").strip().upper()
    canon = canonical_ticker(ticker)
    if canon:
        raw_json["ticker"] = canon
        if not raw_json.get("original_ticker"):
            raw_json["original_ticker"] = ticker

    return IntakeAnalysisResult.model_validate(raw_json)
