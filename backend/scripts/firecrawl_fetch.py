"""
Stáhne stránku, na kterou žádný bezplatný zdroj v appce nedosáhne.

K čemu to je: čtyři pozice (ITMSF/IMP.V, GKPRF/GSI.V, DBOXF/DBO.TO,
KUYAF/KUYA.V) podávají v Kanadě, takže 54 % portfolia je mimo SEC EDGAR.
Rubrika válců pro ně nemá ani jeden tvrdý údaj z podání a spadne na roční
souhrny z Yahoo, uzamčené do 3-7 se střední jistotou. Ta čísla přitom firma
sama zveřejňuje ve čtvrtletní tiskovce. Tenhle skript ji přinese na disk.

Kredity (zůstatek je konečný, ne měsíční):
  * `ledger`, `list`  -- ZDARMA
  * `map`             -- 1 kredit za celou doménu
  * `fetch`           -- 1 kredit za stránku, ale jen když ještě není v cache

Postup, který šetří nejvíc: `map` jednou na doménu, z výpisu vybrat ručně tři
čtyři adresy, které opravdu nesou výsledky, a teprve ty stáhnout. Extrakci
čísel z textu NEDĚLÁ Firecrawl (jeho LLM režim stojí násobek) ani API --
přečte se to v session, stejně jako u `sec_backfill.py`.

Klíč jde VÝHRADNĚ v hlavičce `Authorization: Bearer`. Nikdy v URL: `requests`
skládá text HTTPError z celé adresy, takže by ho `logger.exception` zapsal do
logu živý. Viz `_safe_reason` ve `finnhub_metrics.py` -- v téhle appce se to
už jednou stalo.

Použití:
    python scripts/firecrawl_fetch.py ledger
    python scripts/firecrawl_fetch.py map --ticker DBOXF --search "results"
    python scripts/firecrawl_fetch.py fetch https://... https://...
    python scripts/firecrawl_fetch.py list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.firecrawl import (  # noqa: E402
    CREDITS_PER_MAP,
    CREDITS_PER_SCRAPE,
    Ledger,
    cache_paths,
    map_site,
    scrape,
)

# Konzole na Windows jede v cp1250 a rozbila by se na první diakritice
# v názvu stránky. Soubory se zapisují v UTF-8 vždy.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DATA = Path(__file__).resolve().parent.parent / "data" / "firecrawl"
CACHE = DATA / "pages"
LEDGER = DATA / "ledger.json"

#: Firmy mimo dosah SEC a jejich weby. Názvy sedí s `stocks.company_name`;
#: domény jsou první odhad a ověří je až první `map` -- když vrátí prázdno,
#: doména je špatně a stálo to 1 kredit.
ISSUERS = {
    "DBOXF": ("D-BOX Technologies", "https://www.d-box.com"),
    "GKPRF": ("Gatekeeper Systems", "https://www.gatekeeper-systems.com"),
    "ITMSF": ("Intermap Technologies", "https://www.intermap.com"),
    "KUYAF": ("Kuya Silver", "https://www.kuyasilver.com"),
}


def _key() -> str:
    """Klíč z prostředí, jinak z .env -- skript se pouští i mimo aplikaci."""
    import os

    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if key:
        return key
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FIRECRAWL_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _ledger() -> Ledger:
    return Ledger.load(LEDGER)


def cmd_ledger(_args) -> int:
    led = _ledger()
    print(f"Rozpočet:  {led.budget} kreditů")
    print(f"Utraceno:  {led.spent}")
    print(f"Zbývá:     {led.remaining()}")
    if led.calls:
        print("\nPoslední útraty:")
        for call in led.calls[-10:]:
            print(f"  {call['at']}  {call['what']:6}  -{call['credits']}  {call['url'][:70]}")
    return 0


def cmd_list(_args) -> int:
    if not CACHE.exists():
        print("Cache je prázdná.")
        return 0
    pages = sorted(CACHE.glob("*.md"))
    print(f"{len(pages)} stránek v cache ({CACHE}):")
    for page in pages:
        print(f"  {page.stat().st_size:>8} B  {page.name}")
    return 0


def cmd_map(args) -> int:
    if args.ticker:
        entry = ISSUERS.get(args.ticker.upper())
        if entry is None:
            print(f"Neznám {args.ticker}. Znám: {', '.join(sorted(ISSUERS))}")
            return 2
        name, domain = entry
        print(f"{args.ticker.upper()} = {name} -> {domain}")
    else:
        domain = args.domain

    led = _ledger()
    print(f"Stojí {CREDITS_PER_MAP} kredit (z cache 0), zbývá {led.remaining()}.")
    urls, reason = map_site(
        domain,
        key=_key(),
        ledger=led,
        search=args.search,
        cache_dir=CACHE,
        force=args.force,
    )
    if reason:
        print(f"NEPOVEDLO SE: {reason}")
        return 1
    if not urls:
        print("Doména odpověděla, ale nevrátila žádné adresy — nejspíš špatný web.")
        return 1
    print(f"{len(urls)} adres:")
    for url in urls[: args.limit]:
        print(f"  {url}")
    if len(urls) > args.limit:
        print(f"  ... a dalších {len(urls) - args.limit} (zvyš --limit)")
    return 0


def cmd_fetch(args) -> int:
    led = _ledger()
    key = _key()
    todo = [u for u in args.urls if not cache_paths(CACHE, u)[0].exists()]
    print(
        f"{len(args.urls)} adres, z toho {len(todo)} nových "
        f"= {len(todo) * CREDITS_PER_SCRAPE} kreditů, zbývá {led.remaining()}."
    )
    failed = 0
    for url in args.urls:
        result = scrape(url, key=key, cache_dir=CACHE, ledger=led, force=args.force)
        if result.ok:
            mark = "z cache" if result.from_cache else f"-{result.credits} kr."
            print(f"  OK      {mark:>8}  {len(result.markdown):>7} zn.  {url[:60]}")
        else:
            failed += 1
            print(f"  CHYBA             {result.reason}  |  {url[:60]}")
    print(f"\nUtraceno celkem {led.spent}/{led.budget}, zbývá {led.remaining()}.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ledger", help="stav kreditů (zdarma)").set_defaults(fn=cmd_ledger)
    sub.add_parser("list", help="co už je v cache (zdarma)").set_defaults(fn=cmd_list)

    p_map = sub.add_parser("map", help="adresy na doméně (1 kredit)")
    p_map.add_argument("--ticker", help=f"jeden z: {', '.join(sorted(ISSUERS))}")
    p_map.add_argument("--domain", help="doména, když ticker neznáme")
    p_map.add_argument("--search", help="filtr, např. 'quarterly results'")
    p_map.add_argument("--limit", type=int, default=40, help="kolik vypsat (cache drží vše)")
    p_map.add_argument("--force", action="store_true", help="zmapovat znovu i s cache")
    p_map.set_defaults(fn=cmd_map)

    p_fetch = sub.add_parser("fetch", help="stáhne stránky (1 kredit za novou)")
    p_fetch.add_argument("urls", nargs="+")
    p_fetch.add_argument("--force", action="store_true", help="znovu i to, co je v cache")
    p_fetch.set_defaults(fn=cmd_fetch)

    args = parser.parse_args()
    if args.cmd == "map" and not (args.ticker or args.domain):
        parser.error("map potřebuje --ticker nebo --domain")
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
