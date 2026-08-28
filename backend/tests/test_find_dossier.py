"""
Spis k vlastnímu nálezu: co v něm smí být a co se v něm musí jmenovat jako mezera.

Tři věci, které tady zkoušené být musí, protože v téhle aplikaci každá z nich
už jednou selhala:

  1. Nepřítomnost dat se nesmí stát faktem. Firma, o které nikdo nic neřekl,
     dá mezery, ne mlčení a ne dopočítané číslo.
  2. Nepotvrzený návrh válců nesmí vyrobit obchodovatelné pásmo.
  3. Skládání spisu nesmí sáhnout na jedinou tabulku, která krmí nákupní bránu.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.models.analysis import AnalystTranscript, TickerMention
from app.models.base import Base
from app.models.analyst_roster import RosterEntry
from app.models.breakout import BreakoutWatchChange, BreakoutWatchEntry
from app.models.gomes import StockLifecycleModel
from app.models.portfolio import MarketStatus, MarketStatusEnum
from app.models.earnings import EarningsDate
from app.models.sec import SecCoverage
from app.models.sec_finding import SecFinding
from app.models.stock import Stock
from app.services import find_dossier as fd

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
RATES = {"USD": 25.0, "CZK": 1.0, "CAD": 18.0}


def fx(currency: str) -> float:
    return RATES[currency.upper()]


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


GATE_TABLES = ("stock_lifecycle", "stocks")


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Stock.__table__,
            StockLifecycleModel.__table__,
            AnalystTranscript.__table__,
            TickerMention.__table__,
            BreakoutWatchEntry.__table__,
            BreakoutWatchChange.__table__,
            RosterEntry.__table__,
            SecCoverage.__table__,
            SecFinding.__table__,
            MarketStatus.__table__,
            EarningsDate.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(
        MarketStatus(id=1, status=MarketStatusEnum.GREEN, last_updated=NOW)
    )
    session.commit()
    yield session
    session.close()


def add_transcript(db, said: date) -> int:
    """
    Přepis vložený syrovým SQL.

    `detected_tickers` je postgresovské pole a SQLite do něj neumí navázat
    pythonovský seznam — a sloupec má výchozí hodnotu, takže ho nejde obejít
    ani předáním None (sloupec je NOT NULL a má výchozí hodnotu). Testy o
    detekované tickery nic neopírají, tak se vloží prázdné pole textem.
    """
    db.execute(
        sa.text(
            "INSERT INTO analyst_transcripts "
            "(source_name, raw_text, detected_tickers, date, is_processed, "
            " created_at, updated_at) "
            "VALUES ('Mark Gomes', 'x', '[]', :said, 1, :now, :now)"
        ),
        {"said": said.isoformat(), "now": NOW.replace(tzinfo=None).isoformat()},
    )
    return int(db.execute(sa.text("SELECT MAX(id) FROM analyst_transcripts")).scalar())


def add_gomes_claim(db, ticker, *, said: date, summary: str, quote: str,
                    action="BUY", sentiment="BULLISH"):
    db.add(
        TickerMention(
            ticker=ticker,
            transcript_id=add_transcript(db, said),
            mention_date=said,
            sentiment=sentiment,
            action_mentioned=action,
            context_snippet=quote,
            key_points=[summary],
            # Přesně jak to zapisuje backfill. Viz test níž.
            is_current=False,
        )
    )
    db.commit()


def add_lines(db, ticker, green, red, currency="USD"):
    db.add(
        Stock(
            ticker=ticker,
            company_name="Firma",
            source_key="GOMES",
            green_line=green,
            red_line=red,
            line_currency=currency,
            is_latest=True,
        )
    )
    db.commit()


def build(db, ticker="ABCD", **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("fx_rate_to_czk", fx)
    return fd.build(db, ticker, **kw)


class TestAbsenceIsNamed:
    def test_a_company_nobody_knows_yields_gaps_not_silence(self, db):
        d = build(db, "ZZZZ")
        assert d.facts == ()
        assert len(d.gaps) >= 4
        joined = " ".join(g.text_cs for g in d.gaps)
        assert "Mark Gomes" in joined
        assert "Breakout Investors" in joined

    def test_missing_gomes_names_how_much_we_have_read(self, db):
        """
        „Nemluvil o ní" a „nemáme co číst" jsou dvě různá tvrzení. Když se
        splynou, majitel jde hledat data, která už má — nebo si myslí, že
        ticho je stanovisko.
        """
        add_gomes_claim(
            db, "JINA", said=date(2026, 8, 1), summary="x", quote="y"
        )
        gap = next(g for g in build(db, "ZZZZ").gaps if g.layer == fd.LAYER_GOMES)
        assert "1" in gap.text_cs
        assert "přepis" in gap.text_cs

    def test_no_lines_is_outside_the_method_not_a_bad_company(self, db):
        d = build(db, "ZZZZ")
        assert d.method.band in ("MIMO_METODIKU", "NEZNAME")
        assert d.method.rr_score is None
        assert d.method.buy_below is None
        assert d.method.sell_above is None
        gap = next(g for g in d.gaps if "čáru" in g.text_cs)
        assert "mimo metodiku" in gap.text_cs

    def test_each_sec_absence_gets_its_own_sentence(self, db):
        """Čtyři různé důvody, a jen tři z nich mluví o firmě."""
        seen = set()
        for status in (
            "NOT_AN_SEC_FILER",
            "FOREIGN_PRIVATE_ISSUER",
            "NOT_A_TICKER",
            "LOOKUP_FAILED",
        ):
            db.query(SecCoverage).delete()
            db.add(SecCoverage(ticker="ABCD", status=status))
            db.commit()
            gap = next(
                g for g in build(db).gaps if g.layer == fd.LAYER_FUNDAMENTY
            )
            seen.add(gap.text_cs)
        assert len(seen) == 4


class TestGomesLayer:
    def test_backfilled_claims_are_read_even_though_is_current_is_false(self, db):
        """
        Past, která tiše vyprazdňuje dvě jiná místa v aplikaci.

        `scripts/backfill_transcripts.py` ukládá skutečné výroky s doslovným
        citátem jako `is_current=False`, kdežto `routes/gomes.py` zapisuje
        `is_current=True` na holé nálezy tickeru v textu. Filtr na `is_current`
        by tedy vrátil prázdné řádky a tvrzení schoval.
        """
        add_gomes_claim(
            db,
            "ABCD",
            said=date(2026, 8, 10),
            summary="Podepsali největší zakázku v historii.",
            quote="biggest contract they have ever signed",
        )
        facts = [f for f in build(db).facts if f.layer == fd.LAYER_GOMES]
        assert len(facts) == 1
        assert "největší zakázku" in facts[0].text_cs
        assert facts[0].quote == "biggest contract they have ever signed"

    def test_a_bare_mention_carries_nothing_and_becomes_no_fact(self, db):
        """
        Řádek bez citátu i bez shrnutí nenese nic, co by kdo řekl. Udělat
        z něj fakt by bylo vymýšlení s odkazem na zdroj.
        """
        db.add(
            TickerMention(
                ticker="ABCD",
                transcript_id=add_transcript(db, date(2026, 8, 10)),
                mention_date=date(2026, 8, 10),
                sentiment="NEUTRAL",
                is_current=True,
            )
        )
        db.commit()
        assert [f for f in build(db).facts if f.layer == fd.LAYER_GOMES] == []

    def test_an_old_claim_says_how_old_it_is(self, db):
        add_gomes_claim(
            db, "ABCD", said=date(2025, 1, 5), summary="Staré tvrzení.", quote="q"
        )
        fact = next(f for f in build(db).facts if f.layer == fd.LAYER_GOMES)
        assert "dny" in fact.text_cs
        assert "váha" in fact.text_cs

    def test_a_bearish_claim_points_against(self, db):
        add_gomes_claim(
            db,
            "ABCD",
            said=date(2026, 8, 10),
            summary="Ztratili zakázku.",
            quote="q",
            action="SELL",
            sentiment="BEARISH",
        )
        fact = next(f for f in build(db).facts if f.layer == fd.LAYER_GOMES)
        assert fact.direction == fd.DIR_PROTI


class TestBreakoutIsShownNotObeyed:
    def test_every_breakout_fact_is_neutral(self, db):
        """
        Seškrábaný počet podpisů bez jmenovaného autora není stanovisko.
        Kdyby nesl směr, protlačil by bod na stranu „pro" silou davu, který
        se pod nic nepodepsal.
        """
        db.add(
            BreakoutWatchEntry(
                symbol="ABCD",
                company_name="Firma",
                endorsements=12,
                upside_ratio=0.62,
                price_at_read=4.0,
                implied_target=6.48,
            )
        )
        db.commit()
        facts = [f for f in build(db).facts if f.layer == fd.LAYER_BREAKOUT]
        # Kolik jich je, se mění (přibyla věta o jejich cíli a o změnách na
        # seznamu). Co se měnit nesmí: ani jedna z nich nenese směr.
        assert facts, "vrstva nevydala nic, i když firma na watchlistu je"
        assert all(f.direction == fd.DIR_NEUTRAL for f in facts)
        assert any("nerozhoduje" in f.text_cs for f in facts)

    def test_their_target_is_reported_without_judging_whether_it_was_right(self, db):
        """
        Jejich cíl je jediná padatelná předpověď, kterou od kohokoli máme —
        a zároveň je sledování staré dny. Věta proto smí říct, odkud a kam,
        ale nesmí říct, jestli jim to vychází.
        """
        db.add(
            BreakoutWatchEntry(
                symbol="ABCD",
                company_name="Firma",
                endorsements=3,
                upside_ratio=0.5,
                price_at_read=4.0,
                implied_target=6.0,
                price_at_first_seen=4.0,
                target_at_first_seen=6.0,
            )
        )
        db.commit()
        texts = " ".join(
            f.text_cs for f in build(db).facts if f.layer == fd.LAYER_BREAKOUT
        )
        assert "padatelná" in texts
        assert "je zatím brzy" in texts

    def test_a_named_analyst_is_quoted_by_name_not_folded_into_a_count(self, db):
        """
        Jediná část Breakoutu, pod kterou je někdo podepsaný. Spis ji do
        25. 8. 2026 nečetl vůbec a ukazoval místo ní počet hlasů.
        """
        db.add(
            BreakoutWatchEntry(symbol="ABCD", company_name="Firma", endorsements=2,
                               upside_ratio=0.5, price_at_read=4.0, implied_target=6.0)
        )
        db.add(RosterEntry(name_key="robert mock", display_name="Robert Mock",
                           source_key="BREAKOUT_INVESTORS", active=True))
        tid = add_transcript(db, date(2026, 8, 24))
        db.add(
            TickerMention(
                ticker="ABCD", transcript_id=tid, mention_date=date(2026, 8, 24),
                sentiment="NEUTRAL", speaker="Robert Mock",
                source_key="BREAKOUT_INVESTORS", claim_type="FACT",
                context_snippet="Bliss will be produced using outsourced manufacturing",
            )
        )
        db.commit()
        d = build(db)
        texts = [f.text_cs for f in d.facts if f.layer == fd.LAYER_BREAKOUT]
        assert any("Robert Mock" in t and "outsourced" in t for t in texts)
        assert d.signals.bi_named_claims == 1

    def test_a_claim_without_a_verdict_or_target_still_reaches_the_dossier(self, db):
        """
        Devět z jedenácti tvrzení Roberta Mocka o DFSC nemá verdikt ani cíl.
        Pro stavbu pásma je to šum a `load_analyst_words` je zahazuje správně;
        pro spis je to to jediné cenné, co od Breakoutu máme.
        """
        db.add(
            BreakoutWatchEntry(symbol="ABCD", company_name="Firma", endorsements=1,
                               upside_ratio=0.5, price_at_read=4.0, implied_target=6.0)
        )
        db.add(RosterEntry(name_key="robert mock", display_name="Robert Mock",
                           source_key="BREAKOUT_INVESTORS", active=True))
        tid = add_transcript(db, date(2026, 8, 24))
        db.add(
            TickerMention(
                ticker="ABCD", transcript_id=tid, mention_date=date(2026, 8, 24),
                sentiment="NEUTRAL", speaker="Robert Mock",
                action_mentioned=None, price_target=None,
                context_snippet="General Dynamics owns the major contract",
            )
        )
        db.commit()
        assert build(db).signals.bi_named_claims == 1

    def test_their_endorsements_never_reach_the_score(self, db):
        """
        Signály z BI existují kvůli SHODĚ dvou zdrojů, ne kvůli jejich názoru.
        Samotný počet podpisů se nesmí nikam propsat jako stanovisko.
        """
        db.add(
            BreakoutWatchEntry(
                symbol="ABCD", company_name="Firma", endorsements=9, upside_ratio=1.0,
                price_at_read=4.0, implied_target=8.0,
            )
        )
        db.commit()
        signals = build(db).signals
        assert signals.bi_on_watchlist is True
        assert signals.bi_endorsements == 9
        # Žádný Gomes → žádná shoda, i při devíti podpisech.
        assert signals.second_source_agrees is False


class TestBandNeedsConfirmedCylinders:
    def test_an_unconfirmed_proposal_never_produces_a_tradeable_band(self, db):
        """
        Nejdůležitější test celého souboru.

        Rubrika smí navrhnout jakékoli číslo; dokud ho člověk nepotvrdí,
        pásmo zůstává neznámé. Kdyby návrh vyráběl pásmo, mohl by neschválený
        odhad odemknout nákup — patro nad tou vadou, kvůli které vzniklo celé
        `cylinder_intake`.
        """
        add_lines(db, "ABCD", green=2.0, red=8.0)
        db.add(
            StockLifecycleModel(
                ticker="ABCD",
                phase="GREAT_FIND",
                cylinders_count=7,
                cylinders_confirmed_at=None,  # návrh, ne potvrzení
                detected_at=NOW,
                valid_until=None,
            )
        )
        db.commit()
        method = build(db).method
        assert method.cylinders_confirmed is None
        assert method.band in ("NEZNAME", "MIMO_METODIKU")
        assert method.deserved is None

    def test_a_confirmed_count_does_produce_a_band(self, db):
        add_lines(db, "ABCD", green=2.0, red=8.0)
        db.add(
            StockLifecycleModel(
                ticker="ABCD",
                phase="GREAT_FIND",
                cylinders_count=7,
                cylinders_confirmed_at=NOW - timedelta(days=1),
                cylinders_confirmed_by="Tomas",
                detected_at=NOW,
                valid_until=None,
            )
        )
        db.commit()
        # Kurz do spisu nese Yahoo cache, kterou tenhle in-memory test nemá,
        # takže pásmo zůstane bez ceny — ale zasloužené skóre se spočítat musí.
        assert build(db).method.deserved == 3.0


class TestNothingThatFeedsTheGateIsWritten:
    def _snapshot(self, db):
        return {
            t: [
                tuple(str(v) for v in row)
                for row in db.execute(sa.text(f"SELECT * FROM {t}")).fetchall()
            ]
            for t in GATE_TABLES
        }

    def test_building_a_dossier_changes_no_gate_table(self, db):
        """
        Kardinální pravidlo aplikace, zkoušené na datech, ne na dobrém úmyslu.

        Válce, fáze a cenové čáry jsou vstupy nákupní brány. Měnit je smí
        výhradně `cylinder_intake.confirm()` a `lifecycle_intake.confirm()`
        po lidském potvrzení — `routes/intake.py` je dodnes vypnutá právě za
        to, že tohle pravidlo porušila.
        """
        add_lines(db, "ABCD", green=2.0, red=8.0)
        add_gomes_claim(
            db, "ABCD", said=date(2026, 8, 10), summary="Roste.", quote="q"
        )
        db.add(
            StockLifecycleModel(
                ticker="ABCD",
                phase="GREAT_FIND",
                cylinders_count=6,
                cylinders_confirmed_at=NOW,
                cylinders_confirmed_by="Tomas",
                detected_at=NOW,
                valid_until=None,
            )
        )
        db.commit()

        before = self._snapshot(db)
        for _ in range(3):
            build(db, note="Líbí se mi to.")
        db.rollback()
        assert self._snapshot(db) == before

    def test_the_module_never_names_a_gate_writing_call(self):
        """
        Textová pojistka po vzoru `test_llm.py`: zákaz musí být čitelný ze
        zdroje, ne jen z chování jedné testovací cesty.
        """
        from pathlib import Path

        source = (
            Path(fd.__file__).read_text(encoding="utf-8").split('"""', 2)[2]
        )
        for forbidden in (
            "cylinder_intake.confirm",
            "lifecycle_intake.confirm",
            "record_score",
            "db.add(",
            "db.commit(",
        ):
            assert forbidden not in source, forbidden


class TestConditionalCylinderSentence:
    def test_it_is_silent_when_it_would_add_nothing(self, db):
        """Věta „kdyby válce byly 6, pásmo by bylo stejné" je šum."""
        d = build(db, "ZZZZ")
        assert d.method.if_cylinders_cs is None

    def test_it_never_claims_the_number_is_confirmed(self, db):
        add_lines(db, "ABCD", green=2.0, red=8.0)
        db.commit()
        sentence = build(db).method.if_cylinders_cs
        if sentence is not None:
            assert "nepotvrzeno" in sentence


class TestOwnersNote:
    def test_the_note_becomes_a_fact_the_explainer_can_cite(self, db):
        d = build(db, "ABCD", note="Všiml jsem si jich v recenzi.")
        fact = next(f for f in d.facts if f.layer == fd.LAYER_VLASTNI)
        assert "recenzi" in fact.text_cs
        assert fact.id in d.fact_ids()

    def test_no_note_means_no_fabricated_reason(self, db):
        d = build(db, "ABCD")
        assert [f for f in d.facts if f.layer == fd.LAYER_VLASTNI] == []


class TestIdentifiers:
    def test_fact_ids_are_unique(self, db):
        add_gomes_claim(
            db, "ABCD", said=date(2026, 8, 10), summary="a", quote="q1"
        )
        add_gomes_claim(
            db, "ABCD", said=date(2026, 7, 10), summary="b", quote="q2"
        )
        d = build(db, note="poznámka")
        ids = [f.id for f in d.facts]
        assert len(ids) == len(set(ids))

    def test_no_fact_ever_wears_a_gap_prefix(self, db):
        """
        Na tomhle stojí kontrola ve vysvětlovači: bod citující `MEZ-…` se
        zahazuje jako uvažování z nepřítomnosti dat.
        """
        add_gomes_claim(
            db, "ABCD", said=date(2026, 8, 10), summary="a", quote="q"
        )
        d = build(db, note="poznámka")
        assert all(not f.id.startswith(f"{fd.GAP_PREFIX}-") for f in d.facts)
        assert all(g.id.startswith(f"{fd.GAP_PREFIX}-") for g in d.gaps)


class TestConflictingReadings:
    """
    Dvě rubriky počítají meziroční růst tržeb z jiného období a obě o něm píšou
    stejnou větou. U CVD Equipment stál v jednom spisu vedle sebe pokles
    61,8 % (čtvrtletí proti čtvrtletí z výkazů) a 77,8 % (posledních dvanáct
    měsíců ze souhrnu). Model si vybral druhé a napsal ho do závěru — což
    vypadalo jako vymyšlené číslo, ale bylo to naše číslo, jen to druhé.

    Spor se pojmenuje. Vybrat jedno a druhé zahodit by znamenalo rozhodnout
    za majitele, který zdroj platí.
    """

    def test_two_incompatible_revenue_readings_become_a_named_gap(self):
        facts = [
            fd.Fact(
                id="METOD-1",
                layer=fd.LAYER_METODIKA,
                text_cs="Tržby meziročně silný pokles o 61,8 % (čtvrtletí do 30. 6. 2026)",
                source="rubrika válců (xbrl)",
            ),
            fd.Fact(
                id="METOD-7",
                layer=fd.LAYER_METODIKA,
                text_cs="tržby meziročně -77,8 % — trakce zatím není",
                source="rubrika fáze (finnhub)",
            ),
        ]
        conflict = fd._revenue_conflict(facts)
        assert conflict is not None
        assert "-61,8" in conflict and "-77,8" in conflict
        assert "neshodnou" in conflict

    def test_a_word_can_carry_the_minus_sign(self):
        """
        „pokles o 61,8 %" je záporné číslo napsané kladně. Bez toho by rozdíl
        vyšel na 139 bodů a věta by tvrdila, že jedno čtení roste.
        """
        readings = fd._revenue_readings(
            [
                fd.Fact(
                    id="X",
                    layer=fd.LAYER_METODIKA,
                    text_cs="Tržby meziročně silný pokles o 61,8 %",
                    source="s",
                )
            ]
        )
        assert readings[0][0] == -61.8

    def test_agreeing_readings_produce_no_noise(self):
        facts = [
            fd.Fact(id="A", layer=fd.LAYER_METODIKA,
                    text_cs="Tržby meziročně pokles o 61,8 %", source="a"),
            fd.Fact(id="B", layer=fd.LAYER_METODIKA,
                    text_cs="tržby meziročně -63,0 % — trakce zatím není", source="b"),
        ]
        assert fd._revenue_conflict(facts) is None

    def test_one_reading_is_not_a_conflict(self):
        facts = [
            fd.Fact(id="A", layer=fd.LAYER_METODIKA,
                    text_cs="Tržby meziročně pokles o 61,8 %", source="a"),
        ]
        assert fd._revenue_conflict(facts) is None


class TestATypoIsNamedAsATypo:
    """
    Neúspěšné stažení po sobě nechá řádek v cache kurzů. „Řádek existuje" tedy
    neznamená „firma existuje" — a spis o překlepu tvrdil, že jde o zahraniční
    listing, který se hlásí jinde. To je věta o rejstříku vydávaná za větu
    o firmě, tedy odpověď na otázku, kterou nikdo nepoložil.
    """

    def test_an_empty_cache_row_is_not_a_company(self):
        assert fd._has_market_data(None) is False
        assert fd._has_market_data({"current_price": None, "company_name": None}) is False
        assert fd._has_market_data({"current_price": 4.2}) is True
        assert fd._has_market_data({"company_name": "Firma"}) is True

    def test_an_unknown_symbol_is_told_it_may_be_a_typo(self, db):
        db.add(SecCoverage(ticker="ZZZZ", status="NOT_AN_SEC_FILER"))
        db.commit()
        gaps = [g.text_cs for g in build(db, "ZZZZ").gaps]
        assert any("překlep" in g for g in gaps)
        assert not any("zahraniční listing" in g for g in gaps)

    def test_a_traded_company_outside_edgar_keeps_the_foreign_listing_sentence(self, db):
        """
        GSI.V opravdu je zahraniční listing a tam ta věta platí. Rozhoduje
        jediná věc: jestli se s papírem obchoduje.
        """
        facts, gaps, _ = fd._fundamentals_layer(
            db,
            ("ABCD",),
            {"current_price": 1.79, "company_name": "Gatekeeper"},
            None,
            None,
            fd._Ids(),
        )
        db.add(SecCoverage(ticker="ABCD", status="NOT_AN_SEC_FILER"))
        db.commit()
        _, gaps, _bits = fd._fundamentals_layer(
            db,
            ("ABCD",),
            {"current_price": 1.79, "company_name": "Gatekeeper"},
            None,
            None,
            fd._Ids(),
        )
        assert any("zahraniční listing" in g.text_cs for g in gaps)
        assert not any("překlep" in g.text_cs for g in gaps)


class TestStaleFilings:
    """
    Tři roky staré číslo není mezera a nevypadá jako chyba — a právě proto je
    nebezpečnější než mezera.

    AST SpaceMobile přestala tagovat tržby pod položkou, kterou aplikace čte.
    Série uvízla na čtvrtletí do 31. 3. 2023 a spis pak s naprostou jistotou
    tvrdil „tržby meziročně 0,0 % — ještě to nikam nevystřelilo" u firmy, které
    mezitím tržby vyrostly na 115 mil. za dvanáct měsíců. Rubrika fáze to číslo
    použila k zařazení.
    """

    class _Point:
        def __init__(self, end):
            self.end = end

    class _Series:
        def __init__(self, end):
            self.latest_quarter = TestStaleFilings._Point(end)

    class _Fundamentals:
        def __init__(self, end):
            self._s = TestStaleFilings._Series(end)

        def get(self, key):
            return self._s if key == "revenue" else None

    def test_a_three_year_old_quarter_is_flagged(self):
        stale = fd._filing_staleness(
            self._Fundamentals(date(2023, 3, 31)), date(2026, 8, 24)
        )
        assert stale is not None
        end, age = stale
        assert end == date(2023, 3, 31)
        assert age > 1000

    def test_a_fresh_quarter_is_not_flagged(self):
        assert fd._filing_staleness(
            self._Fundamentals(date(2026, 6, 30)), date(2026, 8, 24)
        ) is None

    def test_one_missed_quarter_is_still_acceptable(self):
        """Firma podává čtvrtletně; jedno zpoždění není důkaz, že série uvízla."""
        assert fd._filing_staleness(
            self._Fundamentals(date(2026, 3, 31)), date(2026, 8, 24)
        ) is None

    def test_missing_fundamentals_is_not_staleness(self):
        assert fd._filing_staleness(None, date(2026, 8, 24)) is None

    def test_the_gap_says_how_old_and_warns_against_judging(self, db):
        _, gaps, _bits = fd._fundamentals_layer(
            db,
            ("ABCD",),
            {"current_price": 4.2, "company_name": "Firma"},
            self._Fundamentals(date(2023, 3, 31)),
            None,
            fd._Ids(),
            date(2026, 8, 24),
        )
        stale_gap = next(g for g in gaps if "měsíců" in g.text_cs)
        assert "2023" in stale_gap.text_cs
        assert "nepopisují dnešek" in stale_gap.text_cs
        assert stale_gap.fixable_cs == "Doplnit data"


class TestSignalsSurviveRealData:
    """
    Signály musí projít i tehdy, když Yahoo a Finnhub něco vrátí.

    Tahle třída existuje kvůli konkrétní vadě: `_fundamentals_layer` měla
    lokální `bits = []` pro kousky věty („tržní kapitalizace X mil., …") a nový
    akumulátor signálů se jmenoval stejně. Ta pozdější proměnná ho uvnitř
    funkce přepsala, takže funkce vracela seznam řetězců místo slovníku a
    `build()` padal na `dict.update()`. Prošlo to celou zelenou sadou, protože
    ve fixtures nebylo v Yahoo ani ve Finnhubu nic — spadlo to na prvním
    tickeru, který měl něco v cache.
    """

    class _Finnhub:
        has_anything = True
        revenue_yoy_pct = 12.5
        gross_margin_pct = 40.0
        net_margin_pct = 5.0
        is_profitable = True

    def test_the_third_return_value_is_a_mapping_not_the_sentence_pieces(self, db):
        _facts, _gaps, bits = fd._fundamentals_layer(
            db,
            ("ABCD",),
            {
                "current_price": 4.2,
                "company_name": "Firma",
                "market_cap": 9_100_000,
                "total_cash": 6_700_000,
                "total_debt": 400_000,
            },
            None,
            self._Finnhub(),
            fd._Ids(),
            date(2026, 8, 24),
        )
        assert isinstance(bits, dict), "vrstva vrátila kousky věty místo signálů"
        assert "filings_fresh" in bits

    def test_the_sentences_themselves_still_come_out(self, db):
        facts, _gaps, _bits = fd._fundamentals_layer(
            db,
            ("ABCD",),
            {"current_price": 4.2, "company_name": "Firma", "market_cap": 9_100_000},
            None,
            self._Finnhub(),
            fd._Ids(),
            date(2026, 8, 24),
        )
        texts = " ".join(f.text_cs for f in facts)
        assert "Finnhub:" in texts
        assert "tržní kapitalizace" in texts


class TestAPriceTargetMustBeInItsOwnQuote:
    """
    `price_target` plní extraktor a bere čísla z okolního textu. Změřeno na
    všech 61 cílech v databázi: **27 se ve vlastním citátu nevyskytuje.**
    U AEHR jsou za pět měsíců cíle 4,00 / 42,00 / 112,00 / 68,00 / 110,00 /
    55,00 při kurzu kolem 101 — a v citátech u nich žádný cíl není.

    Vytisknout takové číslo jako Markův fakt je vymyšlené číslo s odkazem na
    zdroj. Táž kázeň jako `find_explainer.unsupported_numbers()`, jen o vrstvu
    níž: tam se hlídá model, tady extraktor.
    """

    class _M:
        def __init__(self, target, snippet=None, points=None):
            self.price_target = target
            self.context_snippet = snippet
            self.key_points = points

    def test_a_target_absent_from_the_quote_is_dropped(self):
        assert fd._quoted_target(
            self._M(42.0, "this press release is major validation")
        ) is None

    def test_a_target_present_in_the_quote_survives(self):
        assert fd._quoted_target(
            self._M(36.0, "I think RDCM is worth 36.00 on that math")
        ) == 36.0

    def test_a_comma_decimal_counts_as_the_same_number(self):
        assert fd._quoted_target(self._M(12.55, "cíl je 12,55 dolaru")) == 12.55

    def test_key_points_count_as_the_quote_too(self):
        assert fd._quoted_target(self._M(7.5, None, ["target of 7.5 by 2027"])) == 7.5

    def test_a_near_miss_is_not_a_match(self):
        """12,6 není 12,55. Volnější tolerance by pustila rok 2042 jako cíl 42."""
        assert fd._quoted_target(self._M(12.55, "kolem 12,6")) is None

    def test_no_target_at_all_stays_none(self):
        assert fd._quoted_target(self._M(None, "žádné číslo")) is None

    def test_the_sentence_never_calls_the_number_a_target(self, db):
        """
        Že v citátu číslo padlo, ještě neznamená, že je to cílová cena. Věta
        smí říct jen to, co jde obhájit.
        """
        tid = add_transcript(db, date(2026, 8, 1))
        db.add(
            TickerMention(
                ticker="ABCD",
                transcript_id=tid,
                mention_date=date(2026, 8, 1),
                sentiment="BULLISH",
                context_snippet="I think this is worth 36.00 eventually",
                price_target=36.0,
            )
        )
        db.commit()
        texts = " ".join(f.text_cs for f in build(db).facts if f.layer == fd.LAYER_GOMES)
        assert "36,00" in texts
        assert "cíl" not in texts.lower()


class TestCadenceCountsEpisodesNotRows:
    def test_two_mentions_in_one_transcript_are_one_episode(self, db):
        """
        WhatsApp import z 24. 8. dal jedné firmě jedenáct zmínek z jediného
        zdroje. Jako jedenáct epizod by to vypadalo, že o ní mluví každý týden.
        """
        tid = add_transcript(db, date(2026, 8, 1))
        for snippet in ("první věta", "druhá věta"):
            db.add(
                TickerMention(
                    ticker="ABCD",
                    transcript_id=tid,
                    mention_date=date(2026, 8, 1),
                    sentiment="BULLISH",
                    context_snippet=snippet,
                )
            )
        db.commit()
        assert build(db).signals.gomes_episodes_total == 1

    def test_an_old_episode_does_not_count_as_recent(self, db):
        old = add_transcript(db, date(2025, 1, 1))
        db.add(
            TickerMention(
                ticker="ABCD",
                transcript_id=old,
                mention_date=date(2025, 1, 1),
                sentiment="BULLISH",
                context_snippet="dávno",
            )
        )
        db.commit()
        signals = build(db).signals
        assert signals.gomes_episodes_total == 1
        assert signals.gomes_episodes_recent == 0
