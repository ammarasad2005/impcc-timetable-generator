# IMPCC — Timetable Versioning (originals → versions → history)

Saved timetables are not a flat list any more. They form a **version tree**: originals
saved from the main page, versions derived from them (or from other versions), and an
append-only history of the actions that created them.

## 1. Data model (`saved_timetables`)

| Column | Meaning |
|---|---|
| `kind` | `"original"` (saved from the main page, or promoted by a replace) or `"version"` (derived). |
| `parent_id` | the timetable this one was derived from — an original or another version (`null` for a fresh original). |
| `actions` | JSON snapshot of what produced it: `{ tweaks:[], edits:[], engagement:{covered,total} }`. |
| `archived` | `true` when this original was **replaced** (it stays visible as 📦 archived, in history). |

The whole tree lives in the admin's `saved_timetables` (owner RLS: select / insert /
update / delete). New columns: `kind`, `parent_id`, `actions`, `archived`.

## 2. Action history (`timetable_history`)

Append-only (owner RLS: select + insert only — the client can never delete it):

| Column | Meaning |
|---|---|
| `action` | `create_original` · `create_version` · `replace_original` · `delete_timetable` · `push` · `unpush`. |
| `timetable_id` / `parent_id` | the rows involved (may dangle after a version is deleted). |
| `detail` | `{ name, from, replaced, kind, score }` — enough to reconstruct *what happened* even after the timetable row is gone. |

**Deleting a version wipes it from `saved_timetables`; the history of actions remains.**

## 3. Flows

- **Save (main page)** → `kind=original`, `parent_id=null`, `actions` snapshot. History: `create_original`.
- **Load a saved timetable** → it becomes the *source*. Tweak + re-optimise, then **Save**:
  - **Keep as version** → `kind=version`, `parent_id=source.id`. History: `create_version`.
  - **Replace original** → new row `kind=original` with `parent_id=root-of-chain.id`; the
    root original is `archived`. History: `replace_original`.
- **Version chains** — derive from a version the same way (`parent_id` points to it); the
  "root original" of a chain is found by walking `parent_id` up to the first original.
- **Push** — any original or version (still a single public singleton). History: `push`/`unpush`.
- **Delete** — any original or version. History: `delete_timetable`.

## 4. Frontend

- **💾 Saved** tab: originals (🗂), versions (🧬, with "from …" + actions chips), and a
  **📦 archived originals** section for replaced ones. Each card: Load / Push / Delete.
- **🕘 History** tab: the action log, newest first.
- **Save** is context-aware: with a loaded source it opens the version dialog
  (🔀 keep / ♻️ replace); otherwise it saves a new original.
- A fresh **Generate** run clears the source (the new pool is no longer derived from a
  saved timetable).
