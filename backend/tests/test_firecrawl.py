"""
A metered source has to fail loudly, and must never charge twice for one page.

The balance is a fixed number of pages for the life of the account, so the two
things that can go wrong here are not the usual ones. Spending twice for the
same URL wastes a budget that does not refill. Coming back empty when the
budget is gone is worse — the whole portfolio's Canadian half would read as "no
filings found", which is this app's cardinal defect wearing a new coat.
"""

import json

import pytest
import requests

from app.services import firecrawl
from app.services.firecrawl import (
    CREDITS_PER_SCRAPE,
    FetchResult,
    Ledger,
    _links_of,
    _safe_reason,
    cache_paths,
    map_site,
    read_cached,
    scrape,
)

KEY = "fc-secret-key-value"
URL = "https://www.example-issuer.com/news/q1-2027-results"

PAGE = "# Q1 2027 Results\n\n" + ("Revenue increased to CAD 4.1 million. " * 20)


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for url: ...?key={KEY}")

    def json(self):
        return self._payload


class _Session:
    """A stand-in that counts calls, because the count is what is being tested."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if not self._responses:
            raise AssertionError("more requests than the test allowed")
        return self._responses.pop(0)


def _ledger(tmp_path, *, budget=1000, spent=0):
    led = Ledger(path=tmp_path / "ledger.json", budget=budget, spent=spent)
    led.save()
    return led


# ==============================================================================
# The budget is real
# ==============================================================================

def test_exhausted_budget_is_a_stated_reason_not_an_empty_page(tmp_path):
    """
    The failure this module exists to prevent. An engine that receives "" for a
    quarterly release concludes the company published nothing.
    """
    led = _ledger(tmp_path, budget=10, spent=10)
    session = _Session()  # any call at all would be a failure

    result = scrape(URL, key=KEY, cache_dir=tmp_path / "pages", ledger=led, session=session)

    assert result.ok is False
    assert result.markdown is None
    assert "vyčerpaný rozpočet" in result.reason
    assert session.calls == []


def test_a_missing_key_does_not_look_like_a_missing_page(tmp_path):
    led = _ledger(tmp_path)
    result = scrape(URL, key="", cache_dir=tmp_path / "pages", ledger=led, session=_Session())

    assert result.ok is False
    assert "FIRECRAWL_API_KEY" in result.reason
    assert led.spent == 0


def test_spending_is_recorded_where_it_survives_a_restart(tmp_path):
    led = _ledger(tmp_path)
    session = _Session(_Response({"success": True, "data": {"markdown": PAGE}}))

    scrape(URL, key=KEY, cache_dir=tmp_path / "pages", ledger=led, session=session)

    reloaded = Ledger.load(tmp_path / "ledger.json")
    assert reloaded.spent == CREDITS_PER_SCRAPE
    assert reloaded.remaining() == reloaded.budget - CREDITS_PER_SCRAPE
    assert reloaded.calls[-1]["url"] == URL


def test_a_corrupt_ledger_refuses_to_spend_rather_than_starting_over(tmp_path):
    """
    A ledger that cannot be read is not a fresh thousand credits. Refusing is
    recoverable by hand; spending the balance a second time is not.
    """
    path = tmp_path / "ledger.json"
    path.write_text("{ this is not json", encoding="utf-8")

    led = Ledger.load(path)

    assert led.can_afford(1) is False


# ==============================================================================
# A page is paid for once
# ==============================================================================

def test_second_call_for_the_same_url_costs_nothing(tmp_path):
    cache = tmp_path / "pages"
    led = _ledger(tmp_path)
    session = _Session(_Response({"success": True, "data": {"markdown": PAGE}}))

    first = scrape(URL, key=KEY, cache_dir=cache, ledger=led, session=session)
    second = scrape(URL, key=KEY, cache_dir=cache, ledger=led, session=_Session())

    assert first.credits == CREDITS_PER_SCRAPE and first.from_cache is False
    assert second.ok is True and second.credits == 0 and second.from_cache is True
    assert second.markdown == first.markdown
    assert led.spent == CREDITS_PER_SCRAPE


def test_the_cached_page_keeps_where_it_came_from(tmp_path):
    cache = tmp_path / "pages"
    led = _ledger(tmp_path)
    session = _Session(_Response({"success": True, "data": {"markdown": PAGE}}))

    scrape(URL, key=KEY, cache_dir=cache, ledger=led, session=session)

    _, sidecar = cache_paths(cache, URL)
    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert saved["url"] == URL
    assert saved["fetched_at"]
    assert read_cached(cache, URL).fetched_at == saved["fetched_at"]


def test_nothing_cached_reads_as_nothing_cached(tmp_path):
    assert read_cached(tmp_path / "pages", URL) is None


# ==============================================================================
# A page that is not a page
# ==============================================================================

def test_a_javascript_shell_is_a_failure_not_a_short_release(tmp_path):
    """
    A cookie wall answers 200 with a few dozen characters. Written to the cache
    it would be read forever as the company's quarterly release.
    """
    cache = tmp_path / "pages"
    led = _ledger(tmp_path)
    session = _Session(_Response({"success": True, "data": {"markdown": "Enable JS"}}))

    result = scrape(URL, key=KEY, cache_dir=cache, ledger=led, session=session)

    assert result.ok is False
    assert result.markdown is None
    assert "znaků" in result.reason
    assert read_cached(cache, URL) is None  # not cached, so a retry is possible
    assert led.spent == CREDITS_PER_SCRAPE  # the response arrived; the credit is gone


def test_a_network_failure_is_reported_and_costs_nothing(tmp_path):
    led = _ledger(tmp_path)
    session = _Session(_Response({}, status=500))

    result = scrape(URL, key=KEY, cache_dir=tmp_path / "pages", ledger=led, session=session)

    assert result.ok is False
    assert "Firecrawl selhal" in result.reason
    assert led.spent == 0


# ==============================================================================
# The key stays out of everything
# ==============================================================================

def test_the_key_never_appears_in_a_failure_reason(tmp_path):
    """
    `requests` builds HTTPError text out of the request URL. This app has
    already written a live credential into a log once.
    """
    led = _ledger(tmp_path)
    session = _Session(_Response({}, status=403))

    result = scrape(URL, key=KEY, cache_dir=tmp_path / "pages", ledger=led, session=session)

    assert KEY not in result.reason
    assert "***" in result.reason


def test_safe_reason_survives_an_error_with_no_message():
    assert KEY not in _safe_reason(requests.RequestException(), KEY)


def test_the_key_travels_in_the_header_and_not_in_the_body(tmp_path):
    led = _ledger(tmp_path)
    session = _Session(_Response({"success": True, "data": {"markdown": PAGE}}))

    scrape(URL, key=KEY, cache_dir=tmp_path / "pages", ledger=led, session=session)

    call = session.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert KEY not in call["url"]
    assert KEY not in json.dumps(call["json"])


# ==============================================================================
# Map: one credit for a whole site
# ==============================================================================

def test_map_reads_both_api_shapes():
    """v2 returns objects, v1 returns strings. A version bump must not go quiet."""
    assert _links_of({"links": ["https://a.com/x"]}) == ["https://a.com/x"]
    assert _links_of({"links": [{"url": "https://a.com/y", "title": "Y"}]}) == [
        "https://a.com/y"
    ]
    assert _links_of({}) == []


def test_a_map_is_paid_for_once(tmp_path):
    """
    One credit buys hundreds of URLs. Reading the first twenty and paying again
    for the twenty-first is how a budget this size disappears — it nearly did.
    """
    cache = tmp_path / "pages"
    led = _ledger(tmp_path)
    links = [f"https://a.com/{n}" for n in range(300)]
    session = _Session(_Response({"success": True, "links": links}))

    first, _ = map_site("https://a.com", key=KEY, ledger=led, cache_dir=cache, session=session)
    second, reason = map_site(
        "https://a.com", key=KEY, ledger=led, cache_dir=cache, session=_Session()
    )

    assert first == links and second == links and reason is None
    assert led.spent == 1


def test_a_filtered_map_is_a_different_question(tmp_path):
    """
    `search='results'` returns a different set. Serving it from the unfiltered
    map's cache would answer with pages nobody asked for.
    """
    cache = tmp_path / "pages"
    led = _ledger(tmp_path)
    session = _Session(
        _Response({"success": True, "links": ["https://a.com/all"]}),
        _Response({"success": True, "links": ["https://a.com/results"]}),
    )

    plain, _ = map_site("https://a.com", key=KEY, ledger=led, cache_dir=cache, session=session)
    filtered, _ = map_site(
        "https://a.com", key=KEY, ledger=led, search="results", cache_dir=cache, session=session
    )

    assert plain == ["https://a.com/all"]
    assert filtered == ["https://a.com/results"]
    assert led.spent == 2


def test_map_on_an_exhausted_budget_says_so_instead_of_returning_no_links(tmp_path):
    led = _ledger(tmp_path, budget=1, spent=1)

    urls, reason = map_site("https://www.example-issuer.com", key=KEY, ledger=led, session=_Session())

    assert urls == []
    assert "vyčerpaný rozpočet" in reason
