# Tasks

Folder owners: robot/ = Kian, software/ = Shiv, server/ = Shyan, demo/ and business/ = Mat and Gio.

Package details and ready-to-paste prompts: `context/KICKOFF.md` (K0, S0x, Y0x, B0, B1) and `context/MASTER_PLAN.md` section 5 (everything else).

| Task | Owner | Folder | Status |
|------|-------|--------|--------|
| K0 Flexiv bring-up with technician: pinned RDK 1.9.x, read pose + force, handle + payload, soft hold, free axis, answers in robot/BRINGUP.md | Kian | robot/ | In progress |
| K1 `robot/arm.py` per MASTER_PLAN 4.3 (clamps, trips, watchdog, stiffness worker) | Kian | robot/ | In progress |
| K2 On-arm safety checks and technician sign-off (`robot/SAFETY.md`) | Kian | robot/ | Todo |
| K3 Tuning measurements (`robot/TUNING.md`) | Kian | robot/ | Todo |
| K4 Start pose, seating, workspace (`robot/config.json`, `robot/SETUP.md`) | Kian | robot/ | In progress |
| K5 Run book and `robot/recover.py` | Kian | robot/ | In progress |
| S0a `software/metrics.py`: ROM, path error, force, SPARC, contribution | Shiv | software/ | Done |
| S0b `software/reps.py`: rep detection | Shiv | software/ | Done |
| S0c `software/paths.py`: line path, min-jerk, lead target | Shiv | software/ | Done |
| S0d `software/sim_patient.py`: simulated hand and patient | Shiv | software/ | Done |
| S1 `software/sim_arm.py` (same interface as Arm) | Shiv | software/ | Done; follow-up needed: patient timing out of step with engine (LOG S4 blocker) |
| S2 `software/controller.py` (dial to target and stiffness) | Shiv | software/ | Done |
| S3 `software/adapt.py` (auto dial) | Shiv | software/ | Done |
| S4 `software/engine.py` (100 Hz loop, rep state machine, hands-off rule) | Shiv | software/ | Done |
| S5 `software/assess.py` (SHOULD) | Shiv | software/ | Done |
| Y0a `server/contract.py`: Sample, RepResult, SessionSummary | Shyan | server/ | Done |
| Y0b `server/db.py`: SQLite storage | Shyan | server/ | Done |
| Y0c `server/simulate.py`: 14 days of labelled simulated history | Shyan | server/ | Done |
| Y0d `server/export.py`: JSON/CSV exports for Mat and Gio | Shyan | server/ | Done |
| Y1 Contract v1 and `server/api.py` (REST + WebSocket) | Shyan | server/ | Done |
| Y2 `server/run.py` and `server/watch.py` | Shyan | server/ | Done (mock); --sim waits for S4 |
| Y3 `server/note.py` session note | Shyan | server/ | Done |
| Y4 End-to-end sim test | Shyan | server/ | Done (mock); sim variant waits for S1, S4 |
| Y5 `server/API.md` handover for Mat and Gio | Shyan | server/ | Done |
| B0 Therapist interviews in Leukerbad (3 by Sat evening, 5 by Sun midday) | Mat, Gio | business/ | Todo |
| B1 Claims table with checked sources | Mat, Gio | business/ | Todo |
| B2 Verify the claims list (MASTER_PLAN section 7) | Mat, Gio | business/ | Todo |
| B3 Market model | Mat, Gio | business/ | Todo |
| B4 Deck | Mat, Gio | demo/ | Sunday |
| B5 Script, rehearsal, backup video | Mat, Gio | demo/ | Sunday |
| B6 Website and screens | Mat, Gio | demo/ | Waiting on server/exports/ |
| B7 Pilot outreach drafts | Mat, Gio | business/ | Sunday |
| Register team by 17:00 on 14 Nov (name, track, members, 1 hardware item, sign agreement) | Shyan | n/a | Done (hardware: Flexiv Rizon 4) |
