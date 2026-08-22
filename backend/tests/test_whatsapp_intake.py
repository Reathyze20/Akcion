"""
WhatsApp export parsing.

The fixture below mirrors the structure of a real export from the owner's
group — reply blocks, the copy-paste triplication, date separators, reaction
lines, link previews — with every name and number replaced. The real export
carries the phone numbers of ~130 people and is never committed.
"""

from datetime import date, time

import pytest

from app.services.whatsapp_intake import (
    ParsedMessage,
    collapse_duplicated_text,
    parse_export,
    resolve_date_header,
    strip_phone_numbers,
)


# Structure copied from a real export; identities invented.
SAMPLE = """\
Chaty
13. 8. 2026
Anna Novak
+1 (555) 010-1111
Bottom line, there are plenty of details that we need to collect on this.

None of us seems to have proven clairvoyance on it.
16:51
Petr Dvorak
+1 (555) 010-2222
Every other day I could post another bullish news item for DRX.
17:09

❤️
2
Jan Svoboda
+1 (555) 010-3333
Anna Novak
+1 (555) 010-1111
Bottom line, there are plenty of details that we need to collect on this.

None of us seems to have proven clairvoyance on it.
Agreed, but the 10Q overreaction looks clear to me.
Upraveno17:23
Včera
Petr Dvorak
+1 (555) 010-2222
Added some more DBOX. Not a lot because I have a lot already, but way too cheap right here.Added some more DBOX. Not a lot because I have a lot already, but way too cheap right here.
Added some more DBOX. Not a lot because I have a lot already, but way too cheap right here.
19:20
Anna Novak
+1 (555) 010-1111
TOYO fell 24% after results. Revenue rose 88% to $261M.
https://x.com/example/status/123
2:01
"""

PASTED_ON = date(2026, 8, 22)  # a Saturday


@pytest.fixture
def parsed() -> list[ParsedMessage]:
    return parse_export(SAMPLE, pasted_on=PASTED_ON)


# ==============================================================================
# Privacy — the rule that must never regress
# ==============================================================================

def test_no_phone_number_survives_parsing(parsed):
    """~130 real people's numbers are in every export. None may get through."""
    blob = " ".join(
        f"{m.speaker} {m.text} {m.quoted_speaker or ''} {m.quoted_text or ''}"
        for m in parsed
    )
    assert "555" not in blob
    assert "+1" not in blob


def test_strip_phone_numbers_handles_international_formats():
    raw = "+1 (617) 901-3725 / +420 739 171 820 / +44 7826 260370 / +54 9 11 5429-3820"
    out = strip_phone_numbers(raw)
    assert not any(ch.isdigit() for ch in out)


def test_speaker_names_are_kept():
    """Attribution is load-bearing — Gomes and a member are not equal evidence."""
    msgs = parse_export(SAMPLE, pasted_on=PASTED_ON)
    assert {m.speaker for m in msgs} == {"Anna Novak", "Petr Dvorak", "Jan Svoboda"}


# ==============================================================================
# Attribution
# ==============================================================================

def test_each_message_is_attributed_to_its_author(parsed):
    first = parsed[0]
    assert first.speaker == "Anna Novak"
    assert "plenty of details" in first.text


def test_reply_does_not_steal_the_quoted_persons_words(parsed):
    """
    WhatsApp puts the quoted message ABOVE the reply. Without splitting them,
    Anna's sentence would be recorded as Jan's claim.
    """
    reply = next(m for m in parsed if m.speaker == "Jan Svoboda")
    assert reply.is_reply
    assert reply.quoted_speaker == "Anna Novak"
    assert "plenty of details" in (reply.quoted_text or "")
    # The reply itself is only Jan's own sentence.
    assert reply.text == "Agreed, but the 10Q overreaction looks clear to me."
    assert "clairvoyance" not in reply.text


def test_edited_marker_is_captured(parsed):
    reply = next(m for m in parsed if m.speaker == "Jan Svoboda")
    assert reply.edited is True
    assert reply.sent_at == time(17, 23)


# ==============================================================================
# The triplication artifact
# ==============================================================================

def test_copy_paste_triplication_counts_as_one_claim(parsed):
    """
    A long message arrives self-concatenated AND repeated on the next line.
    Counted naively that is three independent data points for one opinion.
    """
    msg = next(m for m in parsed if "Added some more DBOX" in m.text)
    assert msg.text.count("Added some more DBOX") == 1


def test_collapse_duplicated_text_undoubles_a_long_line():
    one = "Moving from IDN to a stock that is performing, the young crowd likes it."
    assert collapse_duplicated_text(one + one) == one


def test_collapse_duplicated_text_leaves_short_repeats_alone():
    """"haha" is not a copy artifact — only long exact doublings are."""
    assert collapse_duplicated_text("hahaha") == "hahaha"


# ==============================================================================
# Dates
# ==============================================================================

def test_numeric_date_separator():
    assert resolve_date_header("13. 8. 2026", PASTED_ON) == date(2026, 8, 13)


def test_yesterday_resolves_against_the_paste_date():
    assert resolve_date_header("Včera", PASTED_ON) == date(2026, 8, 21)


def test_weekday_resolves_to_the_most_recent_one():
    # PASTED_ON is Saturday 2026-08-22; the previous Thursday is the 20th.
    assert resolve_date_header("čtvrtek", PASTED_ON) == date(2026, 8, 20)


def test_weekday_never_resolves_to_the_paste_date_itself():
    """WhatsApp says 'Dnes' for today, so a weekday label means a week back."""
    assert resolve_date_header("sobota", PASTED_ON) == date(2026, 8, 15)


def test_invalid_date_is_rejected_not_guessed():
    assert resolve_date_header("31. 2. 2026", PASTED_ON) is None
    assert resolve_date_header("random text", PASTED_ON) is None


def test_messages_inherit_the_separator_above_them(parsed):
    early = next(m for m in parsed if "plenty of details" in m.text)
    later = next(m for m in parsed if "Added some more DBOX" in m.text)
    assert early.sent_on == date(2026, 8, 13)
    assert later.sent_on == date(2026, 8, 21)  # after the "Včera" separator


# ==============================================================================
# Noise
# ==============================================================================

def test_reaction_lines_are_not_messages(parsed):
    assert all("❤️" not in m.text for m in parsed)
    assert all(m.text.strip() != "2" for m in parsed)


def test_links_are_extracted(parsed):
    toyo = next(m for m in parsed if "TOYO" in m.text)
    assert toyo.links == ["https://x.com/example/status/123"]


def test_empty_input_yields_no_messages():
    assert parse_export("", pasted_on=PASTED_ON) == []
    assert parse_export("Chaty\n\n\n", pasted_on=PASTED_ON) == []
