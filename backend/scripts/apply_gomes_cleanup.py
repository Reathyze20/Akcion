"""
Aplikuje na zivou DB rozhodnuti z nezavisleho overeni 395 jiz importovanych
tvrzeni (viz verify_batch/summary.json):

  MISATTRIBUTED / SPLICE_DISTORTED (40 radku) -> DELETE cele radky
  OVERSTATED (199 radku)                      -> UPDATE: price_target=NULL,
                                                  key_points=NULL; ticker,
                                                  context_snippet, sentiment,
                                                  mention_date zustavaji
  CONFIRMED (156 radku)                       -> beze zmeny

Kazdy radek se dohledava stejne jako v aggregate_gomes_verdicts.py (ticker +
video hash z video_url + fragment verbatim_quote v context_snippet), takze
mazani/uprava jde vzdy po presnem ID, nikdy plosne podle tickeru.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "gomes_transcripts"
BATCH_DIR = DIR / "verify_batch"


def load_env():
    env = Path(__file__).resolve().parent.parent / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def resolve_id(conn, sa, d) -> int | None:
    m = re.match(r"^\d{4}-\d{2}-\d{2}_(.+)$", d["video_id"])
    video_hash = m.group(1) if m else d["video_id"]
    rows = conn.execute(sa.text(
        """
        SELECT tm.id FROM ticker_mentions tm
        JOIN analyst_transcripts at ON tm.transcript_id = at.id
        WHERE tm.ticker = :ticker AND at.video_url LIKE :vid
          AND tm.context_snippet LIKE :frag
        """
    ), {
        "ticker": d["ticker"],
        "vid": f"%{video_hash}%",
        "frag": f"%{d['verbatim_quote'][:40]}%",
    }).fetchall()
    if len(rows) != 1:
        return None
    return rows[0][0]


def main() -> None:
    summary = json.loads((BATCH_DIR / "summary.json").read_text(encoding="utf-8"))
    details = summary["details"]

    load_env()
    import sqlalchemy as sa
    eng = sa.create_engine(os.environ["DATABASE_URL"])

    to_delete: list[int] = []
    to_clean: list[int] = []
    unresolved: list[str] = []

    with eng.connect() as conn:
        for d in details:
            if d["verdict"] not in ("MISATTRIBUTED", "SPLICE_DISTORTED", "OVERSTATED"):
                continue
            row_id = resolve_id(conn, sa, d)
            if row_id is None:
                unresolved.append(f"{d['claim_id']} [{d['verdict']}]")
                continue
            if d["verdict"] in ("MISATTRIBUTED", "SPLICE_DISTORTED"):
                to_delete.append(row_id)
            else:
                to_clean.append(row_id)

    print(f"K SMAZANI:  {len(to_delete)} radku")
    print(f"K VYCISTENI: {len(to_clean)} radku")
    if unresolved:
        print(f"NEDOHLEDANO: {len(unresolved)} -- STOP, nic se nespousti dokud toto neni 0")
        for u in unresolved:
            print("  ", u)
        sys.exit(1)

    overlap = set(to_delete) & set(to_clean)
    if overlap:
        print(f"CHYBA: prekryv mezi mazanim a cistenim: {overlap} -- STOP")
        sys.exit(1)

    if "--commit" not in sys.argv:
        print("\n(DRY RUN -- spust s --commit pro skutecne provedeni)")
        return

    with eng.begin() as conn:  # jedna transakce, vse nebo nic
        before = conn.execute(sa.text(
            "SELECT count(*) FROM ticker_mentions tm JOIN analyst_transcripts at ON tm.transcript_id=at.id "
            "WHERE at.source_name='Mark Gomes'"
        )).scalar()

        if to_delete:
            conn.execute(sa.text("DELETE FROM ticker_mentions WHERE id = ANY(:ids)"),
                         {"ids": to_delete})
        if to_clean:
            conn.execute(sa.text(
                "UPDATE ticker_mentions SET price_target = NULL, key_points = NULL "
                "WHERE id = ANY(:ids)"
            ), {"ids": to_clean})

        after = conn.execute(sa.text(
            "SELECT count(*) FROM ticker_mentions tm JOIN analyst_transcripts at ON tm.transcript_id=at.id "
            "WHERE at.source_name='Mark Gomes'"
        )).scalar()
        still_has_price_target = conn.execute(sa.text(
            "SELECT count(*) FROM ticker_mentions tm JOIN analyst_transcripts at ON tm.transcript_id=at.id "
            "WHERE at.source_name='Mark Gomes' AND tm.id = ANY(:ids) AND tm.price_target IS NOT NULL"
        ), {"ids": to_clean}).scalar()

    print(f"\nHOTOVO. Gomes radku pred: {before}, po: {after} (ocekavano {before - len(to_delete)}).")
    print(f"Vycistenych radku, ktere jeste maji price_target NOT NULL (mel by byt 0): {still_has_price_target}")


if __name__ == "__main__":
    main()
