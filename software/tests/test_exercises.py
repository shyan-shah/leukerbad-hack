"""Tests for the exercise presets (package E1): software/exercises.py and the engine's use of them.

All on SimArm(realtime=False) with the stock simulated patient. Everything here is simulated.
"""

from __future__ import annotations

import numpy as np
import pytest

from server.contract import RepResult, Sample
from software import controller
from software.engine import DT, Engine
from software.exercises import EXERCISES, LIVE, ExercisePreset, get
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)


def make(exercise=None, strength=1.0, present=True, **kw):
    patient = SimPatient(strength=strength, present=present)
    arm = SimArm(patient, start_pos=START, realtime=False)
    arm.connect()
    samples: list[Sample] = []
    reps: list[RepResult] = []
    if exercise is not None:
        kw["exercise"] = exercise
    eng = Engine(arm, "sess-x", "pat-x", True, on_sample=samples.append, on_rep=reps.append, **kw)
    eng.start()
    return eng, arm, samples, reps


def x(v) -> float:
    return v[0] - START[0]


def run_until_phase(eng, phase, max_s=30.0):
    for _ in range(int(max_s / DT)):
        if eng.phase == phase:
            return
        eng.run_for(DT)
    raise AssertionError(f"phase {phase!r} not reached within {max_s} s (phase is {eng.phase!r})")


# --------------------------------------------------------------------------- registry

def test_registry_ids_and_values():
    assert set(EXERCISES) == {"reach", "push", "pull", "armtest", "circle"}
    assert LIVE == ("reach", "push", "pull", "armtest")          # circle is not live
    r, p, q, a, c = (EXERCISES[i] for i in ("reach", "push", "pull", "armtest", "circle"))
    assert (r.kind, r.reach_m, r.direction, r.start_at, r.dial, r.auto, r.default_reps) == \
        ("assist", 0.30, 1, "start", 1.0, True, 10)
    assert (p.kind, p.reach_m, p.direction, p.start_at, p.dial, p.auto, p.default_reps) == \
        ("resist", 0.28, 1, "start", -0.6, False, 10)
    assert (q.kind, q.reach_m, q.direction, q.start_at, q.dial, q.auto, q.default_reps) == \
        ("resist", 0.28, -1, "far", -0.6, False, 10)
    assert (a.kind, a.default_reps, a.push_s, a.rest_s) == ("test", 3, 3.0, 5.0)
    assert (c.kind, c.radius_m, c.period_s, c.default_reps, c.stiffness) == ("guided", 0.08, 6.0, 8, 300.0)
    assert get("push") is p
    with pytest.raises(ValueError):
        get("lift")
    with pytest.raises(ValueError):
        Engine(None, "s", "p", True, exercise="lift")
    with pytest.raises(ValueError):
        ExercisePreset("bad", "bad", "resist", dial=0.5)
    with pytest.raises(ValueError):
        ExercisePreset("bad", "bad", "assist", start_at="far")   # far needs direction -1


def test_preset_dial_and_auto_rules():
    arm = SimArm(SimPatient(), start_pos=START, realtime=False)
    e = Engine(arm, "s", "p", True)                                   # default: reach
    assert (e.exercise, e.dial, e.auto, e.reach_m, e.reps_target) == ("reach", 1.0, True, 0.30, 10)
    e = Engine(arm, "s", "p", True, dial=0.4, auto=False)             # reach keeps the caller's dial
    assert (e.dial, e.auto) == (0.4, False)
    e = Engine(arm, "s", "p", True, dial=1.0, auto=True, exercise="push")   # the server's defaults
    assert (e.dial, e.auto, e.reach_m) == (-0.6, False, 0.28)
    e = Engine(arm, "s", "p", True, dial=-0.3, exercise="pull")       # a resist dial is honoured
    assert (e.dial, e.reach_sign) == (-0.3, -1)
    e = Engine(arm, "s", "p", True, exercise="push", reach_m=0.10, reps=4)
    assert (e.reach_m, e.reps_target) == (0.10, 4)
    with pytest.raises(ValueError):
        Engine(arm, "s", "p", True, reps=0)


# --------------------------------------------------------------------------- reach

def test_reach_is_todays_behaviour():
    _, _, _, reps_default = make(None, strength=0.6)
    eng_d = _
    eng_a, arm_a, _, reps_named = make("reach", strength=0.6)
    eng_b, arm_b, _, reps_b = make(None, strength=0.6)
    eng_a.run_until_reps(4)
    eng_b.run_until_reps(4)
    assert len(reps_named) == 4 and reps_named == reps_b             # identical records
    assert [r.mode for r in reps_named][0] == "assist"
    snap = eng_a.snapshot()
    assert snap["exercise"] == "reach" and snap["kind"] == "assist"
    assert snap["reps_target"] == 10 and snap["done"] is False
    assert eng_a.stop().exercise == "reach_line"                      # unchanged for existing callers
    del eng_d, reps_default, arm_a, arm_b


def test_reps_limit_stops_arming_only_when_given():
    eng, arm, _, reps = make("reach", strength=0.8, reps=2)
    eng.run_for(40.0)
    assert len(reps) == 2 and eng.done and eng.phase == "idle"
    assert arm.get_state().fault is None


# --------------------------------------------------------------------------- push

def test_push_resists_and_strong_patient_completes():
    eng, arm, samples, reps = make("push", strength=1.0)
    eng.run_until_reps(3, max_s=90.0)
    assert len(reps) == 3 and arm.get_state().fault is None
    for r in reps:
        assert r.mode == "resist" and r.dial == -0.6 and r.completed
        assert r.rom_m >= 0.9 * 0.28 - 0.01
        assert 5.0 < r.peak_force_n < 30.0
    assert eng.dial == -0.6 and eng.auto is False                    # no auto dial
    out = [s for s in samples if s.phase == "out" and x(s.pos) > 0.06]
    assert out and all(s.target[0] < s.pos[0] - 0.03 for s in out)   # band pulls back to the start
    assert max(x(s.pos) for s in samples) < 0.28 + 0.12
    assert eng.snapshot()["exercise"] == "push" and eng.stop().exercise == "push"


# --------------------------------------------------------------------------- pull

def test_pull_setup_then_resisted_reps_towards_the_patient():
    eng, arm, samples, reps = make("pull", strength=1.0)
    far = START[0] + 0.28
    assert eng.phase == "setup"
    assert eng.path.start[0] == pytest.approx(far) and eng.path.end[0] == pytest.approx(START[0])
    eng.run_for(0.5)
    setup = [s for s in samples if s.phase == "setup"]
    assert setup and all(s.dial == 0.0 and s.rep_idx == -1 for s in setup)
    assert all(abs(s.target[0] - s.pos[0]) < 1e-9 for s in setup)     # transparent: target rides on the hand
    assert tuple(arm._k) == (0.0, controller.K_WALL, controller.K_WALL)

    run_until_phase(eng, "idle")                                      # the patient brought it to the far end
    assert abs(arm.get_state().pos[0] - far) <= 0.02
    n_setup = len(samples)
    eng.run_until_reps(2, max_s=90.0)
    assert len(reps) == 2 and arm.get_state().fault is None
    for r in reps:
        assert r.mode == "resist" and r.dial == -0.6 and r.completed
        assert r.rom_m >= 0.9 * 0.28 - 0.01
    out = [s for s in samples[n_setup:] if s.phase == "out"]
    assert out[0].pos[0] > out[-1].pos[0] + 0.2                       # "out" moves towards the patient
    mid = [s for s in out if far - s.pos[0] > 0.06]
    assert mid and all(s.target[0] > s.pos[0] + 0.03 for s in mid)    # the band pulls back to the far end
    assert not any(s.phase == "setup" for s in samples[n_setup:])


def test_pull_setup_never_drives_an_empty_handle():
    eng, arm, samples, reps = make("pull", present=False)
    eng.run_for(8.0)
    assert eng.phase == "setup" and not reps
    assert max(abs(x(s.pos)) for s in samples) < 0.005                # it did not move
    assert max(np.linalg.norm(s.vel) for s in samples) < 0.01


# --------------------------------------------------------------------------- armtest

def test_armtest_three_tries_peak_near_patient_push():
    eng, arm, samples, reps = make("armtest", strength=0.8)
    eng.run_for(1.5 + 3 * 3.0 + 2 * 5.0 + 2.0)
    assert len(reps) == 3 and eng.done and eng.phase == "idle"
    assert arm.get_state().fault is None
    for r in reps:
        assert r.mode == "isometric" and r.completed and r.contribution == 1.0
        assert r.peak_force_n == pytest.approx(0.8 * 25.0, rel=0.15)  # the sim patient's capped push
        assert 0 < r.mean_force_n < r.peak_force_n
        assert r.rom_m < 0.05 and r.duration_s == pytest.approx(3.0, abs=0.05)
    assert max(abs(x(s.pos)) for s in samples) < 0.05                 # the handle stays put
    assert reps[1].t_start - reps[0].t_start == pytest.approx(8.0, abs=0.1)   # 3 s push + 5 s rest
    push = [s for s in samples if s.phase == "out"]
    assert all(s.target == pytest.approx(START) for s in push)
    assert {s.rep_idx for s in push} == {0, 1, 2}
    assert any(s.phase == "back" for s in samples)                    # rest
    eng.run_for(10.0)
    assert len(reps) == 3                                             # no fourth try
    snap = eng.snapshot()
    assert snap["exercise"] == "armtest" and snap["kind"] == "test" and snap["done"] is True


def test_armtest_stiffness_is_k_max_on_the_reach_axis_during_a_try():
    eng, arm, _, _ = make("armtest", strength=0.5)
    run_until_phase(eng, "out")
    eng.run_for(0.5)
    assert tuple(arm._k) == (arm.limits.k_max, controller.K_WALL, controller.K_WALL)


def test_armtest_weak_push_is_not_completed():
    eng, _, _, reps = make("armtest", strength=0.1)
    eng.run_until_reps(1, max_s=10.0)
    assert reps[0].peak_force_n < 5.0 and reps[0].completed is False


# --------------------------------------------------------------------------- circle (stretch)

def circle_error(samples):
    """Distance of each moving sample from the circle, constant vertical sag removed."""
    pts = np.array([s.pos for s in samples if s.phase in ("out", "back")])
    c = np.array([START[0] + 0.08, START[1], START[2]])
    d = pts - c
    radial = np.hypot(d[:, 0], d[:, 2])
    err = np.stack([d[:, 0] * (1 - 0.08 / radial), d[:, 1], d[:, 2] * (1 - 0.08 / radial)], axis=1)
    err[:, 2] -= err[:, 2].mean()
    return np.linalg.norm(err, axis=1)


def test_circle_passive_patient_tracks_within_2cm():
    eng, arm, samples, reps = make("circle", strength=0.0)
    eng.run_for(1.5 + 8 * 6.0 + 6.0)
    assert len(reps) == 8 and eng.done and eng.phase == "idle"
    assert arm.get_state().fault is None
    assert all(r.mode == "guided" and r.completed for r in reps)
    assert all(r.duration_s < 7.0 and r.path_err_max_m < 0.02 for r in reps)
    assert circle_error(samples).max() < 0.02
    moving = np.array([s.pos for s in samples if s.phase in ("out", "back")])
    assert np.ptp(moving[:, 0]) > 0.14 and np.ptp(moving[:, 2]) > 0.14    # it really went round
    assert tuple(arm._k) == (300.0, 300.0, 300.0)
    assert "circle" not in LIVE


# --------------------------------------------------------------------------- hands off, every kind

def settle(eng, samples, seconds):
    n = len(samples)
    eng.run_for(seconds)
    return samples[n:]


def test_hands_off_reach_stops_advancing():
    eng, arm, samples, _ = make("reach", strength=0.0)
    run_until_phase(eng, "out")
    eng.run_for(1.8)
    arm.patient.present = False
    x0 = x(arm.get_state().pos)
    after = settle(eng, samples, 3.0)
    assert eng.phase == "idle"
    assert max(x(s.pos) for s in after) - x0 < 0.08
    assert np.linalg.norm(after[-1].vel) < 0.005


@pytest.mark.parametrize("exercise", ["push", "pull"])
def test_hands_off_resist_never_advances_and_stops(exercise):
    eng, arm, samples, _ = make(exercise, strength=1.0)
    if exercise == "pull":
        run_until_phase(eng, "idle")
    run_until_phase(eng, "out")
    eng.run_for(1.5)
    s0 = eng._progress(arm.get_state().pos)
    assert s0 > 0.15
    arm.patient.present = False
    after = settle(eng, samples, 8.0)
    assert max(eng._progress(s.pos) for s in after) < s0 + 0.03      # never carried on along the reach
    assert np.linalg.norm(after[-1].vel) < 0.005                     # and it has stopped
    # In the sim the band snaps the empty handle back and the arm's speed trip holds it;
    # either that, or it is back at the path start.
    st = arm.get_state()
    assert st.mode == "hold" or abs(eng._progress(st.pos)) * eng.reach_m < 0.03


def test_hands_off_armtest_does_not_move():
    eng, arm, samples, reps = make("armtest", strength=0.8)
    run_until_phase(eng, "out")
    eng.run_for(1.0)
    arm.patient.present = False
    after = settle(eng, samples, 4.0)
    assert max(abs(x(s.pos)) for s in after) < 0.05                  # never driven anywhere
    assert np.linalg.norm(after[-1].vel) < 0.005


def test_hands_off_circle_stops_the_target():
    eng, arm, samples, reps = make("circle", strength=0.0)
    run_until_phase(eng, "out")
    eng.run_for(2.0)
    arm.patient.present = False
    after = settle(eng, samples, 3.0)
    late = after[int(0.6 / DT):]
    assert eng.phase == "idle" and all(s.phase == "idle" for s in late)
    assert max(np.linalg.norm(np.subtract(s.target, late[0].target)) for s in late) < 1e-9
    assert np.linalg.norm(after[-1].vel) < 0.005
    assert reps and reps[-1].completed is False


# --------------------------------------------------------------------------- sessions in a row, reach along y

def session(arm, exercise, **kw):
    samples, reps = [], []
    eng = Engine(arm, "sess-y", "pat-y", True, on_sample=samples.append, on_rep=reps.append,
                 exercise=exercise, **kw)
    eng.start()
    return eng, samples, reps


@pytest.mark.parametrize("nxt", ["armtest", "reach", "push", "circle"])
def test_next_session_never_drives_an_empty_handle_left_at_the_far_end(nxt):
    """pull ends 28 cm out. The next exercise must not pull an empty handle back to the start."""
    arm = SimArm(SimPatient(strength=1.0), start_pos=START, realtime=False)
    arm.connect()
    eng, _, reps = session(arm, "pull", reps=1)
    eng.run_until_reps(1, max_s=60.0)
    eng.run_for(1.0)
    eng.stop()
    assert len(reps) == 1 and x(arm.get_state().pos) > 0.20          # left near the far end
    arm.patient.present = False
    for _ in range(300):               # the limb's weight comes off the held handle: let it settle
        arm.step(DT)
    left = arm.get_state().pos
    eng, samples, reps = session(arm, nxt)
    eng.run_for(8.0)
    assert not reps and arm.get_state().fault is None
    assert max(abs(s.pos[0] - left[0]) for s in samples) < 0.005      # never moved along the reach
    # the soft hold may lift the sagged handle back onto the path line (under 3 cm, vertical only)
    assert max(np.linalg.norm(np.subtract(s.pos, left)) for s in samples) < 0.03
    assert np.linalg.norm(samples[-1].vel) < 0.005


@pytest.mark.parametrize("exercise", ["push", "pull", "armtest"])
def test_reach_along_y_layout_b(exercise):
    """Layout B: reach along world y. Same programmes, box laid out along y."""
    from robot.arm import Limits, limits_for_reach_axis
    start = (0.50, -0.15, 0.30)
    arm = SimArm(SimPatient(strength=0.8), limits_for_reach_axis(Limits(), 1), start_pos=start,
                 realtime=False)
    arm.connect()
    samples, reps = [], []
    eng = Engine(arm, "s", "p", True, reach_axis=1, reach_sign=1, exercise=exercise,
                 on_sample=samples.append, on_rep=reps.append)
    eng.start()
    eng.run_until_reps(2, max_s=90.0)
    assert len(reps) == 2 and all(r.completed for r in reps) and arm.get_state().fault is None
    assert max(abs(s.pos[0] - start[0]) for s in samples) < 0.01     # x is a wall axis
    if exercise == "armtest":
        assert reps[0].peak_force_n == pytest.approx(20.0, rel=0.15)
        assert max(abs(s.pos[1] - start[1]) for s in samples) < 0.05
    else:
        assert max(s.pos[1] - start[1] for s in samples) > 0.25
