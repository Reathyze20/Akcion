-- ============================================================================
--  Vlastní nálezy — místo pro nápady, které nepřišly od Gomese ani od Breakout
-- ============================================================================
--  Date: 2026-08-24
--
--  Aplikace uměla posoudit jen to, co jí dal některý ze dvou zdrojů. Vlastní
--  nápad neměl kam jít, takže se buď koupil bez posudku, nebo zapomněl. Tyhle
--  dvě tabulky mu dávají místo a — což je důležitější — dávají mu HISTORII:
--  co jsem si myslel, když jsem si toho všiml, a co na to řekla data.
--
--  Rozdělení na nález a posudek je celý smysl migrace. Nález je jedna věc
--  (ticker a moje věta proč). Posudek je jedno čtení dat v jednom okamžiku a je
--  APPEND-ONLY — druhý posudek nepřepíše první. Jediná tabulka by minulý názor
--  přepsala tím dnešním a přesně to, na čem se dá učit, by zmizelo.
--
--  Žádný sloupec odsud nekrmí nákupní bránu. `band`, `cylinders_proposed` a
--  `phase_proposed` jsou NÁVRHY z rubriky, ne potvrzené hodnoty — potvrzené
--  válce a fáze žijou dál výhradně v `stock_lifecycle` a smí je zapsat jen
--  cylinder_intake.confirm() / lifecycle_intake.confirm() po lidském potvrzení.
--
--  CHECK constrainty jsou tady záměrně, ne pro parádu. Opakovaná vada téhle
--  aplikace je, že se z chybějícího vstupu stane sebejisté číslo, takže schéma
--  samo odmítne uložit „zasloužené skóre" bez válců, z nichž se počítá, a
--  „prošlo bránou" bez kódu, který to říká.
--
--  Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS own_finds (
    id SERIAL PRIMARY KEY,

    -- Kanonický symbol (přes core/tickers.canonical_ticker) — jen pro párování
    -- napříč burzami. Zobrazuje se display_ticker, tedy to, co člověk napsal.
    ticker VARCHAR(20) NOT NULL,
    display_ticker VARCHAR(20) NOT NULL,
    company_name VARCHAR(200),

    -- Vlastní slova majitele: proč si toho všiml. Není to popisek, je to vstup
    -- posudku — vysvětlovač se k té úvaze musí postavit.
    note TEXT NOT NULL,

    found_at DATE NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'OTEVRENY'
        CHECK (status IN ('OTEVRENY', 'ODLOZENY', 'ZAHOZENY')),
    closed_at TIMESTAMP WITH TIME ZONE,
    close_reason TEXT,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Uzavřený nález musí říct kdy. Bez toho by „odložený" a „zahozený" byly
    -- jen barvy bez data a nešlo by je řadit podle toho, co se stalo naposled.
    CONSTRAINT closed_find_has_a_date CHECK (
        status = 'OTEVRENY' OR closed_at IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_own_finds_ticker ON own_finds(ticker);
CREATE INDEX IF NOT EXISTS idx_own_finds_status ON own_finds(status, found_at DESC);

-- Tentýž ticker smí být otevřený jen jednou. Dva otevřené nálezy na jednu firmu
-- nejsou dva nápady, je to jeden nápad zapsaný dvakrát — a rozštěpily by
-- historii posudků, na které je celá tabulka postavená. Zavřené nálezy tomu
-- nebrání: k firmě se člověk smí vrátit později s jinou úvahou.
CREATE UNIQUE INDEX IF NOT EXISTS uq_own_finds_open_ticker
    ON own_finds(ticker) WHERE status = 'OTEVRENY';


CREATE TABLE IF NOT EXISTS own_find_assessments (
    id SERIAL PRIMARY KEY,
    find_id INTEGER NOT NULL REFERENCES own_finds(id) ON DELETE CASCADE,

    assessed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Kurz v okamžiku posudku. Drží se tady, a ne odkazem do cache, aby šlo
    -- později ukázat, co cena udělala od chvíle rozhodnutí — bez jediného
    -- zápisu do sdílených tabulek.
    price_at_assessment NUMERIC(14, 4),
    price_currency VARCHAR(5),
    -- TRUE je záměrný default: „nevíme, že je čerstvý", ne „je zastaralý".
    price_is_stale BOOLEAN NOT NULL DEFAULT TRUE,

    -- Celý spis: fakta (id, vrstva, česká věta, hodnota, datum) a mezery.
    -- Ukládá se celý, protože bod od AI cituje fact_id a bez spisu by po roce
    -- nešlo ověřit, na co se ten bod vlastně odkazoval.
    dossier JSONB NOT NULL,

    -- Odvozeno ze spisu, aby výpis nemusel rozbalovat JSONB.
    band VARCHAR(20),
    rr_score NUMERIC(6, 3),
    deserved NUMERIC(6, 3),
    cylinders_proposed INTEGER
        CHECK (cylinders_proposed IS NULL
               OR cylinders_proposed BETWEEN 0 AND 10),
    -- Co u firmy potvrdil clovek, opsane ze stock_lifecycle. Jen kopie pro
    -- historii; zdrojem pravdy zustava stock_lifecycle a tahle tabulka do nej
    -- nikdy nezapisuje.
    cylinders_confirmed INTEGER
        CHECK (cylinders_confirmed IS NULL
               OR cylinders_confirmed BETWEEN 0 AND 10),
    phase_proposed VARCHAR(20),

    -- NULL = bránu nešlo vůbec vyhodnotit, což je jiný stav než „neprošla".
    gate_passed BOOLEAN,
    gate_code VARCHAR(40),
    gate_reason TEXT,
    gate_reason_cs TEXT,

    -- NULL, dokud si majitel nevyžádá vysvětlení. Placené volání se neděje samo.
    explanation JSONB,
    explanation_model VARCHAR(60),
    explained_at TIMESTAMP WITH TIME ZONE,

    -- Kolik bodů od AI citovalo fact_id, které ve spisu není, a bylo proto
    -- zahozeno. Sloupec, ne log: kdyby model začal vymýšlet, musí to být vidět
    -- na obrazovce, ne jen v souboru, který nikdo nečte.
    points_dropped INTEGER NOT NULL DEFAULT 0 CHECK (points_dropped >= 0),

    -- Zasloužené skóre je 10 − válce (kánon §4b), a počítá se z POTVRZENÝCH
    -- válců, ne z návrhu rubriky. Vázat ho na návrh by znamenalo, že neschválený
    -- odhad může vyrobit laťku, proti které se měří nákup.
    CONSTRAINT deserved_has_its_cylinders CHECK (
        deserved IS NULL OR cylinders_confirmed IS NOT NULL
    ),

    -- „Prošlo bránou" musí pojmenovat, která odpověď to říká.
    CONSTRAINT gate_verdict_names_its_code CHECK (
        gate_passed IS NULL OR gate_code IS NOT NULL
    ),

    -- Vysvětlení musí vědět, kdo ho napsal a kdy. Text bez modelu a data se za
    -- půl roku nedá zařadit ani zpochybnit.
    CONSTRAINT explanation_names_its_author CHECK (
        explanation IS NULL
        OR (explanation_model IS NOT NULL AND explained_at IS NOT NULL)
    ),

    CONSTRAINT assessment_price_is_a_price CHECK (
        price_at_assessment IS NULL OR price_at_assessment > 0
    )
);

CREATE INDEX IF NOT EXISTS idx_own_find_assessments_find
    ON own_find_assessments(find_id, assessed_at DESC);

-- Dorovnani pro databazi, kde tabulka vznikla drive (24. 8. 2026, prvni beh
-- teto migrace jeste bez sloupce cylinders_confirmed). Idempotentni.
ALTER TABLE own_find_assessments
    ADD COLUMN IF NOT EXISTS cylinders_confirmed INTEGER;

ALTER TABLE own_find_assessments
    DROP CONSTRAINT IF EXISTS deserved_has_its_cylinders;
ALTER TABLE own_find_assessments
    ADD CONSTRAINT deserved_has_its_cylinders CHECK (
        deserved IS NULL OR cylinders_confirmed IS NOT NULL
    );
ALTER TABLE own_find_assessments
    DROP CONSTRAINT IF EXISTS cylinders_confirmed_in_range;
ALTER TABLE own_find_assessments
    ADD CONSTRAINT cylinders_confirmed_in_range CHECK (
        cylinders_confirmed IS NULL OR cylinders_confirmed BETWEEN 0 AND 10
    );


COMMENT ON TABLE own_finds IS
    'Vlastni napady majitele: ticker a jeho veta proc si toho vsiml.';
COMMENT ON TABLE own_find_assessments IS
    'Jedno cteni dat k jednomu nalezu. Append-only: druhy posudek neprepise prvni.';
COMMENT ON COLUMN own_find_assessments.band IS
    'Pasmo z NEPOTVRZENYCH valcu. Neni to potvrzeny udaj a nekrmi nakupni branu.';
COMMENT ON COLUMN own_find_assessments.points_dropped IS
    'Kolik bodu od AI citovalo neexistujici fakt a bylo zahozeno. 0 = zadny.';
COMMENT ON COLUMN own_find_assessments.price_is_stale IS
    'TRUE = nevime, ze je kurz cerstvy. Default je zamerne TRUE, ne FALSE.';
