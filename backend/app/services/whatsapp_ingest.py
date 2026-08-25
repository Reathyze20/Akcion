"""
Turning a pasted WhatsApp export into attributed claims.

Two halves that already existed and were never joined
-----------------------------------------------------
`whatsapp_intake.parse_export` turns a raw export into messages with a speaker,
a date and a body, strips every phone number before anything else touches it,
and has never had a caller. `claim_extraction.extract_claims` reads a document
and returns claims whose quotes are verified verbatim against the source. This
module is the wire between them, and it is what makes Breakout Investors a real
second source rather than a scraped list.

Why it matters more since 2026-08-23
------------------------------------
The two sources now sit at the same level: either may refuse a purchase. A
refusal from Breakout can only exist if somebody there has actually written
something, and until now nothing carried their writing into the app at all.

Who is quoted, and who is merely present
----------------------------------------
The roster decides. Around a hundred and thirty people are in that group, and
attributing all of them to the research desk would let any one of them change
a position cap. Everyone's messages are kept with their names — the record is
the record — but only a listed analyst's text is sent for extraction, which is
also the only reason this does not cost a fortune in tokens.

What it does not do
-------------------
It does not write `Stock` rows and therefore does not by itself create a
stance. Claims land in `ticker_mentions` with their speaker and source; turning
a set of claims into a verdict is a separate, deliberate act. A paste is
evidence, not a decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from loguru import logger
from sqlalchemy.orm import Session

from app.core.sources import InvestmentSource, normalize_source
from app.services.analyst_roster import load as load_roster
from app.services.claim_extraction import SourceType
from app.services.whatsapp_intake import ParsedMessage, parse_export

#: Below this a message is a reaction, an emoji or "same here" — nothing a
#: model can extract a checkable claim from, and every one of them costs money
#: to send.
MIN_MESSAGE_CHARS = 40


@dataclass
class IngestReport:
    """What one paste contained, and what was done with each part of it."""

    messages: int = 0
    speakers: dict[str, int] = field(default_factory=dict)
    #: Speakers whose text was sent for extraction, because they are listed.
    quoted: dict[str, int] = field(default_factory=dict)
    #: Present in the paste, not on the roster. Named so the owner can decide
    #: whether any of them belong there.
    unlisted: dict[str, int] = field(default_factory=dict)
    skipped_short: int = 0
    dates: tuple[date | None, date | None] = (None, None)

    def summary_cs(self) -> str:
        if not self.messages:
            return "V textu jsem nenašel žádné zprávy — je to opravdu export z WhatsAppu?"

        span = ""
        first, last = self.dates
        if first and last:
            span = f", {first:%d.%m.%Y} až {last:%d.%m.%Y}"

        parts = [f"{self.messages} zpráv od {len(self.speakers)} lidí{span}"]
        if self.quoted:
            parts.append(
                "k rozboru jde "
                + ", ".join(f"{n} od {who}" for who, n in sorted(self.quoted.items()))
            )
        else:
            parts.append("nikdo ze seznamu analytiků tu nepíše, takže rozbor nespouštím")
        if self.unlisted:
            parts.append(f"{len(self.unlisted)} lidí mimo seznam (uloženo, nepočítá se)")
        return " · ".join(parts)


def analyse_paste(
    db: Session,
    raw: str,
    *,
    pasted_on: date,
) -> tuple[IngestReport, list[ParsedMessage]]:
    """
    Parse an export and say who is in it, without calling any model.

    Deliberately separate from extraction so the owner can look at a paste
    before spending anything on it — and so the answer to "who writes in this
    group" is available without an API key at all.

    Phone numbers are gone before this returns: `strip_phone_numbers` runs
    unconditionally inside the parser, ahead of everything else.
    """
    messages = parse_export(raw, pasted_on=pasted_on)
    roster = load_roster(db)

    report = IngestReport(messages=len(messages))
    quotable: list[ParsedMessage] = []

    dated = [m.sent_on for m in messages if m.sent_on]
    if dated:
        report.dates = (min(dated), max(dated))

    for message in messages:
        speaker = (message.speaker or "").strip() or "(bez jména)"
        report.speakers[speaker] = report.speakers.get(speaker, 0) + 1

        source = normalize_source(speaker, roster)
        if source == InvestmentSource.OTHER.value:
            report.unlisted[speaker] = report.unlisted.get(speaker, 0) + 1
            continue

        if len(message.text.strip()) < MIN_MESSAGE_CHARS:
            report.skipped_short += 1
            continue

        report.quoted[speaker] = report.quoted.get(speaker, 0) + 1
        quotable.append(message)

    return report, quotable


def documents_for_extraction(
    messages: Iterable[ParsedMessage],
    roster: dict[str, str],
) -> dict[str, str]:
    """
    Group a listed speaker's messages into one document per source.

    One document rather than one call per message: a claim often spans a reply
    and its answer, and a model given the thread can quote across it. Each line
    keeps its date and speaker so the verbatim guard still has something to
    match and so a claim can be traced back to who said it and when.
    """
    grouped: dict[str, list[str]] = {}
    for message in messages:
        source = normalize_source(message.speaker, roster)
        if source == InvestmentSource.OTHER.value:
            continue
        when = f"{message.sent_on:%d.%m.%Y}" if message.sent_on else "bez data"
        grouped.setdefault(source, []).append(
            f"[{when}] {message.speaker}: {message.text.strip()}"
        )
    return {source: "\n\n".join(lines) for source, lines in grouped.items()}


def extract_for_sources(
    documents: dict[str, str],
    *,
    today_iso: str,
    api_key: str,
    model: str | None = None,
) -> dict[str, object]:
    """
    Run each source's document through extraction, keeping failures apart.

    One source failing must not lose the other: a refusal or a transport error
    on the Breakout document leaves anything Gomes said in the same paste
    perfectly usable. The exception is returned rather than raised for exactly
    that reason.
    """
    results: dict[str, object] = {}
    for source, text in documents.items():
        try:
            results[source] = extract_claims_for(
                text, today_iso=today_iso, api_key=api_key, model=model
            )
        except Exception as exc:  # noqa: BLE001 — see docstring
            logger.exception("Rozbor pro zdroj {} selhal", source)
            results[source] = exc
    return results


def extract_claims_for(
    text: str, *, today_iso: str, api_key: str, model: str | None = None
):
    """One document through the extractor. Split out so tests can replace it."""
    from app.services.claim_extraction import extract_claims

    return extract_claims(
        text,
        source_type=SourceType.WHATSAPP_GROUP,
        today_iso=today_iso,
        api_key=api_key,
        model=model,
    )
