"""
The other paste shape, and the misattribution it invites.

WhatsApp's "export chat" writes each header on the same line as its text:

    [1:24, 24. 8. 2026] +1 (203) 942-7647: DFSC CEO and CFO meeting...

The screen-copy parser cannot read these at all, because after phone numbers
are stripped what is left is `[1:24, 24. 8. 2026] : text` with no author. That
is correct behaviour and not a gap to route around — in this shape the author
IS the phone number, and phone numbers do not survive contact with storage.

So each distinct author becomes a slot letter and a person names the slots.
The first real paste — Robert Mock's notes from a DFSC management meeting on
2026-08-24 — arrived with six replies from three other members, one of them a
question that a blanket attribution would have recorded as the analyst's own
words. `source_key` decides how large a position may get, so that misattribution
is a position size built on somebody else's question.
"""

from datetime import date, time

from app.services.whatsapp_intake import (
    export_format_slots,
    parse_export_format,
)

# The real thread, trimmed. Numbers are invented; the shape is not.
THREAD = """[1:24, 24. 8. 2026] +1 (203) 942-7647: DFSC CEO and CFO meeting, day after earnings.
Bliss Laser Targeting sensor detection system:
1. Bliss did well in testing. There is no pass or fail.
2. We could see low-rate testing orders Q4 2026 and volume production in 2027.
[2:31, 24. 8. 2026] +1 (972) 965-3901: Would it be fair to say q 3/4 is quiet?
[2:49, 24. 8. 2026] +1 (615) 509-0101: This is great @~Robert Mock !!
[3:16, 24. 8. 2026] +1 (757) 592-7729: So this was right before the raise, correct?
[3:57, 24. 8. 2026] +1 (203) 942-7647: Correct
"""


# ==============================================================================
# Nothing carries a phone number out of here
# ==============================================================================

def test_no_phone_number_survives_the_parse():
    messages = parse_export_format(THREAD, attribute={"A": "Robert Mock"})
    body = " ".join(m.text for m in messages)
    assert "+1" not in body
    assert "942-7647" not in body


def test_the_slot_listing_carries_no_identifier_either():
    """
    What comes back is a letter, a count and a few words — enough for a human
    to recognise who is who, and nothing that identifies them to anybody else.
    """
    for slot, _count, opening in export_format_slots(THREAD):
        assert len(slot) == 1
        assert "+1" not in opening
        assert "942" not in opening


# ==============================================================================
# One slot per author, in order of first appearance
# ==============================================================================

def test_each_distinct_author_gets_one_slot():
    slots = export_format_slots(THREAD)
    assert [s for s, _, _ in slots] == ["A", "B", "C", "D"]


def test_an_author_who_writes_twice_keeps_one_slot():
    """The analyst opens the thread and answers a question in it."""
    [(_slot, count, _opening)] = [s for s in export_format_slots(THREAD) if s[0] == "A"]
    assert count == 2


def test_the_opening_words_are_what_identifies_the_slot():
    slots = dict((s, opening) for s, _, opening in export_format_slots(THREAD))
    assert slots["A"].startswith("DFSC CEO and CFO meeting")
    assert slots["C"].startswith("This is great")


# ==============================================================================
# The misattribution this exists to prevent
# ==============================================================================

def test_only_the_named_slot_is_attributed():
    messages = parse_export_format(THREAD, attribute={"A": "Robert Mock"})
    named = [m for m in messages if m.speaker]
    assert len(named) == 2
    assert {m.speaker for m in named} == {"Robert Mock"}


def test_somebody_elses_question_is_never_put_in_the_analysts_mouth():
    """
    The exact failure a blanket attribution produced on the first real paste.
    Two other members asked questions; one of them would have been stored as
    the analyst's own view, and a view drives position size.
    """
    messages = parse_export_format(THREAD, attribute={"A": "Robert Mock"})
    mock = " ".join(m.text for m in messages if m.speaker == "Robert Mock")
    assert "Would it be fair to say" not in mock
    assert "This is great" not in mock


def test_a_compliment_naming_somebody_does_not_attribute_anything():
    """
    "This is great @~Robert Mock !!" names somebody who might be the author of
    the message above, or of any message, or of none. It is suggestive and it
    is not evidence.
    """
    messages = parse_export_format(THREAD, attribute={})
    assert all(m.speaker == "" for m in messages)


def test_an_unnamed_paste_still_parses_and_still_strips():
    """Reading a thread without recording anybody's opinion is a valid use."""
    messages = parse_export_format(THREAD)
    assert len(messages) == 5
    assert all(m.speaker == "" for m in messages)
    assert "+1" not in " ".join(m.text for m in messages)


def test_the_slot_letter_is_read_case_insensitively():
    messages = parse_export_format(THREAD, attribute={"a": "Robert Mock"})
    assert any(m.speaker == "Robert Mock" for m in messages)


# ==============================================================================
# The shape of a multi-line note
# ==============================================================================

def test_a_numbered_list_stays_one_message():
    """
    A note broken across lines and blank lines is one analyst's note, not four
    fragments — splitting it would strip every point of its context.
    """
    messages = parse_export_format(THREAD, attribute={"A": "Robert Mock"})
    opening = messages[0]
    assert "Bliss did well in testing" in opening.text
    assert "volume production in 2027" in opening.text


def test_the_timestamp_survives():
    messages = parse_export_format(THREAD, attribute={"A": "Robert Mock"})
    assert messages[0].sent_on == date(2026, 8, 24)
    assert messages[0].sent_at == time(1, 24)


def test_an_empty_paste_is_no_messages_not_a_crash():
    assert parse_export_format("") == []
    assert export_format_slots("") == []


def test_text_that_is_not_this_format_yields_nothing():
    """A screen copy goes to the other parser; this one must not half-read it."""
    assert parse_export_format("Robert Mock\n+1 (203) 942-7647\nHello\n16:51") == []
