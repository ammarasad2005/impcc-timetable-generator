"""Run the full generation and save results."""
import json, time
import cp_solver as CS
from solver import UNITS, SECTIONS, TEACHER_FULL, DAYS, SLOTS

def grids_to_dict(grids):
    """Convert to JSON-friendly: sec -> day -> [ (subject, teacher_full), x5 ]."""
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

def main():
    t0 = time.time()
    ranked = CS.generate_many(n_seeds=12, time_per_seed=16, verbose=True)
    # a couple of longer, deeper runs for near-optimal quality
    extra = CS.generate_many(n_seeds=2, time_per_seed=45, verbose=True)
    merged = {}
    for sc, g in ranked + extra:
        from solver import canonical
        merged.setdefault(canonical(g), (sc, g))
    ranked = sorted(merged.values(), key=lambda x: x[0])

    payload = {
        "meta": {
            "days": DAYS, "slots": SLOTS,
            "timings": ["08:30-09:10", "09:10-09:50", "09:50-10:30",
                        "Break 10:30-10:55", "10:55-11:35", "11:35-12:15"],
            "section_order": [s["key"] for s in SECTIONS],
        },
        "solutions": [
            {"score": sc, "timetable": grids_to_dict(g)} for sc, g in ranked
        ],
    }
    with open("solutions.json", "w") as f:
        json.dump(payload, f, indent=1)
    print(f"\nTOTAL distinct: {len(ranked)}  in {time.time()-t0:.0f}s")
    print("score distribution (top 20):", [s for s, _ in ranked[:20]])
    print("score distribution (last 10):", [s for s, _ in ranked[-10:]])

if __name__ == "__main__":
    main()
