"""Tests for software/metrics.py (package S0a)."""

import numpy as np
import pytest

from software import metrics as m

FS = 100.0
START = np.array([0.40, 0.00, 0.10])
END = np.array([0.70, 0.00, 0.10])  # 0.30 m reach along +x


def min_jerk_reach(duration=1.5, bow_m=0.0):
    """Straight minimum-jerk reach START -> END, optional sideways bow in y."""
    t = np.arange(0.0, duration + 1e-9, 1.0 / FS)
    tau = t / duration
    s = 10 * tau**3 - 15 * tau**4 + 6 * tau**5
    pos = START + np.outer(s, END - START)
    pos[:, 1] += bow_m * np.sin(np.pi * s)
    return t, pos


def min_jerk_speed(duration=1.5, length=0.30):
    t = np.arange(0.0, duration + 1e-9, 1.0 / FS)
    tau = t / duration
    return t, length / duration * (30 * tau**2 - 60 * tau**3 + 30 * tau**4)


# --- rom and path error ---------------------------------------------------

def test_straight_reach_rom_and_zero_path_error():
    _, pos = min_jerk_reach()
    assert m.rom(pos, START, END) == pytest.approx(0.30, abs=1e-6)
    mean_err, max_err = m.path_error(pos, START, END)
    assert mean_err == pytest.approx(0.0, abs=1e-9)
    assert max_err == pytest.approx(0.0, abs=1e-9)


def test_bowed_reach_max_error_two_cm():
    _, pos = min_jerk_reach(bow_m=0.02)
    assert m.rom(pos, START, END) == pytest.approx(0.30, abs=1e-6)
    mean_err, max_err = m.path_error(pos, START, END)
    assert max_err == pytest.approx(0.02, abs=1e-4)
    assert 0.0 < mean_err < max_err


def test_rom_is_along_axis_only():
    # Back-and-forth reach covering 0.10..0.25 m along the axis, with sideways wobble.
    s = np.linspace(0.10, 0.25, 50)
    pos = START + np.outer(s, (END - START) / 0.30)
    pos[:, 2] += 0.05
    assert m.rom(pos, START, END) == pytest.approx(0.15, abs=1e-9)


# --- force ------------------------------------------------------------------

def test_force_stats_peak_and_mean():
    force = np.array([[3.0, 4.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 2.0]])
    peak, mean = m.force_stats(force)
    assert peak == pytest.approx(5.0)
    assert mean == pytest.approx(8.0 / 3.0)


# --- sparc ------------------------------------------------------------------

def test_sparc_matches_reference_docstring_example():
    # Example from scripts/smoothness.py in github.com/siva82kb/SPARC.
    t = np.arange(-1, 1, 0.01)
    move = np.exp(-5 * pow(t, 2))
    assert "%.5f" % m.sparc(move, fs=100.0) == "-1.41403"


def test_sparc_tremor_is_less_smooth():
    t, speed = min_jerk_speed()
    tremor = speed + 0.1 * speed.max() * np.sin(2 * np.pi * 5.0 * t)
    clean = m.sparc(speed, FS)
    shaky = m.sparc(tremor, FS)
    assert clean < 0 and shaky < 0
    assert clean > shaky


# --- contribution -----------------------------------------------------------

def test_contribution_force_along_motion_is_one():
    t, pos = min_jerk_reach()
    vel = np.gradient(pos, t, axis=0)
    force = 5.0 * (END - START) / 0.30 * np.ones((len(t), 1))
    assert m.contribution(force, vel, START, END) == pytest.approx(1.0)


def test_contribution_force_against_motion_is_zero():
    t, pos = min_jerk_reach()
    vel = np.gradient(pos, t, axis=0)
    force = -5.0 * (END - START) / 0.30 * np.ones((len(t), 1))
    assert m.contribution(force, vel, START, END) == pytest.approx(0.0)


def test_contribution_no_work_is_zero():
    vel = np.zeros((10, 3))
    force = np.ones((10, 3))
    assert m.contribution(force, vel, START, END) == 0.0


def test_contribution_half_and_half():
    vel = np.tile([0.1, 0.0, 0.0], (10, 1))
    force = np.tile([2.0, 0.0, 0.0], (10, 1))
    force[5:] *= -1
    assert m.contribution(force, vel, START, END) == pytest.approx(0.5)


# --- rep_metrics ------------------------------------------------------------

def test_rep_metrics_keys_and_values():
    t, pos = min_jerk_reach()
    force = np.tile([5.0, 0.0, 0.0], (len(t), 1))
    r = m.rep_metrics(t, pos, force, START, END)
    assert set(r) == {
        "duration_s", "rom_m", "path_err_mean_m", "path_err_max_m",
        "sparc", "peak_force_n", "mean_force_n", "contribution",
    }
    assert r["duration_s"] == pytest.approx(1.5)
    assert r["rom_m"] == pytest.approx(0.30, abs=1e-6)
    assert r["path_err_max_m"] == pytest.approx(0.0, abs=1e-9)
    assert r["sparc"] < 0
    assert r["peak_force_n"] == pytest.approx(5.0)
    assert r["mean_force_n"] == pytest.approx(5.0)
    assert r["contribution"] == pytest.approx(1.0)
    assert all(isinstance(v, float) for v in r.values())


def test_rep_metrics_keys_match_rep_result_fields():
    from dataclasses import fields
    from server.contract import RepResult

    t, pos = min_jerk_reach()
    r = m.rep_metrics(t, pos, np.ones((len(t), 3)), START, END)
    assert set(r) <= {f.name for f in fields(RepResult)}


# --- bad input --------------------------------------------------------------

EMPTY = np.zeros((0, 3))
ONE = np.zeros((1, 3))


@pytest.mark.parametrize("pts", [EMPTY, ONE])
def test_empty_or_single_sample_raises(pts):
    with pytest.raises(ValueError):
        m.rom(pts, START, END)
    with pytest.raises(ValueError):
        m.path_error(pts, START, END)
    with pytest.raises(ValueError):
        m.force_stats(pts)
    with pytest.raises(ValueError):
        m.sparc(pts[:, 0], FS)
    with pytest.raises(ValueError):
        m.contribution(pts, pts, START, END)
    with pytest.raises(ValueError):
        m.rep_metrics(np.arange(len(pts)) / FS, pts, pts, START, END)


def test_zero_length_reach_raises():
    _, pos = min_jerk_reach()
    with pytest.raises(ValueError):
        m.rom(pos, START, START)
