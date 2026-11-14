"""Tests for software/assess.py (package S5). Everything here is simulated."""

from __future__ import annotations

import random

import numpy as np
import pytest

import software.assess as assess
from server.contract import RepResult
from software.assess import HEURISTIC_LABEL, assessment, starting_dial
from software.engine import Engine
from software.paths import min_jerk
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
REACH = 0.30


def rep(idx=0, mode="transparent", completed=True, rom=0.27, contribution=0.9) -> RepResult:
    return RepResult(session_id="s", idx=idx, mode=mode, dial=0.0 if mode == "transparent" else 0.5,
                     t_start=float(idx), duration_s=3.0, rom_m=rom, path_err_mean_m=0.01,
                     path_err_max_m=0.02, sparc=-1.6, peak_force_n=10.0, mean_force_n=5.0,
                     contribution=contribution, completed=completed, simulated=True)


def test_label_is_stated():
    assert HEURISTIC_LABEL == "team heuristic, not a clinical assessment"
    assert "NOT A CLINICAL ASSESSMENT" in assess.__doc__
    assert "not a clinical assessment" in starting_dial.__doc__
    assert assessment([rep()])["label"] == HEURISTIC_LABEL


def test_no_completed_rep_starts_at_full_assistance():
    reps = [rep(i, completed=False, rom=0.05, contribution=0.4) for i in range(3)]
    assert starting_dial(reps) == 1.0


def test_able_patient_starts_at_mild_resistance_only():
    reps = [rep(i, completed=True, rom=0.28, contribution=0.98) for i in range(3)]
    assert starting_dial(reps) == assess.START_MIN == -0.3


def test_partial_patient_starts_with_some_assistance():
    reps = [rep(0, completed=True, rom=0.27, contribution=0.6),
            rep(1, completed=False, rom=0.12, contribution=0.5),
            rep(2, completed=False, rom=0.10, contribution=0.5)]
    a = assessment(reps)
    assert a["completed_share"] == pytest.approx(1 / 3)
    assert a["rom_share"] == pytest.approx((0.49 / 3) / 0.27)
    assert a["contribution"] == pytest.approx(1.6 / 3)
    expected = round(round((1 - 1.6 * a["ability"]) / 0.05) * 0.05, 6)
    assert a["dial"] == pytest.approx(expected)
    assert 0.0 < a["dial"] < 1.0


def test_uses_only_the_last_three_transparent_reps():
    good = [rep(i, completed=True, rom=0.28, contribution=0.98) for i in range(3)]
    old_bad = [rep(10 + i, completed=False, rom=0.0, contribution=0.0) for i in range(3)]
    assisted = [rep(20, mode="assist", completed=False, rom=0.0, contribution=0.0)]
    assert starting_dial(old_bad + good + assisted) == -0.3
    assert assessment(old_bad + good)["n_reps"] == 3


def test_needs_a_transparent_rep():
    with pytest.raises(ValueError):
        starting_dial([])
    with pytest.raises(ValueError):
        starting_dial([rep(mode="assist")])
    with pytest.raises(ValueError):
        starting_dial([rep()], reach_m=0.0)


def test_rom_share_is_capped_and_scaled_by_reach():
    assert assessment([rep(rom=0.5)])["rom_share"] == 1.0
    assert assessment([rep(rom=0.18)], reach_m=0.20)["rom_share"] == pytest.approx(1.0)


def test_better_reps_never_raise_the_starting_dial():
    rng = random.Random(0)
    for _ in range(500):
        c = rng.random() < 0.7
        r1 = rep(completed=c, rom=rng.uniform(0, 0.3), contribution=rng.random())
        r2 = rep(completed=True, rom=min(0.3, r1.rom_m + rng.uniform(0, 0.05)),
                 contribution=min(1.0, r1.contribution + rng.uniform(0, 0.2)))
        assert starting_dial([r2]) <= starting_dial([r1])


def test_result_is_in_range_and_on_the_grid():
    rng = random.Random(1)
    for _ in range(500):
        reps = [rep(i, completed=rng.random() < 0.5, rom=rng.uniform(0, 0.4),
                    contribution=rng.random()) for i in range(rng.randint(1, 5))]
        d = starting_dial(reps)
        assert -0.3 <= d <= 1.0
        assert abs(d / 0.05 - round(d / 0.05)) < 1e-9


# --------------------------------------------------------------------------- on the sim engine

class _Cued(SimPatient):
    """Reaches on the engine's cue (same idea as CuedPatient in test_engine.py)."""

    engine = None

    def effort(self, t, pos, vel, goal):
        e = self.engine
        goal = np.array(START, dtype=float)
        if e is not None and e.phase in ("out", "back"):
            tau = float(t) - e.phase_started_at
            s = min_jerk(0.0, 1.3, 3.0, tau) if e.phase == "out" else min_jerk(1.0, 0.0, 3.0, tau)
            goal[0] += s * REACH
        return super().effort(t, pos, vel, goal)


def _transparent_reps(patient) -> list[RepResult]:
    arm = SimArm(patient, start_pos=START, realtime=False)
    arm.connect()
    reps: list[RepResult] = []
    eng = Engine(arm, "assess", "p", True, dial=0.0, auto=False, on_rep=reps.append)
    if isinstance(patient, _Cued):
        patient.engine = eng
    eng.start()
    eng.run_until_reps(3, max_s=120)
    eng.stop()
    return reps


def test_sim_limp_patient_gets_full_assistance():
    reps = _transparent_reps(SimPatient(strength=0.0))
    assert len(reps) == 3 and all(r.mode == "transparent" for r in reps)
    assert starting_dial(reps) == 1.0


def test_sim_strong_patient_starts_low():
    reps = _transparent_reps(_Cued(strength=1.0))
    assert len(reps) == 3 and all(r.completed for r in reps)
    assert starting_dial(reps) <= 0.0
