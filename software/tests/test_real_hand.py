"""A real hand on the bare flange (15 Nov evening, Shyan's reach sets on the arm). SimArm only.

What the arm showed: a rep armed and ended within 0.5 to 1 s at 1 to 2 cm ("phantom" rep, counted),
the real reach then happened in idle with the target trailing the hand, and nothing stopped the
handle short of the workspace box (35 cm), which tripped.

The hands here differ from SimPatient in what made that visible: they carry their own weight (no
8 N limb load across the motion for the engine to see) and they do not wait for the engine.
"""
from __future__ import annotations

import numpy as np
import pytest

from software import engine as engine_mod
from software.engine import DT, Engine
from software.paths import min_jerk
from software.sim_arm import PASSIVE_LOAD_N, SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
REAL = dict(empty_force_pose_n_per_m=(10.0, 0.0, 0.0), empty_force_moving_n=(3.0, 7.0), friction_n=4.5)
REAL_WITH = dict(REAL, empty_force_moving_dir="with")
BOX_M = 0.35


class BareHand(SimPatient):
    """Grips with ``grip_n`` along the reach while resting at the start, then reaches like
    SimPatient. Carries its own weight at all times."""

    def __init__(self, grip_n=8.0, **kw):
        super().__init__(**kw)
        self.grip_n = float(grip_n)
        self._g0 = None

    def effort(self, t, pos, vel, goal):
        d = float(np.linalg.norm(np.subtract(pos, START)))
        if np.linalg.norm(np.subtract(goal, START)) < 1e-9 and d < 0.10:
            back = 4.5 * float(np.clip((goal[0] - pos[0]) / 0.005, -1.0, 1.0)) * min(1.0, self.strength / 0.3)
            if self._g0 is None:
                self._g0 = t
            g = self.grip_n * min(1.0, (t - self._g0) / 0.3) * float(np.clip((0.10 - d) / 0.04, 0.0, 1.0))
            return np.array([g - back, 0.0, PASSIVE_LOAD_N])
        self._g0 = None
        f = np.array(super().effort(t, pos, vel, goal), dtype=float)
        f[2] += PASSIVE_LOAD_N
        return f


class Script(SimPatient):
    """A hand that follows its own plan whatever the engine cues: ``plan(t_rel, x)`` returns the
    force along x (N) it applies, t_rel in s since its first call, x in m from the start. It
    carries its own weight and holds the handle on the line."""

    def __init__(self, plan, **kw):
        super().__init__(**kw)
        self.plan = plan
        self._t0 = None

    def effort(self, t, pos, vel, goal):
        if self._t0 is None:
            self._t0 = t
        fx = float(self.plan(t - self._t0, float(pos[0]) - START[0], float(vel[0])))
        # (SimArm adds up to 4.5 N towards its own goal, "pushing through friction": cancel it)
        fx -= 4.5 * float(np.clip((goal[0] - pos[0]) / 0.005, -1.0, 1.0)) * min(1.0, self.strength / 0.3)
        return np.array([fx, -150.0 * (pos[1] - START[1]) - 5.0 * vel[1], PASSIVE_LOAD_N])


def creep_then_reach(creep_s, creep_v=0.015, press_n=8.0, press_s=1.0):
    """Presses ``press_n`` at the start for ``press_s`` (the rep arms at about 1.0 s), then, whatever
    the engine does, creeps outward at ``creep_v`` for ``creep_s`` from where the handle is and
    goes on into a 3 s reach to 29 cm, dwells 0.5 s and comes back in 3 s."""
    st = {}

    def plan(t, x, v):
        if t < press_s:
            return press_n * min(1.0, t / 0.3)
        t -= press_s
        x0 = st.setdefault("x0", x)
        x1 = x0 + creep_v * creep_s
        if t < creep_s:
            goal, gv = x0 + creep_v * t, creep_v
        elif t < creep_s + 3.0:
            goal, gv = min_jerk(x1, 0.29, 3.0, t - creep_s), 0.0
        elif t < creep_s + 3.5:
            goal, gv = 0.29, 0.0
        else:
            goal, gv = min_jerk(0.29, 0.0, 3.0, t - creep_s - 3.5), 0.0
        return float(np.clip(600.0 * (goal - x) + 30.0 * (gv - v), -25.0, 25.0))
    return plan


def make(patient, exercise="reach", arm_kw=REAL, **kw):
    arm = SimArm(patient, start_pos=START, realtime=False, **arm_kw)
    arm.connect()
    reps, smp = [], []
    if exercise != "reach":
        kw.setdefault("calibrate", False)
    eng = Engine(arm, "s", "p", True, on_rep=reps.append, on_sample=smp.append, exercise=exercise, **kw)
    eng.start()
    return eng, arm, reps, smp


def run(eng, arm, seconds):
    """Run and return the furthest the handle got from the arm's start pose along x (m)."""
    far = 0.0
    for _ in range(int(round(seconds / DT))):
        eng.run_for(DT)
        st = arm.get_state()
        far = max(far, abs(st.pos[0] - START[0]))
        assert st.mode == "compliant", st.fault
    return far


# ------------------------------------------------------------------ 1. no phantom rep

@pytest.mark.parametrize("arm_kw", [REAL, REAL_WITH], ids=["reading_against", "reading_with"])
@pytest.mark.parametrize("creep_s", [0.6, 1.0, 2.0])
def test_a_hand_that_creeps_out_of_the_start_gets_one_rep_for_its_reach(creep_s, arm_kw):
    """The logged trace: armed, then 0.5 to 1 s of creeping at 1 to 2 cm with a few N, then the
    reach. One rep, completed, with the whole reach in it; nothing counted for the creep."""
    eng, arm, reps, smp = make(Script(creep_then_reach(creep_s)), arm_kw=arm_kw)
    run(eng, arm, 1.0 + creep_s + 6.5 + 2.5)
    assert eng.cancelled_reps == 0
    assert len(reps) == 1 and reps[0].completed, reps
    assert reps[0].rom_m > 0.22
    assert eng.rep_count == 1


def test_before_the_fix_the_creeping_hand_gave_a_phantom_rep(monkeypatch):
    """The reproduction: with the wait and the pause switched off (the engine as it was) the same
    hand's rep ends 0.5 s after arming, about 1 cm out, and is counted."""
    monkeypatch.setattr(engine_mod, "MIN_REP_M", 0.0)
    monkeypatch.setattr(engine_mod, "PAUSE_S", 0.0)
    eng, arm, reps, smp = make(Script(creep_then_reach(1.0)), arm_kw=REAL_WITH)
    eng.run_until_reps(1, max_s=6.0)
    assert len(reps) == 1 and not reps[0].completed
    assert reps[0].duration_s < 0.7 and reps[0].rom_m < 0.02


@pytest.mark.parametrize("strength", [1.0, 0.5, 0.3])
def test_bare_hand_reaches_are_counted_and_completed(strength):
    """A hand with no weight on the handle, moving it freely (reading near 0 N): every reach is a
    completed rep, none is cut short, no trip."""
    eng, arm, reps, smp = make(BareHand(8.0, strength=strength))
    run(eng, arm, 40.0)
    assert len(reps) >= 4 and eng.cancelled_reps == 0
    assert all(r.completed and r.rom_m > 0.24 for r in reps), reps


def test_armed_and_then_nothing_is_cancelled_not_counted():
    """Press, the rep arms, the hand goes: the handle is not driven, and after START_WAIT_S the
    rep is dropped without a RepResult."""
    def plan(t, x, v):
        return 8.0 * min(1.0, t / 0.3)
    p = Script(plan)
    eng, arm, reps, smp = make(p)
    for _ in range(300):
        eng.run_for(DT)
        if eng.phase == "out":
            break
    assert eng.phase == "out"
    p.present = False
    x0 = arm.get_state().pos[0]
    far = 0.0
    for _ in range(int(5.0 / DT)):
        eng.run_for(DT)
        far = max(far, abs(arm.get_state().pos[0] - x0))
    assert far < 0.01                       # never driven
    assert eng.phase == "idle" and reps == [] and eng.rep_count == 0 and eng.cancelled_reps == 1


@pytest.mark.parametrize("arm_kw", [{}, REAL], ids=["ideal", "real"])
def test_go_on_an_empty_handle_is_still_not_driven_and_not_counted(arm_kw):
    """go() can arm an empty handle (its pose reading passes GO_MIN_N). It must not travel and it
    must not become a rep through the wait or the travel rule."""
    eng, arm, reps, smp = make(SimPatient(present=False), arm_kw=dict(arm_kw, empty_force_pose_n_per_m=(10.0, 0.0, 0.0)))
    arm.force_offset = np.array([3.0, 0.0, 0.0])     # an un-zeroed reading above GO_MIN_N
    eng.run_for(3.0)
    eng.go()
    x0 = arm.get_state().pos[0]
    far = 0.0
    for _ in range(int(12.0 / DT)):
        eng.run_for(DT)
        far = max(far, abs(arm.get_state().pos[0] - x0))
    assert far < 0.08
    assert reps == [] and eng.rep_count == 0


# ------------------------------------------------------------------ 3. a reach already under way in idle

def push_out(force_n, from_s=1.0, v_max=0.20):
    """Rests, then pushes outward for good (no pressing at the start first). The push is
    ``force_n`` against a handle that is held and fades to nothing at ``v_max`` (a person does
    not keep accelerating a handle that gives way)."""
    def plan(t, x, v):
        if t < from_s:
            return 0.0
        return force_n * min(1.0, (t - from_s) / 0.3) * float(np.clip(1.0 - v / v_max, 0.0, 1.0))
    return plan


@pytest.mark.parametrize("force_n", [22.0, 25.0])
def test_a_reach_under_way_in_idle_becomes_a_rep_from_there(force_n):
    """The handle is 10 cm out in idle (nothing armed) and a hand pushes on outward: "return to
    start" at first, then, moving outward past 5 cm with force on it, the rep starts where the
    hand is, and it completes. No trip, and the handle stays in the box."""
    eng, arm, reps, smp = make(Script(push_out(force_n, from_s=1.0)))
    arm.patient.present = False
    eng.run_for(0.2)
    arm._pos = np.array([START[0] + 0.10, START[1], START[2]])      # (sim only) the handle was left out
    eng.run_for(0.3)
    assert eng.phase == "idle"
    arm.patient.present = True
    far, begun_at, reasons = 0.0, None, set()
    for _ in range(int(14.0 / DT)):
        eng.run_for(DT)
        st = arm.get_state()
        assert st.mode == "compliant", st.fault
        far = max(far, st.pos[0] - START[0])
        if begun_at is None:
            reasons.add(eng.snapshot()["arming"]["reason"])
            if eng.phase == "out":
                begun_at = st.pos[0] - START[0]
        if reps:
            break
    assert begun_at is not None and 0.09 <= begun_at < 0.16, begun_at
    assert "return to start" in reasons
    assert len(reps) == 1 and reps[0].completed, reps
    assert far < BOX_M


def test_no_take_over_once_the_set_is_done_or_in_the_strength_test():
    eng, arm, reps, smp = make(BareHand(8.0, strength=1.0), reps=1)
    eng.run_until_reps(1, max_s=20.0)
    arm.patient = Script(push_out(20.0, from_s=0.0))
    run(eng, arm, 6.0)
    assert eng.rep_count == 1 and eng.phase == "idle"
    # the strength test: a handle left 10 cm out and pushed on outward never becomes a try
    eng2, arm2, reps2, _ = make(Script(push_out(22.0, from_s=1.0)), exercise="armtest")
    arm2.patient.present = False
    eng2.run_for(0.2)
    arm2._pos = np.array([START[0] + 0.10, START[1], START[2]])
    eng2.run_for(0.3)
    arm2.patient.present = True
    for _ in range(int(5.0 / DT)):
        eng2.run_for(DT)
        assert eng2.phase == "idle"
    assert reps2 == [] and eng2.rep_count == 0


# ------------------------------------------------------------------ 2. idle never follows the hand out of the path

@pytest.mark.parametrize("force_n", [10.0, 18.0, 25.0])
def test_idle_hold_keeps_a_pushing_hand_inside_the_box(force_n):
    """Set finished (no rep can start), the hand pushes outward for 15 s: the idle target stays on
    the path, the end is held at k_max, and the handle stays inside the 35 cm box. No trip.
    (The arm can hold 30 N at most: k_max 600 N/m at the 5 cm lead limit.)"""
    eng, arm, reps, smp = make(BareHand(8.0, strength=1.0), reps=1)
    eng.run_until_reps(1, max_s=20.0)
    assert eng.rep_count == 1
    arm.patient = Script(push_out(force_n, from_s=0.0))
    n0 = len(smp)
    far = run(eng, arm, 15.0)
    assert far < BOX_M, far
    tgt = np.array([s.target[0] for s in smp[n0:]]) - START[0]
    assert tgt.max() <= 0.30 + 1e-9             # never beyond the path end
    assert eng.rep_count == 1


def test_idle_hold_at_the_end_lets_go_gently():
    """The hand leans 25 N on the end hold and then vanishes: the handle is not thrown back."""
    eng, arm, reps, smp = make(BareHand(8.0, strength=1.0), reps=1)
    eng.run_until_reps(1, max_s=20.0)
    arm.patient = Script(push_out(25.0, from_s=0.0))
    run(eng, arm, 10.0)
    arm.patient.present = False
    vmax = 0.0
    for _ in range(int(3.0 / DT)):
        eng.run_for(DT)
        st = arm.get_state()
        assert st.mode == "compliant", st.fault
        vmax = max(vmax, float(np.linalg.norm(st.vel)))
    assert vmax < 0.15, vmax


def test_row_idle_target_stays_on_the_path_at_the_far_end():
    """Row starts at the far end, 5 cm from the box edge. A hand pushing further out there (the
    wrong way) is held, and the idle target never leaves the path."""
    arm = SimArm(SimPatient(present=False), start_pos=START, realtime=False, **REAL)
    arm.connect()
    arm._pos = np.array([START[0] + 0.28, START[1], START[2]])      # handle left at the far end
    smp = []
    eng = Engine(arm, "s", "p", True, on_sample=smp.append, exercise="pull", calibrate=False)
    eng.start()
    eng.run_for(2.0)
    arm.patient = Script(push_out(20.0, from_s=0.0))     # +x: away from the body, towards the box edge
    far = run(eng, arm, 12.0)
    assert far < BOX_M, far
    idle = [s for s in smp if s.phase == "idle"]
    assert idle and max(s.target[0] for s in idle) - START[0] <= 0.28 + 1e-9


# ------------------------------------------------------------------ found while fixing (all sim)

class Weighted(Script):
    """A Script hand that rests its limb's weight (8 N) on the handle."""

    def effort(self, t, pos, vel, goal):
        e = super().effort(t, pos, vel, goal)
        e[2] -= PASSIVE_LOAD_N
        return e


@pytest.mark.parametrize("hand", [Script, Weighted], ids=["bare", "weight_on_handle"])
@pytest.mark.parametrize("force_n", [20.0, 25.0])
def test_idle_target_does_not_trail_a_hand_pushing_from_10cm_to_the_end(force_n, hand):
    """The case on the arm: set done, handle 10 cm out, a steady push outward. Before: the let-go
    rule read the commanded (unclamped) spring, fired once the target was far behind, and the
    target hopped after the hand; with the target far behind nothing held the handle across the
    path either (a limb's weight sank it 8 cm). Now the target does not move outward at all, the
    handle settles before the path end and stays on the line."""
    eng, arm, reps, smp = make(BareHand(8.0, strength=1.0), reps=1)
    eng.run_until_reps(1, max_s=20.0)
    arm.patient.present = False
    eng.run_for(0.3)
    arm._pos = np.array([START[0] + 0.10, START[1], START[2]])
    eng.run_for(0.3)
    arm.patient = hand(push_out(force_n, from_s=0.0))
    n0 = len(smp)
    far = run(eng, arm, 20.0)
    after = smp[n0:]
    tgt = np.array([s.target[0] for s in after])
    assert np.all(np.diff(tgt) <= 0.045 * 1.01 + 1e-9)             # no hop after the hand
    assert max(s.pos[0] - s.target[0] for s in after[50:]) <= 0.05 + 1e-6
    assert far < 0.30, far                                         # settles before the path end
    assert max(abs(s.pos[2] - START[2]) for s in after) < 0.04     # held on the line, limb weight and all
    assert np.linalg.norm(after[-1].vel) < 0.01 and eng.rep_count == 1


@pytest.mark.parametrize("grip_n", [-10.0, -18.0])
def test_a_hand_pressing_backwards_at_the_start_still_arms_without_a_trip(grip_n):
    """The hand-over at arming keeps the target on the hand behind the start too (only the
    box-side path end is clamped)."""
    from test_arming import Gripper
    eng, arm, reps, smp = make(Gripper(grip_n, strength=1.0), reps=3)
    for _ in range(int(40.0 / DT)):
        eng.run_for(DT)
        assert arm.get_state().mode == "compliant", arm.get_state().fault
        if eng.rep_count >= 3:
            break
    assert len(reps) == 3 and all(r.completed for r in reps)


def test_no_take_over_on_the_resist_side():
    """There the one-tick let-go test would cut such a rep short (a counted 3 cm rep)."""
    eng, arm, reps, smp = make(Script(push_out(22.0, from_s=1.0)), exercise="push")
    arm.patient.present = False
    eng.run_for(0.2)
    arm._pos = np.array([START[0] + 0.10, START[1], START[2]])
    eng.run_for(0.3)
    arm.patient.present = True
    run(eng, arm, 10.0)
    assert reps == [] and eng.rep_count == 0 and eng.cancelled_reps == 0
