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

**2026-11-14 15:21 · Shyan · L0**
- L0 done: /screens/ mounted, common.js and style.css ready

**2026-11-14 15:30 · Shyan · L1**
- L1 done: /screens/patient.html (mode word, dial gauge, reach track with hand and target dots, force bar, reps, last-rep contribution, hold/fault and waiting overlays, SIMULATED badge). Fits one projector screen and phone width.
- Reach start/axis/length are inferred in screens/track.js from samples (API does not send them); unit-tested via node.
- Next: L2 physio screen, L3 operator screen. Blockers: none.

**2026-11-14 · Shiv · S4**
- S4 done: engine runs end to end on SimArm, 24 tests (python -m pytest software/tests/test_engine.py -q). The software/ suite passes: 147 tests.
- software/engine.py implements section 4.4 with the section 4.2 state machine (idle/out/back), the hands-off rule (assist side; an empty handle's target is latched where it was let go), stall rescue (1.5 s assist, 3 s resist; none at exactly 0) and the auto dial via adapt.next_dial. Every RepResult metric, including duration_s, is computed on the out-phase slice only. Any exception in a tick (callbacks included) calls arm.hold() and then re-raises.
- Choices made while Shiv was away: "within 2 cm of the start" is measured along the reach axis, because the 8 N limb load sags z by about 2-3 cm. In idle the target sits on the path line. back times out after 10 s and the rep ends anyway. A rep aborted by the hands-off rule or a trip is recorded as not completed. SPARC is reported as 0.0 if the hand did not move. For SimArm(realtime=False) start() runs no thread: drive it with engine.run_for(s) / run_until_reps(n). Extra read-only properties: dial, auto, phase, phase_started_at.
- BLOCKER (software/sim_arm.py, S1 follow-up, not edited in S4): SimArm's patient routine runs on its own clock. It rests 1.5 s, but the engine arms after 1.0 s, and its 3D "near start" check fails under limb sag, so the patient drifts out of step with the engine. A strong patient then pulls back at about 19 N while the arm carries them, contribution reads about 0, and the 10 s intent timeout releases that pull at once, which trips the 0.40 m/s speed limit. Consequences: server/tests/test_e2e_sim.py::test_e2e_sim (stock SimArm, strength 0.8) times out at 300 s, and `server.run --sim` will not show the dial falling. Proposed fix: start the patient's reach when the arm leaves hold stiffness (the engine always changes stiffness at arming), and measure "near start" along the reach axis. The engine tests use a test-local CuedPatient that reaches on the engine's cue.
- Observation for Kian (K3): with K_WALL 500 N/m the simulated 8 N limb load sags the handle 1.2-1.6 cm, so a weak patient's mean path error is above the 1.5 cm success limit. Check limb load and sag on the real arm.

**2026-11-14 · Shiv · S5**
- S5 done: software/assess.py with 11 tests (python -m pytest software/tests/test_assess.py -q). The software/ suite passes: 158 tests.
- starting_dial(reps, reach_m=0.30) uses the last 3 transparent reps. If none was completed: +1.0. Otherwise ability = mean(completed share, ROM / (0.9 x reach) capped at 1, mean contribution), and dial = 1 - 1.6 x ability, clamped to [-0.3, +1.0] and rounded to 0.05. A session never starts beyond -0.3; auto takes it further. assessment() returns the components for a screen. Labelled everywhere "team heuristic, not a clinical assessment".
- Next: S1 follow-up (sim patient timing, see the S4 blocker). Not wired into the API: Shyan can call it after 3 reps at dial 0 if wanted.
- Blockers: none new.

**2026-11-14 · Shiv · sync**
- Changed: S4 engine and S5 assess are on main, and the software/ suite passes 158 tests. TASKS rows S0b-S5 are marked Done (S0b-S3 had been finished earlier but were still listed as Todo).
- Sim check (not committed): with a patient that reaches when the engine starts each rep, one auto session of 10 limp reps then 10 strong reps holds the dial at +1.00 (contribution 0.00), then lowers it +1.00 -> -0.50 (7 strong reps to reach about 0, 0.15 per rep), with no trips. With the stock SimArm patient the strong reps get contribution about 0, and the speed trip fires after 2 strong reps (S4 blocker).
- Caveat: in the frictionless sim, contribution is close to all-or-nothing. A 0.05-strength patient already scores 0.99, because any push keeps the hand ahead of the 4 s reference. Weak patients keep the dial at +1 only because limb sag puts path error at about 1.6 cm, over the 1.5 cm limit. Re-check on the real arm (K3) before relying on the auto dial for weak users.
- Next: S1 follow-up fix in software/sim_arm.py (start the patient's reach on the engine's stiffness change, and measure "near start" along the reach axis). Then rerun server/tests/test_e2e_sim.py.
- For Shyan: server/tests/test_e2e_sim.py::test_e2e_sim now runs (engine exists) and fails on a 300 s timeout until the S1 fix. `server.run --sim` currently stalls after a trip. Use `--mock` for demos meanwhile.

**2026-11-14 · Shiv · S4 follow-up checks (correction)**
- CORRECTION to the sync caveat above: the cause is the metric, not sim friction. metrics.contribution (S0a) only looks at the person's force. Robot work counts only when the person's force opposes the motion, and the arm's spring work K*(target-hand)*v is never counted. Measured on one out phase at D=+1: a 0.05-strength patient did 0.09 J, the arm's spring did 0.19 J (68% of the work), yet contribution = 0.99. So a patient who pushes slightly while being carried scores about 1, which affects the on-screen number and the auto dial. Proposed fix (Shiv, S0a/S4): robot work = sum max(0, F_spring . v) dt, using the target and stiffness the engine already commands.
- Safety finding for Kian (K2) and Shiv (S2/S4): the resist-side stall rescue drops the band in one step. A strong stock-sim patient stalled at D=-1 while pushing 14.5 N lurches to 0.43 m/s within 70 ms, the speed trip fires and the set ends. Proposed fix: ramp the dial to 0 over about 1 s instead of stepping. Not changed yet, because section 4.2 says "drops to transparent".
- Checked: the engine's 100 Hz thread path (SimArm realtime=True, stock limp patient, 20 s wall time) completed 2 reps with no fault. `server.run --sim --strength 0` is usable meanwhile; stronger stock sim patients hit the S4 blocker.

**2026-11-14 · Shiv · S1/S4 follow-up: the three S4 problems fixed**
- software/sim_arm.py: the stock sim patient starts its reach on the engine's cue (applied stiffness leaves the all-axes k_hold soft hold; mid-rep changes are not a cue). "At the start" is measured along the reach axis. It counts as arrived at 0.90 (= engine OUT_DONE). Sim choice: it now aims at 1.3 x reach ("reaching through"), then settles at the end, so a strong patient can complete reps against full resistance. test_sim_arm's force-sign test now ignores the last 5 cm, where the patient brakes. Stock patient, strengths 0-1, 12 auto reps each: no trips, no patient timeouts, peak speed <= 0.33 m/s. The dial falls from +1.00 to -0.60 for strength >= 0.5.
- metrics.contribution / rep_metrics: optional robot_force (the arm's commanded spring force); the engine passes it (DECISIONS). A 0.05-strength patient carried at D=+1 now scores 0.46 instead of 0.99. Note: in the sim a 0.1-strength patient still scores about 0.94, because the frictionless hand moves on 2.5 N; re-check on the real arm.
- engine: the resist-side stall rescue now ramps to transparent over 1 s in 0.1 s steps (DECISIONS). The logged case peaks at 0.20 m/s with no trip, where the one-step drop reached 0.43 m/s and tripped.
- Tests: software/ suite passes, 174 tests (stock-patient engine tests added). server/tests/test_e2e_sim.py passes (2 passed, 69 s, run in a throwaway venv); the rest of server/tests also pass (62 passed, 1 skipped). The S4 blocker is cleared: `server.run --sim` works at any strength.

**2026-11-14 · Shiv · sync**
- Changed: S1 follow-up done; the sim patient now reaches on the engine's cue. Contribution counts the arm's spring work, and the resist-side rescue ramps over 1 s (see the entry above and DECISIONS). The software/ suite passes 174 tests.
- For Shyan: server/tests/test_e2e_sim.py now passes on main (it was failing since S4); Y4's sim variant can be marked done. `server.run --sim` works at any `--strength`.
- For Kian (K3): the resist rescue ramp uses 0.1 s steps because of the stiffness latency; if the real arm's set_stiffness latency is over 100 ms, tell Shiv so the step can be lengthened. Weak-patient path error from 1.2-1.6 cm limb sag (K_WALL 500) still holds weak users at +1.
- Next: re-check contribution and the auto dial on the real arm once K3 tuning lands; S5 assess is ready to wire into the API if Shyan wants it.

**2026-11-14 17:45 · Shyan · sync**
- ARM NOT CONNECTED YET (blocker for everyone). Laptop side fully ruled out: Ethernet 3 static 192.168.2.110/24 no gateway, robot pings on 192.168.2.100 (<1 ms), firewall rules for venv + base python, McAfee off, WiFi off: `flexivrdk.Robot("Rizon4-062157")` still "Failed to connect" every time (10/10 after a power-cycle, Motion Bar slide switch in Auto). Remaining causes are all robot-side: Remote Mode (RDK/Ethernet) not enabled on the Flexiv UI tablet, no RDK licence, wrong serial, or RDK/robot software version mismatch (1.9.4.1 is a guess). Escalated to organisers/technician (MASTER_PLAN R1). Elements is on Flexiv's UI tablet, not a PC download.
- I2 is GREEN: server/tests/test_e2e_sim.py sim variant passes on main after Shiv's S1 follow-up (checked independently). `server.run --sim` works.
- Done since last sync: L0 screens foundation, L1 patient screen (checked in a browser at 1600x900 and 360 px, no console errors), Swiss-time timestamps, root .gitignore.
- Next (Shyan): L2 physio, L3 operator, Y6 arm prepare route (server never calls home()/zero_force() today; RUNBOOK step 10 assumes it). Kian: have K0 scripts 01-03 and K2 safety_check.py ready so they run the moment the arm connects. When the technician comes, ask for the robot software version and exact serial and pin flexivrdk in robot/requirements.txt.
