# IMPCC — Inter (1st Shift) Timetable — Working Notes

Source file: impcc.xlsx (4 sheets)

## Sheet 1: CourseAllocation-Inter1stShift (parsed)

Structure: 2 stream blocks (I.COM rows 6–18, ICS rows 23–32). Columns D/E/F = Sections A/B/C of Year-I, G/H/I = Sections A/B/C of Year-II.

### Sections (11 total)
- I.COM-I: A, B, C
- I.COM-II: A, B, C
- ICS-I: A, B, C
- ICS-II: A, B (no C)

### Per-section subjects (each section = 25 periods/week)
I.COM-I (A/B/C): English 4 (Syed Umair Abid), Urdu 4 (Abdul Basit),
  Tarjama-tul-Quran 2 (Visiting-1), Islamic Education 2 (Visiting-2),
  Accounting 5 (Sikhani), Economics 3 (Yasir Kareem),
  Commerce 3 (Naeem [A,B] / Millat Khan [C]),
  Business Math 2 (Assad Abbas [A,B] / Najam [C]).
  NOT offered: Pak Studies, Commercial Geography, Computer Studies, Banking, Statistics.

I.COM-II (A/B/C): English 4 (Amir Rasheed), Urdu 4 (Ehsam Ullah Baig),
  Tarjama-tul-Quran 2 (Visiting-1), Pak Studies 2 (Ghulam Jilani),
  Accounting 5 (Muhammad Naeem), Commercial Geography 3 (Husnul Amin),
  Statistics 2 (Tanveer Ahmed) [all],
  Computer Studies 3 (Faisal Bashir) [A only],
  Banking 3 (Millat Khan) [B, C only].
  NOT offered: Islamic Education, Economics, Commerce, Business Math.

ICS-I (A/B/C): English 4 (Noor Muhammad), Urdu 4 (Abdul Rauf),
  Tarjama-tul-Quran 2 (Visiting-2), Islamic Education 2 (Visiting-1),
  Computer Science 4 (Babar Jahangir), Mathematics 5 (Assad Abbas),
  Physics 4 (Visiting-3) [A, B only],
  Statistics 4 (Ishfaq Ahmed) [C only].
  NOT offered: Pak Studies, Economics/Statistics.

ICS-II (A/B): English 4 (Syed Umair Abid), Urdu 4 (Abdul Rauf),
  Tarjama-tul-Quran 2 (Visiting-2), Pak Studies 2 (Ghulam Jilani),
  Computer Science 4 (Faisal Bashir), Mathematics 5 (Najam us Saqib),
  Statistics 4 (Ishfaq Ahmed) [A only],
  Economics/Statistics 4 (Naeem Asghar + Ishfaq Ahmed) [B only].
  NOT offered: Islamic Education, Physics.

### Program / Class Incharge
- I.COM Program Incharge: M. Waseem Sikhani (both years)
- ICS Program Incharge: Syed Assad Abbas (both years)
- Class Incharge: I.COM-I A=Dr. Arif, B=Prof. Waseem, C=Prof. Khurram
  I.COM-II A=Prof. Naeem, B=Prof. Amir, C=Prof. G. Jillani
  ICS-I A=Prof. A. Rauf, B=Prof. Faisal, C=(blank)
  ICS-II A=Prof. Najam, B=(blank)

### Teacher loads (periods/week) — allocation only
Muhammad Naeem 21 | Syed Umair Abid 20 | Abdul Rauf 20 | Syed Assad Abbas 19 |
Visiting-1 18 | Visiting-2 16 | M. Waseem Sikhani 15 |
Abdul Basit / Najam us Saqib / Amir Rasheed / Ehsam Ullah Baig / Noor Muhammad / Babar Jahangir 12 each |
Faisal Bashir 11 | Ghulam Jilani 10 | Yasir Kareem / Millat Khan / Husnul Amin 9 each |
Visiting-3 8 | Ishfaq Ahmed 8 (+share of Econ/Stat 4) | Naeem Asghar (share of Econ/Stat 4) | Tanveer Ahmed 6.
Total = 275 = 11 × 25 ✓

### Open questions (Course Allocation)
1. Meaning of '-' (not offered vs TBD teacher).
2. Visiting-1/2/3 → keep as labels or real names?
3. Include ICS-I Section C (missing from Template)?
4. What is "Economics/Statistics" (ICS-II-B)?
5. Name variants / Class Incharge mapping.

## Sheet 2: General Instructions (to review next)
- Start 08:30, 5 periods/day, Mon–Fri, 40 min, break 25 min after 3rd.
- No two periods of same subject in a day.
- Avoid shuffling subject's slot across the week "at the most".
- Accounting & Economics in I.Com-I: one non-overriding period/week/section.

## Sheet 3: FacultyWiseConstraints (to review next)
44 rows; includes Visiting-1/2/3. Many BS-only. Key Inter constraints captured separately.

## Sheet 4: Template (to review next)
5 days × 5 periods grid, Break column after P3. Has 9 sections (ICS-I A,B only — missing C).
Teacher names in template do NOT match current allocation (e.g. English/ICS, Economics teacher, Islamic Studies by Waseem Ahmed Farooq). Template = format/layout reference; allocation = source of truth.

## Confirmed decisions (round 1)
- '-' = subject NOT offered in that section → exclude from that section's timetable.
- Visiting-1/2/3 kept as-is (anonymous labels).
- ICS-I Section C IS included (Statistics group) → 11 sections total.
- 'Economics/Statistics' (ICS-II-B): students pick EITHER Economics (Prof. Naeem Asghar) OR Statistics (Prof. Ishfaq Ahmed). Both run in PARALLEL at the same time in two different rooms, 4 periods/week.
  → Scheduling: one 4-period block/week; BOTH teachers occupied simultaneously (2 rooms).
  → Ishfaq load = 12 (ICS-I-C 4 + ICS-II-A 4 + ICS-II-B 4). Naeem Asghar load = 4 (ICS-II-B Econ, parallel).

## Confirmed decisions (round 2 — General Instructions & Faculty constraints)
- Non-overriding: for each I.Com-I section X, ∃ ≥1 period/week where X has Accounting AND both OTHER sections do NOT have Economics.
- Shuffling (soft, credit-weighted): 5/wk → fixed slot; 4/wk → move only if unavoidable (~98% avoid); 3/wk → 60% keep / 40% ok to shuffle; 2/wk → free. Faculty personal constraints ALWAYS override.
- Class Incharge / Program Incharge: not used in generation.
- '1st period engaged 4 days/week' (Basit, Ishfaq) = teach P1 on ≥4 days.
- 'Engage P1 & P2 in ICS' (Assad, Babar) = fill P1 & P2 with their ICS classes every day; overflow rest.
- 'Engage 3rd period in I.Com' (Assad) = ALL his I.Com (Business Math) classes in P3.
- Tanveer Ahmed = all 6 Statistics periods on Thu & Fri in P1–P3.
- Waseem A. Farooq has no Inter classes → his 'evenly distribute' constraint ignored.
- Visiting-1/2 crossover is intentional; Visiting-3 = ICS-I Physics.

## Confirmed decisions (round 3 — Template & deliverable)
- Template = FORMAT ONLY (regenerate every cell from allocation + constraints).
- Layout: title row, DAYS/P1/P2/P3/Break/P4/P5 header, timing row, 5 day-pairs (subject row + teacher-in-parens row), blank separator. Insert ICS-I Section-C block after ICS-I-B.
- Display names = ALLOCATION sheet names (Tarjama-tul-Quran, Islamic Education, Principles of Commerce, Statistics, Computer Science/Studies).
- Parallel ICS-II-B cell = one cell "Economics / Statistics" + "(Prof. Naeem Asghar / Prof. Ishfaq Ahmed)".
- Deliverable = simple website + data files (xlsx/json) + generator scripts.

