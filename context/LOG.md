# Log

Append-only. Each sync: date/time + name, then 3–5 lines (what changed, what's next, blockers for the others).

**2026-11-14 · Shyan**
- Got the Flexiv Rizon 4. Project locked: pill-cup handover that only releases when vision AND force both confirm a grip. See PROJECT.md.
- Next: Kian does bring-up with a technician (RDK, gripper, force reading). Shiv builds webcam hand detection plus the state machine against a stubbed arm.py.
- Blockers: need to confirm which gripper is fitted to the Rizon and that RDK access is enabled on it.

**2026-11-14 · Shyan**
- Pivoted from pill handover to stroke rehab on the Flexiv: guided mode (assist as needed) and resistance mode. See PROJECT.md and DECISIONS.md.
- Next: Kian gets a handle mounted and impedance control working; Shiv builds both exercise modes against a stub arm.py; Shyan builds the patient screen and dashboard.
- Blockers: need the technician to mount a handle and confirm which RDK control modes are enabled. Agree the CSV log format (Shiv to propose).

**2026-11-14 15:00 · Shyan**
- Added context/KICKOFF.md: ready-to-paste agent packages everyone can start now (K0 bring-up, S0a-d metrics/reps/paths/sim patient, Y0a-d contract/db/simulated history/exports, B0-B1 interviews and claims). New folders server/ (Shyan) and business/ (Mat, Gio).
- Next: context/MASTER_PLAN.md with the frozen arm.py interface, API, full package list, timeline and business plan. It supersedes KICKOFF.md.
- Kian: do NOT pip install flexivrdk unpinned (2.x is the wrong robot family). Pin 1.9.x to the robot software version. The eight answers in K0 freeze the interface, post them in LOG as soon as you have them.
- Shiv: no CSV logging. Your records go to server/contract.py types (Y0a lands first). S0a-d need nothing from anyone.
- Mat, Gio: Leukerbad Clinic lists musculoskeletal, internal medicine and oncology rehab on its site, not neurology. Open interviews with shoulder and arm rehab, not stroke.

**2026-11-14 17:00 · Shyan**
- Added context/MASTER_PLAN.md: verdict, company one-pager, demo script, frozen interfaces (arm 4.3, engine 4.4, contract 4.5, API 4.6), packages K1-K5, S1-S5, Y1-Y5, B2-B7, timeline, claims table, red team. Supersedes KICKOFF.md where they differ; PROJECT.md has a superseded banner.
- Next: Kian K1 and K4 once K0 answers are in; Shiv S1, S2, S3 then S4; Shyan Y1, Y3 then Y2. First integration check on the sim tonight 23:00.
- Kian: K3 must measure handle force with an empty handle versus a relaxed arm (the hands-off rule depends on it) and how long SetCartesianImpedance blocks.
- Shiv: SimArm must report a passive limb load when the patient is present, zero when absent. Contribution uses the out phase only.
- Mat, Gio: no claim marked [U] goes on a slide; [B] claims only after one of you has opened the source. NICE and RATULS are the first two to read.

**2026-11-14 · Shyan · Y0a**
- Y0a done: server/contract.py with Sample, RepResult, SessionSummary including the v1 fields (Sample.phase, Sample.q, RepResult.rescued), to_dict/from_dict, 7 passing tests. Shiv can import `from server.contract import Sample, RepResult, SessionSummary` now.
- Next: Y0b storage, Y0c simulated history, Y0d exports.
