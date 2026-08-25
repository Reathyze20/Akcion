"""
Vlastní nálezy — nápady, které nepřišly od Gomese ani od Breakout Investors.

Dvě tabulky, a to rozdělení je celý smysl souboru:

  own_finds             jeden nápad: ticker a majitelova věta proč
  own_find_assessments  jedno čtení dat v jednom okamžiku, append-only

Jediná tabulka by minulý názor přepsala tím dnešním. Přesně to, na čem se dá
učit — jak se moje úvaha z minulého měsíce srovnala s tím, co udělala cena —
by tím zmizelo. Proto posudek nikdy neupravuje předchozí posudek; přidává se
další řádek, stejně jako to dělá `cylinder_intake.confirm()` u válců.

Nic odsud nekrmí nákupní bránu. `band`, `cylinders_proposed` a `phase_proposed`
jsou návrhy rubriky, ne potvrzené hodnoty; potvrzené válce a fáze žijou dál
výhradně v `stock_lifecycle` a smí je zapsat jen `cylinder_intake.confirm()` /
`lifecycle_intake.confirm()` po lidském potvrzení. Nález je uzavřené pískoviště
(rozhodnutí majitele 2026-08-24) — sám o sobě nesmí zvětšit ani jednu pozici.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base

#: Stavy nálezu. „Odložený" a „zahozený" jsou dvě různé věci: k odloženému se
#: člověk chce vrátit, zahozený je vyřízený. Splynutí do jednoho „neaktivní"
#: by ten rozdíl smazalo a s ním i důvod, proč se k něčemu vracet.
FIND_STATUSES = ("OTEVRENY", "ODLOZENY", "ZAHOZENY")

STATUS_OPEN = "OTEVRENY"
STATUS_DEFERRED = "ODLOZENY"
STATUS_DISCARDED = "ZAHOZENY"


class OwnFind(Base):
    """Jeden vlastní nápad."""

    __tablename__ = "own_finds"

    id = Column(Integer, primary_key=True)

    #: Kanonický symbol z `core/tickers.canonical_ticker` — jen pro párování
    #: napříč burzami (GSI.V ↔ GKPRF). Na obrazovku jde `display_ticker`.
    ticker = Column(String(20), nullable=False, index=True)
    display_ticker = Column(
        String(20),
        nullable=False,
        doc="Symbol tak, jak ho majitel napsal — to je ten, který zná od brokera",
    )
    company_name = Column(String(200), nullable=True)

    note = Column(
        Text,
        nullable=False,
        doc=(
            "Vlastními slovy: proč si toho všiml. Není to popisek — vstupuje do "
            "spisu jako fakt a vysvětlovač se k té úvaze musí postavit."
        ),
    )

    found_at = Column(Date, nullable=False)

    status = Column(String(20), nullable=False, default=STATUS_OPEN)
    closed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    close_reason = Column(Text, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    assessments = relationship(
        "OwnFindAssessment",
        back_populates="find",
        cascade="all, delete-orphan",
        order_by="OwnFindAssessment.assessed_at.desc()",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('OTEVRENY', 'ODLOZENY', 'ZAHOZENY')",
            name="check_own_find_status",
        ),
        CheckConstraint(
            "status = 'OTEVRENY' OR closed_at IS NOT NULL",
            name="closed_find_has_a_date",
        ),
        Index("idx_own_finds_status", "status", "found_at"),
    )

    def __repr__(self) -> str:
        return f"<OwnFind {self.display_ticker} {self.status}>"


class OwnFindAssessment(Base):
    """
    Jedno čtení dat k jednomu nálezu. Append-only.

    Spis (`dossier`) se ukládá celý, ne jen odvozená čísla. Bod od AI cituje
    `fact_id` a bez spisu by po roce nešlo dohledat, na co se ten bod odkazoval
    — což je přesně ta nedohledatelnost, kvůli které se v téhle aplikaci muselo
    zahodit 395 tvrzení.
    """

    __tablename__ = "own_find_assessments"

    id = Column(Integer, primary_key=True)
    find_id = Column(
        Integer,
        ForeignKey("own_finds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    assessed_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    price_at_assessment = Column(
        Numeric(14, 4),
        nullable=True,
        doc=(
            "Kurz v okamžiku posudku. Drží se tady, a ne odkazem do cache, aby "
            "šlo později ukázat, co cena udělala — bez zápisu do sdílených tabulek."
        ),
    )
    price_currency = Column(String(5), nullable=True)
    price_is_stale = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="TRUE = nevíme, že je kurz čerstvý. Default je záměrně TRUE.",
    )

    dossier = Column(JSONB, nullable=False, doc="Fakta a mezery, serializované")

    #: Odvozené ze spisu, aby výpis nemusel rozbalovat JSONB.
    band = Column(
        String(20),
        nullable=True,
        doc="Pásmo z NEPOTVRZENÝCH válců. Není to potvrzený údaj.",
    )
    rr_score = Column(Numeric(6, 3), nullable=True)
    deserved = Column(Numeric(6, 3), nullable=True)
    cylinders_proposed = Column(Integer, nullable=True)
    cylinders_confirmed = Column(
        Integer,
        nullable=True,
        doc=(
            "Co potvrdil člověk, opsané ze `stock_lifecycle`. Jen kopie pro "
            "historii — zdrojem pravdy zůstává `stock_lifecycle`."
        ),
    )
    phase_proposed = Column(String(20), nullable=True)

    #: NULL = bránu nešlo vůbec vyhodnotit. Jiný stav než „neprošla".
    gate_passed = Column(Boolean, nullable=True)
    gate_code = Column(String(40), nullable=True, doc="Hodnota BuyGate")
    gate_reason = Column(Text, nullable=True, doc="Věta, kterou vydal engine")
    gate_reason_cs = Column(Text, nullable=True, doc="Tatáž věta pro člověka")

    explanation = Column(
        JSONB,
        nullable=True,
        doc="NULL, dokud si majitel nevyžádá vysvětlení. Placené volání.",
    )
    explanation_model = Column(String(60), nullable=True)
    explained_at = Column(TIMESTAMP(timezone=True), nullable=True)

    points_dropped = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc=(
            "Kolik bodů od AI citovalo fact_id, které ve spisu není, a bylo "
            "zahozeno. Sloupec, ne log — vymýšlení musí být vidět na obrazovce."
        ),
    )

    find = relationship("OwnFind", back_populates="assessments")

    __table_args__ = (
        CheckConstraint(
            "cylinders_proposed IS NULL OR cylinders_proposed BETWEEN 0 AND 10",
            name="cylinders_proposed_in_range",
        ),
        CheckConstraint(
            "cylinders_confirmed IS NULL OR cylinders_confirmed BETWEEN 0 AND 10",
            name="cylinders_confirmed_in_range",
        ),
        # Zasloužené skóre je 10 − válce (kánon §4b) a počítá se z POTVRZENÝCH
        # válců, ne z návrhu rubriky. Vázat ho na návrh by znamenalo, že
        # neschválený odhad vyrobí laťku, proti které se měří nákup.
        CheckConstraint(
            "deserved IS NULL OR cylinders_confirmed IS NOT NULL",
            name="deserved_has_its_cylinders",
        ),
        CheckConstraint(
            "gate_passed IS NULL OR gate_code IS NOT NULL",
            name="gate_verdict_names_its_code",
        ),
        CheckConstraint(
            "explanation IS NULL "
            "OR (explanation_model IS NOT NULL AND explained_at IS NOT NULL)",
            name="explanation_names_its_author",
        ),
        CheckConstraint("points_dropped >= 0", name="points_dropped_is_a_count"),
        CheckConstraint(
            "price_at_assessment IS NULL OR price_at_assessment > 0",
            name="assessment_price_is_a_price",
        ),
        Index("idx_own_find_assessments_find", "find_id", "assessed_at"),
    )

    def __repr__(self) -> str:
        return f"<OwnFindAssessment find={self.find_id} {self.assessed_at}>"
