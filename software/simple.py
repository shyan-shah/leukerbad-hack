"""BandEngine: Push against a constant, smooth resistance at one of four fixed levels (pitch demo).

A small engine beside software/engine.py (which is untouched). Same interface as ``Engine`` for the
server: ``start()``, ``stop() -> SessionSummary``, ``snapshot()``, ``on_sample``, ``on_rep``;
``set_dial``, ``go`` and ``resume`` do nothing. Extra: ``set_level(n)``.

Smooth by design
- The stiffness is commanded ONCE per session (again only when the level changes, ramped over
  0.5 s). There is no arming, no hand detection and no phase that changes the stiffness.
  Only the target moves.
- Band law: the target is the point on the reach line ``LEAD_M`` (5 cm) behind the hand towards
  the start, never beyond the start. Further out than 5 cm the band therefore pulls back with a
  constant force K x 5 cm = the level force; within 5 cm of the start it is a plain spring to the
  start. The hand position that the target follows is low-passed at about 10 Hz.
- Reach-axis stiffness K = level force / 0.05 m, 500 N/m walls on the other two axes:
  level 1 = 10 N (200 N/m), 2 = 15 N (300), 3 = 20 N (400), 4 = 28 N (560).
- Default arm limits only. ``set_test_limits`` is never called.

A released handle
A band stretched 5 cm holds enough energy to throw an empty handle back faster than the arm's
0.40 m/s speed trip. There is no hand detection by force, so the law itself is gentle on the
way back: the band's anchor follows the hand outward at once but moves back towards the start
at ``V_RETURN`` (0.05 m/s) at most, and a handle that speeds up towards the start past
``V_SNAP`` (0.10 m/s) gets the anchor put onto it at once. An empty handle is then led back at
one steady 0.05 m/s. A hand that returns slower than that feels the full level force both
ways; one that returns faster feels less on the way back.

Reps come from the handle position only: "out" once it has passed 0.20 m, counted when it is
back within 0.05 m of the start. One RepResult per counted rep (mode "resist", completed True).
A push that does not reach 0.20 m is not counted and emits nothing.

End of travel: the reach is 0.30 m and the arm's workspace box trips 0.37 m out. From 0.27 m
the state says "Turn back" (the rep already counts as out). Past 0.31 m ``over_travel`` is set;
the band stays on and nothing follows the hand outward.

Optional, for the real arm (the server asks for both):
- ``prepare=True``: a 3 s "hands off" countdown in the state, then ``arm.zero_force()``, then
  the band. If the handle is more than 2 cm from the start pose the arm first moves there
  (``arm.home()``, slow). The countdown restarts while the handle is moving.
- ``return_home=True``: at ``stop()`` a 3 s "returning to start, hands off" countdown, then
  ``arm.home()``. Skipped, with a message, if the handle is held (force or motion) or the arm
  has a fault. ``stop()`` always returns the summary, also when the move is interrupted.

After a trip (arm no longer compliant) the engine stops commanding and says so in ``message``.
It never re-arms by itself: stop the session and start again.

All numbers are team-chosen, not clinical prescriptions. With a SimArm the data is simulated.
"""
from __future__ import annotations

import datetime as _dt
import math
import re
import threading
import time

import numpy as np

from server.contract import RepResult, Sample, SessionSummary

__all__ = ["BandEngine", "LEVELS", "BAND_IDS", "level_of", "is_band"]

DT = 0.01                    # s, 100 Hz
LEVELS = {1: 10.0, 2: 15.0, 3: 20.0, 4: 28.0}     # level -> band force, N
BAND_IDS = tuple(f"push_{n}" for n in LEVELS)
LEAD_M = 0.05                # m, the band's stretch (= the arm's max lead)
K_WALL = 500.0               # N/m on the two axes across the reach
REACH_M = 0.30               # m, nominal travel
OUT_M = 0.20                 # m: a rep is "out" once the handle has passed this
BACK_M = 0.05                # m: ... and is counted when it is back within this of the start
TURN_BACK_M = 0.27           # m: "Turn back" from here
OVER_M = 0.31                # m: over_travel flag from here (the box trips at 0.37)
TARGET_FILTER_HZ = 10.0      # low-pass on the hand position the target follows
V_RETURN = 0.05              # m/s: the band's anchor moves back towards the start no faster than this
V_SNAP = 0.10                # m/s towards the start: faster than this is a let-go, the anchor goes onto the handle
LEVEL_RAMP_S = 0.5           # s, stiffness ramp on a level change
RAMP_STEPS = 5               # ... in this many equal steps
COUNTDOWN_S = 3.0            # s, "hands off" countdowns
NEAR_START_M = 0.02          # m from the start pose: zero here, otherwise move there first
GATE_SPEED = 0.02            # m/s: the handle counts as held or moving above this
GATE_FORCE_N = 6.0           # N (baseline-relative): the handle counts as held above this
RETURN_WAIT_S = 10.0         # s the return to the start waits for the handle to be let go before giving up
GATE_TICKS = 10              # readings in a row (0.1 s) over a gate before the handle counts as held
HOME_ABORT_N = 10.0          # N: a reading that changes by more than this during a move to the start holds the arm
BASELINE_N = 30              # readings averaged for the empty-handle baseline
MAX_BASELINE_N = 6.0         # N: a larger empty reading right after zeroing means a hand is on it
FORCE_CAP_N = 30.0           # readings stop at about this (the robot's contact limit)
SIM_REST_S = 1.5             # s a simulated patient rests at the start before its next push


def level_of(exercise: str) -> int | None:
    """Level of a band exercise id ("push_3" -> 3), else None."""
    m = re.fullmatch(r"push_(\d)", str(exercise))
    n = int(m.group(1)) if m else None
    return n if n in LEVELS else None


def is_band(exercise: str) -> bool:
    return level_of(exercise) is not None


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _rotation(quat) -> np.ndarray:
    """Rotation matrix (columns = the tool's axes in the base frame) of a quaternion (qw, qx, qy, qz)."""
    w, x, y, z = (float(v) for v in quat)
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _tup3(a) -> tuple[float, float, float]:
    return (float(a[0]), float(a[1]), float(a[2]))


class BandEngine:
    GROUP = "push"               # id prefix and app card. software/simple_more.py subclasses this for Row.

    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool,
                 reach_axis: int = 0, reach_sign: int = 1, reach_m: float | None = None,
                 dial: float | None = None, auto: bool | None = None,
                 on_sample=None, on_rep=None, exercise: str = "push_1", reps: int | None = None,
                 calibrate: bool | None = None, calibration_state: dict | None = None,
                 level: int | None = None, prepare: bool = False, return_home: bool = False) -> None:
        """``exercise``: "push_1" .. "push_4" (``level`` given overrides the id's level).
        ``reps``: the target shown in the state (default 10); the band stays on after it.
        ``dial``, ``auto``, ``reach_m``, ``calibrate`` and ``calibration_state`` are accepted for the
        server's sake and ignored: there is no dial, the reach is 0.30 m, nothing is calibrated."""
        if reach_axis not in (0, 1, 2):
            raise ValueError(f"reach_axis must be 0, 1 or 2, got {reach_axis}")
        lv = level if level is not None else level_of(exercise)
        if lv not in LEVELS:
            raise ValueError(f"exercise must be one of {', '.join(BAND_IDS)} (got {exercise!r}, level {level!r})")
        if reps is not None and (int(reps) != reps or reps < 1):
            raise ValueError(f"reps must be a positive integer, got {reps}")
        self.arm = arm
        self.session_id, self.patient_id = str(session_id), str(patient_id)
        self.simulated = bool(simulated)
        self.exercise = f"{self.GROUP}_{lv}"
        self.axis = int(reach_axis)
        self.sign = 1.0 if reach_sign >= 0 else -1.0
        self.reps_target = int(reps) if reps is not None else 10
        self.on_sample, self.on_rep = on_sample, on_rep
        self.prepare, self.return_home = bool(prepare), bool(return_home)

        self._lock = threading.RLock()
        self._level = int(lv)
        self._k_now = LEVELS[lv] / LEAD_M           # reach-axis stiffness being commanded
        self._ramp: tuple[float, float, float] | None = None    # (k_from, k_to, arm time it began)
        self._level_req: int | None = None
        self.stiffness_commands = 0                 # set_stiffness calls (tests: one per session)
        self._latest: Sample | None = None
        self._arm_mode: str | None = None
        self._message: str | None = None
        self._countdown: float | None = None
        self._band_force = 0.0
        self._over = False
        self.rep_count = 0
        self.reps: list[RepResult] = []
        self.started_at: str | None = None
        self.error: BaseException | None = None

        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._started = False
        self._stage = "new"          # "countdown" | "preparing" | "band" | "stopped" | "error"
        self._job: threading.Thread | None = None
        self._job_exc: BaseException | None = None
        self._count_end: float | None = None
        self._need_home = False
        self._t0: float | None = None
        self._start = np.zeros(3)
        self.force_baseline = np.zeros(3)
        self._s_filt = 0.0
        self._anchor = 0.0                   # m along the reach: where the band pulls to
        self._v_prev = 0.0
        self._last_t: float | None = None
        self._phase = "idle"
        self._rep: dict | None = None
        self._rest_since: float | None = None
        self._sim_present = True             # simulated patient only: was a hand on the handle at start()
        self._tool_R: np.ndarray | None = None      # tool axes in the base frame (real arm), see _k_vector
        self._homing = False                 # a move to the start is under way
        self._home_f0: np.ndarray | None = None     # reading when it began

    # ------------------------------------------------------------------ interface
    @property
    def level(self) -> int:
        return self._level

    @property
    def level_force_n(self) -> float:
        return LEVELS[self._level]

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def stage(self) -> str:
        return self._stage

    @property
    def done(self) -> bool:
        return self.rep_count >= self.reps_target

    def start(self) -> None:
        if self._started:
            raise RuntimeError("engine already started")
        if hasattr(self.arm, "patient") and hasattr(self.arm, "reach_m"):     # simulated patient: same line
            self.arm.reach_axis, self.arm.reach_sign, self.arm.reach_m = self.axis, int(self.sign), REACH_M
            self.arm.auto_cue = False
            self._sim_present = self.arm.patient.present
            if hasattr(self.arm, "cue"):
                self.arm.cue("rest")              # it waits for this engine's cue instead of starting by itself
            if self.prepare:
                self.arm.patient.present = False  # the simulated person follows the procedure: hands off
        self.started_at = _now_iso()
        self._started = True
        self._stop_evt.clear()
        ref0 = self._start_ref()             # for path_start and path_end until the band is on
        self._start = np.asarray(ref0 if ref0 is not None else self.arm.get_state().pos, dtype=float)
        if self.prepare and hasattr(self.arm, "zero_force"):
            st = self.arm.get_state()
            ref = self._start_ref()
            self._need_home = ref is not None and math.dist(st.pos, ref) > NEAR_START_M
            self._stage, self._count_end = "countdown", float(st.t) + COUNTDOWN_S
        else:
            self._begin_band()          # raises RuntimeError if the empty handle reads too much
        if getattr(self.arm, "realtime", True):
            self._thread = threading.Thread(target=self._loop, name="band-engine", daemon=True)
            self._thread.start()

    def stop(self) -> SessionSummary:
        """Hold the arm, optionally return it to the start. Always returns the summary."""
        self._stop_evt.set()
        th, self._thread = self._thread, None
        try:
            if th is not None and th is not threading.current_thread():
                th.join(timeout=2.0)
            job = self._job
            if job is not None and job.is_alive():       # a zero or home still running: let it finish
                job.join(timeout=20.0)
        finally:
            was_band = self._stage in ("band", "error")
            self._stage = "stopped"
            try:
                self.arm.hold()
            except Exception as e:      # the summary is still returned; the server holds again on its own
                self._say(f"The arm did not confirm the hold: {e}")
        if self.return_home and was_band and hasattr(self.arm, "home"):
            try:
                self._return_home()
            except Exception as e:      # an interrupted or refused move never loses the session
                self._say(f"Not returned to the start: {e}")
                try:
                    self.arm.hold()
                except Exception:
                    pass
        with self._lock:
            self._countdown = None
            self._phase, self._rep = "idle", None
        return SessionSummary(session_id=self.session_id, patient_id=self.patient_id,
                              started_at=self.started_at or _now_iso(), ended_at=_now_iso(),
                              exercise=self.exercise, n_reps=self.rep_count, simulated=self.simulated)

    def set_level(self, level: int) -> None:
        """Change the level now. The stiffness ramps to the new value over LEVEL_RAMP_S."""
        if level not in LEVELS:
            raise ValueError(f"level must be one of {sorted(LEVELS)}, got {level!r}")
        with self._lock:
            self._level_req = int(level)

    def set_dial(self, dial: float, auto: bool | None = None) -> None:
        """No dial on the band: accepted and ignored."""

    def go(self) -> None:
        """Nothing to cue: reps come from the handle position."""

    def resume(self) -> None:
        """Nothing to resume: after a trip stop the session and start again."""

    def snapshot(self) -> dict:
        with self._lock:
            d = self._latest.to_dict() if self._latest is not None else {}
            start = self._start
            end = start.copy()
            end[self.axis] += self.sign * REACH_M
            return d | {
                "rep_count": self.rep_count, "auto": False, "arm_mode": self._arm_mode,
                "exercise": self.exercise, "group": self.GROUP, "kind": "resist",
                "level": self._level, "level_force_n": LEVELS[self._level],
                "reps_target": self.reps_target, "done": self.done,
                "message": self._message, "countdown_s": self._countdown,
                "path_start": list(_tup3(start)), "path_end": list(_tup3(end)),
                "force_cap_n": FORCE_CAP_N, "band_force_n": round(self._band_force, 2),
                "over_travel": self._over, "arming": None, "calibration": None}

    # ------------------------------------------------------------------ test and sim drivers
    def run_for(self, seconds: float) -> None:
        """Drive a ``SimArm(realtime=False)``: per 10 ms, one ``tick()`` then ``arm.step(DT)``."""
        if getattr(self.arm, "realtime", True):
            raise RuntimeError("run_for() is only for SimArm(realtime=False)")
        for _ in range(int(round(seconds / DT))):
            self.tick()
            self.arm.step(DT)

    def run_until_reps(self, n: int, max_s: float = 600.0) -> None:
        for _ in range(int(round(max_s / DT))):
            if self.rep_count >= n:
                return
            self.run_for(DT)

    # ------------------------------------------------------------------ loop
    def _loop(self) -> None:
        next_t = time.monotonic()
        while not self._stop_evt.is_set():
            try:
                self.tick()
            except BaseException as e:      # tick already held the arm
                self.error = e
                self._say(f"The session stopped on an error: {e}")
                raise
            next_t += DT
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()

    def tick(self) -> None:
        """One control step. Any exception holds the arm first, then re-raises."""
        try:
            self._tick()
        except BaseException:
            self.arm.hold()
            raise

    # ------------------------------------------------------------------ helpers
    def _say(self, message: str | None) -> None:
        with self._lock:
            self._message = message

    def _start_ref(self):
        """The start pose to compare with before the arm has one of its own."""
        cfg = getattr(self.arm, "config", None)
        if cfg is not None and hasattr(cfg, "start_tcp_pose") and not cfg.is_placeholder("start_pose"):
            return tuple(float(v) for v in cfg.start_tcp_pose[:3])
        sp = getattr(self.arm, "start_pos", None)
        return None if sp is None else tuple(float(v) for v in sp)

    def _emit(self, st, target, phase: str, rep_idx: int, force) -> None:
        if self._t0 is None:
            self._t0 = float(st.t)
        smp = Sample(t=float(st.t) - self._t0, pos=_tup3(st.pos), vel=_tup3(st.vel), force=_tup3(force),
                     target=_tup3(target), dial=-LEVELS[self._level] / FORCE_CAP_N, rep_idx=int(rep_idx),
                     simulated=self.simulated, phase=phase, q=tuple(float(v) for v in st.q))
        with self._lock:
            self._latest = smp
            self._arm_mode = st.mode
        if self.on_sample is not None:
            self.on_sample(smp)

    def _run_job(self, fn) -> None:
        """Run a blocking arm call: in a helper thread on a real-time arm (samples keep flowing), inline otherwise."""
        self._job_exc = None

        def work():
            try:
                fn()
            except BaseException as e:
                self._job_exc = e

        if getattr(self.arm, "realtime", True):
            self._job = threading.Thread(target=work, name="band-prepare", daemon=True)
            self._job.start()
        else:
            self._job = None
            work()

    def _prepare_job(self) -> None:
        if self._need_home:
            self._home_guarded()
        self.arm.zero_force()

    def _home_guarded(self) -> None:
        """arm.home() with ``_homing`` set, so the tick that keeps running can hold the arm if something
        starts pressing on the handle (``_watch_home``)."""
        self._home_f0 = np.asarray(self.arm.get_state().force, dtype=float)
        self._homing = True
        try:
            self.arm.home()
        finally:
            self._homing = False

    def _watch_home(self, st) -> None:
        """During a move to the start (nominal stiffness): if the reading changes by more than HOME_ABORT_N,
        something is in the way. Hold at once; home() then ends with an error and nothing more is sent."""
        if self._homing and self._home_f0 is not None:
            if float(np.linalg.norm(np.asarray(st.force, dtype=float) - self._home_f0)) > HOME_ABORT_N:
                self._homing = False
                self.arm.hold()

    def _begin_band(self) -> None:
        """Empty-handle baseline, compliance on, the ONE stiffness command of the session."""
        realtime = getattr(self.arm, "realtime", True)
        patient = getattr(self.arm, "patient", None) if hasattr(self.arm, "reach_m") else None
        was_present = self._sim_present
        if patient is not None:
            patient.present = False              # the simulated person follows the procedure
        try:
            readings = []
            for i in range(BASELINE_N):
                readings.append(np.asarray(self.arm.get_state().force, dtype=float))
                if realtime and i < BASELINE_N - 1:
                    time.sleep(DT)
        finally:
            if patient is not None:
                patient.present = was_present
        baseline = np.mean(readings, axis=0)
        mag = float(np.linalg.norm(baseline))
        if mag > MAX_BASELINE_N:
            raise RuntimeError(f"the handle reads {mag:.1f} N with nobody meant to be touching it (limit "
                               f"{MAX_BASELINE_N:.0f} N). Hands off, then start again.")
        self.force_baseline = baseline
        self.arm.start_compliance()
        self._start = np.asarray(self.arm.start_pos, dtype=float)
        self._tool_R = None
        quat = getattr(self.arm, "start_quat", None)
        if quat is not None and getattr(self.arm, "stiffness_frame", "base" if hasattr(self.arm, "patient") else "tool") == "tool":
            self._tool_R = _rotation(quat)
        if hasattr(self.arm, "patient") and hasattr(self.arm, "cue"):
            self.arm.reach_origin = _tup3(self._start)
            self.arm.cue("rest")
        s0 = self.sign * float(np.asarray(self.arm.get_state().pos, dtype=float)[self.axis] - self._start[self.axis])
        self._s_filt, self._anchor, self._last_t = s0, max(0.0, s0), None      # the anchor starts on the handle
        self._phase, self._rep, self._rest_since = "idle", None, None
        self._send_k(self._k_now)
        self._stage = "band"
        self._say(None)
        with self._lock:
            self._countdown = None

    def _k_vector(self, k_reach: float) -> list[float]:
        """The three stiffness values to command for ``k_reach`` along the reach and K_WALL across it.

        Measured on the real arm (15 Nov, first hand-on Push set): the robot applies the three values along
        the TOOL's axes, not the base axes. With (200, 500, 500) commanded and the flange pointing down
        (tool y nearly along base x) the push direction had 480 to 500 N/m, so level 1 pulled 25 N. So the
        level's stiffness goes on the tool axis that lies along the reach, corrected for the small angle
        between the two (about 11 degrees), and the walls on the other two. SimArm applies them per base axis."""
        k = [K_WALL, K_WALL, K_WALL]
        if self._tool_R is None:
            k[self.axis] = float(k_reach)
            return k
        w = self._tool_R[self.axis, :] ** 2          # share of each tool axis along the reach (sums to 1)
        i = int(np.argmax(w))
        k[i] = float(np.clip((k_reach - K_WALL * (1.0 - w[i])) / w[i], 20.0, 600.0))
        return k

    def _send_k(self, k_reach: float) -> None:
        self.arm.set_stiffness(*self._k_vector(k_reach))
        self.stiffness_commands += 1

    # ------------------------------------------------------------------ the tick
    def _tick(self) -> None:
        st = self.arm.get_state()
        if self._stage == "countdown":
            return self._tick_countdown(st)
        if self._stage == "preparing":
            return self._tick_preparing(st)
        if self._stage == "band":
            return self._tick_band(st)
        self._emit(st, st.pos, "idle", -1, np.asarray(st.force, dtype=float) - self.force_baseline)

    def _tick_countdown(self, st) -> None:
        t = float(st.t)
        held = float(np.linalg.norm(st.vel)) > GATE_SPEED      # someone is moving the handle: start over
        if self._need_home and float(np.linalg.norm(st.force)) > GATE_FORCE_N:
            held = True         # the arm is about to move by itself: never with something pressing on the handle
        if held:
            self._count_end = t + COUNTDOWN_S
        left = max(0.0, self._count_end - t)
        with self._lock:
            self._countdown = round(left, 1)
            self._message = (f"Hands off: the arm moves to the start in {math.ceil(left - 0.005)}" if self._need_home
                             else f"Hands off: zeroing in {math.ceil(left - 0.005)}")
        self._emit(st, st.pos, "idle", -1, st.force)
        if left <= 0.0:
            with self._lock:
                self._countdown = None
                self._message = ("The arm is moving to the start. Hands off." if self._need_home
                                 else "Zeroing. Hands off.")
            self._stage = "preparing"
            self._run_job(self._prepare_job)

    def _tick_preparing(self, st) -> None:
        if self._job is not None and self._job.is_alive():
            self._watch_home(st)
            return self._emit(st, st.pos, "idle", -1, st.force)
        self._job = None
        err = self._job_exc
        if err is None:
            try:
                self._begin_band()
                return
            except RuntimeError as e:
                err = e
        self._stage = "error"
        self._say(f"Not started: {str(err).rstrip('.')}. Stop the session and start again.")
        self._emit(st, st.pos, "idle", -1, st.force)

    def _tick_band(self, st) -> None:
        t = float(st.t)
        dt = DT if self._last_t is None else float(np.clip(t - self._last_t, 0.0, 0.1))
        self._last_t = t
        pos = np.asarray(st.pos, dtype=float)
        force = np.asarray(st.force, dtype=float) - self.force_baseline
        a = self.axis
        if st.mode != "compliant":
            # tripped, held or faulted: never command, never re-arm. A rep in progress is dropped.
            with self._lock:
                self._phase, self._rep, self._band_force = "idle", None, 0.0
                self._message = (f"The arm has stopped ({st.fault or st.mode}). Let go. "
                                 "Stop the session and start again.")
            return self._emit(st, st.pos, "idle", -1, force)

        s = self.sign * float(pos[a] - self._start[a])                   # m along the reach
        v_back = -self.sign * float(st.vel[a])                           # m/s towards the start
        # level change: ramp the one stiffness
        with self._lock:
            req, self._level_req = self._level_req, None
        if req is not None and req != self._level:
            self._ramp = (self._k_now, LEVELS[req] / LEAD_M, t)
            with self._lock:
                self._level = req
                self.exercise = f"{self.GROUP}_{req}"
        if self._ramp is not None:
            # RAMP_STEPS commands, LEVEL_RAMP_S / RAMP_STEPS apart: the arm applies a stiffness 50 to 200 ms
            # after the call and only the latest one, so sending every tick would end as one late step
            k0, k1, t_r = self._ramp
            step = min(RAMP_STEPS, int((t - t_r) / (LEVEL_RAMP_S / RAMP_STEPS)) + 1)
            k = k0 + (k1 - k0) * step / RAMP_STEPS
            if k != self._k_now:
                self._k_now = k
                self._send_k(k)
            if step >= RAMP_STEPS:
                self._ramp = None

        # one tick of look-ahead on a handle that is speeding up towards the start (a let-go)
        v_eff = v_back + max(0.0, v_back - self._v_prev)
        self._v_prev = v_back
        # The band's anchor (where the spring pulls to). Out: it follows 5 cm behind the hand at once.
        # Back: it moves towards the start at V_RETURN at most, so a hand coming back slowly keeps the full
        # pull, and a handle that is let go is led back at one steady speed (15 Nov on the arm: a lead that
        # shrank with speed and came back made the empty handle go, stop, go, about once a second).
        # A let-go (speeding up towards the start past V_SNAP) puts the anchor on the handle at once.
        tau = 1.0 / (2.0 * math.pi * TARGET_FILTER_HZ)
        self._s_filt += (s - self._s_filt) * min(1.0, dt / (tau + dt))
        want = self._s_filt - LEAD_M
        if want >= self._anchor:
            self._anchor = want
        else:
            self._anchor = max(want, self._anchor - V_RETURN * dt)
        if v_eff > V_SNAP:
            self._anchor = max(self._anchor, s)
        # never ahead of the hand (the band only pulls back), never beyond the start
        self._anchor = max(0.0, min(self._anchor, max(s, 0.0)))
        target_s = self._anchor
        target = self._start.copy()
        target[a] += self.sign * target_s
        self.arm.set_target(_tup3(target))
        self._band_force = self._k_now * min(LEAD_M, max(0.0, s - target_s))

        # reps from position, with hysteresis
        f_along = self.sign * float(force[a])
        lateral = float(np.linalg.norm(np.delete(pos - self._start, a)))
        counted = None
        if self._rep is None:
            if s > BACK_M:
                self._rep = {"t0": t, "t_s": float(st.t) - (self._t0 or float(st.t)), "s_max": s, "out": False,
                             "f": [], "lat": []}
                self._phase = "out"
        if self._rep is not None:
            r = self._rep
            r["s_max"] = max(r["s_max"], s)
            r["lat"].append(lateral)
            if s >= OUT_M:
                r["out"] = True
            if r["out"] and s < r["s_max"] - 0.02:
                self._phase = "back"
            if self._phase == "out" or not r["f"]:
                r["f"].append(f_along)           # force statistics are for the push out, not the way back
            if s <= BACK_M:
                if r["out"]:
                    counted = r
                self._rep, self._phase = None, "idle"
        self._over = s > OVER_M
        msg = None
        if s >= TURN_BACK_M:
            msg = "Turn back"
        elif self.done:
            msg = "Set finished"
        with self._lock:
            self._message = msg
        rep_idx = self.rep_count if self._rep is not None else -1
        self._emit(st, target, self._phase, rep_idx, force)
        if counted is not None:
            self._count(counted, t)
        self._sim_cue(s, t)

    def _count(self, r: dict, t: float) -> None:
        f = np.asarray(r["f"], dtype=float)
        rep = RepResult(
            session_id=self.session_id, idx=self.rep_count, mode="resist",
            dial=round(-LEVELS[self._level] / FORCE_CAP_N, 3), t_start=round(r["t_s"], 2),
            duration_s=round(t - r["t0"], 2), rom_m=round(float(r["s_max"]), 4),
            path_err_mean_m=round(float(np.mean(r["lat"])), 4), path_err_max_m=round(float(np.max(r["lat"])), 4),
            sparc=0.0, peak_force_n=round(float(np.max(f)), 2), mean_force_n=round(float(np.mean(f)), 2),
            contribution=1.0, completed=True, simulated=self.simulated, rescued=False)
        with self._lock:
            self.rep_count += 1
            self.reps.append(rep)
        if self.on_rep is not None:
            self.on_rep(rep)

    def _sim_cue(self, s: float, t: float) -> None:
        """A simulated patient (software.sim_arm) pushes again after resting at the start."""
        if not (hasattr(self.arm, "patient") and hasattr(self.arm, "cue")) or not getattr(self.arm, "sim_cues", True):
            return
        if self._rep is None and s <= BACK_M and not self.done:
            if self._rest_since is None:
                self._rest_since = t
            elif t - self._rest_since >= SIM_REST_S and getattr(self.arm, "_intent", "rest") == "rest":
                self._rest_since = None
                self.arm.cue("out")
        else:
            self._rest_since = None

    # ------------------------------------------------------------------ back to the start at stop()
    def _wait(self) -> None:
        if getattr(self.arm, "realtime", True):
            time.sleep(DT)
        else:
            self.arm.step(DT)

    def _return_home(self) -> None:
        st = self.arm.get_state()
        if st.mode == "fault":
            return self._say("Not returned to the start: the arm reports a fault.")
        end = float(st.t) + COUNTDOWN_S
        give_up = float(st.t) + RETURN_WAIT_S
        held = 0                 # consecutive readings that say "held": one noisy sample is not a hand
        while True:
            st = self.arm.get_state()
            force = np.asarray(st.force, dtype=float) - self.force_baseline
            speed, f = float(np.linalg.norm(st.vel)), float(np.linalg.norm(force))
            held = held + 1 if (speed > GATE_SPEED or f > GATE_FORCE_N) else 0
            if held >= GATE_TICKS and float(st.t) < give_up:
                # still settling after the hold, or a hand on it: wait, and count down again from 3
                end, held = float(st.t) + COUNTDOWN_S, 0
            if held >= GATE_TICKS:
                self._emit(st, st.pos, "idle", -1, force)
                with self._lock:
                    self._countdown = None
                return self._say("Not returned to the start: the handle is being held "
                                 f"(it reads {f:.0f} N, moving {speed * 100:.0f} cm/s). Let go, then press Home.")
            left = end - float(st.t)
            with self._lock:
                self._countdown = round(max(0.0, left), 1)
                self._message = f"Returning to start, hands off: {math.ceil(max(0.0, left - 0.005))}"
            self._emit(st, st.pos, "idle", -1, force)
            if left <= 0:
                break
            self._wait()
        with self._lock:
            self._countdown = None
            self._message = "Returning to start. Hands off."
        self._run_job(self._home_guarded)
        while self._job is not None and self._job.is_alive():
            st = self.arm.get_state()
            self._watch_home(st)
            self._emit(st, st.pos, "idle", -1, np.asarray(st.force, dtype=float) - self.force_baseline)
            time.sleep(DT)
        self._job = None
        if self._job_exc is not None:
            raise self._job_exc
        st = self.arm.get_state()
        self._emit(st, st.pos, "idle", -1, np.asarray(st.force, dtype=float) - self.force_baseline)
        self._say("Back at the start.")
