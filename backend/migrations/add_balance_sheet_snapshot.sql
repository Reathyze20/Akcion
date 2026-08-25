-- ============================================================================
--  Rozvaha do snímků fundamentů — podklad pro ochrannou rezervu
-- ============================================================================
--  `fundamental_snapshots` drží zatím jen to, co appka potřebovala k válcům:
--  tržby, marže, hotovost, dluh, počet akcií. Ochranná rezerva (pátý klíč
--  z Five Keys) se ptá jinak — „co mě drží, když se teze rozpadne" — a na to
--  je potřeba vlastní kapitál a to, kolik z něj je nehmotného.
--
--  Goodwill a nehmotná aktiva se odečítají schválně: jsou to první položky,
--  které se při rozbité tezi odepíšou, takže podlaha, která je počítá, není
--  podlaha. Ukládají se ale zvlášť, ne rovnou odečtené — kdo se na to dívá,
--  má vidět, kolik se odečetlo.
--
--  Nullable všechno: firma, která tyhle položky netaguje, prostě podlahu
--  nemá a aplikace to řekne. Nula by byla tvrzení, ne údaj.
-- ============================================================================

ALTER TABLE fundamental_snapshots
    ADD COLUMN IF NOT EXISTS stockholders_equity DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS goodwill            DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS intangibles         DOUBLE PRECISION;

COMMENT ON COLUMN fundamental_snapshots.stockholders_equity IS
    'Vlastni kapital z vykazu. Zaklad hmotne podlahy.';
COMMENT ON COLUMN fundamental_snapshots.goodwill IS
    'Goodwill. Od podlahy se odecita - pri rozbite tezi se odepisuje prvni.';
COMMENT ON COLUMN fundamental_snapshots.intangibles IS
    'Nehmotna aktiva mimo goodwill. Odecitaji se ze stejneho duvodu.';
