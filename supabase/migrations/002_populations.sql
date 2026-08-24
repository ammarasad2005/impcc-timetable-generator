-- 002_populations.sql — per-population timetable state (additive, idempotent)
--
-- The system now runs THREE timetable populations:
--   inter-1 : Intermediate, 1st shift        (legacy row id=1)
--   bs-1    : BS departments, 1st shift      (id=2)
--   inter-2 : Intermediate, 2nd shift        (id=3)
--
-- Migration strategy: purely ADDITIVE.
--   * `published` + `pushed_timetable` gain a UNIQUE `population` column; the
--     existing singleton rows become population='inter-1' — the legacy client
--     (id=1 upserts) keeps working untouched and stays scoped to inter-1.
--   * `published` also gains `general_instructions` + `timetable_config`
--     jsonb columns (PR-5/PR-6 write them; defaults keep old rows valid).
--   * `saved_timetables` + `timetable_history` gain `population` with DEFAULT
--     'inter-1' — every existing row (the current admin's saves/logs) is
--     scoped to inter-1 automatically.
--   * `workspace` (legacy, unused by the current UI) is intentionally untouched.
--
-- RLS policies are table-level (whole-row), so the new columns are covered by
-- the existing policies: public read on published/pushed; owner-only on
-- saved/history. No policy changes required.
--
-- Safe to re-run (IF NOT EXISTS / WHERE-guarded UPDATEs).

-- ---- published: one row per population ----------------------------------
ALTER TABLE published ADD COLUMN IF NOT EXISTS population text;
CREATE UNIQUE INDEX IF NOT EXISTS published_population_key ON published (population);
UPDATE published SET population = 'inter-1' WHERE population IS NULL AND id = 1;
UPDATE published SET population = 'inter-1' WHERE population IS NULL AND id <> 1 AND (SELECT count(*) FROM published) = 1;
ALTER TABLE published ADD COLUMN IF NOT EXISTS general_instructions jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE published ADD COLUMN IF NOT EXISTS timetable_config jsonb NOT NULL DEFAULT '{}'::jsonb;

-- ---- pushed_timetable: one pushed timetable per population ---------------
ALTER TABLE pushed_timetable ADD COLUMN IF NOT EXISTS population text;
CREATE UNIQUE INDEX IF NOT EXISTS pushed_population_key ON pushed_timetable (population);
UPDATE pushed_timetable SET population = 'inter-1' WHERE population IS NULL AND id = 1;
UPDATE pushed_timetable SET population = 'inter-1' WHERE population IS NULL AND id <> 1 AND (SELECT count(*) FROM pushed_timetable) = 1;

-- ---- saved_timetables / timetable_history: population scope --------------
ALTER TABLE saved_timetables ADD COLUMN IF NOT EXISTS population text NOT NULL DEFAULT 'inter-1';
ALTER TABLE timetable_history ADD COLUMN IF NOT EXISTS population text NOT NULL DEFAULT 'inter-1';

-- ---- verify ---------------------------------------------------------------
-- (run manually after applying)
-- SELECT id, population, updated_at FROM published;
-- SELECT id, population, pushed_at FROM pushed_timetable;
-- SELECT population, count(*) FROM saved_timetables GROUP BY 1;
-- SELECT population, count(*) FROM timetable_history GROUP BY 1;
