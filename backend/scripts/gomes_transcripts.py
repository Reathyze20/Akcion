"""
Stáhne přepisy z YouTube kanálu Marka Gomese přes TranscriptAPI.com.

Proč vlastní skript a ne knihovna: `youtube_transcript_api` chodí přímo na
YouTube a ten ji z domácí IP periodicky blokuje. Pro jednorázové stažení to
stačí, pro naplánovanou týdenní úlohu ne. TranscriptAPI má ten blok vyřešený
na své straně.

Kredity (tarif 1 000/měsíc):
  * výpis nových videí kanálu (`channel/latest`) — ZDARMA
  * jeden přepis — 1 kredit
Takže deset posledních streamů = 10 kreditů.

Klíč se posílá VÝHRADNĚ v hlavičce `Authorization: Bearer`. Nikdy jako
query parametr: `requests` skládá text HTTPError z celé URL, takže by ho
`logger.exception` zapsal do logu živý. Viz `_safe_reason` ve
`finnhub_metrics.py` — tahle chyba se tu už jednou stala.

Použití:
    python scripts/gomes_transcripts.py list
    python scripts/gomes_transcripts.py fetch --limit 10 --out data/gomes_transcripts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

# Konzole na Windows jede v cp1250 a rozbila by se na první diakritice v názvu
# videa. Přepisy samotné se zapisují v UTF-8 vždy, tohle řeší jen výpis.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://transcriptapi.com/api/v2/youtube"

# "Money Mark Stocks" — ověřeno 24. 8. 2026 z videa 9PhWx9rzIaU, které je
# druhým primárním zdrojem kánonu (viz docs/GOMES_VIDEO_ADDENDUM.md).
CHANNEL_ID = "UCM7suHbR_DCbstUXNIS2Kqg"
CHANNEL_HANDLE = "@MoneyMarkStocks"

TIMEOUT = 60


def _key() -> str:
    key = os.environ.get("TRANSCRIPTAPI_KEY", "").strip()
    if not key:
        # .env se načítá jen když běží aplikace; skript se pouští i samostatně.
        env = Path(__file__).resolve().parent.parent / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("TRANSCRIPTAPI_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        sys.exit("TRANSCRIPTAPI_KEY není nastavený (backend/.env).")
    return key


def _safe(error: Exception, key: str) -> str:
    """Popis selhání bez pověření, které ho způsobilo."""
    text = str(error)
    if key:
        text = text.replace(key, "<klíč>")
    return re.sub(r"\?[^\s]*", "?<parametry>", text)


def _get(path: str, params: dict, key: str) -> dict:
    r = requests.get(
        f"{BASE}/{path}",
        params=params,
        headers={"Authorization": f"Bearer {key}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


@dataclass
class Video:
    video_id: str
    published: str  # YYYY-MM-DD
    title: str
    url: str


def list_videos(key: str, limit: int) -> list[Video]:
    """Poslední nahraná videa kanálu. Endpoint `channel/latest` je zdarma."""
    data = _get("channel/latest", {"channel": CHANNEL_HANDLE}, key)
    out: list[Video] = []
    for item in data.get("results", []):
        vid = item.get("videoId")
        if not vid:
            continue
        out.append(
            Video(
                video_id=vid,
                published=(item.get("published") or "")[:10],
                title=item.get("title") or "",
                url=item.get("link") or f"https://www.youtube.com/watch?v={vid}",
            )
        )
    out.sort(key=lambda v: v.published, reverse=True)
    return out[:limit]


def fetch_transcript(key: str, video: Video) -> tuple[str, dict]:
    """Přepis jednoho videa s časovými značkami. Stojí 1 kredit."""
    data = _get(
        "transcript",
        {"video_url": video.video_id, "format": "json"},
        key,
    )
    segments = data.get("transcript") or []
    lines = []
    for seg in segments:
        t = int(seg.get("start") or 0)
        text = (seg.get("text") or "").replace("\n", " ").strip()
        if text:
            lines.append(f"({t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}) {text}")
    meta = {
        "video_id": video.video_id,
        "published": video.published,
        "title": data.get("metadata", {}).get("title") or video.title,
        "url": video.url,
        "language": data.get("language"),
        "length_seconds": data.get("length_seconds"),
        "segments": len(segments),
    }
    return "\n".join(lines), meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["list", "fetch"])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--video-ids", help="Čárkou oddělený seznam video ID ke stažení")
    ap.add_argument("--out", default="data/gomes_transcripts")
    args = ap.parse_args()

    key = _key()

    if args.video_ids:
        v_ids = [vid.strip() for vid in args.video_ids.split(",") if vid.strip()]
        videos = [Video(video_id=vid, published="", title="", url=f"https://www.youtube.com/watch?v={vid}") for vid in v_ids]
    else:
        try:
            videos = list_videos(key, args.limit)
        except Exception as e:  # noqa: BLE001 — text se čistí, ne polyká
            print(f"Výpis videí selhal: {type(e).__name__}: {_safe(e, key)}")
            return 1

    if args.command == "list":
        for v in videos:
            print(f"{v.published}  {v.video_id}  {v.title[:80]}")
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    failures = 0

    for v in videos:
        # Pokud nemáme datum předem, zkusíme najít existující soubor podle video_id
        existing_matches = list(out_dir.glob(f"*_{v.video_id}.txt"))
        if existing_matches:
            print(f"PŘESKOČENO {v.video_id} (už stažené jako {existing_matches[0].name})")
            continue
        try:
            body, meta = fetch_transcript(key, v)
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"SELHALO    {v.video_id}: {type(e).__name__}: {_safe(e, key)}")
            continue
        published = meta.get("published") or v.published or "unknown"
        target = out_dir / f"{published}_{v.video_id}.txt"
        header = (
            f"# {meta['title']}\n"
            f"# datum: {published} | video: {v.video_id} | {v.url}\n"
            f"# jazyk: {meta['language']} | délka: {meta['length_seconds']}s "
            f"| segmentů: {meta['segments']}\n\n"
        )
        target.write_text(header + body, encoding="utf-8")
        index.append(meta)
        print(
            f"OK         {published} {v.video_id}  "
            f"{meta['segments']:5d} segmentu  {len(body):7d} znaku  -> {target.name}"
        )
        time.sleep(0.3)


    if index:
        idx_path = out_dir / "index.json"
        existing = []
        if idx_path.exists():
            existing = json.loads(idx_path.read_text(encoding="utf-8"))
        by_id = {m["video_id"]: m for m in existing}
        by_id.update({m["video_id"]: m for m in index})
        idx_path.write_text(
            json.dumps(sorted(by_id.values(), key=lambda m: m["published"], reverse=True),
                       indent=1, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"\nStaženo {len(index)}, selhalo {failures}. Spotřeba ≈ {len(index)} kreditů.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
