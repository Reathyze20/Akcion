"""
Mechanická (ne-LLM) predverifikace tvrzeni z gomes_transcripts/*.extracted.json.

Pro kazde tvrzeni zjisti, jestli se jeho verbatim_quote doopravdy vyskytuje
v odpovidajicim .txt prepisu, a pokud ano, vytahne okoli (kontext) z PUVODNIHO
textu (s casovymi znackami), aby dalsi (LLM) kontrola atribuce nemusela cist
cely ~130KB soubor -- staci ji poslat uz vyrizeny usek.

Vystup: verify_batch/claims_with_context.json -- pole objektu:
  {video, ticker, claim_type, quote, context, grounded, ...puvodni pole}
plus verify_batch/not_found.json pro tvrzeni, ktera se v textu nenasla vubec
(ta uz nemaji smysl posilat LLM overovateli -- jsou mechanicky vyvracena).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "gomes_transcripts"
OUT = DIR / "verify_batch"
OUT.mkdir(exist_ok=True)


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\(\d+:\d{2}:\d{2}\)\s*", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _fragment(quote_part: str) -> str:
    nq = norm(quote_part)
    words = nq.split()
    if len(words) <= 8:
        return nq
    return " ".join(words[2:-2])


def find_context(raw_txt: str, quote: str) -> tuple[bool, str, str]:
    """
    Vrati (nalezeno, timestamp_u_zacatku, okolni_text_s_casovymi_znackami).

    `quote` casto neni jeden souvisly usek -- extraktor casti spojuje "..."
    (Gemini je oznacuje jako "verbatim", ale je to sestrih vice mist ve
    streamu). Kazdy usek mezi elipsami se proto hleda ZVLAST; "nalezeno"
    znamena, ze VSECHNY useky existuji v textu, ne ze cela veta na sebe
    navazuje doslovne -- to uz je vec pro navazujici (LLM) kontrolu, ne pro
    tenhle mechanicky krok.
    """
    parts = [p.strip() for p in re.split(r"\.\.\.|…", quote) if p.strip()]
    if not parts:
        return False, "", ""

    # Casove znacky jako "(0:20:21)" musi zmizet CELE, vcetne cislic uvnitr --
    # jinak "20" a "21" z nich splynou s okolnim textem jako falesna slova a
    # rozbiji kazdou frazi, pres kterou znacka padne (u hustych prepisu jedna
    # za pár sekund to je skoro kazda fraze). Napred tedy najit jejich rozsahy
    # a znaky uvnitr pri stavbe mapovani uplne preskocit.
    ts_spans = [m.span() for m in re.finditer(r"\(\d+:\d{2}:\d{2}\)", raw_txt)]

    # Mapovani: pro kazdy znak v normalizovanem textu, index v puvodnim textu.
    # `span_i` postupuje spolu s `i` (oboje rostou monotonne), takze cely
    # preskok casovych znacek je O(delka textu), ne O(delka x pocet znacek).
    orig_positions = []
    norm_chars = []
    span_i = 0
    for i, ch in enumerate(raw_txt):
        while span_i < len(ts_spans) and ts_spans[span_i][1] <= i:
            span_i += 1
        if span_i < len(ts_spans) and ts_spans[span_i][0] <= i < ts_spans[span_i][1]:
            continue
        c = ch.lower()
        if c in "abcdefghijklmnopqrstuvwxyz0123456789":
            norm_chars.append(c)
            orig_positions.append(i)
        elif norm_chars and norm_chars[-1] != " ":
            norm_chars.append(" ")
            orig_positions.append(i)
    flat = "".join(norm_chars).strip()

    spans = []  # (orig_start, orig_end) per matched part, in quote order
    for part in parts:
        frag = _fragment(part)
        if not frag:
            continue
        idx = flat.find(frag)
        if idx < 0:
            return False, "", ""  # jedna cast chybi -> cele tvrzeni NOT_FOUND
        orig_start = orig_positions[min(idx, len(orig_positions) - 1)]
        orig_end = orig_positions[min(idx + len(frag), len(orig_positions) - 1)]
        spans.append((orig_start, orig_end))

    if not spans:
        return False, "", ""

    first_ts_match = re.search(
        r"\(\d+:\d{2}:\d{2}\)", raw_txt[max(0, spans[0][0] - 20):spans[0][0] + 5]
    )
    timestamp = first_ts_match.group(0) if first_ts_match else ""

    # Vic useku muze lezet daleko od sebe (elipsa preskocila minuty streamu).
    # Misto jednoho souvisleho okoli sestavime okoli KOLEM KAZDEHO useku
    # zvlast a spojime je -- at navazujici kontrola vidi vsechny, ne jen prvni.
    pieces = []
    for orig_start, orig_end in spans:
        ctx_start = max(0, orig_start - 250)
        ctx_end = min(len(raw_txt), orig_end + 250)
        pieces.append(raw_txt[ctx_start:ctx_end])
    context = "\n[...]\n".join(pieces)
    return True, timestamp, context


def main() -> None:
    files = sorted(DIR.glob("*.extracted.json"))
    all_items = []
    not_found = []
    stats = {"total": 0, "grounded": 0, "grounded_spliced": 0, "not_found": 0, "no_quote": 0}

    for jf in files:
        video_id = jf.stem.replace(".extracted", "")
        txt_path = DIR / f"{video_id}.txt"
        if not txt_path.exists():
            continue
        raw_txt = txt_path.read_text(encoding="utf-8")
        data = json.loads(jf.read_text(encoding="utf-8"))

        for i, c in enumerate(data.get("claims", [])):
            stats["total"] += 1
            quote = c.get("verbatim_quote", "")
            if not quote:
                stats["no_quote"] += 1
                continue
            grounded, ts, context = find_context(raw_txt, quote)
            spliced = bool(re.search(r"\.\.\.|…", quote))
            item = {
                "claim_id": f"{video_id}#{i}",
                "video_id": video_id,
                "ticker": c.get("ticker"),
                "company_hint": c.get("company_hint"),
                "claim_type": c.get("claim_type"),
                "stance": c.get("stance"),
                "summary_cs": c.get("summary_cs") or c.get("summary"),
                "verbatim_quote": quote,
                "numbers": c.get("numbers"),
                "price_mentioned": c.get("price_mentioned"),
                "confidence": c.get("confidence"),
                "grounded": grounded,
                "spliced": spliced,
                "timestamp": ts,
                "context": context,
            }
            if grounded:
                stats["grounded"] += 1
                if spliced:
                    stats["grounded_spliced"] += 1
                all_items.append(item)
            else:
                stats["not_found"] += 1
                not_found.append(item)

    (OUT / "claims_with_context.json").write_text(
        json.dumps(all_items, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "not_found.json").write_text(
        json.dumps(not_found, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps(stats, indent=1))
    print(f"grounded -> {OUT / 'claims_with_context.json'}")
    print(f"not_found -> {OUT / 'not_found.json'}")


if __name__ == "__main__":
    main()
