"""A stand-in engine and arm with the MASTER_PLAN 4.4 interface. Everything it emits is SIMULATED.

Purpose: let the API, run script, terminal readout and Mat and Gio's screens be built and
tested before Shiv's software/engine.py exists, and keep a robot-free feed for demos of the
software. It is NOT the controller: it does not use the arm, and its numbers are shaped to
look plausible, not computed from physics (SPARC in particular is a made-up value here).

Use:  python -m server.run --mock [--strength 0.6] [--time-scale 1]
"""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from . import clock
from .contract import RepResult, Sample, SessionSummary
from .stats import mode_of

IDLE_S = 1.0
SETUP_S = 2.5            # pull: time the pretend patient takes to move the handle to the far end
CAL_WAIT_S = 1.0         # calibrate: wait for the push to begin
CAL_PUSH_S = 3.0         # calibrate: the comfortable push itself (handle held still)
CAL_FRACTION = 0.6       # resistance = this share of the comfortable push (first session)
CAL_FRACTION_MAX = 0.8   # each later session of the same patient and exercise: +0.05 up to this
CALIBRATES = ("push", "pull")
TRY_S = 3.0              # armtest: length of one push-and-hold try
REST_S = 5.0             # armtest: rest between tries (phase "back", rep_idx -1, as the real engine reports it)
K_HOLD_TEST = 600.0      # N/m: the handle gives way by force / this during a try (about 5 cm at 30 N)
FORCE_CAP_N = 30.0       # armtest readings stop at about this (the robot's safety limit)
# exercise -> (dial, auto, reach_m) used when the caller does not set them
PRESETS = {"reach": (1.0, True, 0.30), "push": (-0.6, False, 0.28), "pull": (-0.6, False, 0.28),
           "armtest": (0.0, False, 0.30)}
BAND_LEVELS = {1: 10.0, 2: 15.0, 3: 20.0, 4: 28.0}      # push_1 .. push_4, as software/simple.py
for _n, _f in BAND_LEVELS.items():
    PRESETS[f"push_{_n}"] = (-_f / 30.0, False, 0.30)
# Row and the strength test (software/simple_more.py). Kept beside PRESETS, which older callers list.
MORE_PRESETS = {f"row_{_n}": (-_f / 30.0, False, 0.28) for _n, _f in BAND_LEVELS.items()}   # far end to the start pose
MORE_PRESETS["strength"] = (0.0, False, 0.30)
ALL_PRESETS = PRESETS | MORE_PRESETS
HANDS_OFF_S = 3.0        # push_N, row_N, strength: the "hands off" countdown before the band comes on
ROW_FAR_M = 0.28         # row_N: the far end, as software.simple_more.FAR_M
ROW_MOVE_SPEED = 0.05    # m/s, the arm's own move to the far end
REZERO_S = 2.0           # row_N: the second countdown, at the far end
READY_S = 3.0            # strength: "Get ready"


class MockArm:
    """Placeholder arm for mock mode. Never a real robot, so the server marks data simulated."""
    simulated = True
    reach_axis = 0

    def __init__(self) -> None:
        self.mode = "idle"

    def connect(self) -> None: ...
    def start_compliance(self) -> None: self.mode = "compliant"
    def hold(self) -> None: self.mode, self.test_limits_on = "hold", False   # as the real arm: back to normal limits
    def stop(self) -> None: self.mode = "idle"
    def close(self) -> None: self.mode = "idle"

    test_limits_on = False      # pretend test profile, so screens can show the 60 N force cap

    def set_test_limits(self, on: bool) -> None: self.test_limits_on = bool(on)


def _min_jerk(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x ** 3 * (10 - 15 * x + 6 * x * x)


class MockEngine:
    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool,
                 reach_axis: int = 0, reach_sign: int = 1, reach_m: float | None = None,
                 dial: float | None = None, auto: bool | None = None, on_sample=None, on_rep=None,
                 strength: float = 0.6, time_scale: float = 1.0, seed: int = 0,
                 start_pos=(0.45, 0.0, 0.30), exercise: str = "reach", reps: int | None = None,
                 calibrate: bool | None = None, calibration_state: dict | None = None) -> None:
        """`exercise`: reach, push, pull or armtest (anything else behaves like reach).
        `reps`: stop making reps after this many and stay idle; None = no limit (armtest: 3 tries).
        `calibrate`: play the comfortable-push phase first (None: on for push and pull, never for the others).
        `calibration_state`: `calibration_state_after` of this patient's previous session of the exercise."""
        self.arm = arm
        self.exercise = exercise
        p_dial, p_auto, p_reach = ALL_PRESETS.get(exercise, PRESETS["reach"])
        dial = p_dial if dial is None else dial
        auto = p_auto if auto is None else auto
        reach_m = p_reach if reach_m is None else reach_m
        self.reps = (3 if exercise in ("armtest", "strength") else None) if reps is None else int(reps)
        known = exercise in ALL_PRESETS
        self.group = ("push" if known and exercise.startswith("push_") else "row" if known and exercise.startswith("row_")
                      else "strength" if exercise == "strength" else None)      # the band engines' programmes
        self.flip = exercise == "pull" or self.group == "row"    # the line runs from the far end towards the patient
        self.session_id, self.patient_id = session_id, patient_id
        self.simulated = True                     # always: nothing here comes from a real person
        self.axis, self.sign, self.reach = reach_axis, (1 if reach_sign >= 0 else -1), reach_m
        self.dial, self.auto = float(dial), bool(auto)
        self.on_sample, self.on_rep = on_sample, on_rep
        self.strength, self.time_scale = strength, max(time_scale, 1e-3)
        self.rng = np.random.default_rng(seed)
        self.start_xyz = np.array(start_pos, float)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: Sample | None = None
        self.rep_count = 0
        self.started_at = ""
        can_cal = exercise in CALIBRATES
        self.calibrate = can_cal and (True if calibrate is None else bool(calibrate))
        self.calibration_state = dict(calibration_state) if isinstance(calibration_state, dict) else None
        self.calibration_state_after: dict | None = self.calibration_state
        self.resistance_n: float | None = None
        self._cal: dict | None = None if not can_cal else self._cal_dict(
            "waiting" if self.calibrate else "skipped", 0.0,
            reason="waiting for a push" if self.calibrate else "calibration turned off for this session")
        self._arming = {"progress": 0.0, "reason": "calibrating" if self.calibrate else "resting before the rep"}
        self._go = threading.Event()
        self.level = int(exercise.split("_")[1]) if self.group in ("push", "row") else None
        self._message: str | None = None
        self._countdown: float | None = None
        self._best: float | None = None           # strength: best and last peak so far
        self._last: float | None = None

    # ---------------------------------------------------------------- interface (4.4)
    def start(self) -> None:
        if hasattr(self.arm, "start_compliance"):
            self.arm.start_compliance()
        self.started_at = clock.now_iso()
        self._thread = threading.Thread(target=self._run, name="mock-engine", daemon=True)
        self._thread.start()

    def stop(self) -> SessionSummary:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if hasattr(self.arm, "hold"):
            self.arm.hold()
        return SessionSummary(self.session_id, self.patient_id, self.started_at,
                              clock.now_iso(), self.exercise,
                              self.rep_count, True)

    def set_dial(self, dial: float, auto: bool | None = None) -> None:
        with self._lock:
            self.dial = float(min(max(dial, -1.0), 1.0))
            if auto is not None:
                self.auto = bool(auto)

    def snapshot(self) -> dict:
        with self._lock:
            d = self._latest.to_dict() if self._latest else {}
            return d | {"rep_count": self.rep_count, "auto": self.auto,
                        "arm_mode": getattr(self.arm, "mode", None),
                        "calibration": None if self._cal is None else dict(self._cal),
                        "arming": dict(self._arming)} | self._band_fields()

    def _band_fields(self) -> dict:
        """push_N, row_N, strength: the fields the band engines (software/simple.py, simple_more.py) report."""
        if self.group is None:
            return {}
        start = self.start_xyz.copy()
        if self.group == "row":         # the path starts at the far end and runs 0.30 m towards the patient
            start[self.axis] += self.sign * ROW_FAR_M
            end = start.copy()
            end[self.axis] -= self.sign * 0.30
        else:
            end = start.copy()
            end[self.axis] += self.sign * self.reach
        out = {"exercise": self.exercise, "group": self.group, "level": self.level,
               "level_force_n": BAND_LEVELS[self.level] if self.level else None, "message": self._message,
               "countdown_s": self._countdown, "force_cap_n": 30.0, "arming": None,
               "path_start": [float(v) for v in start], "path_end": [float(v) for v in end]}
        if self.group == "strength":
            n = self.reps or 3
            out |= {"kind": "test", "try": min(self.rep_count + 1, n), "tries": n,
                    "best_force_n": self._best, "last_force_n": self._last}
        return out

    def set_level(self, level: int) -> None:
        """push_N and row_N only: change the resistance level now. The exercise stays Push or Row."""
        if self.level is None:
            raise RuntimeError("levels are for push_1 to push_4 and row_1 to row_4")
        if level not in BAND_LEVELS:
            raise ValueError(f"level must be 1 to 4, got {level!r}")
        with self._lock:
            self.level, self.exercise = int(level), f"{self.group}_{int(level)}"
            self.dial = -BAND_LEVELS[level] / 30.0

    def go(self) -> None:
        """Operator cue: start the next rep now instead of waiting out the rest."""
        self._go.set()

    def resume(self) -> None:
        """Continue after a hold: the pretend arm goes back to compliant."""
        if hasattr(self.arm, "start_compliance"):
            self.arm.start_compliance()

    # ---------------------------------------------------------------- internals
    @staticmethod
    def _cal_dict(status: str, progress: float, comfort=None, resistance=None, fraction=None, reason=None) -> dict:
        return {"status": status, "progress": round(float(progress), 3), "comfort_force_n": comfort,
                "resistance_n": resistance, "fraction": fraction, "reason": reason}

    def _set_arming(self, progress: float, reason: str | None) -> None:
        with self._lock:
            self._arming = {"progress": round(float(progress), 3), "reason": reason}

    def _run_calibrate(self, t: float) -> float | None:
        """One comfortable push with the handle held still: CAL_WAIT_S of waiting, then CAL_PUSH_S with a
        rising then steady force. Sets the resistance from it. Uses no random numbers, so the reps that
        follow are the same with and without it. Returns the new t, or None if stopped."""
        dt = 0.01
        s0 = 1.0 if self.flip else 0.0            # _tick flips it back: the handle stays at the start
        comfort = 10.0 + 20.0 * self.strength     # N, the pretend patient's comfortable push
        limits = getattr(self.arm, "set_test_limits", None)
        if limits:
            limits(True)        # as the real engine does for the push: readings may go to 60 N
        for _ in range(int(CAL_WAIT_S / dt)):
            if self._stop.is_set():
                return None
            self._tick(t, s0, 0.0, "calibrate", -1, 0.0, 0.0, 0.0, dial=0.0)
            t += dt
            self._sleep(dt)
        n, fs = int(CAL_PUSH_S / dt), []
        for i in range(n):
            if self._stop.is_set():
                return None
            x = i / max(n - 1, 1)
            f = comfort * min(1.0, x / 0.3) + 0.4 * math.sin(40 * x)      # rises for 0.9 s, then steady
            with self._lock:
                self._cal = self._cal_dict("pushing", (i + 1) / n)
            self._tick(t, s0, 0.0, "calibrate", -1, -f if self.flip else f, 0.0, 0.0, dial=0.0)
            if x >= 0.4:
                fs.append(f)
            t += dt
            self._sleep(dt)
        prev = self.calibration_state or {}
        try:
            fraction = min(CAL_FRACTION_MAX, float(prev["fraction"]) + 0.05)
            sessions = int(prev.get("sessions", 0)) + 1
        except (KeyError, TypeError, ValueError):
            fraction, sessions = CAL_FRACTION, 1
        comfort_n = round(float(np.mean(fs)), 1)
        resistance = round(fraction * comfort_n, 1)
        if limits:
            limits(False)
        with self._lock:
            self.resistance_n = resistance
            self._cal = self._cal_dict("done", 1.0, comfort_n, resistance, round(fraction, 2))
            self.calibration_state_after = {"version": 1, "fraction": round(fraction, 2),
                                            "comfort_force_n": comfort_n, "resistance_n": resistance,
                                            "sessions": sessions}
        return t

    def _tick(self, t: float, s: float, lateral: float, phase: str, rep_idx: int, force_along: float,
              vel_along: float, lead: float, dial: float | None = None) -> Sample:
        a = self.axis
        side = (a + 1) % 3
        if self.flip:      # progress s counts from the far end back towards the start
            s, vel_along, force_along, lead = 1.0 - s, -vel_along, -force_along, -lead
        pos = self.start_xyz.copy()
        pos[a] += self.sign * s * self.reach
        pos[side] += lateral
        vel = np.zeros(3)
        vel[a] = self.sign * vel_along
        force = np.zeros(3)
        force[a] = self.sign * force_along
        target = pos.copy()
        target[a] += self.sign * lead
        q = tuple(round(0.3 * math.sin(0.7 * j + 2 * s), 4) for j in range(7))
        if dial is None:
            with self._lock:
                dial = self.dial
        smp = Sample(t=round(t, 3), pos=tuple(pos), vel=tuple(vel), force=tuple(force), target=tuple(target),
                     dial=dial, rep_idx=rep_idx, simulated=True, phase=phase, q=q)
        with self._lock:
            self._latest = smp
        if self.on_sample:
            self.on_sample(smp)
        return smp

    def _sleep(self, dt: float) -> None:
        time.sleep(dt / self.time_scale)

    def _idle_forever(self, t: float) -> None:
        """The set is finished: keep sending resting samples until stop()."""
        while not self._stop.is_set():
            self._tick(t, 0.0, 0.0, "idle", -1, 0.0, 0.0, 0.0)
            t += 0.01
            self._sleep(0.01)

    def _run_armtest(self) -> None:
        """Isometric strength test: the handle stays still, the person pushes for TRY_S, `reps` tries."""
        dt, t, rng = 0.01, 0.0, self.rng
        for idx in range(self.reps or 3):
            # 1 s of rest before the first try, then REST_S between tries (reported as phase "back")
            for _ in range(int((IDLE_S if idx == 0 else REST_S) / dt)):
                if self._stop.is_set():
                    return
                self._tick(t, 0.0, 0.0, "idle" if idx == 0 else "back", -1, 0.0, 0.0, 0.0)
                t += dt
                self._sleep(dt)
            peak = (8.0 + 30.0 * float(np.clip(self.strength + rng.normal(0, 0.05), 0.02, 1.0)))
            t_start, fs = t, []
            n = int(TRY_S / dt)
            for i in range(n):
                if self._stop.is_set():
                    return
                x = i / max(n - 1, 1)
                f = min(FORCE_CAP_N, max(0.0, peak * min(1.0, x / 0.25) * (1 - 0.15 * x) + rng.normal(0, 0.3)))
                self._tick(t, f / K_HOLD_TEST / self.reach, 0.0, "out", idx, f, 0.0, 0.0)
                fs.append(f)
                t += dt
                self._sleep(dt)
            rep = RepResult(
                session_id=self.session_id, idx=idx, mode="isometric", dial=0.0, t_start=round(t_start, 2),
                duration_s=TRY_S, rom_m=round(max(fs) / K_HOLD_TEST, 4), path_err_mean_m=0.0,
                path_err_max_m=0.0, sparc=0.0, peak_force_n=round(float(np.max(fs)), 2),
                mean_force_n=round(float(np.mean(fs)), 2), contribution=1.0, completed=True, simulated=True,
                rescued=False)
            with self._lock:
                self.rep_count = idx + 1
            if self.on_rep:
                self.on_rep(rep)
        self._idle_forever(t)

    def _count(self, t: float, seconds: float, text: str, s: float = 0.0, floor: int = 0) -> float | None:
        """A countdown in the state ("<text> 3", 2, 1) with the handle resting at progress s. Returns the new
        t, or None if stopped."""
        dt = 0.01
        for i in range(int(seconds / dt)):
            if self._stop.is_set():
                return None
            left = seconds - i * dt
            with self._lock:
                self._countdown = round(left, 1)
                self._message = f"{text} {max(floor, math.ceil(left - 0.005))}"
            self._tick(t, s, 0.0, "idle", -1, 0.0, 0.0, 0.0)
            t += dt
            self._sleep(dt)
        with self._lock:
            self._countdown, self._message = None, None
        return t

    def _run_strength(self) -> None:
        """The strength test of software/simple_more.py: hands-off countdown, then per try "Get ready: 3, 2, 1",
        3 s "Push and hold" (phase "out"), 5 s "Rest". The handle gives way by force / K_HOLD_TEST."""
        dt, rng = 0.01, self.rng
        t = self._count(0.0, HANDS_OFF_S, "Hands off: zeroing in")
        if t is None:
            return
        for idx in range(self.reps or 3):
            t = self._count(t, READY_S, "Get ready:", floor=1)
            if t is None:
                return
            peak = 8.0 + 30.0 * float(np.clip(self.strength + rng.normal(0, 0.05), 0.02, 1.0))
            t_start, fs, n = t, [], int(TRY_S / dt)
            for i in range(n):
                if self._stop.is_set():
                    return
                x = i / max(n - 1, 1)
                f = min(FORCE_CAP_N, max(0.0, peak * min(1.0, x / 0.25) * (1 - 0.15 * x) + rng.normal(0, 0.3)))
                with self._lock:
                    self._countdown, self._message = round(TRY_S - i * dt, 1), "Push and hold"
                self._tick(t, f / K_HOLD_TEST / self.reach, 0.0, "out", idx, f, 0.0, 0.0, dial=0.0)
                fs.append(f)
                t += dt
                self._sleep(dt)
            pk = round(float(np.max(fs)), 2)
            rep = RepResult(
                session_id=self.session_id, idx=idx, mode="isometric", dial=0.0, t_start=round(t_start, 2),
                duration_s=TRY_S, rom_m=round(max(fs) / K_HOLD_TEST, 4), path_err_mean_m=0.0,
                path_err_max_m=0.0, sparc=0.0, peak_force_n=pk, mean_force_n=round(float(np.mean(fs)), 2),
                contribution=1.0, completed=True, simulated=True, rescued=False)
            with self._lock:
                self.rep_count = idx + 1
                self._last, self._best = pk, pk if self._best is None else max(self._best, pk)
            if self.on_rep:
                self.on_rep(rep)
            n = int(REST_S / dt)
            for i in range(n):
                if self._stop.is_set():
                    return
                with self._lock:
                    self._countdown, self._message = round(REST_S - i * dt, 1), "Rest"
                self._tick(t, 0.0, 0.0, "idle", -1, 0.0, 0.0, 0.0, dial=0.0)
                t += dt
                self._sleep(dt)
        with self._lock:
            self._countdown, self._message = None, "Set finished"
        self._idle_forever(t)

    def _run_row_start(self, t: float) -> float | None:
        """Row after the first zero: a countdown, the arm's own move from the start pose to the far end at
        ROW_MOVE_SPEED, then a second short countdown at the far end (as software.simple_more.RowEngine)."""
        dt = 0.01
        t = self._count(t, HANDS_OFF_S, "Hands off: moving to the start position in", s=1.0)
        if t is None:
            return None
        with self._lock:
            self._message = "The arm is moving to the start position. Hands off."
        n = int(ROW_FAR_M / ROW_MOVE_SPEED / dt)
        for i in range(n):
            if self._stop.is_set():
                return None
            self._tick(t, 1.0 - (i + 1) / n, 0.0, "idle", -1, 0.0, -ROW_MOVE_SPEED, 0.0)
            t += dt
            self._sleep(dt)
        return self._count(t, REZERO_S, "Hands off: zeroing in")

    def _run(self) -> None:
        if self.exercise == "armtest":
            return self._run_armtest()
        if self.group == "strength":
            return self._run_strength()
        dt = 0.01
        t = 0.0
        idx = 0
        rng = self.rng
        if self.calibrate:
            t = self._run_calibrate(t)
            if t is None:
                return
        if self.level is not None:      # the band engine's "hands off" countdown, then zeroing
            n = int(HANDS_OFF_S / dt)
            for i in range(n):
                if self._stop.is_set():
                    return
                left = HANDS_OFF_S - i * dt
                with self._lock:
                    self._countdown = round(left, 1)
                    self._message = f"Hands off: zeroing in {math.ceil(left - 0.005)}"
                self._tick(t, 1.0 if self.group == "row" else 0.0, 0.0, "idle", -1, 0.0, 0.0, 0.0)   # at the start pose
                t += dt
                self._sleep(dt)
            with self._lock:
                self._countdown, self._message = None, None
        if self.group == "row":         # the arm takes the handle to the far end by itself
            t = self._run_row_start(t)
            if t is None:
                return
        elif self.flip:     # pull: the person first moves the handle from the start to the far end
            n = int(SETUP_S / dt)
            for i in range(n):
                if self._stop.is_set():
                    return
                self._tick(t, 1.0 - _min_jerk(i / max(n - 1, 1)), 0.0, "setup", -1, 0.0, 0.0, 0.0, dial=0.0)
                t += dt
                self._sleep(dt)
        while not self._stop.is_set():
            if self.reps is not None and idx >= self.reps:
                self._set_arming(0.0, "set finished")
                if self.level is not None:
                    self._message = "Set finished"
                return self._idle_forever(t)
            with self._lock:
                dial = self.dial
            cap = float(np.clip(self.strength + rng.normal(0, 0.08), 0.02, 1.0))
            help_ = max(dial, 0.0)
            reach_frac = 1.0 if (cap > 0.15 or help_ > 0.3) else 0.6
            T = 3.0 + 3.0 * (1 - cap) * (1 - 0.5 * help_)
            err_amp = 0.004 + 0.025 * (1 - cap) * (1 - 0.4 * help_)
            contribution = float(np.clip(0.15 + 0.85 * cap - 0.1 * help_ * (1 - cap) + rng.normal(0, 0.04), 0, 1))
            rescued = help_ > 0.05 and cap < 0.2
            resist_n = 15.0 * max(-dial, 0.0) if self.resistance_n is None else self.resistance_n
            if self.level is not None:
                resist_n = BAND_LEVELS[self.level]
            # idle
            n_idle = int(IDLE_S / dt)
            for i in range(n_idle):
                if self._stop.is_set():
                    return
                if self._go.is_set():       # operator cue: skip the rest
                    break
                self._set_arming((i + 1) / n_idle, "resting before the rep")
                self._tick(t, 0.0, 0.0, "idle", -1, 0.0, 0.0, 0.0)
                t += dt
                time.sleep(dt / self.time_scale)
            self._go.clear()
            self._set_arming(1.0, None)
            t_start = t
            out_s, out_err, out_f, out_v = [], [], [], []
            for phase, n in (("out", int(T / dt)), ("back", int(T / dt))):
                for i in range(n):
                    if self._stop.is_set():
                        return
                    x = i / max(n - 1, 1)
                    s = reach_frac * (_min_jerk(x) if phase == "out" else 1 - _min_jerk(x))
                    v = reach_frac * self.reach * 30 * x * x * (1 - x) ** 2 / T * (1 if phase == "out" else -1)
                    lat = err_amp * math.sin(math.pi * x) + rng.normal(0, 0.0008)
                    f = (2.0 + 6.0 * cap) * math.sin(math.pi * x) + resist_n * s + rng.normal(0, 0.3)
                    if phase == "back":
                        f = -0.5 * f
                    lead = 0.05 * help_ * (1 - cap) if phase == "out" else 0.0
                    if dial < -0.05:
                        lead = -0.05
                    self._tick(t, s, lat, phase, idx, f, v, lead)
                    if phase == "out":
                        out_s.append(s), out_err.append(abs(lat)), out_f.append(abs(f)), out_v.append(abs(v))
                    t += dt
                    time.sleep(dt / self.time_scale)
            completed = max(out_s) >= 0.9
            rep = RepResult(
                session_id=self.session_id, idx=idx, mode=mode_of(dial), dial=round(dial, 3), t_start=round(t_start, 2),
                duration_s=round(2 * T, 2), rom_m=round((max(out_s) - min(out_s)) * self.reach, 4),
                path_err_mean_m=round(float(np.mean(out_err)), 4), path_err_max_m=round(float(np.max(out_err)), 4),
                sparc=round(-1.5 - 0.8 * (1 - cap) + float(rng.normal(0, 0.05)), 3),
                peak_force_n=round(float(np.max(out_f)), 2), mean_force_n=round(float(np.mean(out_f)), 2),
                contribution=round(contribution, 3), completed=bool(completed), simulated=True, rescued=bool(rescued))
            idx += 1
            with self._lock:
                self.rep_count = idx
                if self.auto:   # same rule as MASTER_PLAN 4.2 / software/adapt.py
                    ok = (completed and rep.path_err_mean_m < 0.015 and T < 6.0
                          and contribution > 0.6 and not rescued)
                    bad = (not completed) or contribution < 0.3 or rescued
                    self.dial = float(np.clip(self.dial - 0.15 if ok else self.dial + 0.10 if bad else self.dial,
                                              -0.6, 1.0))
            if self.on_rep:
                self.on_rep(rep)
