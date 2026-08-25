-- ============================================================================
--  Dorovnání schématu proti modelům
-- ============================================================================
--  Dvanáct sloupců bylo v modelech a ne v databázi. Každý ORM dotaz na takovou
--  tabulku padal na UndefinedColumn — a protože se to stalo uvnitř jedné
--  transakce, shodilo to i všechno, co v ní běželo potom. Tabule vracela 500
--  s hláškou o „aborted transaction", což ukazuje na následek, ne na příčinu.
--
--  NOT NULL sloupce dostávají DEFAULT. Bez něj by ALTER na neprázdné tabulce
--  selhal a s ním by existující řádky dostaly hodnotu, kterou nikdo nezměřil —
--  proto jsou defaulty zvolené tak, aby znamenaly „nevíme", ne „je to v pořádku":
--  `catalyst_severity_known = FALSE` říká, že příčinu nikdo nepojmenoval, což
--  je přesně ten stav, ve kterém ty řádky jsou.
-- ============================================================================

ALTER TABLE market_status
    ADD COLUMN IF NOT EXISTS catalyst_description    TEXT,
    ADD COLUMN IF NOT EXISTS catalyst_identified_at  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS catalyst_severity_known BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE active_watchlist
    ADD COLUMN IF NOT EXISTS conviction_score NUMERIC(4, 2);

ALTER TABLE investment_verdicts
    ADD COLUMN IF NOT EXISTS conviction_score INTEGER;

ALTER TABLE price_lines
    ADD COLUMN IF NOT EXISTS conviction_score_at_green INTEGER,
    ADD COLUMN IF NOT EXISTS conviction_score_at_red   INTEGER;

ALTER TABLE investment_rules_log
    ADD COLUMN IF NOT EXISTS verdict_id  INTEGER,
    ADD COLUMN IF NOT EXISTS rule_result VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS rule_impact TEXT,
    ADD COLUMN IF NOT EXISTS rule_input  JSONB,
    ADD COLUMN IF NOT EXISTS applied_at  TIMESTAMPTZ NOT NULL DEFAULT now();

COMMENT ON COLUMN market_status.catalyst_severity_known IS
    'Zda nekdo pojmenoval pricinu stupne. FALSE = nepojmenoval, ne "je to v poradku".';
