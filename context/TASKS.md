# Tasks

Folder owners: robot/ = Kian, software/ = Shiv, server/ = Shyan, demo/ and business/ = Mat and Gio.

Package details and ready-to-paste prompts: `context/KICKOFF.md` (K0, S0x, Y0x, B0, B1) and `context/MASTER_PLAN.md` section 5 (everything else).

| Task | Owner | Folder | Status |
|------|-------|--------|--------|
| K0 Flexiv bring-up: connect, pinned RDK, read pose + force (answers in `context/BRINGUP_FINDINGS.md`) | Kian | robot/ | Done (connected 14 Nov: Rizon4-062157, robot software v3.9.3, flexivrdk 1.7.0, licence RDK-Professional, K_x_nom [10000,10000,10000,1500,1500,1500], no wrist F/T sensor). Handle + tool, soft hold and free axis moved to K2/K3/K4 |
| K1 `robot/arm.py` per MASTER_PLAN 4.3 (clamps, trips, watchdog, stiffness worker) | Kian | robot/ | In progress (drove the real arm 14 Nov; connect() no longer clears faults or enables a live arm; open: ZeroFTSensor test, config.json values) |
| K2 On-arm safety checks and technician sign-off (`robot/safety_check.py`, `robot/SAFETY.md`) | Kian | robot/ | In progress (15 checks written, sim dry run 13 PASS / 0 FAIL / 2 not reproducible in sim; NOT run on the arm, NOT signed off: needs the arm, the handle and the technician) |
| K3 Tuning measurements (`robot/tune.py`, `robot/TUNING.md`) | Kian | robot/ | In progress (recommendations from the 14 Nov motion test: keep K_ASSIST 400, K_RESIST 300, K_WALL 500, K_HOLD 300; `tune.py` written; on-arm measurements pending) |
| K4 Start pose, seating, workspace (`robot/config.json`, `robot/SETUP.md`) | Kian | robot/ | In progress (Layout B: reach along world y at x ≈ 0.50; config.json still placeholders until the handle is mounted and RehabHandle is the active tool) |
| K5 Run book and `robot/recover.py` | Kian | robot/ | In progress (RUNBOOK updated with the 14-15 Nov findings and proposed pitch roles; open: e-stop location, `Start Demo.bat` cold start, roles confirmed at a rehearsal) |
| S0a `software/metrics.py`: ROM, path error, force, SPARC, contribution | Shiv | software/ | Done |
| S0b `software/reps.py`: rep detection | Shiv | software/ | Done |
| S0c `software/paths.py`: line path, min-jerk, lead target | Shiv | software/ | Done |
| S0d `software/sim_patient.py`: simulated hand and patient | Shiv | software/ | Done |
| S1 `software/sim_arm.py` (same interface as Arm) | Shiv | software/ | Done (patient timing follow-up fixed, 39d9d0b) |
| S2 `software/controller.py` (dial to target and stiffness) | Shiv | software/ | Done |
| S3 `software/adapt.py` (auto dial) | Shiv | software/ | Done |
| S4 `software/engine.py` (100 Hz loop, rep state machine, hands-off rule) | Shiv | software/ | Done |
| S5 `software/assess.py` (SHOULD) | Shiv | software/ | Done |
| Y0a `server/contract.py`: Sample, RepResult, SessionSummary | Shyan | server/ | Done |
| Y0b `server/db.py`: SQLite storage | Shyan | server/ | Done |
| Y0c `server/simulate.py`: 14 days of labelled simulated history | Shyan | server/ | Done |
| Y0d `server/export.py`: JSON/CSV exports for Mat and Gio | Shyan | server/ | Done |
| Y1 Contract v1 and `server/api.py` (REST + WebSocket) | Shyan | server/ | Done |
| Y2 `server/run.py` and `server/watch.py` | Shyan | server/ | Done (--mock and --sim) |
| Y3 `server/note.py` session note | Shyan | server/ | Done |
| Y4 End-to-end sim test | Shyan | server/ | Done (mock and sim variants pass: I2 green) |
| Y5 `server/API.md` handover for Mat and Gio | Shyan | server/ | Done |
| L0 `/screens/` mount, common.js, style.css | Shyan | server/ | Done |
| L1 Patient screen | Shyan | server/ | Done (small fix: hand dot overlaps track-end labels) |
| L2 Physio screen | Shyan | server/ | Todo |
| L3 Operator console | Shyan | server/ | Todo |
| Y6 `POST /api/arm/prepare` (fault check + zero_force before the first real session; no home) | Shyan | server/ | Done |
| L4 QR / LAN phone access | Shyan | server/ | Todo (after L2) |
| Help Kian get the arm connected (K0): organisers/technician for Remote mode + licence | Shyan | n/a | Done (connected 14 Nov, licence RDK-Professional) |
| Arm motion test stages 3-5 (soft hold, free axis, engine dry run) | Shyan | server/hw/ | Todo (needs the robot) |
| B0 Therapist interviews in Leukerbad (3 by Sat evening, 5 by Sun midday) | Mat, Gio | business/ | Todo |
| B1 Claims table with checked sources | Mat, Gio | business/ | Todo |
| B2 Verify the claims list (MASTER_PLAN section 7) | Mat, Gio | business/ | Todo |
| B3 Market model | Mat, Gio | business/ | Todo |
| B4 Deck | Mat, Gio | demo/ | In progress (draft in demo/pitch-deck/) |
| B5 Script, rehearsal, backup video | Mat, Gio | demo/ | Sunday |
| B6 Website and screens | Mat, Gio | demo/ | In progress (site live at vitarehab.netlify.app, app at vitastation.netlify.app; not yet using server/exports/) |
| B7 Pilot outreach drafts | Mat, Gio | business/ | Sunday |
| E1 Engine exercise presets: reach, push, pull (reversed), armtest (isometric) per context/EXERCISE_MAP.md (swap: Shyan works in software/ for this) | Shyan | software/ | Done on SimArm (software/EXERCISES.md); not yet run on the real arm |
| E2 Server `exercise` field on /api/session/start, state, reps, DB, API.md (swap: Shiv works in server/ for this) | Shiv | server/ | Done (GET /api/exercises, note, mock, patient screen; all four run through the real engine on SimArm; patient screen not yet checked in a browser) |
| Register team by 17:00 on 14 Nov (name, track, members, 1 hardware item, sign agreement) | Shyan | n/a | Done (hardware: Flexiv Rizon 4) |
