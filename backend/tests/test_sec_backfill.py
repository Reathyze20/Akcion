"""
Tests for the offline backfill path.

Re-reading every holding after a prompt change is dozens of long documents.
The backend buys the *newest* filing's analysis through the API because a
server has no other way to read one; a bulk re-read is done in a Claude Code
session instead, and this script is the seam between the two.

The one thing it must never do is write an empty template back as an analysis.
`analysis IS NULL` is what the UI renders as "neanalyzováno"; a blank string is
what it would render as a filing read and found unremarkable. Those are
different claims about a company, and this codebase has had to stop conflating
them more than once.
"""

import importlib.util
import pathlib

import pytest


SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "sec_backfill.py"


@pytest.fixture(scope="module")
def backfill():
    """Load the script as a module — it is a CLI, not a package."""
    spec = importlib.util.spec_from_file_location("sec_backfill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSummaryBody:
    def test_the_template_alone_is_not_a_summary(self, backfill):
        assert backfill.summary_body(backfill.INSTRUCTIONS) == ""

    def test_an_empty_file_is_not_a_summary(self, backfill):
        assert backfill.summary_body("") == ""
        assert backfill.summary_body("   \n\n  ") == ""

    def test_what_was_written_after_the_template_is_kept(self, backfill):
        written = backfill.INSTRUCTIONS + "\n**Výhled:** potvrzen 57–63 mil. USD."
        assert backfill.summary_body(written) == "**Výhled:** potvrzen 57–63 mil. USD."

    def test_a_summary_with_no_template_survives_intact(self, backfill):
        """Someone may write the file from scratch rather than editing ours."""
        assert backfill.summary_body("**Varovné signály:**\n  🔴 going concern") == (
            "**Varovné signály:**\n  🔴 going concern"
        )

    def test_an_arrow_inside_the_prose_does_not_truncate_it(self, backfill):
        """
        `-->` is the comment terminator, and splitting on the first one is only
        safe because the template's comment comes first. A summary that opens
        with prose must not lose everything before its own arrow.
        """
        prose = "Tržby 2Q --> 3Q rostou. Zbytek textu."
        assert backfill.summary_body(prose) == prose


class TestExportInstructions:
    def test_the_template_asks_for_the_rendered_shape(self, backfill):
        """
        A hand-written summary and an API-written one land in the same column
        and are shown by the same component, so they have to read alike.
        """
        for section in ("Varovné signály", "Výhled", "Provozní fakta",
                        "Nová/zhoršená rizika"):
            assert section in backfill.INSTRUCTIONS, section

    def test_the_template_forbids_filling_gaps_in(self, backfill):
        assert "Nic nedomýšlej" in backfill.INSTRUCTIONS

    def test_the_template_is_a_comment(self, backfill):
        """Otherwise `summary_body` cannot tell it from written prose."""
        assert backfill.INSTRUCTIONS.strip().startswith("<!--")
        assert "-->" in backfill.INSTRUCTIONS


class TestSlug:
    def test_a_slash_in_a_form_name_does_not_become_a_directory(self, backfill):
        """10-K/A is a real form. Left alone it would write outside the folder."""

        class Fake:
            ticker = "DAIO"
            form = "10-K/A"
            filed_date = "2026-08-14"

        assert backfill._slug(Fake()) == "DAIO_10-K-A_2026-08-14"
