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
