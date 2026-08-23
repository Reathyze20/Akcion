"""
SEC EDGAR — annual reports, quarterly reports and insider transactions.

Pulls 10-K, 10-Q and Form 4 filings for held positions straight from the
regulator, so the app reads primary sources rather than someone's summary of
them. Canon §1 calls this the edge: the value is in the fundamentals of the
company, and these are the documents that state them under penalty of perjury.

Two things here are easy to get wrong, and both would produce the kind of
confident-but-manufactured signal this codebase has had to remove repeatedly.

**1. Not every holding files with the SEC.**

Verified 2026-08-22 against the live ticker index: of fourteen holdings, five
are absent — GSI.V, KUYA.V, IMP.V, QIPT and UMD trade on TSX Venture and other
non-US venues and file with their own regulators. "No filings" for those is a
fact about the exchange. "No filings" for TechPrecision would be a fact about
the company. Rendering them identically would invent the second from the first,
so `CoverageStatus` keeps them apart and every result carries one.

**2. A Form 4 "disposal" is usually not a sale.**

The first Form 4 this module ever fetched (TPCS, filed 2026-08-20) carries
transaction code `G` — a bona fide gift, price $0.00, flagged `D` for disposed.
Counting that as an insider selling 8,000 shares would be a bearish signal
manufactured out of a charitable donation. The same trap sits in `F` (shares
withheld to pay tax on a vest — the insider chose nothing), `M` (option
exercise) and `A` (a grant the board handed over).

Only two codes carry a decision to spend or raise money at the market price:
`P` and `S`. Everything else is recorded, kept, and explicitly marked as
carrying no signal. See `TransactionCode`.

SEC access rules
----------------
A descriptive User-Agent naming a contact is required by SEC policy, and
requests are limited to 10/second. Both are honoured here.
"""

from __future__ import annotations

import html as html_lib
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Final

import requests
from loguru import logger


# ==============================================================================
# Access
# ==============================================================================

#: SEC requires a User-Agent identifying the requester with a contact address.
#: Requests without one are refused, and SEC has blocked repeat offenders.
USER_AGENT: Final[str] = "Akcion Investment Research reathyze20@gmail.com"

TICKER_INDEX_URL: Final[str] = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL: Final[str] = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL: Final[str] = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
INDEX_HEADERS_URL: Final[str] = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession_dashed}-index-headers.html"
)

REQUEST_TIMEOUT_SECONDS: Final[int] = 20

#: SEC's published ceiling is 10 requests/second. Staying under it is not
#: optional — exceeding it gets the IP blocked, and an app that cannot read
#: filings at all is worse than a slow one.
MIN_REQUEST_INTERVAL: Final[float] = 0.12


class SecError(Exception):
    """SEC could not be read. Never silently downgraded to 'nothing found'."""


# ==============================================================================
# What we know about a ticker's coverage
# ==============================================================================

class CoverageStatus(str, Enum):
    """Why a ticker has the filings it has — or has none."""

    COVERED = "COVERED"
    """The company files with the SEC and we read its filings."""

    NOT_AN_SEC_FILER = "NOT_AN_SEC_FILER"
    """
    Absent from SEC's ticker index — a foreign listing filing elsewhere.
    Says nothing whatsoever about the company.
    """

    LOOKUP_FAILED = "LOOKUP_FAILED"
    """SEC could not be reached. Also says nothing about the company."""

    FOREIGN_PRIVATE_ISSUER = "FOREIGN_PRIVATE_ISSUER"
    """
    Files with the SEC, but on the foreign schedule: 20-F/40-F annually and
    6-K for interim news, never 10-K or 10-Q. Reporting "0 filings" for one of
    these reads as a silent company; it is a different form set.
    """

    NOT_A_TICKER = "NOT_A_TICKER"
    """
    The identifier is an ISIN, not a ticker. Three portfolio rows are stored
    this way (e.g. CA00654B1040). Looking it up and reporting "does not file
    with the SEC" would answer a question nobody asked.
    """


# ==============================================================================
# Form 4 transaction codes
# ==============================================================================

class Signal(str, Enum):
    """Whether a transaction reflects a decision worth reading."""

    BUY = "BUY"
    SELL = "SELL"
    NO_SIGNAL = "NO_SIGNAL"


@dataclass(frozen=True)
class TransactionCode:
    """One SEC Table I/II code and what it actually means."""

    code: str
    label_cs: str
    signal: Signal


#: The full Table I/II code set, each with the only honest reading of it.
#:
#: Only P and S involve an insider choosing to transact at a market price.
#: Everything else is administrative, non-discretionary, or a transfer that
#: moves no money — and is therefore NO_SIGNAL no matter which direction the
#: shares moved.
TRANSACTION_CODES: Final[dict[str, TransactionCode]] = {
    "P": TransactionCode("P", "nákup na trhu", Signal.BUY),
    "S": TransactionCode("S", "prodej na trhu", Signal.SELL),
    "A": TransactionCode("A", "přidělené akcie (grant)", Signal.NO_SIGNAL),
    "D": TransactionCode("D", "vrácení akcií firmě", Signal.NO_SIGNAL),
    "F": TransactionCode("F", "akcie zadržené na daň", Signal.NO_SIGNAL),
    "G": TransactionCode("G", "dar", Signal.NO_SIGNAL),
    "M": TransactionCode("M", "uplatnění opce", Signal.NO_SIGNAL),
    "C": TransactionCode("C", "konverze derivátu", Signal.NO_SIGNAL),
    "E": TransactionCode("E", "expirace krátké pozice", Signal.NO_SIGNAL),
    "H": TransactionCode("H", "expirace dlouhé pozice", Signal.NO_SIGNAL),
    "I": TransactionCode("I", "diskreční transakce", Signal.NO_SIGNAL),
    "J": TransactionCode("J", "jiné nabytí/pozbytí", Signal.NO_SIGNAL),
    "K": TransactionCode("K", "equity swap", Signal.NO_SIGNAL),
    "L": TransactionCode("L", "drobné nabytí", Signal.NO_SIGNAL),
    "O": TransactionCode("O", "uplatnění opce mimo peníze", Signal.NO_SIGNAL),
    "U": TransactionCode("U", "tender při změně kontroly", Signal.NO_SIGNAL),
    "W": TransactionCode("W", "dědictví", Signal.NO_SIGNAL),
    "X": TransactionCode("X", "uplatnění opce v penězích", Signal.NO_SIGNAL),
    "Z": TransactionCode("Z", "hlasovací trust", Signal.NO_SIGNAL),
}


def classify(code: str | None) -> TransactionCode:
    """
    Read a transaction code.

    An unrecognised code is NO_SIGNAL, never a guess. SEC adds codes; guessing
    the direction of one we have not seen would be the same mistake as reading
    a gift as a sale.
    """
    if not code:
        return TransactionCode("?", "kód chybí", Signal.NO_SIGNAL)
    key = code.strip().upper()[:1]
    return TRANSACTION_CODES.get(
        key, TransactionCode(key, f"neznámý kód {key}", Signal.NO_SIGNAL)
    )


# ==============================================================================
# Results
# ==============================================================================

@dataclass(frozen=True)
class Filing:
    """One 10-K / 10-Q / 8-K filing."""

    form: str
    filed: date
    period: date | None
    accession: str
    document: str
    cik: str

    @property
    def url(self) -> str:
        return ARCHIVE_URL.format(
            cik=self.cik.lstrip("0"),
            accession=self.accession.replace("-", ""),
            document=self.document,
        )


#: Forms whose filed document is a cover page, not the report. SEC's own
#: instruction for Form 6-K is that the material being furnished is attached as
#: an exhibit; the 6-K itself says "the following is furnished herewith" and
#: names it. 8-K works the same way for a results announcement.
#:
#: Found 2026-08-23 on a live holding: RADCOM's 2026-08-12 6-K rendered to 1,777
#: characters — the entire second quarter, 133 kB of it, was the EX-99.1 sitting
#: beside it. Analysing the cover page alone returned no findings, and "no
#: findings" is what the app then showed for 9.9 % of the portfolio. That is the
#: envelope being reported as the letter.
WRAPPER_FORMS: Final[frozenset[str]] = frozenset({"6-K", "8-K"})

#: EX-99 is where furnished substance lives: press releases, results tables,
#: investor decks. Other exhibit families are contracts, consents and
#: certifications — real documents, but not this quarter's news.
SUBSTANTIVE_EXHIBIT: Final[re.Pattern[str]] = re.compile(r"^EX-99(\.\d+)*$", re.I)

_DOCUMENT_BLOCK: Final[re.Pattern[str]] = re.compile(
    r"<DOCUMENT>(.*?)(?:</DOCUMENT>|\Z)", re.S | re.I
)


def _sgml_field(block: str, name: str) -> str | None:
    """Read one `<TAG>value` line out of an EDGAR document header."""
    match = re.search(rf"<{name}>[ \t]*(.*)", block, re.I)
    return match.group(1).strip() or None if match else None


@dataclass(frozen=True)
class FilingDocument:
    """One file inside a filing, as EDGAR's own manifest describes it."""

    type: str
    filename: str
    description: str | None
    accession: str
    cik: str

    @property
    def is_substantive_exhibit(self) -> bool:
        return bool(SUBSTANTIVE_EXHIBIT.match(self.type))

    @property
    def url(self) -> str:
        return ARCHIVE_URL.format(
            cik=self.cik.lstrip("0"),
            accession=self.accession.replace("-", ""),
            document=self.filename,
        )


@dataclass(frozen=True)
class InsiderTransaction:
    """One line of a Form 4."""

    ticker: str
    insider: str
    is_director: bool
    is_officer: bool
    officer_title: str | None
    is_ten_percent_owner: bool
    transaction_date: date | None
    code: TransactionCode
    shares: float | None
    price_per_share: float | None
    acquired: bool
    shares_owned_after: float | None
    filed: date
    accession: str

    @property
    def value(self) -> float | None:
        """Money that changed hands, when that is a meaningful question."""
        if self.code.signal is Signal.NO_SIGNAL:
            # A grant or a gift has no market value to the insider. Reporting
            # `shares * 0` as "$0 traded" invites reading it as a real trade.
            return None
        if self.shares is None or self.price_per_share is None:
            return None
        return self.shares * self.price_per_share


@dataclass
class TickerCoverage:
    """Everything SEC can tell us about one ticker, including nothing."""

    ticker: str
    status: CoverageStatus
    cik: str | None = None
    company_name: str | None = None
    filings: list[Filing] = field(default_factory=list)
    insider_transactions: list[InsiderTransaction] = field(default_factory=list)
    note: str | None = None

    @property
    def has_signal_bearing_trades(self) -> bool:
        return any(
            t.code.signal is not Signal.NO_SIGNAL
            for t in self.insider_transactions
        )


# ==============================================================================
# Client
# ==============================================================================

class SecEdgarClient:
    """Reads SEC EDGAR, politely and without inventing anything."""

    def __init__(self, user_agent: str = USER_AGENT):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self._ticker_index: dict[str, dict[str, Any]] | None = None
        self._last_request_at = 0.0

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _get(self, url: str) -> requests.Response:
        """One rate-limited request."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

        response = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 403:
            raise SecError(
                "SEC odmítla požadavek (403) — nejspíš chybný User-Agent "
                "nebo překročený limit požadavků."
            )
        if response.status_code != 200:
            raise SecError(f"SEC vrátila {response.status_code} pro {url}")
        return response

    # ------------------------------------------------------------------
    # Ticker to CIK
    # ------------------------------------------------------------------

    def _load_ticker_index(self) -> dict[str, dict[str, Any]]:
        if self._ticker_index is None:
            payload = self._get(TICKER_INDEX_URL).json()
            self._ticker_index = {
                entry["ticker"].upper(): entry for entry in payload.values()
            }
            logger.info("SEC ticker index: {} firem", len(self._ticker_index))
        return self._ticker_index

    #: Exchange suffixes that mean the listing is not American.
    FOREIGN_SUFFIXES: Final[dict[str, str]] = {
        "V": "TSX Venture", "TO": "Toronto", "CN": "CSE", "NE": "NEO",
        "L": "London", "HK": "Hong Kong", "AX": "ASX", "DE": "Xetra",
        "PA": "Euronext Paris", "AS": "Euronext Amsterdam", "SW": "SIX",
        "ST": "Stockholm", "OL": "Oslo", "MI": "Milan", "MC": "Madrid",
        "T": "Tokyo", "KS": "Korea", "TA": "Tel Aviv", "WA": "Warsaw",
    }

    #: An ISIN: two country letters, nine alphanumerics, one check digit.
    ISIN_PATTERN: Final[re.Pattern] = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

    @classmethod
    def _foreign_exchange(cls, ticker: str) -> str | None:
        """
        The exchange named by a ticker's suffix, if it names a foreign one.

        The suffix used to be stripped and the bare base looked up in SEC's
        index. That is how `DBO.TO` — a Toronto listing — matched "Invesco DB
        Oil Fund", a US ETF, and got a whole quarter of someone else's numbers
        attached to it. A wrong company is worse than no company: it looks
        exactly as trustworthy as the truth.
        """
        parts = ticker.upper().strip().rsplit(".", 1)
        if len(parts) != 2:
            return None
        return cls.FOREIGN_SUFFIXES.get(parts[1])

    def resolve_cik(self, ticker: str) -> tuple[str | None, str | None]:
        """
        (CIK, company name) for a ticker, or (None, None) if SEC has no such
        filer. Not an error — most of the world's companies do not file here.
        """
        index = self._load_ticker_index()
        # Exact match only. See `_foreign_exchange` for why the suffix is not
        # stripped and retried.
        entry = index.get(ticker.upper().strip())
        if entry is None:
            return None, None
        return str(entry["cik_str"]).zfill(10), entry.get("title")

    # ------------------------------------------------------------------
    # Filings
    # ------------------------------------------------------------------

    def fetch_coverage(
        self,
        ticker: str,
        *,
        forms: tuple[str, ...] = ("10-K", "10-Q"),
        max_filings: int = 4,
        max_insider_filings: int = 10,
    ) -> TickerCoverage:
        """
        Everything SEC holds for one ticker — or a clear statement of why not.

        Never raises for a ticker SEC does not cover: that is a normal answer
        and it comes back as `CoverageStatus.NOT_AN_SEC_FILER`. Only a genuine
        transport failure produces `LOOKUP_FAILED`, and the two are kept apart
        because one is about the company's listing and the other is about us.
        """
        ticker = ticker.upper().strip()

        # An ISIN is not a ticker. Three portfolio rows are stored as one, and
        # answering "does not file with the SEC" for CA00654B1040 would be
        # answering a question nobody asked.
        if self.ISIN_PATTERN.match(ticker):
            return TickerCoverage(
                ticker=ticker,
                status=CoverageStatus.NOT_A_TICKER,
                note=(
                    f"{ticker} vypadá jako ISIN, ne ticker — u SEC ho dohledat "
                    f"nelze. Doplň v pozici burzovní symbol."
                ),
            )

        # A foreign exchange suffix settles it without a lookup, and stops the
        # base symbol being matched against an unrelated US company.
        exchange = self._foreign_exchange(ticker)
        if exchange is not None:
            return TickerCoverage(
                ticker=ticker,
                status=CoverageStatus.NOT_AN_SEC_FILER,
                note=(
                    f"{ticker} je listovaný na {exchange} — podává u tamního "
                    f"regulátora, ne u SEC. O firmě samotné to neříká nic."
                ),
            )

        try:
            cik, name = self.resolve_cik(ticker)
        except SecError as e:
            return TickerCoverage(
                ticker=ticker, status=CoverageStatus.LOOKUP_FAILED,
                note=f"SEC nedostupná: {e}",
            )

        if cik is None:
            return TickerCoverage(
                ticker=ticker,
                status=CoverageStatus.NOT_AN_SEC_FILER,
                note=(
                    f"{ticker} není v rejstříku SEC — podává u jiného "
                    f"regulátora. O firmě samotné to neříká nic."
                ),
            )

        try:
            payload = self._get(SUBMISSIONS_URL.format(cik=cik)).json()
        except SecError as e:
            return TickerCoverage(
                ticker=ticker, status=CoverageStatus.LOOKUP_FAILED,
                cik=cik, company_name=name, note=f"SEC nedostupná: {e}",
            )

        recent = payload.get("filings", {}).get("recent", {})
        coverage = TickerCoverage(
            ticker=ticker,
            status=CoverageStatus.COVERED,
            cik=cik,
            company_name=payload.get("name") or name,
        )
        coverage.filings = self._select_filings(recent, cik, forms, max_filings)

        # No 10-K/10-Q at all, but 20-F/40-F present: a foreign private issuer
        # on a different form schedule. Leaving this as COVERED with zero
        # filings would read as a company that has stopped reporting.
        if not coverage.filings:
            foreign_forms = self._select_filings(
                recent, cik, ("20-F", "40-F", "6-K"), 4
            )
            if foreign_forms:
                coverage.status = CoverageStatus.FOREIGN_PRIVATE_ISSUER
                coverage.filings = foreign_forms
                kinds = ", ".join(sorted({f.form for f in foreign_forms}))
                coverage.note = (
                    f"{ticker} je zahraniční emitent — podává {kinds}, ne "
                    f"10-K/10-Q. Čtvrtletní čísla nemusí být k dispozici."
                )

        coverage.insider_transactions = self._fetch_insider_transactions(
            recent, cik, ticker, max_insider_filings
        )
        return coverage

    def fetch_documents(self, cik: str, accession: str) -> list[FilingDocument]:
        """
        Every file inside one filing, with the type EDGAR itself assigned it.

        Read from `-index-headers.html`, which carries the submission's SGML
        manifest — `<TYPE>EX-99.1`, `<FILENAME>`, `<DESCRIPTION>`. Guessing the
        type from the filename would work for one filing agent and quietly fail
        for the next; the manifest is what EDGAR indexes on.

        Raises SecError if the manifest cannot be read. An empty list means the
        manifest was read and lists nothing, which is a different answer.
        """
        url = INDEX_HEADERS_URL.format(
            cik=cik.lstrip("0"),
            accession=accession.replace("-", ""),
            accession_dashed=accession,
        )
        # The manifest is HTML-escaped SGML: the tags arrive as &lt;TYPE&gt;.
        raw = html_lib.unescape(self._get(url).text)

        documents: list[FilingDocument] = []
        for block in _DOCUMENT_BLOCK.findall(raw):
            type_ = _sgml_field(block, "TYPE")
            filename = _sgml_field(block, "FILENAME")
            if not type_ or not filename:
                continue
            documents.append(FilingDocument(
                type=type_.upper(),
                filename=filename,
                description=_sgml_field(block, "DESCRIPTION"),
                accession=accession,
                cik=cik,
            ))
        return documents

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date() if value else None
        except ValueError:
            return None

    def _select_filings(
        self,
        recent: dict[str, list],
        cik: str,
        forms: tuple[str, ...],
        limit: int,
    ) -> list[Filing]:
        """The most recent `limit` filings of each requested form type."""
        wanted = {f.upper() for f in forms}
        per_form: dict[str, list[Filing]] = {f: [] for f in wanted}

        for i, form in enumerate(recent.get("form", [])):
            form_upper = form.upper()
            if form_upper not in wanted or len(per_form[form_upper]) >= limit:
                continue
            per_form[form_upper].append(Filing(
                form=form_upper,
                filed=self._parse_date(recent["filingDate"][i]),
                period=self._parse_date(recent.get("reportDate", [None] * (i + 1))[i]),
                accession=recent["accessionNumber"][i],
                document=recent["primaryDocument"][i],
                cik=cik,
            ))

        out = [f for group in per_form.values() for f in group]
        out.sort(key=lambda f: f.filed or date.min, reverse=True)
        return out

    # ------------------------------------------------------------------
    # Form 4
    # ------------------------------------------------------------------

    def _fetch_insider_transactions(
        self,
        recent: dict[str, list],
        cik: str,
        ticker: str,
        limit: int,
    ) -> list[InsiderTransaction]:
        """Parse the most recent Form 4 filings into individual transactions."""
        transactions: list[InsiderTransaction] = []
        seen = 0

        for i, form in enumerate(recent.get("form", [])):
            if form.strip() != "4" or seen >= limit:
                continue
            seen += 1

            accession = recent["accessionNumber"][i]
            document = recent["primaryDocument"][i]
            filed = self._parse_date(recent["filingDate"][i])

            try:
                xml = self._get(ARCHIVE_URL.format(
                    cik=cik.lstrip("0"),
                    accession=accession.replace("-", ""),
                    # `primaryDocument` points at the XSL-rendered view
                    # (xslF345X06/foo.xml); the raw XML sits beside it.
                    document=document.split("/")[-1],
                )).text
                transactions.extend(
                    parse_form4(xml, ticker=ticker, filed=filed, accession=accession)
                )
            except (SecError, ET.ParseError) as e:
                # One unreadable filing must not discard the others.
                logger.warning("Form 4 {} nelze přečíst: {}", accession, e)

        transactions.sort(
            key=lambda t: t.transaction_date or date.min, reverse=True
        )
        return transactions


# ==============================================================================
# Form 4 parsing
# ==============================================================================

def _text(node: ET.Element | None, path: str) -> str | None:
    """Read `path/value` or `path`, whichever the schema used."""
    if node is None:
        return None
    found = node.find(f"{path}/value")
    if found is None:
        found = node.find(path)
    return found.text.strip() if found is not None and found.text else None


def _number(node: ET.Element | None, path: str) -> float | None:
    raw = _text(node, path)
    if raw is None:
        return None
    try:
        return float(re.sub(r"[,$\s]", "", raw))
    except ValueError:
        return None


def _flag(node: ET.Element | None, path: str) -> bool:
    return (_text(node, path) or "0").strip() in {"1", "true", "True"}


def parse_form4(
    xml: str,
    *,
    ticker: str,
    filed: date | None,
    accession: str,
) -> list[InsiderTransaction]:
    """
    Parse one Form 4 into its transactions.

    Both tables are read. Derivative transactions (options, warrants) are kept
    because they are part of the record, but their codes are almost all
    NO_SIGNAL anyway — which is the correct reading: an option grant is not
    someone buying stock.
    """
    root = ET.fromstring(xml)

    owner = root.find("reportingOwner")
    relationship = owner.find("reportingOwnerRelationship") if owner is not None else None
    insider = _text(owner, "reportingOwnerId/rptOwnerName") or "neznámý"
    officer_title = _text(relationship, "officerTitle") if relationship is not None else None

    out: list[InsiderTransaction] = []
    for table, tag in (
        ("nonDerivativeTable", "nonDerivativeTransaction"),
        ("derivativeTable", "derivativeTransaction"),
    ):
        container = root.find(table)
        if container is None:
            continue
        for tx in container.findall(tag):
            code = classify(_text(tx, "transactionCoding/transactionCode"))
            acquired = (
                _text(tx, "transactionAmounts/transactionAcquiredDisposedCode") or "A"
            ).upper().startswith("A")

            price = _number(tx, "transactionAmounts/transactionPricePerShare")
            # A reported price of exactly 0 on a grant or gift is not a price;
            # it is the absence of one. Keeping it as 0.0 would let a later
            # average treat a donated share as a share bought for nothing.
            if price == 0 and code.signal is Signal.NO_SIGNAL:
                price = None

            out.append(InsiderTransaction(
                ticker=ticker.upper(),
                insider=insider,
                is_director=_flag(relationship, "isDirector"),
                is_officer=_flag(relationship, "isOfficer"),
                officer_title=officer_title or None,
                is_ten_percent_owner=_flag(relationship, "isTenPercentOwner"),
                transaction_date=SecEdgarClient._parse_date(
                    _text(tx, "transactionDate")
                ),
                code=code,
                shares=_number(tx, "transactionAmounts/transactionShares"),
                price_per_share=price,
                acquired=acquired,
                shares_owned_after=_number(
                    tx, "postTransactionAmounts/sharesOwnedFollowingTransaction"
                ),
                filed=filed,
                accession=accession,
            ))
    return out


# ==============================================================================
# Summary
# ==============================================================================

def summarize_insider_activity(coverage: TickerCoverage) -> str:
    """
    One Czech sentence about what insiders actually did.

    Deliberately refuses to net gifts, grants and tax withholding into a
    "net insider buying/selling" number — that number is the whole trap. Real
    trades are counted; everything else is reported as what it is.
    """
    if coverage.status is CoverageStatus.NOT_A_TICKER:
        return f"{coverage.ticker}: {coverage.note}"
    if coverage.status is CoverageStatus.NOT_AN_SEC_FILER:
        return f"{coverage.ticker}: nepodává u SEC — insider data nejsou k dispozici."
    if coverage.status is CoverageStatus.LOOKUP_FAILED:
        return f"{coverage.ticker}: SEC se nepodařilo přečíst — {coverage.note}"

    txs = coverage.insider_transactions
    if not txs:
        return f"{coverage.ticker}: žádné Form 4 v posledních podáních."

    buys = [t for t in txs if t.code.signal is Signal.BUY]
    sells = [t for t in txs if t.code.signal is Signal.SELL]
    other = [t for t in txs if t.code.signal is Signal.NO_SIGNAL]

    parts: list[str] = []
    if buys:
        shares = sum(t.shares or 0 for t in buys)
        people = len({t.insider for t in buys})
        parts.append(f"{people}× insider koupil na trhu ({shares:,.0f} ks)")
    if sells:
        shares = sum(t.shares or 0 for t in sells)
        people = len({t.insider for t in sells})
        parts.append(f"{people}× insider prodal na trhu ({shares:,.0f} ks)")

    if not parts:
        # The common case, and the one a naive reading gets wrong.
        kinds = ", ".join(sorted({t.code.label_cs for t in other}))
        return (
            f"{coverage.ticker}: žádný nákup ani prodej na trhu. "
            f"{len(other)} transakcí bez signálu ({kinds}) — administrativa, "
            f"ne rozhodnutí o penězích."
        )

    tail = f"; {len(other)} dalších transakcí bez signálu" if other else ""
    return f"{coverage.ticker}: " + ", ".join(parts) + tail + "."
