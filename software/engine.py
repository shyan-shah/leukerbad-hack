"""The control engine: 100 Hz loop, rep state machine, hands-off rule, auto dial (package S4).

Implements the frozen interface of context/MASTER_PLAN.md section 4.4 using the rules of
section 4.2. It is built from the pure modules of software/: ``paths`` (the line),
``controller.command`` (target and stiffness), ``metrics.rep_metrics`` (per-rep numbers) and
``adapt.next_dial`` (auto dial). It works with ``robot.arm.Arm`` and ``software.sim_arm.SimArm``
through the section 4.3 interface only.

Each tick:
1. ``state = arm.get_state()``.
2. If ``state.mode`` is not "compliant" (hold, fault, idle): emit a Sample with phase "idle",
   send no commands, abandon any rep in progress.
3. Otherwise run the rep state machine (below), compute the target and stiffness, call
   ``set_target`` every tick (feeds the arm watchdog) and ``set_stiffness`` only when the
   stiffness tuple changes.
4. Emit a Sample (``on_sample``). At the end of a rep build a RepResult (``on_rep``) and, in
   auto mode, move the dial with ``next_dial``.

Rep state machine (section 4.2):
- ``idle``: soft hold at ``K_HOLD`` on all axes. Target: the path start while the hand is
  within ``HOLD_START_M`` of it, else the hand projected onto the path line (so the limb weight does not drag the
  target down and the person can bring the handle back). A rep
  is armed when the hand has been within ``NEAR_START_M`` of the start, measured along the
  reach axis, for ``ARM_DWELL_S`` and the handle is occupied.
- ``out``: reference clock starts when the rep is armed. Ends at progress ``OUT_DONE``
  (completed) or after ``OUT_TIMEOUT_S`` (not completed), then ``back``.
- ``back``: same law toward the start. Ends within ``HOLD_START_M`` of the start, or within
  ``NEAR_START_M`` once the handle has stopped (friction lag), or after
  ``BACK_TIMEOUT_S`` (team choice, so a hand that never returns cannot hang the session).
- Occupied: a hand was on the handle within the last ``OCCUPIED_WINDOW_S``. A tick counts as
  "hand on" when the hand force (``_hand_force``, below) is above ``HAND_ON_N`` for both the raw
  reading and the reading smoothed over ``FORCE_FILTER_S``. A noise spike alone (raw only) does
  not count, and letting go is seen as soon as the raw value drops (no added filter delay).
- Hand force (15 Nov, see DECISIONS.md): the real arm has no wrist sensor, and its force
  estimate with nothing on the handle changes by up to ``EMPTY_REST_N`` with pose and reads up
  to ``EMPTY_MOVING_N`` while the handle moves. So the hand force is the baseline-relative
  force with up to ``EMPTY_MOVING_N`` removed along the direction of motion (either sign)
  whenever the handle moves faster than ``V_MOVING``, and the threshold
  is ``HAND_ON_N = F_PRESENT + EMPTY_REST_N``. Every unknown is decided towards "empty": a
  hand that is missed only ends a rep, an empty handle taken for a hand would be driven.

Force baseline (the real arm's sensor reads several N with nothing touching it, see
context/BRINGUP_FINDINGS.md and DECISIONS.md): ``start()`` averages ``BASELINE_N`` force
readings BEFORE compliance starts, with the handle empty (the same "nobody touching" rule
as ``zero_force``), and refuses to start with a RuntimeError if that baseline is over
``MAX_BASELINE_N`` (sensor not zeroed, or something resting on the handle). Every force
the engine uses (occupancy, Samples, metrics) is ``state.force - baseline``. While the
phase is idle, the handle is not occupied, it is not moving and the smoothed reading is within
``F_PRESENT`` of the baseline, the baseline follows the raw reading with time constant
``BASELINE_TRACK_S``, so slow drift does not build up while the handle is empty. The reading
of a moving empty handle is never absorbed, and neither is a hand resting lightly on the
handle (under ``HAND_ON_N`` but over ``F_PRESENT``). Drift while the handle is held is not tracked (re-zero between sets on the real arm).
For ``SimArm`` the simulated patient keeps hands off while the baseline is taken.
- Hands-off rule, assist side only (dial > 0): if the handle is not occupied during a rep the
  rep ends now as not completed and the phase goes to idle. While the handle is empty the
  target is latched at the point where the hand was when it became empty (``K_HOLD``), so an
  empty handle is never driven along the path.
- Hands-off rule, resist side (dial < 0) and the strength test (see DECISIONS.md, 15 Nov):
  the band and the test hold are loaded springs, so on a let-go (``_let_go``) the rep or try
  ends, the target is put on the hand at once, the reach-axis stiffness ramps to zero over
  ``RESIST_RAMP_S`` in ``RESIST_RAMP_STEP_S`` steps, and then, in the soft hold, the target
  walks back to the path start at ``TEST_RETURN_SPEED``. Engine phase "release", Samples
  labelled "idle". A hand back on the handle ends the walk.
- Stall rescue: on the assist side, along-path speed under ``STALL_SPEED`` for
  ``STALL_ASSIST_S`` before 90% phase progress marks the rep rescued (the controller raises
  the dial to at least 0.6). On the resist side (dial < 0) a ``STALL_RESIST_S`` stall marks it
  rescued and the resistance is ramped down to transparent over ``RESIST_RAMP_S`` in steps of
  ``RESIST_RAMP_STEP_S`` (a one-step drop made a patient pushing against it lurch and trip the
  speed limit; see DECISIONS.md). Steps are at least 0.1 s apart so each stiffness change can
  take effect on the arm before the next. Not applied at exactly transparent.

Metrics: every RepResult metric (duration, ROM, path error, SPARC, force, contribution) is
computed on the ``out`` phase slice only, as section 4.2 requires for contribution. If SPARC
is undefined (the hand did not move) it is reported as 0.0. Contribution counts the arm's
own work: each out sample also records the commanded spring force ``K * (target - hand)``
of the command in effect at that sample (the one sent on the previous tick), passed to
``metrics.contribution`` as ``robot_force``.

Drivers: ``start()`` runs the 100 Hz thread for a real-time arm (``Arm`` or
``SimArm(realtime=True)``). For ``SimArm(realtime=False)`` no thread is started; the caller
drives the engine and the sim together with ``run_for(seconds)`` (one ``tick()`` then
``arm.step(DT)`` per 10 ms), which is deterministic. Every timer uses ``ArmState.t``.

Safety: any exception in a tick (including from a callback) calls ``arm.hold()`` first and
is then re-raised.

Exercise presets (package E1, software/exercises.py and software/EXERCISES.md):
``Engine(..., exercise="reach" | "push" | "pull" | "armtest" | "circle", reps=None)``.
"reach" is everything described above. "push" is the same line on the resist side. "pull"
runs the line backwards from the far end. Any exercise whose session starts with the handle
more than ``NEAR_START_M`` from its path start (pull always, the others after a pull or
whenever the handle was left out) begins with a "setup" phase: transparent along the line,
walls on, until the person has held the handle at the path start for ``SETUP_DWELL_S``. The
arm never drives the handle there. "armtest"
is an isometric test (``_tick_test``) and "circle" a robot-led circle (``_tick_guided``).
``snapshot()`` carries ``exercise``, ``kind``, ``reps_target`` and ``done``.

The timing constants below are section 4.2 start values or team choices; they are not
clinical rules.
"""

from __future__ import annotations

import datetime as _dt
import threading
import time
from collections import deque

import numpy as np

from server.contract import RepResult, Sample, SessionSummary
from software import controller
from software import exercises
from software import strength_model
from software.adapt import AUTO_FLOOR, mode_of, next_dial
from software.metrics import contribution, force_stats, path_error, rep_metrics, rom, sparc
from software.paths import LinePath

__all__ = ["Engine", "DT"]

DT = 0.01                    # s, 100 Hz
NEAR_START_M = 0.03          # m along the reach axis: "at the start" for arming, ending a rep and setup (2 cm until 15 Nov; friction dead band is up to 2.5 cm)
HOLD_START_M = 0.02          # m: inside this the idle soft hold pulls a held handle onto the start point; outside it follows the hand
ARM_DWELL_S = 1.0            # s at the start (and occupied) before a rep is armed
OUT_DONE = 0.9               # progress that completes the out phase
OUT_TIMEOUT_S = 10.0         # s, out phase gives up (not completed)
BACK_TIMEOUT_S = 10.0        # s, back phase gives up and the rep ends anyway (team choice)
F_PRESENT = 1.5              # N, margin above the largest empty-handle reading at rest
EMPTY_REST_N = 3.0           # N, largest change of the empty-handle reading with pose, at rest (14 Nov: 0.7 to 3.2 N)
EMPTY_MOVING_N = 7.0         # N, largest empty-handle reading caused by motion (14 Nov: 3 to 7 N), taken along the motion
HAND_ON_N = F_PRESENT + EMPTY_REST_N   # N, hand force above this means "a hand is on the handle"
V_MOVING = 0.002             # m/s, above this the handle counts as moving (motion allowance on, baseline frozen)
OCCUPIED_WINDOW_S = 0.5      # s, occupied if force exceeded F_PRESENT within this window
FORCE_FILTER_S = 0.05        # s, smoothing time constant of the force used for occupancy (noise)
BASELINE_N = 30              # force readings averaged for the empty-handle baseline at start()
MAX_BASELINE_N = 6.0         # N, a larger empty-handle baseline refuses to start (not zeroed, wrong tool, or a hand on it)
BASELINE_TRACK_S = 20.0      # s, time constant of baseline tracking while idle and empty (drift)
STALL_SPEED = 0.01           # m/s along the path
STALL_ASSIST_S = 1.5         # s stall on the assist side before rescue
STALL_RESIST_S = 3.0         # s stall on the resist side before dropping to transparent
STALL_MAX_PROGRESS = 0.9     # stall rescue only before this phase progress
RESIST_RAMP_S = 1.0          # s, resist-side rescue ramps the resistance to 0 over this
RESIST_RAMP_STEP_S = 0.1     # s between ramp steps (10 steps over RESIST_RAMP_S)
TEST_RETURN_SPEED = 0.02     # m/s, the target walks back to the start at this speed (armtest rest, release)
RELEASE_SPRING_N = 1.0       # N, a commanded spring pull above this needs a hand to hold it
ARM_HOLD_S = 0.6             # s of hand force in the firm hold at the start before a rep is armed (15 Nov, replaces ARM_DWELL_S for line reps and tries)
ARM_DIST_M = 0.05            # m (3D) from the start: inside this a rep can be armed and the start is held firmly
ARM_MAX_SPEED = 0.05         # m/s: a faster handle does not arm ("hold still")
ARM_MAX_N = 25.0             # N: a harder push does not arm ("pushing too hard")
IDLE_FRICTION_N = 4.5        # N of the idle hold's pull that the arm's own friction can be carrying
IDLE_SPRING_N = 10.0          # N: an idle hold pulling harder than this needs a hand pushing back with at least half of it
ARM_HANDOVER_S = 0.25        # s after arming with the target on the hand (longer than the stiffness latency)
ARM_GRACE_S = 0.5            # s after arming during which the one-tick let-go test is off
FIRM_EXIT_M = 0.07           # m: the firm hold is given up only beyond this (arming still needs ARM_DIST_M)
FIRM_RAMP_S = 1.5            # s, the idle hold at the start goes from k_hold to k_max over this
FIRM_STEP_S = 0.25           # s between its steps (longer than the arm's stiffness latency, up to 0.2 s)
GO_COUNTDOWN_S = 3.0         # s between Engine.go() and the rep it arms
GO_MIN_N = 2.0               # N of hand force needed for go() to arm the rep
CAL_PUSH_S = 3.0             # s, the comfortable push (handle held still)
CAL_START_N = 2.0            # N along the push direction: the push has begun
CAL_WINDOW_S = 1.0           # s, comfort force = mean over the steadiest window of this length
CAL_MIN_N = 5.0              # N, a comfortable push under this gives the lightest resistance
CAL_WAIT_S = 20.0            # s without a push: give up, lightest resistance
SETUP_DWELL_S = 1.0          # s at the far end before a "far" exercise (pull) leaves the setup phase
EXERCISE = "reach_line"      # SessionSummary.exercise for the default "reach" preset (unchanged)


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _tup3(a) -> tuple[float, float, float]:
    return (float(a[0]), float(a[1]), float(a[2]))


class Engine:
    """Section 4.4 engine. See the module docstring."""

    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool,
                 reach_axis: int = 0, reach_sign: int = 1, reach_m: float | None = None,
                 dial: float | None = None, auto: bool | None = None,
                 on_sample=None, on_rep=None,
                 exercise: str = "reach", reps: int | None = None,
                 calibrate: bool | None = None, calibration_state: dict | None = None) -> None:
        """``exercise`` is a preset id from software/exercises.py (default "reach": unchanged
        behaviour). ``reach_m`` given overrides the preset's length. ``dial`` and ``auto`` are
        the caller's for "reach"; for the other presets ``auto`` is the preset's and ``dial`` is
        used only if it is on the preset's side (a resist preset ignores dial >= 0). ``reps``
        given: no new rep is armed after that many. ``reps=None``: reach/push/pull keep running
        (the preset's default_reps is only reported), armtest and circle stop after theirs."""
        if reach_axis not in (0, 1, 2):
            raise ValueError(f"reach_axis must be 0, 1 or 2, got {reach_axis}")
        self.preset = exercises.get(exercise)
        p = self.preset
        if reach_m is None:
            reach_m = p.reach_m
        if not reach_m > 0:
            raise ValueError(f"reach_m must be > 0, got {reach_m}")
        if reps is not None and (int(reps) != reps or reps < 1):
            raise ValueError(f"reps must be a positive integer, got {reps}")
        if p.id == "reach":
            dial = p.dial if dial is None else dial
            auto = p.auto if auto is None else auto
        else:
            auto = p.auto
            if dial is None or p.kind != "resist" or not dial < 0:
                dial = p.dial
        self.arm = arm
        self.session_id = str(session_id)
        self.patient_id = str(patient_id)
        self.simulated = bool(simulated)
        self.exercise = p.id
        self.reach_axis = int(reach_axis)
        self.config_reach_sign = 1 if reach_sign >= 0 else -1     # the configured reach direction
        self.reach_sign = self.config_reach_sign * p.direction    # direction of this exercise's "out"
        self.reach_m = float(reach_m)
        self.reps_target = int(reps) if reps is not None else p.default_reps
        # hard stop on the count: always for tries and circles, for line reps only when asked
        self._reps_limit = self.reps_target if (reps is not None or p.kind in ("test", "guided")) else None
        self.on_sample = on_sample
        self.on_rep = on_rep

        self._lock = threading.RLock()
        self._dial = float(np.clip(dial, -1.0, 1.0))
        self._auto = bool(auto)
        self._latest: Sample | None = None
        self._arm_mode: str | None = None
        self.rep_count = 0
        self.reps: list[RepResult] = []
        self.started_at: str | None = None
        self.error: BaseException | None = None

        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._started = False
        self._explicit_cues = False          # simulated patient cued by the engine (set in start())

        self.path: LinePath | None = None
        self._t0: float | None = None
        self.force_baseline = np.zeros(3)   # N, empty-handle sensor reading (set by start())
        self._f_filt: np.ndarray | None = None
        self._vel = np.zeros(3)             # handle velocity of the current tick
        self._f_now = np.zeros(3)           # baseline-relative force of the current tick (unfiltered)
        self._f_hist: list[np.ndarray] = []  # calibrate: recent force readings
        self._default_limits = getattr(arm, "limits", None)
        self._last_tick_t: float | None = None
        # comfortable-push calibration (contract of 15 Nov, server/API.md section 7): resist presets only
        can_cal = p.kind == "resist"
        self.calibrate = can_cal and (True if calibrate is None else bool(calibrate))
        self.calibration_state = (dict(calibration_state) if isinstance(calibration_state, dict) and calibration_state
                                  else strength_model.new_state())
        self.calibration_state_after = dict(self.calibration_state)
        self._cal: dict | None = None if not can_cal else self._cal_dict(
            "waiting" if self.calibrate else "skipped",
            reason="waiting for a push" if self.calibrate else "calibration turned off for this session")
        self._cal_pending = self.calibrate   # the calibrate phase has not run yet
        self._cal_anchor: np.ndarray | None = None
        self._cal_t0 = 0.0                   # arm time the calibrate phase began
        self._cal_push_t0: float | None = None
        self._cal_f: list[float] = []
        self._dial_by_user = False           # set_dial() after start: calibration does not override it
        self._test_limits = False
        self._arming = {"progress": 0.0, "reason": None}
        self._go_at: float | None = None
        self._go_req = False
        self._resume_req = False
        self._reset_rep_state()

    # ------------------------------------------------------------------ interface (4.4)

    def start(self) -> None:
        """``arm.start_compliance()``, then the 100 Hz thread (real-time arms only)."""
        if self._started:
            raise RuntimeError("engine already started")
        # Make the simulated patient reach along the same line as the engine.
        if hasattr(self.arm, "patient") and hasattr(self.arm, "reach_m"):
            self.arm.reach_axis = self.reach_axis
            self.arm.reach_sign = self.reach_sign
            self.arm.reach_m = self.reach_m
        baseline = self._measure_baseline()
        mag = float(np.linalg.norm(baseline))
        if mag > MAX_BASELINE_N:
            raise RuntimeError(
                f"force sensor reads {mag:.1f} N with the handle empty "
                f"(fx {baseline[0]:+.1f}, fy {baseline[1]:+.1f}, fz {baseline[2]:+.1f} N; limit "
                f"{MAX_BASELINE_N:.1f} N). The sensor is not zeroed, the wrong tool is selected on "
                "the robot, or something is resting on the handle. With nobody touching the arm, "
                "run arm.zero_force() (robot/RUNBOOK.md), then start the session again.")
        self.force_baseline = baseline
        self._default_limits = self.arm.limits       # before any test profile
        self.arm.start_compliance()
        # The line always lies between the arm's start pose and the far end of the configured
        # reach. "far" presets (pull) run it backwards: path start = the far end.
        start = np.asarray(self.arm.start_pos, dtype=float)
        if self.preset.start_at == "far":
            start = start.copy()
            start[self.reach_axis] += self.config_reach_sign * self.reach_m
        end = start.copy()
        end[self.reach_axis] += self.reach_sign * self.reach_m
        self.path = LinePath(_tup3(start), _tup3(end))
        if abs(self._progress(self.arm.get_state().pos)) * self.reach_m > NEAR_START_M:
            # The handle is not at this exercise's start (pull: the far end; any other exercise
            # after a pull, or when the handle was left out): the person brings it there first.
            self._phase = "setup"
        if self._phase != "setup" and self._cal_pending:
            self._phase = "calibrate"
        if hasattr(self.arm, "patient") and hasattr(self.arm, "cue"):
            # Simulated patient: where its reach starts, and whether the engine cues it itself
            # (pull and armtest) or it follows the stiffness change as before (reach, push).
            # (15 Nov: the idle hold at the start is now at k_max, so the stiffness change no
            # longer means "go"; every preset but the circle cues the patient explicitly)
            self._explicit_cues = self.preset.kind != "guided"
            self.arm.reach_origin = _tup3(start)
            if self._phase == "setup":
                self.arm.auto_cue = False           # the setup stiffness change is not a "go"
                self.arm.cue("back")                # move smoothly to the path start
            else:
                self.arm.auto_cue = not self._explicit_cues
                self._sim_cue("rest")
        self.started_at = _now_iso()
        self._started = True
        self._stop_evt.clear()
        if getattr(self.arm, "realtime", True):
            self._thread = threading.Thread(target=self._loop, name="engine", daemon=True)
            self._thread.start()

    def _measure_baseline(self) -> np.ndarray:
        """Mean of BASELINE_N force readings, handle empty, before compliance starts."""
        realtime = getattr(self.arm, "realtime", True)
        patient = getattr(self.arm, "patient", None) if hasattr(self.arm, "reach_m") else None
        was_present = getattr(patient, "present", None)
        if patient is not None:
            patient.present = False          # the simulated person follows the procedure
        try:
            readings = []
            for i in range(BASELINE_N):
                readings.append(np.asarray(self.arm.get_state().force, dtype=float))
                if realtime and i < BASELINE_N - 1:
                    time.sleep(DT)
            return np.mean(readings, axis=0)
        finally:
            if patient is not None:
                patient.present = was_present

    def stop(self) -> SessionSummary:
        """``arm.hold()``, thread joined. Returns the session summary."""
        self._stop_evt.set()
        th, self._thread = self._thread, None
        try:
            if th is not None and th is not threading.current_thread():
                th.join(timeout=2.0)
        finally:
            try:
                self._set_test_limits(False)
            finally:
                self.arm.hold()
        with self._lock:
            if self._started and self._phase in ("out", "back") and self._rep_idx >= 0:
                self._abort_rep(self._dial)          # a rep in progress at stop() is recorded as not completed
                self._phase = "idle"
            if self.reps and self.preset.kind == "resist":
                self.calibration_state_after = strength_model.update(self.calibration_state, self.reps)
        return SessionSummary(
            session_id=self.session_id, patient_id=self.patient_id,
            started_at=self.started_at or _now_iso(), ended_at=_now_iso(),
            exercise=EXERCISE if self.exercise == "reach" else self.exercise,
            n_reps=self.rep_count, simulated=self.simulated)

    def set_dial(self, dial: float, auto: bool | None = None) -> None:
        """Set the dial (clamped to [-1, 1]); ``auto`` True/False switches auto mode."""
        if not np.isfinite(dial):
            raise ValueError(f"dial must be finite, got {dial}")
        with self._lock:
            self._dial = float(np.clip(dial, -1.0, 1.0))
            self._dial_by_user = True
            if auto is not None:
                self._auto = bool(auto)

    def snapshot(self) -> dict:
        """Latest Sample as a dict plus rep_count, auto and arm_mode. Thread-safe."""
        with self._lock:
            d = self._latest.to_dict() if self._latest is not None else {}
            return d | {"rep_count": self.rep_count, "auto": self._auto,
                        "arm_mode": self._arm_mode, "exercise": self.exercise,
                        "kind": self.preset.kind, "reps_target": self.reps_target,
                        "done": self.done, "arming": dict(self._arming),
                        "calibration": self._calibration_snapshot()}

    def _calibration_snapshot(self) -> dict | None:
        """Contract shape (server/API.md section 7); None for presets without calibration."""
        return None if self._cal is None else dict(self._cal)

    @staticmethod
    def _cal_dict(status, progress=0.0, comfort=None, resistance=None, fraction=None, reason=None) -> dict:
        return {"status": status, "progress": float(progress), "comfort_force_n": comfort,
                "resistance_n": resistance, "fraction": fraction, "reason": reason}

    def _max_resistance_n(self) -> float:
        """The most the band can pull with the DEFAULT arm limits (15 N)."""
        lim = self._default_limits
        return float(min(controller.K_RESIST, lim.k_max) * min(controller.MAX_LEAD, lim.max_lead_m))

    def _set_test_limits(self, on: bool) -> None:
        if hasattr(self.arm, "set_test_limits") and on != self._test_limits:
            self.arm.set_test_limits(on)
            self._test_limits = on
            self._k_sent = None              # the arm changed its stiffness: send ours again

    def _end_calibration(self, comfort: float | None, reason: str | None, pos=None) -> None:
        """Close the calibrate phase. ``reason`` None: a valid push, resistance from the strength
        model, status "done". Otherwise the lightest resistance, status "skipped", with the reason."""
        mx = self._max_resistance_n()
        if reason is None:
            r = strength_model.resistance_for(comfort, self.calibration_state, mx)
            self._cal = self._cal_dict("done", 1.0, round(float(comfort), 2), round(r["resistance_n"], 2),
                                       r["fraction"], None)
        else:
            r = strength_model.resistance_for(0.0, self.calibration_state, mx)
            self._cal = self._cal_dict("skipped", 0.0, None if comfort is None else round(float(comfort), 2),
                                       round(r["resistance_n"], 2), None, reason)
        with self._lock:
            if not self._dial_by_user:
                self._dial = float(r["dial"])
        self._cal_pending = False
        self._cal_push_t0 = None
        self._sim_cue("rest")
        if pos is not None and self._started:
            # the hold is loaded by the push: target onto the hand first, then the default limits
            # (the arm drops to k_hold), then the ordinary idle hold walks the target back.
            self.arm.set_target(_tup3(pos))
        self._set_test_limits(False)
        self._latch = None if pos is None else np.asarray(pos, dtype=float).copy()
        self._firm = False
        self._arm_acc = 0.0
        self._phase = "idle"

    def _tick_calibrate(self, state, t_arm, t, pos, force, dt_tick) -> None:
        """One comfortable push with the handle held still (k_max of the test profile if the arm
        has one). Waits for CAL_START_N along the push direction, then CAL_PUSH_S of pushing."""
        if self._cal_anchor is None:
            self._cal_anchor = np.asarray(pos, dtype=float).copy()
            self._cal_t0 = t_arm
            self._set_test_limits(True)
            self._sim_cue("out")
        along = float(force[self.reach_axis]) * self.reach_sign
        along_f = float(self._f_filt[self.reach_axis]) * self.reach_sign
        km = float(self.arm.limits.k_max)
        if self._cal_push_t0 is None:
            if along_f > CAL_START_N and along > CAL_START_N:
                self._cal_push_t0 = t_arm
                self._cal_f = []
            elif t_arm - self._cal_t0 >= CAL_WAIT_S:
                self._end_calibration(None, "no push within 20 s, lightest resistance set", pos)
        if self._cal_push_t0 is not None and self._phase == "calibrate":
            self._cal_f.append(along)
            el = t_arm - self._cal_push_t0
            self._cal = self._cal_dict("pushing", min(1.0, el / CAL_PUSH_S))
            n = len(self._cal_f)
            w = int(round(CAL_WINDOW_S / DT))
            # let go: nothing on the handle for 0.3 s (the hold is stiff, so the handle stays put)
            k = int(round(0.3 / DT))
            # ... or, at once, a loaded hold with nothing pushing back (as in the idle hold): waiting
            # 0.3 s let the 1500 N/m hold throw the handle back and trip the speed limit
            pull = km * (self._cal_anchor - pos)
            spring = float(np.linalg.norm(pull))
            thrown = (spring > IDLE_SPRING_N
                      and -float(np.asarray(force) @ (pull / spring)) + IDLE_FRICTION_N < 0.5 * spring)
            if thrown or (n > k and max(np.linalg.norm(self._f_hist[-k:], axis=1)) < CAL_START_N):
                self._end_calibration(None, "let go during the push, lightest resistance set", pos)
            elif el >= CAL_PUSH_S:
                f = np.asarray(self._cal_f)
                if len(f) >= w:
                    c = np.cumsum(np.insert(f, 0, 0.0))
                    c2 = np.cumsum(np.insert(f * f, 0, 0.0))
                    mean = (c[w:] - c[:-w]) / w
                    var = (c2[w:] - c2[:-w]) / w - mean ** 2
                    comfort = float(mean[int(np.argmin(var))])
                else:
                    comfort = float(f.mean())
                if comfort < CAL_MIN_N:
                    self._end_calibration(comfort, "push under 5 N, lightest resistance set", pos)
                else:
                    self._end_calibration(comfort, None, pos)
        self._f_hist.append(np.asarray(force, dtype=float))
        if len(self._f_hist) > 200:
            del self._f_hist[:100]
        if self._phase != "calibrate":       # ended on this tick: soft hold on the hand
            kh = float(self.arm.limits.k_hold)
            self._send(_tup3(pos), (kh, kh, kh))
            self._arming = {"progress": 0.0, "reason": "hold still"}
            self._emit(t, state, _tup3(pos), self._dial, "idle", -1, force)
            return
        if self._cal_push_t0 is None:
            self._cal = self._cal_dict("waiting", 0.0, reason="waiting for a push")
        self._arming = {"progress": 0.0, "reason": "calibrating"}
        target = _tup3(self._cal_anchor)
        self._send(target, (km, km, km))
        self._emit(t, state, target, 0.0, "calibrate", -1, force)

    def go(self) -> None:
        """Operator "go": after GO_COUNTDOWN_S the next rep is armed if the handle is within
        ARM_DIST_M of the start and the hand force is above GO_MIN_N. Otherwise nothing happens."""
        with self._lock:
            self._go_req = True

    def resume(self) -> None:
        """After a trip, once the arm has been homed and prepared: restart compliance and carry
        on with the same session (rep count and reps are kept)."""
        with self._lock:
            self._resume_req = True
        if not getattr(self.arm, "realtime", True) or self._thread is None:
            self._do_resume()

    def _do_resume(self) -> None:
        with self._lock:
            if not self._resume_req:
                return
            self._resume_req = False
            if not self._started:
                raise RuntimeError("resume() before start()")
            if self._phase in ("out", "back"):
                self._abort_rep(self._dial)      # resume() in the middle of a rep: it is recorded, not lost
            if self._phase == "calibrate":
                self._test_limits = bool(getattr(self.arm, "test_limits_on", False))
                self._end_calibration(None, "interrupted by resume, lightest resistance set")
            if self.arm.get_state().mode != "compliant":
                self.arm.start_compliance()
            count, reps = self.rep_count, self.reps
            self._reset_rep_state()
            self.rep_count, self.reps = count, reps
            self._last_force_t = None
            self._f_filt = None
            if abs(self._progress(self.arm.get_state().pos)) * self.reach_m > NEAR_START_M:
                self._phase = "setup"
                if self._explicit_cues:
                    self.arm.cue("back")
            else:
                self._sim_cue("rest")

    @property
    def done(self) -> bool:
        """True once the planned number of reps (tries, circles) has been recorded."""
        return self.rep_count >= self.reps_target

    # ------------------------------------------------------------------ extras

    @property
    def dial(self) -> float:
        with self._lock:
            return self._dial

    @property
    def auto(self) -> bool:
        with self._lock:
            return self._auto

    @property
    def phase(self) -> str:
        """Current phase: "idle", "setup", "out", "back", or "release" (after a let-go on the
        resist side or in the strength test; its Samples are labelled "idle")."""
        return self._phase

    @property
    def phase_started_at(self) -> float:
        """Arm-clock time (``ArmState.t``) at which the current out/back phase began."""
        return self._phase_t0

    def run_for(self, seconds: float) -> None:
        """Drive a ``SimArm(realtime=False)``: per 10 ms, one ``tick()`` then ``arm.step(DT)``."""
        if not self._started:
            raise RuntimeError("run_for() before start()")
        if getattr(self.arm, "realtime", True):
            raise RuntimeError("run_for() is only for SimArm(realtime=False); start() runs the thread")
        for _ in range(int(round(seconds / DT))):
            self.tick()
            self.arm.step(DT)

    def run_until_reps(self, n: int, max_s: float = 600.0) -> None:
        """``run_for`` in 10 ms steps until ``rep_count >= n`` or ``max_s`` sim seconds pass."""
        steps = int(round(max_s / DT))
        for _ in range(steps):
            if self.rep_count >= n:
                return
            self.run_for(DT)

    # ------------------------------------------------------------------ loop

    def _loop(self) -> None:
        next_t = time.monotonic()
        while not self._stop_evt.is_set():
            try:
                self.tick()
            except BaseException as e:  # tick already held the arm
                self.error = e
                raise
            next_t += DT
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()  # fell behind: do not try to catch up

    def tick(self) -> None:
        """One control step. Any exception holds the arm first, then re-raises."""
        try:
            self._tick()
        except BaseException:
            self.arm.hold()
            raise

    def _reset_rep_state(self) -> None:
        self._phase = "idle"
        self._phase_t0 = 0.0
        self._near_since: float | None = None
        self._last_force_t: float | None = None
        self._latch: np.ndarray | None = None
        self._k_sent: tuple[float, float, float] | None = None
        self._cmd: tuple[np.ndarray, np.ndarray] | None = None  # (target, k) last sent
        self._theta = 0.0                    # circle angle (guided presets)
        self._test_offset = 0.0              # m along the reach: armtest target offset during rest
        self._rel_k = np.zeros(3)            # release: stiffness when the handle was let go
        self._rel_t0 = 0.0
        self._rel_walk = False
        self._firm = False                   # idle: holding the start at k_max
        self._arm_acc = 0.0                  # s of arming force collected
        self._firm_t0 = 0.0
        self._clear_rep()

    def _clear_rep(self) -> None:
        self._rep_idx = -1
        self._rep_dial = 0.0
        self._rep_t0 = 0.0
        self._rescued = False
        self._rescued_at = 0.0
        self._stall_since: float | None = None
        self._completed = False
        self._out_t: list[float] = []
        self._out_pos: list[tuple[float, float, float]] = []
        self._out_force: list[tuple[float, float, float]] = []
        self._out_robot: list[tuple[float, float, float]] = []

    def _progress(self, pos) -> float:
        start = np.asarray(self.path.start)
        return float((np.asarray(pos) - start)[self.reach_axis] * self.reach_sign / self.reach_m)

    def _on_line(self, pos) -> np.ndarray:
        """Hand projected onto the path line, clamped to the segment."""
        return self.path.point_at(self._progress(pos))

    def _beside_hand(self, pos) -> np.ndarray:
        """Hand projected onto the path line, NOT clamped to the segment: a target here pulls
        the handle back onto the line but never along the reach (armtest and circle idle)."""
        return np.asarray(self.path.start, dtype=float) + self._progress(pos) * self.reach_m * self.path.axis()

    def _tick(self) -> None:
        if self._resume_req:
            self._do_resume()
        state = self.arm.get_state()
        t_arm = float(state.t)
        if self._t0 is None:
            self._t0 = t_arm
        t = t_arm - self._t0
        pos = np.asarray(state.pos, dtype=float)
        raw_force = np.asarray(state.force, dtype=float)
        force = raw_force - self.force_baseline
        self._f_now = force
        dt_tick = DT if self._last_tick_t is None else float(np.clip(t_arm - self._last_tick_t, 0.0, 0.1))
        self._last_tick_t = t_arm
        if self._f_filt is None:
            self._f_filt = force.copy()
        else:
            self._f_filt = self._f_filt + (force - self._f_filt) * min(1.0, dt_tick / FORCE_FILTER_S)
        with self._lock:
            dial = self._dial
            self._arm_mode = state.mode

        if state.mode != "compliant":
            # hold, fault or idle: never command. Abandon any rep in progress.
            if self._phase in ("out", "back"):
                self._abort_rep(dial)
            if self._phase == "calibrate":
                self._test_limits = False        # the arm restored its default profile itself
                self._end_calibration(None, "the arm stopped during the push, lightest resistance set")
            self._phase = "idle"
            self._near_since = None
            self._latch = None
            self._k_sent = None  # re-send stiffness if compliance is restarted
            self._cmd = None
            self._firm = False
            self._arm_acc = 0.0
            self._go_at = None
            self._arming = {"progress": 0.0, "reason": None}
            self._emit(t, state, _tup3(pos), dial, "idle", -1, force)
            return

        # occupied? (hand force of the raw AND the smoothed reading above HAND_ON_N)
        vel = np.asarray(state.vel, dtype=float)
        self._vel = vel
        # (the robot-led circle moves the handle up and down by design, where a limb's weight
        # lies along the motion, so it keeps the allowance along the reach only; it is not live)
        reach_only = self.preset.kind == "guided"
        if self._hand_on(force, vel, reach_only) and self._hand_on(self._f_filt, vel, reach_only):
            self._last_force_t = t_arm
        occupied = (self._last_force_t is not None
                    and t_arm - self._last_force_t <= OCCUPIED_WINDOW_S)
        # follow slow sensor drift while the handle is empty, at rest, and nothing is happening
        # (never a moving handle's reading, and never more than F_PRESENT away from the baseline:
        # drift is slow and stays inside that, a light hand resting on the handle does not)
        if (self._phase in ("idle", "setup") and not occupied
                and float(np.linalg.norm(vel)) < V_MOVING
                and float(np.linalg.norm(self._f_filt)) < F_PRESENT):
            self.force_baseline = (self.force_baseline
                                   + (raw_force - self.force_baseline) * (dt_tick / BASELINE_TRACK_S))

        s = self._progress(pos)
        near_start = abs(s) * self.reach_m <= NEAR_START_M
        at_hold_start = abs(s) * self.reach_m <= HOLD_START_M

        # setup: the session began with the handle away from this exercise's path start (pull:
        # the far end; anything started after a pull). Transparent along the line, walls on,
        # until the person has held the handle at the path start. The arm never drives it there.
        if self._phase == "setup":
            if near_start:
                if self._near_since is None:
                    self._near_since = t_arm
                if t_arm - self._near_since >= SETUP_DWELL_S:
                    self._phase = "calibrate" if self._cal_pending else "idle"
                    self._near_since = None
                    if hasattr(self.arm, "patient") and hasattr(self.arm, "cue"):
                        self.arm.auto_cue = not self._explicit_cues
            else:
                self._near_since = None
            if self._phase == "setup":
                # Target beside the hand on the path line (not clamped to the segment: a handle
                # left beyond the path end must not be pulled to it), reach axis free, walls on.
                target = _tup3(self._beside_hand(pos))
                k = [float(controller.K_WALL)] * 3
                k[self.reach_axis] = 0.0
                self._send(target, (k[0], k[1], k[2]))
                self._emit(t, state, target, 0.0, "setup", -1, force)
                return

        if self._phase == "calibrate":
            self._tick_calibrate(state, t_arm, t, pos, force, dt_tick)
            return
        if self._phase == "release":
            self._tick_release(state, t_arm, t, pos, force, occupied, dial, dt_tick)
            return
        if self.preset.kind == "test":
            self._tick_test(state, t_arm, t, pos, force, occupied, s, near_start, dial, dt_tick)
            return
        if self.preset.kind == "guided":
            self._tick_guided(state, t_arm, t, pos, force, occupied, near_start, dial, dt_tick)
            return

        # hands-off rule, resist side: the band is a loaded spring, so letting go must not let
        # it throw the handle back. End the rep and release the spring gently.
        if self._phase in ("out", "back") and dial < 0 and self._let_go(force, pos, occupied):
            self._finish_rep(dial, aborted=True)
            self._begin_release(t_arm, pos)
            self._tick_release(state, t_arm, t, pos, force, occupied, dial, dt_tick)
            return

        # hands-off rule, assist side
        if self._phase in ("out", "back") and dial > 0 and not occupied:
            self._finish_rep(dial, aborted=True)
            self._phase = "idle"
            self._near_since = None

        # idle -> out (firm hold at the start, hand force for ARM_HOLD_S; see _idle_hold)
        idle_cmd = None
        if self._phase == "idle":
            tgt_i, k_i, armed = self._idle_hold(t_arm, pos, occupied, dt_tick, not self._limit_reached())
            idle_cmd = (tgt_i, k_i)
            if armed:
                self._begin_rep(t_arm, t, dial)
                self._last_force_t = t_arm       # the arming force is a hand: occupied from here
                occupied = True

        # record the out slice (strictly increasing time only)
        if self._phase == "out" and (not self._out_t or t > self._out_t[-1]):
            self._out_t.append(t)
            self._out_pos.append(_tup3(pos))
            self._out_force.append(_tup3(force))
            self._out_robot.append(self._spring_force(pos))
        # the Sample is labelled with the phase it was recorded in (the tick that reaches
        # OUT_DONE is the last "out" sample, the tick that gets back to the start the last "back")
        label_phase, label_idx = self._phase, self._rep_idx

        # phase transitions on progress / time
        if self._phase == "out":
            t_in = t_arm - self._phase_t0
            if s >= OUT_DONE or t_in >= OUT_TIMEOUT_S:
                self._completed = s >= OUT_DONE
                self._phase, self._phase_t0, self._stall_since = "back", t_arm, None
        elif self._phase == "back":
            t_in = t_arm - self._phase_t0
            # back at the start: inside HOLD_START_M, or inside NEAR_START_M and no longer moving
            # (friction can stop the handle up to 2.5 cm short of where the spring pulls it)
            stopped = abs(float(state.vel[self.reach_axis])) < STALL_SPEED
            if at_hold_start or (near_start and stopped) or t_in >= BACK_TIMEOUT_S:
                self._finish_rep(dial, aborted=False)
                self._phase = "idle"
                self._near_since = None

        # stall rescue
        if self._phase in ("out", "back") and dial != 0 and not self._rescued:
            v_along = float(state.vel[self.reach_axis]) * self.reach_sign
            prog = s if self._phase == "out" else 1.0 - s
            if abs(v_along) < STALL_SPEED and prog < STALL_MAX_PROGRESS:
                if self._stall_since is None:
                    self._stall_since = t_arm
                limit = STALL_ASSIST_S if dial > 0 else STALL_RESIST_S
                if t_arm - self._stall_since >= limit:
                    self._rescued = True
                    self._rescued_at = t_arm
            else:
                self._stall_since = None

        # command
        if self._phase in ("out", "back"):
            self._latch = None
            d_cmd, rescued_cmd = self._rescue_dial(dial, t_arm)
            target, k = controller.command(d_cmd, self._phase, s, t_arm - self._phase_t0,
                                           pos, self.path, rescued_cmd)
            if self._phase == "out" and t_arm - self._phase_t0 < ARM_HANDOVER_S:
                # hand-over from the firm hold: the hand was pressing up to 25 N against k_max and
                # the new stiffness takes up to 0.2 s to act. Target on the hand meanwhile, so a
                # hand that relaxes on "go" is not snapped back (0.46 m/s and a trip in the sim).
                # (along the reach only: the walls keep carrying the limb's weight)
                tg = np.array(target, dtype=float)
                tg[self.reach_axis] = pos[self.reach_axis]
                target = _tup3(tg)
        else:
            if idle_cmd is None:                 # the rep ended on this tick
                idle_cmd = self._idle_hold(t_arm, pos, occupied, dt_tick, False)[:2]
            target, k = idle_cmd

        self._send(target, k)
        self._emit(t, state, target, dial, label_phase,
                   label_idx if label_phase != "idle" else -1, force)

    def _idle_hold(self, t_arm, pos, occupied, dt_tick, can_arm):
        """Idle command and arming for line reps and tries (15 Nov). Returns (target, k, armed).

        ``_latch`` is the idle target. Within ARM_DIST_M of the start (3D), or with the handle
        empty, it walks to the start at TEST_RETURN_SPEED in the soft hold; once it is there and
        the handle is within NEAR_START_M the hold goes firm (k_max on all axes, target fixed at
        the start). A hand on the handle further away is held softly where it is; the target
        follows the hand only towards the start (no free sliding away along the line).
        In the firm hold, a baseline-relative force (smoothed, any direction) above HAND_ON_N
        and at most ARM_MAX_N with the handle slower than ARM_MAX_SPEED arms the rep after
        ARM_HOLD_S. An empty handle stands still there and reads its pose error only.
        ``go()``: GO_COUNTDOWN_S later the rep is armed if the force is above GO_MIN_N."""
        start = np.asarray(self.path.start, dtype=float)
        dist = float(np.linalg.norm(pos - start))
        f = float(np.linalg.norm(self._f_filt))
        speed = float(np.linalg.norm(self._vel))
        near = dist <= ARM_DIST_M
        if self._latch is None:
            self._latch = self._beside_hand(pos)
            self._firm = False
        if self._firm and dist > FIRM_EXIT_M:
            self._firm = False
            self._latch = self._beside_hand(pos)
        # let go of a loaded idle hold (a hand pressing 18 N against it and then gone threw the
        # handle back at 0.4 m/s in the sim): the hold pulls with more than IDLE_SPRING_N and
        # this tick's reading shows under half of that. Target onto the hand at once; the walk
        # back at 2 cm/s follows as for any empty handle.
        if self._cmd is not None:
            pull = self._cmd[1] * (self._cmd[0] - pos)
            spring = float(np.linalg.norm(pull))
            seen = 0.0
            if spring > IDLE_SPRING_N:
                # the part of the reading that opposes the hold's pull. A moving handle's own
                # reading can cancel up to EMPTY_MOVING_N of it along the motion (a limp arm
                # sagging on the hold was taken for a let-go on every tick and never armed).
                u = pull / spring
                seen = -float(self._f_now @ u)
                if speed >= V_MOVING:
                    seen += EMPTY_MOVING_N * abs(float(self._vel @ u)) / speed
            # (friction can carry up to IDLE_FRICTION_N of the pull for the hand: a strong patient
            # whose limb reads 5.7 N on a hold pulling 8 N lost the firm hold every 1.5 s)
            if spring > IDLE_SPRING_N and seen + IDLE_FRICTION_N < 0.5 * spring:
                self._firm = False
                self._latch = np.asarray(pos, dtype=float).copy()
                self._arm_acc = 0.0
        ok = False
        if self._firm:
            ok = near and HAND_ON_N < f <= ARM_MAX_N and speed < ARM_MAX_SPEED
            reason = (None if ok else "press gently" if f <= HAND_ON_N
                      else "pushing too hard" if f > ARM_MAX_N
                      else "return to start" if not near else "hold still")
            target = _tup3(start)
            # k_hold -> k_max over FIRM_RAMP_S in FIRM_STEP_S steps (a one-step change snapped a handle
            # that friction had stopped 1.5 cm short at 0.11 m/s)
            kh, km = float(self.arm.limits.k_hold), float(self.arm.limits.k_max)
            el = min(FIRM_RAMP_S, t_arm - self._firm_t0)
            kf = kh + (km - kh) * (int(el / FIRM_STEP_S + 1e-9) * FIRM_STEP_S / FIRM_RAMP_S)
            k = (kf, kf, kf)
        else:
            if occupied and dist > FIRM_EXIT_M:
                cand = self._beside_hand(pos)
                if np.linalg.norm(cand - start) < np.linalg.norm(self._latch - start):
                    self._latch = cand
                reason = "return to start"
            else:
                d = start - self._latch
                left = float(np.linalg.norm(d))
                step_m = TEST_RETURN_SPEED * dt_tick
                if left <= step_m:
                    self._latch = start.copy()
                    # (within 3 cm until this fix: a 10 N hand sat 3.4 cm out and an 18 N hand 5.7 cm
                    # out in the 300 N/m hold for good, since it saturates at 15 N; nothing armed)
                    if dist <= FIRM_EXIT_M:
                        self._firm = True
                        # already on the start (5 mm): firm at once; else ramp (no snap). armtest always ramps:
                        # armed at once, a strong sim patient's first try was cut short as a let-go
                        self._firm_t0 = t_arm - (FIRM_RAMP_S if dist <= 0.005 and self.preset.kind != "test" else 0.0)
                else:
                    self._latch = self._latch + d / left * step_m
                reason = ("too far from start" if not near else
                          "return to start" if dist > NEAR_START_M else "hold still")
            target = _tup3(self._latch)
            kh = float(self.arm.limits.k_hold)
            k = (kh, kh, kh)
        armed = False
        with self._lock:
            go_req, self._go_req = self._go_req, False
        if go_req and can_arm:
            self._go_at = t_arm + GO_COUNTDOWN_S
        if not can_arm:
            self._arm_acc, self._go_at = 0.0, None
            self._arming = {"progress": 0.0, "reason": None}
            return target, k, False
        self._arm_acc = min(ARM_HOLD_S, self._arm_acc + dt_tick) if ok else max(0.0, self._arm_acc - dt_tick)
        progress = self._arm_acc / ARM_HOLD_S
        if self._arm_acc >= ARM_HOLD_S - 1e-9:
            armed = True
        elif self._go_at is not None:
            progress = max(progress, 1.0 - (self._go_at - t_arm) / GO_COUNTDOWN_S)
            if t_arm >= self._go_at:
                self._go_at = None
                if near and GO_MIN_N < f <= ARM_MAX_N:
                    armed = True
                else:
                    reason = "press gently" if near and f <= GO_MIN_N else (reason or "return to start")
        if armed:
            self._arm_acc, self._go_at, self._firm = 0.0, None, False
            progress, reason = 1.0, None
        self._arming = {"progress": float(np.clip(progress, 0.0, 1.0)), "reason": reason}
        return target, k, armed

    def _send(self, target, k) -> None:
        """Target every tick (feeds the watchdog); stiffness only when it changes."""
        self.arm.set_target(target)
        if k != self._k_sent:
            self.arm.set_stiffness(*k)
            self._k_sent = k
        self._cmd = (np.asarray(target, dtype=float), np.asarray(k, dtype=float))

    # ------------------------------------------------------------------ release (hands off a loaded spring)

    def _let_go(self, force, pos, occupied) -> bool:
        """True when the handle has been let go while the arm's spring is pulling on it.

        Either the handle is unoccupied (the usual 0.5 s rule), or, at once, no hand force is
        read on this tick (``_hand_on`` with the same threshold as occupancy and the motion
        allowance along the reach only) while the commanded spring
        pull along the reach axis is above RELEASE_SPRING_N (nothing is holding a loaded spring). The second test is
        what keeps the empty handle slow: waiting 0.5 s would let the spring throw it first.
        A person who is still holding on, even one moving with the band, is not "let go"."""
        if not occupied:
            return True
        if self._phase == "out" and self._last_tick_t is not None and self._last_tick_t - self._phase_t0 < ARM_GRACE_S:
            # just armed: the hand is changing from pressing to pushing and its force passes
            # through small values (a rep was ended 30 ms after it was armed). The 0.5 s
            # occupancy rule above still applies.
            return False
        spring = float(self._spring_force(pos)[self.reach_axis])
        return abs(spring) > RELEASE_SPRING_N and not self._hand_on(force, self._vel, along_reach_only=True)

    def _hand_force(self, force, vel, along_reach_only: bool = False) -> float:
        """Force (N) that can only come from a hand: the baseline-relative reading with the
        motion allowance taken off (an empty moving handle reads up to EMPTY_MOVING_N by itself).

        Default (occupancy): up to EMPTY_MOVING_N, either sign, is removed along the direction
        the handle is moving in, whatever that direction is, at any speed above V_MOVING. A
        freed handle that springs up when a limb's weight comes off is covered too.
        ``along_reach_only`` (the one-tick let-go test): the allowance is removed from the
        reach-axis component only, and only while the handle moves along the reach. That test
        must not mistake a limb's weight on a handle that is settling up or down for no hand."""
        f = np.array(force, dtype=float)
        if along_reach_only:
            a = self.reach_axis
            if abs(float(vel[a])) >= V_MOVING:
                f[a] -= float(np.clip(f[a], -EMPTY_MOVING_N, EMPTY_MOVING_N))
        else:
            speed = float(np.linalg.norm(vel))
            if speed >= V_MOVING:
                u = np.asarray(vel, dtype=float) / speed
                f = f - float(np.clip(f @ u, -EMPTY_MOVING_N, EMPTY_MOVING_N)) * u
        return float(np.linalg.norm(f))

    def _hand_on(self, force, vel, along_reach_only: bool = False) -> bool:
        """True if this reading shows a hand on the handle (see the module docstring)."""
        return self._hand_force(force, vel, along_reach_only) > HAND_ON_N

    def _begin_release(self, t_arm: float, pos) -> None:
        kh = float(self.arm.limits.k_hold)
        self._rel_k = np.array(self._cmd[1] if self._cmd is not None else (kh, kh, kh), dtype=float)
        self._rel_t0 = t_arm
        self._rel_walk = False
        self._latch = np.asarray(pos, dtype=float).copy()   # target on the hand: no spring force at all
        self._near_since = None
        self._phase = "release"

    def _tick_release(self, state, t_arm, t, pos, force, occupied, dial, dt_tick) -> None:
        """After a let-go on the resist side or in the strength test. The target sits where the
        hand was let go while the reach-axis stiffness ramps to zero over RESIST_RAMP_S in
        RESIST_RAMP_STEP_S steps; then, in the soft hold, the target walks back to the path
        start at TEST_RETURN_SPEED. A hand back on the handle ends the walk. Samples: "idle"."""
        elapsed = t_arm - self._rel_t0
        if not self._rel_walk and elapsed >= RESIST_RAMP_S:
            self._rel_walk = True
            self._latch = pos.copy()
        if not self._rel_walk:
            step = int(elapsed / RESIST_RAMP_STEP_S + 1e-9) * RESIST_RAMP_STEP_S
            kk = self._rel_k.copy()
            kk[self.reach_axis] *= (1.0 - step / RESIST_RAMP_S)
            k = _tup3(kk)
            target = _tup3(self._latch)
        else:
            kh = float(self.arm.limits.k_hold)
            k = (kh, kh, kh)
            if occupied:                                    # taken again: ordinary idle from here
                self._phase = "idle"
                self._latch = None
                target = _tup3(pos)
            else:
                goal = np.asarray(self.path.start, dtype=float)
                d = goal - self._latch
                dist = float(np.linalg.norm(d))
                step_m = TEST_RETURN_SPEED * dt_tick
                if dist <= step_m:
                    self._latch = goal
                    self._phase = "idle"
                else:
                    self._latch = self._latch + d / dist * step_m
                target = _tup3(self._latch)
        self._send(target, k)
        self._emit(t, state, target, dial, "idle", -1, force)

    def _limit_reached(self) -> bool:
        return self._reps_limit is not None and self.rep_count >= self._reps_limit

    def _sim_cue(self, intent: str) -> None:
        """Tell a simulated patient what to do ("out" = push/reach now, "rest"). No-op on the real arm."""
        if self._explicit_cues:
            self.arm.cue(intent)

    def _abort_rep(self, dial_now: float) -> None:
        """Close whatever rep, try or circle is in progress as not completed."""
        kind = self.preset.kind
        if kind == "test":
            self._finish_try(aborted=True)
        elif kind == "guided":
            self._finish_circle(completed=False)
        else:
            self._finish_rep(dial_now, aborted=True)

    def _record(self, rep: RepResult, adapt: bool = False) -> None:
        with self._lock:
            self.rep_count += 1
            self.reps.append(rep)
            if adapt and self._auto:
                self._dial = next_dial(self._dial, rep, auto_floor=AUTO_FLOOR)
        if self.on_rep is not None:
            self.on_rep(rep)

    # ------------------------------------------------------------------ armtest (isometric)

    def _tick_test(self, state, t_arm, t, pos, force, occupied, s, near_start, dial, dt_tick) -> None:
        """Isometric strength test. During a push the target is the start pose. From the first
        try to the last the reach axis is at the arm's k_max and the other axes at K_WALL;
        before and after, the arm is in the ordinary soft hold. "out" = push now, "back" = rest.

        When a push ends the target is put on the hand and walked back to the start at
        TEST_RETURN_SPEED, so the stretched spring does not snap the handle back when the
        person relaxes (in the sim that reached 0.46 m/s and tripped the speed limit)."""
        p = self.preset
        idle_cmd = None
        if self._phase == "idle":
            # the first try waits for a hand pressing on the handle at the start, like any rep
            tgt_i, k_i, armed = self._idle_hold(t_arm, pos, occupied, dt_tick, not self._limit_reached())
            idle_cmd = (tgt_i, k_i)
            if armed:
                self._begin_try(t_arm, t, dial)
                self._last_force_t = t_arm
                occupied = True

        label_phase, label_idx = self._phase, self._rep_idx
        if self._phase == "out":
            if not self._out_t or t > self._out_t[-1]:
                self._out_t.append(t)
                self._out_pos.append(_tup3(pos))
                self._out_force.append(_tup3(force))
            if self._let_go(force, pos, occupied):          # let go mid-push: release the spring gently
                self._finish_try(aborted=False)
                self._begin_release(t_arm, pos)
                self._tick_release(state, t_arm, t, pos, force, occupied, dial, dt_tick)
                return
            pushed_too_far = abs(s) * self.reach_m > p.max_disp_m
            if t_arm - self._phase_t0 >= p.push_s or pushed_too_far:
                self._test_offset = float(np.clip(s * self.reach_m, -p.max_disp_m, p.max_disp_m))
                self._finish_try(aborted=False)
                # rest, also after the last try: the stretched spring is always walked back
                self._phase, self._phase_t0 = "back", t_arm
        elif self._phase == "back":
            if self._limit_reached():
                if self._test_offset == 0.0:        # last try done and the target is back at the start
                    self._phase = "idle"
                    self._near_since = None
            elif t_arm - self._phase_t0 >= p.rest_s:
                self._begin_try(t_arm, t, dial)

        if self._phase in ("out", "back"):
            k = [float(controller.K_WALL)] * 3
            k[self.reach_axis] = float(self.arm.limits.k_max)
            k = (k[0], k[1], k[2])
        else:
            if idle_cmd is None:
                idle_cmd = self._idle_hold(t_arm, pos, occupied, dt_tick, False)[:2]
            k = idle_cmd[1]
        if label_phase == "out":                # a push tick (the last one included): start pose
            if self._phase == "out":
                self._test_offset = 0.0
            self._latch = None
            start = _tup3(self.path.point_at(0.0))
        elif self._phase == "back":             # rest: walk the target back to the start pose
            step = TEST_RETURN_SPEED * dt_tick
            self._test_offset -= float(np.clip(self._test_offset, -step, step))
            self._latch = None
            start = _tup3(np.asarray(self.path.start) + self._test_offset * self.path.axis())
        else:                                   # idle: the shared idle hold (_idle_hold)
            if idle_cmd is None:
                idle_cmd = self._idle_hold(t_arm, pos, occupied, dt_tick, False)[:2]
            start = idle_cmd[0]
        self._send(start, k)
        self._emit(t, state, start, dial, label_phase,
                   label_idx if label_phase == "out" else -1, force)

    def _begin_try(self, t_arm: float, t: float, dial: float) -> None:
        self._begin_rep(t_arm, t, dial)

    def _finish_try(self, aborted: bool) -> None:
        """One RepResult per try: mode "isometric", forces along the reach axis (push direction)."""
        p = self.preset
        t = np.asarray(self._out_t)
        pos = np.asarray(self._out_pos)
        force = np.asarray(self._out_force)
        rep_dial, rep_t0, was_open = self._rep_dial, self._rep_t0, self._rep_idx >= 0
        self._clear_rep()
        self._sim_cue("rest")
        if not was_open:
            return                          # no try in progress (rest between tries): nothing to record
        if len(t) < 2:                      # ended on its first tick: still one RepResult
            self._record(self._empty_rep("isometric", rep_dial, rep_t0))
            return
        start, end = self.path.start, self.path.end
        along_f = force[:, self.reach_axis] * self.reach_sign          # N, + = pushing along the reach
        along_d = (pos - np.asarray(start))[:, self.reach_axis] * self.reach_sign
        peak = float(max(along_f.max(), 0.0))
        err_mean, err_max = path_error(pos, start, end)
        rep = RepResult(
            session_id=self.session_id, idx=self.rep_count, mode="isometric", dial=float(rep_dial),
            t_start=float(rep_t0), duration_s=float(t[-1] - t[0]),
            rom_m=float(np.abs(along_d).max()), path_err_mean_m=err_mean, path_err_max_m=err_max,
            sparc=0.0, peak_force_n=peak, mean_force_n=float(along_f.mean()), contribution=1.0,
            completed=bool(not aborted and peak > p.min_peak_n), simulated=self.simulated,
            rescued=False)
        self._record(rep)

    # ------------------------------------------------------------------ circle (guided, robot-led)

    def _circle_point(self, theta: float) -> np.ndarray:
        """Point on the circle at angle theta. theta = 0 is the start pose; the circle lies in
        the plane of the reach axis and world z, its centre one radius along the reach."""
        r = self.preset.radius_m
        c = np.asarray(self.path.start, dtype=float).copy()
        c[self.reach_axis] += self.reach_sign * r
        pt = c.copy()
        pt[self.reach_axis] -= self.reach_sign * r * np.cos(theta)
        pt[2] += r * np.sin(theta)
        return pt

    def _tick_guided(self, state, t_arm, t, pos, force, occupied, near_start, dial, dt_tick) -> None:
        """Robot-led circle. The target moves round the circle at a fixed pace with the same
        stiffness on every axis; it waits while the hand is more than MAX_LEAD behind, and an
        empty handle ends the circle and stops the target (hands-off rule)."""
        p = self.preset
        kiso = (float(p.stiffness),) * 3
        if self._phase in ("out", "back") and not occupied:
            self._finish_circle(completed=False)
            self._phase = "idle"
            self._near_since = None

        if self._phase == "idle":
            if near_start and occupied and not self._limit_reached():
                if self._near_since is None:
                    self._near_since = t_arm
                if t_arm - self._near_since >= ARM_DWELL_S:
                    self._begin_rep(t_arm, t, dial)
                    self._theta = 0.0
            else:
                self._near_since = None

        if self._phase not in ("out", "back"):
            kh = float(self.arm.limits.k_hold)
            if occupied:
                self._latch = None
                target = _tup3(self.path.point_at(0.0) if abs(self._progress(pos)) * self.reach_m <= HOLD_START_M
                               else self._beside_hand(pos))
            else:
                if self._latch is None:
                    self._latch = self._beside_hand(pos)
                target = _tup3(self._latch)
            self._send(target, (kh, kh, kh))
            self._emit(t, state, target, dial, "idle", -1, force)
            return

        self._latch = None
        if not self._out_t or t > self._out_t[-1]:
            self._out_t.append(t)
            self._out_pos.append(_tup3(pos))
            self._out_force.append(_tup3(force))
            self._out_robot.append(self._spring_force(pos))
        label_phase, label_idx = self._phase, self._rep_idx
        if float(np.linalg.norm(self._circle_point(self._theta) - pos)) <= controller.MAX_LEAD:
            self._theta += 2.0 * np.pi * dt_tick / p.period_s
        if self._theta >= 2.0 * np.pi:
            self._finish_circle(completed=True)
            if self._limit_reached():
                self._phase = "idle"
                self._near_since = None
            else:                                   # straight into the next circle
                self._begin_rep(t_arm, t, dial)
                self._theta = 0.0
        else:
            self._phase = "out" if self._theta < np.pi else "back"
        target = _tup3(self._circle_point(self._theta if self._phase != "idle" else 0.0))
        self._send(target, kiso)
        self._emit(t, state, target, dial, label_phase, label_idx, force)

    def _finish_circle(self, completed: bool) -> None:
        """One RepResult per circle: mode "guided". Path error is the distance from the circle
        (constant vertical sag removed, as for the line)."""
        t = np.asarray(self._out_t)
        pos = np.asarray(self._out_pos)
        force = np.asarray(self._out_force)
        robot = np.asarray(self._out_robot)
        rep_dial, rep_t0, was_open = self._rep_dial, self._rep_t0, self._rep_idx >= 0
        self._clear_rep()
        if not was_open:
            return
        if len(t) < 2:
            self._record(self._empty_rep("guided", rep_dial, rep_t0))
            return
        r = self.preset.radius_m
        a = self.reach_axis
        other = 1 - a if a in (0, 1) else 0          # the horizontal axis across the circle's plane
        c = self._circle_point(0.0)
        c[a] += self.reach_sign * r                   # centre
        d = pos - c
        radial = np.hypot(d[:, a], d[:, 2])
        scale = np.where(radial > 1e-9, r / np.maximum(radial, 1e-9), 0.0)
        err = np.zeros_like(d)
        err[:, a] = d[:, a] * (1.0 - scale)
        err[:, 2] = d[:, 2] * (1.0 - scale)
        err[:, other] = d[:, other]
        err[:, 2] -= err[:, 2].mean()
        dist = np.linalg.norm(err, axis=1)
        vel = np.gradient(pos, t, axis=0)
        dt = float(np.median(np.diff(t)))
        try:
            smooth = sparc(np.linalg.norm(vel, axis=1), 1.0 / dt)
        except ValueError:
            smooth = 0.0
        wp = float(np.sum(np.maximum(0.0, np.sum(force * vel, axis=1))) * dt)
        wr = float(np.sum(np.maximum(0.0, np.sum(robot * vel, axis=1))) * dt)
        peak, mean = force_stats(force)
        rep = RepResult(
            session_id=self.session_id, idx=self.rep_count, mode="guided", dial=float(rep_dial),
            t_start=float(rep_t0), duration_s=float(t[-1] - t[0]),
            rom_m=float(np.ptp(pos[:, a])), path_err_mean_m=float(dist.mean()),
            path_err_max_m=float(dist.max()), sparc=float(smooth), peak_force_n=peak,
            mean_force_n=mean, contribution=(wp / (wp + wr)) if (wp + wr) > 1e-6 else 0.0,
            completed=bool(completed), simulated=self.simulated, rescued=False)
        self._record(rep)

    def _rescue_dial(self, dial: float, t_arm: float) -> tuple[float, bool]:
        """(dial, rescued) for controller.command. Resist-side rescue ramps the dial to 0."""
        if not self._rescued or dial >= 0:
            return dial, self._rescued
        elapsed = t_arm - self._rescued_at
        if elapsed >= RESIST_RAMP_S:
            return dial, True                      # controller goes transparent
        step = int(elapsed / RESIST_RAMP_STEP_S + 1e-9) * RESIST_RAMP_STEP_S
        return dial * (1.0 - step / RESIST_RAMP_S), False

    def _spring_force(self, pos) -> tuple[float, float, float]:
        """Arm's force on the hand from the command in effect: K * (target - hand)."""
        if self._cmd is None:
            return (0.0, 0.0, 0.0)
        target, k = self._cmd
        return _tup3(k * (target - np.asarray(pos, dtype=float)))

    def _begin_rep(self, t_arm: float, t: float, dial: float) -> None:
        self._clear_rep()
        self._phase = "out"
        self._phase_t0 = t_arm
        self._near_since = None
        self._rep_idx = self.rep_count
        self._rep_dial = dial
        self._rep_t0 = t
        self._sim_cue("out")

    def _emit(self, t: float, state, target, dial: float, phase: str, rep_idx: int,
              force) -> None:
        smp = Sample(t=float(t), pos=_tup3(state.pos), vel=_tup3(state.vel),
                     force=_tup3(force), target=_tup3(target), dial=float(dial),
                     rep_idx=int(rep_idx), simulated=self.simulated, phase=phase,
                     q=tuple(float(v) for v in state.q))
        with self._lock:
            self._latest = smp
        if self.on_sample is not None:
            self.on_sample(smp)

    def _out_metrics(self) -> dict | None:
        """rep_metrics on the out slice only. None if there are under 2 samples."""
        if len(self._out_t) < 2:
            return None
        t = np.asarray(self._out_t)
        pos = np.asarray(self._out_pos)
        force = np.asarray(self._out_force)
        robot = np.asarray(self._out_robot)
        start, end = self.path.start, self.path.end
        try:
            return rep_metrics(t, pos, force, start, end, robot_force=robot)
        except ValueError:
            # SPARC is undefined when the hand did not move; everything else still holds.
            vel = np.gradient(pos, t, axis=0)
            err_mean, err_max = path_error(pos, start, end)
            peak, mean = force_stats(force)
            return {
                "duration_s": float(t[-1] - t[0]), "rom_m": rom(pos, start, end),
                "path_err_mean_m": err_mean, "path_err_max_m": err_max, "sparc": 0.0,
                "peak_force_n": peak, "mean_force_n": mean,
                "contribution": contribution(force, vel, start, end,
                                             dt=float(np.median(np.diff(t))), robot_force=robot),
            }

    def _empty_rep(self, mode: str, rep_dial: float, rep_t0: float) -> RepResult:
        """A rep, try or circle that ended before two samples were taken: not completed, all zeros."""
        return RepResult(
            session_id=self.session_id, idx=self.rep_count, mode=mode, dial=float(rep_dial),
            t_start=float(rep_t0), duration_s=0.0, rom_m=0.0, path_err_mean_m=0.0, path_err_max_m=0.0,
            sparc=0.0, peak_force_n=0.0, mean_force_n=0.0, contribution=0.0, completed=False,
            simulated=self.simulated, rescued=False)

    def _finish_rep(self, dial_now: float, aborted: bool) -> None:
        """Close the current rep: RepResult, on_rep, auto dial. Aborted reps are not completed."""
        m = self._out_metrics()
        completed = self._completed and not aborted
        rescued = self._rescued
        rep_dial = self._rep_dial
        rep_t0 = self._rep_t0
        was_open = self._rep_idx >= 0
        self._clear_rep()
        if not was_open:
            return  # no rep in progress: nothing to record (each rep is recorded exactly once)
        if m is None:
            # ended on its first tick (too short to measure): still exactly one RepResult
            self._record(self._empty_rep(mode_of(rep_dial), rep_dial, rep_t0))
            return
        rep = RepResult(
            session_id=self.session_id, idx=self.rep_count, mode=mode_of(rep_dial),
            dial=float(rep_dial), t_start=float(rep_t0), completed=bool(completed),
            simulated=self.simulated, rescued=bool(rescued), **m)
        with self._lock:
            self.rep_count += 1
            self.reps.append(rep)
            if self._auto:
                self._dial = next_dial(self._dial, rep, auto_floor=AUTO_FLOOR)
        if self.on_rep is not None:
            self.on_rep(rep)
