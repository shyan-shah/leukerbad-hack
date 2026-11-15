"""Every way a rep, try or circle can end emits exactly one RepResult and counts once (15 Nov);
a grab-and-shove in idle does not end the session. SimArm only."""
from __future__ import annotations

import numpy as np
import pytest

from software import engine as engine_mod
from software.engine import DT, Engine
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
REAL = dict(empty_force_pose_n_per_m=(10.0, 0.0, 0.0), empty_force_moving_n=(3.0, 7.0), friction_n=4.5)


def make(exercise="reach", strength=1.0, patient=None, arm_kw=REAL, **kw):
    arm = SimArm(patient or SimPatient(strength=strength), start_pos=START, realtime=False, **arm_kw)
    arm.connect()
    reps, begun = [], []
    kw.setdefault("calibrate", False)
    eng = Engine(arm, "s", "p", True, exercise=exercise, on_rep=reps.append, **kw)
    orig = eng._begin_rep

    def counting(*a, **k):
        begun.append(eng.rep_count)
        return orig(*a, **k)
    eng._begin_rep = counting
    eng.start()
    return eng, arm, reps, begun


def until_phase(eng, phase, max_s=40.0):
    for _ in range(int(max_s / DT)):
        if eng.phase == phase:
            return
        eng.run_for(DT)
    raise AssertionError(f"phase {phase!r} not reached (is {eng.phase!r})")


def check(eng, reps, begun, n=None):
    assert len(begun) == len(reps) == eng.rep_count, (len(begun), len(reps), eng.rep_count)
    assert [r.idx for r in reps] == list(range(len(reps)))
    if n is not None:
        assert len(reps) == n


def recover(eng, arm):
    arm.patient.present = False
    arm.home()
    arm.patient.present = True
    eng.resume()
    assert arm.get_state().mode == "compliant"


ENDINGS = ["completed", "out_timeout", "let_go", "trip", "hold", "stop", "trip_first_tick", "resume_mid_rep"]


@pytest.mark.parametrize("exercise", ["reach", "push", "pull", "armtest"])
@pytest.mark.parametrize("ending", ENDINGS)
def test_each_ending_emits_exactly_one_rep_result(exercise, ending):
    eng, arm, reps, begun = make(exercise)
    until_phase(eng, "out")
    if ending == "trip_first_tick":
        arm._trip("test trip")                       # before the rep has two samples
        eng.run_for(0.5)
        check(eng, reps, begun, 1)
        assert not reps[0].completed
        return
    eng.run_for(0.6)
    if ending == "completed":
        eng.run_until_reps(1, max_s=40.0)
    elif ending == "out_timeout":
        arm.patient.strength = 0.0                   # stops helping: stall rescue or timeout, then the rep ends
        arm.cue("rest")
        eng.run_until_reps(1, max_s=40.0)
    elif ending == "let_go":
        arm.patient.present = False
        eng.run_for(3.0)
    elif ending == "trip":
        arm._trip("test trip")
        eng.run_for(0.5)
    elif ending == "hold":
        arm.hold()
        eng.run_for(0.5)
    elif ending == "stop":
        eng.stop()
    elif ending == "resume_mid_rep":
        eng.resume()
        eng.run_for(0.2)
    check(eng, reps, begun, 1)
    if ending in ("let_go", "trip", "hold", "stop", "resume_mid_rep") and exercise != "armtest":
        assert not reps[0].completed                 # (an armtest try cut short still counts its peak)


def test_many_reps_with_mixed_endings_count_once_each():
    eng, arm, reps, begun = make("reach", strength=1.0)
    for i in range(6):
        until_phase(eng, "out")
        eng.run_for(0.8)
        if i % 3 == 1:
            arm.patient.present = False
            eng.run_for(2.0)
            arm.cue("rest")              # the hand comes back calmly (a sim patient still "reaching" hauls the handle at 0.45 m/s)
            arm.patient.present = True
        elif i % 3 == 2:
            arm._trip("test trip")
            eng.run_for(0.3)
            recover(eng, arm)
        else:
            eng.run_until_reps(len(reps) + 1, max_s=40.0)
        check(eng, reps, begun, i + 1)
    assert [r.completed for r in reps] == [True, False, False, True, False, False]
    assert eng.stop().n_reps == 6


def test_stall_rescue_and_back_timeout_are_one_rep_each(monkeypatch):
    monkeypatch.setattr(engine_mod, "BACK_TIMEOUT_S", 2.0)
    eng, arm, reps, begun = make("reach", strength=0.0, arm_kw={}, dial=0.3, auto=False)
    until_phase(eng, "back", max_s=60.0)
    arm.patient.present = False
    arm._vel[:] = 0.0
    eng.run_for(6.0)
    check(eng, reps, begun, 1)


class Shover(SimPatient):
    """Grabs the idle handle and shoves it: 40 N along the reach for 0.3 s."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.shove_at = None

    def effort(self, t, pos, vel, goal):
        if self.shove_at is not None and 0.0 <= t - self.shove_at < 0.3:
            return np.array([40.0, 0.0, 8.0])
        return super().effort(t, pos, vel, goal)


@pytest.mark.parametrize("exercise", ["reach", "push"])
def test_grab_and_shove_in_idle_does_not_end_the_session(exercise):
    pat = Shover(strength=1.0)
    eng, arm, reps, begun = make(exercise, patient=pat, reps=4)
    eng.run_until_reps(1, max_s=40.0)
    until_phase(eng, "idle")
    pat.shove_at = arm.get_state().t
    peak = 0.0
    for _ in range(100):
        eng.run_for(DT)
        peak = max(peak, float(np.linalg.norm(arm._vel)))
    st = arm.get_state()
    # 40 N is the arm's own force trip and the handle passes 0.4 m/s: the arm goes to hold by itself
    assert eng.error is None and peak >= 0.4
    assert st.mode == "hold" and ("speed" in (st.fault or "") or "force" in (st.fault or ""))
    snap = eng.snapshot()
    assert snap["phase"] == "idle" and snap["rep_count"] == 1          # the engine is alive and has lost nothing
    pat.shove_at = None
    recover(eng, arm)                                    # operator: home, prepare, resume
    eng.run_until_reps(4, max_s=90.0)
    check(eng, reps, begun, 4)
    assert all(r.completed for r in reps) and arm.get_state().fault is None
    assert eng.stop().n_reps == 4
