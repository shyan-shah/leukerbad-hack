"""Tests for software/sim_arm.py (package S1)."""

import inspect
import math
import time

import numpy as np
import pytest

from robot.arm import Arm, ArmState, Limits
from software.paths import min_jerk
from software.sim_arm import PASSIVE_LOAD_N, STIFFNESS_LATENCY_S, SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
DT = 0.01
WALL = 500.0

INTERFACE = ["connect", "zero_force", "home", "start_compliance", "set_stiffness",
             "set_target", "get_state", "hold", "stop", "close"]


def make_arm(strength=1.0, present=True, **kw):
    arm = SimArm(SimPatient(strength=strength, present=present), start_pos=START,
                 realtime=False, **kw)
    arm.connect()
    return arm


def run_on_path(arm, seconds, kx=0.0):
    """Engine-like loop: along-reach axis free, walls on y and z, target on the path line
    at the hand's x. Returns the list of states seen."""
    arm.start_compliance()
    arm.set_stiffness(kx, WALL, WALL)
    states = []
    for _ in range(int(round(seconds / DT))):
        st = arm.get_state()
        states.append(st)
        arm.set_target((st.pos[0], START[1], START[2]))
        arm.step(DT)
    return states


# ------------------------------------------------------------------ interface

def test_interface_matches_arm():
    arm = SimArm(SimPatient(), realtime=False)
    for name in INTERFACE:
        assert callable(getattr(arm, name)), name
        sim_params = list(inspect.signature(getattr(SimArm, name)).parameters)
        arm_params = list(inspect.signature(getattr(Arm, name)).parameters)
        assert sim_params == arm_params, name
    assert isinstance(arm.limits, Limits)
    assert arm.start_pos == START
    params = inspect.signature(SimArm).parameters
    positional = [n for n, p in params.items() if p.kind is not p.KEYWORD_ONLY]
    assert positional == ["patient", "limits", "start_pos", "realtime"]   # frozen (4.3)
    extras = [p for p in params.values() if p.kind is p.KEYWORD_ONLY]
    # sensor-error options are keyword-only with defaults, so the frozen call still works
    assert {p.name for p in extras} == {"force_offset", "force_drift_n_per_min",
                                        "force_noise_n", "stiffness_latency_s", "seed",
                                        "empty_force_pose_n_per_m", "empty_force_moving_n",
                                        "empty_force_moving_dir", "friction_n"}
    assert all(p.default is not p.empty for p in extras)


def test_get_state_returns_arm_state():
    arm = make_arm()
    st = arm.get_state()
    assert isinstance(st, ArmState)
    assert st.pos == START and st.vel == (0.0, 0.0, 0.0)
    assert len(st.quat) == 4 and len(st.q) == 7
    assert st.mode == "idle" and st.fault is None


def test_commands_before_start_compliance_raise():
    arm = make_arm()
    with pytest.raises(RuntimeError):
        arm.set_target(START)
    with pytest.raises(RuntimeError):
        arm.set_stiffness(100, 100, 100)


def test_get_state_before_connect_raises():
    arm = SimArm(SimPatient(), realtime=False)
    with pytest.raises(RuntimeError):
        arm.get_state()


def test_step_refused_in_realtime_mode():
    arm = SimArm(SimPatient(), realtime=True)
    with pytest.raises(RuntimeError):
        arm.step(DT)


# ------------------------------------------------------------------ clamps

def test_target_clamped_to_lead_and_box():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    lim = arm.limits
    rng = np.random.default_rng(1)
    for _ in range(500):
        req = np.array(START) + rng.uniform(-1.0, 1.0, size=3)
        arm.set_target(tuple(req))
        hand = np.array(arm.get_state().pos)
        tgt = arm._target
        assert np.linalg.norm(tgt - hand) <= lim.max_lead_m + 1e-12
        assert np.all(np.abs(tgt - np.array(START)) <= np.array(lim.box_half_m) + 1e-12)


def test_target_20cm_away_clamped_to_5cm():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    arm.set_target((START[0] + 0.20, START[1], START[2]))
    assert arm._target[0] == pytest.approx(START[0] + 0.05)


def test_stiffness_clamped_and_delayed():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    k_hold = arm.limits.k_hold
    arm.set_stiffness(5000.0, -10.0, float("nan"))
    assert np.allclose(arm._k, k_hold)           # not applied yet
    for _ in range(int(math.ceil(STIFFNESS_LATENCY_S / DT)) + 1):
        arm.set_target(arm.get_state().pos)
        arm.step(DT)
    assert tuple(arm._k) == (arm.limits.k_max, 0.0, 0.0)


# ------------------------------------------------------------------ physics

def test_strong_patient_moves_at_zero_axis_stiffness():
    arm = make_arm(strength=1.0)
    states = run_on_path(arm, 6.0)
    x = np.array([s.pos[0] for s in states])
    assert x.max() - START[0] > 0.25              # reaches most of the 0.30 m
    assert all(s.mode == "compliant" for s in states)


def test_limp_patient_does_not_move_at_zero_axis_stiffness():
    arm = make_arm(strength=0.0)
    states = run_on_path(arm, 6.0)
    x = np.array([s.pos[0] for s in states])
    assert np.abs(x - START[0]).max() < 1e-3
    assert all(s.mode == "compliant" for s in states)


def test_assist_spring_carries_limp_patient():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    arm.set_stiffness(400.0, WALL, WALL)
    for i in range(500):                           # 4 s min-jerk reference, as the controller uses
        arm.get_state()
        ref = START[0] + min_jerk(0.0, 0.30, 4.0, i * DT)
        arm.set_target((ref, START[1], START[2]))  # arm clamps the lead to 5 cm
        arm.step(DT)
    st = arm.get_state()
    assert st.pos[0] - START[0] > 0.2
    assert st.mode == "compliant"


# ------------------------------------------------------------------ force reporting

def test_force_sign_positive_when_pushing_plus_x():
    arm = make_arm(strength=1.0)
    states = run_on_path(arm, 6.0)
    # before the last 5 cm: near the end the patient brakes (force < 0 while still moving +x)
    pushing = [s for s in states if s.vel[0] > 0.05 and s.pos[0] - START[0] < 0.25]
    assert pushing, "patient never moved toward +x"
    assert all(s.force[0] > 0 for s in pushing)


def test_passive_limb_load_when_present():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    st = arm.get_state()
    assert st.force == pytest.approx((0.0, 0.0, -PASSIVE_LOAD_N))


def test_force_zero_when_handle_empty():
    arm = make_arm(strength=1.0, present=False)
    states = run_on_path(arm, 6.0)
    assert all(s.force == (0.0, 0.0, 0.0) for s in states)
    x = np.array([s.pos[0] for s in states])
    assert np.abs(x - START[0]).max() < 1e-9      # empty handle on a free axis stays put


def test_letting_go_mid_reach_zeroes_force():
    arm = make_arm(strength=1.0)
    run_on_path(arm, 3.0)
    assert arm.get_state().force != (0.0, 0.0, 0.0)
    arm.patient.present = False
    assert arm.get_state().force == (0.0, 0.0, 0.0)


# ------------------------------------------------------------------ trips and stops

def test_watchdog_trip_then_commands_ignored():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    for _ in range(25):                            # 0.25 s with no set_target
        arm.step(DT)
    st = arm.get_state()
    assert st.mode == "hold" and "watchdog" in st.fault
    target_before = arm._target.copy()
    k_before = arm._k.copy()
    arm.set_target((START[0] + 0.03, START[1], START[2]))
    arm.set_stiffness(0.0, 0.0, 0.0)
    for _ in range(20):
        arm.step(DT)
    assert np.array_equal(arm._target, target_before)
    assert np.array_equal(arm._k, k_before)
    assert arm.get_state().mode == "hold"
    arm.start_compliance()                         # re-arm clears the fault
    st = arm.get_state()
    assert st.mode == "compliant" and st.fault is None


def test_speed_trip_drops_to_hold():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    arm.set_stiffness(600.0, 600.0, 600.0)
    tripped = None
    for _ in range(200):
        st = arm.get_state()
        if st.mode == "hold":
            tripped = st
            break
        # keep yanking the target 5 cm ahead: a stiff spring on a limp arm overshoots fast
        arm.set_target((st.pos[0] + 0.05, START[1], START[2]))
        arm.step(DT)
    assert tripped is not None and "speed" in tripped.fault
    assert np.allclose(arm._k, arm.limits.k_hold)


def test_hand_outside_box_trips():
    arm = make_arm(strength=0.0)
    arm.start_compliance()
    arm._pos = np.array(START) + np.array([0.0, arm.limits.box_half_m[1] + 0.03, 0.0])
    st = arm.get_state()
    assert st.mode == "hold" and "outside workspace box" in st.fault


def test_hold_puts_target_on_hand_at_k_hold():
    arm = make_arm(strength=1.0)
    run_on_path(arm, 3.0)
    arm.hold()
    st = arm.get_state()
    assert st.mode == "hold" and st.fault is None
    assert np.allclose(arm._target, st.pos)
    assert np.allclose(arm._k, arm.limits.k_hold)


def test_stop_and_close_leave_idle():
    arm = make_arm(strength=1.0)
    run_on_path(arm, 3.0)
    arm.stop()
    p = arm.get_state().pos
    arm.step(0.5)
    st = arm.get_state()
    assert st.mode == "idle" and st.pos == p
    arm.close()
    assert arm.get_state().mode == "idle"


# ------------------------------------------------------------------ realtime

def test_realtime_thread_advances_and_watchdog_fires():
    arm = SimArm(SimPatient(strength=0.0), start_pos=START, realtime=True)
    arm.connect()
    try:
        arm.start_compliance()
        t0 = arm.get_state().t
        for _ in range(10):
            arm.set_target(START)
            time.sleep(0.01)
        assert arm.get_state().t > t0
        assert arm.get_state().mode == "compliant"
        time.sleep(0.4)                            # stop feeding: watchdog after 0.2 s
        st = arm.get_state()
        assert st.mode == "hold" and "watchdog" in st.fault
    finally:
        arm.close()


# ------------------------------------------------------------------ patient cue

def test_patient_reaches_on_cue_from_soft_hold_only():
    arm = make_arm(strength=1.0)
    arm.start_compliance()
    for _ in range(300):                           # 3 s at the soft hold: before the first
        arm.get_state()                            # cue it rests 1.5 s, then reaches alone
        arm.set_target(START)
        arm.step(DT)
    assert arm._cued is False
    arm2 = make_arm(strength=1.0)
    arm2.start_compliance()
    arm2.set_target(START)
    arm2.step(DT)
    assert arm2._intent == "rest"
    arm2.set_stiffness(0.0, WALL, WALL)            # leaves the soft hold: the engine's cue
    arm2.step(STIFFNESS_LATENCY_S + DT)
    assert arm2._intent == "out" and arm2._cued
    arm2._intent = "back"
    arm2.set_stiffness(100.0, WALL, WALL)          # mid-rep change (rescue, dial): not a cue
    arm2.step(STIFFNESS_LATENCY_S + DT)
    assert arm2._intent == "back"


def test_cued_patient_does_not_start_alone_and_near_start_is_along_reach():
    arm = make_arm(strength=1.0)
    arm.start_compliance()
    arm.set_stiffness(0.0, WALL, WALL)
    arm.step(STIFFNESS_LATENCY_S + DT)             # cued once: engine-driven from now on
    arm._intent = "rest"
    arm._pos = np.array(START) + np.array([0.0, 0.0, -0.03])   # 3 cm limb sag, on the start
    for _ in range(400):
        arm._update_intent()
        arm._t += DT
    assert arm._intent == "rest"                   # waits for the next cue
    arm._intent = "back"
    arm._intent_t0 = arm._t - 3.0
    arm._update_intent()
    assert arm._intent == "rest"                   # sag does not hide "back at the start"


# --------------------------------------------------------------------------- test-limits profile (same contract as robot.arm.Arm)

def test_test_limits_profile_and_default_untouched():
    arm = make_arm()
    default = arm.limits
    assert default == Limits() and not arm.test_limits_on
    arm.start_compliance()
    arm.set_test_limits(True)
    t = arm.limits
    assert (t.k_max, t.max_contact_n, t.trip_force) == (1500.0, 65.0, 75.0)
    assert (t.k_hold, t.max_lead_m, t.trip_speed, t.box_half_m) == (default.k_hold, default.max_lead_m, default.trip_speed, default.box_half_m)
    arm.set_stiffness(5000, 5000, 5000)
    arm.step(STIFFNESS_LATENCY_S + 0.05)
    assert np.allclose(arm._k, 1500.0)
    arm.set_test_limits(False)
    assert arm.limits is default and np.allclose(arm._k, default.k_hold)     # nothing above the default cap stays on
    arm.close()


@pytest.mark.parametrize("how", ["hold", "stop", "start_compliance", "close", "trip"])
def test_test_limits_restored_to_default(how):
    arm = make_arm()
    arm.start_compliance()
    arm.set_test_limits(True)
    if how == "trip":
        arm._trip("test trip")
        assert arm.get_state().mode == "hold"
    else:
        getattr(arm, how)()
    assert not arm.test_limits_on and arm.limits == Limits()
    if how != "close":
        arm.close()


def test_set_test_limits_signature_matches_arm():
    assert inspect.signature(SimArm.set_test_limits) == inspect.signature(Arm.set_test_limits)
