"""BandEngine (software/simple.py) on SimArm with the real arm's effects: 4.5 N Coulomb friction and the
measured empty-handle reading (3 N across the reach with pose, 3 to 7 N while moving). All simulated.

The hand is scripted (``Hand``): it follows a planned position along the reach with its own strength,
so level 4 (28 N) can be pushed (SimPatient's effort stops at 25 N).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from server.contract import RepResult, Sample
from software.simple import (BAND_IDS, BandEngine, DT, LEAD_M, LEVELS, OUT_M, K_WALL, is_band, level_of)
from software.sim_arm import SimArm

START = (0.45, 0.0, 0.30)
REAL = dict(empty_force_pose_n_per_m=(10.0, 0.0, 0.0), empty_force_moving_n=(3.0, 7.0), friction_n=4.5)


def min_jerk(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x ** 3 * (10 - 15 * x + 6 * x * x)


def cycle(depth=0.28, out_s=3.0, dwell_s=0.4, back_s=3.0, rest_s=1.0, wobble_m=0.0):
    """Planned hand position (m along the reach) at time t: out, dwell, back, rest, repeat."""
    period = out_s + dwell_s + back_s + rest_s

    def plan(t: float) -> float:
        u = t % period
        if u < out_s:
            s = depth * min_jerk(u / out_s)
        elif u < out_s + dwell_s:
            s = depth
        elif u < out_s + dwell_s + back_s:
            s = depth * (1 - min_jerk((u - out_s - dwell_s) / back_s))
        else:
            s = 0.0
        return s + wobble_m * math.sin(2 * math.pi * 2.0 * t) * (1.0 if 0.02 < s else 0.0)
    plan.period = period
    return plan


class Hand:
    """A scripted hand on the handle. ``strength`` 0 switches SimArm's own friction helper off:
    this hand pushes through the friction by itself, like a person does."""
    strength = 0.0

    def __init__(self, plan, sign=1.0, kp=1500.0, kd=40.0, cap=48.0, side_n=0.0):
        self.plan, self.sign, self.kp, self.kd, self.cap, self.side_n = plan, sign, kp, kd, cap, side_n
        self.present = True
        self.t0 = None
        self.fade = None            # (t_release, seconds): the grip eases off instead of vanishing

    def release(self, t: float, over_s: float = 0.0) -> None:
        if over_s <= 0:
            self.present = False
        else:
            self.fade = (t, over_s)

    def effort(self, t, pos, vel, goal):
        if self.t0 is None:
            self.t0 = t
        s = self.sign * (pos[0] - START[0])
        v = self.sign * vel[0]
        f = float(np.clip(self.kp * (self.plan(t - self.t0) - s) - self.kd * v, -self.cap, self.cap))
        out = np.array([self.sign * f, self.side_n * math.sin(2 * math.pi * 2.0 * t), 0.0])
        if self.fade is not None:
            out *= max(0.0, 1.0 - (t - self.fade[0]) / self.fade[1])
            if t - self.fade[0] >= self.fade[1]:
                self.present = False
        return out


def make(level=1, plan=None, sign=1, arm_kw=None, present=True, **kw):
    hand = Hand(plan or cycle(), sign=float(sign))
    hand.present = False                         # zeroed with nobody touching, as on the arm
    arm = SimArm(hand, start_pos=START, realtime=False, **(REAL if arm_kw is None else arm_kw))
    arm.connect()
    arm.zero_force()
    hand.present = present
    samples: list[Sample] = []
    reps: list[RepResult] = []
    eng = BandEngine(arm, "sess-b", "pat-b", True, reach_axis=0, reach_sign=sign, on_sample=samples.append,
                     on_rep=reps.append, exercise=f"push_{level}", **kw)
    eng.start()
    return eng, arm, hand, samples, reps


def prog(sample_or_pos, sign=1) -> float:
    p = sample_or_pos.pos if hasattr(sample_or_pos, "pos") else sample_or_pos
    return sign * (p[0] - START[0])


def spring_force(arm, sign=1) -> float:
    """What the simulated arm's spring really pulls with along the reach, towards the start (N)."""
    return float(-sign * arm._k[0] * (arm._target[0] - arm._pos[0]))


# --------------------------------------------------------------------------- ids and interface

def test_ids_and_levels():
    assert BAND_IDS == ("push_1", "push_2", "push_3", "push_4")
    assert [level_of(i) for i in BAND_IDS] == [1, 2, 3, 4] and level_of("push") is None and not is_band("reach")
    assert LEVELS == {1: 10.0, 2: 15.0, 3: 20.0, 4: 28.0}
    assert [round(LEVELS[n] / LEAD_M) for n in LEVELS] == [200, 300, 400, 560]
    with pytest.raises(ValueError):
        BandEngine(None, "s", "p", True, exercise="reach")


def test_server_kwargs_are_accepted_and_noops_exist():
    eng, arm, hand, samples, reps = make(2, dial=-0.3, auto=False, reach_m=0.28, calibrate=True,
                                         calibration_state={"x": 1}, reps=5)
    eng.set_dial(0.5, True), eng.go(), eng.resume()
    eng.run_for(0.5)
    snap = eng.snapshot()
    for key in ("pos", "target", "phase", "rep_idx", "force", "rep_count", "reps_target", "exercise", "done",
                "level", "level_force_n", "path_start", "path_end", "message", "countdown_s", "force_cap_n",
                "arm_mode", "group"):
        assert key in snap, key
    assert snap["exercise"] == "push_2" and snap["level"] == 2 and snap["level_force_n"] == 15.0
    assert snap["reps_target"] == 5 and snap["force_cap_n"] == 30.0 and snap["group"] == "push"
    assert snap["calibration"] is None and snap["arming"] is None
    assert np.allclose(snap["path_start"], START) and np.allclose(snap["path_end"], (0.75, 0.0, 0.30))
    s = eng.stop()
    assert s.exercise == "push_2" and s.simulated is True and arm.get_state().mode == "hold"


# --------------------------------------------------------------------------- reps from position

STYLES = {
    "slow": dict(out_s=4.5, back_s=4.5, dwell_s=0.6, rest_s=1.2),
    "fast": dict(out_s=2.0, back_s=2.0, dwell_s=0.2, rest_s=0.6),
    "wobbly": dict(out_s=3.0, back_s=3.0, dwell_s=0.5, rest_s=1.0, wobble_m=0.006),
}


@pytest.mark.parametrize("level", [1, 2, 3, 4])
@pytest.mark.parametrize("style", list(STYLES))
def test_ten_reps_are_counted_as_exactly_ten(level, style):
    plan = cycle(**STYLES[style])
    eng, arm, hand, samples, reps = make(level, plan)
    hand.side_n = 3.0 if style == "wobbly" else 0.0
    eng.run_for(10 * plan.period + 1.0)
    assert arm.get_state().mode == "compliant", arm.get_state().fault        # no trip
    assert eng.rep_count == 10 and len(reps) == 10
    assert [r.idx for r in reps] == list(range(10))
    for r in reps:
        assert r.mode == "resist" and r.completed and r.simulated and not r.rescued
        assert 0.24 <= r.rom_m <= 0.31 and r.duration_s > 1.0
        # the hand pushes the band, the friction and a little drag: near the level, never far above
        assert LEVELS[level] - 1.0 <= r.peak_force_n <= LEVELS[level] + 12.0, r.peak_force_n
        assert 0.0 < r.mean_force_n < r.peak_force_n
    assert eng.done and eng.snapshot()["message"] == "Set finished"
    assert eng.stiffness_commands == 1                                        # smooth by design


def test_counts_with_the_real_arm_reach_direction():
    plan = cycle()
    eng, arm, hand, samples, reps = make(3, plan, sign=-1)
    eng.run_for(3 * plan.period + 1.0)
    assert eng.rep_count == 3 and min(s.pos[0] for s in samples) < START[0] - 0.25
    assert np.allclose(eng.snapshot()["path_end"], (0.15, 0.0, 0.30))


def test_a_ten_centimetre_push_is_not_counted():
    plan = cycle(depth=0.10)
    eng, arm, hand, samples, reps = make(2, plan)
    eng.run_for(4 * plan.period)
    assert max(prog(s) for s in samples) > 0.08
    assert eng.rep_count == 0 and reps == []
    assert {s.phase for s in samples} <= {"idle", "out"}                      # it was "out", never "back"


def test_phases_and_rep_idx_for_the_app():
    plan = cycle()
    eng, arm, hand, samples, reps = make(1, plan)
    eng.run_for(2 * plan.period + 0.5)
    phases = [s.phase for s in samples]
    assert set(phases) == {"idle", "out", "back"}
    first_out = phases.index("out")
    assert samples[first_out].rep_idx == 0 and samples[0].rep_idx == -1
    assert any(s.phase == "back" and s.rep_idx == 1 for s in samples)
    assert all(s.rep_idx == -1 for s in samples if s.phase == "idle")


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_an_empty_handle_never_leaves_the_start(level):
    eng, arm, hand, samples, reps = make(level, present=False)
    eng.run_for(20.0)
    assert max(abs(prog(s)) for s in samples) < 0.002
    assert max(np.linalg.norm(np.array(s.pos) - START) for s in samples) < 0.002
    assert eng.rep_count == 0 and {s.phase for s in samples} == {"idle"} and arm.get_state().mode == "compliant"


# --------------------------------------------------------------------------- smoothness

@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_band_force_is_steady_between_6_and_27_cm_on_the_way_out(level):
    """The arm's real spring force along the reach stays within 2 N of the level while the hand pushes
    out between 6 and 27 cm. (The READING is the hand's force: the band plus friction and drag.)"""
    plan = cycle(out_s=3.5, back_s=3.5)
    eng, arm, hand, samples, reps = make(level, plan)
    band, reading = [], []
    for _ in range(int(3 * plan.period / DT)):
        eng.tick()
        s, st = eng.snapshot(), arm.get_state()
        if s["phase"] == "out" and 0.06 <= prog(st.pos) <= 0.27 and st.vel[0] > 0.005:
            band.append(spring_force(arm))
            reading.append(s["force"][0])
        arm.step(DT)
    assert len(band) > 300
    assert max(abs(f - LEVELS[level]) for f in band) <= 2.0, (min(band), max(band))
    assert np.std(band) < 0.5
    assert abs(np.mean(reading) - LEVELS[level]) < 12.0          # band + 4.5 N friction + drag, minus the artefact


def test_stiffness_is_commanded_once_and_ramped_on_a_level_change():
    plan = cycle()
    eng, arm, hand, samples, reps = make(1, plan)
    sent = []
    real = arm.set_stiffness
    arm.set_stiffness = lambda *k: (sent.append(k), real(*k))[1]
    eng.run_for(2 * plan.period)
    assert sent == [] and eng.stiffness_commands == 1                         # only the one at start
    assert tuple(arm._k) == (200.0, K_WALL, K_WALL)
    eng.set_level(3)
    eng.run_for(0.25)
    assert 200.0 < arm._k[0] < 400.0                                          # half way through the ramp
    eng.run_for(0.5)
    n = len(sent)
    assert n == 5 and sent[-1] == (400.0, K_WALL, K_WALL)                    # five steps, 0.1 s apart
    assert all(b[0] >= a[0] for a, b in zip(sent, sent[1:]))                  # a ramp, no step
    assert max(b[0] - a[0] for a, b in zip(sent, sent[1:])) <= 40.0 + 1e-9    # 2 N of band force per step
    eng.run_for(2 * plan.period)
    assert len(sent) == n                                                     # and nothing after it
    snap = eng.snapshot()
    assert snap["level"] == 3 and snap["level_force_n"] == 20.0 and snap["exercise"] == "push_3"
    with pytest.raises(ValueError):
        eng.set_level(5)


# --------------------------------------------------------------------------- letting go

def hold_at_full_travel(level, **kw):
    plan = cycle(depth=0.30, out_s=3.0, dwell_s=60.0)
    eng, arm, hand, samples, reps = make(level, plan, **kw)
    eng.run_for(4.0)
    assert prog(arm.get_state().pos) > 0.26
    return eng, arm, hand, samples


def back_speeds(eng, arm, seconds=12.0):
    v = []
    for _ in range(int(seconds / DT)):
        eng.tick()
        for _ in range(2):                       # look between the control ticks too
            arm.step(DT / 2)
            v.append(float(np.linalg.norm(arm._vel)))
    return v


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_let_go_at_full_travel_comes_back_slowly(level):
    """A grip that eases off over 0.1 s (a hand cannot drop 28 N in one tick): under 0.15 m/s, no trip."""
    eng, arm, hand, samples = hold_at_full_travel(level)
    hand.release(arm._t, over_s=0.1)
    v = back_speeds(eng, arm)
    st = arm.get_state()
    assert st.mode == "compliant", st.fault
    assert max(v) < 0.15, max(v)
    assert prog(st.pos) < 0.05                   # and it does come back, to within the friction dead band
    assert eng.rep_count == 1                    # it was out past 20 cm and is back: one rep


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_abrupt_let_go_does_not_trip(level):
    """The force vanishes between two ticks: the first 10 ms are not covered by any rule. No trip, and
    the speed is back under 0.15 m/s within 0.1 s."""
    eng, arm, hand, samples = hold_at_full_travel(level)
    hand.release(arm._t)
    v = back_speeds(eng, arm)
    st = arm.get_state()
    assert st.mode == "compliant", st.fault
    assert max(v) < 0.30, max(v)                 # the speed trip is at 0.40
    assert max(v[20:]) < 0.15, max(v[20:])
    assert prog(st.pos) < 0.05


def test_let_go_with_slow_stiffness_latency_does_not_chatter():
    eng, arm, hand, samples = hold_at_full_travel(4, arm_kw=REAL | {"stiffness_latency_s": 0.2})
    hand.release(arm._t, over_s=0.1)
    v = np.array(back_speeds(eng, arm, 8.0))
    assert arm.get_state().mode == "compliant" and v.max() < 0.15
    moving = v[120:800]                          # from 0.6 s after the let-go, for 3.4 s of the way back
    assert moving.min() > 0.02                   # one steady glide: never stop-and-go
    assert 0.04 < moving.mean() < 0.06 and moving.max() < 0.08


# --------------------------------------------------------------------------- end of travel and trips

def test_turn_back_and_over_travel():
    plan = cycle(depth=0.33, dwell_s=3.0)
    eng, arm, hand, samples, reps = make(2, plan)
    seen = {}
    for _ in range(int(5.0 / DT)):
        eng.tick()
        s = eng.snapshot()
        seen.setdefault((s["message"], s["over_travel"]), prog(arm.get_state().pos))
        arm.step(DT)
    assert 0.265 < seen[("Turn back", False)] < 0.28
    assert 0.305 < seen[("Turn back", True)] < 0.32
    assert spring_force(arm) == pytest.approx(LEVELS[2], abs=1.0)            # the band is still on out there
    assert max(prog(s.target) for s in samples) < max(prog(s) for s in samples) - 0.04   # the target never leads out


def test_after_a_trip_it_stops_commanding_and_says_so():
    plan = cycle(depth=0.45, out_s=4.0, dwell_s=30.0)                         # pushed out of the workspace box
    eng, arm, hand, samples, reps = make(1, plan)
    eng.run_for(8.0)
    st = arm.get_state()
    assert st.mode == "hold" and "workspace box" in st.fault
    snap = eng.snapshot()
    assert "has stopped" in snap["message"] and "workspace box" in snap["message"] and snap["phase"] == "idle"
    hand.present = False
    sent = []
    arm.set_target = lambda p: sent.append(p)
    eng.run_for(2.0)
    assert sent == [] and arm.get_state().mode == "hold"                      # never re-arms by itself
    assert eng.stop().n_reps == 0


def test_never_calls_set_test_limits():
    calls = []
    plan = cycle()
    eng, arm, hand, samples, reps = make(4, plan)
    arm.set_test_limits = lambda on: calls.append(on)
    eng.run_for(plan.period)
    eng.stop()
    assert calls == [] and arm.test_limits_on is False


# --------------------------------------------------------------------------- prepare and return home

def test_prepare_counts_down_zeroes_then_starts():
    hand = Hand(cycle())
    hand.present = False
    arm = SimArm(hand, start_pos=START, realtime=False, force_offset=(4.5, -2.5, 11.9), **REAL)   # not zeroed
    arm.connect()
    eng = BandEngine(arm, "s", "p", True, exercise="push_2", prepare=True)
    eng.start()
    assert eng.stage == "countdown" and arm.get_state().mode == "idle"
    eng.run_for(1.05)
    snap = eng.snapshot()
    assert snap["message"] == "Hands off: zeroing in 2" and 1.9 <= snap["countdown_s"] <= 2.1
    assert snap["phase"] == "idle" and eng.stiffness_commands == 0
    eng.run_for(2.2)
    assert eng.stage == "band" and arm.get_state().mode == "compliant"
    assert np.linalg.norm(arm.get_state().force) < 0.5                        # it was zeroed
    snap = eng.snapshot()
    assert snap["message"] is None and snap["countdown_s"] is None and eng.stiffness_commands == 1


def test_prepare_restarts_the_countdown_while_the_handle_moves_and_homes_from_afar():
    hand = Hand(cycle())
    hand.present = False
    arm = SimArm(hand, start_pos=START, realtime=False, **REAL)
    arm.connect()
    arm._pos = np.array([0.55, 0.0, 0.30])                                    # left 10 cm out
    eng = BandEngine(arm, "s", "p", True, exercise="push_1", prepare=True)
    eng.start()
    eng.run_for(1.0)
    assert eng.snapshot()["message"].startswith("Hands off: the arm moves to the start in")
    arm._vel = np.array([0.05, 0.0, 0.0])                                     # someone nudges it
    eng.tick()
    arm._vel = np.zeros(3)
    assert eng.snapshot()["countdown_s"] == pytest.approx(3.0, abs=0.05)
    eng.run_for(3.3)
    assert eng.stage == "band" and np.allclose(arm.get_state().pos, START, atol=1e-3)


def test_stop_returns_to_the_start_after_a_countdown():
    plan = cycle(out_s=3.0, dwell_s=60.0)
    eng, arm, hand, samples, reps = make(1, plan, return_home=True)
    eng.run_for(4.0)
    hand.present = False
    arm.hold()                                   # as the server's Hold would: it stays where it was let go
    out = prog(arm.get_state().pos)
    assert out > 0.2
    n = len(samples)
    s = eng.stop()
    msgs = [m for m in (samples[i] for i in range(n, len(samples)))]
    assert len(msgs) >= 290                      # 3 s of countdown samples
    assert np.allclose(arm.get_state().pos, START, atol=1e-6) and s.n_reps == 0
    assert eng.snapshot()["message"] == "Back at the start." and eng.snapshot()["countdown_s"] is None


def test_stop_does_not_move_a_held_handle_and_survives_an_interrupted_home():
    plan = cycle(out_s=3.0, dwell_s=60.0)
    eng, arm, hand, samples, reps = make(2, plan, return_home=True)
    eng.run_for(4.0)
    here = arm.get_state().pos
    t_before = arm._t
    s = eng.stop()                               # the hand is still pushing on it
    assert s.session_id == "sess-b" and "being held" in eng.snapshot()["message"]
    assert 9.5 < arm._t - t_before < 11.5        # it waited 10 s for the hand to let go, then gave up
    assert np.allclose(arm.get_state().pos, here, atol=0.03)

    eng, arm, hand, samples, reps = make(2, plan, return_home=True)
    eng.run_for(4.0)
    hand.present = False

    def interrupted():
        raise RuntimeError("home() interrupted after 3 of 500 steps; arm mode is 'hold'")
    arm.home = interrupted
    s = eng.stop()
    assert s.n_reps == 0 and "interrupted" in eng.snapshot()["message"] and arm.get_state().mode == "hold"


# --------------------------------------------------------------------------- found on the real arm, 15 Nov

REAL_QUAT = (-0.0017, -0.637798, 0.770077, -0.013832)        # robot/config.json start orientation (flange down)


def test_stiffness_goes_on_the_tool_axis_that_lies_along_the_reach():
    """The real arm applies the three stiffness values along the tool's axes. With the flange down the tool's
    y axis lies along base x, so (200, 500, 500) gave about 489 N/m along the push: level 1 pulled 25 N."""
    from software.simple import _rotation
    R = _rotation(REAL_QUAT)
    assert (R @ np.diag([200.0, 500.0, 500.0]) @ R.T)[0, 0] == pytest.approx(489.0, abs=3.0)   # what happened
    eng, arm, hand, samples, reps = make(1, present=False)
    assert eng._k_vector(200.0) == [200.0, K_WALL, K_WALL]                    # SimArm: base axes, unchanged
    eng._tool_R = R
    for level, f in LEVELS.items():
        k = eng._k_vector(f / LEAD_M)
        world = R @ np.diag(k) @ R.T
        assert world[0, 0] == pytest.approx(f / LEAD_M, abs=0.5)              # the level's stiffness along the push
        assert k[0] == K_WALL and k[2] == K_WALL and abs(k[1] - f / LEAD_M) < 15   # on tool y, walls on the others
        assert world[2, 2] == pytest.approx(K_WALL, abs=1.0) and 450.0 < world[1, 1] <= K_WALL + 5


class _HomingArm:
    """Just enough of an arm to test the guard on the move to the start."""
    realtime = True

    def __init__(self):
        self.force, self.held, self.homed = np.zeros(3), False, False

    def get_state(self):
        import types
        return types.SimpleNamespace(force=tuple(self.force), vel=(0.0, 0.0, 0.0), pos=(0.5, 0.0, 0.3), t=0.0,
                                     mode="hold" if self.held else "idle", fault=None, q=(0.0,) * 7)

    def hold(self):
        self.held = True

    def home(self):
        import time as _t
        for _ in range(100):
            if self.held:
                raise RuntimeError("home() interrupted; arm mode is 'hold'")
            _t.sleep(0.005)
        self.homed = True


def test_a_move_to_the_start_holds_when_something_presses_on_the_handle():
    """15 Nov: a start with the handle 10 cm out homed against a hand and the reading reached 61 N."""
    import threading
    arm = _HomingArm()
    eng = BandEngine(arm, "s", "p", False, exercise="push_1")
    th = threading.Thread(target=lambda: pytest.raises(RuntimeError, eng._home_guarded))
    th.start()
    time_limit = 200
    while not eng._homing and time_limit:
        time_limit -= 1
        __import__("time").sleep(0.002)
    eng._watch_home(arm.get_state())
    assert arm.held is False                                                  # nothing touching: it carries on
    arm.force = np.array([-12.0, 0.0, 0.0])                                   # a hand pushes back
    eng._watch_home(arm.get_state())
    th.join(2.0)
    assert arm.held is True and arm.homed is False and eng._homing is False


def test_start_countdown_waits_while_the_handle_is_pressed_before_a_move_to_the_start():
    hand = Hand(cycle())
    hand.present = False
    arm = SimArm(hand, start_pos=START, realtime=False, **REAL)
    arm.connect()
    arm.zero_force()
    arm._pos = np.array([0.55, 0.0, 0.30])                                    # left 10 cm out after a trip
    arm.force_offset = np.array([-20.0, 0.0, 0.0])                            # ... with a hand resting on it
    eng = BandEngine(arm, "s", "p", True, exercise="push_1", prepare=True)
    eng.start()
    eng.run_for(6.0)
    assert eng.stage == "countdown" and eng.snapshot()["countdown_s"] == pytest.approx(3.0, abs=0.05)
    assert np.allclose(arm.get_state().pos, (0.55, 0.0, 0.30))                # it has not moved
    arm.force_offset = np.zeros(3)                                            # hands off
    eng.run_for(3.4)
    assert eng.stage == "band" and np.allclose(arm.get_state().pos, START, atol=1e-3)


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_a_released_handle_is_led_back_at_one_steady_speed(level):
    """15 Nov on the arm: the empty handle came back go, stop, go (0 to 0.09 m/s, once a second). Now the
    band.s anchor walks back at 0.05 m/s: from 1.5 s after the let-go until the handle is within 6 cm of the
    start the speed never drops below 0.02 m/s and never exceeds 0.08 m/s."""
    eng, arm, hand, samples = hold_at_full_travel(level)
    hand.release(arm._t, over_s=0.1)
    v, s = [], []
    for _ in range(int(9.0 / DT)):
        eng.tick()
        arm.step(DT)
        v.append(float(np.linalg.norm(arm._vel)))
        s.append(prog(arm._pos))
    glide = [x for x, p in zip(v[150:], s[150:]) if p > 0.06]      # from 1.5 s after the let-go
    assert len(glide) > 250 and min(glide) > 0.02 and max(glide) < 0.08, (min(glide), max(glide))
    assert s[-1] < 0.05 and arm.get_state().mode == "compliant"


def test_a_slow_return_keeps_the_full_pull():
    """Coming back slower than the anchor walks (0.05 m/s), the hand feels the level force both ways."""
    plan = cycle(out_s=4.0, dwell_s=1.0, back_s=14.0)         # back at 0.02 m/s on average, 0.0375 at most
    eng, arm, hand, samples, reps = make(2, plan)
    back = []
    for _ in range(int(19.5 / DT)):
        eng.tick()
        if eng.phase == "back" and 0.10 <= prog(arm._pos) <= 0.20 and -0.045 < arm._vel[0] < -0.005:
            back.append(spring_force(arm))
        arm.step(DT)
    assert len(back) > 50 and min(back) > LEVELS[2] - 2.0 and max(back) < LEVELS[2] + 1.0


def test_stop_waits_for_the_hand_to_let_go_then_returns():
    plan = cycle(out_s=3.0, dwell_s=60.0)
    eng, arm, hand, samples, reps = make(1, plan, return_home=True)
    eng.run_for(4.0)
    hand.release(arm._t + 4.0, over_s=0.01)      # the hand lets go 4 s after Stop was pressed
    orig = hand.effort

    def effort(t, pos, vel, goal):
        if hand.fade and t < hand.fade[0]:
            saved, hand.fade = hand.fade, None
            try:
                return orig(t, pos, vel, goal)
            finally:
                hand.fade = saved
        return orig(t, pos, vel, goal)
    hand.effort = effort
    t_before = arm._t
    s = eng.stop()
    assert eng.snapshot()["message"] == "Back at the start." and np.allclose(arm.get_state().pos, START, atol=1e-6)
    assert 6.5 < arm._t - t_before < 9.0         # 4 s held, then a fresh 3 s countdown
