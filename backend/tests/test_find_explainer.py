"""
Ověřování bodů od modelu — nejdůležitější pojistka celé části „Nálezy".

Tahle aplikace už třikrát vydala sebejistý verdikt na prázdno: atrapa AI
analytika psala vymyšlená čísla do živého portfolia, 395 neověřených tvrzení
se dostalo do databáze a `price_lines_data.py` držel natvrdo zapsaná pásma,
systematicky o 1,2 bodu býčí. Bod, který cituje fakt, jenž ve spisu není, je
tatáž vada v novém obalu — jen s odkazem místo doslovného citátu.

Testy níž popisují, co se s takovým bodem musí stát: zahodí se, spočítá a
počet se ukáže. Nic z toho není otázka vkusu.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import find_explainer as fe
from app.services.find_dossier import (
    DIR_NEUTRAL,
    DIR_PRO,
    DIR_PROTI,
    Dossier,
    Fact,
    Gap,
    MethodReading,
)
from app.services.llm import LLMError


def _dossier() -> Dossier:
    """Malý spis: jeden fakt pro, jeden proti, jeden kontext a jedna mezera."""
    return Dossier(
        ticker="ABCD",
        symbol="ABCD",
        company_name="Firma, s. r. o.",
        as_of=datetime(2026, 8, 24, tzinfo=timezone.utc),
        price=4.2,
        price_currency="USD",
        price_is_stale=False,
        facts=(
            Fact(
                id="FUND-1",
                layer="FUNDAMENTY",
                text_cs="Tržby meziročně +28 %.",
                source="SEC XBRL",
                direction=DIR_PRO,
            ),
            Fact(
                id="METOD-1",
                layer="METODIKA",
                text_cs="Hotovost vydrží zhruba 4 měsíce.",
                source="rubrika válců",
                direction=DIR_PROTI,
            ),
            Fact(
                id="TRH-1",
                layer="TRH",
                text_cs="Kurz 4,20 USD k 24. 8. 2026.",
                source="Yahoo Finance",
                direction=DIR_NEUTRAL,
            ),
        ),
        gaps=(
            Gap(
                id="MEZ-1",
                layer="METODIKA",
                text_cs="Válce nikdo nepotvrdil.",
            ),
        ),
        method=MethodReading(band="NEZNAME", band_reason_cs="Válce neznáme"),
    )


def _point(**kwargs) -> fe.ExplainedPoint:
    base = dict(
        side="PRO",
        headline_cs="Tržby rostou",
        body_cs="Meziročně o 28 %.",
        fact_ids=["FUND-1"],
        canon_ref="§3",
        check_yourself_cs="Ve výkazu 10-Q v řádku Revenues proti témuž kvartálu loni.",
        weight="PODSTATNY",
    )
    base.update(kwargs)
    return fe.ExplainedPoint(**base)


class TestVerifyPoints:
    def test_valid_point_survives(self):
        kept, dropped = fe.verify_points([_point()], _dossier())
        assert len(kept) == 1
        assert dropped == []

    def test_point_with_no_fact_ids_is_dropped(self):
        kept, dropped = fe.verify_points([_point(fact_ids=[])], _dossier())
        assert kept == []
        assert "neuvádí žádný fakt" in dropped[0].reason_cs

    def test_point_citing_an_unknown_fact_is_dropped(self):
        """Vymyšlený fakt oblečený do citace. Přesně ta vada, kvůli které to je."""
        kept, dropped = fe.verify_points([_point(fact_ids=["FUND-99"])], _dossier())
        assert kept == []
        assert "FUND-99" in dropped[0].reason_cs

    def test_point_citing_a_gap_is_dropped(self):
        """Usuzovat z toho, co nevíme, je nejdražší způsob, jak se splést."""
        kept, dropped = fe.verify_points([_point(fact_ids=["MEZ-1"])], _dossier())
        assert kept == []
        assert "mezeru" in dropped[0].reason_cs

    def test_pro_point_built_only_on_a_proti_fact_is_dropped(self):
        """„Hotovost vydrží čtyři měsíce, což je dobře" nesmí projít."""
        kept, dropped = fe.verify_points(
            [_point(side="PRO", fact_ids=["METOD-1"])], _dossier()
        )
        assert kept == []
        assert "opačně" in dropped[0].reason_cs

    def test_proti_point_may_cite_the_proti_fact(self):
        kept, dropped = fe.verify_points(
            [_point(side="PROTI", fact_ids=["METOD-1"])], _dossier()
        )
        assert len(kept) == 1
        assert dropped == []

    def test_a_neutral_fact_supports_either_side(self):
        """Kontext patří do obou stran — kurz sám o sobě nemluví ani pro, ani proti."""
        for side in ("PRO", "PROTI"):
            kept, _ = fe.verify_points(
                [_point(side=side, fact_ids=["TRH-1"])], _dossier()
            )
            assert len(kept) == 1, side

    def test_unknown_canon_reference_is_dropped(self):
        kept, dropped = fe.verify_points([_point(canon_ref="§42")], _dossier())
        assert kept == []
        assert "§42" in dropped[0].reason_cs

    def test_unknown_side_is_dropped(self):
        kept, dropped = fe.verify_points([_point(side="MOZNA")], _dossier())
        assert kept == []


class TestCanonDigest:
    def test_every_reference_exists_in_the_canon_documents(self):
        """
        Kánon je deklarovaný zdroj pravdy. Odkaz na sekci, která v něm není,
        by z vysvětlení udělal ozdobu s falešnou autoritou.
        """
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "docs"
        text = ""
        for name in ("GOMES_METHODOLOGY_CANON.md", "GOMES_VIDEO_ADDENDUM.md"):
            path = root / name
            assert path.exists(), f"chybí {path}"
            text += path.read_text(encoding="utf-8")

        headings = re.findall(r"^#{2,3}\s+(.*)$", text, flags=re.MULTILINE)
        blob = " ".join(headings)

        for ref in fe.CANON_DIGEST:
            number = ref.lstrip("§")
            if number.startswith("V"):
                assert re.search(rf"\b{number}\.", blob), f"{ref} není v dodatku"
            else:
                assert re.search(rf"(?<![\w.]){re.escape(number)}[.\s]", blob), (
                    f"{ref} není v kánonu"
                )

    def test_canon_text_returns_words_not_the_key(self):
        assert "zasloužené" in fe.canon_text("§4b").lower()
        assert fe.canon_text("§99") == ""


class TestSystemPrompt:
    def test_the_iron_rules_are_stated(self):
        """Prompt je smlouva. Když se z něj pravidlo ztratí, ztratí se tiše."""
        prompt = fe.build_system_prompt()
        assert "Nedělej verdikt" in prompt
        assert "O mezerách nepiš" in prompt
        assert "Nevymýšlej čísla" in prompt
        assert "check_yourself_cs" in prompt
        assert "MIMO_METODIKU" in prompt  # jako příklad toho, co se NEPÍŠE

    def test_prompt_lists_only_real_canon_keys(self):
        prompt = fe.build_system_prompt()
        for ref in fe.CANON_DIGEST:
            assert ref in prompt


class TestExplain:
    def _payload(self, points):
        return {
            "one_line_cs": "Malá firma, o které metodika zatím neumí rozhodnout.",
            "points": points,
            "own_reason_cs": "Úvaha o růstu tržeb sedí.",
            "own_reason_verdict": "DRZI",
            "lesson_cs": "Růst tržeb bez hotovosti není teze.",
        }

    def test_never_touches_the_api_when_a_double_is_injected(self):
        calls = []

        def fake(prompt, **kwargs):
            calls.append((prompt, kwargs))
            return self._payload([_point().model_dump()])

        result = fe.explain(_dossier(), note="Roste jim to.", complete_json=fake)
        assert len(calls) == 1
        assert result.points_kept == 1
        assert result.points_dropped == 0
        assert result.model == fe.EXPLAIN_MODEL

    def test_invented_citations_are_dropped_and_counted(self):
        """
        Neúspěch se nesmí tvářit jako úspěch: body zmizí, ale počet zůstane
        a routa ho ukáže.
        """
        payload = self._payload(
            [
                _point(fact_ids=["FUND-1"]).model_dump(),
                _point(fact_ids=["VYMYSLENO-7"]).model_dump(),
                _point(fact_ids=["MEZ-1"]).model_dump(),
            ]
        )
        result = fe.explain(_dossier(), complete_json=lambda *a, **k: payload)
        assert result.points_kept == 1
        assert result.points_dropped == 2

    def test_a_wholly_invented_answer_leaves_no_points_but_says_so(self):
        payload = self._payload(
            [_point(fact_ids=["NIC-1"]).model_dump() for _ in range(3)]
        )
        result = fe.explain(_dossier(), complete_json=lambda *a, **k: payload)
        assert result.explanation.points == []
        assert result.points_dropped == 3

    def test_llm_failure_is_an_error_never_an_empty_verdict(self):
        def boom(*args, **kwargs):
            raise LLMError("529 overloaded")

        with pytest.raises(fe.FindExplainError):
            fe.explain(_dossier(), complete_json=boom)

    def test_a_malformed_answer_is_an_error(self):
        with pytest.raises(fe.FindExplainError):
            fe.explain(_dossier(), complete_json=lambda *a, **k: {"neco": "jineho"})

    def test_each_side_is_capped(self):
        payload = self._payload(
            [
                _point(side="PRO", weight="DROBNY", headline_cs=f"bod {i}").model_dump()
                for i in range(9)
            ]
        )
        result = fe.explain(_dossier(), complete_json=lambda *a, **k: payload)
        assert len(result.explanation.points) == fe.MAX_POINTS_PER_SIDE

    def test_the_owners_note_reaches_the_prompt(self):
        """Vlastní úvaha je vstup, ne popisek. Kdyby se nedostala do promptu,
        nebylo by se na čem učit."""
        seen = {}

        def fake(prompt, **kwargs):
            seen["prompt"] = prompt
            return self._payload([])

        fe.explain(_dossier(), note="Všiml jsem si jich na konferenci.", complete_json=fake)
        assert "konferenci" in seen["prompt"]

    def test_gaps_are_marked_do_not_write_about_them(self):
        seen = {}

        def fake(prompt, **kwargs):
            seen["prompt"] = prompt
            return self._payload([])

        fe.explain(_dossier(), complete_json=fake)
        assert "NEPIŠ O NICH" in seen["prompt"]
        assert "MEZ-1" in seen["prompt"]


class TestInventedNumbers:
    """
    Čísla, která model napsal, ale ve spisu nejsou.

    Tohle našel první živý běh: spis o CVD Equipment říkal „tržby meziročně
    -61,8 %", model napsal „spadly o 77,8 procenta" — a udělal to dvakrát,
    včetně závěru. Citoval přitom platná `fact_id`, takže všech pět původních
    kontrol prošlo. Číslo v bodu je tvrzení jako každé jiné a musí být
    doložitelné, stejně jako doslovný citát v `claim_extraction`.
    """

    def test_a_number_that_is_not_in_the_cited_facts_drops_the_point(self):
        kept, dropped = fe.verify_points(
            [
                _point(
                    fact_ids=["FUND-1"],
                    headline_cs="Tržby spadly",
                    body_cs="Meziročně o 77,8 procenta.",
                )
            ],
            _dossier(),
        )
        assert kept == []
        assert "77,8" in dropped[0].reason_cs or "77.8" in dropped[0].reason_cs

    def test_a_number_that_is_in_the_cited_fact_survives(self):
        kept, dropped = fe.verify_points(
            [_point(fact_ids=["FUND-1"], body_cs="Meziročně o 28 %.")], _dossier()
        )
        assert len(kept) == 1, dropped

    def test_rounding_is_not_treated_as_invention(self):
        """61,8 a 61,75 je totéž číslo řečené jinak."""
        pool = fe._allowed_numbers(_dossier(), _dossier().facts)
        pool.append(61.8)
        assert fe.unsupported_numbers("pokles o 61,75 %", pool) == []

    def test_a_year_is_not_a_claim_about_the_company(self):
        assert fe.unsupported_numbers("k 30. 6. 2026 firma…", []) == []

    def test_whole_numbers_are_left_alone(self):
        """
        „tři body", „půl roku", „10 válců" — hlídat celá čísla by zahazovalo
        poctivé věty a nic by to nechytilo: vymyšlená čísla byla desetinná.
        """
        assert fe.unsupported_numbers("pozice do 10 % portfolia", []) == []

    def test_a_summary_with_an_invented_number_is_withheld_not_printed(self):
        """
        Závěr si člověk zapamatuje. Vymyšlené procento v něm je nebezpečnější
        než v jednom z osmi bodů, a zmizet beze stopy taky nesmí.
        """
        payload = {
            "one_line_cs": "Tržby spadly o 77,8 procenta.",
            "points": [],
            "own_reason_cs": "Úvaha sedí.",
            "own_reason_verdict": "DRZI",
            "lesson_cs": "Kontroluj tržby.",
        }
        result = fe.explain(_dossier(), complete_json=lambda *a, **k: payload)
        assert result.explanation.one_line_cs != "Tržby spadly o 77,8 procenta."
        assert "není" in result.explanation.one_line_cs
        assert result.withheld_cs == ["one_line_cs"]
        assert result.anything_withheld is True

    def test_a_clean_summary_is_left_alone(self):
        payload = {
            "one_line_cs": "Firma roste, ale hotovost dochází.",
            "points": [],
            "own_reason_cs": "Úvaha o růstu sedí.",
            "own_reason_verdict": "DRZI",
            "lesson_cs": "Růst bez hotovosti není teze.",
        }
        result = fe.explain(_dossier(), complete_json=lambda *a, **k: payload)
        assert result.withheld_cs == []
        assert result.explanation.one_line_cs.startswith("Firma roste")

    def test_the_prompt_states_the_number_rule(self):
        prompt = fe.build_system_prompt()
        assert "ani přepočítané" in prompt
        assert "napiš ho slovy" in prompt


class TestCost:
    """
    Vysvětlení se platí z API. Levnější model je tu obhajitelný jen proto, že
    každé jeho tvrzení projde strojovou kontrolou — chybu chytá aritmetika,
    ne čtenář.
    """

    def test_the_explainer_does_not_use_the_most_expensive_model(self):
        assert fe.EXPLAIN_MODEL != fe.llm.MODEL
        assert fe.EXPLAIN_MODEL == fe.llm.MODEL_MID

    def test_thinking_is_off_for_a_schema_bound_answer(self):
        assert fe.EXPLAIN_THINKING is False

    def test_the_model_and_thinking_actually_reach_the_call(self):
        seen = {}

        def fake(prompt, **kw):
            seen.update(kw)
            return {
                "one_line_cs": "x", "points": [],
                "own_reason_cs": "y", "own_reason_verdict": "DRZI",
                "lesson_cs": "z",
            }

        fe.explain(_dossier(), complete_json=fake)
        assert seen["model"] == fe.EXPLAIN_MODEL
        assert seen["thinking"] is False

    def test_no_model_name_is_written_outside_llm_module(self):
        """Jména modelů žijí jen v llm.py — jinak se rozejdou."""
        from pathlib import Path

        for name in ("find_explainer.py", "find_dossier.py"):
            src = Path(fe.__file__).parent.joinpath(name).read_text(encoding="utf-8")
            assert "claude-" not in src, name
