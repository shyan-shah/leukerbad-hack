"""Offline tests for robot/arm.py (package K1). No robot and no flexivrdk needed.

Run: python -m pytest robot/tests/test_arm_offline.py -q
"""

import json
import math
import random
import sys
import time
from types import SimpleNamespace

import pytest

from robot.arm import (
    Arm, ArmState, Limits, check_trip, clamp_stiffness, clamp_target, limits_for_reach_axis,
    load_config,
)

LIM = Limits()
START = (0.45, 0.0, 0.30)


# --------------------------------------------------------------------------- test double

class FakeRobot:
    """Minimal stand-in for flexivrdk.Robot: records calls, reports a settable state."""

    def __init__(self, pos=START):
        self.pos = list(pos)
        self.quat = [0.0, 0.0, 1.0, 0.0]
        self.vel = [0.0] * 6
        self.wrench = [0.0] * 6
        self.is_fault = False
        self.calls = []

    def states(self):
        return SimpleNamespace(tcp_pose=self.pos + self.quat, tcp_vel=self.vel,
                               ext_wrench_in_world=self.wrench, q=[0.0] * 7)

    def fault(self):
        return self.is_fault

    def __getattr__(self, name):  # SwitchMode, SendCartesianMotionForce, SetCartesianImpedance, ...
        if name[0].isupper():
            return lambda *a, **k: self.calls.append((name, a))
        raise AttributeError(name)

    def count(self, name):
        return sum(1 for n, _ in self.calls if n == name)

    def last(self, name):
        return [a for n, a in self.calls if n == name][-1]


FAKE_RDK = SimpleNamespace(Mode=SimpleNamespace(NRT_CARTESIAN_MOTION_FORCE="cart",
                                                NRT_PRIMITIVE_EXECUTION="prim"))
K_NOM = (10000.0, 10000.0, 10000.0, 1500.0, 1500.0, 1500.0)


@pytest.fixture
def arm():
    a = Arm("Rizon4-TEST01")
    robot = FakeRobot()
    a._attach(robot, FAKE_RDK, K_NOM)
    yield a, robot
    a.close()


# --------------------------------------------------------------------------- module hygiene

def test_import_does_not_load_flexivrdk():
    assert "flexivrdk" not in sys.modules


def test_config_loads_and_is_marked_placeholder():
    cfg = load_config()
    for key in ("serial", "force_sign", "start_pose", "reach_axis"):
        assert hasattr(cfg, {"start_pose": "start_tcp_pose"}.get(key, key))
    assert cfg.force_sign in (1.0, -1.0)
    assert cfg.reach_axis in (0, 1)
    assert len(cfg.start_tcp_pose) == 7


def test_connect_refuses_placeholder_serial():
    a = Arm.from_config()
    if a.config.is_placeholder("serial"):
        with pytest.raises(RuntimeError, match="placeholder"):
            a.connect()


def test_reach_axis_y_lays_box_along_y():
    lim = limits_for_reach_axis(LIM, 1)
    assert lim.box_half_m == (0.10, 0.35, 0.10)


def test_force_sign_from_config(tmp_path):
    raw = json.loads((__import__("robot.arm", fromlist=["CONFIG_PATH"]).CONFIG_PATH)
                     .read_text(encoding="utf-8"))
    raw["force_sign"] = -1
    p = tmp_path / "config.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    a = Arm("Rizon4-TEST01", config_path=p)
    robot = FakeRobot()
    robot.wrench = [-5.0, 0, 0, 0, 0, 0]
    a._attach(robot, FAKE_RDK, K_NOM)
    try:
        assert a.get_state().force[0] == pytest.approx(5.0)
    finally:
        a.close()


# --------------------------------------------------------------------------- connect()

class FakeConnectRobot(FakeRobot):
    """FakeRobot plus the getters connect() uses. Enable() makes it operational."""

    def __init__(self, operational, fault=False, clearable=True):
        super().__init__()
        self.is_operational = operational
        self.is_fault = fault
        self.clearable = clearable

    def operational(self):
        return self.is_operational

    def info(self):
        return SimpleNamespace(K_x_nom=list(K_NOM))

    def ClearFault(self):
        self.calls.append(("ClearFault", ()))
        if self.clearable:
            self.is_fault = False

    def Enable(self):
        self.calls.append(("Enable", ()))
        self.is_operational = True


def _connect_with(monkeypatch, robot):
    """Run Arm.connect() against a fake flexivrdk module that hands out `robot`."""
    fake = SimpleNamespace(Robot=lambda serial: robot, Mode=None)
    monkeypatch.setitem(sys.modules, "flexivrdk", fake)
    a = Arm("Rizon4-TEST01")
    a.connect()
    return a


def test_connect_skips_clearfault_and_enable_when_already_operational(monkeypatch):
    robot = FakeConnectRobot(operational=True)
    a = _connect_with(monkeypatch, robot)
    try:
        assert robot.count("ClearFault") == 0 and robot.count("Enable") == 0
        assert a.get_state().mode == "idle"
        assert a._k_nom == K_NOM
    finally:
        a.close()


def test_connect_refuses_operational_robot_with_fault(monkeypatch):
    robot = FakeConnectRobot(operational=True, fault=True)
    with pytest.raises(RuntimeError, match="fault"):
        _connect_with(monkeypatch, robot)
    assert robot.count("ClearFault") == 0 and robot.count("Enable") == 0


def test_connect_enables_a_robot_that_is_not_operational(monkeypatch):
    robot = FakeConnectRobot(operational=False)
    a = _connect_with(monkeypatch, robot)
    try:
        assert robot.count("Enable") == 1 and robot.count("ClearFault") == 0
    finally:
        a.close()


def test_connect_clears_fault_then_enables_when_not_operational(monkeypatch):
    robot = FakeConnectRobot(operational=False, fault=True)
    a = _connect_with(monkeypatch, robot)
    try:
        assert [n for n, _ in robot.calls if n in ("ClearFault", "Enable")] == ["ClearFault", "Enable"]
    finally:
        a.close()


def test_connect_raises_when_fault_will_not_clear(monkeypatch):
    robot = FakeConnectRobot(operational=False, fault=True, clearable=False)
    with pytest.raises(RuntimeError, match="could not be cleared"):
        _connect_with(monkeypatch, robot)
    assert robot.count("Enable") == 0


# --------------------------------------------------------------------------- pure clamps

def _inside_box(p, start, lim, margin=0.0):
    return all(abs(x - s) <= h - margin + 1e-12 for x, s, h in zip(p, start, lim.box_half_m))


def test_clamp_target_random_1000():
    rng = random.Random(0)
    checked_box = 0
    for _ in range(1000):
        hand = tuple(s + rng.uniform(-1.5 * h, 1.5 * h) for s, h in zip(START, LIM.box_half_m))
        req = tuple(rng.uniform(-2.0, 2.0) for _ in range(3))
        out = clamp_target(req, hand, START, LIM)
        assert math.dist(out, hand) <= LIM.max_lead_m
        if _inside_box(hand, START, LIM, margin=LIM.max_lead_m):
            checked_box += 1
            assert _inside_box(out, START, LIM)
    assert checked_box > 50


def test_clamp_target_small_request_passes_through():
    hand = START
    req = (START[0] + 0.02, START[1], START[2])
    assert clamp_target(req, hand, START, LIM) == pytest.approx(req)


def test_clamp_target_nonfinite_returns_hand():
    assert clamp_target((math.nan, 0, 0), START, START, LIM) == START
    assert clamp_target((math.inf, 0, 0), START, START, LIM) == START


def test_clamp_stiffness_never_exceeds_k_max():
    rng = random.Random(1)
    for _ in range(1000):
        k = tuple(rng.choice([rng.uniform(-1e4, 1e5), math.nan, math.inf, -math.inf]) for _ in range(3))
        for k_nom in (None, K_NOM, (400.0, 400.0, 400.0, 100.0, 100.0, 100.0)):
            out = clamp_stiffness(k, LIM, k_nom)
            cap = LIM.k_max if k_nom is None else min(LIM.k_max, k_nom[0])
            assert all(0.0 <= v <= cap for v in out)
    assert clamp_stiffness((5000, 5000, 5000), LIM) == (600.0, 600.0, 600.0)


# --------------------------------------------------------------------------- trips

def test_check_trip_box_speed_force():
    zero = (0.0, 0.0, 0.0)
    assert check_trip(START, zero, zero, START, LIM) is None
    out3cm = (START[0], START[1] + LIM.box_half_m[1] + 0.03, START[2])
    assert "outside" in check_trip(out3cm, zero, zero, START, LIM)
    out1cm = (START[0], START[1] + LIM.box_half_m[1] + 0.01, START[2])
    assert check_trip(out1cm, zero, zero, START, LIM) is None
    assert "speed" in check_trip(START, (0.5, 0, 0), zero, START, LIM)
    assert "force" in check_trip(START, zero, (0, 0, 45.0), START, LIM)


def test_hand_3cm_outside_box_trips_arm(arm):
    a, robot = arm
    a.start_compliance()
    robot.pos[0] = START[0] + LIM.box_half_m[0] + 0.03
    s = a.get_state()
    assert isinstance(s, ArmState)
    assert s.mode == "hold" and "outside" in s.fault


# --------------------------------------------------------------------------- command rules

def test_set_target_before_start_compliance_raises():
    a = Arm("Rizon4-TEST01")
    with pytest.raises(RuntimeError):
        a.set_target(START)
    with pytest.raises(RuntimeError):
        a.set_stiffness(100, 100, 100)


def test_set_target_before_start_compliance_raises_when_connected(arm):
    a, _ = arm
    with pytest.raises(RuntimeError):
        a.set_target(START)


def test_set_target_is_clamped_and_passes_velocity_limits(arm):
    a, robot = arm
    a.start_compliance()
    a.set_target((START[0] + 0.20, START[1], START[2]))
    pose, wrench, max_lv, max_av, max_la, max_aa = robot.last("SendCartesianMotionForce")
    assert math.dist(pose[:3], START) == pytest.approx(LIM.max_lead_m)
    assert pose[3:] == pytest.approx([0.0, 0.0, 1.0, 0.0])
    assert max_lv == LIM.max_linear_vel and max_la == LIM.max_linear_acc
    assert wrench == [0.0] * 6


def test_stiffness_worker_applies_clamped_value_with_nominal_rotation(arm):
    a, robot = arm
    a.start_compliance()
    a.set_target(START)
    a.set_stiffness(5000, 0, 250)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        k = robot.last("SetCartesianImpedance")[0]
        if k[:3] == [600.0, 0.0, 250.0]:
            break
        a.set_target(START)
        time.sleep(0.01)
    assert k == [600.0, 0.0, 250.0, *K_NOM[3:]]


def test_after_trip_commands_are_ignored(arm):
    a, robot = arm
    a.start_compliance()
    robot.wrench = [0.0, 0.0, 50.0, 0, 0, 0]  # 50 N > 40 N trip
    s = a.get_state()
    assert s.mode == "hold" and "force" in s.fault
    robot.wrench = [0.0] * 6
    time.sleep(0.15)  # let any in-flight stiffness work drain
    n_send = robot.count("SendCartesianMotionForce")
    n_imp = robot.count("SetCartesianImpedance")
    a.set_target((START[0] + 0.03, START[1], START[2]))
    a.set_stiffness(500, 500, 500)
    time.sleep(0.2)
    assert robot.count("SendCartesianMotionForce") == n_send
    assert robot.count("SetCartesianImpedance") == n_imp
    # start_compliance() re-arms
    a.start_compliance()
    assert a.get_state().mode == "compliant" and a.get_state().fault is None
    a.set_target(START)
    assert robot.count("SendCartesianMotionForce") > n_send


def test_watchdog_trips_to_hold(arm):
    a, _ = arm
    a.start_compliance()
    a.set_target(START)
    time.sleep(LIM.watchdog_s + 0.15)
    s = a.get_state()
    assert s.mode == "hold" and "watchdog" in s.fault


def test_close_restores_nominal_stiffness(arm):
    a, robot = arm
    a.start_compliance()
    a.close()
    assert robot.last("SetCartesianImpedance")[0] == list(K_NOM)
    assert robot.calls[-1][0] == "Stop"


# --------------------------------------------------------------------------- home() can be interrupted

HOME_QUAT = (0.0, 0.0, 0.0, 1.0)      # not the fake robot's orientation, so the flange is turning mid-home


def _home_arm(tmp_path, distance_m):
    """Arm on a FakeRobot whose start pose lies `distance_m` along +x from where the hand is."""
    import threading
    from robot.arm import CONFIG_PATH
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["placeholders"] = [k for k in raw.get("placeholders", []) if k != "start_pose"]
    raw["start_pose"] = {"tcp_pose": [START[0] + distance_m, START[1], START[2], *HOME_QUAT], "q": None}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    a = Arm("Rizon4-TEST01", config_path=p)
    robot = FakeRobot()
    a._attach(robot, FAKE_RDK, K_NOM)
    out = {}

    def run():
        try:
            a.home()
            out["result"] = "finished"
        except Exception as e:      # noqa: BLE001 (the test inspects it)
            out["result"] = e
    th = threading.Thread(target=run, daemon=True)
    return a, robot, th, out


def _wait_for_sends(robot, n, timeout=10.0):
    deadline = time.monotonic() + timeout
    while robot.count("SendCartesianMotionForce") < n:
        assert time.monotonic() < deadline, "home() never streamed that many targets"
        time.sleep(0.002)


def test_hold_halfway_through_home_stops_the_stream_and_holds(tmp_path):
    from robot.arm import HomeInterrupted, TICK_S
    a, robot, th, out = _home_arm(tmp_path, 0.20)       # 0.20 m at 0.05 m/s: 400 targets, 4 s
    try:
        th.start()
        _wait_for_sends(robot, 200)                     # halfway
        robot.pos = [START[0] + 0.10, START[1], START[2]]   # where the arm has got to
        a.hold()
        n_after_hold = robot.count("SendCartesianMotionForce")
        th.join(timeout=5 * TICK_S + 0.2)
        assert not th.is_alive(), "home() kept running after hold()"
        assert isinstance(out["result"], HomeInterrupted) and isinstance(out["result"], RuntimeError)
        assert 200 <= n_after_hold < 260                # it was mid-move, not finished
        time.sleep(0.15)
        assert robot.count("SendCartesianMotionForce") == n_after_hold   # nothing streamed after hold()
        assert a.get_state().mode == "hold"
        # the last command is the hold itself: current position and current orientation, at k_hold
        pose = robot.last("SendCartesianMotionForce")[0]
        assert pose[:3] == pytest.approx(robot.pos) and pose[3:7] == pytest.approx(robot.quat)
        assert robot.last("SetCartesianImpedance")[0] == [LIM.k_hold] * 3 + list(K_NOM[3:])
        assert a.start_pos is None                      # an interrupted home does not set the start pose
    finally:
        a.close()


def test_hold_returns_only_after_the_last_home_target(tmp_path):
    """hold() and the home loop share the arm lock, so no home target can follow the hold command."""
    a, robot, th, out = _home_arm(tmp_path, 0.20)
    try:
        th.start()
        _wait_for_sends(robot, 50)
        a.hold()
        th.join(timeout=1.0)
        sends = [args[0] for name, args in robot.calls if name == "SendCartesianMotionForce"]
        assert sends[-1][:3] == pytest.approx(robot.pos)          # the hold, at the (unmoved) fake position
        assert all(s[0] > START[0] for s in sends[:-1])           # everything before it was the ramp
    finally:
        a.close()


def test_stop_during_home_ends_the_move(tmp_path):
    from robot.arm import HomeInterrupted
    a, robot, th, out = _home_arm(tmp_path, 0.20)
    try:
        th.start()
        _wait_for_sends(robot, 100)
        a.stop()
        n = robot.count("SendCartesianMotionForce")
        th.join(timeout=0.5)
        assert not th.is_alive() and isinstance(out["result"], HomeInterrupted)
        time.sleep(0.1)
        assert robot.count("SendCartesianMotionForce") == n
        assert robot.calls[-1][0] == "Stop" and a.get_state().mode == "idle"
    finally:
        a.close()


def test_hold_during_the_settle_second_of_home_is_seen(tmp_path):
    from robot.arm import HomeInterrupted
    a, robot, th, out = _home_arm(tmp_path, 0.0)        # already there: 200 targets, then 1 s to settle
    try:
        th.start()
        _wait_for_sends(robot, 200)
        time.sleep(0.2)                                 # inside the settle second
        a.hold()
        th.join(timeout=0.5)
        assert not th.is_alive() and isinstance(out["result"], HomeInterrupted)
        assert a.get_state().mode == "hold"
    finally:
        a.close()


def test_home_still_completes_and_a_later_hold_uses_the_start_orientation(tmp_path):
    a, robot, th, out = _home_arm(tmp_path, 0.0)
    try:
        th.start()
        th.join(timeout=10)
        assert out["result"] == "finished" and a.start_pos == pytest.approx(START)
        a.hold()                                        # not homing any more: orientation is the start one
        assert robot.last("SendCartesianMotionForce")[0][3:7] == pytest.approx(a.start_quat)
        assert a.get_state().mode == "hold"
    finally:
        a.close()


# --------------------------------------------------------------------------- test-limits profile (isometric pushes)

def _differs(a, b):
    from dataclasses import fields
    return {f.name for f in fields(a) if getattr(a, f.name) != getattr(b, f.name)}


def test_test_profile_changes_only_three_limits_and_default_is_untouched(arm):
    a, robot = arm
    default = a.limits
    assert default == limits_for_reach_axis(LIM, a.reach_axis) and not a.test_limits_on
    a.start_compliance()
    a.set_test_limits(True)
    t = a.limits
    assert a.test_limits_on and (t.k_max, t.max_contact_n, t.trip_force) == (1500.0, 65.0, 75.0)
    assert _differs(t, default) == {"k_max", "max_contact_n", "trip_force"}
    assert t.k_max * t.max_lead_m >= 60.0            # holds 60 N within the 5 cm lead
    a.set_test_limits(False)
    assert a.limits == default and a.limits is default


def test_contact_limit_is_resent_when_the_profile_changes(arm):
    a, robot = arm
    a.set_test_limits(True)                          # not in Cartesian mode yet: nothing to send, and start_compliance resets it
    assert robot.count("SetMaxContactWrench") == 0
    a.start_compliance()
    assert not a.test_limits_on and robot.last("SetMaxContactWrench")[0] == [30.0] * 3 + [5.0] * 3
    n = robot.count("SetMaxContactWrench")
    a.set_test_limits(True)
    assert robot.count("SetMaxContactWrench") == n + 1 and robot.last("SetMaxContactWrench")[0] == [65.0] * 3 + [5.0] * 3
    a.set_test_limits(True)                          # no change, nothing sent
    assert robot.count("SetMaxContactWrench") == n + 1
    a.set_test_limits(False)
    assert robot.last("SetMaxContactWrench")[0] == [30.0] * 3 + [5.0] * 3
    assert robot.last("SetCartesianImpedance")[0] == [LIM.k_hold] * 3 + list(K_NOM[3:])   # nothing above the default cap stays on


def test_test_profile_lifts_the_stiffness_cap_and_the_force_trip(arm):
    a, robot = arm
    a.start_compliance()
    a.set_test_limits(True)
    a.set_stiffness(5000, 5000, 5000)
    time.sleep(0.15)
    assert robot.last("SetCartesianImpedance")[0] == [1500.0] * 3 + list(K_NOM[3:])
    robot.wrench = [60.0, 0, 0, 0, 0, 0]             # over the default trip (40 N), under the test trip (75 N)
    a.set_target(START)
    assert a.get_state().mode == "compliant"
    robot.wrench = [80.0, 0, 0, 0, 0, 0]
    s = a.get_state()
    assert s.mode == "hold" and "force" in s.fault
    assert not a.test_limits_on and a.limits.trip_force == 40.0                     # a trip puts the default back
    assert robot.last("SetMaxContactWrench")[0] == [30.0] * 3 + [5.0] * 3


@pytest.mark.parametrize("how", ["hold", "stop", "start_compliance", "close", "watchdog"])
def test_default_profile_is_restored(arm, how):
    a, robot = arm
    a.start_compliance()
    a.set_test_limits(True)
    a.set_target(START)
    if how == "watchdog":
        time.sleep(LIM.watchdog_s + 0.15)
        assert a.get_state().mode == "hold"
    else:
        getattr(a, how)()
    assert not a.test_limits_on and a.limits.max_contact_n == 30.0 and a.limits.k_max == 600.0
    if how != "stop" and how != "close":             # after a hard stop the limit is sent by the next start_compliance()
        assert robot.last("SetMaxContactWrench")[0] == [30.0] * 3 + [5.0] * 3
    if how in ("stop", "close"):
        a._attach(robot, FAKE_RDK, K_NOM) if how == "close" else None
        a.start_compliance()
        assert robot.last("SetMaxContactWrench")[0] == [30.0] * 3 + [5.0] * 3


def test_default_force_trip_still_40_n_without_the_test_profile(arm):
    a, robot = arm
    a.start_compliance()
    robot.wrench = [45.0, 0, 0, 0, 0, 0]
    assert a.get_state().mode == "hold"


# --------------------------------------------------------------------------- stiffness is applied in the tool frame

def _start_quat():
    return load_config().start_tcp_pose[3:7]      # the real start pose (15 Nov, flange down)


def test_tool_frame_reproduces_the_489_measured_on_the_arm():
    """15 Nov, first hand-on Push: (200, 500, 500) commanded, 480 to 500 N/m measured along base x."""
    from robot.arm import base_stiffness
    kb = base_stiffness((200.0, 500.0, 500.0), _start_quat())
    assert kb[0] == pytest.approx(489.0, abs=1.0)      # along the reach: almost the "wall" value
    assert kb[1] == pytest.approx(211.0, abs=1.0)      # and the 200 landed across it
    assert kb[2] == pytest.approx(500.0, abs=0.5)


def test_tool_stiffness_for_reach_puts_the_value_on_tool_y_with_the_angle_correction():
    from robot.arm import base_stiffness, tool_stiffness_for_reach
    r = tool_stiffness_for_reach(200.0, 500.0, _start_quat(), 0)
    assert r.tool_axis == 1 and r.angle_deg == pytest.approx(11.0, abs=0.5)
    assert r.k[0] == 500.0 and r.k[2] == 500.0
    assert r.k[1] == pytest.approx(189.0, abs=1.0)     # what software/simple.py commands for level 1
    assert r.k_reach == pytest.approx(200.0, abs=1e-6) and not r.clipped
    assert r.k_base == pytest.approx(base_stiffness(r.k, _start_quat()))
    assert r.k_base[1] == pytest.approx(489.0, abs=1.0)        # across the reach: nearly the wall
    for k_reach in (200.0, 300.0, 400.0, 560.0):               # the four Push levels
        assert tool_stiffness_for_reach(k_reach, 500.0, _start_quat(), 0).k_reach == pytest.approx(k_reach, abs=1e-6)


def test_tool_stiffness_matches_shyans_engine_rule():
    """Same numbers as software/simple.py BandEngine._k_vector, written out here so robot/ imports nothing
    from software/: w = R[axis, :] ** 2, i = argmax, k[i] = clip((k_reach - K_WALL * (1 - w[i])) / w[i], 20, 600)."""
    from robot.arm import _rotation, tool_stiffness_for_reach
    q = _start_quat()
    R = _rotation(q)
    for axis in (0, 1):
        w = [R[axis][j] ** 2 for j in range(3)]
        i = max(range(3), key=lambda j: w[j])
        for k_reach in (0.0, 100.0, 200.0, 560.0, 600.0):
            want = [500.0] * 3
            want[i] = min(max((k_reach - 500.0 * (1 - w[i])) / w[i], 20.0), 600.0)
            assert tool_stiffness_for_reach(k_reach, 500.0, q, axis).k == pytest.approx(want)


def test_tool_stiffness_reports_a_clipped_value_and_a_bad_angle():
    from robot.arm import tool_stiffness_for_reach
    q = _start_quat()
    low = tool_stiffness_for_reach(0.0, 500.0, q, 0)           # a free reach axis cannot be had exactly
    assert low.clipped and low.k[1] == 20.0 and low.k_reach == pytest.approx(37.5, abs=1.0)
    high = tool_stiffness_for_reach(600.0, 500.0, q, 0)        # never above k_max
    assert high.clipped and max(high.k) == 600.0 and high.k_reach < 600.0
    s = 2 ** -0.5
    r45 = tool_stiffness_for_reach(200.0, 500.0, (math.cos(math.pi / 8), 0.0, 0.0, math.sin(math.pi / 8)), 0)
    assert r45.angle_deg == pytest.approx(45.0, abs=1e-6) and r45.clipped and r45.k_reach > 250.0
    ident = tool_stiffness_for_reach(200.0, 500.0, (1.0, 0.0, 0.0, 0.0), 1)
    assert ident.k == (500.0, 200.0, 500.0) and ident.angle_deg == pytest.approx(0.0, abs=1e-6)
    assert s > 0
    with pytest.raises(ValueError):
        tool_stiffness_for_reach(float("nan"), 500.0, q, 0)


def test_arm_reach_stiffness_uses_the_held_orientation_and_sends_nothing(arm):
    a, robot = arm
    robot.quat = list(_start_quat())
    assert a.stiffness_frame == "tool"
    a.start_compliance()
    n = robot.count("SetCartesianImpedance")
    r = a.reach_stiffness(200.0, 500.0)
    assert r.tool_axis == 1 and r.k[1] == pytest.approx(189.0, abs=1.0) and r.angle_deg == pytest.approx(11.0, abs=0.5)
    assert robot.count("SetCartesianImpedance") == n
    a.set_stiffness(*r.k)
    time.sleep(0.2)
    assert robot.last("SetCartesianImpedance")[0][:3] == pytest.approx(list(r.k))


def test_set_stiffness_still_passes_its_values_through_unchanged(arm):
    """Existing callers get what they got before: no remapping inside set_stiffness."""
    a, robot = arm
    robot.quat = list(_start_quat())
    a.start_compliance()
    a.set_stiffness(200.0, 500.0, 500.0)
    time.sleep(0.2)
    assert robot.last("SetCartesianImpedance")[0][:3] == [200.0, 500.0, 500.0]


# --------------------------------------------------------------------------- move_to(): home()'s ramp to another point

class FollowingRobot(FakeRobot):
    """A FakeRobot whose hand goes where the last target was sent."""

    def SendCartesianMotionForce(self, pose, *a):
        self.calls.append(("SendCartesianMotionForce", (list(pose), *a)))
        self.pos, self.quat = list(pose[:3]), list(pose[3:7])


def _move_arm(tmp_path):
    from robot.arm import CONFIG_PATH
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["placeholders"] = [k for k in raw.get("placeholders", []) if k != "start_pose"]
    raw["start_pose"] = {"tcp_pose": [*START, 0.0, 0.0, 1.0, 0.0], "q": None}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    a = Arm("Rizon4-TEST01", config_path=p)
    robot = FollowingRobot()
    a._attach(robot, FAKE_RDK, K_NOM)
    return a, robot


def test_move_to_ramps_in_a_straight_line_at_home_speed_and_keeps_the_box(tmp_path):
    from robot.arm import HOME_SPEED, TICK_S
    a, robot = _move_arm(tmp_path)
    try:
        goal = (START[0] - 0.10 if a.reach_axis == 0 else START[0], START[1] - (0.10 if a.reach_axis == 1 else 0.0), START[2])
        a.move_to(goal)
        sends = [args[0] for name, args in robot.calls if name == "SendCartesianMotionForce"]
        assert len(sends) in (200, 201)                                 # 0.10 m at 0.05 m/s, 100 Hz
        steps = [math.dist(p[:3], q[:3]) for p, q in zip(sends, sends[1:])]
        assert 0.99 * HOME_SPEED * TICK_S <= min(steps) and max(steps) <= HOME_SPEED * TICK_S + 1e-9     # never faster
        assert max(steps) == pytest.approx(min(steps), rel=1e-6)        # one continuous move, no stops
        assert sends[-1][:3] == pytest.approx(goal) and all(s[3:7] == pytest.approx([0.0, 0.0, 1.0, 0.0]) for s in sends)
        assert robot.last("SetCartesianImpedance")[0] == list(K_NOM)    # nominal stiffness, as home()
        assert robot.last("SetMaxContactWrench")[0][0] == LIM.max_contact_n
        assert a.get_state().mode == "idle"
        assert a.start_pos == pytest.approx(START)                      # the box stays round the start pose
        a.start_compliance()
        assert a.start_pos == pytest.approx(START) and a.get_state().mode == "compliant"
    finally:
        a.close()


def test_move_to_refuses_a_goal_outside_the_box_and_sends_nothing(tmp_path):
    a, robot = _move_arm(tmp_path)
    try:
        for goal in ((START[0], START[1], START[2] + 0.15), (START[0] + 0.5, START[1] + 0.5, START[2]),
                     (float("nan"), 0.0, 0.3)):
            with pytest.raises(ValueError):
                a.move_to(goal)
        assert robot.count("SendCartesianMotionForce") == 0 and robot.count("SwitchMode") == 0
    finally:
        a.close()


def test_hold_during_move_to_ends_it(tmp_path):
    import threading
    from robot.arm import HomeInterrupted
    a, robot = _move_arm(tmp_path)
    out = {}
    goal = list(START)
    goal[a.reach_axis] += 0.20

    def run():
        try:
            a.move_to(goal)
            out["result"] = "finished"
        except Exception as e:      # noqa: BLE001
            out["result"] = e
    th = threading.Thread(target=run, daemon=True)
    try:
        th.start()
        _wait_for_sends(robot, 100)
        a.hold()
        n = robot.count("SendCartesianMotionForce")
        th.join(timeout=0.5)
        assert not th.is_alive() and isinstance(out["result"], HomeInterrupted) and "move_to()" in str(out["result"])
        time.sleep(0.1)
        assert robot.count("SendCartesianMotionForce") == n and a.get_state().mode == "hold"
        assert 0.04 < abs(robot.pos[a.reach_axis] - START[a.reach_axis]) < 0.08     # held part-way
    finally:
        a.close()
