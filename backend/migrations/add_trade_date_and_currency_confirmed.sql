-- Migration: datum obchodu a potvrzená měna
-- Date: 2026-08-23
--
-- Dvě samostatné opravy, obě téhož druhu: aplikace tvrdila něco, co
-- nevěděla.
--
-- 1. `investment_logs.trade_date` — dosud existoval jen `created_at`, tedy
--    kdy byl řádek NAPSANÝ. Tři zbytkové pozice zavřené 23. 8. 2026 se proto
--    četly jako tři obchody v jednom týdnu a spustily brzdu proti
--    přeobchodování. NULL znamená „nevím" a čtenáři spadnou zpátky na
--    created_at, ne na dnešek.
--
-- 2. `positions.currency_confirmed` — kontrola měny čte příponu tickeru
--    (.V = TSX Venture = CAD) a když nesedí s uloženou měnou, tvrdí, že
--    hodnota portfolia je špatně. U IMP.V a KUYA.V je ale správně EUR
--    (€0,459 × kurz = $0,537 proti OTC kvótě $0,534; jako CAD by to bylo
--    o 38 % vedle) a přípona je jen přezdívka z Gomesova trackeru. Která
--    strana je špatně, ví jenom majitel — tohle je jeho odpověď.

ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS trade_date DATE;

CREATE INDEX IF NOT EXISTS idx_investment_logs_trade_date
    ON investment_logs (trade_date);

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS currency_confirmed BOOLEAN NOT NULL DEFAULT FALSE;
