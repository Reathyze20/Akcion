"""
WhatsApp export → clean, attributed messages.

This is the deterministic half of the paste intake. It does no AI work: it
takes the raw text the owner copied out of WhatsApp and turns it into a list
of messages with a speaker, a date and a body. Meaning extraction (which
ticker, fact vs opinion, does this move the thesis) happens afterwards, on
this cleaned output.

The split is deliberate. Structure — who said what, when, what is a quote of
an earlier message — is regex work: free, instant, and testable against a real
export. Only judgement needs a model. Feeding raw export text straight to an
LLM would pay tokens for participant lists and reaction emoji, and would make
speaker attribution a probabilistic guess rather than a parse.

PRIVACY: a WhatsApp export carries the phone number of every participant —
around 130 real people in the owner's group. `strip_phone_numbers` runs first
and unconditionally, so numbers never reach the database, the model, or a log
line. Display names are kept, because attribution is load-bearing: a claim
from Mark Gomes and a claim from another member are not the same evidence
(see docs/GOMES_METHODOLOGY_CANON.md §8 and app/core/sources.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta

# A phone number as WhatsApp renders it: +1 (617) 901-3725, +420 739 171 820,
# +44 7826 260370, +54 9 11 5429-3820.
_PHONE = re.compile(r"\+\d[\d\s\(\)\-]{6,}\d")
# A line that is ONLY a phone number — this is what marks the line above it
# as a speaker name.
_PHONE_LINE = re.compile(r"^\s*\+\d[\d\s\(\)\-]{6,}\d\s*$")
# 16:51, or Upraveno17:23 / Upraveno 19:05 when the message was edited.
_TIMESTAMP_LINE = re.compile(r"^\s*(?P<edited>Upraveno)?\s*(?P<h>\d{1,2}):(?P<m>\d{2})\s*$")
_DATE_NUMERIC = re.compile(r"^\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*$")
_URL = re.compile(r"https?://\S+")

# The OTHER paste shape. WhatsApp's "export chat" writes one header per
# message on the same line as the text:
#
#     [1:24, 24. 8. 2026] +1 (203) 942-7647: DFSC CEO and CFO meeting...
#
# The screen-copy parser below cannot see these, because after phone numbers
# are stripped what remains is `[1:24, 24. 8. 2026] : text` with no speaker at
# all. That is the correct outcome and not a bug to route around: in this shape
# the author IS the phone number, and the phone number must not survive
# contact with storage. Attribution therefore has to come from the person
# pasting — `parse_export_format(..., attributed_to=...)` — the same way a
# cylinder count needs a human to agree to it.
_EXPORT_HEADER = re.compile(
    r"^\s*\[\s*(?P<h>\d{1,2}):(?P<m>\d{2})\s*,\s*"
    r"(?P<d>\d{1,2})\.\s*(?P<mo>\d{1,2})\.\s*(?P<y>\d{4})\s*\]\s*"
    r"(?P<speaker>[^:]*?)\s*:\s*(?P<text>.*)$"
)

_WEEKDAYS_CS = {
    "pondělí": 0, "úterý": 1, "středa": 2, "čtvrtek": 3,
    "pátek": 4, "sobota": 5, "neděle": 6,
}
_TODAY_CS = {"dnes"}
_YESTERDAY_CS = {"včera"}

# Standalone UI noise WhatsApp exports leave behind.
_NOISE_LINES = {"chaty", "vy", "upraveno"}


@dataclass(frozen=True)
class ParsedMessage:
    """One message, attributed and dated."""

    speaker: str
    text: str
    sent_on: date | None
    sent_at: time | None = None
    edited: bool = False
    # When the message was a reply, who/what it replied to. The quoted body is
    # kept as context but must never be attributed to `speaker`.
    quoted_speaker: str | None = None
    quoted_text: str | None = None
    links: list[str] = field(default_factory=list)

    @property
    def is_reply(self) -> bool:
        return self.quoted_speaker is not None


def strip_phone_numbers(raw: str) -> str:
    """
    Remove every phone number. Runs before anything else touches the text.

    Also drops the participant-list blob at the top of an export — a single
    line of a hundred-plus comma-separated numbers — which is left as an empty
    line once the numbers are gone.
    """
    return _PHONE.sub("", raw)


def collapse_duplicated_text(text: str) -> str:
    """
    Undo the duplication a copied WhatsApp export introduces.

    Long messages come out of the clipboard both self-concatenated with no
    separator ("...likes DBOX.Moving from IDN...likes DBOX.") and repeated on
    the following line. Left alone, one claim would be counted three times and
    look like three independent data points.
    """
    # 1) exact self-doubling inside one line
    def _undouble(line: str) -> str:
        s = line.strip()
        n = len(s)
        if n >= 40 and n % 2 == 0 and s[: n // 2] == s[n // 2:]:
            return s[: n // 2]
        return s

    lines = [_undouble(ln) for ln in text.splitlines()]

    # 2) a line that repeats the previous one
    out: list[str] = []
    for ln in lines:
        if out and ln and ln == out[-1]:
            continue
        out.append(ln)
    return "\n".join(out).strip()


def resolve_date_header(header: str, pasted_on: date) -> date | None:
    """
    Turn a WhatsApp date separator into a real date.

    Handles "13. 8. 2026", "Včera", "Dnes" and bare Czech weekday names.
    A weekday means the most recent such day at or before `pasted_on`, which
    is how WhatsApp uses them (they only appear within the last week).
    """
    h = header.strip().lower()

    m = _DATE_NUMERIC.match(header)
    if m:
        day, month, year = (int(g) for g in m.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    if h in _TODAY_CS:
        return pasted_on
    if h in _YESTERDAY_CS:
        return pasted_on - timedelta(days=1)

    if h in _WEEKDAYS_CS:
        target = _WEEKDAYS_CS[h]
        delta = (pasted_on.weekday() - target) % 7
        # A weekday label never means "today" — that would say Dnes.
        return pasted_on - timedelta(days=delta or 7)

    return None


def _is_reaction_line(line: str) -> bool:
    """A standalone emoji reaction, optionally followed by its count."""
    s = line.strip()
    if not s or len(s) > 8:
        return False
    if s.isdigit():
        return True
    # No letters and no digits -> emoji only.
    return not any(ch.isalnum() for ch in s)


def parse_export_format(
    raw: str,
    *,
    attribute: dict[str, str] | None = None,
) -> list[ParsedMessage]:
    """
    Parse WhatsApp's "export chat" shape, where each header shares a line with
    its text: `[1:24, 24. 8. 2026] +1 (203) 942-7647: the message`.

    Authors become slots, and a human names the slots
    -------------------------------------------------
    In this shape the speaker field IS the phone number, and phone numbers do
    not survive contact with storage. But they still distinguish one person
    from another, so each distinct author is assigned a slot letter in order of
    first appearance — A, B, C — and the number itself is dropped inside this
    function without ever being returned or written anywhere.

    `attribute` maps a slot to a real name: `{"A": "Robert Mock"}`. Messages in
    an unnamed slot come back with `speaker=""` and are carried no further.

    Why not just attribute the whole paste to one person
    ----------------------------------------------------
    Because a paste is usually a thread, not a block. The note that prompted
    this arrived with six replies from four other members, including a question
    ("So this was conducted right before the latest raise, correct?") that a
    blanket attribution would have recorded as the analyst's own words. Since
    `source_key` decides how large a position may get, putting somebody else's
    question in a named analyst's mouth is a position size built on a
    misattribution.

    Guessing the name from the text was available and was rejected. A later
    message said "This is great @~Robert Mock !!", which names somebody who
    might be the author of the message above, or of any message, or of none.
    """
    attribute = {k.strip().upper(): v for k, v in (attribute or {}).items()}

    #: Raw speaker -> slot letter. Lives only for this call; the keys are phone
    #: numbers and are never returned, logged or stored.
    slots: dict[str, str] = {}

    def slot_for(rawspeaker: str) -> str:
        key = rawspeaker.strip()
        if key not in slots:
            slots[key] = chr(ord("A") + len(slots)) if len(slots) < 26 else "?"
        return slots[key]

    messages: list[ParsedMessage] = []
    pending: dict | None = None
    body: list[str] = []

    def close() -> None:
        nonlocal pending
        if pending is None:
            return
        joined = '\n'.join([pending["text"], *body])
        full = strip_phone_numbers(joined).strip()
        if full:
            messages.append(
                ParsedMessage(
                    speaker=attribute.get(pending["slot"], ""),
                    text=collapse_duplicated_text(full),
                    sent_on=pending["sent_on"],
                    sent_at=pending["sent_at"],
                    links=_URL.findall(full),
                )
            )
        pending = None
        body.clear()

    for line in raw.splitlines():
        header = _EXPORT_HEADER.match(line)
        if header is None:
            # A continuation line. Blank lines are kept: a numbered list broken
            # by one is a single note, not two.
            if pending is not None:
                body.append(line)
            continue

        close()
        pending = {
            "slot": slot_for(header.group("speaker")),
            "text": header.group("text"),
            "sent_on": date(
                int(header.group("y")), int(header.group("mo")), int(header.group("d"))
            ),
            "sent_at": time(int(header.group("h")), int(header.group("m"))),
        }

    close()
    return messages


def export_format_slots(raw: str) -> list[tuple[str, int, str]]:
    """
    Who is in this paste, as slots, so a person can say which one to trust.

    Returns `(slot, message_count, first_words)` per distinct author, ordered
    by first appearance. The phone numbers that distinguish them are used to
    group and then dropped — what comes back carries no identifier at all,
    only enough of the opening text for a human to recognise who is who.
    """
    seen: dict[str, list] = {}
    order: list[str] = []
    pending_key: str | None = None

    for line in raw.splitlines():
        header = _EXPORT_HEADER.match(line)
        if header is None:
            continue
        key = header.group("speaker").strip()
        if key not in seen:
            seen[key] = [0, strip_phone_numbers(header.group("text")).strip()[:60]]
            order.append(key)
        seen[key][0] += 1
        pending_key = key

    del pending_key
    return [
        (chr(ord("A") + i), seen[k][0], seen[k][1]) for i, k in enumerate(order)
    ]


def parse_export(raw: str, *, pasted_on: date) -> list[ParsedMessage]:
    """
    Parse a copied WhatsApp conversation into attributed messages.

    Args:
        raw: text as pasted, phone numbers still present.
        pasted_on: the date the owner pasted it. Anchors relative separators
            ("Včera", weekday names) — without it they cannot be resolved.

    Returns:
        Messages in the order they appear. Anything that could not be
        attributed to a speaker is dropped rather than guessed at.
    """
    text = strip_phone_numbers(raw)
    lines = text.splitlines()

    messages: list[ParsedMessage] = []
    current_date: date | None = None

    # Index of earlier bodies per speaker, used to tell a quoted block from the
    # actual reply: a quote is text that speaker already said further up.
    said_by: dict[str, list[str]] = {}

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.lower() in _NOISE_LINES or _is_reaction_line(stripped):
            i += 1
            continue

        resolved = resolve_date_header(stripped, pasted_on)
        if resolved is not None:
            current_date = resolved
            i += 1
            continue

        # A speaker header is a name on one line and a (now-blank) phone line
        # under it. After stripping, the phone line is empty — so detect the
        # header on the ORIGINAL text instead.
        if i + 1 < n and _PHONE_LINE.match(_original_line(raw, lines, i + 1)):
            speaker = stripped
            i += 2

            quoted_speaker: str | None = None
            # A second header immediately after is the quoted person.
            if i + 1 < n and _PHONE_LINE.match(_original_line(raw, lines, i + 1)):
                quoted_speaker = lines[i].strip()
                i += 2

            body: list[str] = []
            sent_at: time | None = None
            edited = False
            while i < n:
                cur = lines[i].strip()
                ts = _TIMESTAMP_LINE.match(lines[i])
                if ts:
                    edited = bool(ts.group("edited"))
                    try:
                        sent_at = time(int(ts.group("h")), int(ts.group("m")))
                    except ValueError:
                        sent_at = None
                    i += 1
                    break
                # Next speaker header ends this message without a timestamp.
                if i + 1 < n and _PHONE_LINE.match(_original_line(raw, lines, i + 1)) and cur:
                    break
                if cur and not _is_reaction_line(cur):
                    body.append(cur)
                i += 1

            full = collapse_duplicated_text("\n".join(body))
            if not full:
                continue

            quoted_text: str | None = None
            if quoted_speaker:
                quoted_text, full = _split_quote(full, said_by.get(quoted_speaker, []))
                if not full:
                    # Nothing but the quote — no new claim was made.
                    continue

            messages.append(
                ParsedMessage(
                    speaker=speaker,
                    text=full,
                    sent_on=current_date,
                    sent_at=sent_at,
                    edited=edited,
                    quoted_speaker=quoted_speaker,
                    quoted_text=quoted_text,
                    links=_URL.findall(full),
                )
            )
            said_by.setdefault(speaker, []).append(full)
            continue

        i += 1

    return messages


def _original_line(raw: str, stripped_lines: list[str], idx: int) -> str:
    """
    Look up line `idx` in the ORIGINAL text.

    Phone numbers are removed before parsing, which is what makes them safe —
    but it also erases the marker that identifies a speaker header. The
    original text is consulted for that one check and nowhere else, so no
    number is ever carried into a message.
    """
    original = raw.splitlines()
    return original[idx] if idx < len(original) else ""


def _split_quote(full: str, earlier_by_quoted: list[str]) -> tuple[str | None, str]:
    """
    Separate a quoted block from the reply that follows it.

    WhatsApp renders the quoted message *above* the reply, so without this the
    quoted person's words get attributed to the replier. Detection is exact:
    the quote is text the quoted speaker demonstrably said earlier in this same
    paste. When no earlier message matches, the first line is treated as the
    quote — the common shape — and the rest as the reply.
    """
    for said in earlier_by_quoted:
        if full.startswith(said):
            reply = full[len(said):].strip()
            return said, reply

    lines = full.split("\n")
    if len(lines) >= 2:
        return lines[0].strip(), "\n".join(lines[1:]).strip()

    # A one-line reply with nothing to match: keep it as the reply, unquoted.
    return None, full
