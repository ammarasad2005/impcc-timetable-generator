-- 003_global_constraints.sql — ONE shared faculty-constraint set (additive)
--
-- Today each `published` row (one per population: inter-1 / bs-1 / inter-2)
-- carries its OWN constraints snapshot. Constraint edits are published only
-- for the population the admin currently has selected, so the three rows
-- silently diverge (observed live: Yasir Kareem P1,P2,P3 on inter-1 while
-- bs-1 and inter-2 kept serving P1,P2,P4).
--
-- Constraints are a property of the FACULTY MEMBER, not of a population:
-- an unscoped personal rule applies to that teacher's timetable everywhere
-- ("the faculty's own individual timetable"); department/department-stream
-- restriction is expressed INSIDE the rule itself via scope.populations /
-- scope.streams / scoped rule kinds (allowed_slots_in_stream, …). Therefore
-- constraint state moves to a single global row.
--
-- Migration: purely ADDITIVE + one row seeded from the NEWEST published
-- constraints snapshot (the most recent admin edit). The per-population
-- `published.constraints` column is left in place as a legacy mirror — the
-- new client writes it too (so older cached frontends keep functioning for
-- their own population) but no longer READS it when the global row exists.
--
-- Safe to re-run.

CREATE TABLE IF NOT EXISTS global_constraints (
  id          smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  constraints jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE global_constraints ENABLE ROW LEVEL SECURITY;

-- readable by EVERYONE (same policy shape as `published`)
DROP POLICY IF EXISTS "public read global_constraints" ON global_constraints;
CREATE POLICY "public read global_constraints"
  ON global_constraints FOR SELECT USING (true);

-- writable only by signed-in users
DROP POLICY IF EXISTS "auth write global_constraints" ON global_constraints;
CREATE POLICY "auth write global_constraints"
  ON global_constraints FOR INSERT TO authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "auth update global_constraints" ON global_constraints;
CREATE POLICY "auth update global_constraints"
  ON global_constraints FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

-- seed from the newest published constraints snapshot, if any (first run only)
INSERT INTO global_constraints (id, constraints, updated_at)
SELECT 1, p.constraints, p.updated_at
  FROM published p
 WHERE p.constraints IS NOT NULL
 ORDER BY p.updated_at DESC
 LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- ---- verify ---------------------------------------------------------------
-- SELECT id, updated_at, jsonb_array_length(to_jsonb(constraints)) IS NULL FROM global_constraints;
-- SELECT constraints->'Yasir' FROM global_constraints;
