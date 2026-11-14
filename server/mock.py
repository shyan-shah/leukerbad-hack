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


class MockArm:
    """Placeholder arm for mock mode. Never a real robot, so the server marks data simulated."""
    simulated = True
    reach_axis = 0

    def __init__(self) -> None:
        self.mode = "idle"

    def connect(self) -> None: ...
    def start_compliance(self) -> None: self.mode = "compliant"
    def hold(self) -> None: self.mode = "hold"
    def stop(self) -> None: self.mode = "idle"
    def close(self) -> None: self.mode = "idle"


def _min_jerk(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x ** 3 * (10 - 15 * x + 6 * x * x)


class MockEngine:
    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool,
                 reach_axis: int = 0, reach_sign: int = 1, reach_m: float = 0.30,
                 dial: float = 1.0, auto: bool = True, on_sample=None, on_rep=None,
                 strength: float = 0.6, time_scale: float = 1.0, seed: int = 0,
                 start_pos=(0.45, 0.0, 0.30)) -> None:
        self.arm = arm
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
                              clock.now_iso(), "reach_line",
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
                        "arm_mode": getattr(self.arm, "mode", None)}

    # ---------------------------------------------------------------- internals
    def _tick(self, t: float, s: float, lateral: float, phase: str, rep_idx: int, force_along: float,
              vel_along: float, lead: float) -> Sample:
        a = self.axis
        side = (a + 1) % 3
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
        with self._lock:
            dial = self.dial
        smp = Sample(t=round(t, 3), pos=tuple(pos), vel=tuple(vel), force=tuple(force), target=tuple(target),
                     dial=dial, rep_idx=rep_idx, simulated=True, phase=phase, q=q)
        with self._lock:
            self._latest = smp
        if self.on_sample:
            self.on_sample(smp)
        return smp

    def _run(self) -> None:
        dt = 0.01
        t = 0.0
        idx = 0
        rng = self.rng
        while not self._stop.is_set():
            with self._lock:
                dial = self.dial
            cap = float(np.clip(self.strength + rng.normal(0, 0.08), 0.02, 1.0))
            help_ = max(dial, 0.0)
            reach_frac = 1.0 if (cap > 0.15 or help_ > 0.3) else 0.6
            T = 3.0 + 3.0 * (1 - cap) * (1 - 0.5 * help_)
            err_amp = 0.004 + 0.025 * (1 - cap) * (1 - 0.4 * help_)
            contribution = float(np.clip(0.15 + 0.85 * cap - 0.1 * help_ * (1 - cap) + rng.normal(0, 0.04), 0, 1))
            rescued = help_ > 0.05 and cap < 0.2
            resist_n = 15.0 * max(-dial, 0.0)
            # idle
            for _ in range(int(IDLE_S / dt)):
                if self._stop.is_set():
                    return
                self._tick(t, 0.0, 0.0, "idle", -1, 0.0, 0.0, 0.0)
                t += dt
                time.sleep(dt / self.time_scale)
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
