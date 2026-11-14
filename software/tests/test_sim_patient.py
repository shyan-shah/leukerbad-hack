"""Tests for software/sim_patient.py (package S0d)."""

import numpy as np
import pytest

from software.sim_patient import SimPatient, simulate_reach

START = np.array([0.45, 0.00, 0.30])
END = np.array([0.75, 0.00, 0.30])  # 0.30 m reach along +x
N_REPS = 5
K_ZERO_ALONG_REACH = (0.0, 400.0, 400.0)  # no stiffness along x, the reach axis
LEAD = 0.05


def progress(pos):
    d = END - START
    return (pos - START) @ d / (d @ d)


def per_rep(out, n_reps=N_REPS):
    """Split the progress trace into equal per-rep windows."""
    s = progress(out["pos"])
    return np.array_split(s, n_reps)


def test_strong_patient_completes_reps_alone():
    out = simulate_reach(SimPatient(strength=1.0), START, END, N_REPS, K_ZERO_ALONG_REACH, LEAD)
    reps = per_rep(out)
    assert len(reps) == N_REPS
    for s in reps:
        assert s.max() >= 0.9      # reaches the end
        assert s[-1] <= 0.1        # comes back to the start
    assert np.abs(out["pos"][:, 1:] - START[1:]).max() < 1e-3  # stays on the line


def test_limp_patient_with_zero_stiffness_does_not_move():
    out = simulate_reach(SimPatient(strength=0.0), START, END, N_REPS, K_ZERO_ALONG_REACH, LEAD)
    assert np.abs(out["pos"] - START).max() < 1e-9
    assert np.abs(out["force"]).max() == 0.0


def test_limp_patient_is_carried_by_400_n_per_m_and_5_cm_lead():
    out = simulate_reach(SimPatient(strength=0.0), START, END, N_REPS, (400.0, 400.0, 400.0), LEAD)
    for s in per_rep(out):
        assert s.max() >= 0.95
        assert s[-1] <= 0.1
    assert np.abs(out["force"]).max() == 0.0  # all the work is the arm's


def test_deterministic_for_fixed_seed():
    p = dict(strength=0.6, tremor_n=2.0)
    a = simulate_reach(SimPatient(seed=3, **p), START, END, 2, (200.0, 200.0, 200.0), LEAD)
    b = simulate_reach(SimPatient(seed=3, **p), START, END, 2, (200.0, 200.0, 200.0), LEAD)
    c = simulate_reach(SimPatient(seed=4, **p), START, END, 2, (200.0, 200.0, 200.0), LEAD)
    for key in ("t", "pos", "vel", "force", "target"):
        np.testing.assert_array_equal(a[key], b[key])
    assert not np.array_equal(a["force"], c["force"])


def test_arrays_match_shared_conventions():
    dt = 0.01
    out = simulate_reach(SimPatient(), START, END, 3, K_ZERO_ALONG_REACH, LEAD, dt=dt)
    t = out["t"]
    n = len(t)
    assert t.shape == (n,) and n > 0
    for key in ("pos", "vel", "force", "target"):
        assert out[key].shape == (n, 3), key
        assert np.all(np.isfinite(out[key])), key
    assert t[0] == 0.0
    np.testing.assert_allclose(np.diff(t), dt)
    assert out["simulated"] is True
    np.testing.assert_allclose(out["pos"][0], START)
    # target is always on the segment
    s_target = progress(out["target"])
    assert s_target.min() >= -1e-12 and s_target.max() <= 1 + 1e-12


def test_target_leads_hand_by_lead_m():
    out = simulate_reach(SimPatient(), START, END, 1, K_ZERO_ALONG_REACH, LEAD)
    s_hand = np.clip(progress(out["pos"]), 0, 1)
    s_target = progress(out["target"])
    gap_m = np.abs(s_target - s_hand) * np.linalg.norm(END - START)
    assert gap_m.max() <= LEAD + 1e-9


def test_effort_capped_scaled_and_with_tremor():
    goal = END
    far = START - np.array([1.0, 0.0, 0.0])
    f_full = SimPatient(strength=1.0).effort(0.0, far, np.zeros(3), goal)
    assert np.linalg.norm(f_full) == pytest.approx(25.0)
    f_half = SimPatient(strength=0.5).effort(0.0, far, np.zeros(3), goal)
    np.testing.assert_allclose(f_half, 0.5 * f_full)
    # tremor alone: 5 Hz, bounded by its amplitude
    p = SimPatient(strength=0.0, tremor_n=3.0, seed=1)
    ts = np.arange(0.0, 1.0, 0.01)
    fs = np.array([p.effort(t, START, np.zeros(3), START) for t in ts])
    assert np.abs(fs).max() <= 3.0 + 1e-12
    assert np.abs(fs).max() > 2.5
    np.testing.assert_allclose(fs[:-20], fs[20:], atol=1e-9)  # period 0.2 s


def test_present_defaults_true():
    assert SimPatient().present is True


def test_absent_patient_applies_no_force():
    p = SimPatient(strength=1.0, tremor_n=2.0, present=False)
    np.testing.assert_array_equal(p.effort(0.1, START, np.zeros(3), END), np.zeros(3))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(start=START, end=START, n_reps=1),
        dict(start=START, end=END, n_reps=0),
        dict(start=START[:2], end=END, n_reps=1),
    ],
)
def test_bad_input_raises(kwargs):
    with pytest.raises(ValueError):
        simulate_reach(SimPatient(), k_xyz=K_ZERO_ALONG_REACH, lead_m=LEAD, **kwargs)
