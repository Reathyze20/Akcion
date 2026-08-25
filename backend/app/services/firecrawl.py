"""
Reading a page the free sources cannot reach — once, and on the record.

Why this exists at all
----------------------
Four of the twelve positions (ITMSF/IMP.V, GKPRF/GSI.V, DBOXF/DBO.TO,
KUYAF/KUYA.V) file in Canada, so 54 % of the portfolio by value is invisible to
SEC EDGAR. `cylinders.propose_cylinders` refuses to say anything without at
least two hard readings; for those four it has none, falls back to Yahoo's
trailing aggregates and is clamped to 3-7 at medium confidence, permanently.
The numbers themselves are not secret — the company publishes them in its own
quarterly release. This module is how one of those pages gets read.

What makes this source different from every other one in the app
----------------------------------------------------------------
It is metered, and the meter does not refill. The balance is a fixed number of
pages, so a scheduled job that fetches without counting spends the lot in an
afternoon and then goes quiet. Two rules run through everything below.

1. **A page is fetched once.** The markdown lands on disk beside a sidecar
   saying where it came from and when. Asking again costs nothing and admits
   it (`from_cache`) — the discipline `scripts/gomes_transcripts.py` already
   uses for transcripts.

2. **Running out is a stated fact, never an empty string.** The worst outcome
   available here is this app's cardinal defect: an absent input reaching the
   engine as a confident number. So an exhausted budget, a dead URL and a page
   that came back blank all return `ok=False` and a reason in Czech, and the
   caller has to look at it. Nothing here ever hands back markdown it did not
   receive.

The key travels in the Authorization header and nowhere else. `requests` builds
HTTPError text out of the full request URL, so a key in a query parameter is a
key in the log file — that has happened in this app once already, which is what
`_safe_reason` in `finnhub_metrics.py` exists to stop.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

#: Firecrawl's REST version this module speaks. v2 returns map links as objects
#: and v1 as bare strings, so `_links_of` reads both shapes; a version bump
#: should not silently start returning nothing.
BASE_URL = "https://api.firecrawl.dev/v2"

#: One page of markdown. Firecrawl's own LLM extraction costs several times
#: this and is deliberately not used: the numbers come out of the text in a
#: session, which spends nothing at all.
CREDITS_PER_SCRAPE = 1
CREDITS_PER_MAP = 1

#: The entire balance, not a monthly allowance. Written down rather than
#: assumed, because every guard below is arithmetic against it.
DEFAULT_BUDGET = 1000

#: Below this many characters a scrape counts as failed. A cookie wall or a
#: JavaScript shell answers 200 with no content; letting that through as "the
#: press release" is the failure this module exists to prevent.
MIN_USEFUL_CHARS = 200

TIMEOUT = 120


# ==============================================================================
# What a fetch returns
# ==============================================================================

@dataclass(frozen=True)
class FetchResult:
    """
    One page, or an explicit account of why there is no page.

    `ok` is the only thing a caller may branch on. `markdown` is None whenever
    `ok` is False — there is no half-success here, because a caller that reads
    `markdown or ""` would turn a missing filing into a company with no news.
    """

    url: str
    ok: bool
    markdown: str | None = None
    #: Czech, meant to be shown to the owner rather than logged and forgotten.
    reason: str | None = None
    from_cache: bool = False
    credits: int = 0
    path: Path | None = None
    fetched_at: str | None = None


# ==============================================================================
# The meter
# ==============================================================================

@dataclass
class Ledger:
    """
    Every credit this app has ever spent, and what it bought.

    Kept as a file rather than a counter in memory because the point is to
    survive: the budget is consumed across sessions, scripts and scheduled
    runs, and a balance that resets on restart is not a balance.
    """

    path: Path
    budget: int = DEFAULT_BUDGET
    spent: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path, *, budget: int = DEFAULT_BUDGET) -> "Ledger":
        if not path.exists():
            return cls(path=path, budget=budget)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt ledger must not read as a fresh budget. Refusing to
            # spend is recoverable; spending twice is not.
            return cls(path=path, budget=0, spent=0)
        return cls(
            path=path,
            budget=int(raw.get("budget", budget)),
            spent=int(raw.get("spent", 0)),
            calls=list(raw.get("calls", [])),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"budget": self.budget, "spent": self.spent, "calls": self.calls},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def remaining(self) -> int:
        return max(0, self.budget - self.spent)

    def can_afford(self, credits: int) -> bool:
        return self.remaining() >= credits

    def charge(self, credits: int, *, what: str, url: str) -> None:
        """Record a spend. Called only after the response actually arrived."""
        self.spent += credits
        self.calls.append(
            {
                "at": _now(),
                "what": what,
                "url": url,
                "credits": credits,
                "spent_after": self.spent,
            }
        )
        self.save()


# ==============================================================================
# The cache
# ==============================================================================

def _slug(url: str) -> str:
    """A readable file name that still cannot collide."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    tail = re.sub(r"[^a-zA-Z0-9]+", "-", url.split("://", 1)[-1]).strip("-").lower()
    return f"{tail[:60]}-{digest}" if tail else digest


def cache_paths(cache_dir: Path, url: str) -> tuple[Path, Path]:
    """The markdown file and its provenance sidecar."""
    base = cache_dir / _slug(url)
    return base.with_suffix(".md"), base.with_suffix(".json")


def map_cache_path(cache_dir: Path, domain: str, search: str | None) -> Path:
    """
    Where a site map is kept.

    A map is one credit for hundreds of URLs, and the temptation is to read the
    first twenty, discard the rest and pay again for the twenty-first. Keyed by
    the search phrase as well as the domain, because a filtered map is a
    different answer to a different question.
    """
    return cache_dir / f"map-{_slug(domain + '|' + (search or ''))}.json"


def read_cached(cache_dir: Path, url: str) -> FetchResult | None:
    """What is already on disk for this URL, or None if nothing is."""
    page, sidecar = cache_paths(cache_dir, url)
    if not page.exists():
        return None
    text = page.read_text(encoding="utf-8")
    fetched_at = None
    if sidecar.exists():
        try:
            fetched_at = json.loads(sidecar.read_text(encoding="utf-8")).get("fetched_at")
        except (json.JSONDecodeError, OSError):
            fetched_at = None
    return FetchResult(
        url=url,
        ok=True,
        markdown=text,
        from_cache=True,
        credits=0,
        path=page,
        fetched_at=fetched_at,
    )


def _write_cache(cache_dir: Path, url: str, markdown: str, meta: dict[str, Any]) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    page, sidecar = cache_paths(cache_dir, url)
    page.write_text(markdown, encoding="utf-8")
    sidecar.write_text(
        json.dumps(
            {"url": url, "fetched_at": _now(), "metadata": meta},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return page


# ==============================================================================
# Talking to Firecrawl
# ==============================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_reason(error: Exception, key: str) -> str:
    """
    A failure described without the credential that caused it.

    Same guard as `finnhub_metrics._safe_reason`, and for the same reason: the
    text of an HTTPError is built from the request, and anything the request
    carried is in it.
    """
    text = str(error)
    if key:
        text = text.replace(key, "***")
    return f"{type(error).__name__}: {text[:300]}" if text else type(error).__name__


def _post(
    endpoint: str,
    payload: dict[str, Any],
    *,
    key: str,
    session: requests.Session | None,
) -> dict[str, Any]:
    http = session or requests.Session()
    response = http.post(
        f"{BASE_URL}/{endpoint}",
        json=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def scrape(
    url: str,
    *,
    key: str,
    cache_dir: Path,
    ledger: Ledger,
    session: requests.Session | None = None,
    force: bool = False,
) -> FetchResult:
    """
    One page as markdown, from disk if it is there and from Firecrawl if not.

    Never raises on a network or budget problem: the point of this module is
    that the caller sees a reason instead of an exception it might swallow.
    """
    if not force:
        cached = read_cached(cache_dir, url)
        if cached is not None:
            return cached

    if not key:
        return FetchResult(
            url=url,
            ok=False,
            reason="chybí FIRECRAWL_API_KEY — stránka se nestahovala",
        )

    if not ledger.can_afford(CREDITS_PER_SCRAPE):
        return FetchResult(
            url=url,
            ok=False,
            reason=(
                f"vyčerpaný rozpočet Firecrawlu ({ledger.spent}/{ledger.budget} "
                "kreditů) — zdroj je nedosažitelný, ne prázdný"
            ),
        )

    try:
        payload = _post(
            "scrape",
            {
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
            },
            key=key,
            session=session,
        )
    except (requests.RequestException, ValueError) as exc:
        return FetchResult(
            url=url,
            ok=False,
            reason=f"Firecrawl selhal: {_safe_reason(exc, key)}",
        )

    # The response arrived, so the credit is gone whatever it contains.
    ledger.charge(CREDITS_PER_SCRAPE, what="scrape", url=url)

    data = payload.get("data") or {}
    markdown = (data.get("markdown") or "").strip()
    if len(markdown) < MIN_USEFUL_CHARS:
        return FetchResult(
            url=url,
            ok=False,
            reason=(
                f"stránka vrátila jen {len(markdown)} znaků — nejspíš JS obal "
                "nebo cookie zeď, ne obsah"
            ),
            credits=CREDITS_PER_SCRAPE,
        )

    path = _write_cache(cache_dir, url, markdown, data.get("metadata") or {})
    return FetchResult(
        url=url,
        ok=True,
        markdown=markdown,
        credits=CREDITS_PER_SCRAPE,
        path=path,
        fetched_at=_now(),
    )


def _links_of(payload: dict[str, Any]) -> list[str]:
    """Map results as plain URLs, whichever shape the API version returns."""
    out: list[str] = []
    for item in payload.get("links") or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("url"):
            out.append(str(item["url"]))
    return out


def map_site(
    domain: str,
    *,
    key: str,
    ledger: Ledger,
    search: str | None = None,
    session: requests.Session | None = None,
    cache_dir: Path | None = None,
    force: bool = False,
) -> tuple[list[str], str | None]:
    """
    Every URL Firecrawl knows on a domain, optionally filtered by a phrase.

    One credit for the whole site, which is what makes it the right way to find
    a company's quarterly releases: map once, then scrape only the handful of
    pages that matter. The full list is kept on disk — reading twenty of eight
    hundred URLs and paying again for the twenty-first is the obvious way to
    waste a budget this size. Returns `(urls, reason)`; a reason means the list
    is empty because something failed, not because the site is.
    """
    cached = map_cache_path(cache_dir, domain, search) if cache_dir else None
    if cached is not None and cached.exists() and not force:
        try:
            return list(json.loads(cached.read_text(encoding="utf-8"))["urls"]), None
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # unreadable cache is not a reason to refuse; pay again

    if not key:
        return [], "chybí FIRECRAWL_API_KEY"
    if not ledger.can_afford(CREDITS_PER_MAP):
        return [], (
            f"vyčerpaný rozpočet Firecrawlu ({ledger.spent}/{ledger.budget} kreditů)"
        )

    body: dict[str, Any] = {"url": domain}
    if search:
        body["search"] = search

    try:
        payload = _post("map", body, key=key, session=session)
    except (requests.RequestException, ValueError) as exc:
        return [], f"Firecrawl selhal: {_safe_reason(exc, key)}"

    ledger.charge(CREDITS_PER_MAP, what="map", url=domain)
    urls = _links_of(payload)

    if cached is not None and urls:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(
            json.dumps(
                {"domain": domain, "search": search, "at": _now(), "urls": urls},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return urls, None
