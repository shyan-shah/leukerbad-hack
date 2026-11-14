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
    pose, wrench, vel, max_lv, max_av, max_la, max_aa = robot.last("SendCartesianMotionForce")
    assert math.dist(pose[:3], START) == pytest.approx(LIM.max_lead_m)
    assert pose[3:] == pytest.approx([0.0, 0.0, 1.0, 0.0])
    assert max_lv == LIM.max_linear_vel and max_la == LIM.max_linear_acc
    assert wrench == [0.0] * 6 and vel == [0.0] * 6


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
