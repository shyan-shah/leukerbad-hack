"""Tests for software/engine.py (package S4), run on SimArm(realtime=False).

Two simulated patients are used:
- the stock ``SimPatient`` inside ``SimArm``, whose routine starts a reach when the engine's
  stiffness leaves the soft hold (see software/sim_arm.py);
- ``CuedPatient`` (defined here, test only): a SimPatient whose goal follows the engine's phase
  directly, with an adjustable overshoot, for cases that need a specific behaviour (a patient
  who refuses to reach, or one who stalls against resistance).
Everything here is simulated.
"""

from __future__ import annotations

import numpy as np
import pytest

from server.contract import RepResult, Sample, SessionSummary
from software import engine as engine_mod
from software.engine import DT, Engine
from software.metrics import contribution, rep_metrics
from software.paths import min_jerk
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
REACH = 0.30


class CuedPatient(SimPatient):
    """Test patient whose goal follows the engine's phase (see module docstring)."""

    engine: Engine | None = None
    reach_s: float = 3.0
    overshoot: float = 0.3      # aims at progress 1.3 on the way out

    def effort(self, t, pos, vel, goal):
        e = self.engine
        if e is not None and e.phase in ("out", "back"):
            tau = float(t) - e.phase_started_at
            if e.phase == "out":
                s_goal = min_jerk(0.0, 1.0 + self.overshoot, self.reach_s, tau)
            else:
                s_goal = min_jerk(1.0, 0.0, self.reach_s, tau)
            goal = np.array(START, dtype=float)
            goal[0] += s_goal * REACH
        else:
            goal = np.array(START, dtype=float)
        return super().effort(t, pos, vel, goal)


class Spy:
    """Wraps an arm and counts commands."""

    def __init__(self, arm):
        self._arm = arm
        self.targets: list[tuple] = []
        self.stiffness: list[tuple] = []
        self.holds = 0

    def __getattr__(self, name):
        return getattr(self._arm, name)

    def set_target(self, pos):
        self.targets.append(tuple(pos))
        self._arm.set_target(pos)

    def set_stiffness(self, kx, ky, kz):
        self.stiffness.append((kx, ky, kz))
        self._arm.set_stiffness(kx, ky, kz)

    def hold(self):
        self.holds += 1
        self._arm.hold()


def make(patient=None, dial=1.0, auto=False, spy=False, simulated=True):
    patient = patient if patient is not None else SimPatient(strength=0.0)
    arm = SimArm(patient, start_pos=START, realtime=False)
    arm.connect()
    if spy:
        arm = Spy(arm)
    samples: list[Sample] = []
    reps: list[RepResult] = []
    eng = Engine(arm, "sess-1", "pat-1", simulated, dial=dial, auto=auto,
                 on_sample=samples.append, on_rep=reps.append)
    if isinstance(patient, CuedPatient):
        patient.engine = eng
    eng.start()
    return eng, arm, samples, reps


def cued(strength=1.0, **kw) -> CuedPatient:
    p = CuedPatient(strength=strength)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def progress_x(p) -> float:
    return (p[0] - START[0]) / REACH


# --------------------------------------------------------------------------- acceptance tests

def test_limp_patient_full_assist_completes_with_low_contribution():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), dial=1.0, auto=False)
    eng.run_until_reps(5, max_s=120)
    assert len(reps) == 5
    assert all(r.completed for r in reps)
    assert all(r.contribution < 0.3 for r in reps)
    assert all(r.mode == "assist" and r.dial == 1.0 for r in reps)
    assert eng.dial == 1.0                       # manual: dial unchanged
    assert arm.get_state().mode == "compliant"   # never tripped


def test_strong_patient_auto_dial_falls_below_0_3_within_8_reps():
    eng, arm, samples, reps = make(cued(1.0), dial=1.0, auto=True)
    eng.run_until_reps(8, max_s=200)
    assert len(reps) == 8
    dials_after = [r.dial for r in reps[1:]] + [eng.dial]
    assert min(dials_after) < 0.3
    assert reps[0].contribution > 0.6
    assert arm.get_state().fault is None


def test_strong_patient_full_resistance_completes_with_peak_force_near_15n():
    eng, arm, samples, reps = make(cued(1.0), dial=-1.0, auto=False)
    eng.run_until_reps(3, max_s=120)
    assert len(reps) == 3
    for r in reps:
        assert r.mode == "resist"
        assert r.completed
        # K_RESIST * MAX_LEAD = 15 N along the reach; the magnitude also includes the
        # simulated 8 N limb load, so the band is wide on the upper side.
        assert 12.0 <= r.peak_force_n <= 22.0
    assert arm.get_state().fault is None


def test_tripped_arm_gets_no_commands_and_emits_idle_samples():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), dial=1.0, spy=True)
    eng.run_for(2.0)                               # into the out phase
    assert eng.phase == "out"
    arm._arm._trip("test trip")
    n_t, n_k = len(arm.targets), len(arm.stiffness)
    n_s = len(samples)
    eng.run_for(3.0)
    assert len(arm.targets) == n_t and len(arm.stiffness) == n_k
    new = samples[n_s:]
    assert len(new) == 300
    assert all(s.phase == "idle" and s.rep_idx == -1 for s in new)
    assert eng.snapshot()["arm_mode"] == "hold"


def test_empty_handle_never_starts_a_rep():
    p = SimPatient(strength=0.0, present=False)
    eng, arm, samples, reps = make(p, dial=1.0)
    eng.run_for(20.0)
    assert eng.rep_count == 0 and reps == []
    assert all(s.phase == "idle" for s in samples)
    xs = [s.target[0] for s in samples]
    assert max(xs) - min(xs) < 1e-9                # the target never moves


def test_letting_go_mid_reach_stops_target_advance_within_0_5s():
    p = SimPatient(strength=0.0)
    eng, arm, samples, reps = make(p, dial=1.0)
    while not (eng.phase == "out" and progress_x(arm.get_state().pos) > 0.3):
        eng.run_for(DT)
    t_release = samples[-1].t
    p.present = False
    eng.run_for(3.0)
    after = [s for s in samples if s.t > t_release]
    settle = [s for s in after if s.t >= t_release + 0.5 + 2 * DT]
    s_at = progress_x(settle[0].target)
    assert max(progress_x(s.target) for s in settle) <= s_at + 1e-9
    assert all(s.phase == "idle" for s in settle)
    assert eng.phase == "idle"
    assert len(reps) == 1 and reps[0].completed is False
    # the empty handle stops within about 8 cm of where it was let go
    hand_at_release = progress_x(after[0].pos)
    assert (progress_x(samples[-1].pos) - hand_at_release) * REACH < 0.08


def test_contribution_uses_out_phase_only():
    eng, arm, samples, reps = make(cued(1.0), dial=-1.0, auto=False)
    eng.run_until_reps(1, max_s=60)
    rep = reps[0]
    out = [s for s in samples if s.rep_idx == 0 and s.phase == "out"]
    both = [s for s in samples if s.rep_idx == 0]
    assert any(s.phase == "back" for s in both)

    def arrays(ss):
        return (np.array([s.t for s in ss]), np.array([s.pos for s in ss]),
                np.array([s.force for s in ss]))

    t, pos, f = arrays(out)
    m = rep_metrics(t, pos, f, START, (START[0] + REACH, START[1], START[2]))
    assert rep.contribution == pytest.approx(m["contribution"], abs=1e-12)
    assert rep.duration_s == pytest.approx(t[-1] - t[0])

    t2, pos2, f2 = arrays(both)
    vel2 = np.gradient(pos2, t2, axis=0)
    c_both = contribution(f2, vel2, START, (START[0] + REACH, START[1], START[2]))
    assert abs(c_both - rep.contribution) > 0.1   # the return phase would distort it


def test_stop_returns_summary_and_holds():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), dial=1.0)
    eng.run_until_reps(2, max_s=60)
    summary = eng.stop()
    assert isinstance(summary, SessionSummary)
    assert summary.n_reps == 2 == len(reps)
    assert summary.session_id == "sess-1" and summary.patient_id == "pat-1"
    assert summary.exercise == "reach_line" and summary.simulated is True
    assert summary.ended_at is not None
    assert arm.get_state().mode == "hold"


def test_every_record_is_simulated():
    eng, arm, samples, reps = make(cued(1.0), dial=1.0, auto=True)
    eng.run_until_reps(3, max_s=60)
    assert samples and reps
    assert all(s.simulated is True for s in samples)
    assert all(r.simulated is True for r in reps)
    assert eng.stop().simulated is True


def test_simulated_flag_is_passed_through_not_invented():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), simulated=False)
    eng.run_for(0.5)
    assert all(s.simulated is False for s in samples)


# --------------------------------------------------------------------------- behaviour details

def test_exception_in_callback_holds_arm_then_reraises():
    arm = SimArm(SimPatient(strength=0.0), start_pos=START, realtime=False)
    arm.connect()
    calls = []

    def boom(sample):
        calls.append(sample)
        if len(calls) == 50:
            raise RuntimeError("callback failed")

    eng = Engine(arm, "s", "p", True, on_sample=boom)
    eng.start()
    with pytest.raises(RuntimeError, match="callback failed"):
        eng.run_for(2.0)
    assert arm.get_state().mode == "hold"


def test_exception_in_arm_holds_arm_then_reraises():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), spy=True)
    eng.run_for(0.2)

    def bad_get_state():
        raise ValueError("sensor glitch")

    arm.get_state = bad_get_state
    holds = arm.holds
    with pytest.raises(ValueError, match="sensor glitch"):
        eng.tick()
    assert arm.holds == holds + 1
    assert arm._arm.get_state().mode == "hold"


def test_target_every_tick_stiffness_only_on_change():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), dial=1.0, spy=True)
    eng.run_until_reps(2, max_s=60)
    assert len(arm.targets) == len(samples)        # every compliant tick feeds the watchdog
    assert len(arm.stiffness) < 40                 # hold -> firm ramp (6 steps) -> assist -> hold ...
    assert all(a != b for a, b in zip(arm.stiffness, arm.stiffness[1:]))
    assert arm.get_state().fault is None


def test_rep_record_fields():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), dial=1.0)
    eng.run_until_reps(2, max_s=60)
    assert [r.idx for r in reps] == [0, 1]
    assert all(r.session_id == "sess-1" for r in reps)
    assert reps[0].t_start < reps[1].t_start
    assert all(0.0 <= r.contribution <= 1.0 for r in reps)
    assert all(r.rom_m > 0.25 for r in reps)
    in_rep = [s for s in samples if s.rep_idx == 0]
    assert {s.phase for s in in_rep} == {"out", "back"}
    assert [s.phase for s in samples[:50]] == ["idle"] * 50


def test_samples_carry_engine_time_and_arm_state():
    eng, arm, samples, reps = make(SimPatient(strength=0.0))
    eng.run_for(1.0)
    assert samples[0].t == pytest.approx(0.0)
    assert samples[-1].t == pytest.approx(0.99, abs=1e-6)
    assert len(samples[0].q) == 7
    assert all(s.dial == 1.0 for s in samples)


def test_arms_only_after_one_second_at_start():
    eng, arm, samples, reps = make(SimPatient(strength=0.0))
    eng.run_for(0.95)
    assert eng.phase == "idle"
    eng.run_for(0.2)
    assert eng.phase == "out"


def test_stall_rescue_on_assist_side_marks_rep():
    # a strong patient who holds back toward the start against weak assistance
    p = cued(1.0, overshoot=-1.0)              # aims at progress 0: refuses to reach
    eng, arm, samples, reps = make(p, dial=0.2, auto=False)
    eng.run_until_reps(1, max_s=40)
    assert reps[0].rescued is True
    assert reps[0].completed is False


def test_auto_failure_raises_dial_and_manual_holds_it():
    p = cued(1.0, overshoot=-1.0)
    eng, arm, samples, reps = make(p, dial=0.5, auto=True)
    eng.run_until_reps(1, max_s=40)
    assert eng.dial == pytest.approx(0.6)      # failure: +0.10
    eng.set_dial(0.4, auto=False)
    eng.run_until_reps(2, max_s=40)
    assert eng.dial == 0.4 and eng.auto is False


def test_set_dial_clamps_and_rejects_nan():
    eng, arm, samples, reps = make()
    eng.set_dial(5.0)
    assert eng.dial == 1.0
    eng.set_dial(-3.0, auto=True)
    assert eng.dial == -1.0 and eng.auto is True
    with pytest.raises(ValueError):
        eng.set_dial(float("nan"))


def test_snapshot_before_and_after_first_tick():
    arm = SimArm(SimPatient(strength=0.0), start_pos=START, realtime=False)
    arm.connect()
    eng = Engine(arm, "s", "p", True, dial=0.5, auto=False)
    snap = eng.snapshot()
    assert snap["rep_count"] == 0 and snap["auto"] is False
    eng.start()
    eng.run_for(0.1)
    snap = eng.snapshot()
    for key in ("t", "pos", "force", "target", "dial", "phase", "simulated", "q",
                "rep_count", "auto", "arm_mode"):
        assert key in snap
    assert snap["arm_mode"] == "compliant" and snap["phase"] == "idle" and snap["dial"] == 0.5


def test_run_for_rejects_realtime_arm_and_unstarted_engine():
    arm = SimArm(SimPatient(strength=0.0), start_pos=START, realtime=False)
    arm.connect()
    eng = Engine(arm, "s", "p", True)
    with pytest.raises(RuntimeError):
        eng.run_for(0.1)


def test_realtime_thread_runs_and_stop_joins():
    arm = SimArm(SimPatient(strength=0.0), start_pos=START, realtime=True)
    arm.connect()
    samples = []
    eng = Engine(arm, "s", "p", True, on_sample=samples.append)
    try:
        eng.start()
        import time
        time.sleep(0.5)
        summary = eng.stop()
    finally:
        arm.close()
    assert 20 < len(samples) < 80
    assert summary.n_reps == 0
    assert eng._thread is None


def test_bad_constructor_args():
    arm = SimArm(SimPatient(), realtime=False)
    with pytest.raises(ValueError):
        Engine(arm, "s", "p", True, reach_axis=3)
    with pytest.raises(ValueError):
        Engine(arm, "s", "p", True, reach_m=0.0)


def test_module_constants_match_section_4_2():
    assert engine_mod.F_PRESENT == 1.5
    assert engine_mod.OCCUPIED_WINDOW_S == 0.5
    assert engine_mod.ARM_DWELL_S == 1.0
    assert engine_mod.NEAR_START_M == 0.03 and engine_mod.HOLD_START_M == 0.02     # 15 Nov, see DECISIONS
    assert engine_mod.EMPTY_REST_N == 3.0 and engine_mod.EMPTY_MOVING_N == 7.0
    assert engine_mod.HAND_ON_N == 4.5 and engine_mod.MAX_BASELINE_N == 6.0
    assert engine_mod.OUT_DONE == 0.9 and engine_mod.OUT_TIMEOUT_S == 10.0
    assert engine_mod.STALL_SPEED == 0.01
    assert engine_mod.STALL_ASSIST_S == 1.5 and engine_mod.STALL_RESIST_S == 3.0


# --------------------------------------------------------------------------- stock SimPatient

def test_stock_patient_strong_auto_dial_falls_below_0_3_within_8_reps():
    # SimArm's own patient: reaches on the engine's cue (stiffness leaves the soft hold)
    eng, arm, samples, reps = make(SimPatient(strength=1.0), dial=1.0, auto=True)
    eng.run_until_reps(8, max_s=200)
    assert len(reps) == 8
    assert all(r.completed for r in reps)
    assert min([r.dial for r in reps[1:]] + [eng.dial]) < 0.3
    assert reps[0].contribution > 0.6
    assert arm.get_state().fault is None


def test_stock_patient_strong_full_resistance_completes_without_trip():
    eng, arm, samples, reps = make(SimPatient(strength=1.0), dial=-1.0, auto=False)
    eng.run_until_reps(3, max_s=120)
    assert len(reps) == 3
    assert all(r.completed and not r.rescued for r in reps)
    assert all(12.0 <= r.peak_force_n <= 22.0 for r in reps)
    assert arm.get_state().fault is None


@pytest.mark.parametrize("strength", [0.0, 0.3, 0.8])
def test_stock_patient_session_never_trips(strength):
    eng, arm, samples, reps = make(SimPatient(strength=strength), dial=1.0, auto=True)
    eng.run_until_reps(12, max_s=300)
    assert len(reps) == 12
    assert arm.get_state().fault is None
    assert max(float(np.linalg.norm(s.vel)) for s in samples) < 0.40


def test_weak_patient_auto_dial_falls_despite_gravity_sag():
    # 0.3 strength: the limb sags the handle 1.2-1.6 cm on the walls, which alone used to fail
    # the 1.5 cm path-error test and hold weak patients at +1 (see DECISIONS.md)
    eng, arm, samples, reps = make(SimPatient(strength=0.3), dial=1.0, auto=True)
    eng.run_until_reps(8, max_s=200)
    assert len(reps) == 8 and all(r.completed for r in reps)
    out_z = np.array([s.pos[2] for s in samples if s.phase == "out"])
    assert START[2] - out_z.mean() > 0.012            # the sag is still there
    assert all(r.path_err_mean_m < 0.005 for r in reps)
    assert eng.dial < 0.5
    dials = [r.dial for r in reps] + [eng.dial]
    assert all(b <= a for a, b in zip(dials, dials[1:]))   # falls, never rises


def test_limp_patient_auto_dial_stays_at_full_assist():
    eng, arm, samples, reps = make(SimPatient(strength=0.0), dial=1.0, auto=True)
    eng.run_until_reps(4, max_s=120)
    assert len(reps) == 4 and eng.dial == 1.0


# --------------------------------------------------------------------------- arm's own work

def test_lightly_pushing_carried_patient_does_not_score_about_one():
    # 0.05 strength at full assist: the arm's spring does most of the work
    eng, arm, samples, reps = make(SimPatient(strength=0.05), dial=1.0, auto=False)
    eng.run_until_reps(2, max_s=60)
    assert len(reps) == 2
    assert all(r.contribution < 0.6 for r in reps)


def test_contribution_includes_commanded_spring_force():
    eng, arm, samples, reps = make(cued(0.05), dial=1.0, auto=False)
    eng.run_until_reps(1, max_s=60)
    out = [s for s in samples if s.rep_idx == 0 and s.phase == "out"]
    t = np.array([s.t for s in out])
    pos = np.array([s.pos for s in out])
    f = np.array([s.force for s in out])
    end = (START[0] + REACH, START[1], START[2])
    person_only = rep_metrics(t, pos, f, START, end)["contribution"]
    assert person_only > 0.9                       # the old rule called this patient able
    assert reps[0].contribution < person_only - 0.3


# --------------------------------------------------------------------------- resist rescue ramp

def test_resist_rescue_ramps_to_transparent_without_lurch():
    # strong patient aiming exactly at the end: against full resistance it stalls at about
    # 2/3 of the reach while pushing about 15 N (the case that tripped with a one-step drop)
    eng, arm, samples, reps = make(cued(1.0, overshoot=0.0), dial=-1.0, auto=False, spy=True)
    eng.run_until_reps(1, max_s=40)
    assert reps[0].rescued is True
    assert arm.get_state().fault is None
    assert max(float(np.linalg.norm(s.vel)) for s in samples) < 0.40
    # the reach-axis stiffness went down in several steps, not one
    kx = [k[0] for k in arm.stiffness]
    i = kx.index(max(kx))
    steps = []
    for k in kx[i:]:
        if steps and k > steps[-1]:
            break
        steps.append(k)
    assert 300.0 - 1e-6 <= steps[0] <= 600.0 and steps[-1] == 0.0      # 15 Nov: the rep starts from the firm hold
    assert len(steps) >= 8


def test_resist_rescue_one_step_drop_would_trip(monkeypatch):
    # guards the test above: with no ramp the same patient trips the speed limit
    monkeypatch.setattr(engine_mod, "RESIST_RAMP_S", 1e-6)
    eng, arm, samples, reps = make(cued(1.0, overshoot=0.0), dial=-1.0, auto=False)
    eng.run_until_reps(1, max_s=40)
    assert arm.get_state().fault is not None and "speed" in arm.get_state().fault
