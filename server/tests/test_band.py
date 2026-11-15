"""Push at four fixed levels (push_1 .. push_4): exercise list, /api/level, feed fields, the band engine
behind the default engine factory on SimArm, the mock, the note, and what --robot offers."""
import argparse
import time
from functools import partial

import pytest
from fastapi.testclient import TestClient

from server import exercises
from server.api import create_app
from server.mock import MockArm, MockEngine
from server.note import session_note
from server.contract import RepResult, SessionSummary
from server.run import exercise_sets

BAND = ["push_1", "push_2", "push_3", "push_4"]
FIELDS = {"group", "level", "level_force_n", "message", "countdown_s", "path_start", "path_end", "force_cap_n"}


def _mock_client(tmp_path, **kw):
    return TestClient(create_app(MockArm, tmp_path / "b.db", engine_factory=partial(MockEngine, time_scale=100),
                                 site_dir=tmp_path / "nosite", live_exercises=BAND + ["reach", "push"], **kw))


def _wait(c, pred, timeout=15):
    t0 = time.time()
    st = {}
    while time.time() - t0 < timeout:
        st = c.get("/api/state").json()
        if pred(st):
            return st
        time.sleep(0.01)
    raise AssertionError(f"state never matched; last: {st}")


def test_levels_match_the_engine():
    from software.simple import BAND_IDS, LEVELS
    assert exercises.BAND_LEVELS == LEVELS and exercises.BAND_IDS == BAND_IDS == tuple(BAND)
    assert [exercises.band_level(i) for i in BAND] == [1, 2, 3, 4]
    assert exercises.band_level("push") is None and not exercises.is_band("reach") and not exercises.is_band(None)


def test_exercise_list_has_group_level_and_newtons(tmp_path):
    with _mock_client(tmp_path) as c:
        out = {e["id"]: e for e in c.get("/api/exercises").json()}
    assert list(out)[:4] == BAND
    assert out["push_1"] == {"id": "push_1", "name": "Push · Level 1 (10 N)", "kind": "resist", "reps": 10,
                             "calibrates": False, "group": "push", "level": 1, "level_force_n": 10.0}
    assert [out[i]["level_force_n"] for i in BAND] == [10.0, 15.0, 20.0, 28.0]
    assert out["reach"]["group"] == "reach" and out["reach"]["level"] is None and out["reach"]["level_force_n"] is None
    assert out["push"]["calibrates"] is True and out["push"]["group"] == "push"
    assert exercises.info("pull")["group"] == "row"


def test_mock_plays_push_levels_with_countdown_fields_and_level_change(tmp_path):
    slow = partial(MockEngine, time_scale=3)
    app = create_app(MockArm, tmp_path / "b.db", engine_factory=slow, site_dir=tmp_path / "nosite",
                     live_exercises=BAND)
    with TestClient(app) as c:
        assert c.post("/api/level", json={"level": 2}).status_code == 409           # no session
        with c.websocket_connect("/ws/live") as ws:
            r = c.post("/api/session/start", json={"patient_id": "sim-b", "exercise": "push_2", "reps": 2})
            assert r.status_code == 200 and r.json()["exercise"] == "push_2"
            m = next(m for m in iter(ws.receive_json, None) if m["type"] == "sample")
        assert FIELDS <= set(m) and m["exercise"] == "push_2" and m["group"] == "push"
        assert m["level"] == 2 and m["level_force_n"] == 15.0 and m["calibration"] is None and m["force_cap_n"] == 30.0
        assert m["message"].startswith("Hands off: zeroing in ") and 0 < m["countdown_s"] <= 3.0
        assert len(m["path_start"]) == 3 and abs(m["path_end"][0] - m["path_start"][0]) == pytest.approx(0.30)
        st = _wait(c, lambda s: s.get("phase") == "out")
        assert st["message"] is None and st["countdown_s"] is None and st["level"] == 2
        assert c.post("/api/level", json={"level": 4}).json() == {"ok": True, "level": 4, "level_force_n": 28.0}
        st = c.get("/api/state").json()
        assert st["level"] == 4 and st["level_force_n"] == 28.0 and st["exercise"] == "push_4"
        assert c.post("/api/level", json={"level": 5}).status_code == 422
        c.post("/api/session/stop")
        c.post("/api/session/start", json={"patient_id": "sim-b", "exercise": "push_1", "reps": 1})
        c.post("/api/session/stop")


def test_level_is_refused_for_an_exercise_without_levels(tmp_path):
    with _mock_client(tmp_path) as c:
        c.post("/api/session/start", json={"patient_id": "sim-b", "exercise": "reach"})
        r = c.post("/api/level", json={"level": 2})
        assert r.status_code == 409 and "level" in r.json()["detail"]
        st = c.get("/api/state").json()
        assert FIELDS <= set(st) and st["level"] is None and st["message"] is None      # nulls for other engines
        c.post("/api/session/stop")


def test_level_needs_the_operator_token(tmp_path):
    with _mock_client(tmp_path, control_token="secret") as c:
        assert c.post("/api/level", json={"level": 2}).status_code == 403


# ---------------------------------------------------------------- the real band engine on SimArm, through the API

def test_band_engine_through_the_api_on_simarm(tmp_path):
    """Default engine factory -> software.simple.BandEngine on a real-time SimArm: hands-off countdown, zero,
    reps counted from position, a level change, then the return to the start at stop. About 20 s."""
    pytest.importorskip("software.simple")
    from software.sim_arm import SimArm
    from software.sim_patient import SimPatient

    arm_box = []

    def arm_factory():
        arm = SimArm(SimPatient(strength=1.0), friction_n=4.5)
        arm_box.append(arm)
        return arm

    app = create_app(arm_factory, tmp_path / "s.db", site_dir=tmp_path / "nosite", live_exercises=BAND,
                     exports_dir=tmp_path / "exports")
    with TestClient(app) as c:
        r = c.post("/api/session/start", json={"patient_id": "sim-band", "exercise": "push_1", "reps": 2,
                                               "calibrate": True, "dial": -0.3})
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]
        st = _wait(c, lambda s: s.get("countdown_s"))
        assert st["message"].startswith("Hands off: zeroing in ") and st["phase"] == "idle" and st["level"] == 1
        st = _wait(c, lambda s: s.get("arm_mode") == "compliant" and s.get("message") is None)
        assert st["calibration"] is None and st["arming"] is None and st["force_cap_n"] == 30.0
        assert st["group"] == "push" and st["level_force_n"] == 10.0 and st["reps_target"] == 2
        _wait(c, lambda s: (s.get("rep_count") or 0) >= 1, timeout=30)
        assert c.post("/api/level", json={"level": 2}).status_code == 200
        st = _wait(c, lambda s: s.get("done"), timeout=30)
        assert st["rep_count"] >= 2 and st["exercise"] == "push_2" and st["level"] == 2
        t0 = time.time()
        s = c.post("/api/session/stop").json()
        assert s["exercise"] == "push_2" and s["n_reps"] >= 2 and s["resistance_n"] is None
        reps = c.get(f"/api/sessions/{sid}/reps").json()
        assert len(reps) == s["n_reps"] and all(r["mode"] == "resist" and r["completed"] for r in reps)
        assert all(r["exercise"] == "push_2" for r in reps)
        note = c.get(f"/api/sessions/{sid}/note").text
        assert "constant resistance of 15 N (level 2 of 4)" in note and "resistance level 2 (15 N constant band)" in note
        assert c.get("/api/health").json()["session"] is False
    # the simulated hand keeps holding the handle, so the arm must NOT have been driven home under it
    assert time.time() - t0 < 16         # it waits 10 s for the hand to let go, then gives up


def test_note_for_a_band_session():
    s = SessionSummary("s1", "p", "2026-11-15T20:00:00", "2026-11-15T20:02:00", "push_4", 1, True)
    r = RepResult("s1", 0, "resist", -0.933, 1.0, 5.0, 0.28, 0.004, 0.009, 0.0, 33.0, 24.0, 1.0, True, True)
    note = session_note(s, [r])
    assert "Exercise: push forward against a constant resistance of 28 N (level 4 of 4)" in note
    assert "resistance level 4 (28 N constant band), mean force 24.0 N" in note


# ---------------------------------------------------------------- what each server mode offers

def _ns(**kw):
    return argparse.Namespace(**({"mock": False, "sim": False, "robot": None, "exercises": None} | kw))


def test_robot_offers_only_the_four_push_levels_unless_exercises_is_given(monkeypatch):
    monkeypatch.setattr(exercises, "live_ids", lambda: ["reach", "push", "pull", "armtest"])
    assert exercise_sets(_ns(robot="")) == (BAND, None)
    live, enabled = exercise_sets(_ns(robot="", exercises="reach,push_2"))
    assert enabled == ["reach", "push_2"] and set(live) == set(BAND) | {"reach", "push", "pull", "armtest"}
    assert exercise_sets(_ns(sim=True)) == (None, None)                       # --sim: as before
    live, enabled = exercise_sets(_ns(sim=True, exercises="push_1"))
    assert enabled == ["push_1"] and "push_1" in live
    live, enabled = exercise_sets(_ns(mock=True))
    assert set(BAND) <= set(live) and "reach" in live and enabled is None
    with pytest.raises(ValueError):
        exercise_sets(_ns(robot="", exercises="circle"))
