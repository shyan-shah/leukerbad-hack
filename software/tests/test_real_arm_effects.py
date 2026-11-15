"""Real-arm effects in the sim (pose- and motion-dependent empty-handle force, Coulomb friction)
and the engine rules that cope with them: occupancy, start refusal, near-start, setup.

Numbers come from context/MOTION_TEST.md and robot/TUNING.md (14 Nov, tool Flange, nothing
mounted): the empty reading changed by up to 3 N with pose and read 3 to 7 N while moving,
and friction is about 4.5 N. Everything here is simulated.
"""

from __future__ import annotations

import numpy as np
import pytest

from server.contract import RepResult, Sample
from software import engine as engine_mod
from software.engine import DT, Engine
from software.sim_arm import SimArm
from software.sim_patient import SimPatient

START = (0.45, 0.0, 0.30)
POSE = (10.0, 0.0, 0.0)          # N/m: 3 N across a 0.30 m reach, along the reach axis
POSE_ACROSS = (0.0, -6.5, -7.5)  # N/m: 3 N across the reach, lying across it (sideways and down), as measured on
                                 # 15 Nov (server/hw/results/drift_check_2026-11-15.json: up to 2.76 N, mostly y and z)
MOVING = (3.0, 7.0)              # N while moving
FRICTION = 4.5                   # N
REAL = dict(empty_force_pose_n_per_m=POSE, empty_force_moving_n=MOVING, friction_n=FRICTION)
ARTEFACT_ONLY = dict(empty_force_pose_n_per_m=POSE, empty_force_moving_n=MOVING)   # no friction to help it stop
LIVE4 = ["reach", "push", "pull", "armtest"]


def sim(patient=None, **kw) -> SimArm:
    arm = SimArm(patient or SimPatient(strength=0.0, present=False), start_pos=START, realtime=False, **kw)
    arm.connect()
    return arm


def make(exercise="reach", strength=1.0, present=True, arm_kw=None, **kw):
    arm = sim(SimPatient(strength=strength, present=present), **(arm_kw if arm_kw is not None else REAL))
    samples: list[Sample] = []
    reps: list[RepResult] = []
    kw.setdefault("calibrate", False)        # the band at the preset dial (calibration: test_calibration.py)
    eng = Engine(arm, "sess-r", "pat-r", True, on_sample=samples.append, on_rep=reps.append,
                 exercise=exercise, **kw)
    eng.start()
    return eng, arm, samples, reps


def x(v) -> float:
    return v[0] - START[0]


def run_until_phase(eng, phase, max_s=30.0):
    for _ in range(int(max_s / DT)):
        if eng.phase == phase:
            return
        eng.run_for(DT)
    raise AssertionError(f"phase {phase!r} not reached within {max_s} s (phase is {eng.phase!r})")


def drive(arm, k, target, seconds, lead=0.005):
    """Empty arm pulled by its own spring (no engine). ``lead`` keeps it under the speed trip."""
    arm.start_compliance()
    arm.set_stiffness(k, k, k)
    out = []
    for _ in range(int(seconds / DT)):
        st = arm.get_state()
        arm.set_target(tuple(np.clip(np.array(target) - st.pos, -lead, lead) + st.pos))
        arm.step(DT)
        out.append(arm.get_state())
    return out


# --------------------------------------------------------------------------- SimArm options

def test_options_are_off_by_default():
    arm = sim()
    assert arm.friction_n == 0 and arm.empty_force_moving_n == (0.0, 0.0)
    assert not arm.empty_force_pose_n_per_m.any()
    states = drive(arm, 300.0, (0.60, 0.0, 0.30), 2.0)
    assert all(np.allclose(s.force, 0.0) for s in states)             # nothing on the handle: reads zero
    assert abs(states[-1].pos[0] - 0.60) < 1e-3                         # and the spring reaches its target


def test_pose_term_changes_the_empty_reading_across_the_reach_only_in_the_reading():
    arm = sim(empty_force_pose_n_per_m=POSE)
    assert np.allclose(arm.get_state().force, 0.0)
    states = drive(arm, 300.0, (0.75, 0.0, 0.30), 6.0)
    end = states[-1]
    assert abs(end.pos[0] - 0.75) < 1e-3                                # the physics does not feel it
    assert end.force == pytest.approx((3.0, 0.0, 0.0), abs=0.02)        # 3 N across the 0.30 m reach, at rest
    arm.zero_force()
    assert np.allclose(arm.get_state().force, 0.0)                      # zeroing removes it at this pose only


def test_moving_term_reads_3_to_7_n_against_the_motion_and_nothing_at_rest():
    arm = sim(empty_force_moving_n=MOVING)
    states = drive(arm, 300.0, (0.75, 0.0, 0.30), 6.0)
    moving = [s for s in states if s.vel[0] > 0.02]
    assert moving and all(-7.01 <= s.force[0] <= -3.0 for s in moving)  # against +x motion
    fast = max(states, key=lambda s: s.vel[0])
    assert fast.vel[0] >= 0.10 and fast.force[0] == pytest.approx(-7.0, abs=0.01)
    assert np.allclose(states[-1].force, 0.0, atol=0.05)                # at rest again: nothing


@pytest.mark.parametrize("direction,expect", [("with", (1, 0, 0)), ((0, 0, 2.0), (0, 0, 1)), ((0, -1, 0), (0, -1, 0))])
def test_moving_term_direction_is_free(direction, expect):
    arm = sim(empty_force_moving_n=MOVING, empty_force_moving_dir=direction)
    states = drive(arm, 300.0, (0.75, 0.0, 0.30), 2.0)
    s = max(states, key=lambda st: st.vel[0])
    assert np.allclose(np.array(s.force) / np.linalg.norm(s.force), expect, atol=1e-6)
    assert 3.0 <= np.linalg.norm(s.force) <= 7.01


@pytest.mark.parametrize("k,short_cm", [(300.0, 1.5), (400.0, 1.125), (600.0, 0.75)])
def test_friction_stops_the_handle_short_of_the_target(k, short_cm):
    """TUNING.md section 2: a spring of stiffness K stops within 4.5 / K of its target."""
    arm = sim(friction_n=FRICTION)
    states = drive(arm, k, (0.47, 0.0, 0.30), 4.0, lead=0.05)          # a 2 cm move, as in motion-test stage 2
    short = (0.47 - states[-1].pos[0]) * 100
    assert abs(short) <= short_cm + 0.01                                # inside the dead band
    assert np.linalg.norm(states[-1].vel) == 0.0                        # stuck, not creeping
    assert np.allclose(states[-1].force, 0.0)                           # friction alone is not in the reading


def test_friction_holds_a_handle_at_rest_until_the_force_exceeds_it():
    arm = sim(friction_n=FRICTION)
    arm.start_compliance()
    arm.set_stiffness(300.0, 300.0, 300.0)
    arm.set_target((0.45 + 0.014, 0.0, 0.30))                           # 4.2 N: under the friction
    for _ in range(100):
        arm.step(DT)
        arm.set_target((0.45 + 0.014, 0.0, 0.30))
    assert arm.get_state().pos == pytest.approx(START)
    arm.set_target((0.45 + 0.03, 0.0, 0.30))                            # 9 N: moves
    for _ in range(100):
        arm.step(DT)
        arm.set_target((0.45 + 0.03, 0.0, 0.30))
    assert arm.get_state().pos[0] > 0.455


def test_bad_real_arm_options_rejected():
    p = SimPatient()
    for kw in (dict(friction_n=-1.0), dict(empty_force_moving_n=(5.0, 3.0)), dict(empty_force_moving_n=(-1.0, 3.0)),
               dict(empty_force_moving_dir="sideways"), dict(empty_force_moving_dir=(0, 0, 0)),
               dict(empty_force_pose_n_per_m=(1.0, 2.0))):
        with pytest.raises(ValueError):
            SimArm(p, **kw)


# =========================================================================== engine rules
#
# Option sets used below. NOISY adds sensor noise and the slowest stiffness latency seen.

NOISY = REAL | dict(force_noise_n=0.3, stiffness_latency_s=0.2)
ACROSS = NOISY | dict(empty_force_pose_n_per_m=POSE_ACROSS)       # pose reading across the reach, like the real arm
SETS = {"off": {}, "artefact": ARTEFACT_ONLY, "friction": dict(friction_n=FRICTION), "real": REAL, "real+noise": NOISY,
        "real-across": ACROSS}
EFFECT_SETS = ["artefact", "friction", "real", "real+noise", "real-across"]


# --------------------------------------------------------------------------- the hand-force rule itself

def _eng():
    eng, *_ = make("reach", arm_kw={})
    return eng


def test_hand_force_threshold_at_rest_is_f_present_above_the_largest_empty_reading():
    eng = _eng()
    rest = np.zeros(3)
    assert engine_mod.HAND_ON_N == engine_mod.F_PRESENT + engine_mod.EMPTY_REST_N == 4.5
    assert not eng._hand_on((3.0, 0.0, 0.0), rest)                  # the largest empty reading at rest
    assert not eng._hand_on((0.0, 0.0, -4.4), rest)
    assert eng._hand_on((0.0, 0.0, -4.6), rest)
    assert eng._hand_on((0.0, 0.0, -8.0), rest)                     # the simulated limb's weight


def test_hand_force_removes_up_to_7_n_along_the_motion_either_sign():
    eng = _eng()
    v = np.array([0.10, 0.0, 0.0])
    for along in (-7.0, -3.0, 3.0, 7.0):                             # an empty moving handle, either sign
        assert eng._hand_force((along, 0.0, 0.0), v) == pytest.approx(0.0)
        assert not eng._hand_on((along + 3.0 * np.sign(along), 0.0, 0.0), v)      # plus the pose change
    assert eng._hand_on((-7.0, 0.0, -8.0), v)                        # a carried limb: weight across the motion
    assert eng._hand_on((12.0, 0.0, 0.0), v)                         # a firm push along the motion
    assert not eng._hand_on((9.0, 0.0, 0.0), v)                      # decided towards "empty": 2 N left
    # motion in any direction: a freed handle springing up, its reading against that motion
    up = np.array([0.15, 0.0, 0.30])
    assert not eng._hand_on(tuple(-6.5 * up / np.linalg.norm(up)), up)
    # slower than V_MOVING: no allowance
    assert eng._hand_on((5.0, 0.0, 0.0), np.array([0.001, 0.0, 0.0]))


def test_one_tick_let_go_test_keeps_a_limbs_weight_while_the_handle_settles():
    """The instant let-go test takes the allowance along the reach only: a limb resting on a
    handle that is moving up or down is still a hand (the occupancy rule would discount it)."""
    eng = _eng()
    settling = np.array([0.004, 0.0, -0.03])
    weight = (1.0, 0.0, -8.0)
    assert not eng._hand_on(weight, settling)                        # occupancy: towards "empty" (0.5 s window bridges it)
    assert eng._hand_on(weight, settling, along_reach_only=True)     # let-go test: still held
    assert not eng._hand_on((-7.0, 0.0, 3.0), np.array([-0.2, 0.0, 0.0]), along_reach_only=True)   # thrown empty handle


# --------------------------------------------------------------------------- starts are not refused

@pytest.mark.parametrize("exercise", LIVE4)
@pytest.mark.parametrize("at", ["start", "far"])
def test_start_is_not_refused_on_a_prepared_arm_anywhere_on_the_reach(exercise, at):
    """Zeroed at the start pose, the empty reading is up to 3 N elsewhere on the reach (the old
    3.0 N limit refused that). 6.0 N still refuses a resting hand (8 N) and the wrong tool (12 N)."""
    arm = sim(**NOISY)
    arm.zero_force()
    if at == "far":
        arm._pos[0] += 0.30
        assert np.linalg.norm(arm._empty_force() - arm._zero_ref) == pytest.approx(3.0)
        across = sim(**ACROSS)
        across._pos[0] += 0.30
        assert np.linalg.norm(across._empty_force()) == pytest.approx(2.98, abs=0.01)
        assert across._empty_force()[0] == 0.0
    eng = Engine(arm, "s", "p", True, exercise=exercise, calibrate=False)
    eng.start()                                                      # no RuntimeError
    assert 0.0 <= np.linalg.norm(eng.force_baseline) < 3.5
    eng.run_for(2.0)
    assert arm.get_state().fault is None


def test_start_still_refuses_a_hand_on_the_handle_and_the_wrong_tool():
    assert 3.2 + 1.0 < engine_mod.MAX_BASELINE_N < 8.0               # above the real empty readings, below a limb
    arm = sim(SimPatient(strength=0.0, present=True), **REAL)
    arm.zero_force()                                                 # zeroed with the hand on: wrong
    arm.patient.present = False
    with pytest.raises(RuntimeError, match="zero_force"):            # 8 N when the hand comes off
        Engine(arm, "s", "p", True).start()
    arm = sim(force_offset=(0.0, 0.0, 12.0), **REAL)                 # the other team's tool, not zeroed
    with pytest.raises(RuntimeError, match="wrong tool"):
        Engine(arm, "s", "p", True).start()


# --------------------------------------------------------------------------- an empty handle

@pytest.mark.parametrize("exercise", LIVE4)
@pytest.mark.parametrize("name", EFFECT_SETS)
def test_empty_handle_never_arms_and_never_moves(exercise, name):
    eng, arm, samples, reps = make(exercise, present=False, arm_kw=SETS[name])
    eng.run_for(20.0)
    assert not reps and arm.get_state().fault is None
    assert all(s.rep_idx == -1 for s in samples)
    assert max(abs(s.pos[0] - samples[0].pos[0]) for s in samples) < 0.002


def _empty_handle_dragged(arm_kw):
    """An empty handle being moved along the reach by something that is not a hand on the sensor
    (here: the test moves it). Returns the share of ticks the engine called it occupied."""
    eng, arm, samples, reps = make("reach", present=False, arm_kw=arm_kw)
    eng.run_for(0.5)
    flags = []
    for i in range(300):                                             # 0.10 m/s out, then back
        v = 0.10 if i < 150 else -0.10
        arm._vel[:] = (v, 0.0, 0.0)
        arm._pos[0] += v * DT
        arm._t += DT
        arm._last_target_t = arm._t
        eng.tick()
        flags.append(eng._last_force_t is not None and arm._t - eng._last_force_t <= engine_mod.OCCUPIED_WINDOW_S)
    return sum(flags) / len(flags), reps


def test_moving_empty_handle_is_not_taken_for_a_hand(monkeypatch):
    share, reps = _empty_handle_dragged(ARTEFACT_ONLY)
    assert share == 0.0 and not reps
    # the rule before 15 Nov (1.5 N on the plain reading) called the same handle occupied all the way
    monkeypatch.setattr(engine_mod, "HAND_ON_N", 1.5)
    monkeypatch.setattr(engine_mod, "EMPTY_MOVING_N", 0.0)
    share, _ = _empty_handle_dragged(ARTEFACT_ONLY)
    assert share > 0.9


def test_baseline_does_not_absorb_a_moving_handles_reading():
    eng, arm, samples, reps = make("push", arm_kw=ARTEFACT_ONLY)
    run_until_phase(eng, "out")
    while eng._progress(arm.get_state().pos) < 0.5:
        eng.run_for(DT)
    arm.patient.present = False
    base0 = eng.force_baseline.copy()
    run_until_phase(eng, "release")
    eng.run_for(6.0)                                                 # ramp, then the 2 cm/s walk back: 3 N readings
    assert eng.phase == "release"
    walking = [s for s in samples[-300:]]
    assert max(abs(s.vel[0]) for s in walking) > 0.015
    assert np.linalg.norm(eng.force_baseline - base0) < 0.05         # frozen while it moves


def test_baseline_does_not_absorb_a_hand_resting_lightly_on_the_handle(monkeypatch):
    """A 4 N hand is under HAND_ON_N (4.5 N), so the handle counts as empty. Tracked into the
    baseline (3.8 N of it within 60 s before this rule), the empty handle would afterwards read
    4 N plus the pose change: over the threshold, an empty handle taken for a hand."""
    from software import sim_arm
    monkeypatch.setattr(sim_arm, "PASSIVE_LOAD_N", 4.0)
    eng, arm, samples, reps = make("reach", strength=0.0, arm_kw={})
    base0 = eng.force_baseline.copy()
    eng.run_for(60.0)
    assert eng.phase == "idle" and not reps                          # too light to count as a hand
    assert np.linalg.norm(samples[-1].force) == pytest.approx(4.0, abs=0.1)
    assert np.linalg.norm(eng.force_baseline - base0) < 0.05         # and not absorbed
    arm.patient.present = False                                      # the hand comes off: reads empty again
    eng.run_for(1.0)
    assert np.linalg.norm(samples[-1].force) < 0.2


def test_baseline_still_follows_slow_drift_on_an_empty_handle():
    eng, arm, samples, reps = make("reach", present=False, arm_kw=dict(force_drift_n_per_min=(0.5, -0.3, 0.4)))
    eng.run_for(300.0)                                               # 5 minutes: 3.5 N of drift in all
    assert not reps and np.linalg.norm(samples[-1].force) < 0.3      # followed, the handle still reads empty
    assert np.linalg.norm(eng.force_baseline) > 3.0


# --------------------------------------------------------------------------- hands off, assist side (the 8 cm rule)

def assist_let_go(arm_kw, strength, frac):
    eng, arm, samples, reps = make("reach", strength=strength, arm_kw=arm_kw)
    run_until_phase(eng, "out")
    while eng._progress(arm.get_state().pos) < frac:
        eng.run_for(DT)
    x0, t0 = arm.get_state().pos[0], samples[-1].t
    arm.patient.present = False
    n = len(samples)
    eng.run_for(6.0)
    after = samples[n:]
    idle_after = next(s.t for s in after if s.phase == "idle") - t0
    return eng, arm, max(s.pos[0] for s in after) - x0, idle_after, after


@pytest.mark.parametrize("name", ["off"] + EFFECT_SETS)
@pytest.mark.parametrize("strength,frac", [(0.0, 0.3), (0.0, 0.6), (0.3, 0.5), (1.0, 0.5)])
def test_assist_side_let_go_stops_within_8cm(name, strength, frac):
    eng, arm, travel, idle_after, after = assist_let_go(SETS[name], strength, frac)
    assert travel < 0.08                                              # measured: 7.6 cm at most (limp, 30%, no friction)
    # 15 Nov evening: a handle still travelling with no pull from the arm counts as held (a real hand moving it
    # freely reads under the motion allowance), so a handle that coasts on is seen as empty up to NOPULL_S later.
    # The 8 cm above is unchanged.
    # (only without friction: with it the handle stops at once and detection is at most 0.1 s later)
    slack = engine_mod.NOPULL_S if name in ("off", "artefact") else 0.1
    assert idle_after <= engine_mod.OCCUPIED_WINDOW_S + slack + 3 * DT
    assert eng.phase == "idle" and arm.get_state().fault is None
    assert np.linalg.norm(after[-1].vel) < 0.025      # 15 Nov: the empty handle is walked back to the start at 2 cm/s
    late = after[int(1.0 / DT):]
    # 15 Nov: the target is no longer latched for good; it only walks back towards the start at 2 cm/s
    assert all(b.target[0] <= a.target[0] + 1e-9 and a.target[0] - b.target[0] <= 0.02 * DT + 1e-6 for a, b in zip(late, late[1:]))


def test_assist_side_let_go_with_a_reading_along_the_motion_of_the_other_sign():
    """The moving reading's sign is not known on the real arm: with the motion instead of against."""
    kw = ARTEFACT_ONLY | dict(empty_force_moving_dir="with")
    for strength, frac in ((0.0, 0.3), (0.0, 0.6), (1.0, 0.5)):
        _, arm, travel, idle_after, _ = assist_let_go(kw, strength, frac)
        assert travel < 0.08 and arm.get_state().fault is None


def test_known_limit_a_moving_reading_across_the_motion_defeats_the_rule():
    """NOT a pass: a record of where the rule ends. If the real arm's moving reading (up to 7 N)
    pointed across the motion instead of along it, an empty handle would read as held and be
    carried well past 8 cm (measured here: 19 cm), as with the rule before 15 Nov. Kian must
    measure the direction of that reading before anyone holds the handle. If this test starts
    failing because the travel dropped under 8 cm, the limit is gone: update
    software/EXERCISES.md and turn it into an ordinary 8 cm test."""
    kw = dict(empty_force_pose_n_per_m=POSE, empty_force_moving_n=MOVING, empty_force_moving_dir=(0.0, 1.0, 0.0))
    eng, arm, travel, idle_after, _ = assist_let_go(kw, 0.0, 0.3)
    assert eng._hand_on((0.0, 7.0, 0.0), np.array([0.1, 0.0, 0.0]))    # an empty handle that reads as a hand
    assert travel > 0.08
    assert arm.get_state().fault is None                               # carried on at rep speed, no trip
    # at rest that handle still never arms a rep by itself
    eng, arm, samples, reps = make("reach", present=False, arm_kw=kw)
    eng.run_for(20.0)
    assert not reps and max(abs(s.pos[0] - samples[0].pos[0]) for s in samples) < 0.002


# --------------------------------------------------------------------------- hands off, resist side and the strength test

def let_go_at(exercise, frac, arm_kw, strength=1.0):
    eng, arm, samples, reps = make(exercise, strength=strength, arm_kw=arm_kw)
    if exercise == "pull":
        run_until_phase(eng, "idle")
    run_until_phase(eng, "out")
    if exercise == "armtest":
        eng.run_for(3.0 * frac)
    else:
        for _ in range(3000):
            if eng._progress(arm.get_state().pos) >= frac:
                break
            eng.run_for(DT)
        assert eng._progress(arm.get_state().pos) >= frac
    v_release = float(np.linalg.norm(arm.get_state().vel))
    s_release = eng._progress(arm.get_state().pos)
    arm.patient.present = False
    n = len(samples)
    eng.run_for(25.0)
    return eng, arm, reps, samples[n:], v_release, s_release


@pytest.mark.parametrize("name", EFFECT_SETS)
@pytest.mark.parametrize("exercise", ["push", "pull", "armtest"])
@pytest.mark.parametrize("frac", [0.25, 0.50, 0.90])
def test_resist_side_let_go_is_still_gentle_with_the_real_arm_effects(name, exercise, frac):
    """Shyan's release rule (software/tests/test_exercises.py) with the effects on."""
    eng, arm, reps, after, v_release, s_release = let_go_at(exercise, frac, SETS[name])
    speed = [float(np.linalg.norm(s.vel)) for s in after]
    assert max(speed) <= v_release + (0.035 if exercise == "armtest" else 0.005)      # the arm adds no speed
    assert max(speed[30:]) < 0.15
    if v_release < 0.15:
        assert max(speed) < 0.15
    st = arm.get_state()
    assert st.fault is None and st.mode == "compliant" and eng.error is None           # no trip
    assert all(s.phase == "idle" and s.rep_idx == -1 for s in after[1:])               # seen on the first tick
    assert max(eng._progress(s.pos) for s in after) < s_release + 0.08
    assert eng.phase == "idle"
    # back at the path start: exactly without friction, inside the 300 N/m dead band (1.5 cm) with it
    assert abs(eng._progress(st.pos)) * eng.reach_m <= (0.016 if "friction_n" in SETS[name] else 0.01)
    assert abs(eng._progress(st.pos)) * eng.reach_m <= engine_mod.NEAR_START_M
    n = len(reps)
    arm.patient.present = True                                       # a hand again: the session goes on
    eng.run_for(25.0)
    assert len(reps) > n and reps[-1].completed and arm.get_state().fault is None


# --------------------------------------------------------------------------- whole sessions with friction and the readings on

@pytest.mark.parametrize("name", EFFECT_SETS)
@pytest.mark.parametrize("exercise,strength,n", [("reach", 1.0, 5), ("reach", 0.3, 5), ("reach", 0.0, 4),
                                                 ("push", 1.0, 4), ("push", 0.5, 3), ("pull", 1.0, 4),
                                                 ("armtest", 0.8, 3), ("armtest", 0.3, 3)])
def test_sessions_complete_with_the_real_arm_effects(name, exercise, strength, n):
    eng, arm, samples, reps = make(exercise, strength=strength, arm_kw=SETS[name], reps=n)
    eng.run_until_reps(n, max_s=120.0)
    eng.run_for(4.0)                                                  # armtest: the walk back after the last try
    st = arm.get_state()
    assert st.fault is None and st.mode == "compliant"
    assert len(reps) == n and eng.done and eng.phase == "idle"
    assert all(r.completed for r in reps)
    if exercise == "armtest":
        assert all(r.mode == "isometric" and r.peak_force_n > 5.0 for r in reps)
        assert max(np.linalg.norm(s.vel) for s in samples) < 0.25     # relaxing after a try never snaps back
    else:
        # the path-error success limit (1.5 cm) and the range still hold with the friction lag
        assert all(r.path_err_mean_m < 0.015 for r in reps)
        assert all(r.rom_m > 0.23 for r in reps)
        # reps end by getting back to the start, not by the 10 s back-phase timeout
        assert samples[-1].t < n * 13.0


@pytest.mark.parametrize("name", ["friction", "real"])
def test_auto_dial_still_follows_the_patient_with_friction(name):
    eng, arm, samples, reps = make("reach", strength=1.0, arm_kw=SETS[name], reps=8)
    eng.run_until_reps(8, max_s=120.0)
    assert len(reps) == 8 and eng.dial < 0.3                          # strong: the help comes off
    eng, arm, samples, reps = make("reach", strength=0.0, arm_kw=SETS[name], reps=4)
    eng.run_until_reps(4, max_s=120.0)
    assert len(reps) == 4 and eng.dial == 1.0                         # limp: stays at full help
    assert all(r.contribution < 0.1 and r.completed for r in reps)


def test_back_phase_ends_inside_the_friction_dead_band_not_by_timeout():
    """A released handle on the resist side stops up to 2.5 cm short at dial -0.6 (180 N/m). A
    rep whose return stops between 2 and 3 cm from the start still ends, once the handle is
    at rest; without friction the 2 cm window is unchanged."""
    assert engine_mod.NEAR_START_M == 0.03 and engine_mod.HOLD_START_M == 0.02
    eng, arm, samples, reps = make("push", strength=1.0, arm_kw=dict(friction_n=FRICTION))
    run_until_phase(eng, "back")
    while eng._progress(arm.get_state().pos) * eng.reach_m > 0.028:
        eng.run_for(DT)
    # hold the handle still 2.8 cm from the start (a patient who stops just short)
    for _ in range(40):
        arm._vel[:] = 0.0
        arm._pos[0] = START[0] + 0.028
        eng.run_for(DT)
        if eng.phase == "idle":
            break
    assert eng.phase == "idle" and len(reps) == 1 and reps[0].completed
    # and while it is still moving through 2.8 cm the rep is not cut short
    eng2, arm2, _, reps2 = make("push", strength=1.0, arm_kw={})
    run_until_phase(eng2, "back")
    while eng2._progress(arm2.get_state().pos) * eng2.reach_m > 0.028:
        eng2.run_for(DT)
    assert eng2.phase == "back" and abs(arm2.get_state().vel[0]) > engine_mod.STALL_SPEED


def test_idle_near_the_start_walks_the_target_there_and_then_holds_it_firmly():
    """15 Nov: near the start the idle target walks to the start (2 cm/s), then the hold ramps to k_max."""
    eng, arm, samples, reps = make("reach", strength=0.0, arm_kw={}, reps=1)
    eng.run_until_reps(1, max_s=60.0)
    eng.run_for(4.0)
    assert samples[-1].target == pytest.approx(START)
    assert tuple(eng._cmd[1]) == pytest.approx((arm.limits.k_max,) * 3)
    assert arm.get_state().fault is None and max(np.linalg.norm(s.vel) for s in samples[-400:]) < 0.15


# --------------------------------------------------------------------------- setup: a session that starts away from the path start

def pull_then(nxt, arm_kw, **kw):
    arm = sim(SimPatient(strength=0.8), **arm_kw)
    eng = Engine(arm, "s1", "p", True, exercise="pull", reps=2, calibrate=False)
    eng.start()
    eng.run_until_reps(2, max_s=90.0)
    eng.run_for(0.5)
    eng.stop()
    assert x(arm.get_state().pos) > 0.20                              # pull leaves the handle at the far end
    samples, reps = [], []
    kw.setdefault("calibrate", False)
    eng = Engine(arm, "s2", "p", True, exercise=nxt, on_sample=samples.append, on_rep=reps.append, **kw)
    eng.start()
    return eng, arm, samples, reps


@pytest.mark.parametrize("name", ["off", "real", "real+noise"])
@pytest.mark.parametrize("nxt", ["armtest", "reach", "push", "pull"])
def test_session_after_a_pull_guides_the_patient_back_and_then_runs(nxt, name):
    """Before 15 Nov: the next session began in idle with the handle 28 cm out, the simulated
    patient hauled it to the start at 0.45 m/s, the speed trip fired within 0.03 s and the
    session sat in hold with no reps for ever."""
    n = 3 if nxt == "armtest" else 2
    eng, arm, samples, reps = pull_then(nxt, SETS[name], reps=n)
    if nxt == "pull":
        assert eng.phase == "idle"                                    # already at its own start (the far end)
    else:
        assert eng.phase == "setup"
    eng.run_until_reps(n, max_s=90.0)
    st = arm.get_state()
    assert st.fault is None and st.mode == "compliant"
    assert len(reps) == n and all(r.completed for r in reps)
    if nxt != "pull":
        setup = [s for s in samples if s.phase == "setup"]
        assert setup and setup[0] is samples[0] and all(s.rep_idx == -1 and s.dial == 0.0 for s in setup)
        assert 1.0 < setup[-1].t < 8.0                                # brought back in a few seconds
        assert abs(x(setup[-1].pos)) <= engine_mod.NEAR_START_M + 1e-9
        assert max(np.linalg.norm(s.vel) for s in setup) < 0.30       # well under the 0.40 m/s trip
        first_rep = next(s for s in samples if s.rep_idx == 0)
        assert first_rep.t > setup[-1].t                              # reps only after the setup


@pytest.mark.parametrize("nxt", ["armtest", "reach", "push"])
def test_setup_never_drives_an_empty_handle_and_waits_for_a_person(nxt):
    eng, arm, samples, reps = pull_then(nxt, REAL)
    arm.patient.present = False
    eng.run_for(0.2)
    left = arm.get_state().pos[0]
    n = len(samples)
    eng.run_for(10.0)
    assert eng.phase == "setup" and not reps and arm.get_state().fault is None
    assert all(s.phase == "setup" for s in samples[n:])
    assert max(abs(s.pos[0] - left) for s in samples[n:]) < 0.003     # nothing moved along the reach
    arm.patient.present = True                                        # the person comes back and brings it home
    arm.cue("back")
    eng.run_until_reps(1, max_s=60.0)
    assert reps and arm.get_state().fault is None


def test_setup_does_not_pull_a_handle_left_beyond_the_path_end():
    """A short reach (--reach-m 0.10) started with the handle 28 cm out: the setup target stays
    beside the hand. Clamped to the path end it pulled the handle with the soft hold still on
    (15 N) and tripped the speed limit in 40 ms."""
    eng, arm, samples, reps = pull_then("reach", {}, reach_m=0.10)
    arm.patient.present = False
    eng.run_for(0.1)
    left = arm.get_state().pos[0]
    eng.run_for(5.0)
    assert arm.get_state().fault is None and eng.phase == "setup"
    assert abs(arm.get_state().pos[0] - left) < 0.003
    assert all(abs(s.target[0] - s.pos[0]) < 1e-9 for s in samples[20:])


def test_setup_is_not_entered_at_the_start_and_is_not_a_patient_cue():
    eng, arm, samples, reps = make("reach", arm_kw=REAL)
    assert eng.phase == "idle" and arm.auto_cue is False             # 15 Nov: the engine cues every line rep itself
    eng, arm, samples, reps = pull_then("reach", {})
    assert eng.phase == "setup" and arm.auto_cue is False            # the stiffness change is not a "go"
    run_until_phase(eng, "idle")
    assert arm.auto_cue is False


# --------------------------------------------------------------------------- armtest: the spring is walked back after the last try too

def test_armtest_last_try_is_walked_back_like_the_others():
    """With 200 ms stiffness latency the last try used to go straight to idle: the 600 N/m
    spring was still on when the target jumped to the start and the relaxing arm was snapped
    back at 0.43 m/s (speed trip, session lost after the last try)."""
    eng, arm, samples, reps = make("armtest", strength=0.8, arm_kw=NOISY)
    eng.run_until_reps(3, max_s=60.0)
    assert eng.done and eng.phase == "back"                           # resting, target walking back
    eng.run_for(4.0)
    assert eng.phase == "idle" and arm.get_state().fault is None
    assert max(np.linalg.norm(s.vel) for s in samples) < 0.25
    assert len(reps) == 3 and all(r.completed for r in reps)
