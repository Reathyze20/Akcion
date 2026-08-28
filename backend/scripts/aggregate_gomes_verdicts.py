"""
Slouci vsech 10 verdict_NN.json (nezavisla LLM kontrola) s
claims_with_context.json (mechanicke zakotveni) do jedne zpravy a napoji na
skutecne radky v zive `ticker_mentions`, aby dalsi krok (uklid) mel presne
ID radku, ne jen popis tvrzeni.

Nic nemaze ani neupravuje -- jen cte a shrnuje. Vystup:
  verify_batch/summary.json   -- agregovane pocty + seznam k reseni
  verify_batch/cleanup.sql    -- navrh (NE spusteni) DELETE prikazu pro
                                  MISATTRIBUTED / SPLICE_DISTORTED radky,
                                  zakomentovany, k rucni kontrole
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "gomes_transcripts"
BATCH_DIR = DIR / "verify_batch"


def load_env():
    env = Path(__file__).resolve().parent.parent / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    claims = json.loads((BATCH_DIR / "claims_with_context.json").read_text(encoding="utf-8"))
    by_id = {c["claim_id"]: c for c in claims}

    verdict_files = sorted(BATCH_DIR.glob("verdict_*.json"))
    verdicts = {}
    missing_batches = []
    for i in range(10):
        f = BATCH_DIR / f"verdict_{i:02d}.json"
        if not f.exists():
            missing_batches.append(i)
            continue
        for v in json.loads(f.read_text(encoding="utf-8")):
            verdicts[v["claim_id"]] = v

    if missing_batches:
        print(f"POZOR: chybi verdict soubory pro davky {missing_batches} -- "
              f"agregace bude neuplna, spust znovu az doběhnou vsechny.")

    uncovered = [cid for cid in by_id if cid not in verdicts]
    if uncovered:
        print(f"POZOR: {len(uncovered)} tvrzeni nema verdikt vubec "
              f"(agent je vynechal): {uncovered[:10]}{'...' if len(uncovered) > 10 else ''}")

    counts = {"CONFIRMED": 0, "MISATTRIBUTED": 0, "OVERSTATED": 0, "SPLICE_DISTORTED": 0, "UNVERIFIED": 0}
    detail = []
    for cid, c in by_id.items():
        v = verdicts.get(cid)
        verdict = v["verdict"] if v else "UNVERIFIED"
        counts[verdict] = counts.get(verdict, 0) + 1
        detail.append({
            "claim_id": cid,
            "video_id": c["video_id"],
            "ticker": c["ticker"],
            "verdict": verdict,
            "note": v.get("note") if v else "agent tuto polozku vynechal",
            "summary_cs": c["summary_cs"],
            "verbatim_quote": c["verbatim_quote"][:200],
        })

    summary = {
        "total_claims": len(by_id),
        "counts": counts,
        "confirmed_rate": round(counts["CONFIRMED"] / len(by_id), 3) if by_id else None,
        "missing_batches": missing_batches,
        "uncovered_claim_ids": uncovered,
        "by_ticker_failure": {},
        "details": detail,
    }

    # kolik ne-CONFIRMED na ticker, at je hned videt kde je skoda nejvetsi
    fails_by_ticker: dict[str, int] = {}
    for d in detail:
        if d["verdict"] != "CONFIRMED":
            fails_by_ticker[d["ticker"]] = fails_by_ticker.get(d["ticker"], 0) + 1
    summary["by_ticker_failure"] = dict(sorted(fails_by_ticker.items(), key=lambda kv: -kv[1]))

    (BATCH_DIR / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps({"total": summary["total_claims"], "counts": counts,
                       "confirmed_rate": summary["confirmed_rate"]}, indent=1))

    if missing_batches:
        return  # cleanup navrh az na uplnych datech

    # --- napojeni na zive radky v ticker_mentions ---------------------------
    load_env()
    import sqlalchemy as sa
    eng = sa.create_engine(os.environ["DATABASE_URL"])

    bad = [d for d in detail if d["verdict"] in ("MISATTRIBUTED", "SPLICE_DISTORTED")]
    sql_lines = [
        "-- NAVRH uklidu zivych radku ticker_mentions, ktere nezavisla kontrola",
        "-- oznacila jako MISATTRIBUTED nebo SPLICE_DISTORTED. NIC SE NESPOUSTI",
        "-- automaticky -- zkontroluj radek po radku a spust rucne, co dava smysl.",
        "",
    ]
    with eng.connect() as c:
        for d in bad:
            # d["video_id"] je nazev souboru "YYYY-MM-DD_<hash>" -- video_url
            # v DB ale obsahuje jen holy YouTube hash bez data. rsplit("_", 1)
            # by uriznul spatne, kdyz hash sam zacina podtrzitkem (napr.
            # "2025-12-05__1yH1EYvqgk" -> skutecne ID je "_1yH1EYvqgk"), proto
            # regex na pevny tvar data na zacatku misto stripovani od konce.
            m = re.match(r"^\d{4}-\d{2}-\d{2}_(.+)$", d["video_id"])
            video_id = m.group(1) if m else d["video_id"]
            ticker = d["ticker"]
            quote_frag = d["verbatim_quote"][:40].replace("'", "''")
            rows = c.execute(sa.text(
                """
                SELECT tm.id FROM ticker_mentions tm
                JOIN analyst_transcripts at ON tm.transcript_id = at.id
                WHERE tm.ticker = :ticker AND at.video_url LIKE :vid
                  AND tm.context_snippet LIKE :frag
                """
            ), {"ticker": ticker, "vid": f"%{video_id}%", "frag": f"%{d['verbatim_quote'][:40]}%"}).fetchall()
            ids = [r[0] for r in rows]
            sql_lines.append(f"-- {d['claim_id']}  [{d['verdict']}]  {d['note']}")
            if ids:
                sql_lines.append(f"-- DELETE FROM ticker_mentions WHERE id IN ({','.join(map(str, ids))});")
            else:
                sql_lines.append(f"-- (radek se nenasel presnou shodou -- over rucne: ticker={ticker}, video={video_id})")
            sql_lines.append("")

    (BATCH_DIR / "cleanup.sql").write_text("\n".join(sql_lines), encoding="utf-8")
    print(f"\nNavrh uklidu ({len(bad)} kandidatu) -> {BATCH_DIR / 'cleanup.sql'}")


if __name__ == "__main__":
    main()
