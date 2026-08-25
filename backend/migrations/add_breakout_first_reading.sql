-- ============================================================================
--  Breakout Investors: zapamatovat si PRVNÍ čtení, ne jen to poslední
-- ============================================================================
--  Date: 2026-08-25
--
--  Jejich watchlist je jediný zdroj v téhle aplikaci, který dává padatelnou
--  předpověď: `upside_ratio` k datu, z něhož se dopočítá cílová cena. Gomes
--  dává čáru bez data, oni dávají cíl s datem. To se dá po roce změřit — a
--  teprve pak se dá zodpovědně říct, jestli si jejich hlas zaslouží váhu.
--
--  Jenže `breakout_sync.sync_watchlist()` při každém pollu přepisuje
--  `price_at_read` i `implied_target` novými hodnotami. `first_seen_at` se
--  zachovává správně, takže hodiny běží — ale startovní čára, proti které se
--  ten čas měří, se při druhém pollu ztratí. Za rok by tabulka řekla „sledujeme
--  je 365 dní" a nevěděla, odkud.
--
--  Tyhle dva sloupce se zapisují JEDNOU, při vzniku řádku, a víc se jich nikdo
--  nedotkne. Je to táž kázeň jako u posudků nálezů: zápis je tvrzení učiněné
--  v jednom okamžiku a nepřepisuje se.
--
--  Dorovnání existujících 28 řádků: kopíruje dnešní čtení. U nich to není
--  cena při jejich přidání — je to cena, za kterou to stálo v neděli 23. 8.
--  2026, kdy poller poprvé běžel. `breakout_lookup.POLLING_STARTED` už tenhle
--  rozdíl zná a `seen_added` podle něj rozlišuje jména, u kterých jsme přidání
--  opravdu viděli. Dorovnaná hodnota tedy není lež, jen slabší údaj — a pozná
--  se podle data.
--
--  Safe to re-run.
-- ============================================================================

ALTER TABLE breakout_watchlist
    ADD COLUMN IF NOT EXISTS price_at_first_seen NUMERIC(12, 4);

ALTER TABLE breakout_watchlist
    ADD COLUMN IF NOT EXISTS target_at_first_seen NUMERIC(12, 4);

UPDATE breakout_watchlist
   SET price_at_first_seen = price_at_read
 WHERE price_at_first_seen IS NULL
   AND price_at_read IS NOT NULL;

UPDATE breakout_watchlist
   SET target_at_first_seen = implied_target
 WHERE target_at_first_seen IS NULL
   AND implied_target IS NOT NULL;

-- Cíl bez ceny, ze které vznikl, se nedá ověřit ani přečíst. Stejný constraint
-- jako u dvojice price_at_read / implied_target o pár sloupců vedle.
ALTER TABLE breakout_watchlist
    DROP CONSTRAINT IF EXISTS first_target_has_its_price;
ALTER TABLE breakout_watchlist
    ADD CONSTRAINT first_target_has_its_price CHECK (
        target_at_first_seen IS NULL OR price_at_first_seen IS NOT NULL
    );

ALTER TABLE breakout_watchlist
    DROP CONSTRAINT IF EXISTS first_price_is_a_price;
ALTER TABLE breakout_watchlist
    ADD CONSTRAINT first_price_is_a_price CHECK (
        price_at_first_seen IS NULL OR price_at_first_seen > 0
    );

COMMENT ON COLUMN breakout_watchlist.price_at_first_seen IS
    'Kurz pri PRVNIM cteni. Zapisuje se jednou a neprepisuje - je to startovni cara mereni.';
COMMENT ON COLUMN breakout_watchlist.target_at_first_seen IS
    'Jejich dopoctny cil pri prvnim cteni. Jedina padatelna predpoved, kterou od nich mame.';
