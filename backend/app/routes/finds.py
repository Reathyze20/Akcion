"""
Nálezy — vlastní nápady majitele a jejich posudky.

Sedm endpointů a jen jediný z nich stojí peníze: `POST /{id}/explain`. Všechno
ostatní je čtení z databáze nebo bezplatný sběr veřejných dat. Žádný cron,
žádná smyčka, žádné posuzování při otevření stránky — placené volání se děje
výhradně po kliknutí.

Nic tady nezapisuje do `stock_lifecycle`, `stocks` ani `positions`. Nález je
uzavřené pískoviště (rozhodnutí majitele 24. 8. 2026): sám o sobě nesmí zvětšit
ani jednu pozici a nesmí odemknout nákupní bránu.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.tickers import canonical_ticker
from app.database.connection import get_db
from app.models.own_find import STATUS_OPEN, OwnFind, OwnFindAssessment
from app.services import find_dossier, find_explainer
from app.services.buy_gate_cs import gate_cs
from app.services.find_explainer import FindExplainError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/finds", tags=["Nálezy"])


# ==============================================================================
# Schémata
# ==============================================================================

class FindCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    #: Krátká poznámka je za rok nečitelná, a je to zároveň vstup posudku —
    #: proto minimum, ne volitelné pole.
    note: str = Field(min_length=10, max_length=4000)
    found_at: date | None = None


class FindUpdate(BaseModel):
    note: str | None = Field(default=None, min_length=10, max_length=4000)
    status: str | None = None
    close_reason: str | None = None


class FactOut(BaseModel):
    id: str
    layer: str
    text_cs: str
    source: str
    as_of: date | None = None
    quote: str | None = None
    direction: str


class GapOut(BaseModel):
    id: str
    layer: str
    text_cs: str
    fixable_cs: str | None = None


class MethodOut(BaseModel):
    band: str
    band_reason_cs: str
    rr_score: float | None = None
    deserved: float | None = None
    buy_below: float | None = None
    sell_above: float | None = None
    green_line: float | None = None
    red_line: float | None = None
    line_currency: str | None = None
    cylinders_confirmed: int | None = None
    cylinders_proposed: int | None = None
    if_cylinders_cs: str | None = None
    phase_proposed: str | None = None
    #: Fáze je NÁVRH rubriky, ne potvrzený stav. Pole je tu proto, aby na to
    #: obrazovka nemohla zapomenout.
    phase_is_proposal: bool = True
    phase_rough_patch: bool = False
    market_alert: str | None = None
    market_alert_stale: bool = True
    gate_passed: bool | None = None
    gate_code: str | None = None
    gate_reason_cs: str


class DossierOut(BaseModel):
    ticker: str
    symbol: str
    company_name: str | None = None
    as_of: datetime
    price: float | None = None
    price_currency: str | None = None
    price_is_stale: bool
    facts: list[FactOut]
    gaps: list[GapOut]
    method: MethodOut


class PointOut(BaseModel):
    side: str
    headline_cs: str
    body_cs: str
    fact_ids: list[str]
    canon_ref: str
    #: Znění pravidla doplňuje server z `CANON_DIGEST`. Model dodá odkaz,
    #: slova dodá aplikace — kánon se nepřevypravuje modelem.
    canon_text_cs: str
    check_yourself_cs: str
    weight: str


class ExplanationOut(BaseModel):
    one_line_cs: str
    points: list[PointOut]
    own_reason_cs: str
    own_reason_verdict: str
    lesson_cs: str


class AssessmentOut(BaseModel):
    id: int
    assessed_at: datetime
    price_at_assessment: float | None = None
    price_currency: str | None = None
    price_is_stale: bool
    band: str | None = None
    gate_code: str | None = None
    gate_reason_cs: str | None = None
    explanation: ExplanationOut | None = None
    explanation_model: str | None = None
    explained_at: datetime | None = None
    points_dropped: int
    dossier: DossierOut | None = None


class FindOut(BaseModel):
    id: int
    ticker: str
    symbol: str
    company_name: str | None = None
    note: str
    found_at: date
    status: str
    closed_at: datetime | None = None
    close_reason: str | None = None
    assessment_count: int
    last_assessed_at: datetime | None = None
    last_band: str | None = None
    last_price: float | None = None
    last_one_line_cs: str | None = None


class FindDetailOut(BaseModel):
    find: FindOut
    dossier: DossierOut
    assessments: list[AssessmentOut]
    collect_notes_cs: list[str] = Field(default_factory=list)
    collect_errors_cs: list[str] = Field(default_factory=list)


# ==============================================================================
# Převody
# ==============================================================================

def _method_out(m: find_dossier.MethodReading) -> MethodOut:
    return MethodOut(
        band=m.band,
        band_reason_cs=m.band_reason_cs,
        rr_score=m.rr_score,
        deserved=m.deserved,
        buy_below=m.buy_below,
        sell_above=m.sell_above,
        green_line=m.green_line,
        red_line=m.red_line,
        line_currency=m.line_currency,
        cylinders_confirmed=m.cylinders_confirmed,
        cylinders_proposed=m.cylinders_proposed,
        if_cylinders_cs=m.if_cylinders_cs,
        phase_proposed=m.phase_proposed,
        phase_rough_patch=m.phase_rough_patch,
        market_alert=m.market_alert,
        market_alert_stale=m.market_alert_stale,
        gate_passed=m.gate_passed,
        gate_code=m.gate_code,
        gate_reason_cs=gate_cs(
            m.gate_code,
            market_alert=m.market_alert,
            rr_score=m.rr_score,
            deserved=m.deserved,
        ),
    )


def _dossier_out(d: find_dossier.Dossier) -> DossierOut:
    return DossierOut(
        ticker=d.ticker,
        symbol=d.symbol,
        company_name=d.company_name,
        as_of=d.as_of,
        price=d.price,
        price_currency=d.price_currency,
        price_is_stale=d.price_is_stale,
        facts=[FactOut(**vars(f)) for f in d.facts],
        gaps=[GapOut(**vars(g)) for g in d.gaps],
        method=_method_out(d.method),
    )


def _explanation_out(payload: dict[str, Any] | None) -> ExplanationOut | None:
    if not payload:
        return None
    points = [
        PointOut(
            **{**p, "canon_text_cs": find_explainer.canon_text(p.get("canon_ref", ""))}
        )
        for p in payload.get("points", [])
    ]
    return ExplanationOut(
        one_line_cs=payload.get("one_line_cs", ""),
        points=points,
        own_reason_cs=payload.get("own_reason_cs", ""),
        own_reason_verdict=payload.get("own_reason_verdict", "NELZE_POSOUDIT"),
        lesson_cs=payload.get("lesson_cs", ""),
    )


def _assessment_out(row: OwnFindAssessment, *, with_dossier: bool) -> AssessmentOut:
    return AssessmentOut(
        id=row.id,
        assessed_at=row.assessed_at,
        price_at_assessment=(
            float(row.price_at_assessment)
            if row.price_at_assessment is not None
            else None
        ),
        price_currency=row.price_currency,
        price_is_stale=row.price_is_stale,
        band=row.band,
        gate_code=row.gate_code,
        gate_reason_cs=row.gate_reason_cs,
        explanation=_explanation_out(row.explanation),
        explanation_model=row.explanation_model,
        explained_at=row.explained_at,
        points_dropped=row.points_dropped,
        dossier=DossierOut(**row.dossier) if with_dossier and row.dossier else None,
    )


def _find_out(db: Session, find: OwnFind) -> FindOut:
    rows = (
        db.query(OwnFindAssessment)
        .filter(OwnFindAssessment.find_id == find.id)
        .order_by(desc(OwnFindAssessment.assessed_at))
        .all()
    )
    newest = rows[0] if rows else None
    one_line = None
    if newest is not None and newest.explanation:
        one_line = newest.explanation.get("one_line_cs")
    return FindOut(
        id=find.id,
        ticker=find.ticker,
        symbol=find.display_ticker,
        company_name=find.company_name,
        note=find.note,
        found_at=find.found_at,
        status=find.status,
        closed_at=find.closed_at,
        close_reason=find.close_reason,
        assessment_count=len(rows),
        last_assessed_at=newest.assessed_at if newest else None,
        last_band=newest.band if newest else None,
        last_price=(
            float(newest.price_at_assessment)
            if newest is not None and newest.price_at_assessment is not None
            else None
        ),
        last_one_line_cs=one_line,
    )


def _fx():
    """Kurzová funkce pro přepočet ceny do měny čar. Selhání se nepředstírá."""
    from app.services.currency import CurrencyService

    return CurrencyService.get_rate_to_czk


def _assess(
    db: Session,
    find: OwnFind,
    collected: find_dossier.Enriched | None = None,
) -> tuple[find_dossier.Dossier, OwnFindAssessment]:
    """
    Složit spis a připsat nový řádek posudku. Bez placeného volání.

    `collected` se předává dál záměrně: výkazy, které sběr právě přečetl, jsou
    v databázi jen jako uložená podání, ne jako spočítané řady. Bez nich by
    rubrika válců spadla na neauditované roční souhrny z Yahoo a čerstvě
    načtené XBRL by se zahodilo.
    """
    dossier = find_dossier.build(
        db,
        find.ticker,
        symbol=find.display_ticker,
        note=find.note,
        fundamentals=collected.fundamentals if collected else None,
        finnhub=collected.finnhub if collected else None,
        fx_rate_to_czk=_fx(),
    )
    if dossier.company_name and not find.company_name:
        find.company_name = dossier.company_name

    m = dossier.method
    row = OwnFindAssessment(
        find_id=find.id,
        assessed_at=datetime.now(timezone.utc),
        price_at_assessment=dossier.price,
        price_currency=dossier.price_currency,
        price_is_stale=dossier.price_is_stale,
        dossier=_dossier_out(dossier).model_dump(mode="json"),
        band=m.band,
        rr_score=m.rr_score,
        deserved=m.deserved,
        cylinders_proposed=m.cylinders_proposed,
        cylinders_confirmed=m.cylinders_confirmed,
        phase_proposed=m.phase_proposed,
        gate_passed=m.gate_passed,
        gate_code=m.gate_code,
        gate_reason=m.gate_reason,
        gate_reason_cs=gate_cs(
            m.gate_code,
            market_alert=m.market_alert,
            rr_score=m.rr_score,
            deserved=m.deserved,
        ),
    )
    db.add(row)
    return dossier, row


def _get(db: Session, find_id: int) -> OwnFind:
    find = db.query(OwnFind).filter(OwnFind.id == find_id).first()
    if find is None:
        raise HTTPException(status_code=404, detail="Takový nález neexistuje.")
    return find


# ==============================================================================
# Endpointy
# ==============================================================================

@router.get("", response_model=list[FindOut])
def list_finds(
    include_closed: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Výpis nálezů, nejnovější první."""
    query = db.query(OwnFind)
    if not include_closed:
        query = query.filter(OwnFind.status == STATUS_OPEN)
    finds = query.order_by(desc(OwnFind.found_at), desc(OwnFind.id)).all()
    return [_find_out(db, f) for f in finds]


@router.post("", response_model=FindDetailOut, status_code=201)
def create_find(body: FindCreate, db: Session = Depends(get_db)):
    """
    Založit nález, dotáhnout veřejná data a rovnou složit spis.

    Sběr jde na síť (Yahoo, EDGAR, Finnhub) a u neznámého tickeru trvá pár
    sekund. Placené API se nevolá — vysvětlení je samostatné tlačítko.
    """
    symbol = body.symbol.upper().strip()
    canonical = canonical_ticker(symbol)

    clash = (
        db.query(OwnFind)
        .filter(OwnFind.ticker == canonical)
        .filter(OwnFind.status == STATUS_OPEN)
        .first()
    )
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Nález pro {clash.display_ticker} už máš otevřený "
                f"(z {clash.found_at:%d. %m. %Y}). Doplň k němu poznámku "
                f"místo zakládání druhého."
            ),
        )

    # Sběr běží PŘED založením nálezu: `sec_sync` si uvnitř commituje, a kdyby
    # nález už existoval, zůstal by po pozdějším selhání v databázi napůl.
    collected = find_dossier.enrich(db, symbol)

    find = OwnFind(
        ticker=canonical,
        display_ticker=symbol,
        note=body.note.strip(),
        found_at=body.found_at or datetime.now(timezone.utc).date(),
        status=STATUS_OPEN,
    )
    db.add(find)
    db.flush()

    dossier, row = _assess(db, find, collected)
    db.commit()
    db.refresh(find)
    db.refresh(row)

    return FindDetailOut(
        find=_find_out(db, find),
        dossier=_dossier_out(dossier),
        assessments=[_assessment_out(row, with_dossier=False)],
        collect_notes_cs=collected.notes_cs,
        collect_errors_cs=collected.errors_cs,
    )


@router.get("/{find_id}", response_model=FindDetailOut)
def get_find(find_id: int, db: Session = Depends(get_db)):
    """Nález, čerstvý spis z databáze (zdarma) a všechny posudky."""
    find = _get(db, find_id)
    dossier = find_dossier.build(
        db,
        find.ticker,
        symbol=find.display_ticker,
        note=find.note,
        fx_rate_to_czk=_fx(),
    )
    rows = (
        db.query(OwnFindAssessment)
        .filter(OwnFindAssessment.find_id == find.id)
        .order_by(desc(OwnFindAssessment.assessed_at))
        .all()
    )
    return FindDetailOut(
        find=_find_out(db, find),
        dossier=_dossier_out(dossier),
        assessments=[_assessment_out(r, with_dossier=True) for r in rows],
    )


@router.post("/{find_id}/refresh", response_model=FindDetailOut)
def refresh_find(find_id: int, db: Session = Depends(get_db)):
    """
    Dotáhnout data znovu a připsat nový posudek.

    Zdarma. Posudky jsou append-only — tenhle nepřepíše předchozí, přibude
    vedle něj, takže je pak vidět, jak se čtení v čase měnilo.
    """
    find = _get(db, find_id)
    collected = find_dossier.enrich(db, find.display_ticker)
    dossier, row = _assess(db, find, collected)
    db.commit()
    db.refresh(row)

    rows = (
        db.query(OwnFindAssessment)
        .filter(OwnFindAssessment.find_id == find.id)
        .order_by(desc(OwnFindAssessment.assessed_at))
        .all()
    )
    return FindDetailOut(
        find=_find_out(db, find),
        dossier=_dossier_out(dossier),
        assessments=[_assessment_out(r, with_dossier=True) for r in rows],
        collect_notes_cs=collected.notes_cs,
        collect_errors_cs=collected.errors_cs,
    )


@router.post("/{find_id}/explain", response_model=AssessmentOut)
def explain_find(
    find_id: int,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Nechat vysvětlit poslední posudek. **Jediné placené volání v téhle části.**

    Když už vysvětlený je, vrací 409 — druhé zaplacení za tutéž odpověď se
    nemá stát omylem. `force=true` ho vynutí.
    """
    find = _get(db, find_id)
    row = (
        db.query(OwnFindAssessment)
        .filter(OwnFindAssessment.find_id == find.id)
        .order_by(desc(OwnFindAssessment.assessed_at))
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=409, detail="K tomuhle nálezu zatím není žádný posudek."
        )
    if row.explanation is not None and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                "Poslední posudek už vysvětlený je. Další vysvětlení je další "
                "placené volání — pošli force=true, jestli ho opravdu chceš."
            ),
        )

    if not row.dossier:
        raise HTTPException(status_code=409, detail="Posudek nemá uložený spis.")

    # Vysvětluje se ULOŽENÝ spis, ne čerstvě složený.
    #
    # Skládat ho znovu vypadalo nevinně a bylo to špatně: sběr má výkazy
    # v ruce jen při zakládání, takže druhé sestavení stálo na slabších datech
    # a model pak vysvětloval jinou sadu faktů, než jakou má majitel na
    # obrazovce. Uvedl číslo, které v zobrazeném spisu nebylo — a kontrola
    # citací ho pustila, protože ve svém spisu ho našel. Vysvětlení musí platit
    # k tomu, co je zapsané, jinak se ověřuje proti něčemu, co nikdo neviděl.
    dossier = find_dossier.from_payload(row.dossier)

    try:
        result = find_explainer.explain(dossier, note=find.note)
    except FindExplainError as exc:
        # Nic se neukládá. Prázdné vysvětlení by se četlo jako „nic pro ani
        # proti", což je úplně jiné tvrzení než „nepovedlo se".
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    row.explanation = result.explanation.model_dump(mode="json")
    row.explanation_model = result.model
    row.explained_at = datetime.now(timezone.utc)
    row.points_dropped = result.points_dropped
    db.commit()
    db.refresh(row)
    return _assessment_out(row, with_dossier=False)


@router.patch("/{find_id}", response_model=FindOut)
def update_find(find_id: int, body: FindUpdate, db: Session = Depends(get_db)):
    """Upravit poznámku nebo stav. Nález se nemaže, jen uzavírá."""
    find = _get(db, find_id)

    if body.note is not None:
        find.note = body.note.strip()

    if body.status is not None:
        status = body.status.upper().strip()
        from app.models.own_find import FIND_STATUSES

        if status not in FIND_STATUSES:
            raise HTTPException(
                status_code=422, detail=f"Neznámý stav nálezu: {body.status}"
            )
        if status != STATUS_OPEN and find.status == STATUS_OPEN:
            find.closed_at = datetime.now(timezone.utc)
            find.close_reason = body.close_reason
        if status == STATUS_OPEN:
            find.closed_at = None
            find.close_reason = None
        find.status = status

    db.commit()
    db.refresh(find)
    return _find_out(db, find)
