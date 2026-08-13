"""Shared metrics + teacher-schedule helpers for reporting/export."""
import json
from collections import defaultdict

DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
SLOTS = ["P1", "P2", "P3", "P4", "P5"]

def load():
    return json.load(open("solutions.json"))

def subject_counts(key):
    """Reference per-section subject loads."""
    base = {
        "I.COM-I": [("English", 4), ("Urdu", 4), ("Tarjama-tul-Quran", 2),
                    ("Islamic Education", 2), ("Principles of Accounting", 5),
                    ("Principles of Economics", 3), ("Principles of Commerce", 3),
                    ("Business Mathematics", 2)],
        "I.COM-II": [("English", 4), ("Urdu", 4), ("Tarjama-tul-Quran", 2),
                     ("Pakistan Studies", 2), ("Principles of Accounting", 5),
                     ("Commercial Geography", 3), ("Statistics", 2)],
        "ICS-I": [("English", 4), ("Urdu", 4), ("Tarjama-tul-Quran", 2),
                  ("Islamic Education", 2), ("Computer Science", 4),
                  ("Mathematics", 5)],
        "ICS-II": [("English", 4), ("Urdu", 4), ("Tarjama-tul-Quran", 2),
                   ("Pakistan Studies", 2), ("Computer Science", 4),
                   ("Mathematics", 5)],
    }
    stream, year, sec = key.rsplit("-", 2)
    st = f"{stream}-{year}"
    subs = dict(base[st])
    # stream-specific extras
    if st == "I.COM-II":
        if sec == "A":
            subs["Computer Studies"] = 3
        else:
            subs["Banking"] = 3
    if st == "ICS-I":
        if sec in ("A", "B"):
            subs["Physics"] = 4
        else:
            subs["Statistics"] = 4
    if st == "ICS-II":
        if sec == "A":
            subs["Statistics"] = 4
        else:
            subs["Economics/Statistics"] = 4
    return subs

def section_metrics(tt):
    """Per-section shuffle counts by credit tier."""
    out = defaultdict(int)
    for key, grid in tt.items():
        counts = subject_counts(key)
        slots_by_subj = defaultdict(set)
        for d in range(5):
            for s in range(5):
                slots_by_subj[grid[d][s][0]].add(s)
        for subj, c in counts.items():
            n = len(slots_by_subj[subj])
            if n > 1:
                out[c] += 1   # credit tier -> #shuffled subjects
    return dict(out)

def teacher_schedule(tt):
    """teacher full name -> list of (day, slot, section, subject)."""
    out = defaultdict(list)
    for key, grid in tt.items():
        for d in range(5):
            for s in range(5):
                subj, t = grid[d][s]
                for name in t.split(" / "):
                    out[name.strip()].append((d, s, key, subj))
    for name in out:
        out[name].sort()
    return dict(out)

# per-teacher constraint notes for display
RULES = {
    "Prof. Muhammad Naeem": "Mon P1 & P2 free",
    "Prof. Syed Assad Abbas": "ICS fills P1 & P2 daily · Bus-Math in P3 · no I.Com Friday",
    "Prof. Babar Jahangir": "ICS fills P1 & P2 daily",
    "Prof. Ishfaq Ahmed": "P1 ≥ 4 days · never P5",
    "Prof. Dr. Yasir Kareem": "only P1, P2, P4",
    "Prof. Abdul Basit": "P1 ≥ 4 days · never P5 · no day off",
    "Prof. Amir Rasheed": "never P1 · never P5",
    "Prof. Husnul Amin": "never P1 · never P5",
    "Prof. Millat Khan": "never P1",
    "Prof. Naeem Asghar": "never P1 · never P2",
    "Prof. Tanveer Ahmed": "Thu & Fri only · P1–P3",
    "Visiting-1": "placeholder visiting faculty",
    "Visiting-2": "placeholder visiting faculty",
    "Visiting-3": "placeholder visiting faculty",
}
