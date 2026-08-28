"""
Zapíše tři modely tržeb, které Mark publikoval a Tomáš stáhl 25. 8. 2026:
OPTX (Syntec Optics), TPCS (TechPrecision) a DFSC.V (DEFSEC Technologies).

Každý model má jinou strukturu, což je právě ta hodnota — ukazuje, na čem
staví ocenění tří různých typů firem:

  - OPTX: zdola nahoru, 28 produktových řádků × kusy × cena, jen rok 2025.
    Roky 2026-2029 se z dokumentu záměrně NEIMPORTUJÍ: hlavička projektovaných
    sloupců na str. 5 zdrojového PDF zní doslova "2026 2027 2027 2028" (dva
    sloupce "2027" s různými čísly) a bez pohledu do barevně rozlišeného
    originálu (černá = objednávka, červená = odhad) by šlo jen hádat, který
    sloupec je který rok. Radši žádné číslo než špatně přiřazené.
  - TPCS: jediný řádek "Total Revenues" po čtvrtletích — model, který sleduje
    trend, ne mix. Backlog a Bookings z téhož dokumentu jdou do poznámky u
    každého řádku, ne do součtu (jsou to jiné veličiny než tržba).
  - DFSC.V: tři scénáře (Bear/Base/Bull) × čtyři fiskální roky. Each label
    nese i scénář ("FY2026-Bear"), aby se scénáře navzájem nesčítaly do
    jednoho čísla za rok — a proto se taky nedají automaticky porovnat s
    realitou přes /compare (label není rozpoznatelný jako rok ani datum),
    což je správně: srovnávat realitu s "Bear" scénářem by bylo svévolné.

Idempotentní: model se stejným (ticker, model_name) se přeskočí.

Run:
    python scripts/seed_revenue_models.py --dry-run
    python scripts/seed_revenue_models.py
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import date

BACKEND = pathlib.Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import initialize_database, session_scope  # noqa: E402
import app.models  # noqa: F401,E402
import app.models.trading  # noqa: F401,E402
from app.models.revenue_model import AnalystRevenueModel, AnalystRevenueModelLine  # noqa: E402


# ==============================================================================
# OPTX — Syntec Optics, rok 2025, zdola nahoru
# ==============================================================================

OPTX_LINES = [
    # (category, item_name, quantity, price_per_unit)
    ("Medical", "Disposable Endoscope Optics", 77000, 65.00),
    ("Medical", "Bio Fluidic Sensor Chips", 208000, 12.00),
    ("Medical", "Surgical Robot Assemblies", 4500, 550.00),
    ("Consumer", "AR/VR Pancake Lenses", 102994, 35.00),
    ("Consumer", "Smart glass waveguides", 89820, 20.00),
    ("Consumer", "Legacy Camera Lenses", 119762, 5.00),
    ("Communications", "Fast Steering Mirror Assy", 1593, 725.40),
    ("Communications", "Transmit/Receive Telescope (OTA)", 1593, 544.05),
    ("Communications", "Beam Expander and Collimator", 1593, 241.80),
    ("Communications", "Radiation hardened windows", 1593, 120.90),
    ("Defense NVG (ENVG-B)", "Objective Lens Assembly", 3700, 600.00),
    ("Defense NVG (ENVG-B)", "Eyepiece Assembly", 3700, 350.00),
    ("Defense NVG (ENVG-B)", "Sensor protection window", 3700, 90.00),
    ("Legacy Munitions Program", "Seeker Window", 2350, 300.00),
    ("Legacy Munitions Program", "Detector Lens Stack", 2350, 500.00),
    ("Legacy Munitions Program", "Fin/Actuator Optics", 2350, 200.00),
    ("Legacy IR Rifle Scopes", "Prism Assembly", 10500, 35.00),
    ("Legacy IR Rifle Scopes", "Objective lens", 10500, 60.00),
    ("Legacy IR Rifle Scopes", "Eyepiece/Display", 10500, 70.00),
]
# Řádky bez sazby za kus v dokumentu — rovnou částka.
OPTX_AMOUNT_LINES = [
    ("AI Data Center", "Microlens Arrays", 1_500_000),
]

OPTX_NOTES = (
    "Zdroj: 'OPTX Model - Revenue Breakdown.pdf' (stažen 25.8.26). "
    "Součet 2025 sedí na cent na uvedený TOTAL $28,006,515. "
    "Poznámka z dokumentu: 'Black text = locked in orders / Red text = "
    "evidence-based estimates' (str. 9-11) — appka barvu z PDF nedokáže "
    "přečíst, takže confidence u těchto řádků zůstává NULL. Roky 2026-2029 "
    "v dokumentu jsou, ale hlavička je poškozená (dva sloupce '2027' s "
    "různými čísly) a neimportovaly se — viz docstring tohoto skriptu. "
    "Firma navíc sleduje 13 dalších kategorií bez čísla pro 2025 (Anduril "
    "Eagle Eye AR Goggles, Hyperspectral Imaging, Weather Satellite optika, "
    "L3 Red Wolf, Vision Correction Lens čekající na FDA, Quantum Sensing, "
    "Drones) — to jsou budoucí sázky, ne dnešní tržba."
)

OPTX_ANDURIL_ZERO = [
    ("Defense AR Goggles (Anduril Eagle Eye)", "Polymer Waveguide"),
    ("Defense AR Goggles (Anduril Eagle Eye)", "Freeform Prism"),
    ("Defense AR Goggles (Anduril Eagle Eye)", "Mil-Spec coatings"),
    ("Defense AR Goggles (Anduril Eagle Eye)", "Assembly and Housing"),
]


def build_optx() -> AnalystRevenueModel:
    model = AnalystRevenueModel(
        ticker="OPTX",
        company_name="Syntec Optics Holdings, Inc.",
        source_name="Mark Gomes",
        model_name="OPTX Product Revenue Breakdown",
        document_date=date(2026, 8, 25),
        notes=OPTX_NOTES,
    )
    for category, item, qty, price in OPTX_LINES:
        model.lines.append(
            AnalystRevenueModelLine(
                category=category, item_name=item, period_label="2025",
                quantity=qty, price_per_unit=price, currency="USD",
            )
        )
    for category, item, amount in OPTX_AMOUNT_LINES:
        model.lines.append(
            AnalystRevenueModelLine(
                category=category, item_name=item, period_label="2025",
                amount=amount, currency="USD",
            )
        )
    # Nulové řádky (program ještě negeneruje tržbu) — amount=0 je číslo, ne
    # mezera, takže smí být uloženo přímo.
    for category, item in OPTX_ANDURIL_ZERO:
        model.lines.append(
            AnalystRevenueModelLine(
                category=category, item_name=item, period_label="2025",
                amount=0, currency="USD",
                note="Program v roce 2025 negeneroval tržbu (čeká na kontrakt).",
            )
        )
    return model


# ==============================================================================
# TPCS — TechPrecision, trend po čtvrtletích
# ==============================================================================

# (quarter_end m/d/yy, total_revenue_musd, backlog_musd, bookings_musd)
TPCS_QUARTERS = [
    ("6/30/24", 8.00, 41.20, -0.80),
    ("9/30/24", 8.95, 48.64, 16.39),
    ("12/31/24", 7.60, 45.50, 4.46),
    ("3/31/25", 9.48, 48.60, 12.58),
    ("6/30/25", 7.38, 50.10, 8.88),
    ("9/30/25", 9.09, 47.80, 6.79),
    ("12/31/25", 7.09, 46.00, 5.29),
    ("3/31/26", 8.09, 52.10, 14.19),
    ("6/30/26", 9.10, 52.70, 9.70),
]

TPCS_NOTES = (
    "Zdroj: 'TPCS Operating Model - Aug 2023 - Bookings & Backlog.pdf' "
    "(stažen 25.8.26, Source: Pipeline Data, LLC — Markova vlastní firma). "
    "Jediný sledovaný řádek je Total Revenues; Backlog a Bookings jsou u "
    "každého čtvrtletí v poznámce, ne v součtu (jiná veličina než tržba, "
    "sečíst by je bylo zavádějící)."
)


def build_tpcs() -> AnalystRevenueModel:
    model = AnalystRevenueModel(
        ticker="TPCS",
        company_name="TechPrecision Corporation",
        source_name="Mark Gomes",
        model_name="TPCS Bookings & Backlog Trend",
        document_date=date(2026, 8, 25),
        notes=TPCS_NOTES,
    )
    for quarter, revenue, backlog, bookings in TPCS_QUARTERS:
        model.lines.append(
            AnalystRevenueModelLine(
                category="Operations", item_name="Total Revenues",
                period_label=quarter, amount=revenue * 1_000_000, currency="USD",
                note=f"Backlog {backlog:.2f} M $, Bookings {bookings:+.2f} M $.",
            )
        )
    return model


# ==============================================================================
# DFSC.V — DEFSEC Technologies, scénáře Bear/Base/Bull
# ==============================================================================

# scenario -> {fiscal_year: (revenue_cad, headcount)}
DEFSEC_SCENARIOS = {
    "Bear": {2026: (8_892_000, 38), 2027: (10_530_000, 45), 2028: (11_700_000, 50), 2029: (12_870_000, 55)},
    "Base": {2026: (8_892_000, 38), 2027: (12_870_000, 55), 2028: (16_380_000, 70), 2029: (19_188_000, 82)},
    "Bull": {2026: (8_892_000, 38), 2027: (15_210_000, 65), 2028: (21_060_000, 90), 2029: (25_740_000, 110)},
}
DEFSEC_GROSS_MARGIN_PCT = 33.5

DEFSEC_NOTES = (
    "Zdroj: 'DEFSEC Headcount Scenarios Model - Sheet1.pdf' (stažen 25.8.26, "
    "Fiskální rok končí 30.9.). Hnací síla je počet fakturovatelných lidí, "
    "ne produktový mix jako u OPTX — DEFSEC je štábní/inženýrská firma "
    "(programy DSEF a L4CSIR pro General Dynamics), tržba roste s "
    "náborem, ne s výrobou. Tři scénáře NEJDOU sečíst do jednoho čísla za "
    "rok (proto label nese i scénář) a proto se ani automaticky "
    "neporovnávají s realitou přes /compare — bylo by svévolné říct, který "
    "scénář je 'ten model'."
)


def build_defsec() -> AnalystRevenueModel:
    model = AnalystRevenueModel(
        ticker="DFSC.V",
        company_name="DEFSEC Technologies Inc.",
        source_name="Mark Gomes",
        model_name="DEFSEC Headcount Ramp Scenarios",
        document_date=date(2026, 8, 25),
        notes=DEFSEC_NOTES,
    )
    for scenario, years in DEFSEC_SCENARIOS.items():
        for fy, (revenue, headcount) in years.items():
            model.lines.append(
                AnalystRevenueModelLine(
                    category=f"{scenario} Scenario", item_name="Annual revenue",
                    period_label=f"FY{fy}-{scenario}", amount=revenue, currency="CAD",
                    note=(
                        f"Průměr fakturovatelných lidí: {headcount}, "
                        f"hrubá marže: {DEFSEC_GROSS_MARGIN_PCT:.1f} %."
                    ),
                )
            )
    return model


BUILDERS = {
    "OPTX Product Revenue Breakdown": build_optx,
    "TPCS Bookings & Backlog Trend": build_tpcs,
    "DEFSEC Headcount Ramp Scenarios": build_defsec,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="rozhodni a vypiš, nic nezapisuj")
    args = parser.parse_args()

    ok, error = initialize_database(get_settings().database_url)
    if not ok:
        print(f"Databáze není dostupná: {error}")
        return 1

    with session_scope() as db:
        existing = {
            (m.ticker, m.model_name)
            for m in db.query(AnalystRevenueModel.ticker, AnalystRevenueModel.model_name).all()
        }
        for model_name, builder in BUILDERS.items():
            model = builder()
            key = (model.ticker, model.model_name)
            if key in existing:
                print(f"přeskočeno (už existuje): {model.ticker} — {model_name}")
                continue
            total_lines = len(model.lines)
            periods = sorted({line.period_label for line in model.lines})
            print(f"{'[dry-run] ' if args.dry_run else ''}{model.ticker} — {model_name}: "
                  f"{total_lines} řádků, období: {', '.join(periods)}")
            if not args.dry_run:
                db.add(model)
        if not args.dry_run:
            db.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
