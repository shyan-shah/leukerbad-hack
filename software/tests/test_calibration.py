"""Comfortable-push calibration in the engine (contract of 15 Nov, server/API.md section 7). SimArm only."""
from __future__ import annotations

import json

import pytest

from software import strength_model
from software.engine import Engine
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
REAL = dict(empty_force_pose_n_per_m=(10.0, 0.0, 0.0), empty_force_moving_n=(3.0, 7.0), friction_n=4.5)
KEYS = {"status", "progress", "comfort_force_n", "resistance_n", "fraction", "reason"}


def make(exercise="push", strength=0.6, present=True, arm_kw=REAL, **kw):
    arm = SimArm(SimPatient(strength=strength, present=present), start_pos=START, realtime=False, **arm_kw)
    arm.connect()
    samples, reps = [], []
    eng = Engine(arm, "s", "p", True, exercise=exercise, on_sample=samples.append, on_rep=reps.append, **kw)
    eng.start()
    return eng, arm, samples, reps


def run_until(eng, cond, max_s=40.0):
    for _ in range(int(max_s * 100)):
        if cond():
            return
        eng.run_for(0.01)
    raise AssertionError(f"not reached within {max_s} s (phase {eng.phase!r}, {eng.snapshot()['calibration']})")


def cal(eng):
    return eng.snapshot()["calibration"]


@pytest.mark.parametrize("exercise", ["push", "pull"])
def test_weak_medium_strong_patients_get_clearly_different_resistances(exercise):
    got = []
    for strength in (0.3, 0.6, 1.0):
        eng, arm, samples, reps = make(exercise, strength, reps=3)
        seen = set()
        run_until(eng, lambda: seen.add(cal(eng)["status"]) or eng.phase == "idle" and cal(eng)["status"] != "waiting")
        c = cal(eng)
        assert set(c) == KEYS and c["status"] == "done" and c["progress"] == 1.0 and c["reason"] is None
        assert {"waiting", "pushing", "done"} <= seen
        assert c["fraction"] == 0.5 and c["resistance_n"] == pytest.approx(0.5 * c["comfort_force_n"], abs=0.02)
        assert eng.dial == pytest.approx(-c["resistance_n"] / 15.0, abs=0.01)
        n_cal = sum(s.phase == "calibrate" for s in samples)
        assert 300 <= n_cal <= 400                                    # 3 s push plus the short wait for it
        assert all(s.rep_idx == -1 and s.dial == 0.0 for s in samples if s.phase == "calibrate")
        moved = [abs(s.pos[0] - samples[i0].pos[0]) for i0 in [next(i for i, s in enumerate(samples) if s.phase == "calibrate")]
                 for s in samples if s.phase == "calibrate"]
        assert max(moved) < 0.03                                      # the handle is held still
        assert not getattr(arm, "test_limits_on", False)              # the test profile is off again
        eng.run_until_reps(3, max_s=90.0)
        assert eng.rep_count == 3 and all(r.completed for r in reps) and arm.get_state().fault is None
        assert all(r.dial == pytest.approx(eng.dial) for r in reps)
        got.append(c["resistance_n"])
        eng.stop()
        json.dumps(eng.calibration_state_after)
    # measured (push / pull, friction on): about 6.0 / 4.6, 9.8 / 8.4, 14.8 / 13.4 N
    assert got[0] >= 3.0 and got[1] > got[0] + 2.0 and got[2] > got[1] + 2.0 and got[2] <= 15.0


def test_easy_set_raises_the_next_fraction_and_a_hard_one_lowers_it():
    eng, arm, samples, reps = make("push", 1.0, reps=3)               # all reps completed, on time, no rescue
    eng.run_until_reps(3, max_s=90.0)
    eng.stop()
    up = eng.calibration_state_after
    assert up["fraction"] > 0.5 and up["sets"] == 1
    eng2, arm2, _, reps2 = make("push", 1.0, reps=3, calibration_state=up)
    run_until(eng2, lambda: cal(eng2)["status"] == "done")
    assert cal(eng2)["fraction"] == up["fraction"]                    # the next session uses it
    run_until(eng2, lambda: eng2.phase == "out")
    eng2.run_for(1.0)
    arm2.patient.present = False                                      # a hard set: the rep is not completed
    eng2.run_for(3.0)
    eng2.stop()
    assert reps2 and not reps2[-1].completed
    assert eng2.calibration_state_after["fraction"] < up["fraction"]


def test_empty_handle_times_out_with_the_lightest_resistance_and_a_reason():
    eng, arm, samples, reps = make("push", 0.0, present=False)
    eng.run_for(10.0)
    assert cal(eng)["status"] == "waiting" and eng.phase == "calibrate" and eng.rep_count == 0
    assert abs(arm.get_state().pos[0] - START[0]) < 0.002
    eng.run_for(11.0)
    c = cal(eng)
    assert c["status"] == "skipped" and c["resistance_n"] == 3.0 and c["comfort_force_n"] is None and "no push" in c["reason"]
    assert eng.dial == pytest.approx(-0.2) and eng.phase == "idle" and eng.rep_count == 0
    assert not getattr(arm, "test_limits_on", False) and arm.get_state().fault is None


def test_push_under_5n_gives_the_lightest_resistance_with_a_reason():
    eng, arm, samples, reps = make("push", 0.15, arm_kw={})           # pushes about 3.75 N
    run_until(eng, lambda: cal(eng)["status"] in ("done", "skipped"))
    c = cal(eng)
    assert c["status"] == "skipped" and c["resistance_n"] == 3.0 and "under 5 N" in c["reason"]
    assert 2.0 < c["comfort_force_n"] < 5.0 and eng.dial == pytest.approx(-0.2)


def test_let_go_during_the_push_gives_the_lightest_resistance_no_trip():
    eng, arm, samples, reps = make("push", 1.0)
    run_until(eng, lambda: cal(eng)["status"] == "pushing")
    eng.run_for(1.5)
    arm.patient.present = False
    eng.run_for(3.0)
    c = cal(eng)
    assert c["status"] == "skipped" and c["resistance_n"] == 3.0 and "let go" in c["reason"]
    st = arm.get_state()
    assert st.fault is None and st.mode == "compliant" and eng.phase == "idle"
    assert max(abs(s.vel[0]) for s in samples) < 0.15


def test_calibrate_false_set_dial_and_stop_during_the_push():
    eng, arm, samples, reps = make("push", 1.0, calibrate=False, reps=1)
    assert cal(eng)["status"] == "skipped" and cal(eng)["resistance_n"] is None and eng.dial == -0.6
    eng.run_until_reps(1, max_s=40.0)
    assert all(s.phase != "calibrate" for s in samples) and reps[0].dial == -0.6
    eng, arm, samples, reps = make("push", 1.0)
    eng.set_dial(-0.3)                                                # set_dial still overrides
    run_until(eng, lambda: cal(eng)["status"] == "done")
    assert eng.dial == -0.3
    eng, arm, samples, reps = make("push", 1.0)
    run_until(eng, lambda: cal(eng)["status"] == "pushing")
    eng.stop()
    assert cal(eng)["status"] == "pushing"                            # the server saves nulls unless "done"
    assert eng.calibration_state_after == strength_model.new_state()
    assert not getattr(arm, "test_limits_on", False)


@pytest.mark.parametrize("exercise", ["reach", "armtest"])
def test_reach_and_armtest_have_no_calibration(exercise):
    eng, arm, samples, reps = make(exercise, 0.8, calibrate=True)
    eng.run_until_reps(2, max_s=60.0)
    assert cal(eng) is None and all(s.phase != "calibrate" for s in samples)
    assert eng.rep_count >= 2 and arm.get_state().fault is None
    eng.stop()
    assert eng.calibration_state_after == strength_model.new_state()
