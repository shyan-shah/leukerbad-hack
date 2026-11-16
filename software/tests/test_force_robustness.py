"""Force-sensor errors: SimArm's error options and the engine's empty-handle baseline.

The real arm read about (4.5, -2.5, 11.9) N un-zeroed with nothing touching it
(docs/BRINGUP_FINDINGS.md), against a 1.5 N occupancy threshold. These tests use that
offset, 0.5 N/min drift, 0.3 N noise and up to 200 ms stiffness latency. Everything here is
simulated.
"""

from __future__ import annotations

import numpy as np
import pytest

from software import engine as engine_mod
from software.engine import DT, Engine
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
REACH = 0.30
REAL_OFFSET = (4.5, -2.5, 11.9)          # measured on the arm, un-zeroed, nothing touching
DRIFT = (0.0, 0.0, 0.5)                  # N/min
NOISE = 0.3                              # N
SLOW = 0.2                               # s stiffness latency (worst case of 50-200 ms)


def sim(patient, **kw) -> SimArm:
    arm = SimArm(patient, start_pos=START, realtime=False, **kw)
    arm.connect()
    return arm


def zero_hands_off(arm: SimArm) -> None:
    """Zero the sensor the right way: nobody touching the handle."""
    was = arm.patient.present
    arm.patient.present = False
    arm.zero_force()
    arm.patient.present = was


def engine_on(arm, dial=1.0, auto=False):
    samples, reps = [], []
    eng = Engine(arm, "sess-f", "pat-f", True, dial=dial, auto=auto,
                 on_sample=samples.append, on_rep=reps.append)
    eng.start()
    return eng, samples, reps


def all_errors(patient, zero=True, offset=REAL_OFFSET, **kw) -> SimArm:
    arm = sim(patient, force_offset=offset, force_drift_n_per_min=DRIFT, force_noise_n=NOISE,
              stiffness_latency_s=SLOW, **kw)
    if zero:
        zero_hands_off(arm)
    return arm


def progress_x(p) -> float:
    return (p[0] - START[0]) / REACH


# --------------------------------------------------------------------------- SimArm options

def test_defaults_report_the_true_force():
    arm = sim(SimPatient(strength=0.0, present=False))
    assert arm.get_state().force == (0.0, 0.0, 0.0)


def test_offset_is_reported_but_does_not_push_the_hand():
    arm = sim(SimPatient(strength=0.0, present=False), force_offset=REAL_OFFSET)
    assert arm.get_state().force == pytest.approx(REAL_OFFSET)
    arm.start_compliance()
    for _ in range(200):
        arm.set_target(START)
        arm.step(DT)
    st = arm.get_state()
    assert np.allclose(st.pos, START, atol=1e-9)    # a sensor offset is not a real force
    assert st.mode == "compliant"


def test_drift_grows_from_the_last_zero():
    arm = sim(SimPatient(strength=0.0, present=False), force_drift_n_per_min=DRIFT)
    for _ in range(6000):                           # 60 s, idle
        arm.step(DT)
    assert arm.get_state().force[2] == pytest.approx(0.5, abs=1e-6)
    arm.zero_force()
    assert arm.get_state().force == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)


def test_noise_has_the_requested_spread_and_is_seeded():
    a = sim(SimPatient(strength=0.0, present=False), force_noise_n=NOISE, seed=3)
    b = sim(SimPatient(strength=0.0, present=False), force_noise_n=NOISE, seed=3)
    fa = np.array([a.get_state().force for _ in range(4000)])
    fb = np.array([b.get_state().force for _ in range(4000)])
    assert np.array_equal(fa, fb)
    assert np.std(fa, axis=0) == pytest.approx([NOISE] * 3, rel=0.1)
    assert np.abs(np.mean(fa, axis=0)).max() < 0.03


def test_zero_force_removes_offset_but_zeroing_with_a_hand_on_bakes_it_in():
    p = SimPatient(strength=0.0, present=False)
    arm = sim(p, force_offset=REAL_OFFSET)
    arm.zero_force()
    assert arm.get_state().force == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)
    p.present = True                                # limb rests on the handle: 8 N down
    assert arm.get_state().force[2] == pytest.approx(-8.0)
    arm.zero_force()                                # wrong: zeroed with the hand on
    p.present = False
    assert arm.get_state().force[2] == pytest.approx(8.0)


def test_stiffness_latency_option():
    arm = sim(SimPatient(strength=0.0, present=False), stiffness_latency_s=SLOW)
    arm.start_compliance()
    arm.set_target(START)
    arm.set_stiffness(100.0, 100.0, 100.0)
    for _ in range(19):
        arm.step(DT)
        arm.set_target(START)
    assert np.allclose(arm._k, arm.limits.k_hold)  # 190 ms: not yet
    arm.step(2 * DT)
    assert np.allclose(arm._k, 100.0)               # 210 ms: applied


def test_bad_options_rejected():
    with pytest.raises(ValueError):
        SimArm(SimPatient(), realtime=False, force_noise_n=-0.1)
    with pytest.raises(ValueError):
        SimArm(SimPatient(), realtime=False, stiffness_latency_s=-0.01)


# --------------------------------------------------------------------------- engine baseline

def test_unzeroed_real_offset_refuses_to_start_with_a_clear_error():
    arm = all_errors(SimPatient(strength=0.0), zero=False)
    eng = Engine(arm, "sess-f", "pat-f", True)
    with pytest.raises(RuntimeError, match=r"13\.\d N with the handle empty.*zero_force"):
        eng.start()
    assert arm.get_state().mode == "idle"           # compliance never started
    with pytest.raises(RuntimeError):
        eng.run_for(DT)                             # and the engine did not start
    # the fix the message asks for works
    zero_hands_off(arm)
    eng2, samples, reps = engine_on(arm)
    eng2.run_until_reps(2, max_s=60)
    assert len(reps) == 2 and all(r.completed for r in reps)


def test_unzeroed_12n_offset_refuses_even_on_one_axis():
    arm = sim(SimPatient(strength=0.0), force_offset=(0.0, 0.0, 12.0))
    with pytest.raises(RuntimeError, match="zero_force"):
        Engine(arm, "s", "p", True).start()


def test_baseline_is_taken_with_the_handle_empty_and_patient_restored():
    p = SimPatient(strength=0.0)                    # present: the limb would load 8 N
    arm = sim(p, force_offset=(1.0, -1.0, 1.5))
    eng, samples, reps = engine_on(arm)
    assert eng.force_baseline == pytest.approx((1.0, -1.0, 1.5), abs=1e-9)
    assert p.present is True


def test_reps_with_offset_drift_noise_and_200ms_latency():
    arm = all_errors(SimPatient(strength=0.0))
    eng, samples, reps = engine_on(arm, dial=1.0)
    eng.run_until_reps(4, max_s=120)
    assert len(reps) == 4
    assert all(r.completed for r in reps)
    assert arm.get_state().fault is None


def test_auto_dial_still_falls_for_strong_patient_with_errors():
    arm = all_errors(SimPatient(strength=1.0))
    eng, samples, reps = engine_on(arm, dial=1.0, auto=True)
    eng.run_until_reps(8, max_s=200)
    assert len(reps) == 8 and all(r.completed for r in reps)
    assert min([r.dial for r in reps[1:]] + [eng.dial]) < 0.3
    assert arm.get_state().fault is None


def test_residual_offset_above_f_present_is_handled_by_the_baseline():
    # un-zeroed 2.5 N: over F_PRESENT (an absolute check would call the empty handle
    # occupied) but under MAX_BASELINE_N, so the engine starts and subtracts it
    offset = (1.5, -1.0, 1.7)
    assert engine_mod.F_PRESENT < np.linalg.norm(offset) < engine_mod.MAX_BASELINE_N
    empty = SimPatient(strength=0.0, present=False)
    eng, samples, reps = engine_on(all_errors(empty, zero=False, offset=offset))
    eng.run_for(20.0)
    assert reps == [] and all(s.phase == "idle" for s in samples)
    held = SimPatient(strength=0.0)
    eng, samples, reps = engine_on(all_errors(held, zero=False, offset=offset))
    eng.run_until_reps(2, max_s=60)
    assert len(reps) == 2 and all(r.completed for r in reps)


def test_samples_carry_baseline_corrected_force():
    arm = all_errors(SimPatient(strength=0.0, present=False), zero=False, offset=(1.5, -1.0, 1.7))
    eng, samples, reps = engine_on(arm)
    eng.run_for(2.0)
    f = np.array([s.force for s in samples])
    assert np.abs(f.mean(axis=0)).max() < 0.25     # about zero (30-reading baseline), not 2.5 N


def test_empty_handle_with_five_minutes_of_drift_never_starts_a_rep():
    # without tracking, 0.5 N/min would pass F_PRESENT after 3 minutes
    arm = all_errors(SimPatient(strength=0.0, present=False))
    eng, samples, reps = engine_on(arm)
    eng.run_for(300.0)
    assert eng.rep_count == 0 and reps == []
    assert all(s.phase == "idle" for s in samples)
    xs = [s.target[0] for s in samples]
    assert max(xs) - min(xs) < 1e-9
    assert eng.force_baseline[2] == pytest.approx(2.5, abs=0.3)   # it followed the drift


def _let_go_mid_reach(eng, arm, samples, reps, p):
    while not (eng.phase == "out" and progress_x(arm.get_state().pos) > 0.3):
        eng.run_for(DT)
    t_release = samples[-1].t
    n_reps = len(reps)
    p.present = False
    eng.run_for(3.0)
    after = [s for s in samples if s.t > t_release]
    settle = [s for s in after if s.t >= t_release + engine_mod.OCCUPIED_WINDOW_S + 2 * DT]
    s_at = progress_x(settle[0].target)
    assert max(progress_x(s.target) for s in settle) <= s_at + 1e-9
    assert all(s.phase == "idle" for s in settle)
    assert len(reps) == n_reps + 1 and reps[-1].completed is False
    hand_at_release = progress_x(after[0].pos)
    assert (progress_x(samples[-1].pos) - hand_at_release) * REACH < 0.08


def test_hands_off_rule_with_offset_drift_noise_and_200ms_latency():
    p = SimPatient(strength=0.0)
    arm = all_errors(p)
    eng, samples, reps = engine_on(arm, dial=1.0)
    _let_go_mid_reach(eng, arm, samples, reps, p)


def test_hands_off_rule_after_two_minutes_of_holding_with_drift():
    # drift is not tracked while the handle is held: after 2 min it is 1 N, still under
    # F_PRESENT, so letting go is still seen (re-zero between sets on the real arm)
    p = SimPatient(strength=0.0)
    arm = all_errors(p)
    eng, samples, reps = engine_on(arm, dial=1.0)
    eng.run_for(120.0)
    assert len(reps) >= 5
    _let_go_mid_reach(eng, arm, samples, reps, p)
