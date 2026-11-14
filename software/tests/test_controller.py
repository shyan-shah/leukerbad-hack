"""Tests for software/controller.py (package S2)."""

import numpy as np
import pytest

from software.controller import (
    K_ASSIST,
    K_RESIST,
    K_WALL,
    MAX_LEAD,
    RESCUE_DIAL,
    T_OUT_S,
    command,
    reach_axis_index,
    reference_progress,
)
from software.paths import LinePath

START = (0.45, 0.0, 0.30)
L = 0.30


def make_path(axis: int = 0, sign: int = 1, start=START, length: float = L) -> LinePath:
    end = list(start)
    end[axis] += sign * length
    return LinePath(start=tuple(start), end=tuple(end))


PATH = make_path()


def hand_at(path: LinePath, s: float, side=(0.0, 0.0, 0.0)) -> tuple:
    p = path.point_at(s) + np.asarray(side, dtype=float)
    return tuple(p)


def along(path: LinePath, target, pos) -> float:
    """Signed distance from hand to target along the path axis (+ toward the end)."""
    return float(np.dot(np.asarray(target) - np.asarray(pos), path.axis()))


def on_segment(path: LinePath, p) -> bool:
    _, _, dist = path.closest(p)
    s = float(np.dot(np.asarray(p) - np.asarray(path.start), path.axis()) / path.length())
    return dist < 1e-9 and -1e-9 <= s <= 1 + 1e-9


# --- assist -----------------------------------------------------------------

def test_assist_hand_behind_reference_leads_by_at_most_max_lead():
    t = T_OUT_S / 2  # reference at s = 0.5
    s_hand = 0.1
    pos = hand_at(PATH, s_hand)
    target, k = command(1.0, "out", s_hand, t, pos, PATH, False)
    lead = along(PATH, target, pos)
    assert 0 < lead <= MAX_LEAD + 1e-12
    assert lead == pytest.approx(MAX_LEAD)  # 0.12 m behind, capped
    assert k == (K_ASSIST, K_WALL, K_WALL)
    assert k[0] == 400.0


def test_assist_small_lag_leads_by_the_lag_only():
    t = T_OUT_S / 2
    ref = reference_progress("out", t)
    s_hand = ref - 0.02 / L  # 2 cm behind
    pos = hand_at(PATH, s_hand)
    target, _ = command(1.0, "out", s_hand, t, pos, PATH, False)
    assert along(PATH, target, pos) == pytest.approx(0.02)


def test_assist_hand_ahead_of_reference_target_on_hand():
    t = 0.5  # reference barely moved
    s_hand = 0.6
    pos = hand_at(PATH, s_hand)
    target, k = command(1.0, "out", s_hand, t, pos, PATH, False)
    np.testing.assert_allclose(target, pos, atol=1e-12)
    assert k[0] == K_ASSIST


def test_assist_stiffness_scales_with_dial():
    pos = hand_at(PATH, 0.2)
    _, k = command(0.5, "out", 0.2, 1.0, pos, PATH, False)
    assert k == (0.5 * K_ASSIST, K_WALL, K_WALL)


def test_assist_back_phase_leads_toward_start():
    t = T_OUT_S / 2  # back reference at s = 0.5
    s_hand = 0.9
    pos = hand_at(PATH, s_hand)
    target, _ = command(1.0, "back", s_hand, t, pos, PATH, False)
    assert along(PATH, target, pos) == pytest.approx(-MAX_LEAD)


def test_assist_back_phase_hand_ahead_target_on_hand():
    s_hand = 0.2  # already nearer the start than the back reference
    pos = hand_at(PATH, s_hand)
    target, _ = command(1.0, "back", s_hand, 1.0, pos, PATH, False)
    np.testing.assert_allclose(target, pos, atol=1e-12)


def test_assist_at_t0_limp_hand_is_led_once_reference_moves():
    # reference clock starts when the rep arms; at t=0 nothing leads, a moment later it does
    pos = hand_at(PATH, 0.0)
    target0, _ = command(1.0, "out", 0.0, 0.0, pos, PATH, False)
    np.testing.assert_allclose(target0, pos, atol=1e-12)
    target1, _ = command(1.0, "out", 0.0, 1.5, pos, PATH, False)
    assert 0 < along(PATH, target1, pos) <= MAX_LEAD + 1e-12


# --- transparent ------------------------------------------------------------

def test_transparent_axis_floats_target_on_hand():
    pos = hand_at(PATH, 0.3)
    for phase in ("out", "back"):
        target, k = command(0.0, phase, 0.3, 2.0, pos, PATH, False)
        assert k == (0.0, K_WALL, K_WALL)
        np.testing.assert_allclose(target, pos, atol=1e-12)


# --- resist -----------------------------------------------------------------

@pytest.mark.parametrize("phase", ["out", "back"])
def test_resist_target_max_lead_behind_hand(phase):
    s_hand = 0.6
    pos = hand_at(PATH, s_hand)
    target, k = command(-1.0, phase, s_hand, 2.0, pos, PATH, False)
    assert along(PATH, target, pos) == pytest.approx(-0.05)
    assert k == (K_RESIST, K_WALL, K_WALL)
    assert k[0] == 300.0


def test_resist_never_beyond_start():
    s_hand = 0.05  # 1.5 cm from the start
    pos = hand_at(PATH, s_hand)
    target, _ = command(-1.0, "out", s_hand, 1.0, pos, PATH, False)
    np.testing.assert_allclose(target, PATH.start, atol=1e-12)


def test_resist_stiffness_scales_with_dial():
    pos = hand_at(PATH, 0.5)
    _, k = command(-0.4, "out", 0.5, 1.0, pos, PATH, False)
    assert k[0] == pytest.approx(0.4 * K_RESIST)


# --- walls, path segment, rescue --------------------------------------------

@pytest.mark.parametrize("dial", [1.0, 0.5, 0.0, -0.5, -1.0])
@pytest.mark.parametrize("phase", ["out", "back"])
def test_walls_on_other_axes_and_target_on_line(dial, phase):
    pos = hand_at(PATH, 0.4, side=(0.0, 0.02, -0.015))  # hand off the line
    target, k = command(dial, phase, 0.4, 1.0, pos, PATH, False)
    assert k[1] == K_WALL and k[2] == K_WALL
    assert target[1] == pytest.approx(PATH.start[1])  # pulled back to the line
    assert target[2] == pytest.approx(PATH.start[2])


def test_target_never_leaves_segment_random():
    rng = np.random.default_rng(0)
    for _ in range(2000):
        axis = int(rng.integers(0, 3))
        sign = int(rng.choice([-1, 1]))
        path = make_path(axis, sign)
        dial = float(rng.uniform(-1.5, 1.5))
        phase = str(rng.choice(["out", "back"]))
        s_hand = float(rng.uniform(-0.3, 1.3))
        t = float(rng.uniform(-1.0, 6.0))
        pos = hand_at(path, s_hand, side=rng.uniform(-0.05, 0.05, 3))
        rescued = bool(rng.integers(0, 2))
        target, k = command(dial, phase, s_hand, t, pos, path, rescued)
        assert on_segment(path, target)
        assert 0.0 <= k[axis] <= max(K_ASSIST, K_RESIST)
        others = [k[i] for i in range(3) if i != axis]
        assert others == [K_WALL, K_WALL]
        # along-path offset from the (clamped) hand progress never exceeds MAX_LEAD
        s_c = float(np.clip(s_hand, 0, 1))
        assert abs(along(path, target, path.point_at(s_c))) <= MAX_LEAD + 1e-12


def test_rescue_raises_assist_dial():
    pos = hand_at(PATH, 0.1)
    _, k = command(0.2, "out", 0.1, 2.0, pos, PATH, True)
    assert k[0] == pytest.approx(RESCUE_DIAL * K_ASSIST)
    _, k = command(0.9, "out", 0.1, 2.0, pos, PATH, True)
    assert k[0] == pytest.approx(0.9 * K_ASSIST)


def test_rescue_on_resist_side_goes_transparent():
    pos = hand_at(PATH, 0.5)
    target, k = command(-0.8, "out", 0.5, 2.0, pos, PATH, True)
    assert k[0] == 0.0
    np.testing.assert_allclose(target, pos, atol=1e-12)


def test_dial_is_clamped():
    pos = hand_at(PATH, 0.1)
    _, k = command(3.0, "out", 0.1, 2.0, pos, PATH, False)
    assert k[0] == K_ASSIST
    _, k = command(-3.0, "out", 0.1, 2.0, pos, PATH, False)
    assert k[0] == K_RESIST


# --- reach axis and sign ----------------------------------------------------

@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("sign", [1, -1])
def test_reach_axis_and_sign(axis, sign):
    path = make_path(axis, sign)
    assert reach_axis_index(path) == axis
    wall_axes = [i for i in range(3) if i != axis]

    # assist, hand behind: target leads toward the end by MAX_LEAD
    pos = hand_at(path, 0.1)
    target, k = command(1.0, "out", 0.1, T_OUT_S / 2, pos, path, False)
    assert k[axis] == K_ASSIST
    assert all(k[i] == K_WALL for i in wall_axes)
    delta = np.asarray(target) - np.asarray(pos)
    assert delta[axis] == pytest.approx(sign * MAX_LEAD)
    assert np.allclose(delta[wall_axes], 0.0)

    # resist: target behind the hand, toward the start
    pos = hand_at(path, 0.6)
    target, k = command(-1.0, "out", 0.6, 1.0, pos, path, False)
    assert k[axis] == K_RESIST
    delta = np.asarray(target) - np.asarray(pos)
    assert delta[axis] == pytest.approx(-sign * MAX_LEAD)

    # transparent
    _, k = command(0.0, "out", 0.6, 1.0, pos, path, False)
    assert k[axis] == 0.0
    assert all(k[i] == K_WALL for i in wall_axes)


# --- input validation -------------------------------------------------------

def test_bad_phase_raises():
    with pytest.raises(ValueError):
        command(1.0, "idle", 0.0, 0.0, START, PATH, False)


def test_diagonal_path_raises():
    diag = LinePath(start=(0.0, 0.0, 0.0), end=(0.2, 0.2, 0.0))
    with pytest.raises(ValueError):
        command(1.0, "out", 0.0, 0.0, (0.0, 0.0, 0.0), diag, False)


def test_returns_plain_float_tuples():
    target, k = command(1.0, "out", 0.1, 1.0, hand_at(PATH, 0.1), PATH, False)
    assert isinstance(target, tuple) and len(target) == 3
    assert isinstance(k, tuple) and len(k) == 3
    assert all(type(v) is float for v in (*target, *k))
