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

**2026-11-14 · Kian · K5**
- K5 done: runbook covers start, fault, shutdown. Files: `robot/RUNBOOK.md`, `robot/recover.py` (connect, print fault state, ClearFault, Enable, restore K_x_nom, Stop; `--check` changes nothing).
- Stub until K2: every `TODO(confirm on arm)` (names, e-stop location, serial, Elements steps, ClearFault behaviour, SwitchMode holds pose) must be checked on the robot. recover.py tested offline only (--help, clean exit without flexivrdk).
- Next: finalise RUNBOOK after K2 sign-off; fill in exact home/zero commands once K1 and Y2 land.
- Blockers: none. Shyan: RUNBOOK assumes `server.run` Ctrl+C calls hold() then close() as in Y2.

**2026-11-14 · Kian · K1**
- K1 done: arm.py matches section 4.3, offline tests pass (18/18), on-arm test pending.
- Serial, force sign, start pose and reach axis are loaded from robot/config.json and are still PLACEHOLDERS (listed in its "placeholders" key); connect() refuses the placeholder serial, home() refuses a placeholder start pose. flexivrdk is imported lazily inside connect().
- Clamps are pure helpers (clamp_target, clamp_stiffness, check_trip) importable from robot.arm. home() ramps at 0.05 m/s (no move primitive confirmed). Angular vel/acc limits are module constants (0.5 rad/s, 2.0 rad/s^2), not in Limits.
- Next: K0 answers into robot/BRINGUP.md and robot/config.json, then on-arm test of K1 and K2.
- Shiv: robot.arm now exports ArmState and Limits, so S1 can drop its fallback dataclasses. Note: after any hold (not only a trip) set_target/set_stiffness are ignored until start_compliance().

**2026-11-14 · Shyan · Y0b Y0c Y0d Y3**
- Y0b done: server/db.py SQLite storage (patients, sessions, reps, all with simulated; real and simulated cannot mix; forward migration for new contract fields).
- Y0c done: server/simulate.py writes 14 days of SIMULATED history for "Anna (SIMULATED)" (dial +0.94 to -0.35, contribution 0.19 to 0.85, one bad day, forces within the 15 N resistance design).
- Y0d done: server/export.py; generated files are committed in server/exports/ with a plain-English README. Mat and Gio can use server/exports/ now: yes.
- Y3 done: server/note.py template session note (no AI, no diagnosis, SIMULATED label when relevant). 34 server tests pass.
- Next: Y1 API (REST + WebSocket) against the engine interface in MASTER_PLAN 4.4.

**2026-11-14 13:50 · Shiv · S0a**
- S0a done: software/metrics.py with 15 passing tests (rom, path_error, force_stats, sparc ported line-for-line from siva82kb/SPARC and checked against its docstring example -1.41403, contribution, rep_metrics with RepResult key names).
- Note: contribution takes an optional dt (default 0.01); rep_metrics passes the median dt. The engine (S4) must pass only the out-phase slice for contribution (MASTER_PLAN 4.2). sparc raises ValueError on an all-zero speed profile.
- Blockers: none.

**2026-11-14 · Shyan · Y1 Y2 Y4**
- Y1 done: server/api.py, every route of MASTER_PLAN 4.6 plus WS /ws/live at 30 Hz; `simulated` set from the arm type (only robot.arm.Arm counts as real). Optional operator token (`--lan`) guards start/stop/dial/go; /api/hold is never guarded.
- Y2 done: `python -m server.run --mock | --sim | --robot [SERIAL]` and `python -m server.watch`. Tested on a live server process: session start, reps, auto dial +1.00 to -0.60, stop, note.
- Added server/mock.py: stand-in engine with the 4.4 interface, all output SIMULATED. Use `--mock` until Shiv's engine is on main; it is also a live feed for Mat and Gio.
- Y4 done: server/tests/test_e2e_sim.py. Mock variant passes; the SimArm + Engine variant skips until S1, S0d, S4 land, then runs automatically (this is the I2 check). 51 server tests pass.
- Shiv: the server calls `Engine(arm=, session_id=, patient_id=, simulated=, dial=, auto=, on_sample=, on_rep=, reach_axis=arm.reach_axis)` with keyword arguments only, exactly as in 4.4. If you add `go()` to the engine, /api/go will call it.
- Kian: run.py `--robot` with no serial uses `Arm.from_config()`; Ctrl+C and crashes call hold() then close().

**2026-11-14 · Shyan · Y5**
- Y5 done: server/API.md (plain-English guide with real captured responses for every route and the live feed) and server/examples/live.html (25-line live page, checked against captured messages). Mat and Gio can build against server/API.md now, using `python -m server.run --mock` as the feed.
- All Shyan packages Y0a-Y5 done. 52 server tests pass. Remaining on my side: run the sim variant of the end-to-end test when Shiv's S1, S0d and S4 land (I2), then the real-arm run with Kian (I3).
