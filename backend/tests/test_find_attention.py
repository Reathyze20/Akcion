"""
Rubrika pozornosti — testy na pevných číslech, bez databáze a bez sítě.

Čemu se tady hlídá záda: rubrika se dá snadno posunout do role verdiktu. Stačí,
aby chybějící vstup srazil body místo stropu, a z „o téhle firmě nevíme dost"
se stane „tahle firma je špatná". Přesně ta záměna už tuhle aplikaci stála tři
sebejisté verdikty na prázdno, takže na ní stojí většina testů níž.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.services import find_attention as fa
from app.services.find_dossier import (
    DIR_PRO,
    DIR_PROTI,
    Dossier,
    MethodReading,
    Signals,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def make_dossier(
    *,
    green: float | None = None,
    red: float | None = None,
    rr: float | None = None,
    deserved: float | None = None,
    confirmed: int | None = None,
    proposed: int | None = None,
    price_is_stale: bool = False,
    **signal_kwargs,
) -> Dossier:
    """Spis jen s tím, co rubrika čte. Fakta a mezery na skóre nemají vliv."""
    return Dossier(
        ticker="TEST",
        symbol="TEST",
        company_name="Testovací",
        as_of=NOW,
        price=10.0,
        price_currency="USD",
        price_is_stale=price_is_stale,
        facts=(),
        gaps=(),
        method=MethodReading(
            band="NEZNAME",
            band_reason_cs="",
            rr_score=rr,
            deserved=deserved,
            green_line=green,
            red_line=red,
            cylinders_confirmed=confirmed,
            cylinders_proposed=proposed,
        ),
        signals=Signals(recorded=True, **signal_kwargs),
    )


def pillar(att: fa.Attention, key: str) -> fa.Pillar:
    return next(p for p in att.pillars if p.key == key)


# ==============================================================================
# Jádro: mezera snižuje strop, ne body
# ==============================================================================

class TestMissingInputLowersTheCeiling:
    def test_no_gomes_lines_makes_valuation_unreachable_not_zero_scored(self):
        """
        Bez čar není pásmo. Kdyby to bylo 0/30 místo 0/0, každý vlastní nález
        by dostal třicetibodovou srážku za to, že ho Gomes nepokrývá — tedy
        trest za volbu, kvůli které tahle část aplikace vznikla.
        """
        att = fa.score(make_dossier())
        oceneni = pillar(att, fa.KEY_OCENENI)
        assert oceneni.points == 0
        assert oceneni.ceiling == 0
        assert oceneni.max_points == fa.MAX_OCENENI
        assert "nevydal zelenou a červenou čáru" in oceneni.missing_cs

    def test_the_ceiling_is_reported_and_is_below_the_total(self):
        att = fa.score(make_dossier())
        assert att.ceiling < fa.TOTAL
        assert att.to_dict()["total"] == fa.TOTAL

    def test_lines_without_confirmed_cylinders_still_cannot_value(self):
        """Návrh rubriky ocenění neodemyká — zasloužené skóre stojí na potvrzených."""
        att = fa.score(make_dossier(green=1.0, red=10.0, rr=6.0, proposed=5))
        oceneni = pillar(att, fa.KEY_OCENENI)
        assert oceneni.ceiling == 0
        assert "nikdo nepotvrdil" in oceneni.missing_cs
        assert oceneni.action == fa.ACTION_CONFIRM_CYLINDERS

    def test_a_stale_price_lowers_the_ceiling_rather_than_the_points(self):
        fresh = fa.score(
            make_dossier(green=1.0, red=10.0, rr=9.0, deserved=4.0, confirmed=6)
        )
        stale = fa.score(
            make_dossier(
                green=1.0,
                red=10.0,
                rr=9.0,
                deserved=4.0,
                confirmed=6,
                price_is_stale=True,
            )
        )
        assert pillar(fresh, fa.KEY_OCENENI).ceiling == fa.MAX_OCENENI
        assert pillar(stale, fa.KEY_OCENENI).ceiling == fa.OCENENI_STALE_CEILING
        assert pillar(stale, fa.KEY_OCENENI).points <= fa.OCENENI_STALE_CEILING


# ==============================================================================
# Známá nepřítomnost je nula při plném stropu
# ==============================================================================

class TestAKnownAbsenceIsNotAGap:
    def test_transcripts_that_never_mention_the_company_score_zero_at_full_ceiling(self):
        """
        „Máme 61 přepisů a v žádném o ní nemluví" je odpověď. Snížit za ni strop
        by znamenalo tvrdit, že se to teprve dá zjistit.
        """
        att = fa.score(make_dossier(gomes_transcripts_total=61))
        kryti = pillar(att, fa.KEY_KRYTI)
        assert kryti.points == 0
        assert kryti.ceiling == fa.MAX_KRYTI
        assert kryti.missing_cs is None
        assert "odpověď, ne mezera" in kryti.reason_cs

    def test_having_no_transcripts_at_all_is_a_gap_and_lowers_the_ceiling(self):
        att = fa.score(make_dossier(gomes_transcripts_total=0))
        kryti = pillar(att, fa.KEY_KRYTI)
        assert kryti.ceiling == 0
        assert kryti.missing_cs is not None

    def test_silence_after_coverage_is_zero_at_full_ceiling_and_says_so(self):
        """
        VTSI: dvacet epizod a půl roku nic. Držíme ji. „Přestal o tom mluvit"
        je jiný stav než „nikdy o tom nemluvil" a musí být napsaný.
        """
        att = fa.score(
            make_dossier(
                gomes_transcripts_total=61,
                gomes_episodes_total=20,
                gomes_episodes_recent=0,
                gomes_newest_age_days=102,
            )
        )
        kryti = pillar(att, fa.KEY_KRYTI)
        assert kryti.points == 0
        assert kryti.ceiling == fa.MAX_KRYTI
        assert "ticho po pokrytí" in kryti.reason_cs
        assert "102" in kryti.reason_cs


# ==============================================================================
# Krytí se měří kadencí, ne sentimentem
# ==============================================================================

class TestCoverageIsMeasuredByCadence:
    """
    `sentiment` je na 366 zmínkách 311× BULLISH a z deseti „BEARISH" jsou
    správně dvě — pole, které v 85 % říká totéž a ve zbytku se mýlí, neměří
    nic. Kadence kolísá od 37 epizod po jednu a dá se ověřit spočítáním.
    """

    def test_the_sentiment_of_the_newest_mention_does_not_move_the_score(self):
        base = dict(gomes_transcripts_total=61, gomes_episodes_total=10,
                    gomes_episodes_recent=4, gomes_newest_age_days=5)
        bullish = fa.score(make_dossier(**base, gomes_newest_direction=DIR_PRO))
        bearish = fa.score(make_dossier(**base, gomes_newest_direction=DIR_PROTI))
        assert pillar(bullish, fa.KEY_KRYTI).points == pillar(bearish, fa.KEY_KRYTI).points

    def test_more_recent_episodes_score_higher(self):
        quiet = fa.score(make_dossier(gomes_transcripts_total=61,
                                      gomes_episodes_total=20, gomes_episodes_recent=1))
        loud = fa.score(make_dossier(gomes_transcripts_total=61,
                                     gomes_episodes_total=20, gomes_episodes_recent=5))
        assert pillar(loud, fa.KEY_KRYTI).points > pillar(quiet, fa.KEY_KRYTI).points

    def test_cadence_alone_cannot_take_the_whole_pillar(self):
        """Pět z patnácti bodů patří shodě dvou zdrojů, ne kadenci."""
        att = fa.score(make_dossier(gomes_transcripts_total=61,
                                    gomes_episodes_total=40, gomes_episodes_recent=40))
        assert pillar(att, fa.KEY_KRYTI).points == pytest.approx(fa.MAX_KADENCE)

    def test_a_second_source_adds_only_when_gomes_also_covers_it(self):
        bi_only = fa.score(
            make_dossier(gomes_transcripts_total=61, bi_on_watchlist=True,
                         bi_endorsements=9)
        )
        assert pillar(bi_only, fa.KEY_KRYTI).points == 0
        assert "jeden zdroj, ne dva" in pillar(bi_only, fa.KEY_KRYTI).reason_cs

        both = fa.score(
            make_dossier(gomes_transcripts_total=61, gomes_episodes_total=3,
                         gomes_episodes_recent=3, bi_on_watchlist=True,
                         bi_endorsements=9, second_source_agrees=True)
        )
        assert pillar(both, fa.KEY_KRYTI).points > pillar(bi_only, fa.KEY_KRYTI).points

    def test_a_named_analyst_counts_for_more_than_the_anonymous_list(self):
        """
        Pod počtem podpisů není nikdo podepsaný, pod jmenovaným tvrzením ano.
        Robert Mock napsal o DFSC jedenáct vět s citáty — to je jiná váha než
        „dva členové to odklikli".
        """
        base = dict(gomes_transcripts_total=61, gomes_episodes_total=4,
                    gomes_episodes_recent=4, bi_on_watchlist=True,
                    bi_endorsements=2, second_source_agrees=True)
        anonymous = fa.score(make_dossier(**base))
        named = fa.score(make_dossier(**base, bi_named_claims=11))
        assert (
            pillar(named, fa.KEY_KRYTI).points
            - pillar(anonymous, fa.KEY_KRYTI).points
        ) == fa.SHODA_JMENOVANY
        assert "jmenovaný analytik" in pillar(named, fa.KEY_KRYTI).reason_cs

    def test_the_two_halves_of_agreement_never_exceed_their_share(self):
        att = fa.score(
            make_dossier(gomes_transcripts_total=61, gomes_episodes_total=40,
                         gomes_episodes_recent=40, bi_on_watchlist=True,
                         bi_endorsements=99, second_source_agrees=True,
                         bi_named_claims=50)
        )
        assert pillar(att, fa.KEY_KRYTI).points == fa.MAX_KRYTI

    def test_endorsements_alone_never_move_the_score(self):
        """Dav, který se pod nic nepodepsal, nesmí nález protlačit nahoru."""
        few = fa.score(make_dossier(gomes_transcripts_total=61, bi_on_watchlist=True,
                                    bi_endorsements=1))
        many = fa.score(make_dossier(gomes_transcripts_total=61, bi_on_watchlist=True,
                                     bi_endorsements=99))
        assert pillar(few, fa.KEY_KRYTI).points == pillar(many, fa.KEY_KRYTI).points


# ==============================================================================
# Breakout Investors se ukazuje a neposlouchá
# ==============================================================================

class TestBreakoutNeverMovesTheScore:
    def test_no_pillar_reads_the_breakout_layer(self):
        """
        Rozhodnutí majitele z 23. 8. 2026: seškrábaný počet podpisů bez
        jmenovaného autora není stanovisko. Kdyby zvedal skóre, protlačil by
        nález nahoru silou davu, který se pod nic nepodepsal.
        """
        with_entry = make_dossier(gomes_transcripts_total=10)
        assert not any(
            "breakout" in (p.reason_cs + (p.missing_cs or "")).lower()
            for p in fa.score(with_entry).pillars
        )


# ==============================================================================
# Provoz
# ==============================================================================

class TestOperations:
    def test_hard_evidence_counts_double_the_soft(self):
        hard = fa.score(make_dossier(cylinder_evidence_count=4, cylinder_hard_delta=2,
                                     proposed=5))
        soft = fa.score(make_dossier(cylinder_evidence_count=4, cylinder_soft_delta=2,
                                     proposed=5))
        assert pillar(hard, fa.KEY_PROVOZ).points > pillar(soft, fa.KEY_PROVOZ).points

    def test_a_short_runway_caps_the_pillar_however_good_the_rest_is(self):
        """
        Sedm měsíců hotovosti je ta AZTR situace. Runway je jediné pravidlo,
        které platí i u firmy, kterou metodika ocenit neumí, takže nesmí být
        jen poznámkou pod dobrým skóre.
        """
        att = fa.score(
            make_dossier(
                proposed=6,
                cylinder_evidence_count=6,
                cylinder_hard_delta=4,
                runway_months=7.0,
            )
        )
        provoz = pillar(att, fa.KEY_PROVOZ)
        assert provoz.points <= fa.MAX_PROVOZ * fa.RUNWAY_TIGHT_CAP
        assert "měsíců drží tenhle díl dole" in provoz.reason_cs

    def test_a_critical_runway_caps_harder_than_a_tight_one(self):
        tight = fa.score(make_dossier(proposed=6, cylinder_evidence_count=6,
                                      cylinder_hard_delta=4, runway_months=9.0))
        critical = fa.score(make_dossier(proposed=6, cylinder_evidence_count=6,
                                         cylinder_hard_delta=4, runway_months=3.0))
        assert (
            pillar(critical, fa.KEY_PROVOZ).points
            < pillar(tight, fa.KEY_PROVOZ).points
        )

    def test_evidence_without_a_cylinder_number_keeps_a_reduced_ceiling(self):
        att = fa.score(make_dossier(cylinder_evidence_count=3, cylinder_hard_delta=1))
        provoz = pillar(att, fa.KEY_PROVOZ)
        assert provoz.ceiling == fa.PROVOZ_CEILING_WITHOUT_NUMBER
        assert provoz.missing_cs is not None

    def test_no_evidence_at_all_is_an_unreachable_pillar(self):
        provoz = pillar(fa.score(make_dossier()), fa.KEY_PROVOZ)
        assert provoz.ceiling == 0
        assert provoz.action == fa.ACTION_REFRESH


# ==============================================================================
# Naléhavost
# ==============================================================================

class TestUrgency:
    def test_an_unknown_earnings_date_lowers_the_ceiling(self):
        """
        „Nevíme kdy" není totéž co „daleko". Kdyby se to počítalo jako daleko,
        tichá mezera by na obrazovce vypadala jako klid.
        """
        unknown = pillar(fa.score(make_dossier()), fa.KEY_NALEHAVOST)
        assert unknown.ceiling == fa.MAX_NALEHAVOST - fa.NALEH_EARNINGS
        assert unknown.missing_cs is not None

    def test_a_distant_earnings_date_is_full_ceiling_and_no_points(self):
        far = pillar(
            fa.score(make_dossier(earnings_known=True, earnings_days=120)),
            fa.KEY_NALEHAVOST,
        )
        assert far.ceiling == fa.MAX_NALEHAVOST
        assert far.points == 0
        assert far.missing_cs is None

    def test_an_imminent_print_scores(self):
        soon = pillar(
            fa.score(
                make_dossier(
                    earnings_known=True, earnings_days=9, earnings_confirmed=True
                )
            ),
            fa.KEY_NALEHAVOST,
        )
        assert soon.points == fa.NALEH_EARNINGS

    def test_an_estimated_date_says_so(self):
        soon = pillar(
            fa.score(
                make_dossier(
                    earnings_known=True, earnings_days=9, earnings_confirmed=False
                )
            ),
            fa.KEY_NALEHAVOST,
        )
        assert "odhad" in soon.reason_cs

    def test_urgency_never_exceeds_its_own_ceiling(self):
        att = fa.score(
            make_dossier(
                insider_buy_recent=True,
                filings_fresh=True,
                gomes_newest_age_days=3,
                gomes_transcripts_total=5,
                gomes_newest_weight=0.9,
                gomes_newest_direction=DIR_PRO,
            )
        )
        naleh = pillar(att, fa.KEY_NALEHAVOST)
        assert naleh.points <= naleh.ceiling


# ==============================================================================
# Tvoje teze — jediná páka, která stojí peníze
# ==============================================================================

class TestOwnThesis:
    def test_without_an_explanation_the_pillar_is_unreachable(self):
        teze = pillar(fa.score(make_dossier()), fa.KEY_TEZE)
        assert teze.ceiling == 0
        assert teze.action == fa.ACTION_EXPLAIN
        assert "placené" in teze.missing_cs

    @pytest.mark.parametrize(
        "verdict,expected",
        [
            ("DRZI", fa.TEZE_HOLDS),
            ("NEDRZI", 0.0),
            ("NELZE_POSOUDIT", fa.TEZE_UNDECIDED),
        ],
    )
    def test_each_verdict_scores_at_full_ceiling(self, verdict, expected):
        att = fa.score(make_dossier(), own_reason_verdict=verdict)
        teze = pillar(att, fa.KEY_TEZE)
        assert teze.points == expected
        assert teze.ceiling == fa.MAX_TEZE

    def test_explaining_raises_the_ceiling_by_the_whole_pillar(self):
        before = fa.score(make_dossier())
        after = fa.score(make_dossier(), own_reason_verdict="NEDRZI")
        assert after.ceiling - before.ceiling == fa.MAX_TEZE


# ==============================================================================
# Součet, páka a slova
# ==============================================================================

class TestTheWholeScore:
    def test_points_never_exceed_the_ceiling_and_the_ceiling_never_exceeds_the_total(self):
        cases = [
            make_dossier(),
            make_dossier(green=1.0, red=10.0, rr=9.9, deserved=0.0, confirmed=10),
            make_dossier(
                green=1.0,
                red=10.0,
                rr=9.9,
                deserved=0.0,
                confirmed=10,
                proposed=10,
                cylinder_evidence_count=8,
                cylinder_hard_delta=9,
                cylinder_soft_delta=4,
                insider_buy_recent=True,
                filings_fresh=True,
                earnings_known=True,
                earnings_days=2,
                earnings_confirmed=True,
                gomes_transcripts_total=61,
                gomes_newest_weight=1.0,
                gomes_newest_direction=DIR_PRO,
                gomes_newest_age_days=1,
            ),
        ]
        for d in cases:
            for verdict in (None, "DRZI", "NEDRZI"):
                att = fa.score(d, own_reason_verdict=verdict)
                assert 0 <= att.points <= att.ceiling <= fa.TOTAL

    def test_the_ratio_is_none_at_a_zero_ceiling_never_zero(self):
        """Nula by tvrdila „nic nezískal". Prázdný strop znamená „nedá se říct"."""
        empty = fa.Attention(points=0.0, ceiling=0.0)
        assert empty.ratio is None

    def test_the_lever_names_the_biggest_unreachable_pillar(self):
        att = fa.score(make_dossier(gomes_transcripts_total=61))
        # Ocenění je 30 bodů, tedy víc než teze (15) i naléhavost (6).
        assert "nevydal zelenou a červenou čáru" in att.lever_cs
        assert "30 bodů" in att.lever_cs

    def test_the_lever_offers_an_action_when_one_exists(self):
        att = fa.score(
            make_dossier(green=1.0, red=10.0, rr=6.0, gomes_transcripts_total=61)
        )
        assert att.lever_action == fa.ACTION_CONFIRM_CYLINDERS

    def test_a_fully_known_company_has_no_lever(self):
        att = fa.score(
            make_dossier(
                green=1.0,
                red=10.0,
                rr=8.0,
                deserved=4.0,
                confirmed=6,
                proposed=6,
                cylinder_evidence_count=5,
                cylinder_hard_delta=3,
                earnings_known=True,
                earnings_days=40,
                gomes_transcripts_total=61,
            ),
            own_reason_verdict="DRZI",
        )
        assert att.ceiling == fa.TOTAL
        assert att.lever_cs is None

    def test_a_low_ceiling_is_described_as_ignorance_not_as_a_bad_company(self):
        att = fa.score(make_dossier())
        assert att.ceiling < fa.CEILING_TOO_LOW
        assert "není soud o firmě" in att.verdict_cs

    def test_the_conditional_cylinder_sentence_appears_only_when_it_adds_something(self):
        without = fa.score(make_dossier(green=1.0, red=10.0, rr=6.0))
        assert without.if_cylinders_cs is None  # návrh chybí

        with_proposal = fa.score(make_dossier(green=1.0, red=10.0, rr=6.0, proposed=5))
        assert "nepotvrzeno" in with_proposal.if_cylinders_cs

        confirmed = fa.score(
            make_dossier(green=1.0, red=10.0, rr=6.0, deserved=5.0, confirmed=5,
                         proposed=5)
        )
        assert confirmed.if_cylinders_cs is None

    def test_serialisation_always_carries_the_ceiling_next_to_the_points(self):
        payload = fa.score(make_dossier()).to_dict()
        assert {"points", "ceiling", "total", "verdict_cs", "pillars"} <= set(payload)
        assert all(
            {"points", "ceiling", "max_points", "reason_cs"} <= set(p)
            for p in payload["pillars"]
        )


# ==============================================================================
# Posudek bez zapsaných signálů se neskóruje
# ==============================================================================

class TestAnUnrecordedAssessmentIsNotScoredAsZero:
    """
    Prázdné `Signals` znamená „nevíme", ne „nula ze všeho".

    Bez tohohle rozlišení dostal první nález (AZTR, posudek z 24. 8., zapsaný
    ještě před rubrikou) skóre 0/24 s větou „nemáme od Marka Gomese jediný
    přepis" — u firmy, jejíž vlastní spis o kus výš hlásí, že jich máme 61.
    """

    def _unrecorded(self) -> Dossier:
        d = make_dossier(gomes_transcripts_total=61)
        return replace(d, signals=Signals())

    def test_it_returns_no_score_at_all_rather_than_a_low_one(self):
        att = fa.score(self._unrecorded())
        assert att.points == 0
        assert att.ceiling == 0
        assert att.ratio is None
        assert att.pillars == ()

    def test_it_says_why_and_offers_the_one_action_that_helps(self):
        att = fa.score(self._unrecorded())
        assert "před skóre" in att.verdict_cs
        assert att.lever_action == fa.ACTION_REFRESH
        assert "zpětně nepřepisuje" in att.lever_cs

    def test_the_same_answer_is_available_without_a_dossier_at_all(self):
        """Route ji potřebuje pro řádek, kde `attention` je NULL."""
        assert fa.not_scored().verdict_cs == fa.score(self._unrecorded()).verdict_cs
        assert fa.not_scored().lever_action == fa.ACTION_REFRESH

    def test_it_never_claims_the_company_lacks_coverage(self):
        """Ta věta by byla nepravdivá a spis by si s ní odporoval."""
        att = fa.score(self._unrecorded())
        assert "přepis" not in att.verdict_cs


# ==============================================================================
# AZTR — ta obrazovka, kvůli které to celé vzniklo
# ==============================================================================

class TestTheAztrCase:
    """
    Nano-cap bez Gomesova pokrytí, se sedmiměsíční hotovostí a insiderskými
    nákupy. Dnes o ní stůl říká „semafor je žlutá" a nic víc.
    """

    def _aztr(self, **kw):
        return make_dossier(
            proposed=4,
            cylinder_evidence_count=6,
            cylinder_hard_delta=1,
            cylinder_soft_delta=0,
            insider_buy_recent=True,
            runway_months=7.0,
            filings_fresh=True,
            gomes_transcripts_total=61,
            **kw,
        )

    def test_it_scores_low_but_says_the_ceiling_is_the_reason(self):
        att = fa.score(self._aztr())
        assert att.ceiling < fa.TOTAL
        assert pillar(att, fa.KEY_OCENENI).ceiling == 0
        assert pillar(att, fa.KEY_KRYTI).ceiling == fa.MAX_KRYTI  # známá nepřítomnost
        assert att.lever_cs is not None

    def test_the_short_runway_is_visible_in_the_operations_reason(self):
        att = fa.score(self._aztr())
        assert "7 měsíců" in pillar(att, fa.KEY_PROVOZ).reason_cs

    def test_insider_buying_shows_up_as_urgency_not_as_quality(self):
        att = fa.score(self._aztr())
        assert "insider" in pillar(att, fa.KEY_NALEHAVOST).reason_cs.lower()
