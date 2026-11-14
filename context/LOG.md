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

**2026-11-14 14:50 · Shiv · S0a**
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

**2026-11-14 15:00 · Shiv · sync**
- Changed: S0a merged (software/metrics.py, 15 tests); software/__init__.py and software/requirements.txt (numpy, pytest) now exist on main. TASKS S0a set to Done.
- Next: S0b reps, S0c paths, S0d sim_patient, then S1 sim_arm, S2 controller, S3 adapt, S4 engine (Engine keyword-only constructor per Shyan's Y1 note).
- For Shyan: rep_metrics(t, pos, force, start, end) returns RepResult-named keys; contribution must be given the out-phase slice by the engine. For everyone: run software tests with `python -m pytest software/tests -q` from the repo root.
- Blockers: none.

**2026-11-14 · Shyan · housekeeping**
- Timestamps fixed: new server/clock.py, api.py and mock.py now write Europe/Zurich time whatever the laptop's zone (was an hour behind on UK laptops). Same string format, so sorting, exports and notes are unchanged. Added tzdata to server/requirements.txt (Windows needs it): re-run pip install -r server/requirements.txt.
- Added a root .gitignore (__pycache__, .venv, .pytest_cache, editor/OS files). Kian, Shiv: no more stray __pycache__ in robot/ and software/.
- 87 tests pass, 1 skipped (end-to-end, waiting for S1, S0d, S4).

**2026-11-14 14:05 · Shiv · S0c**
- S0c done: software/paths.py with 19 passing tests (LinePath length/axis/point_at/closest, min_jerk, lead_target capped by max_lead_m and the path ends).
- Next: S0b reps, S0d sim_patient.
- Blockers: none.

**2026-11-14 15:06 · Shiv · S0b**
- S0b done: software/reps.py (progress, segment_reps, RepDetector) with 14 passing tests.
- Notes for S4 engine: a too-short excursion (under min_duration_s, i.e. threshold jitter) after a rep_start closes with None, not rep_end; check detector.in_rep. Finished reps are in detector.reps as (i_start, i_end, completed). A rep still out when the recording stops is not returned.
- Next: S0c paths, S0d sim_patient, then S1-S4.
- Blockers: none.

**2026-11-14 · Shiv · S0d**
- S0d done: software/sim_patient.py with 12 passing tests (python -m pytest software/tests/test_sim_patient.py -q). The software/ suite passes: 60 tests.
- SimPatient(strength, tremor_n, seed, present=True). effort() returns zero when present is False, which S1 and S4 need for the hands-off rule. simulate_reach returns t/pos/vel/force/target plus "simulated": True. It reuses paths.lead_target and min_jerk. The patient's PD gains (150 N/m, 5 N s/m), the 1.5 s reach and the 0.5 s dwell are team-chosen sim values.
- Next: S1 sim_arm, then S2 to S4.
- Blockers: none.

**2026-11-14 15:05 · Kian · sync**
- Changed: arm-laptop venv at C:\venvs\leukerbad (uv, Python 3.12.16, outside OneDrive); robot offline tests pass in it (18). New robot/SETUP.md: venv + firewall steps (allow BOTH the venv python.exe launcher and the uv base python.exe), K4 workspace section still TODO. Added context/EVENT.md (opening-slide info). Root .gitignore now also ignores .env and .claude/settings.local.json.
- Next: K0 bring-up with the technician (find exact flexivrdk 1.9.x, add robot/requirements.txt pinned), then K4 measurements into config.json/SETUP.md.
- For everyone: on Windows, firewall rules for a uv venv must include the base interpreter (sys._base_executable), not just Scripts\python.exe.
- Blockers: none yet; flexivrdk version waits on the technician.

**2026-11-14 15:20 · Kian · sync**
- Changed: robot/RUNBOOK.md step 6 now activates C:\venvs\leukerbad\Scripts\activate (was .venv placeholder), pointing to robot/SETUP.md.
- Next: K0 bring-up with the technician; add robot/requirements.txt with the pinned flexivrdk 1.9.x.
- Blockers: none.

**2026-11-14 · Shiv · S3**
- S3 done: software/adapt.py (next_dial, mode_of) with 9 passing tests (python -m pytest software/tests/test_adapt.py -q). The software/ suite passes: 69 tests.
- Rules per section 4.2: success -0.15, failure +0.10, else hold, clamped to [auto_floor (-0.6), 1.0]. A rescued rep counts as failure. On the resist side (dial < 0) success does not need contribution > 0.6. The result is rounded to 6 decimals so five successes from 1.0 land on exactly 0.25 and crossing zero is exactly transparent.
- Next: S1 sim_arm, S2 controller, then S4 engine.
- Blockers: none.

**2026-11-14 · Shiv · S2**
- S2 done: controller covers assist, transparent, resist, 33 tests (python -m pytest software/tests/test_controller.py -q).
- command() per sections 4.2/4.4: reach axis = the base axis the path lies along (diagonal paths raise); walls K_WALL on the other two axes, target always on the path segment. Assist leads the hand toward the min-jerk reference by at most MAX_LEAD, target on the hand when ahead; resist puts the target MAX_LEAD behind the hand toward the start in both phases. rescued=True raises the dial to >= 0.6 on the assist side and goes transparent on the resist side. Constants (K_WALL, K_ASSIST, K_RESIST, MAX_LEAD, REACH_M, T_OUT_S, T_BACK_S, RESCUE_DIAL) at the top of the file for K3 tuning.
- Next: S1 sim_arm, then S4 engine.
- Blockers: none.

**2026-11-14 · Shiv · S1**
- S1 done: SimArm passes 21 tests, matches Arm interface (python -m pytest software/tests/test_sim_arm.py -q).
- software/sim_arm.py: same method names and signatures as robot/arm.py (checked by test). Imports ArmState, Limits, clamp_target, clamp_stiffness, check_trip straight from robot.arm (K1 had already landed, so there is no local fallback). Box, lead, k_max clamps, speed/force/box trips and the 0.2 s watchdog therefore behave the same as on the real arm. Physics: 1.5 kg, 8 N s/m, per-axis spring, stiffness applied 50 ms after the call. Reported force = patient effort + passive limb load (8 N down + 5 N s/m drag) when present, exactly 0 when patient.present is False.
- Simulated patient routine: rest 1.5 s at start, 3 s min-jerk reach, 0.5 s dwell, 3 s return. Phase changes wait for the hand to arrive (10 s timeout). Reach set by attributes arm.reach_axis/reach_sign/reach_m (default x, +1, 0.30 m). realtime=True runs a 100 Hz thread started by connect(); realtime=False uses step(dt). Like Arm, get_state() needs connect() first.
- Next: S4 engine on SimArm(realtime=False).
- Blockers: none. Note for Shyan: call arm.connect() on SimArm before Engine.start(), the same as for Arm.
