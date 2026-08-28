"""
The FIT layer in find_dossier.py — whether a candidate's chart shape
resembles Mark's own entries, read from `gomes_fit_cache`.

Three things this must get right:
  1. No cache row -> a Gap pointing at enrich(), never silence.
  2. An outlier feature becomes a Fact with neutral direction and no
     BUY/AVOID-shaped wording — gomes_fit.py's own no-verdict rule.
  3. build() never touches the network: `_gomes_fit_layer` reads the cache
     table only, same contract as the fundamentals layer's SEC lookup.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.gomes_fit_cache import GomesFitCache
from app.services import find_dossier as fd


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[GomesFitCache.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def layer(db, symbols=("ABCD",)):
    return fd._gomes_fit_layer(db, symbols, fd._Ids())


class TestNoCacheIsAGapNotSilence:
    def test_missing_row_yields_a_gap(self, db):
        facts, gaps = layer(db)
        assert facts == []
        assert len(gaps) == 1
        assert gaps[0].layer == fd.LAYER_FIT
        assert gaps[0].fixable_cs == "Doplnit data"


class TestOutlierFeaturesBecomeFacts:
    def test_a_mimo_feature_produces_a_neutral_fact(self, db):
        db.add(
            GomesFitCache(
                ticker="ABCD",
                as_of=date(2026, 8, 24),
                computed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
                summary_cs="1 mimo, 0 na okraji, 2 typické.",
                fits_json=[
                    {"name": "pe_ratio", "label_cs": "P/E poměr", "value": 120.0,
                     "bucket": "MIMO", "below": 39, "of": 40},
                    {"name": "rsi", "label_cs": "RSI", "value": 55.0,
                     "bucket": "TYPICKE", "below": 20, "of": 40},
                ],
                uncomputable_json=[],
            )
        )
        db.commit()

        facts, gaps = layer(db)
        assert gaps == []
        assert len(facts) == 1
        f = facts[0]
        assert f.layer == fd.LAYER_FIT
        assert f.direction == fd.DIR_NEUTRAL
        assert "P/E poměr" in f.text_cs
        assert "mimo rozsah" in f.text_cs
        # The module's own rule: no verdict word anywhere in the sentence.
        for verdict_word in ("kup", "prod", "levn", "drah", "podhodnocen", "nadhodnocen"):
            assert verdict_word not in f.text_cs.lower()

    def test_all_typical_produces_one_summary_fact_not_per_feature(self, db):
        db.add(
            GomesFitCache(
                ticker="ABCD",
                as_of=date(2026, 8, 24),
                computed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
                summary_cs="0 mimo, 0 na okraji, 2 typické.",
                fits_json=[
                    {"name": "pe_ratio", "label_cs": "P/E poměr", "value": 10.0,
                     "bucket": "TYPICKE", "below": 20, "of": 40},
                    {"name": "rsi", "label_cs": "RSI", "value": 55.0,
                     "bucket": "TYPICKE", "below": 20, "of": 40},
                ],
                uncomputable_json=[],
            )
        )
        db.commit()

        facts, gaps = layer(db)
        assert len(facts) == 1
        assert "typickém rozsahu" in facts[0].text_cs

    def test_uncomputable_features_become_a_gap_alongside_the_facts(self, db):
        db.add(
            GomesFitCache(
                ticker="ABCD",
                as_of=date(2026, 8, 24),
                computed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
                summary_cs="0 mimo, 0 na okraji, 1 typické. Nešlo spočítat: objem.",
                fits_json=[
                    {"name": "rsi", "label_cs": "RSI", "value": 55.0,
                     "bucket": "TYPICKE", "below": 20, "of": 40},
                ],
                uncomputable_json=["Průměrný denní objem"],
            )
        )
        db.commit()

        facts, gaps = layer(db)
        assert len(facts) == 1
        assert len(gaps) == 1
        assert "Průměrný denní objem" in gaps[0].text_cs
        assert gaps[0].fixable_cs is None


class TestSymbolVariantsAreMatched:
    def test_a_row_under_a_variant_spelling_is_still_found(self, db):
        """Mirrors how every other layer resolves KUYAF vs KUYA.V."""
        db.add(
            GomesFitCache(
                ticker="KUYAF",
                as_of=date(2026, 8, 24),
                computed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
                summary_cs="0 mimo, 0 na okraji, 1 typické.",
                fits_json=[
                    {"name": "rsi", "label_cs": "RSI", "value": 55.0,
                     "bucket": "TYPICKE", "below": 20, "of": 40},
                ],
                uncomputable_json=[],
            )
        )
        db.commit()

        facts, gaps = layer(db, symbols=("KUYA.V", "KUYAF"))
        assert len(facts) == 1
        assert gaps == []
