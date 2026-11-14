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
- Occupied: force magnitude above ``F_PRESENT`` within the last ``OCCUPIED_WINDOW_S``.
- Hands-off rule, assist side only (dial > 0): if the handle is not occupied during a rep the
  rep ends now as not completed and the phase goes to idle. While the handle is empty the
  target is latched at the point where the hand was when it became empty (``K_HOLD``), so an
  empty handle is never driven along the path.
- Stall rescue: on the assist side, along-path speed under ``STALL_SPEED`` for
  ``STALL_ASSIST_S`` before 90% phase progress marks the rep rescued (the controller raises
  the dial to at least 0.6). On the resist side (dial < 0) a ``STALL_RESIST_S`` stall marks it
  rescued (the controller goes transparent). Not applied at exactly transparent.

Metrics: every RepResult metric (duration, ROM, path error, SPARC, force, contribution) is
computed on the ``out`` phase slice only, as section 4.2 requires for contribution. If SPARC
is undefined (the hand did not move) it is reported as 0.0.

Drivers: ``start()`` runs the 100 Hz thread for a real-time arm (``Arm`` or
``SimArm(realtime=True)``). For ``SimArm(realtime=False)`` no thread is started; the caller
drives the engine and the sim together with ``run_for(seconds)`` (one ``tick()`` then
``arm.step(DT)`` per 10 ms), which is deterministic. Every timer uses ``ArmState.t``.

Safety: any exception in a tick (including from a callback) calls ``arm.hold()`` first and
is then re-raised.

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
from software.adapt import AUTO_FLOOR, mode_of, next_dial
from software.metrics import contribution, force_stats, path_error, rep_metrics, rom
from software.paths import LinePath

__all__ = ["Engine", "DT"]

DT = 0.01                    # s, 100 Hz
NEAR_START_M = 0.02          # m along the reach axis: "at the start"
ARM_DWELL_S = 1.0            # s at the start (and occupied) before a rep is armed
OUT_DONE = 0.9               # progress that completes the out phase
OUT_TIMEOUT_S = 10.0         # s, out phase gives up (not completed)
BACK_TIMEOUT_S = 10.0        # s, back phase gives up and the rep ends anyway (team choice)
F_PRESENT = 1.5              # N, handle force magnitude meaning "a hand is on it"
OCCUPIED_WINDOW_S = 0.5      # s, occupied if force exceeded F_PRESENT within this window
STALL_SPEED = 0.01           # m/s along the path
STALL_ASSIST_S = 1.5         # s stall on the assist side before rescue
STALL_RESIST_S = 3.0         # s stall on the resist side before dropping to transparent
STALL_MAX_PROGRESS = 0.9     # stall rescue only before this phase progress
EXERCISE = "reach_line"


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _tup3(a) -> tuple[float, float, float]:
    return (float(a[0]), float(a[1]), float(a[2]))


class Engine:
    """Section 4.4 engine. See the module docstring."""

    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool,
                 reach_axis: int = 0, reach_sign: int = 1, reach_m: float = 0.30,
                 dial: float = 1.0, auto: bool = True,
                 on_sample=None, on_rep=None) -> None:
        if reach_axis not in (0, 1, 2):
            raise ValueError(f"reach_axis must be 0, 1 or 2, got {reach_axis}")
        if not reach_m > 0:
            raise ValueError(f"reach_m must be > 0, got {reach_m}")
        self.arm = arm
        self.session_id = str(session_id)
        self.patient_id = str(patient_id)
        self.simulated = bool(simulated)
        self.reach_axis = int(reach_axis)
        self.reach_sign = 1 if reach_sign >= 0 else -1
        self.reach_m = float(reach_m)
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

        self.path: LinePath | None = None
        self._t0: float | None = None
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
        self.arm.start_compliance()
        start = np.asarray(self.arm.start_pos, dtype=float)
        end = start.copy()
        end[self.reach_axis] += self.reach_sign * self.reach_m
        self.path = LinePath(_tup3(start), _tup3(end))
        self.started_at = _now_iso()
        self._started = True
        self._stop_evt.clear()
        if getattr(self.arm, "realtime", True):
            self._thread = threading.Thread(target=self._loop, name="engine", daemon=True)
            self._thread.start()

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
            exercise=EXERCISE, n_reps=self.rep_count, simulated=self.simulated)

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
                        "arm_mode": self._arm_mode}

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
        self._clear_rep()

    def _clear_rep(self) -> None:
        self._rep_idx = -1
        self._rep_dial = 0.0
        self._rep_t0 = 0.0
        self._rescued = False
        self._stall_since: float | None = None
        self._completed = False
        self._out_t: list[float] = []
        self._out_pos: list[tuple[float, float, float]] = []
        self._out_force: list[tuple[float, float, float]] = []

    def _progress(self, pos) -> float:
        start = np.asarray(self.path.start)
        return float((np.asarray(pos) - start)[self.reach_axis] * self.reach_sign / self.reach_m)

    def _on_line(self, pos) -> np.ndarray:
        """Hand projected onto the path line, clamped to the segment."""
        return self.path.point_at(self._progress(pos))

    def _tick(self) -> None:
        state = self.arm.get_state()
        t_arm = float(state.t)
        if self._t0 is None:
            self._t0 = t_arm
        t = t_arm - self._t0
        pos = np.asarray(state.pos, dtype=float)
        force = np.asarray(state.force, dtype=float)
        with self._lock:
            dial = self._dial
            self._arm_mode = state.mode

        if state.mode != "compliant":
            # hold, fault or idle: never command. Abandon any rep in progress.
            if self._phase != "idle":
                self._finish_rep(dial, aborted=True)
            self._phase = "idle"
            self._near_since = None
            self._latch = None
            self._k_sent = None  # re-send stiffness if compliance is restarted
            self._emit(t, state, _tup3(pos), dial, "idle", -1)
            return

        # occupied?
        if float(np.linalg.norm(force)) > F_PRESENT:
            self._last_force_t = t_arm
        occupied = (self._last_force_t is not None
                    and t_arm - self._last_force_t <= OCCUPIED_WINDOW_S)

        s = self._progress(pos)
        near_start = abs(s) * self.reach_m <= NEAR_START_M

        # hands-off rule (assist side only)
        if self._phase in ("out", "back") and dial > 0 and not occupied:
            self._finish_rep(dial, aborted=True)
            self._phase = "idle"
            self._near_since = None

        # idle -> out
        if self._phase == "idle":
            if near_start and occupied:
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
            else:
                self._stall_since = None

        # command
        if self._phase in ("out", "back"):
            self._latch = None
            target, k = controller.command(dial, self._phase, s, t_arm - self._phase_t0,
                                           pos, self.path, self._rescued)
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

        self.arm.set_target(target)
        if k != self._k_sent:
            self.arm.set_stiffness(*k)
            self._k_sent = k
        self._emit(t, state, target, dial, label_phase,
                   label_idx if label_phase != "idle" else -1)

    def _begin_rep(self, t_arm: float, t: float, dial: float) -> None:
        self._clear_rep()
        self._phase = "out"
        self._phase_t0 = t_arm
        self._near_since = None
        self._rep_idx = self.rep_count
        self._rep_dial = dial
        self._rep_t0 = t

    def _emit(self, t: float, state, target, dial: float, phase: str, rep_idx: int) -> None:
        smp = Sample(t=float(t), pos=_tup3(state.pos), vel=_tup3(state.vel),
                     force=_tup3(state.force), target=_tup3(target), dial=float(dial),
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
        start, end = self.path.start, self.path.end
        try:
            return rep_metrics(t, pos, force, start, end)
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
                                             dt=float(np.median(np.diff(t)))),
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
