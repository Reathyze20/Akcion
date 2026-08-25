"""
Hromadné zpracování přepisů Marka Gomese → DB.

Vezme všechny .txt soubory z data/gomes_transcripts/, prožene je přes
claim_extraction (Claude Sonnet), a výsledky uloží jako:
  - analyst_transcripts  — jeden řádek na video
  - ticker_mentions      — jeden řádek na ticker × video

Videa, která jsou v DB už uložená (shoda na video_url), se přeskočí, takže
skript lze pouštět opakovaně bez duplicit.

Zpracování jde od nejstaršího videa po nejnovější, aby historická data
v DB odpovídala časové ose a pozdější přepisy nemusely přepisovat starší stav.

Použití:
    python scripts/backfill_transcripts.py              # zpracuje vše nové
    python scripts/backfill_transcripts.py --dry-run    # jen vypíše co by dělal
    python scripts/backfill_transcripts.py --status     # co je v DB
    python scripts/backfill_transcripts.py --limit 2    # jen první 2 videa (test)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from datetime import date, datetime, timezone

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

# -- musí být před importem modelů --
from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402

# SQLAlchemy potřebuje mít každý mapper zaregistrovaný před použitím
import app.models.trading   # noqa: F401,E402
import app.models.gomes     # noqa: F401,E402
import app.models.analysis  # noqa: F401,E402
import app.models.sec       # noqa: F401,E402

from app.models.analysis import AnalystTranscript, TickerMention  # noqa: E402
from app.services.claim_extraction import (  # noqa: E402
    ClaimExtractionError,
    ClaimType,
    SourceType,
    extract_claims,
)

# Konzole na Windows může být cp1250 — přepisy mají diakritiku v názvech videí
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

TRANSCRIPT_DIR = BACKEND / "data" / "gomes_transcripts"

# Regex pro rozpoznání metadat z hlavičky souboru:
#   # datum: 2026-07-31 | video: SWgLlu4W5vQ | https://...
_HEADER_RE = re.compile(
    r"#\s*datum:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*video:\s*(?P<vid>[A-Za-z0-9_-]+)\s*\|\s*(?P<url>https?://\S+)"
)


# ==============================================================================
# Helpers
# ==============================================================================

def _parse_header(txt_path: pathlib.Path) -> dict | None:
    """Přečte první čtyři řádky souboru a vytáhne datum, video ID a URL."""
    try:
        lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines[:4]:
        m = _HEADER_RE.search(line)
        if m:
            return {"date": m.group("date"), "video_id": m.group("vid"), "url": m.group("url")}
    return None


def _already_in_db(db, url: str) -> bool:
    """Vrátí True, pokud transcript s tímto URL je v DB."""
    return (
        db.query(AnalystTranscript)
        .filter(AnalystTranscript.video_url == url)
        .first()
    ) is not None


def _sentiment_from_stance(stance: str) -> str:
    """Mapuje stance z claim_extraction na sentiment v TickerMention."""
    s = stance.upper()
    if s == "BULLISH":
        return "BULLISH"
    if s == "BEARISH":
        return "BEARISH"
    return "NEUTRAL"


def _action_from_claim(claim) -> str | None:
    """Odhadne action_mentioned z typu tvrzení a stance."""
    if claim.claim_type == ClaimType.TRADE_DISCLOSURE:
        stance = claim.stance.upper()
        if "BEAR" in stance:
            return "SELL"
        if "BULL" in stance:
            return "BUY"
        return "HOLD"
    return None


def _conviction_from_confidence(conf: float) -> str:
    if conf >= 0.75:
        return "HIGH"
    if conf >= 0.45:
        return "MEDIUM"
    return "LOW"


def _estimate_quality(segments: int) -> str:
    """Odhad kvality přepisu z počtu segmentů (cca 30 seg/min pro yt auto-cc)."""
    if segments >= 2500:
        return "high"
    if segments >= 1500:
        return "medium"
    return "low"


# ==============================================================================
# Zpracování jednoho souboru
# ==============================================================================

def process_file(
    txt_path: pathlib.Path,
    api_key: str,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """
    Zpracuje jeden přepis a uloží výsledky do DB.

    Vrátí slovník s výsledkem:
      status: 'ok' | 'skipped' | 'error'
      claims: počet uložených tvrzení
      tickers: seznam tickerů
      message: str (při chybě nebo přeskočení)
    """
    meta = _parse_header(txt_path)
    if not meta:
        return {"status": "error", "claims": 0, "tickers": [], "message": f"Nelze přečíst hlavičku: {txt_path.name}"}

    video_date_str = meta["date"]
    video_url = meta["url"]
    video_id = meta["video_id"]

    try:
        video_date = date.fromisoformat(video_date_str)
    except ValueError:
        return {"status": "error", "claims": 0, "tickers": [], "message": f"Špatný formát data: {video_date_str}"}

    raw_text = txt_path.read_text(encoding="utf-8", errors="replace")

    # Odhadni počet segmentů z dat v hlavičce (řádek "# segmentů: N")
    seg_match = re.search(r"segmentů:\s*(\d+)", raw_text[:500])
    segments = int(seg_match.group(1)) if seg_match else 0
    quality = _estimate_quality(segments)

    # Název videa z prvního řádku
    title_match = re.search(r"^#\s*(.+)$", raw_text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else txt_path.stem

    if dry_run:
        print(f"  DRY-RUN  {video_date_str}  {video_id}  {title[:60]}")
        return {"status": "ok", "claims": 0, "tickers": [], "message": "dry-run"}

    # Pokud existuje pre-extrahovaný JSON, načti ho (šetří API tokeny)
    extracted_json_path = txt_path.with_suffix(".extracted.json")
    
    with session_scope() as db:
        existing = db.query(AnalystTranscript).filter(AnalystTranscript.video_url == video_url).first()
        if existing:
            if not force:
                return {
                    "status": "skipped",
                    "claims": 0,
                    "tickers": [],
                    "message": f"Již v DB: {video_url}",
                }
            # Smaž staré mentions a transcript před novým uložením
            db.query(TickerMention).filter(TickerMention.transcript_id == existing.id).delete()
            db.delete(existing)
            db.flush()

        if extracted_json_path.exists():
            try:
                import json
                raw_json = extracted_json_path.read_text(encoding="utf-8")
                result_data = json.loads(raw_json)
                
                # Zpracuj claims z JSONu
                from app.services.claim_extraction import ExtractedClaim, verify_claims
                parsed_claims = [ExtractedClaim(**c) for c in result_data.get("claims", [])]
                verified, _ = verify_claims(parsed_claims, raw_text)
                
                detected = result_data.get("detected_tickers") or sorted({c.ticker for c in verified})
                discarded = result_data.get("discarded_as_noise", 0)
                notes = result_data.get("notes") or f"Pre-extracted JSON · {len(verified)} claims"
                
                from app.services.claim_extraction import ExtractionResult
                result = ExtractionResult(
                    claims=verified,
                    detected_tickers=detected,
                    discarded_as_noise=discarded,
                    notes=notes
                )
            except Exception as exc:
                return {"status": "error", "claims": 0, "tickers": [], "message": f"Chyba při čtení JSON: {exc}"}
        else:
            if not api_key:
                return {
                    "status": "skipped",
                    "claims": 0,
                    "tickers": [],
                    "message": "Chybí .extracted.json a není nastaven ANTHROPIC_API_KEY",
                }
            # Extrakce claims přes API
            try:
                result = extract_claims(
                    raw_text,
                    source_type=SourceType.GOMES_VIDEO,
                    today_iso=video_date_str,
                    api_key=api_key,
                )
            except ClaimExtractionError as exc:
                return {"status": "error", "claims": 0, "tickers": [], "message": str(exc)}

        # Ulož AnalystTranscript
        transcript = AnalystTranscript(
            source_name="Mark Gomes",
            raw_text=raw_text,
            processed_summary=result.notes or "",
            detected_tickers=result.detected_tickers,
            date=video_date,
            video_url=video_url,
            transcript_quality=quality,
            is_processed=True,
            processing_notes=(
                f"backfill_transcripts.py · {len(result.claims)} claims · "
                f"{result.discarded_as_noise} noise"
            ),
        )
        db.add(transcript)
        db.flush()  # potřebujeme transcript.id pro FK v TickerMention

        # Jeden TickerMention na ticker × transcript (nejsilnější claim pro daný ticker)
        # Ticker může mít více claims → vybereme ten s nejvyšší confidence
        by_ticker: dict[str, list] = {}
        for claim in result.claims:
            by_ticker.setdefault(claim.ticker.upper(), []).append(claim)

        saved_mentions = 0
        for ticker, claims in by_ticker.items():
            best = max(claims, key=lambda c: c.confidence)
            price_target = None
            if best.price_mentioned is not None:
                price_target = best.price_mentioned
            elif best.numbers:
                # Zkus první číslo označené jako price_target nebo similar
                for n in best.numbers:
                    if any(kw in (n.label or "").lower() for kw in ("target", "green", "price")):
                        price_target = n.value
                        break

            mention = TickerMention(
                ticker=ticker,
                transcript_id=transcript.id,
                mention_date=video_date,
                sentiment=_sentiment_from_stance(best.stance),
                action_mentioned=_action_from_claim(best),
                context_snippet=best.verbatim_quote[:1000] if best.verbatim_quote else None,
                key_points=[c.summary for c in claims if c.summary],
                price_target=price_target,
                conviction_level=_conviction_from_confidence(best.confidence),
                ai_extracted=True,
                is_current=False,  # backfill — is_current nastaví tracker_sync až pro aktuální
            )
            db.add(mention)
            saved_mentions += 1

        db.commit()

    return {
        "status": "ok",
        "claims": len(result.claims),
        "tickers": result.detected_tickers,
        "message": f"Uloženo {saved_mentions} mentions pro {len(by_ticker)} tickerů",
    }


# ==============================================================================
# Status — co je v DB
# ==============================================================================

def cmd_status() -> None:
    with session_scope() as db:
        rows = (
            db.query(AnalystTranscript)
            .filter(AnalystTranscript.source_name == "Mark Gomes")
            .order_by(AnalystTranscript.date)
            .all()
        )
        if not rows:
            print("DB je prázdná — žádné Gomesovy přepisy zatím neuloženy.")
            return
        print(f"{'Datum':<12} {'Video URL':<55} {'Tickery':>7}  {'Notes'}")
        print("-" * 100)
        for r in rows:
            tickers = len(r.detected_tickers) if r.detected_tickers else 0
            url_short = (r.video_url or "")[-50:]
            notes = (r.processing_notes or "")[:40]
            print(f"{str(r.date):<12} {url_short:<55} {tickers:>7}  {notes}")
        print(f"\nCelkem: {len(rows)} přepisů v DB")


# ==============================================================================
# Main
# ==============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Jen vypíše co by zpracoval, nic neuloží")
    ap.add_argument("--status", action="store_true", help="Zobrazí co je v DB a skončí")
    ap.add_argument("--force", action="store_true", help="Přepíše již existující záznamy v DB")
    ap.add_argument("--use-api", action="store_true", help="Povolit volání placeného Anthropic API (výchozí: False)")
    ap.add_argument("--limit", type=int, default=0, help="Zpracuj jen N souborů (0 = vše)")
    ap.add_argument(
        "--dir",
        default=str(TRANSCRIPT_DIR),
        help="Adresář s .txt přepisy (výchozí: data/gomes_transcripts)",
    )
    args = ap.parse_args()

    settings = get_settings()
    ok, err = initialize_database(str(settings.database_url))
    if not ok:
        print(f"Chyba připojení k DB: {err}")
        return 1

    if args.status:
        cmd_status()
        return 0

    transcript_dir = pathlib.Path(args.dir)
    if not transcript_dir.exists():
        print(f"Adresář neexistuje: {transcript_dir}")
        return 1

    txt_files = sorted(
        [f for f in transcript_dir.glob("*.txt") if not f.name.startswith("index")],
        key=lambda f: f.name,  # soubory jsou pojmenovány YYYY-MM-DD_* → chronologicky
    )

    if not txt_files:
        print("Žádné .txt soubory nenalezeny.")
        return 0

    if args.limit:
        txt_files = txt_files[: args.limit]

    api_key = (settings.anthropic_api_key or "") if args.use_api else ""
    # Není-li api_key, spoléháme se na .extracted.json soubory vygenerované v IDE session (nulové API náklady)

    print(f"Nalezeno {len(txt_files)} souborů k zpracování.")
    if args.dry_run:
        print(">>> DRY RUN — nic se nezapisuje do DB <<<\n")

    total_ok = total_skip = total_err = 0

    for i, txt_path in enumerate(txt_files, 1):
        print(f"\n[{i}/{len(txt_files)}] {txt_path.name}")
        res = process_file(txt_path, api_key=api_key, dry_run=args.dry_run, force=args.force)

        status = res["status"]
        if status == "ok":
            total_ok += 1
            tickers = ", ".join(res["tickers"][:10])
            if len(res["tickers"]) > 10:
                tickers += f" … ({len(res['tickers'])} celkem)"
            print(f"  ✓ {res['message']}")
            print(f"  Tickery: {tickers or '—'}")
        elif status == "skipped":
            total_skip += 1
            print(f"  ⏭  {res['message']}")
        else:
            total_err += 1
            print(f"  ✗ {res['message']}")

    print(f"\n{'='*60}")
    print(f"Hotovo: {total_ok} zpracováno, {total_skip} přeskočeno, {total_err} chyb")
    return 1 if total_err and not total_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
