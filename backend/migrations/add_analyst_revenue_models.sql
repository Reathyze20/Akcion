-- ============================================================================
--  Analytikovy modely tržeb — co je pro něj důležité, po řádcích
-- ============================================================================
--  Date: 2026-08-25
--
--  Mark občas publikuje vlastní model tržeb po produktech nebo scénářích
--  (např. OPTX: 28 produktových řádků × kusy × cena, po letech 2025-2028;
--  DEFSEC: scénáře Bear/Base/Bull podle počtu fakturovatelných lidí). Tyhle
--  dokumenty ukazují, co bere jako hnací sílu ocenění — a jde ověřit, jestli
--  se jeho odhady trefují, když čtvrtletí doopravdy dorazí.
--
--  Rozdělení na model a řádky kopíruje vlastní tabulku dokumentu: jeden model
--  (odkud je, kdy, pro koho) a k němu řádky (kategorie, položka, období,
--  kusy × cena nebo přímo částka). Součet řádků za období je součet přesně
--  toho, co je vidět v dokumentu — nic se nedopočítává navíc.
--
--  `confidence` je NULL, dokud to někdo ručně neurčí přečtením barvy
--  v originálním dokumentu (Mark rozlišuje černou = potvrzená objednávka,
--  červenou = odhad podložený důkazem) — appka to sama neuhodne, protože
--  z textu PDF barva nejde vytáhnout. NULL tedy znamená "nevíme", ne "odhad".
--
--  Nic odsud nekrmí nákupní bránu ani pásma — je to čtecí vrstva vedle
--  Gomesových zelených/červených čar, ne jejich náhrada.
--
--  Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS analyst_revenue_models (
    id SERIAL PRIMARY KEY,

    ticker VARCHAR(20) NOT NULL,
    company_name VARCHAR(200),

    -- Kdo model publikoval a odkud pochází (jméno souboru/zdroje pro dohledání).
    source_name VARCHAR(100) NOT NULL DEFAULT 'Mark Gomes',
    model_name VARCHAR(200) NOT NULL,
    document_date DATE,

    -- Volný text: souhrnné poznámky z dokumentu, které nejdou svázat s
    -- konkrétním řádkem (např. "Black text = locked orders, Red = estimates").
    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_analyst_revenue_models_ticker
    ON analyst_revenue_models(ticker);

COMMENT ON COLUMN analyst_revenue_models.notes IS
    'Poznámky z dokumentu bez jasné vazby na jeden řádek — např. metodika barevného rozlišení.';


CREATE TABLE IF NOT EXISTS analyst_revenue_model_lines (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES analyst_revenue_models(id) ON DELETE CASCADE,

    -- Kategorie = jak dokument řádky seskupuje (segment, scénář...).
    category VARCHAR(150) NOT NULL,
    item_name VARCHAR(200) NOT NULL,

    -- Období tak, jak ho dokument pojmenoval ("2025", "FY2026", "Q2 2025").
    -- Text, ne datum — dokumenty používají fiskální roky i kalendářní čtvrtletí.
    period_label VARCHAR(20) NOT NULL,

    quantity NUMERIC(18, 2),
    price_per_unit NUMERIC(18, 4),
    -- Částka: buď přímo z dokumentu (TPCS, DEFSEC uvádí $ rovnou), nebo
    -- quantity * price_per_unit (OPTX). CHECK dole vynucuje, že aspoň jedno
    -- z toho musí být — řádek bez čísla by byl jen jméno bez obsahu.
    amount NUMERIC(18, 2),
    currency VARCHAR(5) NOT NULL DEFAULT 'USD',

    -- Vidí to jen ten, kdo přečetl barvu v originále — appka sama nehádá.
    confidence VARCHAR(10) CHECK (confidence IS NULL OR confidence IN ('LOCKED', 'ESTIMATE')),

    note TEXT,

    CONSTRAINT amount_or_unit_math CHECK (
        amount IS NOT NULL OR (quantity IS NOT NULL AND price_per_unit IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_analyst_revenue_model_lines_model
    ON analyst_revenue_model_lines(model_id);

COMMENT ON COLUMN analyst_revenue_model_lines.confidence IS
    'LOCKED = potvrzená objednávka, ESTIMATE = odhad podložený důkazem (Markovo černá/červená). NULL = nikdo to zatím nepřečetl z originálu.';
