"""Vercel serverless entry point for the IMPCC CP-SAT backend + frontend host.

Serves:
  GET  /            → the frontend (index.html)
  GET  /solver.js   → the in-browser solver script
  GET  /health      → liveness
  POST /generate    → CP-SAT solve (ranked, valid timetables)
  GET  /docs        → Swagger UI

The solver modules (cp_solver.py, solver.py) and the static assets (index.html,
solver.js) live at the repo root and are bundled into this function via
`includeFiles` in vercel.json.
"""
import os
import sys
import time
import pathlib

# Make the repo root importable (parent of api/) so cp_solver / solver resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import cp_solver as CS
import llm_translate
from solver import UNITS, SECTIONS, TEACHER_FULL, DAYS, SLOTS, DEFAULT_CONSTRAINTS

app = FastAPI(
    title="IMPCC Timetable Generator API",
    description="CP-SAT solver for IMPCC (H-8) Inter 1st-shift timetables (ICS & I.Com).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _find_root() -> pathlib.Path:
    """Locate the directory holding index.html / solver.js (robust to bundling)."""
    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parent.parent,   # api/.. = project root
        here.parent,          # api/ (if assets were copied alongside)
        pathlib.Path.cwd(),
    ]
    for c in candidates:
        if (c / "index.html").exists() or (c / "solver.js").exists():
            return c
    return here.parent.parent


@app.get("/", include_in_schema=False)
def home():
    root = _find_root()
    index = root / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return JSONResponse({"ok": True, "service": "impcc-timetable-generator",
                         "hint": "frontend assets not bundled"}, status_code=404)


@app.get("/solver.js", include_in_schema=False)
def solver_js():
    root = _find_root()
    f = root / "solver.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript")
    return JSONResponse({"detail": "solver.js not found"}, status_code=404)


class GenerateRequest(BaseModel):
    # Vercel Hobby gives 1 vCPU + a 300s cap, so defaults are tuned for that:
    # 20s reliably returns the best-known 560 without needing a 45s prove-optimal run.
    time_limit: int = Field(default=45, ge=1, le=300,
                            description="seconds per CP-SAT seed (45s returns best 560; ~120s proves optimality)")
    n_seeds: int = Field(default=1, ge=1, le=4,
                         description="number of randomized optimization seeds")
    max_solutions: int = Field(default=0, ge=0,
                               description="cap on returned solutions (0 = no cap)")
    constraints: dict = Field(default=None,
                              description="optional faculty-constraint overrides (see constraints_schema.md)")


class TranslateRequest(BaseModel):
    text: str = Field(..., description="the natural-language constraint statement")
    teacher: str = Field(default=None, description="optional faculty member name")


def grids_to_dict(grids):
    out = {}
    for sec in SECTIONS:
        g = grids[sec["key"]]
        rows = []
        for d in range(5):
            row = []
            for s in range(5):
                u = UNITS[g[d][s]]
                row.append([u["subject"], TEACHER_FULL[u["teacher"]]])
            rows.append(row)
        out[sec["key"]] = rows
    return out


@app.get("/health")
def health():
    return {"ok": True, "service": "impcc-timetable-generator", "solver": "cp-sat"}


@app.get("/constraints")
def constraints():
    """Return the default faculty constraints (the 'system language' data)."""
    return {"defaults": DEFAULT_CONSTRAINTS, "schema_url": "/constraints"}


@app.post("/translate")
def translate(req: TranslateRequest):
    """Translate a natural-language constraint into the system schema via the LLM."""
    if not (req.text or "").strip():
        return {"error": "text is required"}
    result = llm_translate.translate_constraints(req.text.strip(), req.teacher)
    return result


@app.post("/generate")
def generate(req: GenerateRequest):
    t0 = time.time()
    ranked, any_optimal = CS.generate_ranked(
        n_seeds=req.n_seeds,
        time_per_seed=req.time_limit,
        max_solutions=req.max_solutions,
        constraints=req.constraints,
    )
    solutions = []
    for sc, g in ranked:
        solutions.append({"score": sc, "timetable": grids_to_dict(g)})

    return {
        "solver": "cp-sat",
        "solutions": solutions,
        "total_found": len(ranked),
        "optimal": any_optimal,
        "best_score": ranked[0][0] if ranked else None,
        "worst_score": ranked[-1][0] if ranked else None,
        "elapsed_seconds": round(time.time() - t0, 2),
        "meta": {
            "days": DAYS,
            "slots": SLOTS,
            "section_order": [s["key"] for s in SECTIONS],
        },
    }
