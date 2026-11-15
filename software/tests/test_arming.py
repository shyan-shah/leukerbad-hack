"""Arming for a real hand (15 Nov): firm hold at the start, hand force for 0.6 s, go(), resume(), stop()."""
from __future__ import annotations

import numpy as np
import pytest

from software.engine import DT, Engine
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
REAL = dict(empty_force_pose_n_per_m=(10.0, 0.0, 0.0), empty_force_moving_n=(3.0, 7.0), friction_n=4.5)


class Gripper(SimPatient):
    """While resting at the start: a steady grip force along the reach plus a 1 Hz sideways
    wobble (the force that moves a 600 N/m hold 1 cm peak to peak); the limb's weight is carried."""

    def __init__(self, grip_n, wobble_phase=0.0, **kw):
        super().__init__(**kw)
        self.wobble_phase = float(wobble_phase)      # turns; the arm clock starts at an arbitrary time
        self._t_first = None
        self.grip_n = float(grip_n)
        self._grip_t0 = None

    def effort(self, t, pos, vel, goal):
        if self._t_first is None:
            self._t_first = t
        tw = t - self._t_first + self.wobble_phase
        d = float(np.linalg.norm(np.subtract(pos, START)))
        if np.linalg.norm(np.subtract(goal, START)) < 1e-9 and d < 0.10:
            # (SimArm adds up to 4.5 N towards the goal for strong patients, "pushing through friction": cancel it)
            back = 4.5 * float(np.clip((goal[0] - pos[0]) / 0.005, -1.0, 1.0)) * min(1.0, self.strength / 0.3)
            if self._grip_t0 is None:
                self._grip_t0 = t
            g = self.grip_n * min(1.0, (t - self._grip_t0) / 0.3)      # a hand takes 0.3 s to build its grip
            g *= float(np.clip((0.10 - d) / 0.04, 0.0, 1.0))           # and eases off between 6 and 10 cm out (no force cliff)
            return np.array([g - back, 3.0 * np.sin(2 * np.pi * tw), 8.0])
        self._grip_t0 = None
        return super().effort(t, pos, vel, goal)


def make(patient, exercise="reach", **kw):
    arm = SimArm(patient, start_pos=START, realtime=False, **REAL)
    arm.connect()
    reps = []
    eng = Engine(arm, "s", "p", True, on_rep=reps.append, exercise=exercise, **kw)
    eng.start()
    return eng, arm, reps


@pytest.mark.parametrize("exercise", ["reach", "push"])
@pytest.mark.parametrize("phase", [0.0, 0.25, 0.5, 0.75])
@pytest.mark.parametrize("grip", [6.0, 10.0, 18.0])
def test_grip_arms_and_ten_reps_in_a_row_reach_the_target(grip, phase, exercise):
    """A hand that grips at 6, 10 or 18 N with a 1 cm wobble: every rep arms, the counter reaches
    the target, no trip. (Before 15 Nov evening: parked at 3.4 or 5.7 cm in the 300 N/m hold,
    reps cut 30 ms after arming on the resist side, speed trips at arming and on a let-go.)"""
    kw = {} if exercise == "reach" else {"calibrate": False}
    eng, arm, reps = make(Gripper(grip, wobble_phase=phase, strength=1.0), exercise=exercise, reps=10, **kw)
    t = 0.0
    while eng.phase != "out" and t < 3.0:
        eng.run_for(DT)
        t += DT
    assert eng.phase == "out" and t <= 0.3 + 1.0 + 2 * DT    # grip built over 0.3 s; measured 0.95 s (10, 18 N), 1.28 to 1.31 s (6 N) from first touch
    eng.run_until_reps(10, max_s=150.0)
    assert eng.rep_count == 10 and len(reps) == 10 and all(r.completed for r in reps)
    st = arm.get_state()
    assert st.mode == "compliant" and st.fault is None


def test_empty_handle_never_arms_and_snapshot_has_the_contract_fields():
    eng, arm, reps = make(SimPatient(strength=0.0, present=False))
    eng.run_for(20.0)
    snap = eng.snapshot()
    assert eng.rep_count == 0 and eng.phase == "idle"
    assert snap["arming"] == {"progress": 0.0, "reason": "press gently"}
    assert snap["calibration"] is None            # reach has no calibration (server/API.md section 7)
    assert np.linalg.norm(np.subtract(arm.get_state().pos, START)) < 0.002


def test_a_push_above_25n_does_not_arm():
    eng, arm, reps = make(Gripper(26.0, strength=1.0))
    eng.run_for(3.0)
    # (a 26 N step on the sim's 1.5 kg handle also trips the arm's own speed limit)
    assert eng.rep_count == 0 and eng.phase == "idle"


def test_go_never_drives_an_empty_handle_more_than_8cm():
    eng, arm, reps = make(SimPatient(strength=0.0, present=False))
    eng.run_for(1.0)
    eng.go()
    far = 0.0
    for _ in range(1500):
        eng.run_for(DT)
        far = max(far, abs(arm.get_state().pos[0] - START[0]))
    assert far < 0.08 and arm.get_state().fault is None


def test_go_arms_a_light_hand_after_the_countdown():
    eng, arm, reps = make(Gripper(3.0, strength=1.0))        # 3 N: under the 4.5 N arming force
    eng.run_for(2.0)
    assert eng.phase == "idle"
    eng.go()
    eng.run_for(2.5)
    assert eng.phase == "idle" and 0.5 < eng.snapshot()["arming"]["progress"] < 1.0
    eng.run_for(1.0)
    assert eng.phase == "out"


def test_stop_mid_rep_records_the_rep_as_not_completed():
    eng, arm, reps = make(SimPatient(strength=1.0))
    while eng.phase != "out":
        eng.run_for(DT)
    eng.run_for(1.0)
    summary = eng.stop()
    assert len(reps) == 1 and not reps[0].completed and summary.n_reps == 1 and eng.rep_count == 1


def test_resume_after_a_trip_continues_the_same_session():
    eng, arm, reps = make(SimPatient(strength=1.0))
    eng.run_until_reps(1, max_s=30.0)
    arm._trip("test trip")
    eng.run_for(0.5)
    assert arm.get_state().mode == "hold"
    arm.patient.present = False
    arm.home()
    arm.patient.present = True
    eng.resume()
    assert arm.get_state().mode == "compliant"
    n = eng.rep_count
    eng.run_until_reps(n + 1, max_s=30.0)
    assert eng.rep_count == n + 1 and reps[-1].completed and arm.get_state().fault is None
