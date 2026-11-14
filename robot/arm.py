"""robot/arm.py: the only code in the repo that talks to the Flexiv Rizon 4.

Implements the frozen interface of context/MASTER_PLAN.md section 4.3 (package K1).

The arm runs its own Cartesian impedance controller (NRT_CARTESIAN_MOTION_FORCE).
Python only streams target points and, a few times per rep, per-axis stiffness.
Every safety clamp lives in the pure helpers at the top of this file
(clamp_target, clamp_stiffness, check_trip) so they are testable with no robot.

`flexivrdk` is imported lazily inside Arm.connect(), so importing this module and
running robot/tests/test_arm_offline.py works on any machine.

Robot-specific values (serial, force sign, start pose, reach axis) come from
robot/config.json. Until K0/K4 are done they are PLACEHOLDERS listed in the
config's "placeholders" key; connect() refuses the placeholder serial and home()
refuses a placeholder start pose.
"""

from __future__ import annotations

import json
import math
import threading
import time
import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

CONFIG_PATH = Path(__file__).with_name("config.json")

# Orientation is locked to the start orientation, so these only bound small corrections.
# Not part of the frozen Limits dataclass; tune in K3 and record in robot/TUNING.md.
MAX_ANGULAR_VEL = 0.5   # rad/s  (RDK default 1.0)
MAX_ANGULAR_ACC = 2.0   # rad/s^2 (RDK default 5.0)
HOME_SPEED = 0.05       # m/s, straight-line ramp used by home()
HOME_MAX_DISTANCE = 0.60  # m, refuse to home from further away than this (jog manually instead)
BOX_TRIP_MARGIN = 0.02  # m, hand this far outside the workspace box trips to hold
TICK_S = 0.01           # 100 Hz


# --------------------------------------------------------------------------- data types

@dataclass(frozen=True)
class ArmState:
    t: float                                  # time.monotonic(), seconds
    pos: tuple[float, float, float]           # handle (TCP) position, m, base frame
    quat: tuple[float, float, float, float]   # qw, qx, qy, qz
    vel: tuple[float, float, float]           # m/s, base frame
    force: tuple[float, float, float]         # N, force the PERSON applies to the handle, base frame
    q: tuple[float, ...]                      # 7 joint angles, rad
    mode: str                                 # "idle" | "compliant" | "hold" | "fault"
    fault: str | None                         # human-readable reason for the last trip, else None


@dataclass(frozen=True)
class Limits:
    k_max: float = 600.0
    max_lead_m: float = 0.05
    k_hold: float = 300.0
    max_linear_vel: float = 0.15
    max_linear_acc: float = 0.5
    trip_speed: float = 0.40
    trip_force: float = 40.0
    max_contact_n: float = 30.0
    max_contact_nm: float = 5.0
    watchdog_s: float = 0.2
    box_half_m: tuple[float, float, float] = (0.35, 0.10, 0.10)   # around the start pose, base axes


# --------------------------------------------------------------------------- config

@dataclass(frozen=True)
class ArmConfig:
    serial: str
    force_sign: float                          # +1 or -1
    reach_axis: int                            # 0 = x, 1 = y
    start_tcp_pose: tuple[float, ...]          # x, y, z, qw, qx, qy, qz
    start_q: tuple[float, ...] | None
    placeholders: frozenset[str]

    def is_placeholder(self, key: str) -> bool:
        return key in self.placeholders


def load_config(path: str | Path | None = None) -> ArmConfig:
    """Load robot/config.json. Raises ValueError on malformed values."""
    p = Path(path) if path is not None else CONFIG_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    serial = str(raw["serial"])
    force_sign = float(raw["force_sign"])
    if force_sign not in (1.0, -1.0):
        raise ValueError(f"force_sign must be +1 or -1, got {force_sign}")
    reach_axis = int(raw["reach_axis"])
    if reach_axis not in (0, 1):
        raise ValueError(f"reach_axis must be 0 (x) or 1 (y), got {reach_axis}")
    sp = raw["start_pose"]
    tcp = tuple(float(v) for v in sp["tcp_pose"])
    if len(tcp) != 7 or not all(math.isfinite(v) for v in tcp):
        raise ValueError("start_pose.tcp_pose must be 7 finite numbers: x, y, z, qw, qx, qy, qz")
    q = sp.get("q")
    q = tuple(float(v) for v in q) if q is not None else None
    return ArmConfig(serial, force_sign, reach_axis, tcp, q, frozenset(raw.get("placeholders", [])))


def limits_for_reach_axis(limits: Limits, reach_axis: int) -> Limits:
    """Lay the workspace box out along the reach axis.

    `limits.box_half_m` is read as (reach, side, up). For reach axis x that is already
    base axes; for reach axis y the first two are swapped. The returned Limits has the
    box in base axes, which is what clamp_target and check_trip use.
    """
    if reach_axis == 0:
        return limits
    if reach_axis == 1:
        r, s, u = limits.box_half_m
        return replace(limits, box_half_m=(s, r, u))
    raise ValueError(f"reach_axis must be 0 or 1, got {reach_axis}")


# --------------------------------------------------------------------------- pure safety helpers

Vec3 = tuple[float, float, float]


def _finite3(v: Sequence[float]) -> bool:
    return len(v) == 3 and all(math.isfinite(float(x)) for x in v)


def clamp_target(pos: Sequence[float], hand: Sequence[float], start: Sequence[float],
                 limits: Limits) -> Vec3:
    """Clamp a requested target, first to the workspace box around `start`, then to at
    most `limits.max_lead_m` from the hand. The lead clamp is applied last, so the result
    is never further than max_lead_m from the hand. A non-finite request returns the hand.
    """
    hand = tuple(float(x) for x in hand)
    if not _finite3(pos):
        return hand  # type: ignore[return-value]
    boxed = [min(max(float(p), s - h), s + h) for p, s, h in zip(pos, start, limits.box_half_m)]
    d = [b - x for b, x in zip(boxed, hand)]
    dist = math.sqrt(sum(c * c for c in d))
    lead = limits.max_lead_m
    if dist > lead:
        scale = lead / dist
        # Scale, then guard against float rounding pushing the result a hair past the lead.
        out = [x + c * scale for x, c in zip(hand, d)]
        while math.dist(out, hand) > lead:
            scale *= 1.0 - 1e-12
            out = [x + c * scale for x, c in zip(hand, d)]
        return tuple(out)  # type: ignore[return-value]
    return tuple(boxed)  # type: ignore[return-value]


def clamp_stiffness(k: Sequence[float], limits: Limits,
                    k_nom: Sequence[float] | None = None) -> Vec3:
    """Clamp per-axis translational stiffness (N/m) to [0, min(k_max, K_x_nom[axis])].

    `k_nom` is robot.info().K_x_nom (six values, only the first three used) or None before
    connect. A non-finite value becomes 0 (free axis; the target stays on/near the hand).
    """
    if len(k) != 3:
        raise ValueError(f"stiffness needs 3 values, got {len(k)}")
    out = []
    for i, v in enumerate(k):
        v = float(v)
        cap = limits.k_max if k_nom is None else min(limits.k_max, float(k_nom[i]))
        if not math.isfinite(v):
            v = 0.0
        out.append(min(max(v, 0.0), cap))
    return tuple(out)  # type: ignore[return-value]


def check_trip(pos: Sequence[float], vel: Sequence[float], force: Sequence[float],
               start: Sequence[float], limits: Limits) -> str | None:
    """Return a human-readable trip reason, or None if all is well.

    Trips: hand speed above trip_speed, force above trip_force, hand more than
    BOX_TRIP_MARGIN outside the workspace box, or non-finite readings.
    """
    if not (_finite3(pos) and _finite3(vel) and _finite3(force)):
        return "non-finite state reading"
    speed = math.sqrt(sum(float(v) ** 2 for v in vel))
    if speed > limits.trip_speed:
        return f"speed {speed:.2f} m/s above {limits.trip_speed:.2f} m/s"
    f = math.sqrt(sum(float(v) ** 2 for v in force))
    if f > limits.trip_force:
        return f"force {f:.1f} N above {limits.trip_force:.1f} N"
    for i, (p, s, h) in enumerate(zip(pos, start, limits.box_half_m)):
        out = abs(float(p) - float(s)) - h
        if out > BOX_TRIP_MARGIN:
            return f"hand {out * 100:.1f} cm outside workspace box on axis {'xyz'[i]}"
    return None


# --------------------------------------------------------------------------- Arm

class Arm:
    """Real Flexiv Rizon 4 behind the section 4.3 interface. See the module docstring."""

    limits: Limits
    start_pos: tuple[float, float, float]     # set by home() or start_compliance()

    def __init__(self, serial: str, limits: Limits = Limits(),
                 config_path: str | Path | None = None) -> None:
        self.config = load_config(config_path)
        self.serial = serial
        self.force_sign = self.config.force_sign
        self.reach_axis = self.config.reach_axis
        self.limits = limits_for_reach_axis(limits, self.reach_axis)
        self.start_pos = None  # type: ignore[assignment]
        self.start_quat: tuple[float, float, float, float] | None = None

        self._lock = threading.RLock()          # every RDK call and every mode change
        self._robot: Any = None
        self._rdk: Any = None
        self._k_nom: tuple[float, ...] | None = None
        self._in_cartesian = False
        self._started = False                   # start_compliance() has been called
        self._mode = "idle"
        self._fault: str | None = None
        self._last_target_t = 0.0
        self._gen = 0                           # bumped on hold/start; stale stiffness is dropped

        self._stiff_cv = threading.Condition()  # never held while taking self._lock
        self._stiff_pending: tuple[Vec3, int] | None = None
        self._running = False
        self._threads: list[threading.Thread] = []

    @classmethod
    def from_config(cls, limits: Limits = Limits(), config_path: str | Path | None = None) -> "Arm":
        cfg = load_config(config_path)
        return cls(cfg.serial, limits, config_path)

    # ------------------------------------------------------------------ connection

    def connect(self) -> None:
        """Connect, clear fault, enable, wait operational, read K_x_nom, start worker threads."""
        if "XXXXXX" in self.serial or (self.serial == self.config.serial
                                       and self.config.is_placeholder("serial")):
            raise RuntimeError(f"serial {self.serial!r} is a placeholder; set it in robot/config.json "
                               "from robot/BRINGUP.md")
        for key in ("force_sign", "reach_axis"):
            if self.config.is_placeholder(key):
                warnings.warn(f"robot/config.json '{key}' is still a placeholder; confirm it in K0",
                              stacklevel=2)
        import flexivrdk  # lazy: only the real arm needs the RDK

        robot = flexivrdk.Robot(self.serial)
        if robot.fault():
            robot.ClearFault()
            if robot.fault():
                raise RuntimeError("robot fault could not be cleared; see robot/RUNBOOK.md")
        robot.Enable()
        deadline = time.monotonic() + 30.0
        while not robot.operational():
            if time.monotonic() > deadline:
                raise RuntimeError("robot did not become operational within 30 s (e-stop released?)")
            time.sleep(0.1)
        self._attach(robot, flexivrdk, tuple(robot.info().K_x_nom))

    def _attach(self, robot: Any, rdk: Any, k_nom: Sequence[float]) -> None:
        """Wire an RDK robot (or a test double) and start the worker threads."""
        k_nom = tuple(float(v) for v in k_nom)
        if len(k_nom) != 6:
            raise RuntimeError(f"K_x_nom should have 6 values, got {k_nom}")
        if any(self.limits.k_max > k for k in k_nom[:3]):
            warnings.warn(f"k_max {self.limits.k_max} exceeds K_x_nom {k_nom[:3]}; "
                          "stiffness will be capped at K_x_nom", stacklevel=2)
        with self._lock:
            self._robot, self._rdk, self._k_nom = robot, rdk, k_nom
            self._mode, self._fault = "idle", None
        self._running = True
        self._threads = [
            threading.Thread(target=self._stiffness_worker, name="arm-stiffness", daemon=True),
            threading.Thread(target=self._watchdog_worker, name="arm-watchdog", daemon=True),
        ]
        for th in self._threads:
            th.start()

    def _require_connected(self) -> None:
        if self._robot is None:
            raise RuntimeError("Arm is not connected; call connect() first")

    # ------------------------------------------------------------------ RDK wrappers (call with lock held)

    def _read(self) -> tuple[Vec3, tuple[float, float, float, float], Vec3, Vec3, tuple[float, ...]]:
        s = self._robot.states()
        tcp = [float(v) for v in s.tcp_pose]
        vel = tuple(float(v) for v in list(s.tcp_vel)[:3])
        w = [float(v) for v in list(s.ext_wrench_in_world)[:3]]
        force = tuple(self.force_sign * v for v in w)
        return (tuple(tcp[:3]), tuple(tcp[3:7]), vel, force,  # type: ignore[return-value]
                tuple(float(v) for v in s.q))

    def _send_pose(self, pos: Sequence[float], quat: Sequence[float]) -> None:
        lim = self.limits
        self._robot.SendCartesianMotionForce(
            [*map(float, pos), *map(float, quat)], [0.0] * 6, [0.0] * 6,
            lim.max_linear_vel, MAX_ANGULAR_VEL, lim.max_linear_acc, MAX_ANGULAR_ACC)

    def _set_impedance(self, k3: Sequence[float]) -> None:
        k = clamp_stiffness(k3, self.limits, self._k_nom)
        assert self._k_nom is not None
        self._robot.SetCartesianImpedance([*k, *self._k_nom[3:6]])  # rotation stays nominal

    def _enter_cartesian(self) -> None:
        if not self._in_cartesian:
            self._robot.SwitchMode(self._rdk.Mode.NRT_CARTESIAN_MOTION_FORCE)
            self._in_cartesian = True
        lim = self.limits
        self._robot.SetMaxContactWrench([lim.max_contact_n] * 3 + [lim.max_contact_nm] * 3)

    def _drop_pending_stiffness(self) -> None:
        with self._stiff_cv:
            self._stiff_pending = None

    # ------------------------------------------------------------------ setup moves

    def zero_force(self) -> None:
        """ZeroFTSensor primitive. Nothing may touch the arm. Leaves mode "idle"."""
        self._require_connected()
        with self._lock:
            self._gen += 1
            self._drop_pending_stiffness()
            self._mode = "idle"
            self._in_cartesian = False
            self._robot.SwitchMode(self._rdk.Mode.NRT_PRIMITIVE_EXECUTION)
            self._robot.ExecutePrimitive("ZeroFTSensor", dict())
        deadline = time.monotonic() + 15.0
        while True:
            with self._lock:
                done = bool(self._robot.primitive_states().get("terminated", False))
            if done:
                return
            if time.monotonic() > deadline:
                raise RuntimeError("ZeroFTSensor did not terminate within 15 s")
            time.sleep(0.05)

    def home(self) -> None:
        """Slow straight-line move to the start pose from robot/config.json. Nobody holding. Blocking.

        No move primitive has been confirmed with the technician, so this ramps the
        Cartesian target at HOME_SPEED (0.05 m/s) at nominal stiffness.
        """
        self._require_connected()
        if self.config.is_placeholder("start_pose"):
            raise RuntimeError("start_pose in robot/config.json is a placeholder; record it in K0/K4 first")
        goal_pos = self.config.start_tcp_pose[:3]
        goal_quat = _normalize(self.config.start_tcp_pose[3:7])
        with self._lock:
            self._gen += 1
            self._drop_pending_stiffness()
            self._mode = "idle"
            self._enter_cartesian()
            assert self._k_nom is not None
            self._robot.SetCartesianImpedance(list(self._k_nom))
            p0, q0, *_ = self._read()
        dist = math.dist(p0, goal_pos)
        if dist > HOME_MAX_DISTANCE:
            raise RuntimeError(f"start pose is {dist:.2f} m away; jog closer before home()")
        if _dot(q0, goal_quat) < 0:  # take the short way round
            goal_quat = tuple(-c for c in goal_quat)
        n = max(1, math.ceil(dist / (HOME_SPEED * TICK_S)))
        n = max(n, 200)  # at least 2 s so orientation changes are slow too
        for i in range(1, n + 1):
            a = i / n
            pos = [p + (g - p) * a for p, g in zip(p0, goal_pos)]
            quat = _normalize([c + (g - c) * a for c, g in zip(q0, goal_quat)])
            with self._lock:
                if self._robot.fault():
                    self._mode, self._fault = "fault", "robot fault during home()"
                    raise RuntimeError(self._fault)
                self._send_pose(pos, quat)
            time.sleep(TICK_S)
        time.sleep(1.0)
        with self._lock:
            p_end, *_ = self._read()
        err = math.dist(p_end, goal_pos)
        if err > 0.02:
            raise RuntimeError(f"home() ended {err * 100:.1f} cm from the start pose")
        self.start_pos = tuple(float(v) for v in goal_pos)  # type: ignore[assignment]
        self.start_quat = tuple(goal_quat)  # type: ignore[assignment]

    def start_compliance(self) -> None:
        """Enter Cartesian mode holding the current pose at k_hold; records start_pos.

        start_pos (the centre of the workspace box) is taken from home() if it ran, else
        from the current hand position on the first call. Calling again after a trip
        re-arms with the same box. Orientation is locked to start_quat.
        """
        self._require_connected()
        with self._lock:
            self._gen += 1
            self._drop_pending_stiffness()
            self._enter_cartesian()
            pos, quat, *_ = self._read()
            if self.start_pos is None:
                self.start_pos = pos
            if self.start_quat is None:
                self.start_quat = quat
            self._set_impedance((self.limits.k_hold,) * 3)
            self._send_pose(pos, self.start_quat)
            self._last_target_t = time.monotonic()
            self._fault = None
            self._mode = "compliant"
            self._started = True

    # ------------------------------------------------------------------ live commands

    def _check_commandable(self, what: str) -> bool:
        if not self._started:
            raise RuntimeError(f"{what}() before start_compliance()")
        return self._mode == "compliant"

    def set_stiffness(self, kx: float, ky: float, kz: float) -> None:
        """N/m per base axis, each clamped to [0, k_max]. Returns immediately; a worker
        applies the latest value (the RDK call blocks). Ignored unless compliant."""
        if not self._check_commandable("set_stiffness"):
            return
        k = clamp_stiffness((kx, ky, kz), self.limits, self._k_nom)
        with self._stiff_cv:
            self._stiff_pending = (k, self._gen)
            self._stiff_cv.notify()

    def set_target(self, pos: tuple[float, float, float]) -> None:
        """Clamped to the workspace box, then to max_lead_m from the current hand position.
        Orientation is always the start orientation. Feeds the watchdog. Ignored unless compliant."""
        if not self._check_commandable("set_target"):
            return
        with self._lock:
            if self._mode != "compliant":
                return
            hand, *_ = self._read()
            target = clamp_target(pos, hand, self.start_pos, self.limits)
            self._send_pose(target, self.start_quat)  # type: ignore[arg-type]
            self._last_target_t = time.monotonic()

    def get_state(self) -> ArmState:
        """Fresh state. While compliant, also runs the trip checks (speed, force, box)."""
        self._require_connected()
        with self._lock:
            pos, quat, vel, force, q = self._read()
            if self._robot.fault():
                if self._mode != "fault":
                    self._gen += 1
                    self._drop_pending_stiffness()
                self._mode = "fault"
                self._fault = self._fault or "robot reported a fault"
            elif self._mode == "compliant":
                reason = check_trip(pos, vel, force, self.start_pos, self.limits)
                if reason is not None:
                    self._trip(reason)
            return ArmState(time.monotonic(), pos, quat, vel, force, q, self._mode, self._fault)

    # ------------------------------------------------------------------ stops

    def _trip(self, reason: str) -> None:
        with self._lock:
            self._fault = reason
            self._hold_locked()

    def _hold_locked(self) -> None:
        self._gen += 1
        self._drop_pending_stiffness()
        if self._robot is not None and self._in_cartesian:
            try:
                pos, quat, *_ = self._read()
                self._set_impedance((self.limits.k_hold,) * 3)
                self._send_pose(pos, self.start_quat or quat)
            except Exception as exc:  # hold failed: hard stop is the fallback
                try:
                    self._robot.Stop()
                finally:
                    self._in_cartesian = False
                    self._mode, self._fault = "fault", f"hold failed: {exc!r}"
                raise
        self._mode = "hold"

    def hold(self) -> None:
        """Soft stop: target = current position, k_hold on all axes, mode "hold"."""
        with self._lock:
            self._hold_locked()

    def stop(self) -> None:
        """Hard stop: robot.Stop(), mode "idle"."""
        with self._lock:
            self._gen += 1
            self._drop_pending_stiffness()
            if self._robot is not None:
                self._robot.Stop()
            self._in_cartesian = False
            self._mode = "idle"

    def close(self) -> None:
        """Hold, restore nominal stiffness (it persists on the robot), stop, end worker threads."""
        try:
            if self._robot is not None and self._in_cartesian:
                with self._lock:
                    self._hold_locked()
                    assert self._k_nom is not None
                    self._robot.SetCartesianImpedance(list(self._k_nom))
        finally:
            try:
                self.stop()
            finally:
                self._running = False
                with self._stiff_cv:
                    self._stiff_cv.notify_all()
                for th in self._threads:
                    if th is not threading.current_thread():
                        th.join(timeout=1.0)
                self._threads = []

    # ------------------------------------------------------------------ workers

    def _stiffness_worker(self) -> None:
        while self._running:
            with self._stiff_cv:
                while self._running and self._stiff_pending is None:
                    self._stiff_cv.wait(timeout=0.1)
                item, self._stiff_pending = self._stiff_pending, None
            if item is None:
                continue
            k, gen = item
            try:
                with self._lock:
                    if gen == self._gen and self._mode == "compliant":
                        self._set_impedance(k)
            except Exception as exc:
                try:
                    self._trip(f"SetCartesianImpedance failed: {exc!r}")
                except Exception:
                    pass

    def _watchdog_worker(self) -> None:
        while self._running:
            time.sleep(0.02)
            if self._mode != "compliant":
                continue
            age = time.monotonic() - self._last_target_t
            if age > self.limits.watchdog_s:
                try:
                    with self._lock:
                        # re-check under the lock: a set_target may have just landed
                        age = time.monotonic() - self._last_target_t
                        if self._mode == "compliant" and age > self.limits.watchdog_s:
                            self._trip(f"watchdog: no set_target for {age:.2f} s")
                except Exception:
                    pass


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _normalize(q: Sequence[float]) -> tuple[float, float, float, float]:
    n = math.sqrt(_dot(q, q))
    if n < 1e-9:
        raise ValueError("zero quaternion")
    return tuple(float(c) / n for c in q)  # type: ignore[return-value]
