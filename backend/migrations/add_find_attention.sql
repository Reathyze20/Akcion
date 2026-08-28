-- ============================================================================
--  Skóre pozornosti u posudku nálezu
-- ============================================================================
--  Date: 2026-08-25
--
--  Nálezy uměly odpovědět „smím to koupit" (nákupní brána) a neuměly
--  odpovědět „mám tomu věnovat čas". U vlastního nápadu je přitom první
--  odpověď skoro vždycky stejná: pásmo vyjde MIMO_METODIKU, protože Gomes pro
--  tu firmu nevydal čáry, a brána se zastaví na semaforu dřív, než se podívá
--  na firmu. Dvanáct nápadů pak není podle čeho seřadit.
--
--  `attention` drží celý výsledek rubriky (`app/services/find_attention.py`):
--  body, dosažitelný strop, pět pilířů s vlastními důvody a větu, co by tím
--  nejvíc pohnulo.
--
--  Proč se to UKLÁDÁ, když je to čistá funkce uloženého spisu
--  ---------------------------------------------------------
--  Protože váhy v rubrice jsou investiční rozhodnutí a budou se měnit.
--  Kdyby se skóre počítalo až při čtení, změna váhy by přepsala i to, co
--  aplikace tvrdila loni — a řada posudků je tu právě proto, aby šlo číst, jak
--  se čtení v čase měnilo. Stejná kázeň jako u deníku skóre: zápis je tvrzení
--  učiněné v jednom okamžiku a nepřepisuje se.
--
--  `attention_points` a `attention_ceiling` jsou vytažené vedle JSONB kvůli
--  řazení a kvůli CHECK constraintu. Dvojice body/strop se nesmí rozejít:
--  skóre bez stropu se čte jako známka ze sta, a to je přesně to, čemu se
--  tahle rubrika vyhýbá.
--
--  Safe to re-run.
-- ============================================================================

ALTER TABLE own_find_assessments
    ADD COLUMN IF NOT EXISTS attention JSONB;

ALTER TABLE own_find_assessments
    ADD COLUMN IF NOT EXISTS attention_points NUMERIC(5, 1);

ALTER TABLE own_find_assessments
    ADD COLUMN IF NOT EXISTS attention_ceiling NUMERIC(5, 1);

-- Body bez stropu jsou známka ze sta. Buď obojí, nebo nic.
ALTER TABLE own_find_assessments
    DROP CONSTRAINT IF EXISTS attention_points_have_a_ceiling;
ALTER TABLE own_find_assessments
    ADD CONSTRAINT attention_points_have_a_ceiling CHECK (
        (attention_points IS NULL AND attention_ceiling IS NULL)
        OR (attention_points IS NOT NULL AND attention_ceiling IS NOT NULL)
    );

-- Nad strop se nedá dostat a záporné skóre rubrika nevydává. Kdyby ano, je to
-- chyba ve vahách a databáze ji má zastavit dřív, než se objeví na obrazovce.
ALTER TABLE own_find_assessments
    DROP CONSTRAINT IF EXISTS attention_within_its_ceiling;
ALTER TABLE own_find_assessments
    ADD CONSTRAINT attention_within_its_ceiling CHECK (
        attention_points IS NULL
        OR (
            attention_points >= 0
            AND attention_ceiling >= 0
            AND attention_ceiling <= 100
            AND attention_points <= attention_ceiling
        )
    );

-- Číslo bez rozpisu pilířů je neobhajitelné skóre. Sloupec `attention` nese
-- důvod ke každému dílu, takže se nesmí ztratit, když čísla existují.
ALTER TABLE own_find_assessments
    DROP CONSTRAINT IF EXISTS attention_shows_its_work;
ALTER TABLE own_find_assessments
    ADD CONSTRAINT attention_shows_its_work CHECK (
        attention_points IS NULL OR attention IS NOT NULL
    );

CREATE INDEX IF NOT EXISTS idx_own_find_assessments_attention
    ON own_find_assessments(find_id, attention_points DESC);

COMMENT ON COLUMN own_find_assessments.attention IS
    'Rubrika pozornosti: body, strop, pet piliru s duvody, veta co by pohnulo.';
COMMENT ON COLUMN own_find_assessments.attention_ceiling IS
    'Kolik bodu o teto firme VUBEC jde ziskat. Strop pod 100 = chybi vstupy, ne spatna firma.';
