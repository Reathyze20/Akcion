"""
Nálezy: co smí endpoint udělat, a hlavně co udělat nesmí.

Dvě věci se tady hlídají nad rámec běžného CRUD:

  1. **Placené volání se nesmí stát samo.** Zakládání nálezu ani jeho čtení
     nesmí sáhnout na jazykový model. Jediná placená cesta je `/explain`,
     a i ta odmítne zaplatit podruhé za tutéž odpověď.
  2. **Kód nákupní brány se nesmí dostat na obrazovku syrový.** `GREEN`,
     `YELLOW` ani `NOT_CHEAP_ENOUGH` nejsou česká slova a majitel si výslovně
     přál, aby žádná hodnota z databáze nestála ve větě.
"""

from __future__ import annotations

import pytest

from app.services import buy_gate_cs
from app.services.buy_gate_cs import BuyGate, gate_cs


class TestGateTranslation:
    def test_every_gate_code_has_a_czech_sentence(self):
        """
        Parametrizace přes `list(BuyGate)`, aby nový kód brány shodil test,
        ne obrazovku.
        """
        for gate in BuyGate:
            sentence = gate_cs(gate)
            assert sentence
            assert sentence[0].isupper()
            assert sentence.endswith(".")

    def test_no_sentence_leaks_a_raw_database_value(self):
        forbidden = (
            "GREEN",
            "YELLOW",
            "ORANGE",
            "RED",
            "WAIT_TIME",
            "GOLD_MINE",
            "GREAT_FIND",
            "MIMO_METODIKU",
            "BUY_NOW",
        )
        for gate in BuyGate:
            sentence = gate_cs(
                gate,
                market_alert="YELLOW",
                rr_score=4.2,
                deserved=5.0,
                days_to_earnings=6,
            )
            for token in forbidden + tuple(g.value for g in BuyGate):
                assert token not in sentence, f"{gate.value} pustilo {token}"

    def test_the_semaphore_is_named_in_czech(self):
        sentence = gate_cs(BuyGate.MARKET_NOT_GREEN, market_alert="ORANGE")
        assert "oranžová" in sentence

    def test_the_price_gate_says_by_how_much(self):
        sentence = gate_cs(BuyGate.NOT_CHEAP_ENOUGH, rr_score=4.25, deserved=5.0)
        assert "4,25" in sentence  # desetinná čárka, ne tečka
        assert "5,0" in sentence

    def test_an_unevaluated_gate_is_neither_yes_nor_no(self):
        """
        Chybějící odpověď se nesmí číst jako zamítnutí ani jako souhlas —
        je to třetí stav a musí být pojmenovaný.
        """
        sentence = gate_cs(None)
        assert "nepodařilo" in sentence
        assert "není souhlas ani" in sentence

    def test_an_unknown_future_code_admits_it_rather_than_printing_it(self):
        sentence = gate_cs("NEJAKY_NOVY_KOD")
        assert "nemáme" in sentence

    def test_accepts_the_bare_string_the_database_stores(self):
        """`own_find_assessments.gate_code` i `refused_buys.failed_gate` drží
        prostý řetězec, ne enum."""
        assert gate_cs("MARKET_NOT_GREEN") == gate_cs(BuyGate.MARKET_NOT_GREEN)


class TestRouteModuleDiscipline:
    def test_the_route_never_writes_a_gate_feeding_table(self):
        """
        Kardinální pravidlo, čitelné ze zdroje. `routes/intake.py` je dodnes
        vypnutá v `main.py` právě za to, že ho porušila.
        """
        from pathlib import Path

        from app.routes import finds

        source = Path(finds.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "cylinder_intake.confirm",
            "lifecycle_intake.confirm",
            "StockLifecycleModel",
            "record_score",
            "Position(",
            "green_line =",
            "red_line =",
        ):
            assert forbidden not in source, forbidden

    def test_only_one_endpoint_reaches_the_paid_model(self):
        from pathlib import Path

        from app.routes import finds

        source = Path(finds.__file__).read_text(encoding="utf-8")
        assert source.count("find_explainer.explain(") == 1

    def test_creating_a_find_does_not_call_the_explainer(self):
        """
        Zakládání nálezu je zdarma. Kdyby volalo model, platil by majitel za
        každý ticker, který jen zapíše.
        """
        import inspect

        from app.routes import finds

        assert "find_explainer" not in inspect.getsource(finds.create_find)
        assert "find_explainer" not in inspect.getsource(finds.get_find)
        assert "find_explainer" not in inspect.getsource(finds.refresh_find)

    def test_there_is_no_delete_endpoint(self):
        """Nález se uzavírá, nemaže — historie posudků je to cenné."""
        from app.main import app

        for route in app.routes:
            if getattr(route, "path", "").startswith("/api/finds"):
                assert "DELETE" not in getattr(route, "methods", set())

    def test_the_registered_paths_are_what_the_client_expects(self):
        from app.main import app

        paths = {
            r.path for r in app.routes if getattr(r, "path", "").startswith("/api/finds")
        }
        assert paths == {
            "/api/finds",
            "/api/finds/{find_id}",
            "/api/finds/{find_id}/refresh",
            "/api/finds/{find_id}/explain",
        }


class TestSchemas:
    def test_a_two_word_note_is_refused(self):
        """
        Poznámka je vstup posudku a za rok je to jediné, co připomene, proč
        si toho člověk vůbec všiml. „ok" tu roli neplní.
        """
        from pydantic import ValidationError

        from app.routes.finds import FindCreate

        with pytest.raises(ValidationError):
            FindCreate(symbol="ABCD", note="ok")

        FindCreate(symbol="ABCD", note="Všiml jsem si jich v recenzi hardwaru.")

    def test_the_phase_is_flagged_as_a_proposal_by_default(self):
        """
        Fáze cyklu je návrh rubriky. Kdyby výchozí hodnota byla False,
        obrazovka by na to mohla zapomenout a vydávala by odhad za potvrzení.
        """
        from app.routes.finds import MethodOut

        m = MethodOut(band="NEZNAME", band_reason_cs="x", gate_reason_cs="y")
        assert m.phase_is_proposal is True
        assert m.market_alert_stale is True


class TestExplainUsesTheStoredDossier:
    """
    Vysvětlovat se smí jen to, co je zapsané.

    Endpoint `/explain` si spis skládal znovu. Vypadalo to nevinně, jenže sběr
    má výkazy ze SEC v ruce jen při zakládání nálezu — druhé sestavení stálo
    na slabších datech z Yahoo. Model pak dostal jinou sadu faktů, než jakou
    má majitel na obrazovce, a napsal číslo (-77,8 % místo -61,8 %), které
    v zobrazeném spisu nebylo. Kontrola citací ho pustila, protože ve SVÉM
    spisu ho našel.
    """

    def test_the_route_reads_the_stored_dossier_instead_of_rebuilding(self):
        import inspect

        from app.routes import finds

        source = inspect.getsource(finds.explain_find)
        assert "from_payload(row.dossier)" in source
        assert "find_dossier.build(" not in source

    def test_a_stored_dossier_round_trips(self):
        from datetime import datetime, timezone

        from app.routes.finds import _dossier_out
        from app.services import find_dossier as fd

        original = fd.Dossier(
            ticker="ABCD",
            symbol="ABCD",
            company_name="Firma",
            as_of=datetime(2026, 8, 24, tzinfo=timezone.utc),
            price=4.2,
            price_currency="USD",
            price_is_stale=False,
            facts=(
                fd.Fact(
                    id="FUND-1",
                    layer=fd.LAYER_FUNDAMENTY,
                    text_cs="Tržby meziročně pokles o 61,8 %.",
                    source="SEC XBRL",
                    direction=fd.DIR_PROTI,
                ),
            ),
            gaps=(fd.Gap(id="MEZ-1", layer=fd.LAYER_METODIKA, text_cs="Válce neznáme."),),
            method=fd.MethodReading(
                band="NEZNAME", band_reason_cs="Válce neznáme", cylinders_proposed=6
            ),
        )

        payload = _dossier_out(original).model_dump(mode="json")
        restored = fd.from_payload(payload)

        assert restored.fact_ids() == original.fact_ids()
        assert restored.fact("FUND-1").direction == fd.DIR_PROTI
        assert restored.fact("FUND-1").text_cs == original.fact("FUND-1").text_cs
        assert restored.gaps[0].id == "MEZ-1"
        assert restored.method.cylinders_proposed == 6
        assert restored.price == 4.2

    def test_a_restored_dossier_still_catches_an_invented_number(self):
        """Ověření musí po načtení z databáze fungovat stejně jako čerstvé."""
        from datetime import datetime, timezone

        from app.routes.finds import _dossier_out
        from app.services import find_dossier as fd
        from app.services import find_explainer as fe

        d = fd.Dossier(
            ticker="ABCD", symbol="ABCD", company_name=None,
            as_of=datetime(2026, 8, 24, tzinfo=timezone.utc),
            price=4.2, price_currency="USD", price_is_stale=False,
            facts=(
                fd.Fact(id="FUND-1", layer=fd.LAYER_FUNDAMENTY,
                        text_cs="Tržby meziročně pokles o 61,8 %.",
                        source="SEC XBRL", direction=fd.DIR_PROTI),
            ),
            gaps=(),
            method=fd.MethodReading(band="NEZNAME", band_reason_cs="x"),
        )
        restored = fd.from_payload(_dossier_out(d).model_dump(mode="json"))

        point = fe.ExplainedPoint(
            side="PROTI",
            headline_cs="Tržby spadly o 77,8 procenta.",
            body_cs="Propad je hluboký.",
            fact_ids=["FUND-1"],
            canon_ref="§3",
            check_yourself_cs="Ve výkazu.",
            weight="ROZHODUJICI",
        )
        kept, dropped = fe.verify_points([point], restored)
        assert kept == []
        assert dropped
