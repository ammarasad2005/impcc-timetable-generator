"""IMPCC timetable generator — FastAPI backend wrapping the CP-SAT solver.

Run locally:  uvicorn backend.main:app --host 0.0.0.0 --port 8080
Deploy:       see backend/README.md and deploy.sh (Google Cloud Run).

Endpoints:
  GET  /health    → liveness
  POST /generate  → run CP-SAT, return ranked, valid timetables as JSON
"""
import os
import sys
import time

# make the repo root importable so we can import cp_solver / solver
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import cp_solver as CS
import llm_translate
from solver import UNITS, SECTIONS, TEACHER_FULL, DAYS, SLOTS, DEFAULT_CONSTRAINTS

app = FastAPI(
    title="IMPCC Timetable Generator API",
    description="CP-SAT solver for IMPCC (H-8) Inter 1st-shift timetables (ICS & I.Com).",
    version="1.0.0",
)

# The frontend is a static site on Vercel; allow cross-origin calls from anywhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    time_limit: int = Field(default=45, ge=1, le=300,
                            description="seconds per CP-SAT seed (45s proves optimality)")
    n_seeds: int = Field(default=2, ge=1, le=8,
                         description="number of randomized optimization seeds")
    max_solutions: int = Field(default=0, ge=0,
                               description="cap on returned solutions (0 = no cap)")
    constraints: dict = Field(default=None,
                              description="optional faculty-constraint overrides (see constraints_schema.md)")


class TranslateRequest(BaseModel):
    text: str = Field(..., description="the natural-language constraint statement")
    teacher: str = Field(default=None, description="optional faculty member name")


def grids_to_dict(grids):
    """Convert internal grids (day -> slot -> unit index) to JSON-friendly form."""
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
    return {"defaults": DEFAULT_CONSTRAINTS}


@app.post("/translate")
def translate(req: TranslateRequest):
    if not (req.text or "").strip():
        return {"error": "text is required"}
    return llm_translate.translate_constraints(req.text.strip(), req.teacher)


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
