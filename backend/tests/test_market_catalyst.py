"""
The semafor's escalations have to stand on something written down.

GOMES_VIDEO_ADDENDUM.md §V3. Yellow is a statement about valuation — "too
expensive, I don't know what will cause it". Orange and red are statements
about a CAUSE somebody identified, separated by whether its size is known.

Two failures are being tested for, and the second is the expensive one:

  * an escalation nobody can justify — ORANGE moves the target allocation to
    25/35/40 and sells most of a portfolio, and
  * an escalation nobody revisits. Nothing in this app lowers the semafor:
    `market_watch` tightens and never loosens, by design. An ORANGE set during
    a scare and forgotten goes on refusing every purchase forever, silently,
    because a refusal looks exactly like caution working.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services import market_catalyst as mc

NOW = datetime(2026, 8, 24, 12, 0)


def cause(days_ago: int = 0, *, severity_known: bool = False) -> mc.Catalyst:
    return mc.Catalyst(
        description="banky přestaly půjčovat",
        identified_at=NOW - timedelta(days=days_ago),
        severity_known=severity_known,
    )


class Row:
    """A `market_status` row, as far as this module is concerned."""

    def __init__(self, description=None, identified_at=None, severity_known=False):
        self.catalyst_description = description
        self.catalyst_identified_at = identified_at
        self.catalyst_severity_known = severity_known


class TestWhichGradeACauseJustifies:
    def test_no_cause_justifies_no_escalation(self):
        assert mc.grade_for(None) is None

    def test_a_cause_of_unknown_size_is_orange(self):
        # COVID: "I knew it was bad. I just didn't know HOW bad."
        assert mc.grade_for(cause()) == "ORANGE"

    def test_a_cause_known_to_be_severe_is_red(self):
        assert mc.grade_for(cause(severity_known=True)) == "RED"


class TestGradesThatNeedNoCause:
    """
    GREEN and YELLOW are valuation, and this module has nothing to say about
    them. It must stay silent there — a warning that appears every day stops
    being read, and the owner's whole budget for this screen is two minutes.
    """

    def test_green_is_supported_without_anything_written_down(self):
        verdict = mc.check("GREEN", None, now=NOW)
        assert verdict.supported and not verdict.needs_review
        assert verdict.message_cs == ""

    def test_yellow_is_supported_without_anything_written_down(self):
        verdict = mc.check("YELLOW", None, now=NOW)
        assert verdict.supported and not verdict.needs_review

    def test_an_unset_semafor_is_not_this_modules_problem(self):
        # The daily engine already warns about a semafor nobody set; saying it
        # twice in different words would just be noise.
        assert mc.check(None, None, now=NOW).supported


class TestEscalationWithNothingBehindIt:
    def test_orange_with_no_cause_is_unsupported(self):
        verdict = mc.check("ORANGE", None, now=NOW)

        assert not verdict.supported
        assert verdict.needs_review

    def test_it_falls_back_to_yellow_and_never_to_green(self):
        """
        The floor is YELLOW on purpose. This function must never be the reason
        an all-clear appears — and Gomes says most of his alerts are yellow.
        """
        assert mc.check("RED", None, now=NOW).supported_alert == "YELLOW"

    def test_the_reason_names_the_grade_in_czech_not_the_enum(self):
        message = mc.check("ORANGE", None, now=NOW).message_cs

        assert "oranžové" in message
        assert "ORANGE" not in message

    def test_it_reports_and_never_lowers_the_grade_itself(self):
        # The verdict carries what the evidence supports; `alert` still says
        # what is actually set. Lowering it is a person's decision.
        verdict = mc.check("ORANGE", None, now=NOW)

        assert verdict.alert == "ORANGE"
        assert verdict.supported_alert == "YELLOW"


class TestACauseThatDoesNotMatchTheGrade:
    def test_a_severe_cause_under_an_orange_is_flagged(self):
        verdict = mc.check("ORANGE", cause(severity_known=True), now=NOW)

        assert not verdict.supported
        assert verdict.supported_alert == "RED"

    def test_a_cause_of_unknown_size_under_a_red_is_flagged(self):
        verdict = mc.check("RED", cause(), now=NOW)

        assert not verdict.supported
        assert verdict.supported_alert == "ORANGE"


class TestACauseNobodyHasRevisited:
    def test_a_fresh_cause_is_supported_and_quiet(self):
        verdict = mc.check("ORANGE", cause(days_ago=3), now=NOW)

        assert verdict.supported
        assert not verdict.needs_review

    def test_an_old_cause_still_supports_the_grade(self):
        """
        Staleness is a prompt, not an expiry. A real crisis lasts longer than a
        quarter and the semafor must not fall off it on a timer.
        """
        verdict = mc.check("ORANGE", cause(days_ago=200), now=NOW)

        assert verdict.supported
        assert verdict.stale
        assert verdict.needs_review

    def test_the_prompt_says_how_long_and_what_it_is_costing(self):
        message = mc.check("ORANGE", cause(days_ago=200), now=NOW).message_cs

        assert "200" in message
        assert "nepovolí žádný nákup" in message

    def test_the_boundary_is_the_documented_one(self):
        assert not mc.check(
            "ORANGE", cause(days_ago=mc.STALE_AFTER_DAYS - 1), now=NOW
        ).stale
        assert mc.check(
            "ORANGE", cause(days_ago=mc.STALE_AFTER_DAYS), now=NOW
        ).stale


class TestReadingItOffARow:
    def test_a_row_with_both_halves_becomes_a_cause(self):
        found = mc.of_row(Row("covid", NOW, severity_known=True))

        assert found is not None
        assert found.description == "covid"
        assert found.severity_known is True

    def test_a_description_with_no_date_is_no_cause_at_all(self):
        # The age is the only thing that makes a forgotten escalation visible.
        # A cause that cannot be aged cannot be questioned.
        assert mc.of_row(Row("covid", None)) is None

    def test_a_date_with_no_description_is_no_cause_either(self):
        assert mc.of_row(Row(None, NOW)) is None

    def test_no_row_is_no_cause(self):
        assert mc.of_row(None) is None


class TestTheOneLineForTheDailyList:
    def test_silent_when_the_grade_stands_on_something(self):
        assert mc.note_for("ORANGE", Row("covid", NOW), now=NOW) is None

    def test_silent_on_the_grades_that_need_no_cause(self):
        assert mc.note_for("GREEN", None, now=NOW) is None
        assert mc.note_for("YELLOW", None, now=NOW) is None

    def test_speaks_when_an_escalation_has_nothing_written_down(self):
        note = mc.note_for("ORANGE", None, now=NOW)

        assert note is not None
        assert "není zapsané proč" in note

    def test_speaks_when_the_cause_has_gone_unreviewed(self):
        note = mc.note_for(
            "ORANGE", Row("covid", NOW - timedelta(days=200)), now=NOW
        )

        assert note is not None
        assert "Platí pořád?" in note

    def test_the_away_digest_can_find_it_by_its_marker(self):
        """
        `app/routes/away.py` ranks blind spots by uppercased markers, and
        SEMAFOR is the one that means "the gate itself is questionable". The
        note has to survive that filter or it never reaches somebody who has
        been away for a fortnight.
        """
        note = mc.note_for("ORANGE", None, now=NOW)

        assert "SEMAFOR" in note.upper()
