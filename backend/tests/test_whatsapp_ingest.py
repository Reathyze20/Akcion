"""
Getting a written opinion out of a group chat, and only from the right people.

`whatsapp_intake.parse_export` existed and had no caller; `claim_extraction`
existed and had nothing to read. This is the wire between them, and since
2026-08-23 it matters more than it did: the two sources sit at the same level,
either may refuse a purchase, and a refusal from Breakout can only exist if
somebody there has actually written something.

What is tested is the filter. A hundred and thirty people are in that group, and
attributing all of them to the research desk would let any one of them change a
position cap.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.models.trading  # noqa: F401
from app.models.analyst_roster import RosterEntry
from app.models.base import Base
from app.services.analyst_roster import add
from app.services.whatsapp_ingest import (
    MIN_MESSAGE_CHARS,
    analyse_paste,
    documents_for_extraction,
    extract_for_sources,
)

PASTED_ON = date(2026, 8, 23)

EXPORT = """\
22. 8. 2026

Mark Gomes
+1 (617) 901-3725
Crexendo just reported another quarter of record subscription revenue and the
backlog is up again, this is exactly the inflection I described in June.
16:51

Brad Steveson
+420 739 171 820
I went through the TPCS filing this morning. Gross margin is up 4 points year
over year and the order book covers the next three quarters.
17:02

Honza Nováček
+420 605 111 222
same here
17:05

Petr Malý
+420 606 222 333
nice
17:06
"""


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[RosterEntry.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


# ==============================================================================
# Privacy, before anything else
# ==============================================================================

def test_no_phone_number_survives_the_parse(db):
    """
    Around a hundred and thirty real people's numbers are in an export. They
    are stripped unconditionally, ahead of storage, logging and any model.
    """
    report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)

    everything = " ".join(m.text for m in quotable) + " ".join(report.speakers)
    assert "617" not in everything
    assert "739 171 820" not in everything
    assert "+" not in everything


# ==============================================================================
# Who is quoted, and who is merely present
# ==============================================================================

def test_everyone_is_counted_even_when_nobody_is_listed(db):
    """
    The record is the record. What changes with the roster is who is quoted,
    not who is seen.
    """
    report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)

    assert report.messages == 4
    assert "Brad Steveson" in report.speakers
    assert "Honza Nováček" in report.speakers


def test_gomes_is_quoted_without_anyone_adding_him(db):
    """His name is the one case the keyword fallback still covers on its own."""
    _report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)
    assert any(m.speaker == "Mark Gomes" for m in quotable)


def test_an_unlisted_analyst_is_named_but_not_quoted(db):
    """
    The whole point. Brad wrote a real piece of research and it is not sent
    anywhere until somebody says he counts — and the app says his name so that
    decision can be made.
    """
    report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)

    assert "Brad Steveson" in report.unlisted
    assert not any(m.speaker == "Brad Steveson" for m in quotable)
    assert "mimo seznam" in report.summary_cs()


def test_listing_him_makes_the_same_paste_quote_him(db):
    add(db, "Brad Steveson", "BREAKOUT_INVESTORS", note="píše jejich analýzy")
    db.flush()

    report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)

    assert "Brad Steveson" in report.quoted
    assert any(m.speaker == "Brad Steveson" for m in quotable)


def test_chatter_is_not_sent_to_a_model(db):
    """
    "same here" and "nice" carry no checkable claim and every one of them
    costs money to send.
    """
    add(db, "Honza Nováček", "BREAKOUT_INVESTORS")
    add(db, "Petr Malý", "BREAKOUT_INVESTORS")
    db.flush()

    report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)

    # Both are listed, so nothing but length keeps them out.
    assert report.skipped_short == 2
    assert not any(m.speaker in ("Honza Nováček", "Petr Malý") for m in quotable)
    assert all(len(m.text.strip()) >= MIN_MESSAGE_CHARS for m in quotable)


def test_the_span_of_the_paste_is_reported(db):
    report, _ = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)
    first, last = report.dates
    assert first == date(2026, 8, 22)
    assert last == date(2026, 8, 22)


def test_an_export_of_nothing_says_so(db):
    report, quotable = analyse_paste(db, "   ", pasted_on=PASTED_ON)
    assert report.messages == 0
    assert quotable == []
    assert "nenašel" in report.summary_cs()


# ==============================================================================
# One document per source
# ==============================================================================

def test_each_source_gets_its_own_document(db):
    """
    Both sources can appear in one paste, and that is what makes cross-source
    agreement computable from a single document — but they must not be mixed
    into one text, or a claim would be attributed to whoever came first.
    """
    add(db, "Brad Steveson", "BREAKOUT_INVESTORS")
    db.flush()

    _report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)
    docs = documents_for_extraction(
        quotable, {"brad steveson": "BREAKOUT_INVESTORS"}
    )

    assert set(docs) == {"GOMES", "BREAKOUT_INVESTORS"}
    assert "Crexendo" in docs["GOMES"]
    assert "TPCS" in docs["BREAKOUT_INVESTORS"]


def test_a_document_keeps_the_date_and_the_speaker(db):
    """
    The verbatim guard needs something to match, and a claim has to be
    traceable to who said it and when.
    """
    _report, quotable = analyse_paste(db, EXPORT, pasted_on=PASTED_ON)
    docs = documents_for_extraction(quotable, {})

    assert "22.08.2026" in docs["GOMES"]
    assert "Mark Gomes:" in docs["GOMES"]


# ==============================================================================
# One source failing does not lose the other
# ==============================================================================

def test_a_failure_on_one_source_leaves_the_other_usable(monkeypatch):
    """
    A refusal or a transport error on the Breakout document must not throw away
    what Gomes said in the same paste.
    """
    def flaky(text, **_kw):
        if "TPCS" in text:
            raise RuntimeError("model refused")
        return {"claims": ["ok"]}

    monkeypatch.setattr(
        "app.services.whatsapp_ingest.extract_claims_for", flaky
    )

    out = extract_for_sources(
        {"GOMES": "Crexendo backlog up", "BREAKOUT_INVESTORS": "TPCS margin up"},
        today_iso="2026-08-23", api_key="x",
    )

    assert out["GOMES"] == {"claims": ["ok"]}
    assert isinstance(out["BREAKOUT_INVESTORS"], RuntimeError)
