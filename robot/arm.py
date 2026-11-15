"""robot/arm.py: the only code in the repo that talks to the Flexiv Rizon 4.

Implements the frozen interface of context/MASTER_PLAN.md section 4.3 (package K1).

The arm runs its own Cartesian impedance controller (NRT_CARTESIAN_MOTION_FORCE).
Python only streams target points and, a few times per rep, per-axis stiffness.
Every safety clamp lives in the pure helpers at the top of this file
(clamp_target, clamp_stiffness, check_trip) so they are testable with no robot.

`flexivrdk` is imported lazily inside Arm.connect(), so importing this module and
running robot/tests/test_arm_offline.py works on any machine.

STIFFNESS FRAME (measured on the arm, 15 Nov): the robot applies the three translational stiffness
values of SetCartesianImpedance along the TOOL (TCP) axes, not the base axes. set_stiffness() passes
its three values through unchanged, so they are tool-axis values. A caller that wants one stiffness
along the reach and another across it must use Arm.reach_stiffness() / tool_stiffness_for_reach().
Targets, positions, forces, the workspace box and every clamp are in the base frame as before.

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


# Test profile: only for isometric pushes (strength test, comfortable-push calibration), switched on with
# Arm.set_test_limits(True). Everything not listed here stays as in the default profile.
TEST_K_MAX = 1500.0         # N/m: holds the handle against 60 N within about 4 cm (60 / 1500), inside the 5 cm lead
TEST_MAX_CONTACT_N = 65.0   # robot-side contact limit, above the 60 N a test may read
TEST_TRIP_FORCE = 75.0      # our own force trip


def isometric_limits(base: Limits) -> Limits:
    """The test profile derived from a default profile."""
    return replace(base, k_max=TEST_K_MAX, max_contact_n=TEST_MAX_CONTACT_N, trip_force=TEST_TRIP_FORCE)


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


# --------------------------------------------------------------------------- stiffness frame (tool axes)

K_TOOL_MIN = 20.0   # N/m: floor for the corrected tool-axis value (same floor as software/simple.py)


@dataclass(frozen=True)
class ToolStiffness:
    """Result of tool_stiffness_for_reach()."""
    k: tuple[float, float, float]           # what to pass to set_stiffness(): N/m along tool x, y, z
    tool_axis: int                          # 0, 1 or 2: the tool axis that lies closest to the reach axis
    angle_deg: float                        # angle between that tool axis and the reach axis
    k_base: tuple[float, float, float]      # stiffness that results along base x, y, z (diagonal terms)
    k_reach: float                          # stiffness that results along the reach axis
    clipped: bool                           # True: the corrected value hit a bound, k_reach is not what was asked


def _rotation(quat: Sequence[float]) -> list[list[float]]:
    """Rotation matrix of a quaternion (qw, qx, qy, qz): column j is tool axis j in the base frame."""
    w, x, y, z = _normalize(quat)
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def base_stiffness(k_tool: Sequence[float], quat: Sequence[float]) -> Vec3:
    """Stiffness along base x, y, z that results from three tool-axis values at orientation `quat`
    (the diagonal of R diag(k) R^T). With a tilted tool there are also cross terms between base axes:
    a push along one base axis is answered with a small sideways force as well."""
    R = _rotation(quat)
    return tuple(sum(R[i][j] ** 2 * float(k_tool[j]) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def tool_stiffness_for_reach(k_reach: float, k_across: float, quat: Sequence[float], reach_axis: int,
                             k_max: float = Limits().k_max, k_min: float = K_TOOL_MIN) -> ToolStiffness:
    """Tool-axis stiffness values that give `k_reach` along base axis `reach_axis` and `k_across` on the
    other two tool axes, at orientation `quat` (qw, qx, qy, qz).

    Same rule as software/simple.py BandEngine._k_vector (which was tried on the arm): w[j] is the share of
    tool axis j along the reach (the squared component, the three sum to 1). The tool axis with the largest
    share gets (k_reach - k_across * (1 - w)) / w, so that the stiffness along the reach comes out as
    k_reach; the other two get k_across. The corrected value is clipped to [k_min, k_max]; if it was,
    `clipped` is True and `k_reach` in the result is what the reach axis really gets.

    Meant for a tool axis within a few degrees of the reach axis (11 degrees at the 15 Nov start pose).
    At large angles (45 degrees is the worst case) no single tool axis lies along the reach, the correction
    clips, and the across directions get a mix: read `angle_deg` and `k_base` before trusting the result.
    """
    if reach_axis not in (0, 1, 2):
        raise ValueError(f"reach_axis must be 0, 1 or 2, got {reach_axis}")
    k_reach, k_across = float(k_reach), float(k_across)
    if not (math.isfinite(k_reach) and math.isfinite(k_across)) or k_reach < 0 or k_across < 0:
        raise ValueError(f"stiffness must be finite and not negative, got {k_reach}, {k_across}")
    R = _rotation(quat)
    w = [R[reach_axis][j] ** 2 for j in range(3)]
    i = max(range(3), key=lambda j: w[j])
    want = (k_reach - k_across * (1.0 - w[i])) / w[i]
    got = min(max(want, k_min), k_max)
    k = [k_across] * 3
    k[i] = got
    k_base = base_stiffness(k, quat)
    return ToolStiffness(k=tuple(k), tool_axis=i,  # type: ignore[arg-type]
                         angle_deg=math.degrees(math.acos(min(1.0, math.sqrt(w[i])))),
                         k_base=k_base, k_reach=k_base[reach_axis], clipped=abs(got - want) > 1e-9)


# --------------------------------------------------------------------------- Arm

class HomeInterrupted(RuntimeError):
    """home() was ended early by hold(), stop(), a trip or another mode change."""


class Arm:
    """Real Flexiv Rizon 4 behind the section 4.3 interface. See the module docstring."""

    start_pos: tuple[float, float, float]     # set by home() or start_compliance()
    stiffness_frame = "tool"                  # set_stiffness() values act along the tool axes (software.sim_arm: base)

    def __init__(self, serial: str, limits: Limits = Limits(),
                 config_path: str | Path | None = None) -> None:
        self.config = load_config(config_path)
        self.serial = serial
        self.force_sign = self.config.force_sign
        self.reach_axis = self.config.reach_axis
        self._test_limits_on = False
        self.limits = limits_for_reach_axis(limits, self.reach_axis)   # the default profile (see the property)
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
        self._home_gen: int | None = None       # value of _gen while home() is streaming, else None

        self._stiff_cv = threading.Condition()  # never held while taking self._lock
        self._stiff_pending: tuple[Vec3, int] | None = None
        self._running = False
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------------ limits: default profile and test profile

    @property
    def limits(self) -> Limits:
        """The limits in force now: the default profile, or the test profile while set_test_limits(True) is on."""
        return self._limits_test if self._test_limits_on else self._limits_default

    @limits.setter
    def limits(self, value: Limits) -> None:
        self._limits_default = value
        self._limits_test = isometric_limits(value)

    @property
    def test_limits_on(self) -> bool:
        return self._test_limits_on

    def set_test_limits(self, on: bool) -> None:
        """Switch to the test profile for an isometric push (k_max 1500 N/m, contact 65 N, force trip 75 N),
        or back to the default profile. Call it after start_compliance(): start_compliance(), hold(), stop(),
        close(), home(), zero_force() and every trip put the default profile back by themselves.
        The robot's contact limit is re-sent whenever the profile changes. Switching off while compliant also
        drops the stiffness to k_hold, so nothing above the default cap stays on the robot."""
        with self._lock:
            on = bool(on)
            if on == self._test_limits_on:
                return
            if on:
                self._require_connected()
            self._test_limits_on = on
            if self._robot is not None and self._in_cartesian:
                self._send_contact_limit()
                if not on and self._mode == "compliant":
                    self._gen += 1
                    self._drop_pending_stiffness()
                    self._set_impedance((self.limits.k_hold,) * 3)

    def _default_limits_locked(self) -> None:
        """Back to the default profile (lock held). Re-sends the contact limit if the robot is in Cartesian mode."""
        if self._test_limits_on:
            self._test_limits_on = False
            if self._robot is not None and self._in_cartesian:
                self._send_contact_limit()

    def _send_contact_limit(self) -> None:
        lim = self.limits
        self._robot.SetMaxContactWrench([lim.max_contact_n] * 3 + [lim.max_contact_nm] * 3)

    @classmethod
    def from_config(cls, limits: Limits = Limits(), config_path: str | Path | None = None) -> "Arm":
        cfg = load_config(config_path)
        return cls(cfg.serial, limits, config_path)

    # ------------------------------------------------------------------ connection

    def connect(self) -> None:
        """Connect, make sure the robot is operational, read K_x_nom, start worker threads.

        This Rizon 4 comes up already enabled in Auto (Remote) mode. If operational() is
        already True, connect() calls neither ClearFault() nor Enable() (same rule as
        server/hw/checked_arm.py); a robot that is operational but reports a fault is refused.
        Only a robot that is not yet operational is un-faulted and enabled here.
        """
        if "XXXXXX" in self.serial or (self.serial == self.config.serial
                                       and self.config.is_placeholder("serial")):
            raise RuntimeError(f"serial {self.serial!r} is a placeholder; set it in robot/config.json "
                               "(see context/BRINGUP_FINDINGS.md)")
        for key in ("force_sign", "reach_axis"):
            if self.config.is_placeholder(key):
                warnings.warn(f"robot/config.json '{key}' is still a placeholder; confirm it in K0",
                              stacklevel=2)
        import flexivrdk  # lazy: only the real arm needs the RDK

        robot = flexivrdk.Robot(self.serial)
        if robot.operational():
            # Already live (normal after power-on in Auto/Remote mode): change nothing.
            if robot.fault():
                raise RuntimeError("robot is operational but reports a fault; clear it with "
                                   "robot/recover.py (see robot/RUNBOOK.md), then connect again")
        else:
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
            [*map(float, pos), *map(float, quat)], [0.0] * 6,
            lim.max_linear_vel, MAX_ANGULAR_VEL, lim.max_linear_acc, MAX_ANGULAR_ACC)

    def _set_impedance(self, k3: Sequence[float]) -> None:
        k = clamp_stiffness(k3, self.limits, self._k_nom)
        assert self._k_nom is not None
        self._robot.SetCartesianImpedance([*k, *self._k_nom[3:6]])  # rotation stays nominal

    def _enter_cartesian(self) -> None:
        if not self._in_cartesian:
            self._robot.SwitchMode(self._rdk.Mode.NRT_CARTESIAN_MOTION_FORCE)
            self._in_cartesian = True
        self._send_contact_limit()

    def _drop_pending_stiffness(self) -> None:
        with self._stiff_cv:
            self._stiff_pending = None

    # ------------------------------------------------------------------ setup moves

    def zero_force(self) -> None:
        """ZeroFTSensor primitive. Nothing may touch the arm. Leaves mode "idle"."""
        self._require_connected()
        with self._lock:
            self._default_limits_locked()
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

        Interruptible from another thread: hold() or stop() (or a trip or fault) ends the move
        before the next target is sent, and home() raises HomeInterrupted. After hold() the arm
        holds where it is at k_hold, mode "hold"; after stop() the robot is stopped, mode "idle".
        start_pos is not updated by an interrupted home.
        """
        self._require_connected()
        if self.config.is_placeholder("start_pose"):
            raise RuntimeError("start_pose in robot/config.json is a placeholder; record it in K0/K4 first")
        goal_pos = self.config.start_tcp_pose[:3]
        goal_quat = self._ramp_to(goal_pos, _normalize(self.config.start_tcp_pose[3:7]), "home()", "start pose")
        self.start_pos = tuple(float(v) for v in goal_pos)  # type: ignore[assignment]
        self.start_quat = tuple(goal_quat)  # type: ignore[assignment]

    def move_to(self, pos: Sequence[float]) -> None:
        """Slow straight-line move of the handle to `pos` (base frame). Nobody holding. Blocking.

        The same ramp as home(): HOME_SPEED (0.05 m/s), nominal stiffness, interruptible by hold() or
        stop() from another thread (raises HomeInterrupted), leaves mode "idle". The orientation is the
        one the arm holds (start_quat; the current one if there is none yet). `pos` must lie inside the
        workspace box around the start pose (start_pos; the start pose from robot/config.json before
        start_pos is set, which then becomes start_pos). start_pos is not moved: the box stays where it is.
        """
        self._require_connected()
        goal = tuple(float(v) for v in pos)
        if not _finite3(goal):
            raise ValueError(f"move_to() needs 3 finite numbers, got {pos!r}")
        ref = self.start_pos
        if ref is None:
            if self.config.is_placeholder("start_pose"):
                raise RuntimeError("move_to() before the start pose is known: home() or start_compliance() first")
            ref = tuple(float(v) for v in self.config.start_tcp_pose[:3])
        for i, (g, r, h) in enumerate(zip(goal, ref, self.limits.box_half_m)):
            if abs(g - r) > h + 1e-9:
                raise ValueError(f"move_to() goal is {abs(g - r) * 100:.1f} cm from the start pose on axis "
                                 f"{'xyz'[i]}, outside the workspace box ({h * 100:.0f} cm)")
        quat = self._ramp_to(goal, self.start_quat, "move_to()", "goal")
        if self.start_pos is None:
            self.start_pos = ref  # type: ignore[assignment]
        if self.start_quat is None:
            self.start_quat = tuple(quat)  # type: ignore[assignment]

    def _ramp_to(self, goal_pos: Sequence[float], goal_quat: Sequence[float] | None, what: str,
                 name: str) -> tuple[float, ...]:
        """The move behind home() and move_to(). `goal_quat` None keeps the orientation the arm has now.
        Returns the goal orientation used."""
        with self._lock:
            self._test_limits_on = False     # _enter_cartesian() below sends the default contact limit
            self._gen += 1
            self._drop_pending_stiffness()
            self._mode = "idle"
            self._enter_cartesian()
            assert self._k_nom is not None
            self._robot.SetCartesianImpedance(list(self._k_nom))
            p0, q0, *_ = self._read()
            dist = math.dist(p0, goal_pos)
            if dist > HOME_MAX_DISTANCE:
                raise RuntimeError(f"{name} is {dist:.2f} m away; jog closer before {what}")
            if goal_quat is None:
                goal_quat = q0
            # From here until the move ends, any hold(), stop(), trip, fault or other mode change
            # bumps _gen. The loop below checks that under the lock before every target it sends.
            my_gen = self._home_gen = self._gen
        if _dot(q0, goal_quat) < 0:  # take the short way round
            goal_quat = tuple(-c for c in goal_quat)
        n = max(1, math.ceil(dist / (HOME_SPEED * TICK_S)))
        n = max(n, 200)  # at least 2 s so orientation changes are slow too
        settle = round(1.0 / TICK_S)
        try:
            for i in range(1, n + settle + 1):
                with self._lock:
                    if self._gen != my_gen:     # checked and sent under one lock: nothing is streamed after a hold
                        raise HomeInterrupted(f"{what} interrupted after {min(i - 1, n)} of {n} steps; "
                                              f"arm mode is {self._mode!r}")
                    if self._robot.fault():
                        self._mode, self._fault = "fault", f"robot fault during {what}"
                        raise RuntimeError(self._fault)
                    if i <= n:                  # after the ramp: 1 s to settle, still interruptible
                        a = i / n
                        pos = [p + (g - p) * a for p, g in zip(p0, goal_pos)]
                        quat = _normalize([c + (g - c) * a for c, g in zip(q0, goal_quat)])
                        self._send_pose(pos, quat)
                time.sleep(TICK_S)
        finally:
            with self._lock:
                if self._home_gen == my_gen:
                    self._home_gen = None
        with self._lock:
            p_end, *_ = self._read()
        err = math.dist(p_end, goal_pos)
        if err > 0.02:
            raise RuntimeError(f"{what} ended {err * 100:.1f} cm from the {name}")
        return tuple(goal_quat)

    def start_compliance(self) -> None:
        """Enter Cartesian mode holding the current pose at k_hold; records start_pos.

        start_pos (the centre of the workspace box) is taken from home() if it ran, else
        from the current hand position on the first call. Calling again after a trip
        re-arms with the same box. Orientation is locked to start_quat.
        """
        self._require_connected()
        with self._lock:
            self._test_limits_on = False     # always starts in the default profile; _enter_cartesian() sends its contact limit
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
        """N/m along the TOOL (TCP) x, y, z axes, NOT the base axes, each clamped to [0, k_max].
        Returns immediately; a worker applies the latest value (the RDK call blocks). Ignored unless compliant.

        Measured on the arm on 15 Nov: with (200, 500, 500) at the start pose (flange down, tool y about
        11 degrees from base -x) the push direction along base x had 480 to 500 N/m, not 200. Three equal
        values are the same in any frame. For different values along and across the reach use
        `set_stiffness(*arm.reach_stiffness(k_reach, k_across).k)`. The parameter names are kept for the
        callers that pass them by keyword; read them as tool x, y, z."""
        if not self._check_commandable("set_stiffness"):
            return
        k = clamp_stiffness((kx, ky, kz), self.limits, self._k_nom)
        with self._stiff_cv:
            self._stiff_pending = (k, self._gen)
            self._stiff_cv.notify()

    def reach_stiffness(self, k_reach: float, k_across: float) -> ToolStiffness:
        """What to pass to set_stiffness() for `k_reach` N/m along the configured reach axis (base frame) and
        `k_across` across it, at the orientation the arm holds (start_quat; the current orientation before
        start_compliance()). Sends nothing. The result carries the angle between the reach axis and the
        tool axis used, and the stiffness each base axis ends up with. See tool_stiffness_for_reach()."""
        quat = self.start_quat
        if quat is None:
            self._require_connected()
            with self._lock:
                _, quat, *_ = self._read()
        return tool_stiffness_for_reach(k_reach, k_across, quat, self.reach_axis, k_max=self.limits.k_max)

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
        homing = self._home_gen is not None and self._home_gen == self._gen
        try:
            self._default_limits_locked()     # hold, trip, close: back to the default profile first
        except Exception:
            pass                              # the hold below still runs; its own failure path stops the robot
        self._gen += 1                          # also ends a home() in progress (it checks _gen every tick)
        self._drop_pending_stiffness()
        if self._robot is not None and self._in_cartesian:
            try:
                pos, quat, *_ = self._read()
                self._set_impedance((self.limits.k_hold,) * 3)
                # Mid-home the flange may still be turning towards the start orientation: hold it as it is.
                self._send_pose(pos, quat if homing else (self.start_quat or quat))
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
            self._test_limits_on = False     # the default contact limit is sent again by the next _enter_cartesian()
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
