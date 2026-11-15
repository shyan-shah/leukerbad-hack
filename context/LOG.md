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

**2026-11-14 19:35 · Shyan · arm probe**
- Connected: NO. `flexivrdk.Robot("Rizon4-062157")` fails on Windows and in WSL with flexivrdk 1.7.0 (and earlier with 1.9.4.1). Robot software is v3.9.3 (from Elements), so the pin is `flexivrdk==1.7.0` plus `numpy`, not 1.9.x.
- Cause narrowed by packet capture: network, firewall and serial are fine, but the robot only publishes its read-only `flexiv_ddk` topics and none of the `flexiv_rdk` topics. Most likely no RDK licence, or Remote Mode not saved as Ethernet before the power cycle. Ask the technician to check both.
- Findings in `context/BRINGUP_FINDINGS.md`. No start pose, `K_x_nom`, licence type or wrench yet (all need a connection).
- Next for Kian: add `robot/requirements.txt` (`flexivrdk==1.7.0`, `numpy`); fix `arm.py` `_send_pose` (1.7.0 `SendCartesianMotionForce` has no `velocity` argument, the current 7-argument call raises TypeError); set `serial` in `robot/config.json`; change "1.9.x" in SETUP/RUNBOOK/recover.py.

**2026-11-14 20:33 · Shiv · flexivrdk 1.7.0 API check of robot/arm.py + robot/recover.py (blocker for Kian)**
- Checked every RDK name with dir()/help() in the installed flexivrdk 1.7.0. EXIST in 1.7.0: `flexivrdk.Robot(serial)`; Robot `fault`, `ClearFault` (returns bool), `Enable`, `operational`, `info`, `states`, `SetCartesianImpedance` (6 K values, Z optional), `SwitchMode`, `SetMaxContactWrench` (6 values), `ExecutePrimitive(name, dict)`, `primitive_states` (returns dict), `Stop`; recover.py's optional `connected`, `estop_released`, `enabling_button_pressed`, `busy`, `mode` all exist too (TODO at recover.py:84 can be closed). `Mode.NRT_CARTESIAN_MOTION_FORCE`, `Mode.NRT_PRIMITIVE_EXECUTION` OK. `states()`: `tcp_pose`, `tcp_vel`, `ext_wrench_in_world`, `q` OK. `info().K_x_nom` OK.
- WRONG in 1.7.0 (confirms Shyan 19:35): arm.py:297 `_send_pose` calls `SendCartesianMotionForce(pose, [0]*6, [0]*6, lin_vel, ang_vel, lin_acc, ang_acc)` with 7 args. The 1.7.0 signature is `(pose[7], wrench[6]=0, max_linear_vel, max_angular_vel, max_linear_acc, max_angular_acc)`, with no velocity vector, so the real arm will raise TypeError. Fix: remove one `[0.0] * 6`. Also update robot/tests/test_arm_offline.py:197 to unpack 6 values. The offline tests pass only because the fake robot accepts any arguments.
- Docs/packaging: `robot/requirements.txt` does not exist, but recover.py:60 tells users to install it. Add it with `flexivrdk==1.7.*` and `numpy`. Change "1.9.x" to "1.7.x" in recover.py:13 and :61.
- Can't be checked offline (needs a connected arm or simulator): that the primitive name `"ZeroFTSensor"` and the `primitive_states()["terminated"]` key are right for robot software 3.9.3.

**2026-11-14 20:37 · Shiv · robot/ fix for flexivrdk 1.7.0 (with Kian's OK)**
- Shiv made this change in robot/ with Kian's OK: arm.py `_send_pose` now calls `SendCartesianMotionForce(pose, wrench, max_lin_vel, max_ang_vel, max_lin_acc, max_ang_acc)`. That's 6 args, matching 1.7.0 (extra velocity vector removed). test_arm_offline.py expects 6 args. New robot/requirements.txt (`flexivrdk==1.7.*`, `numpy`). recover.py lines 13 and 61 now say 1.7.x. robot/tests + software/tests: 192 passed.
- Left for Kian: recover.py comments at lines 83 and 117 still say "1.9.x". ZeroFTSensor name and `primitive_states()["terminated"]` still need checking on a connected arm.

**2026-11-14 21:00 · Shiv · Plan B for the RDK licence risk (software/PLAN_B.md)**
- flexivrdk 1.7.0 Python has only NRT modes (no RT at all). Flexiv's v1.x manual gives non-real-time features to the "Standard" licence and real-time streaming and dynamics to "Professional", so NRT_CARTESIAN_MOTION_FORCE is probably Standard (not verified). The visible risk is having no licence at all, which leaves no mode working.
- Plan B if the Cartesian mode is refused but primitives work: FloatingCartesian free drive, engine with the dial locked at 0 (measurement only), new `software/freedrive_arm.py` behind the same Arm interface. Joint impedance was rejected (needs our own IK, loses the tunnel walls). Recommendation and probe script are in PLAN_B.md.
- For Kian: run the PLAN_B.md section 4 licence probe on first connect and record `info().license_type`. For Shyan: if plan B is used, add `--freedrive` to server/run.py (FreeDriveArm, `dial=0.0, auto=False`).

**2026-11-14 20:53 · Shiv · force-sensor robustness (Task 1)**
- Engine now works on force relative to an empty-handle baseline taken at start() (before compliance), tracks drift while idle and empty, and refuses to start if the empty handle reads over 3 N (message says to run arm.zero_force()). SimArm has offset/drift/noise/latency options. New software/tests/test_force_robustness.py (19 tests): reps, auto dial and the hands-off rule hold with offset (4.5, -2.5, 11.9) zeroed, 0.5 N/min drift, 0.3 N noise and 200 ms latency; an un-zeroed 13 N or 12 N offset refuses with a clear error. software + server tests: 254 passed, 1 skipped (node).
- For Shyan (Y6): on the real arm every session will refuse until arm.zero_force() is run with nobody touching (and our handle set as the tool). The prepare route should call zero_force() before /api/session/start. Engine.start() now takes about 0.3 s longer (the baseline).
- For Kian: re-zero between sets. Drift while the handle is held isn't tracked; at 0.5 N/min it reaches F_PRESENT after about 3 min of holding. Please measure the real drift in K3.

**2026-11-14 20:57 · Shiv · gravity sag no longer fails weak patients (Task 2)**
- metrics.path_error removes the mean vertical sag (see DECISIONS). In the sim, path error went from 14.6-15.4 mm (all sag) to about 0.9 mm. The 0.3-strength auto dial now falls 1.0, 0.85, ..., 0.1, -0.05, -0.2, -0.35 over 10 reps (it used to stick at -0.05). A limp 0.0 patient still stays at +1 (contribution 0). New tests: 3 in test_metrics, 2 in test_engine. software + server tests: 259 passed, 1 skipped (node).
- Note: the stock 0.2 patient now also falls into resistance, because the sim's 0.2 patient completes reaches alone with contribution 0.99. That's a sim-patient calibration point, not an engine rule.
- For Shyan, Mat and Gio: path error on screens and in exports now means "off the line, not counting the constant sag". Older stored reps include the sag.

**2026-11-14 21:10 · Shyan · arm probe**
- Connected: STILL NO. Re-ran at 20:03: 5/5 failed on Windows and 5/5 in WSL with `flexivrdk==1.7.0` (robot software v3.9.3). Firewalls ruled out on both; a second capture again shows the robot offering only `flexiv_ddk` topics, no `flexiv_rdk`.
- Elements Studio 3.9.3 runs on Shyan's laptop (desktop shortcut "Start Flexiv Studio.bat") and sees the robot, so the single blocker is robot-side: RDK licence missing, or Remote Mode not saved as Ethernet and power-cycled.
- `context/BRINGUP_FINDINGS.md` updated (Studio launch command, probe counts). Still no start pose, `K_x_nom`, licence type or wrench.
- Next for Kian: Shiv has already fixed `_send_pose` (20:37 entry); still open are `robot/requirements.txt` (pin 1.7.0 + numpy) and the serial in config.json. Next for Shyan: check the licence page and Remote Mode setting in Studio. (Probe times in this entry are laptop clock, one hour behind Swiss time.)

**2026-11-14 21:20 · Shiv · 30-session sim soak through the server stack**
- Ran 30 back-to-back sessions through server.api.create_app (real HTTP routes, Hub, SQLite, default Engine) on one SimArm kept across sessions, like `server.run --sim`. Each session had a random strength 0-1, offset ±15 N per axis, drift ±1 N/min, noise 0-0.5 N, stiffness latency 50-200 ms, and a hands-off zero_force before start. Sim time was stepped (realtime=False), so the engine thread itself wasn't exercised. Script: software/scratch/soak30.py (not committed).
- Result: 30 sessions, 300 reps, 0 trips, 0 crashes, 0 stalls, 0 refused starts (9 reps were stall-rescued, 3 incomplete). Second seed: 30/300, all zeros, 3 rescued. Auto dial ended at -0.25 to -0.5 for strength ≥0.09, and +0.9/+1.0 for the 0.07 and 0.04 patients.
- Found: zeroing with the hand on bakes the 8 N limb weight in, and every start is then refused (the engine guard works as intended). For Shyan (server/): that refusal comes out of POST /api/session/start as an unhandled 500. Please catch engine.start()'s RuntimeError and return 409 with its message so the operator screen shows "run zero_force with nobody touching". Ties in with the Y6 prepare route calling zero_force().

**2026-11-14 21:25 · Shyan · arm connected**
- CONNECTED (read-only) with `flexivrdk==1.7.0` after Remote Mode was set to Ethernet in Elements and the robot rebooted. Licence `RDK-Professional+TDK-Standard`, software v3.9.3, `K_x_nom = [10000, 10000, 10000, 1500, 1500, 1500]`, no fault, mode IDLE. The arm was ALREADY ENABLED (`operational()` True) on connect, without any `Enable()` call: treat it as live whenever powered.
- Start pose (hand-placed, tool `Seat_Assembly_tool` active): tcp_pose `[0.805597, 0.449626, 0.619889, 0.720262, -0.127445, -0.104004, -0.673917]`, q `[0.983714, -1.800170, -1.986748, 0.989766, -1.113379, 0.253691, 1.555811]`. Empty wrench reads about 12.6 N, almost all +z (matches the 1.338 kg of the selected tool, probably not mounted): Shiv's 3 N start guard will refuse until the handle is set as the tool and zeroed.
- Next for Kian (`context/BRINGUP_FINDINGS.md` section 6): set `serial` in `robot/config.json`; add our handle as the tool, then re-read the start pose (tcp_pose changes with the tool); test `ZeroFTSensor` (`ft_sensor_raw` is all zeros, possibly no wrist sensor); decide `reach_axis` and `force_sign` (the pose is diagonal in the world frame).

**2026-11-14 21:50 · Shyan · first motion test (in progress)**
- THE ARM MOVES UNDER OUR CODE. `robot/arm.py` (unchanged) drove the real Rizon 4 via flexivrdk 1.7.0: 5 s hold at nominal stiffness drifted 0.15 mm (pass); a 2 cm move at 600 N/m ran safely but ended 7.4 mm short (fails the 3 mm mark, friction about 4.5 N); a 4-minute translation-only video run at 2000 N/m and up to 0.10 m/s completed with no trips (mean lag 15 mm). Plan A (NRT_CARTESIAN_MOTION_FORCE) works with the RDK-Professional licence.
- Robot tool switched from `Seat_Assembly_tool` to `Flange`: empty force reading fell from 12.7 N to 1.7 N (nothing is mounted). It then varied 0.7 to 3.2 N with pose, close to the engine's 3 N start guard. Reach direction from the current pose is mostly world -x (27 degrees off axis).
- Details and to-dos for Kian and Shiv in `context/MOTION_TEST.md`. Still to run: soft hold with a hand push, free axis, engine dry run.

**2026-11-15 morning · Shyan · morning sync**
- Now on main: `server/hw/` (last night's scripts: read-only probe, tool switch, staged motion test, video run, API check, Studio launcher, README with how to run them on `C:\venvs\flexiv17` and their limits, plus the 14 Nov result files); `POST /api/session/start` returns 409 with the engine's message instead of an unhandled 500 when `engine.start()` refuses; new `POST /api/arm/prepare` (Y6). All offline tests pass on flexivrdk 1.7.0 (285).
- Prepare route: real arm only, nobody touching. It checks connected and fault-free, calls `arm.zero_force()` (a failure is logged and not fatal) and returns the empty-handle force. On a real arm `/api/session/start` answers 409 "prepare the arm first" until it has succeeded since server start; sim and mock skip it. It does not call `home()`. Documented in `server/API.md`; `/api/health` has a new `arm_prepared` field.
- For Kian: please commit into `robot/config.json` the serial `Rizon4-062157`, `reach_axis` 0 with reach sign -1 (the real direction is 27 degrees off x), and the start pose from `context/MOTION_TEST.md`. The robot's tool is now `Flange`. `ZeroFTSensor` is still untested on this arm. For Shiv: expect a 1 to 3 N pose-dependent empty-handle force and 1 to 1.5 cm of friction lag at our stiffnesses (MOTION_TEST.md); the 500 to 409 fix is in.
- Left: arm motion test stages 3 to 5 (soft hold, free axis, engine dry run), which need the robot; then L2 physio and L3 operator screens (the operator screen should call `/api/arm/prepare`).

**2026-11-15 · Mat · website, app and deck pushed to demo/**
- Now on main in `demo/`: `website/` (11-page marketing site, live at https://vitarehab.netlify.app), `app/` (patient app prototype, live at https://vitastation.netlify.app), `pitch-deck/`, `app-backend/` (the app prototype's own SQLite backend, separate from `server/`; key and database not committed) and `src/` (sources and build scripts). See `demo/README.md`.
- Figures on the site and in the deck are still illustrative; they need B1/B2 (claims table) before the pitch.
- Next: hook the website/app screens to `server/exports/` (B6), finish the deck (B4). No blockers for the others.

**2026-11-15 · Shyan · exercise map**
- Read Mat's app (demo/app/index.html: `EX` library, `MOV` 3D motions). New `context/EXERCISE_MAP.md` maps each app exercise to the robot: MUST live on the arm = reach (assist), push (resist), pull (reversed resist), armtest (isometric strength test). SHOULD (robot-led, isotropic stiffness, scaled down) = circle, trace, rot. Not this weekend = lift, knee, kneebend, legtest.
- Shiv: engine presets for the four MUST exercises. Shyan: `exercise` field on /api/session/start. Mat/Gio: a demo plan in the app with only robot-live exercises, and the exercise screen calling the laptop server. Kian: far-end pose for pull, isometric hold in the safety checks.

**2026-11-15 · Shyan · task swap**
- Shyan does E1 (engine presets for reach/push/pull/armtest) in software/; Shiv does E2 (exercise field on /api/session/start, state, reps, DB, API.md) in server/. Interface between them: Engine(..., exercise=<id>) keyword; ids exactly as in context/EXERCISE_MAP.md. See DECISIONS.

**2026-11-15 · Shyan · name**
- Product name is **Vita** everywhere (site, app, deck, screens, pitch). "The dial" still means the control. Mat/Gio: trademark and domain check (IGE, EUIPO, UK IPO) is still unverified.

**2026-11-15 · Shiv · E2 started: the interface the server will assume from E1 (for Shyan)**
- `software.exercises.LIVE`: the ids the robot can run now (set, list or dict keys). Until the file exists the server uses `{"reach"}`.
- Registry: the server looks for a dict or list named `EXERCISES`, `REGISTRY`, `PRESETS` or `PROGRAMMES`, with entries (dicts or objects) holding `id`, `name`, `kind` and `reps` (or `default_reps`). Anything missing falls back to the server's own table, so any of those names works.
- Engine: `Engine(..., exercise="push", reps=10)`. The server always sends a rep count (the caller's, else the registry default; `reps=None` only when the caller asks for no limit). `dial` and `auto` are passed only when the caller sent them, so the preset's own dial applies otherwise. `reach_sign`/`reach_m` from `server.run` are passed as today; please treat `reach_sign` as the push direction and reverse it inside the `pull` preset.
- The server adds `exercise` and `reps_target` to state, sample and rep messages itself (from the session), so the engine doesn't need to emit them. If E1 differs from any of this, tell me and I'll change the adapter (server/exercises.py).
**2026-11-15 · Mat · robot colours**
- Website, app and pitch deck (demo/) recoloured to the robot arm's own palette: cyan light rings `#58E6F2` as the accent, petrol `#0A4552` as the brand colour, teal `#0B7F91` for text, silver-white backgrounds. Logo dot is now a glowing cyan light ring. Coral/red/yellow (load, stop button) unchanged.

**2026-11-15 · Shyan · E1 done**
- E1 done: `software/exercises.py` (presets `reach`, `push`, `pull`, `armtest`, `circle`; `LIVE = ("reach", "push", "pull", "armtest")`), engine support, `software/tests/test_exercises.py` (23 tests, including reach along y as in Layout B and one exercise started after another) and `software/EXERCISES.md`. robot + software + server: 322 passed. Tested on SimArm only, nothing run on the real arm.
- Interface for Shiv (E2): `Engine(..., exercise="<id>", reps=None)`, keyword only, default `"reach"` (unchanged). Unknown id raises `ValueError`; refuse ids not in `software.exercises.LIVE` with 422. You can keep sending `dial`, `auto` and `reach_m`: for non-reach presets the preset's `auto` wins and `dial` is used only if negative on push/pull; a given `reach_m` overrides the preset's. `reach_sign` stays the configured direction (pull reverses it itself). `reps=N` stops arming after N; `reps=None` leaves reach/push/pull running until stop, armtest stops after 3 tries. `server/run.py` passes `reach_m` only when `--reach-m` is given, which is right (presets keep 0.28 m); its banner still prints 0.30 in that case.
- New values: `Sample.phase` `"setup"` (pull: patient moves the handle to the far end, dial reported 0), `RepResult.mode` `"isometric"` (armtest: `peak_force_n`/`mean_force_n` are along the reach axis, `rom_m` is displacement, `contribution` 1.0) and `"guided"` (circle). `snapshot()` (so `/api/state` and the live feed if you pass it on) adds `exercise`, `kind`, `reps_target`, `done`. The contract has no exercise field on Sample/RepResult, so it is in `snapshot()` only; `Engine.stop()` gives `SessionSummary.exercise` = the id (`"reach_line"` for reach, as before).
- Shiv, checked against your "E2 started" entry: everything you assume holds. `software.exercises.LIVE` is a tuple of ids, `EXERCISES` is a dict of objects with `id`, `name`, `kind`, `default_reps`; `Engine(..., exercise=, reps=)` accepts a count for every exercise (for armtest it is the number of tries); `dial`/`auto` may be omitted; `reach_sign` is the push direction and pull reverses it inside the preset. No adapter change needed.
- Files touched in software/: `exercises.py` (new), `engine.py`, `sim_arm.py` (sim patient hooks `reach_origin`, `auto_cue`, `cue()`; defaults unchanged), tests, `EXERCISES.md`.
- Found in the sim, for Shiv and Kian: letting go on the resist side (push, pull) or mid-push in armtest releases the spring, the empty handle reaches 0.40 to 0.46 m/s and the speed trip puts the arm in hold. Safe, but the session then needs a restart. Proposal, not applied: apply the hands-off rule on the resist side too. Check on the real arm before the pitch. Circle tracks within 1.5 cm only after removing the constant 2.7 cm limb sag at 300 N/m.

**2026-11-15 11:55 · Kian · Part A (offline robot work) done; arm not touched**
- Done, all in `robot/`: `arm.connect()` no longer calls `ClearFault()`/`Enable()` on an arm that is already operational (and refuses an operational arm that reports a fault); `safety_check.py` (15 interactive checks, each motion step waits for Enter, `--sim` dry run: 13 PASS, 0 FAIL, 2 not reproducible in the sim); `SAFETY.md` (results table, technician sign-off block, Elements limits to fill in); `RUNBOOK.md` rewritten with the 14-15 Nov findings; `TUNING.md` (recommend keeping K_ASSIST 400, K_RESIST 300, K_WALL 500, K_HOLD 300) plus `tune.py`; `tool_handle.md` and read-only `read_tool_force.py`. robot + software tests: 248 passed. **Nothing has been run on the real arm and nothing is signed off: nobody holds the handle yet.** `robot/config.json` is untouched (still placeholders) until Kian says the arm is free.
- For Shyan (E1, armtest): while targets stream, `set_target` clamps the target to 5 cm from the hand, so a hold gives way at stiffness x 5 cm = **30 N at k_max**. The isometric test cannot read more than about 30 N: a 30 N push moves the handle 5 cm, above that it slides and trips at 40 N or 0.40 m/s. "No motion beyond about 1 cm" holds only up to 6 N. `k_max` stays 600. Suggest the actor pushes under 25 N and the screen does not call it maximum strength. Same finding as yours on letting go on the resist side: the sim hits the speed trip; `safety_check.py` checks 10, 11 and 13 measure it on the real arm.
- For Shyan and Shiv: friction is about 4.5 N, so a spring of K stops 4.5/K short: 1.5 cm at 300 N/m, 2.5 cm at dial -0.6 (180 N/m), wider than the 2 cm start window; assist below about dial 0.4 pulls less than 8 N and barely moves the arm. Details in `robot/TUNING.md` section 2. Once the handle is on, start the server with `--tool RehabHandle` (the default `Flange` will then refuse). The safety checks use their own copies of the assist/band/free-axis laws (robot/ does not import software/), so one engine run per exercise with a deliberate let-go is still needed after they pass.
- For Mat and Gio: `robot/RUNBOOK.md` proposes pitch roles (operator Shyan, backup Kian; e-stop holder Kian, backup Shiv; patient actor Shiv, backup Gio). They are a proposal: say if they clash with who presents. No footage with a person on the handle until `robot/SAFETY.md` is signed.
- Next (needs "arm is free", the printed handle and the technician): mount the handle, create `RehabHandle` (`robot/tool_handle.md`), `read_tool_force.py`, test `ZeroFTSensor` once, fill `config.json` (start pose re-read with the handle, reach along world y, force sign, far end for pull), run `safety_check.py` and get the sign-off, then `tune.py`.

**2026-11-15 · Gio · patient app drives the robot (demo/app)**
- `demo/app/index.html`: when the station laptop serves the app at `/app/`, it reads `GET /api/exercises` and runs those exercises on the arm. `POST /api/session/start` sends `{patient_id, display_name, exercise, reps}` with no dial or auto, so each preset keeps its own. Reps, the coach line and a live force bar come from `/ws/live`. Finish, leaving the screen or closing the page calls `POST /api/session/stop`. The timer stays as the fallback when the server is unreachable, and for exercises not in the list, which are labelled "demo animation". A refused start (409/503/403) shows the server's `detail` and offers Back or Try again; reps are never faked.
- New plan "Arm recovery (robot)" (id `robot`): reach, push, armtest. Row (pull) is added when the server lists it. The measured reach (best `rom_m`, in cm) replaces `stepOf()` on the progress chart. Push and armtest show the peak force on the break screen, capped at "30 N+". A SIMULATED tag shows on the exercise screen, on the measured value and in Progress and Report whenever the server says `simulated: true`.
- Tested against `server.run --mock` plus a scratch wrapper that adds `/app/` and `/api/exercises`, with an operator token: the reach session counted 12 reps and recorded 30 cm; leaving mid-session stopped it on the server; a wrong token showed the 403 detail.
- For Shiv (server/): (1) mount `demo/app` at `/app/` on the station server. (2) `GET /api/exercises`: the app accepts a list of ids or a list of objects with `id` (`live: false` entries are skipped), or `{"exercises": [...]}`. (3) Operator token with `--lan`: open the app once with `?op=<token>`. The app stores it and sends it as `x-operator-token`. Printing that full URL (or a QR of it) at start-up would help.


**2026-11-15 · Shiv · E2 done: exercises through the server (in server/, per the task swap)**
- New: `GET /api/exercises` (id, name, kind, default reps of the live programmes). `POST /api/session/start` takes `exercise` (default reach) and `reps`; an id that is not live gives 422 with the live list. `exercise` and `reps_target` are in /api/state and sample messages, `exercise` in rep messages, GET reps, reps.csv (last column) and latest_session.json. sessions.exercise holds the id; old "reach_line" rows migrate to "reach" on open. Phase "setup" and mode "isometric" pass through DB, exports, note, watch and the patient screen.
- note.py has per-exercise lines (armtest: best and mean peak over the tries, with the 30 N cap sentence). The patient screen shows the exercise name, "Move the handle to the far end" in setup, and "Push and hold" with best try for armtest. The mock engine plays reach, push, pull (with setup) and armtest (3 isometric tries) and stops at the rep count. `--mock` offers all four now. server/API.md section 6 is the guide for Mat, with real messages.
- Checked against E1 after it landed: the adapter reads Shyan's `EXERCISES`/`LIVE` as is (names and kinds in /api/exercises are his: assist, resist, test), and all four live ids run through the real engine on SimArm via the API (`pytest server/tests/test_exercises.py -k e2e_sim`). State and sample messages also carry `done` (the engine's own flag, else rep_count >= reps_target). Not checked: the patient screen changes in a browser, and track.js under node (node is not installed on my laptop). Nothing here was run on the real arm.
- For Shyan: behaviour change in server/: a start without `reps` now sends the engine the default count (10; 3 for armtest), so reach stops arming after 10 reps; send `"reps": 0` for an endless demo feed. `dial`/`auto` reach the engine only when the caller sends them. The run.py banner still prints 0.30 m for push/pull (left as is). Please open /screens/patient.html once in a browser during a push, pull and armtest session.
- For Mat and Gio: build from `GET /api/exercises`; flow and examples in server/API.md section 6. Start no longer needs `dial`/`auto`.

**2026-11-15 · Shiv · reply to Gio's three server/ requests**
- (2) is live: `GET /api/exercises` returns a list of objects with `id`, `name`, `kind`, `reps` (only live ones, no `live` field). Note for the app: a not-live exercise gives 422 whose `detail` is an object, `{"message": "...", "live": [ids]}`, not a string; show `detail.message`. Samples and /api/state also carry `done` (true when the set is finished) and `reps_target`.
- (1) mounting `demo/app` at `/app/` and (3) printing the `?op=<token>` URL at start-up are NOT done: they are outside E2 and server/ is Shyan's outside the swap. Blocker for Shyan: both are a few lines in server/api.py (a StaticFiles mount before "/") and server/run.py (the --lan banner); say if you want me to do them.

**2026-11-15 · Gio · native iPhone app in demo/ios**
- New `demo/ios/`: the Vita patient app as a native SwiftUI iPhone app (Xcode project generated by XcodeGen from `project.yml`; see `demo/ios/README.md`). It has a white, large-text theme for older users, and its colours are the arm's lights (cyan `#58E6F2`, petrol `#0A4552`, teal deepened to `#075E6B` for 7:1 text contrast). It uses the same fonts as the website (Bricolage Grotesque, Inter; OFL).
- Its exercise data is still a demo; it does not talk to `server/` yet. The web app in `demo/app/` is the one wired to the robot.

**2026-11-15 · Shyan · hands-off on the resist side and the strength test (software/)**
- `software/engine.py`: letting go during push, pull, armtest (and reach at a negative dial) no longer lets the spring throw the handle. Target on the hand at once, reach-axis stiffness ramped to zero over 1 s (0.1 s steps), then the target walks back to the path start at 2 cm/s in the soft hold. New engine phase `"release"` (`Engine.phase` only; Samples say `"idle"`, so nothing changes for the server or screens). See DECISIONS and `software/EXERCISES.md` "Release".
- Sim: 9 let-go cases (25/50/90% of push, pull, armtest) plus the back phase: no trip, session goes on, reps resume on re-grab, under 0.15 m/s within 0.3 s. Two limits on "never above 0.15": the simulated patient is itself moving at up to 0.23 m/s when it lets go in the out phase (the arm adds nothing), and if the let-go is seen one 10 ms tick late the handle reaches 0.17 m/s (armtest, 25 N held) or 0.175 m/s (push, mid-return); two ticks late 0.32 m/s, still no trip. That is the 100 Hz limit on the sim's 1.5 kg handle. software/tests/test_exercises.py: 39 tests.
- For Shiv: the aborted rep is recorded as not completed (auto dial, if on, counts it as a failure). An armtest try that is let go is still recorded, completed if its peak was over 5 N. For pull the walk goes to the far end (the path start), away from the patient; this is the one case where the arm moves an empty handle to the far end (Shyan to confirm).
- For Kian and Shiv, real arm: the instant let-go test needs the empty handle to read under 1.5 N. The empty flange read 3 to 7 N while moving on 14 Nov, so this must be checked on the arm (and the occupancy threshold proposal decided) before filming a let-go on the resist side.

**2026-11-15 · Mat · gym sign**
- In the deck and film gym scene, the desk sign now reads "Reception" instead of "Physiotherapist": a regular gym employee supervises the station.

**2026-11-15 · Shyan · patient app served by the station; phone → app → server chain checked**
- server/: Mat and Gio's app (`demo/app`) is now mounted at `/app/` on the station server (Gio's request 1), and with `--lan` the start-up banner prints the phone link with the operator token, `http://<laptop>:8000/app/?op=<token>` (request 3). Without `--lan` it prints `http://127.0.0.1:8000/app/`.
- Checked in a phone-sized browser against `server.run --mock`: the app lists reach, push, row and the strength test as "on the arm" and the rest as "demo animation"; starting Forward reach starts a server session (`exercise: reach`, target 12), the app's rep counter and force bar follow the live feed, the session stops by itself at 12 reps, and the break screen shows "forward reach 30 cm, measured by the arm (SIMULATED)". No console errors. 368 tests pass.
- Not checked: the same on the real arm, the camera QR scan (I skipped the scan in the test), push/row/armtest from the app, and a real phone over the hotspot.

**2026-11-15 · Shiv · E2 follow-up: mock and API.md matched to the real engine; patient screen checked**
- Compared the mock with Shyan's engine on SimArm through the API and fixed two differences in server/mock.py and server/API.md section 6: pull's `setup` phase reports dial 0 (the mock said -0.6), and armtest goes idle, then per try `out` (3 s push) and `back` with rep_idx -1 (5 s rest), with the handle giving way a few cm (the mock rested 1 s in `idle` and moved 8 mm).
- Patient screen opened in headless Chrome against `--mock` for armtest, pull, push and reach: exercise name, "Move the handle to the far end", "Push and hold" / "Rest", best try and the rep line all show, no JavaScript errors. Not seen by a person on a real display yet. track.js still has no node run on my laptop.
- Found, for Shyan (E1) and Kian: a session started right after a `pull` session begins with the handle at the far end (0.70 m in the sim). An armtest started there sat in arm_mode `hold` from the first sample and recorded no tries in 120 s. Armtest twice in a row, and each exercise on a fresh arm, are fine. Not fixed (engine/robot question: who brings the handle back). Until then put `pull` last in a plan; API.md tells Mat and Gio the same.
- server + software + robot tests: 366 passed, 1 skipped (node).

**2026-11-15 · Shyan · screens handed to Kian**
- Kian builds L2 (physio screen) and L3 (operator console) in `server/screens/` as new files only (physio.*, operator.*), against `server.run --mock`. Shyan's robot session is adding `POST /api/arm/home` and a prepare rule (refuses unless within 2 cm of the start pose); the operator console should call home then prepare and show the server's `detail` on a refusal.

**2026-11-15 · Shiv · hand-on-handle rule for the real arm's force reading, friction, and the pull follow-up (software/)**
- SimArm options (off by default): `empty_force_pose_n_per_m`, `empty_force_moving_n` + `empty_force_moving_dir`, `friction_n`. With 3 N across the reach, 3 to 7 N while moving and 4.5 N friction the OLD engine carried an empty handle 12 to 18 cm on the assist side, tripped on a let-go in push, and never left pull's setup. So the sim now shows the real-arm problem.
- New values in `software/engine.py` (reasons in DECISIONS): `HAND_ON_N` 4.5 N (= `F_PRESENT` 1.5 + `EMPTY_REST_N` 3.0), `EMPTY_MOVING_N` 7.0 N taken off along the motion, `V_MOVING` 0.002 m/s, `MAX_BASELINE_N` 6.0 N (was 3.0), `NEAR_START_M` 0.03 m (was 0.02), new `HOLD_START_M` 0.02 m. Baseline is frozen while the handle moves. armtest walks its spring back after the last try too.
- Results with the effects on (sim): empty handle never arms or moves; assist-side let-go travel 7.3 cm with friction, 7.6 cm without (the same as before the change, limit 8 cm, so detection is not slower: the rep ends 0.5 s after the let-go as before); Shyan's nine push/pull/armtest let-go cases pass unchanged (no trip, seen on the first tick, session goes on); the handle ends 1.4 cm short of the start after the walk back (friction); all sessions of the four exercises complete; no start refused on a zeroed arm anywhere on the reach. Soak: 40 random sessions on one arm, 0 trips, 0 refusals.
- Pull follow-up fixed: any exercise started with the handle away from its path start begins in `setup` (reach axis free, arm never moves it) until the handle has been at the start for 1 s. pull then armtest on one arm through the server API now runs all three tries. Cause was the simulated patient hauling the handle back at 0.45 m/s (speed trip in 0.03 s), then a session stuck in hold.
- Tests: new `software/tests/test_real_arm_effects.py` (178). software + server + robot: 561 passed, 1 skipped (node). `software/EXERCISES.md` has the rule, the table of measured values and the limits.
- **Limits, not solved:** (1) the rule assumes the moving reading lies along the motion. If it points across the motion an empty handle still reads as held (sim: carried 19 cm, push let-go trips). (2) A real relaxed hand must read over 4.5 N; in the sim the limb reads 5.7 to 8 N. (3) A patient who cannot push 4.5 N cannot slide the handle in setup, push or pull (sim: strength under 0.2 stalls there). (4) Forces on screen include up to 7 N of the arm's own reading error while moving.
- **For Kian, to measure with `RehabHandle` before a person holds the handle** (list in software/EXERCISES.md): empty handle moving along the reach at 5 and 14 cm/s both ways, reading per axis (how much along the motion, how much across, which sign); empty at rest at 0/10/20/28 cm approached from each side (is the change under 3 N?); a relaxed arm on the handle, still and carried, per axis (is it over 4.5 N?); assist-side let-go travel (under 8 cm); let-go in push at -0.6 and in armtest at 15 to 20 N (no trip, stops about 1.5 cm short); force to start the handle moving with the reach axis free (4.5 N expected). If the across-motion part is over about 2 N, or a relaxed arm reads under 4.5 N, do not run the assist side with a person until the rule is changed.
- **For Shyan (server/, not edited):** the patient screen and the app show "Move the handle to the far end" for every `setup` sample; for reach, push and armtest it should say "Bring the handle back to the start" (setup is no longer pull-only; API.md section 6 and the mock say it is). After the last armtest try the phase is `back` for up to 2.5 s (with `done: true`) before `idle`. API.md still says starts are refused above 3 N; it is 6 N now. "Put pull last in a plan" is no longer needed.
- Checked against Shyan's 15 Nov arm run (`server/hw/results/drift_check_2026-11-15.json`, pushed while I was working): empty reading standing along the reach 0.04 to 2.76 N, so `EMPTY_REST_N` 3.0 covers it with 0.24 N to spare plus the 1.5 N margin; it lies mostly sideways and down, not along the reach, so I added a sim set with the pose reading across the reach (same results). While moving at 5 cm/s the whole reading peaked at 3.39 N, under the 4.5 N threshold whatever its direction. Still unmeasured: the reading at rep speed (14 cm/s) and its direction, and a relaxed hand on the handle.

**2026-11-15 · Shiv · two corrections to my hand-on-handle entry above**
- Fixed (software/engine.py, with tests): the baseline no longer absorbs a hand resting lightly on the handle. With the 4.5 N threshold a 4 N hand counts as empty and was tracked into the baseline (3.8 N in 60 s); the empty handle would then have read as held. The baseline now follows the reading only within 1.5 N of itself (slow drift still is followed).
- Corrected: against Shyan's 15 Nov data I wrote that `EMPTY_REST_N` 3.0 covers the standing readings with 0.24 N to spare. That is only true relative to the zero at the start pose (worst 2.76 N). The largest difference between any two standing readings is 3.30 N (20 cm out, on the way out against the way back), which is what applies when a session starts elsewhere on the reach. It is still under the 4.5 N threshold, with 1.2 N to spare. Constants unchanged; to be re-measured with the handle on.
- For Kian, two more measurements (software/EXERCISES.md items 7 and 8): 5 s of `tcp_vel` with the arm standing still (`V_MOVING` is 2 mm/s, a sim value), and a push rep with a normal grip letting the band bring the hand back (it must not be cut short as a let-go).
- Open, found by the soak, NOT caused by today's changes (the engine from before them does the same with the sim effects off): `push` with a simulated patient of strength 0.25 to 0.29 trips the speed limit (0.40 m/s) a few seconds in. The patient stalls against the band, the stall rescue ramps the resistance to zero over 1 s, and the patient, still pushing at full effort, runs away with the freed handle. Strength 0.2 and 0.35 and above are fine. Safe (the trip holds the arm) but the session is lost. Not fixed; candidates are a longer ramp or keeping some resistance on. Repro: `Engine(SimArm(SimPatient(strength=0.29), realtime=False), ..., exercise="push", reps=3)`.

**2026-11-15 13:15 · Shyan · start pose, zeroing and config on the real arm**
- Arm moved in joint space to a new start pose (two MoveJ legs, `server/hw/move_joints.py`, scale 3 then 2): hand (0.213, 0.470, 0.375), 0.516 m from the base, flange down. `robot/config.json` is filled (Shyan's agent, Kian OK): serial, start pose, `reach_axis` 0, new key `reach_sign` -1 (reach towards world -x). `force_sign` +1 is inferred, not push-tested, and stays in `placeholders`.
- Force estimate: after the joint moves the empty flange read 11 to 27 N (a constant -5.7 Nm offset on A2), steady for 60 s. `ZeroFTSensor` works on this arm and removes it (15.5 N to 0.2 N, `server/hw/zero_ft.py`). Zeroed at the start, along the 0.30 m reach the empty flange reads up to 2.8 N standing and 3.4 N moving, 0.9 N back at the start (`server/hw/drift_check.py`, results in `server/hw/README.md`).
- For Kian: `Arm.zero_force()` as written works (the primitive terminates in 0.1 s). Zero at the start pose before every set; the RUNBOOK needs that step. Everything here is with tool Flange: when the handle is mounted and set as the tool, redo start pose, zero, drift check and config.
- For Shiv: the empty handle reads above the engine's 1.5 N occupancy threshold along the reach; Shyan is changing it to 5 N with hysteresis in software/ (task swap) and will log it. Layout B (reach along y) is replaced by a reach along -x from this pose.
