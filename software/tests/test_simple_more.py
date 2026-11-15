"""RowEngine and StrengthEngine (software/simple_more.py) on SimArm with the real arm's effects: 4.5 N
Coulomb friction and the measured empty-handle reading (10 N/m with pose, 3 to 7 N while moving).
All simulated: nothing here says how the real arm behaves.

The hands are scripted. ``RowHand`` follows a planned position measured from the far end towards the
patient; ``PushHand`` pushes with a set force while the strength test says "Push and hold".
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from server.contract import RepResult, Sample
from software import simple, simple_more
from software.simple import DT, FORCE_CAP_N, LEAD_M, LEVELS, BandEngine
from software.simple_more import (EASE_M, EASED_MSG, FAR_M, PUSH_S, READY_S, REST_S, ROW_IDS, RowEngine,
                                  StrengthEngine, engine_class, row_level)
from software.sim_arm import PASSIVE_LOAD_N, SimArm
from software.tests.test_simple import REAL, START, STYLES, cycle

FAR = (START[0] + FAR_M, START[1], START[2])


class RowHand:
    """A scripted hand for Row: ``plan(t)`` is the distance pulled from the far end towards the patient."""
    strength = 0.0                  # SimArm's own friction helper off: this hand pulls through the friction

    def __init__(self, plan, sign0=1.0, kp=1500.0, kd=40.0, cap=48.0, side_n=0.0):
        self.plan, self.sign0, self.kp, self.kd, self.cap, self.side_n = plan, sign0, kp, kd, cap, side_n
        self.present = True
        self.t0 = None
        self.fade = None
        self.far_x = START[0] + sign0 * FAR_M

    def release(self, t: float, over_s: float = 0.0) -> None:
        if over_s <= 0:
            self.present = False
        else:
            self.fade = (t, over_s)

    def effort(self, t, pos, vel, goal):
        if self.t0 is None:
            self.t0 = t
        s = -self.sign0 * (pos[0] - self.far_x)                  # m pulled towards the patient
        v = -self.sign0 * vel[0]
        f = float(np.clip(self.kp * (self.plan(t - self.t0) - s) - self.kd * v, -self.cap, self.cap))
        out = np.array([-self.sign0 * f, self.side_n * math.sin(2 * math.pi * 2.0 * t), 0.0])
        if self.fade is not None:
            out *= max(0.0, 1.0 - (t - self.fade[0]) / self.fade[1])
            if t - self.fade[0] >= self.fade[1]:
                self.present = False
        return out


def make_row(level=1, plan=None, sign=1, present=True, to_band=True, arm_kw=None, **kw):
    hand = RowHand(plan or cycle(), sign0=float(sign))
    hand.present = present
    arm = SimArm(hand, start_pos=START, realtime=False, **(REAL if arm_kw is None else arm_kw))
    arm.connect()
    samples: list[Sample] = []
    reps: list[RepResult] = []
    kw.setdefault("prepare", True)
    eng = RowEngine(arm, "sess-r", "pat-r", True, reach_axis=0, reach_sign=sign, on_sample=samples.append,
                    on_rep=reps.append, exercise=f"row_{level}", **kw)
    eng.start()
    if to_band:
        run_to_band(eng)
    return eng, arm, hand, samples, reps


def run_to_band(eng, max_s=40.0):
    for _ in range(int(max_s / DT)):
        if eng.stage in ("band", "error"):
            break
        eng.run_for(DT)
    assert eng.stage == "band", (eng.stage, eng.snapshot()["message"])


def pulled(sample_or_pos, sign=1) -> float:
    """m pulled from the far end towards the patient."""
    p = sample_or_pos.pos if hasattr(sample_or_pos, "pos") else sample_or_pos
    return -sign * (p[0] - (START[0] + sign * FAR_M))


def stretch_run(samples, i0=0):
    """Speeds (m/s) of the samples in which the arm was moving by itself, from index i0 on."""
    v = [float(np.linalg.norm(s.vel)) for s in samples[i0:]]
    moving = [i for i, x in enumerate(v) if x > 0.005]
    return v[moving[0]:moving[-1] + 1] if moving else []


def assert_continuous(v, what):
    assert len(v) > 300, (what, len(v))                          # 28 cm at 5 cm/s is 5.6 s
    mid = v[len(v) // 10: len(v) - len(v) // 10]
    assert min(mid) >= 0.03 and max(mid) <= 0.06, (what, min(mid), max(mid))


# --------------------------------------------------------------------------- ids, interface, Push untouched

def test_ids_levels_and_engine_classes():
    assert ROW_IDS == ("row_1", "row_2", "row_3", "row_4")
    assert [row_level(i) for i in ROW_IDS] == [1, 2, 3, 4] and row_level("push_1") is None
    assert engine_class("push_2") is BandEngine and engine_class("row_2") is RowEngine
    assert engine_class("strength") is StrengthEngine and engine_class("reach") is None
    with pytest.raises(ValueError):
        RowEngine(None, "s", "p", True, exercise="push_1")
    with pytest.raises(ValueError):
        StrengthEngine(None, "s", "p", True, exercise="row_1")


def test_push_constants_are_reused_not_redefined():
    for name in ("LEAD_M", "K_WALL", "OUT_M", "BACK_M", "TURN_BACK_M", "COUNTDOWN_S", "V_RETURN", "V_SNAP",
                 "GATE_SPEED", "GATE_FORCE_N", "HOME_ABORT_N", "MAX_BASELINE_N", "FORCE_CAP_N", "LEVELS"):
        if hasattr(simple_more, name):
            assert getattr(simple_more, name) is getattr(simple, name), name
    assert BandEngine.GROUP == "push"
    eng = BandEngine(None, "s", "p", True, exercise="push_3")
    assert eng.exercise == "push_3" and eng.snapshot()["group"] == "push"


def test_row_levels_follow_simple_levels(monkeypatch):
    """Shyan's Level 4 change carries over: the row stiffness is read from simple.LEVELS at run time."""
    eng, arm, hand, samples, reps = make_row(4, present=False)
    eng.run_for(0.2)                                             # the simulated arm applies a stiffness 50 ms late
    assert eng.level_force_n == LEVELS[4] and arm._k[0] == pytest.approx(LEVELS[4] / LEAD_M)
    assert eng.snapshot()["level_force_n"] == LEVELS[4]


# --------------------------------------------------------------------------- Row: the start

def test_row_start_sequence_messages_and_fields():
    eng, arm, hand, samples, reps = make_row(2, present=False, to_band=False)
    assert eng.stage == "countdown"
    seen = []
    for _ in range(int(40.0 / DT)):
        m = eng.snapshot()["message"]
        if m and (not seen or seen[-1] != m):
            seen.append(m)
        if eng.stage == "band":
            break
        eng.run_for(DT)
    text = " | ".join(seen)
    assert seen[0] == "Hands off: zeroing in 3"
    assert "Hands off: moving to the start position in 3" in seen and "Hands off: moving to the start position in 1" in seen
    assert "The arm is moving to the start position. Hands off." in seen
    moved = seen.index("The arm is moving to the start position. Hands off.")
    assert "Hands off: zeroing in 2" in seen[moved:] and "Zeroing. Hands off." in seen[moved:], text   # the second zero
    assert eng.stage == "band" and arm.get_state().mode == "compliant"
    assert np.allclose(arm.get_state().pos, FAR, atol=1e-3)
    snap = eng.snapshot()
    for key in ("pos", "target", "phase", "rep_idx", "rep_count", "reps_target", "done", "level", "level_force_n",
                "message", "countdown_s", "path_start", "path_end", "force_cap_n", "exercise"):
        assert key in snap, key
    assert snap["exercise"] == "row_2" and snap["group"] == "row" and snap["level"] == 2 and snap["kind"] == "resist"
    assert np.allclose(snap["path_start"], FAR) and np.allclose(snap["path_end"], (FAR[0] - 0.30, 0.0, 0.30))
    assert snap["message"] is None and snap["countdown_s"] is None and snap["force_cap_n"] == FORCE_CAP_N
    assert eng.stiffness_commands == 1


def test_row_path_is_the_far_end_from_the_first_sample_on():
    eng, arm, hand, samples, reps = make_row(1, present=False, to_band=False)
    snap = eng.snapshot()
    assert np.allclose(snap["path_start"], FAR) and np.allclose(snap["path_end"], (FAR[0] - 0.30, 0.0, 0.30))


def test_row_with_the_real_arm_reach_direction():
    plan = cycle()
    eng, arm, hand, samples, reps = make_row(3, plan, sign=-1)
    assert np.allclose(arm.get_state().pos, (START[0] - FAR_M, 0.0, 0.30), atol=1e-3)
    eng.run_for(3 * plan.period + 1.0)
    assert eng.rep_count == 3
    snap = eng.snapshot()
    assert np.allclose(snap["path_start"], (START[0] - FAR_M, 0.0, 0.30))
    assert np.allclose(snap["path_end"], (START[0] - FAR_M + 0.30, 0.0, 0.30))       # towards the patient


def test_the_move_to_the_far_end_is_one_continuous_move():
    eng, arm, hand, samples, reps = make_row(1, present=False)
    v = stretch_run(samples)
    assert_continuous(v, "to the far end")
    assert max(v) <= 0.06


def test_the_move_waits_while_a_hand_presses_over_6_n():
    eng, arm, hand, samples, reps = make_row(1, present=False, to_band=False)
    for _ in range(2000):
        if eng.stage == "far_count":
            break
        eng.run_for(DT)
    assert eng.stage == "far_count"
    arm.force_offset = np.array([0.0, 8.0, 0.0])                 # something presses on the handle with 8 N
    eng.run_for(8.0)
    assert eng.stage == "far_count" and np.allclose(arm.get_state().pos, START, atol=1e-6)
    assert eng.snapshot()["message"] == "Hands off: moving to the start position in 3"
    arm.force_offset = np.zeros(3)
    eng.run_for(3.2)
    assert eng.stage in ("far_move", "far_zero_count") or arm.get_state().pos[0] > START[0] + 0.01


def test_the_move_holds_at_once_when_the_reading_changes_by_10_n():
    eng, arm, hand, samples, reps = make_row(1, present=False, to_band=False)
    orig = arm.step

    def step(dt):
        orig(dt)
        if arm.moving and arm._pos[0] > START[0] + 0.10:
            arm.force_offset = np.array([18.0, 0.0, 0.0])        # a hand gets in the way mid-move (the moving
                                                                 # empty reading alone is 3 to 7 N: no hold)
    arm.step = step
    for _ in range(int(30.0 / DT)):
        if eng.stage == "error":
            break
        eng.run_for(DT)
    assert eng.stage == "error" and arm.get_state().mode == "hold"
    assert START[0] + 0.10 < arm.get_state().pos[0] < START[0] + 0.12        # held where it was, within a tick or two
    assert eng.snapshot()["message"].startswith("Not started: the move ended")
    assert eng.stiffness_commands == 0


def test_a_handle_that_does_not_read_empty_is_refused():
    hand = RowHand(cycle())
    hand.present = False
    arm = SimArm(hand, start_pos=START, realtime=False, **REAL)
    arm.connect()
    arm.zero_force = lambda: None                                # the zero did nothing: the reading stays
    arm.force_offset = np.array([0.0, 0.0, 9.0])
    eng = RowEngine(arm, "s", "p", True, exercise="row_1", prepare=True)
    eng.start()
    eng.run_for(4.0)
    assert eng.stage == "error" and "Hands off" in eng.snapshot()["message"]
    assert np.allclose(arm.get_state().pos, START, atol=1e-6)    # it never moved


# --------------------------------------------------------------------------- Row: reps

@pytest.mark.parametrize("level", [1, 2, 3, 4])
@pytest.mark.parametrize("style", list(STYLES))
def test_ten_rows_are_counted_as_exactly_ten(level, style):
    plan = cycle(**STYLES[style])
    eng, arm, hand, samples, reps = make_row(level, plan)
    hand.side_n = 3.0 if style == "wobbly" else 0.0
    eng.run_for(10 * plan.period + 1.0)
    assert arm.get_state().mode == "compliant", arm.get_state().fault        # no trip
    assert eng.rep_count == 10 and len(reps) == 10
    assert [r.idx for r in reps] == list(range(10))
    for r in reps:
        assert r.mode == "resist" and r.completed and r.simulated and not r.rescued
        assert 0.24 <= r.rom_m <= 0.31 and r.duration_s > 1.0
        assert LEVELS[level] - 1.0 <= r.peak_force_n <= LEVELS[level] + 12.0, r.peak_force_n
        assert 0.0 < r.mean_force_n < r.peak_force_n
    assert eng.done and eng.snapshot()["message"] == "Set finished"
    assert eng.stiffness_commands == 1
    # never pulled more than 5 cm past the start pose
    assert max(pulled(s) for s in samples) < FAR_M + 0.05


def test_a_ten_centimetre_pull_is_not_counted():
    plan = cycle(depth=0.10)
    eng, arm, hand, samples, reps = make_row(2, plan)
    n = len(samples)
    eng.run_for(4 * plan.period)
    assert max(pulled(s) for s in samples[n:]) > 0.08
    assert eng.rep_count == 0 and reps == []
    assert {s.phase for s in samples[n:]} <= {"idle", "out"}


def test_row_phases_and_rep_idx_for_the_app():
    plan = cycle()
    eng, arm, hand, samples, reps = make_row(1, plan)
    n = len(samples)
    assert all(s.phase == "idle" and s.rep_idx == -1 for s in samples[:n])   # countdowns and the move
    eng.run_for(2 * plan.period + 0.5)
    band = samples[n:]
    assert {s.phase for s in band} == {"idle", "out", "back"}
    first_out = [s.phase for s in band].index("out")
    assert band[first_out].rep_idx == 0
    assert any(s.phase == "back" and s.rep_idx == 1 for s in band)
    # the target (the band's anchor) is on the far side of the hand: it pulls back to the far end
    out = [s for s in band if s.phase == "out" and pulled(s) > 0.10]
    assert out and all(pulled(s.target) < pulled(s) for s in out)


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_an_empty_handle_never_leaves_the_far_end(level):
    eng, arm, hand, samples, reps = make_row(level, present=False)
    n = len(samples)
    eng.run_for(20.0)
    assert max(abs(pulled(s)) for s in samples[n:]) < 0.002
    assert max(np.linalg.norm(np.array(s.pos) - FAR) for s in samples[n:]) < 0.002
    assert eng.rep_count == 0 and {s.phase for s in samples[n:]} == {"idle"} and arm.get_state().mode == "compliant"


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_row_band_force_is_steady_on_the_way_out(level):
    """The spring the simulated arm really applies, between 6 and 27 cm of pull: within 2 N of the level."""
    plan = cycle(out_s=4.0)
    eng, arm, hand, samples, reps = make_row(level, plan)
    f = []
    for _ in range(int(4.0 / DT)):
        eng.tick()
        if 0.06 <= pulled(arm._pos) <= 0.27 and eng.phase == "out":
            f.append(float(arm._k[0] * (arm._target[0] - arm._pos[0])))      # + = towards the far end (+x)
        arm.step(DT)
    assert len(f) > 100 and min(f) > LEVELS[level] - 2.0 and max(f) < LEVELS[level] + 2.0, (min(f), max(f))


def test_row_turn_back_and_over_travel():
    plan = cycle(depth=0.325, out_s=3.5, dwell_s=60.0)
    eng, arm, hand, samples, reps = make_row(1, plan)
    msgs = []
    for _ in range(int(5.0 / DT)):
        eng.run_for(DT)
        msgs.append((pulled(arm._pos), eng.snapshot()["message"], eng.snapshot()["over_travel"]))
    assert any(m == "Turn back" for p, m, o in msgs if p >= 0.27)
    assert not any(m == "Turn back" for p, m, o in msgs if p < 0.265)
    assert any(o for p, m, o in msgs if p > 0.312)
    assert arm.get_state().mode == "compliant"                   # 4.5 cm past the start pose is inside the box


def test_row_level_change_mid_set_keeps_counting():
    plan = cycle()
    eng, arm, hand, samples, reps = make_row(1, plan)
    eng.run_for(3 * plan.period + 0.2)
    assert eng.rep_count == 3 and eng.stiffness_commands == 1
    eng.run_for(1.5)                                             # mid-pull of the fourth
    eng.set_level(3)
    eng.run_for(1.0)
    assert eng.level == 3 and eng.exercise == "row_3" and eng.snapshot()["level_force_n"] == LEVELS[3]
    assert eng.stiffness_commands == 6                           # the one command, then a 5-step ramp
    assert arm._k[0] == pytest.approx(LEVELS[3] / LEAD_M)
    eng.run_for(7 * plan.period)
    assert eng.rep_count == 10 and arm.get_state().mode == "compliant"
    assert eng.stop().exercise == "row_3"


# --------------------------------------------------------------------------- Row: letting go

def hold_at_full_pull(level, **kw):
    plan = cycle(depth=0.30, out_s=3.0, dwell_s=60.0)
    eng, arm, hand, samples, reps = make_row(level, plan, **kw)
    eng.run_for(4.0)
    assert pulled(arm.get_state().pos) > 0.26
    return eng, arm, hand, samples


def back_speeds(eng, arm, seconds=12.0):
    v = []
    for _ in range(int(seconds / DT)):
        eng.tick()
        for _ in range(2):
            arm.step(DT / 2)
            v.append(float(np.linalg.norm(arm._vel)))
    return v


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_let_go_at_full_pull_comes_back_slowly(level):
    eng, arm, hand, samples = hold_at_full_pull(level)
    hand.release(arm._t, over_s=0.1)
    v = back_speeds(eng, arm)
    st = arm.get_state()
    assert st.mode == "compliant", st.fault
    assert max(v) < 0.15, max(v)
    assert pulled(st.pos) < 0.05 and eng.rep_count == 1


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_abrupt_let_go_at_full_pull_does_not_trip(level):
    eng, arm, hand, samples = hold_at_full_pull(level)
    hand.release(arm._t)
    v = back_speeds(eng, arm)
    st = arm.get_state()
    assert st.mode == "compliant", st.fault
    assert max(v) < 0.30 and max(v[20:]) < 0.15, (max(v), max(v[20:]))
    assert pulled(st.pos) < 0.05


# --------------------------------------------------------------------------- Row: stop and the return to the start

def test_row_stop_returns_to_the_start_pose_in_one_continuous_move():
    plan = cycle()
    eng, arm, hand, samples, reps = make_row(1, plan, return_home=True)
    eng.run_for(2 * plan.period + 0.5)
    hand.present = False
    eng.run_for(1.0)
    n = len(samples)
    s = eng.stop()
    assert s.n_reps == 2 and s.exercise == "row_1"
    assert np.allclose(arm.get_state().pos, START, atol=1e-3)
    assert eng.snapshot()["message"] == "Back at the start." and eng.snapshot()["countdown_s"] is None
    assert_continuous(stretch_run(samples, n), "back to the start")


def test_row_stop_waits_for_a_held_handle_and_does_not_move_it():
    plan = cycle(out_s=3.0, dwell_s=60.0)
    eng, arm, hand, samples, reps = make_row(2, plan, return_home=True)
    eng.run_for(4.0)
    here = arm.get_state().pos
    t_before = arm._t
    s = eng.stop()                                               # the hand is still pulling on it
    assert s.session_id == "sess-r" and "being held" in eng.snapshot()["message"]
    assert 9.5 < arm._t - t_before < 11.5
    assert np.allclose(arm.get_state().pos, here, atol=0.03)


def test_row_return_holds_when_something_presses_on_the_handle():
    eng, arm, hand, samples, reps = make_row(1, present=False, return_home=True)
    eng.run_for(1.0)
    orig = arm.step

    def step(dt):
        orig(dt)
        if arm.moving and arm._pos[0] < START[0] + 0.15:
            arm.force_offset = np.array([-18.0, 0.0, 0.0])
    arm.step = step
    s = eng.stop()
    assert s.n_reps == 0 and "Not returned to the start" in eng.snapshot()["message"]
    assert arm.get_state().mode == "hold" and START[0] + 0.13 < arm.get_state().pos[0] < START[0] + 0.15


def test_row_never_calls_set_test_limits():
    plan = cycle()
    eng, arm, hand, samples, reps = make_row(4, plan, to_band=False, return_home=True)
    calls = []
    arm.set_test_limits = lambda on: calls.append(on)
    run_to_band(eng)
    eng.run_for(2 * plan.period)
    hand.present = False
    eng.stop()
    assert calls == [] and not arm.test_limits_on


# --------------------------------------------------------------------------- Strength test

class PushHand:
    """Pushes along the reach with ``force_n`` while the engine says "Push and hold": up over ``rise_s``,
    then steady. After the try the force vanishes at once (``fall_s`` 0) or eases off."""
    strength = 0.0

    def __init__(self, force_n=20.0, rise_s=0.6, fall_s=0.0, sign=1.0):
        self.force_n, self.rise_s, self.fall_s, self.sign = force_n, rise_s, fall_s, sign
        self.present = True
        self.eng = None
        self._t_push = self._t_end = None
        self._f_end = 0.0

    def effort(self, t, pos, vel, goal):
        seg = self.eng._seg if self.eng is not None and self.eng.stage == "band" else None
        if seg == "push":
            if self._t_push is None:
                self._t_push, self._t_end = t, None
            f = self.force_n * min(1.0, (t - self._t_push) / self.rise_s)
            self._f_end = f
        else:
            if self._t_push is not None:
                self._t_push, self._t_end = None, t
            f = 0.0
            if self._t_end is not None and self.fall_s > 0:
                f = self._f_end * max(0.0, 1.0 - (t - self._t_end) / self.fall_s)
        return np.array([self.sign * f, 0.0, PASSIVE_LOAD_N])     # carries its own weight: SimArm adds 8 N of limb


def make_strength(hand=None, sign=1, to_band=True, **kw):
    hand = hand or PushHand(sign=float(sign))
    arm = SimArm(hand, start_pos=START, realtime=False, **REAL)
    arm.connect()
    samples: list[Sample] = []
    reps: list[RepResult] = []
    kw.setdefault("prepare", True)
    eng = StrengthEngine(arm, "sess-s", "pat-s", True, reach_axis=0, reach_sign=sign, on_sample=samples.append,
                         on_rep=reps.append, exercise="strength", **kw)
    hand.eng = eng
    eng.start()
    if to_band:
        run_to_band(eng)
    return eng, arm, hand, samples, reps


def run_tries(eng, arm, seconds):
    """Run and record (time since the band began, segment, message, countdown, speed at half ticks)."""
    log, v = [], []
    t0 = arm._t
    for _ in range(int(seconds / DT)):
        eng.tick()
        snap = eng.snapshot()
        log.append((arm._t - t0, snap["segment"], snap["message"], snap["countdown_s"], snap["phase"], snap["rep_idx"]))
        for _ in range(2):
            arm.step(DT / 2)
            v.append(float(np.linalg.norm(arm._vel)))
    return log, v


def test_strength_three_tries_with_the_right_timing():
    eng, arm, hand, samples, reps = make_strength()
    assert eng.stiffness_commands == 1 and arm.get_state().mode == "compliant"
    eng.run_for(0.2)
    assert arm._k[0] == pytest.approx(600.0) and arm._k[1] == pytest.approx(simple.K_WALL)
    snap = eng.snapshot()
    assert snap["exercise"] == "strength" and snap["group"] == "strength" and snap["kind"] == "test"
    assert snap["level"] is None and snap["level_force_n"] is None and snap["force_cap_n"] == FORCE_CAP_N
    assert snap["try"] == 1 and snap["tries"] == 3 and snap["reps_target"] == 3
    log, v = run_tries(eng, arm, 3 * (READY_S + PUSH_S + REST_S) + 0.5)
    seg_at = lambda t: next(x for x in log if x[0] >= t)
    for i in range(3):
        base = i * (READY_S + PUSH_S + REST_S) - 0.2
        ready, push, rest = seg_at(base + 0.5), seg_at(base + READY_S + 1.0), seg_at(base + READY_S + PUSH_S + 1.0)
        assert ready[1] == "ready" and ready[2] == "Get ready: 3" and ready[4] == "idle" and ready[5] == -1, ready
        assert push[1] == "push" and push[2] == "Push and hold" and push[4] == "out" and push[5] == i, push
        assert rest[1] == "rest" and rest[2] == "Rest" and rest[4] == "idle" and rest[5] == -1, rest
        assert 1.9 <= push[3] <= 2.1 and 3.9 <= rest[3] <= 4.1
    assert {x[2] for x in log if x[1] == "ready"} == {"Get ready: 3", "Get ready: 2", "Get ready: 1"}
    assert eng.rep_count == 3 and eng.done and log[-1][1] == "done" and log[-1][2] == "Set finished"
    assert [r.idx for r in reps] == [0, 1, 2]
    for r in reps:
        assert r.mode == "isometric" and r.completed and r.simulated
        assert r.peak_force_n == pytest.approx(20.0, abs=2.0), r.peak_force_n       # a simulated 20 N push
        assert 10.0 < r.mean_force_n < r.peak_force_n
        assert 0.015 < r.rom_m < 0.040 and r.duration_s == pytest.approx(PUSH_S, abs=0.05)
    snap = eng.snapshot()
    assert snap["best_force_n"] == max(r.peak_force_n for r in reps) and snap["last_force_n"] == reps[-1].peak_force_n
    assert eng.stiffness_commands == 1 and arm.get_state().mode == "compliant"


@pytest.mark.parametrize("force_n,fall_s", [(20.0, 0.0), (20.0, 0.1), (26.0, 0.0), (26.0, 0.1), (10.0, 0.0)])
def test_strength_release_never_faster_than_15_cm_per_s(force_n, fall_s):
    eng, arm, hand, samples, reps = make_strength(PushHand(force_n=force_n, fall_s=fall_s))
    log, v = run_tries(eng, arm, 3 * (READY_S + PUSH_S + REST_S) + 0.5)
    assert max(v) < 0.15, max(v)
    assert arm.get_state().mode == "compliant", arm.get_state().fault
    assert abs(arm.get_state().pos[0] - START[0]) < 0.012        # back at the start, within the friction band
    assert eng.rep_count == 3 and all(r.completed for r in reps)


def test_strength_eases_off_past_4_5_cm():
    eng, arm, hand, samples, reps = make_strength(PushHand(force_n=36.0, rise_s=1.5, fall_s=0.3))
    log, v = run_tries(eng, arm, READY_S + PUSH_S + REST_S)
    assert len(reps) == 1 and reps[0].duration_s < PUSH_S - 0.5              # the try ended early
    assert EASE_M < reps[0].rom_m < EASE_M + 0.01
    assert reps[0].peak_force_n <= FORCE_CAP_N and reps[0].completed
    rest = [x for x in log if x[1] == "rest"]
    assert rest and all(x[2] == EASED_MSG for x in rest)
    assert log[-1][1] == "ready" and any(x[2] == "Get ready: 3" for x in log[-250:])   # the next try is announced
    assert arm.get_state().mode == "compliant", arm.get_state().fault
    assert max(v) < 0.15, max(v)


def test_strength_untouched_session_records_three_empty_tries():
    hand = PushHand(force_n=0.0)
    hand.present = False
    eng, arm, hand, samples, reps = make_strength(hand, return_home=True)
    n = len(samples)
    eng.run_for(3 * (READY_S + PUSH_S + REST_S) + 0.5)
    assert len(reps) == 3 and all(r.peak_force_n < 3.0 and not r.completed and r.mode == "isometric" for r in reps)
    assert max(np.linalg.norm(np.array(s.pos) - START) for s in samples[n:]) < 0.002
    s = eng.stop()
    assert s.n_reps == 3 and s.exercise == "strength" and eng.snapshot()["message"] == "Back at the start."


def test_strength_has_no_levels_and_never_calls_set_test_limits():
    eng, arm, hand, samples, reps = make_strength(to_band=False, return_home=True)
    calls = []
    arm.set_test_limits = lambda on: calls.append(on)
    with pytest.raises(ValueError, match="no levels"):
        eng.set_level(2)
    run_to_band(eng)
    eng.run_for(READY_S + PUSH_S + REST_S)
    eng.stop()
    assert calls == [] and not arm.test_limits_on


def test_strength_with_the_real_arm_reach_direction():
    eng, arm, hand, samples, reps = make_strength(PushHand(sign=-1.0), sign=-1)
    eng.run_for(READY_S + PUSH_S + 1.0)
    assert len(reps) == 1 and reps[0].peak_force_n == pytest.approx(20.0, abs=2.0)
    snap = eng.snapshot()
    assert np.allclose(snap["path_start"], START) and np.allclose(snap["path_end"], (START[0] - 0.30, 0.0, 0.30))


def test_strength_after_a_trip_it_stops_and_says_so():
    eng, arm, hand, samples, reps = make_strength()
    eng.run_for(READY_S + 1.0)
    arm._trip("force 41.0 N above 40.0 N")
    eng.run_for(1.0)
    snap = eng.snapshot()
    assert snap["message"].startswith("The arm has stopped (force 41.0 N") and snap["phase"] == "idle"
    n = eng.rep_count
    eng.run_for(12.0)
    assert eng.rep_count == n and arm.get_state().mode == "hold"
