"""Soak of Row and the strength test (software/simple_more.py) through the real server routes
(server.api.create_app: HTTP, Hub, SQLite, the default engine factory) on ONE SimArm kept across 30
back-to-back sessions, as `server.run --sim` keeps one arm: 20 Row sessions and 10 strength tests in a
shuffled order, each with a random level, strength and tempo. SimArm has 4.5 N Coulomb friction and the
measured empty-handle reading. All of it is simulated: it says nothing about the real arm.

Built like Shiv's soak of Push (test_simple_soak.py, which is not changed): sim time is stepped
(SimArm(realtime=False)), the engine is ticked from here, and what "really happened" is read from the
simulated arm (true position, speed, mode), not from the engine.

Row session: n full pulls (3 to 6) at a random level and tempo by a hand strong enough for the level,
some with a level change in the middle and some with one short pull that must not count; then the hand
lets go and the session is stopped (the arm returns to the start pose by itself).
Strength session: three tries with a random push (8 to 26 N) and a random way of letting go.

The soak runs once (about 40 s); each requirement is its own test.
"""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from server.api import create_app
from software.sim_arm import SimArm
from software.simple import DT, LEVELS
from software.simple_more import FAR_M, PUSH_S, READY_S, REST_S
from software.tests.test_simple import REAL, START, cycle
from software.tests.test_simple_more import PushHand, RowHand

SEED = 20261116
KINDS = ["row"] * 20 + ["strength"] * 10
NINE = [f"push_{n}" for n in LEVELS] + [f"row_{n}" for n in LEVELS] + ["strength"]
AT_START_M = 0.005


class Switch:
    """The one 'patient' the arm keeps: whichever scripted hand the current session uses."""
    strength = 0.0

    def __init__(self) -> None:
        self.hand = None
        self._present = False

    @property
    def present(self) -> bool:
        return self._present if self.hand is None else self.hand.present

    @present.setter
    def present(self, v: bool) -> None:
        self._present = bool(v)
        if self.hand is not None:
            self.hand.present = bool(v)

    def effort(self, t, pos, vel, goal):
        return np.zeros(3) if self.hand is None else self.hand.effort(t, pos, vel, goal)


def _drive(eng, arm, seconds, rec, watch=None):
    for _ in range(int(round(seconds / DT))):
        eng.tick()
        for _ in range(2):
            arm.step(DT / 2)
            v = float(np.linalg.norm(arm._vel))
            rec["v_max"] = max(rec["v_max"], v)
            if not arm.patient.present:                         # nobody on the handle: the arm's own doing.
                # Along the reach only: when a simulated hand lets go, its 8 N of limb weight leaves the
                # handle too and the 500 N/m wall lifts it 1.6 cm at 0.13 m/s, which is not the band's return.
                rec["v_free"] = max(rec["v_free"], abs(float(arm._vel[0])))
            if watch is not None:
                watch(v)
        if arm._mode == "hold" and eng.stage == "band" and not rec["trip"]:
            rec["trip"] = arm._fault or "hold"


def _to_band(eng, arm, rec, max_s=40.0):
    for _ in range(int(max_s / DT)):
        if eng.stage in ("band", "error"):
            break
        _drive(eng, arm, DT, rec)
    rec["stage"] = eng.stage


def run_soak(db_path, seed: int = SEED) -> list[dict]:
    rng = np.random.default_rng(seed)
    kinds = list(KINDS)
    rng.shuffle(kinds)
    sw = Switch()
    arm = SimArm(sw, start_pos=START, realtime=False, **REAL)
    app = create_app(lambda: arm, db_path, site_dir=str(db_path) + ".nosite", live_exercises=NINE)
    hub = app.state.hub
    out = []
    with TestClient(app) as c:
        for i, kind in enumerate(kinds):
            rec = {"i": i, "kind": kind, "trip": None, "v_max": 0.0, "crash": None, "v_band": 0.0, "v_free": 0.0}
            try:
                if kind == "row":
                    level = int(rng.integers(1, 5))
                    n = int(rng.integers(3, 7))
                    out_s, back_s = float(rng.uniform(2.0, 4.5)), float(rng.uniform(2.0, 4.5))
                    plan = cycle(out_s=out_s, back_s=back_s, dwell_s=float(rng.uniform(0.2, 0.7)),
                                 rest_s=float(rng.uniform(0.6, 1.4)), wobble_m=float(rng.choice([0.0, 0.0, 0.006])))
                    short = bool(rng.random() < 0.3)            # one 10 cm pull first: it must not count
                    change = int(rng.integers(1, 5)) if rng.random() < 0.4 else None
                    top = max(level, change or level)           # strong enough for every level of the session
                    hand = RowHand(plan, cap=float(LEVELS[top] + rng.uniform(10.0, 20.0)))
                    rec |= {"level": level, "planned": n, "tempo": round(out_s + back_s, 1), "short": short, "change": change}
                    sw.hand, hand.present = hand, False
                    r = c.post("/api/session/start", json={"patient_id": "soak-more", "exercise": f"row_{level}", "reps": n})
                    assert r.status_code == 200, r.text
                    eng = hub.engine
                    _to_band(eng, arm, rec)
                    rec["at_far_m"] = float(abs(arm._pos[0] - (START[0] + FAR_M)))
                    if short:
                        sp = cycle(depth=0.10, out_s=1.5, back_s=1.5, dwell_s=0.3, rest_s=0.7)
                        hand.plan, hand.t0, hand.present = sp, None, True
                        _drive(eng, arm, sp.period, rec)
                        rec["short_counted"] = eng.rep_count
                        hand.plan, hand.t0 = plan, None
                    hand.present = True
                    half = (n // 2) * plan.period + 0.5 * out_s
                    if change is not None:
                        _drive(eng, arm, half, rec)
                        assert c.post("/api/level", json={"level": change}).status_code == 200
                        _drive(eng, arm, n * plan.period + 1.0 - half, rec)
                    else:
                        _drive(eng, arm, n * plan.period + 1.0, rec)
                    rec["counted"] = eng.rep_count
                    rec["ended_as"] = f"row_{change if change is not None else level}"
                else:
                    force = float(rng.uniform(8.0, 26.0))
                    hand = PushHand(force_n=force, rise_s=float(rng.uniform(0.3, 1.0)), fall_s=float(rng.choice([0.0, 0.1, 0.3])))
                    rec |= {"force": round(force, 1), "fall_s": hand.fall_s, "planned": 3}
                    sw.hand, hand.present = hand, False
                    r = c.post("/api/session/start", json={"patient_id": "soak-more", "exercise": "strength"})
                    assert r.status_code == 200, r.text
                    eng = hub.engine
                    hand.eng = eng
                    _to_band(eng, arm, rec)
                    hand.present = True
                    _drive(eng, arm, 3 * (READY_S + PUSH_S + REST_S) + 0.5, rec,
                           watch=lambda v: rec.__setitem__("v_band", max(rec["v_band"], v)))
                    rec["counted"] = eng.rep_count
                    rec["peaks"] = [r.peak_force_n for r in eng.reps]
                    rec["ended_as"] = "strength"
                rec["mode_before_stop"] = arm._mode
                # the person lets go, then the app stops the session. A row hand may be a second into its next
                # pull: it eases off over 0.1 s, as a hand does (an instant let-go is in test_simple_more.py)
                if kind == "row":
                    hand.release(arm._t, over_s=0.1)
                    _drive(eng, arm, 0.2, rec)
                sw.present = False
                _drive(eng, arm, 1.0, rec)
                s = c.post("/api/session/stop").json()
                rec |= {"stored": s["n_reps"], "stored_as": s["exercise"], "mode_after": arm._mode,
                        "from_start_m": float(np.linalg.norm(arm._pos - np.array(START))),
                        "message": eng.snapshot()["message"], "test_limits": arm.test_limits_on,
                        "db_reps": len(c.get(f"/api/sessions/{s['session_id']}/reps").json())}
            except Exception as e:      # noqa: BLE001  (reported by the fixture)
                rec["crash"] = repr(e)
                try:
                    c.post("/api/session/stop")
                except Exception:       # noqa: BLE001
                    pass
            out.append(rec)
    return out


@pytest.fixture(scope="module")
def soak(tmp_path_factory):
    out = run_soak(tmp_path_factory.mktemp("soak_more") / "soak.db")
    crashed = [(s["i"], s["kind"], s["crash"]) for s in out if s["crash"]]
    assert not crashed, crashed
    return out


def _rows(soak, kind):
    return [s for s in soak if s["kind"] == kind]


def test_thirty_sessions_ran(soak):
    assert len(_rows(soak, "row")) == 20 and len(_rows(soak, "strength")) == 10
    assert all(s["stage"] == "band" for s in soak), [(s["i"], s["stage"]) for s in soak if s["stage"] != "band"]
    assert {s["level"] for s in _rows(soak, "row")} == {1, 2, 3, 4}
    assert any(s["change"] for s in _rows(soak, "row")) and any(s["short"] for s in _rows(soak, "row"))


def test_rep_counts_are_exact(soak):
    bad = [(s["i"], s["kind"], s["planned"], s["counted"], s["stored"], s["db_reps"]) for s in soak
           if not (s["planned"] == s["counted"] == s["stored"] == s["db_reps"])]
    assert not bad, bad
    assert all(s["short_counted"] == 0 for s in _rows(soak, "row") if s["short"])


def test_no_trips(soak):
    bad = [(s["i"], s["kind"], s["trip"], s["mode_before_stop"]) for s in soak
           if s["trip"] or s["mode_before_stop"] != "compliant"]
    assert not bad, bad


def test_no_session_ends_in_hold_and_every_one_ends_at_the_start(soak):
    bad = [(s["i"], s["kind"], s["mode_after"], round(s["from_start_m"], 4), s["message"]) for s in soak
           if s["mode_after"] == "hold" or s["from_start_m"] > AT_START_M or s["message"] != "Back at the start."]
    assert not bad, bad


def test_row_starts_at_the_far_end_and_is_stored_at_the_level_it_ended_on(soak):
    rows = _rows(soak, "row")
    assert max(s["at_far_m"] for s in rows) < 0.002
    assert all(s["stored_as"] == s["ended_as"] for s in soak), [(s["i"], s["stored_as"], s["ended_as"]) for s in soak]


def test_nothing_ever_moves_faster_than_the_speed_trip_and_strength_stays_under_15_cm_per_s(soak):
    # with a hand on it the fastest planned pull peaks at 0.26 m/s; the speed trip is at 0.40
    assert max(s["v_max"] for s in soak) < 0.40, sorted((round(s["v_max"], 3), s["i"], s["kind"]) for s in soak)[-3:]
    # with nobody on it (the moves, the countdowns, after the let-go): never faster than 0.15 m/s along the reach
    assert max(s["v_free"] for s in soak) < 0.15, sorted((round(s["v_free"], 3), s["i"], s["kind"]) for s in soak)[-3:]
    st = _rows(soak, "strength")
    assert max(s["v_band"] for s in st) < 0.15, [(s["i"], s["force"], s["fall_s"], round(s["v_band"], 3)) for s in st]


def test_strength_peaks_match_the_push(soak):
    for s in _rows(soak, "strength"):
        assert len(s["peaks"]) == 3
        assert all(abs(p - s["force"]) < 2.5 for p in s["peaks"]), (s["i"], s["force"], s["peaks"])


def test_the_test_limits_are_never_switched_on(soak):
    assert not any(s["test_limits"] for s in soak)
