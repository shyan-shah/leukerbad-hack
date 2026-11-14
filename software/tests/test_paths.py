"""Tests for software/paths.py (package S0c)."""

import numpy as np
import pytest

from software.paths import LinePath, lead_target, min_jerk

PATH = LinePath(start=(0.40, 0.00, 0.10), end=(0.70, 0.00, 0.10))  # 0.30 m along +x


# --- LinePath basics --------------------------------------------------------

def test_length_and_axis():
    assert PATH.length() == pytest.approx(0.30)
    np.testing.assert_allclose(PATH.axis(), [1.0, 0.0, 0.0])
    assert np.linalg.norm(PATH.axis()) == pytest.approx(1.0)


def test_point_at_clamps():
    np.testing.assert_allclose(PATH.point_at(0.0), [0.40, 0.0, 0.10])
    np.testing.assert_allclose(PATH.point_at(0.5), [0.55, 0.0, 0.10])
    np.testing.assert_allclose(PATH.point_at(1.0), [0.70, 0.0, 0.10])
    np.testing.assert_allclose(PATH.point_at(-0.3), [0.40, 0.0, 0.10])
    np.testing.assert_allclose(PATH.point_at(1.7), [0.70, 0.0, 0.10])


def test_zero_length_path_raises():
    p = LinePath(start=(0.1, 0.2, 0.3), end=(0.1, 0.2, 0.3))
    assert p.length() == 0.0
    with pytest.raises(ValueError):
        p.axis()
    with pytest.raises(ValueError):
        p.closest((0.1, 0.2, 0.3))


def test_bad_pos_shape_raises():
    with pytest.raises(ValueError):
        PATH.closest((0.5, 0.0))


# --- closest ------------------------------------------------------------------

def test_closest_on_segment():
    point, s, d = PATH.closest((0.49, 0.0, 0.10))
    np.testing.assert_allclose(point, [0.49, 0.0, 0.10])
    assert s == pytest.approx(0.3)
    assert d == pytest.approx(0.0, abs=1e-12)


def test_closest_beside_segment():
    point, s, d = PATH.closest((0.55, 0.03, 0.06))
    np.testing.assert_allclose(point, [0.55, 0.0, 0.10])
    assert s == pytest.approx(0.5)
    assert d == pytest.approx(0.05)  # sqrt(0.03^2 + 0.04^2)


def test_closest_beyond_end():
    point, s, d = PATH.closest((0.80, 0.0, 0.10))
    np.testing.assert_allclose(point, [0.70, 0.0, 0.10])
    assert s == 1.0
    assert d == pytest.approx(0.10)


def test_closest_before_start():
    point, s, d = PATH.closest((0.37, 0.04, 0.10))
    np.testing.assert_allclose(point, [0.40, 0.0, 0.10])
    assert s == 0.0
    assert d == pytest.approx(0.05)  # sqrt(0.03^2 + 0.04^2)


def test_closest_on_diagonal_path():
    p = LinePath(start=(0.0, 0.0, 0.0), end=(0.3, 0.3, 0.0))
    point, s, d = p.closest((0.3, 0.0, 0.0))
    np.testing.assert_allclose(point, [0.15, 0.15, 0.0])
    assert s == pytest.approx(0.5)
    assert d == pytest.approx(0.15 * np.sqrt(2))


# --- min_jerk -----------------------------------------------------------------

def test_min_jerk_endpoints_and_midpoint():
    assert min_jerk(0.0, 1.0, 2.0, 0.0) == pytest.approx(0.0)
    assert min_jerk(0.0, 1.0, 2.0, 1.0) == pytest.approx(0.5)
    assert min_jerk(0.0, 1.0, 2.0, 2.0) == pytest.approx(1.0)
    assert min_jerk(1.0, 0.0, 2.0, 2.0) == pytest.approx(0.0)  # return stroke


def test_min_jerk_clamped_outside_duration():
    assert min_jerk(0.2, 0.8, 1.5, -1.0) == 0.2
    assert min_jerk(0.2, 0.8, 1.5, 5.0) == 0.8


def test_min_jerk_zero_slope_at_both_ends():
    T, h = 1.5, 1e-5
    slope_start = (min_jerk(0.0, 1.0, T, h) - min_jerk(0.0, 1.0, T, 0.0)) / h
    slope_end = (min_jerk(0.0, 1.0, T, T) - min_jerk(0.0, 1.0, T, T - h)) / h
    peak_slope = (min_jerk(0.0, 1.0, T, T / 2 + h) - min_jerk(0.0, 1.0, T, T / 2 - h)) / (2 * h)
    assert abs(slope_start) < 1e-6
    assert abs(slope_end) < 1e-6
    assert peak_slope == pytest.approx(1.875 / T, rel=1e-4)  # known min-jerk peak


def test_min_jerk_monotonic():
    ts = np.linspace(0.0, 1.0, 201)
    s = np.array([min_jerk(0.0, 1.0, 1.0, t) for t in ts])
    assert np.all(np.diff(s) >= 0)


def test_min_jerk_bad_duration_raises():
    with pytest.raises(ValueError):
        min_jerk(0.0, 1.0, 0.0, 0.5)


# --- lead_target --------------------------------------------------------------

def test_lead_target_ahead_and_behind():
    hand = (0.50, 0.02, 0.10)  # closest point x = 0.50
    np.testing.assert_allclose(lead_target(PATH, hand, 0.03), [0.53, 0.0, 0.10])
    np.testing.assert_allclose(lead_target(PATH, hand, -0.03), [0.47, 0.0, 0.10])
    np.testing.assert_allclose(lead_target(PATH, hand, 0.0), [0.50, 0.0, 0.10])


def test_lead_target_respects_max_lead():
    hand = (0.50, 0.0, 0.10)
    ahead = lead_target(PATH, hand, 0.20, max_lead_m=0.05)
    behind = lead_target(PATH, hand, -0.20, max_lead_m=0.05)
    np.testing.assert_allclose(ahead, [0.55, 0.0, 0.10])
    np.testing.assert_allclose(behind, [0.45, 0.0, 0.10])
    for lead in np.linspace(-0.2, 0.2, 41):
        target = lead_target(PATH, hand, lead, max_lead_m=0.05)
        assert np.linalg.norm(target - np.array([0.50, 0.0, 0.10])) <= 0.05 + 1e-12


def test_lead_target_stops_at_path_ends():
    np.testing.assert_allclose(lead_target(PATH, (0.68, 0.0, 0.10), 0.05), [0.70, 0.0, 0.10])
    np.testing.assert_allclose(lead_target(PATH, (0.42, 0.0, 0.10), -0.05), [0.40, 0.0, 0.10])
    np.testing.assert_allclose(lead_target(PATH, (0.90, 0.0, 0.10), 0.05), [0.70, 0.0, 0.10])
    np.testing.assert_allclose(lead_target(PATH, (0.20, 0.0, 0.10), -0.05), [0.40, 0.0, 0.10])


def test_lead_target_always_on_path():
    rng = np.random.default_rng(0)
    for _ in range(200):
        hand = rng.uniform([0.2, -0.2, -0.1], [0.9, 0.2, 0.3])
        target = lead_target(PATH, hand, rng.uniform(-0.1, 0.1))
        _, _, d = PATH.closest(target)
        assert d == pytest.approx(0.0, abs=1e-12)


def test_lead_target_negative_max_raises():
    with pytest.raises(ValueError):
        lead_target(PATH, (0.5, 0.0, 0.1), 0.01, max_lead_m=-0.01)
