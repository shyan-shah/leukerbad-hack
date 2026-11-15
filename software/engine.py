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
- ``idle``: soft hold at ``K_HOLD`` on all axes. Target: the path start while the hand is at
  the start, else the hand projected onto the path line (so the limb weight does not drag the
  target down and the person can bring the handle back). A rep
  is armed when the hand has been within ``NEAR_START_M`` of the start, measured along the
  reach axis, for ``ARM_DWELL_S`` and the handle is occupied.
- ``out``: reference clock starts when the rep is armed. Ends at progress ``OUT_DONE``
  (completed) or after ``OUT_TIMEOUT_S`` (not completed), then ``back``.
- ``back``: same law toward the start. Ends within ``NEAR_START_M`` of the start, or after
  ``BACK_TIMEOUT_S`` (team choice, so a hand that never returns cannot hang the session).
- Occupied: the baseline-relative force magnitude was above ``F_PRESENT`` within the last
  ``OCCUPIED_WINDOW_S``, counting only ticks where both the raw value and the value smoothed
  over ``FORCE_FILTER_S`` are above it. A noise spike alone (raw only) does not count, and
  letting go is seen as soon as the raw value drops (no added filter delay).

Force baseline (the real arm's sensor reads several N with nothing touching it, see
context/BRINGUP_FINDINGS.md and DECISIONS.md): ``start()`` averages ``BASELINE_N`` force
readings BEFORE compliance starts, with the handle empty (the same "nobody touching" rule
as ``zero_force``), and refuses to start with a RuntimeError if that baseline is over
``MAX_BASELINE_N`` (sensor not zeroed, or something resting on the handle). Every force
the engine uses (occupancy, Samples, metrics) is ``state.force - baseline``. While the
phase is idle and the handle is not occupied the baseline follows the raw reading with
time constant ``BASELINE_TRACK_S``, so slow drift does not build up while the handle is
empty. Drift while the handle is held is not tracked (re-zero between sets on the real arm).
For ``SimArm`` the simulated patient keeps hands off while the baseline is taken.
- Hands-off rule, assist side only (dial > 0): if the handle is not occupied during a rep the
  rep ends now as not completed and the phase goes to idle. While the handle is empty the
  target is latched at the point where the hand was when it became empty (``K_HOLD``), so an
  empty handle is never driven along the path.
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
runs the line backwards from the far end: a "setup" phase (transparent, walls on) lasts until
the person has brought the handle to the far end; the arm never drives it there. "armtest"
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
from software.adapt import AUTO_FLOOR, mode_of, next_dial
from software.metrics import contribution, force_stats, path_error, rep_metrics, rom, sparc
from software.paths import LinePath

__all__ = ["Engine", "DT"]

DT = 0.01                    # s, 100 Hz
NEAR_START_M = 0.02          # m along the reach axis: "at the start"
ARM_DWELL_S = 1.0            # s at the start (and occupied) before a rep is armed
OUT_DONE = 0.9               # progress that completes the out phase
OUT_TIMEOUT_S = 10.0         # s, out phase gives up (not completed)
BACK_TIMEOUT_S = 10.0        # s, back phase gives up and the rep ends anyway (team choice)
F_PRESENT = 1.5              # N, handle force magnitude (relative to the baseline) meaning "a hand is on it"
OCCUPIED_WINDOW_S = 0.5      # s, occupied if force exceeded F_PRESENT within this window
FORCE_FILTER_S = 0.05        # s, smoothing time constant of the force used for occupancy (noise)
BASELINE_N = 30              # force readings averaged for the empty-handle baseline at start()
MAX_BASELINE_N = 3.0         # N, a larger empty-handle baseline refuses to start (not zeroed)
BASELINE_TRACK_S = 20.0      # s, time constant of baseline tracking while idle and empty (drift)
STALL_SPEED = 0.01           # m/s along the path
STALL_ASSIST_S = 1.5         # s stall on the assist side before rescue
STALL_RESIST_S = 3.0         # s stall on the resist side before dropping to transparent
STALL_MAX_PROGRESS = 0.9     # stall rescue only before this phase progress
RESIST_RAMP_S = 1.0          # s, resist-side rescue ramps the resistance to 0 over this
RESIST_RAMP_STEP_S = 0.1     # s between ramp steps (10 steps over RESIST_RAMP_S)
TEST_RETURN_SPEED = 0.02     # m/s, armtest: after a push the target walks back to the start at this speed
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
                 exercise: str = "reach", reps: int | None = None) -> None:
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
        self._last_tick_t: float | None = None
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
                f"{MAX_BASELINE_N:.1f} N). The sensor is not zeroed or something is resting on the "
                "handle. With nobody touching the arm, run arm.zero_force() (robot/RUNBOOK.md), "
                "then start the session again.")
        self.force_baseline = baseline
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
        if self.preset.start_at == "far" and abs(self._progress(self.arm.get_state().pos)) * self.reach_m > NEAR_START_M:
            self._phase = "setup"                   # the person moves the handle to the far end
        if hasattr(self.arm, "patient") and hasattr(self.arm, "cue"):
            # Simulated patient: where its reach starts, and whether the engine cues it itself
            # (pull and armtest) or it follows the stiffness change as before (reach, push).
            self._explicit_cues = self.preset.start_at == "far" or self.preset.kind == "test"
            self.arm.reach_origin = _tup3(start)
            self.arm.auto_cue = not self._explicit_cues
            self._sim_cue("back" if self._phase == "setup" else "rest")
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
            self.arm.hold()
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
            if auto is not None:
                self._auto = bool(auto)

    def snapshot(self) -> dict:
        """Latest Sample as a dict plus rep_count, auto and arm_mode. Thread-safe."""
        with self._lock:
            d = self._latest.to_dict() if self._latest is not None else {}
            return d | {"rep_count": self.rep_count, "auto": self._auto,
                        "arm_mode": self._arm_mode, "exercise": self.exercise,
                        "kind": self.preset.kind, "reps_target": self.reps_target,
                        "done": self.done}

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
        """Current rep phase: "idle", "out" or "back"."""
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
        state = self.arm.get_state()
        t_arm = float(state.t)
        if self._t0 is None:
            self._t0 = t_arm
        t = t_arm - self._t0
        pos = np.asarray(state.pos, dtype=float)
        raw_force = np.asarray(state.force, dtype=float)
        force = raw_force - self.force_baseline
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
            self._phase = "idle"
            self._near_since = None
            self._latch = None
            self._k_sent = None  # re-send stiffness if compliance is restarted
            self._cmd = None
            self._emit(t, state, _tup3(pos), dial, "idle", -1, force)
            return

        # occupied? (baseline-relative force; raw AND smoothed above F_PRESENT)
        if (float(np.linalg.norm(force)) > F_PRESENT
                and float(np.linalg.norm(self._f_filt)) > F_PRESENT):
            self._last_force_t = t_arm
        occupied = (self._last_force_t is not None
                    and t_arm - self._last_force_t <= OCCUPIED_WINDOW_S)
        # follow slow sensor drift while the handle is empty and nothing is happening
        if self._phase in ("idle", "setup") and not occupied:
            self.force_baseline = (self.force_baseline
                                   + (raw_force - self.force_baseline) * (dt_tick / BASELINE_TRACK_S))

        s = self._progress(pos)
        near_start = abs(s) * self.reach_m <= NEAR_START_M

        if self.preset.kind == "test":
            self._tick_test(state, t_arm, t, pos, force, occupied, s, near_start, dial, dt_tick)
            return
        if self.preset.kind == "guided":
            self._tick_guided(state, t_arm, t, pos, force, occupied, near_start, dial, dt_tick)
            return

        # setup ("far" presets such as pull): transparent along the line, walls on, until the
        # person has brought the handle to the far end. The arm never drives it there.
        if self._phase == "setup":
            if near_start:
                if self._near_since is None:
                    self._near_since = t_arm
                if t_arm - self._near_since >= SETUP_DWELL_S:
                    self._phase = "idle"
                    self._near_since = None
            else:
                self._near_since = None
            if self._phase == "setup":
                target, k = controller.command(0.0, "out", s, 0.0, pos, self.path, False)
                self._send(target, k)
                self._emit(t, state, target, 0.0, "setup", -1, force)
                return

        # hands-off rule (assist side only)
        if self._phase in ("out", "back") and dial > 0 and not occupied:
            self._finish_rep(dial, aborted=True)
            self._phase = "idle"
            self._near_since = None

        # idle -> out
        if self._phase == "idle":
            if near_start and occupied and not self._limit_reached():
                if self._near_since is None:
                    self._near_since = t_arm
                if t_arm - self._near_since >= ARM_DWELL_S:
                    self._begin_rep(t_arm, t, dial)
            else:
                self._near_since = None

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
            if near_start or t_in >= BACK_TIMEOUT_S:
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
        else:
            kh = float(self.arm.limits.k_hold)
            k = (kh, kh, kh)
            if occupied:
                self._latch = None
                # at the start: hold the start point; elsewhere: follow the hand along the line
                target = _tup3(self.path.point_at(0.0) if near_start else self._on_line(pos))
            else:
                if self._latch is None:
                    self._latch = self._on_line(pos)
                target = _tup3(self._latch)

        self._send(target, k)
        self._emit(t, state, target, dial, label_phase,
                   label_idx if label_phase != "idle" else -1, force)

    def _send(self, target, k) -> None:
        """Target every tick (feeds the watchdog); stiffness only when it changes."""
        self.arm.set_target(target)
        if k != self._k_sent:
            self.arm.set_stiffness(*k)
            self._k_sent = k
        self._cmd = (np.asarray(target, dtype=float), np.asarray(k, dtype=float))

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
        if self._phase == "idle" and not self._limit_reached():
            # the first try waits for a hand on the handle at the start, like any rep
            if near_start and occupied:
                if self._near_since is None:
                    self._near_since = t_arm
                if t_arm - self._near_since >= ARM_DWELL_S:
                    self._begin_try(t_arm, t, dial)
            else:
                self._near_since = None

        label_phase, label_idx = self._phase, self._rep_idx
        if self._phase == "out":
            if not self._out_t or t > self._out_t[-1]:
                self._out_t.append(t)
                self._out_pos.append(_tup3(pos))
                self._out_force.append(_tup3(force))
            pushed_too_far = abs(s) * self.reach_m > p.max_disp_m
            if t_arm - self._phase_t0 >= p.push_s or pushed_too_far:
                self._test_offset = float(np.clip(s * self.reach_m, -p.max_disp_m, p.max_disp_m))
                self._finish_try(aborted=False)
                if self._limit_reached():
                    self._phase = "idle"
                else:
                    self._phase, self._phase_t0 = "back", t_arm
        elif self._phase == "back":
            if t_arm - self._phase_t0 >= p.rest_s:
                self._begin_try(t_arm, t, dial)

        if self._phase in ("out", "back"):
            k = [float(controller.K_WALL)] * 3
            k[self.reach_axis] = float(self.arm.limits.k_max)
            k = (k[0], k[1], k[2])
        else:
            kh = float(self.arm.limits.k_hold)
            k = (kh, kh, kh)
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
        elif occupied:                          # idle, same rule as the line: never pull the hand
            self._latch = None
            start = _tup3(self.path.point_at(0.0) if near_start else self._beside_hand(pos))
        else:                                   # idle and empty: the target stays where it is
            if self._latch is None:
                self._latch = self._beside_hand(pos)
            start = _tup3(self._latch)
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
        rep_dial, rep_t0 = self._rep_dial, self._rep_t0
        self._clear_rep()
        self._sim_cue("rest")
        if len(t) < 2:
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
                target = _tup3(self.path.point_at(0.0) if near_start else self._beside_hand(pos))
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
        rep_dial, rep_t0 = self._rep_dial, self._rep_t0
        self._clear_rep()
        if len(t) < 2:
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

    def _finish_rep(self, dial_now: float, aborted: bool) -> None:
        """Close the current rep: RepResult, on_rep, auto dial. Aborted reps are not completed."""
        m = self._out_metrics()
        completed = self._completed and not aborted
        rescued = self._rescued
        rep_dial = self._rep_dial
        rep_t0 = self._rep_t0
        self._clear_rep()
        if m is None:
            return  # too short to measure (aborted right at the start): no rep recorded
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
