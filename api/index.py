"""Vercel serverless entry point for the IMPCC CP-SAT backend.

Vercel serves the `app` object (FastAPI/ASGI). The routes live under
`/api/index/*` and are exposed at clean URLs (`/health`, `/generate`, `/docs`)
via the rewrites in vercel.json.

The solver modules (cp_solver.py, solver.py) live at the repo root and are
bundled into this function via `includeFiles` in vercel.json.
"""
import os
import sys
import time

# Make the repo root importable (parent of api/) so cp_solver / solver resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import cp_solver as CS
from solver import UNITS, SECTIONS, TEACHER_FULL, DAYS, SLOTS

app = FastAPI(
    title="IMPCC Timetable Generator API (Vercel)",
    description="CP-SAT solver for IMPCC (H-8) Inter 1st-shift timetables (ICS & I.Com).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    # Vercel Hobby gives 1 vCPU + a 300s cap, so defaults are tuned for that:
    # 20s reliably returns the best-known 560 without needing a 45s prove-optimal run.
    time_limit: int = Field(default=20, ge=1, le=300,
                            description="seconds per CP-SAT seed")
    n_seeds: int = Field(default=1, ge=1, le=4,
                         description="number of randomized optimization seeds")
    max_solutions: int = Field(default=0, ge=0,
                               description="cap on returned solutions (0 = no cap)")


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


@app.post("/generate")
def generate(req: GenerateRequest):
    t0 = time.time()
    ranked, any_optimal = CS.generate_ranked(
        n_seeds=req.n_seeds,
        time_per_seed=req.time_limit,
        max_solutions=req.max_solutions,
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
