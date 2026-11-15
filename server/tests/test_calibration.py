"""Comfortable-push calibration: pass-through, mock phase, storage, go/resume (contract of 15 Nov)."""
import json
import time
from functools import partial

import pytest
from fastapi.testclient import TestClient

from server import db, exercises
from server.api import create_app
from server.contract import SessionSummary
from server.mock import CAL_FRACTION, MockArm, MockEngine
from server.note import session_note

FAST = partial(MockEngine, strength=0.8, time_scale=200)
LIVE = ["reach", "push", "pull", "armtest"]
CAL_KEYS = {"status", "progress", "comfort_force_n", "resistance_n", "fraction", "reason"}


def _client(tmp_path, factory=FAST, **kw):
    return TestClient(create_app(MockArm, tmp_path / "c.db", engine_factory=factory,
                                 site_dir=tmp_path / "nosite", live_exercises=LIVE, **kw))


def _wait(client, pred, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get("/api/state").json()
        if pred(st):
            return st
        time.sleep(0.01)
    raise AssertionError(f"state never matched; last: {st}")


def _start(c, exercise="push", **extra):
    r = c.post("/api/session/start", json={"patient_id": "sim-cal", "exercise": exercise, "reps": 2} | extra)
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


# ---------------------------------------------------------------- step 1: pass-through
def test_exercises_carry_calibrates(tmp_path):
    with _client(tmp_path) as c:
        got = {e["id"]: e["calibrates"] for e in c.get("/api/exercises").json()}
    assert got == {"reach": False, "push": True, "pull": True, "armtest": False}
    assert exercises.info("circle")["calibrates"] is False


class OldEngine:
    """An engine from before the contract: no calibrate arguments, no snapshot fields, no go/resume."""

    def __init__(self, arm, session_id, patient_id, simulated, exercise="reach", reps=None,
                 on_sample=None, on_rep=None, reach_axis=0):
        self.inner = MockEngine(arm, session_id, patient_id, simulated, exercise="reach", reps=reps,
                                on_sample=on_sample, on_rep=on_rep, time_scale=200)

    def start(self): self.inner.start()
    def stop(self): return self.inner.stop()
    def set_dial(self, dial, auto=None): self.inner.set_dial(dial, auto)

    def snapshot(self):
        d = self.inner.snapshot()
        d.pop("calibration"), d.pop("arming")
        return d


def test_old_engine_still_works_and_sends_nulls(tmp_path):
    with _client(tmp_path, factory=OldEngine) as c:
        sid = _start(c, calibrate=True)
        st = _wait(c, lambda s: (s.get("rep_count") or 0) >= 1)
        assert st["calibration"] is None and st["arming"] is None
        with c.websocket_connect("/ws/live") as ws:
            m = next(m for m in iter(ws.receive_json, None) if m["type"] == "sample")
        assert m["calibration"] is None and m["arming"] is None
        assert c.post("/api/session/resume").status_code == 409
        assert c.post("/api/go").status_code == 501
        s = c.post("/api/session/stop").json()
        assert s["session_id"] == sid
        assert s["comfort_force_n"] is None and s["resistance_n"] is None and s["resistance_fraction"] is None


def test_start_passes_calibrate_and_stored_state(tmp_path):
    seen = []

    def factory(**kw):
        seen.append({k: kw.get(k, "absent") for k in ("calibrate", "calibration_state")})
        return FAST(**kw)

    with _client(tmp_path, factory=factory) as c:
        _start(c)
        _wait(c, lambda s: (s.get("calibration") or {}).get("status") == "done")
        c.post("/api/session/stop")
        _start(c, calibrate=False)
        c.post("/api/session/stop")
        _start(c, exercise="pull")          # state is per exercise: none stored for pull yet
        c.post("/api/session/stop")
    assert seen[0] == {"calibrate": None, "calibration_state": None}
    assert seen[1]["calibrate"] is False and seen[1]["calibration_state"]["fraction"] == CAL_FRACTION
    assert seen[2] == {"calibrate": None, "calibration_state": None}


# ---------------------------------------------------------------- step 2: mock
@pytest.mark.parametrize("ex", ["push", "pull"])
def test_mock_plays_calibrate_then_reps(ex):
    samples = []
    e = MockEngine(MockArm(), "s", "p", True, exercise=ex, reps=1, time_scale=400, on_sample=samples.append)
    assert e.snapshot()["calibration"]["status"] == "waiting"
    e.start()
    t0 = time.time()
    while e.rep_count < 1 and time.time() - t0 < 10:
        time.sleep(0.01)
    snap = e.snapshot()
    e.stop()
    cal = [s for s in samples if s.phase == "calibrate"]
    assert samples[0].phase == "calibrate" and 395 <= len(cal) <= 400          # 4 s at 100 Hz
    assert all(s.rep_idx == -1 for s in cal)
    assert max(abs(s.pos[0] - 0.45) for s in cal) < 1e-9                       # handle held still at the start
    f = [abs(s.force[0]) for s in cal]
    assert max(f[:100]) == 0.0 and f[120] < f[160] < f[190]                    # waiting, then rising
    assert max(f[250:]) - min(f[250:]) < 1.0                                   # then steady
    c = snap["calibration"]
    assert set(c) == CAL_KEYS and c["status"] == "done" and c["progress"] == 1.0 and c["reason"] is None
    assert c["fraction"] == CAL_FRACTION and c["resistance_n"] == pytest.approx(c["fraction"] * c["comfort_force_n"], abs=0.06)
    assert abs(c["comfort_force_n"] - 22.0) < 1.0                              # 10 + 20 * strength (default 0.6)
    assert set(snap["arming"]) == {"progress", "reason"}
    json.dumps(e.calibration_state_after)
    assert e.calibration_state_after["fraction"] == CAL_FRACTION


def test_mock_skip_other_exercises_and_state():
    e = MockEngine(MockArm(), "s", "p", True, exercise="push", calibrate=False)
    assert e.snapshot()["calibration"]["status"] == "skipped" and e.calibration_state_after is None
    assert MockEngine(MockArm(), "s", "p", True, exercise="reach", calibrate=True).snapshot()["calibration"] is None
    assert MockEngine(MockArm(), "s", "p", True, exercise="armtest").snapshot()["calibration"] is None
    prev = {"version": 1, "fraction": 0.6, "sessions": 1}
    e = MockEngine(MockArm(), "s", "p", True, exercise="push", reps=0, time_scale=400, calibration_state=prev)
    e.start()
    t0 = time.time()
    while e.snapshot()["calibration"]["status"] != "done" and time.time() - t0 < 10:
        time.sleep(0.01)
    e.stop()
    assert e.calibration_state_after["fraction"] == 0.65 and e.calibration_state_after["sessions"] == 2


# ---------------------------------------------------------------- step 3: storage
def test_state_and_samples_carry_calibration_then_session_row(tmp_path):
    with _client(tmp_path, exports_dir=tmp_path / "exports") as c:
        with c.websocket_connect("/ws/live") as ws:
            sid = _start(c)
            m = next(m for m in iter(ws.receive_json, None) if m["type"] == "sample")
            assert set(m["calibration"]) == CAL_KEYS and set(m["arming"]) == {"progress", "reason"}
        st = _wait(c, lambda s: (s.get("rep_count") or 0) >= 1)
        cal = st["calibration"]
        assert cal["status"] == "done" and cal["resistance_n"] > 0
        s = c.post("/api/session/stop").json()
        assert s["comfort_force_n"] == cal["comfort_force_n"] and s["resistance_n"] == cal["resistance_n"]
        assert s["resistance_fraction"] == cal["fraction"]
        row = next(x for x in c.get("/api/patients/sim-cal/sessions").json() if x["session_id"] == sid)
        assert row["resistance_n"] == cal["resistance_n"]
        note = c.get(f"/api/sessions/{sid}/note").text
        assert (f"Resistance set to {cal['resistance_n']:.1f} N from a comfortable push of "
                f"{cal['comfort_force_n']:.1f} N (team heuristic, adjusts to the patient)") in note
        exported = json.loads((tmp_path / "exports" / "sessions.json").read_text(encoding="utf-8"))
        assert exported[-1]["comfort_force_n"] == cal["comfort_force_n"]
        latest = json.loads((tmp_path / "exports" / "latest_session.json").read_text(encoding="utf-8"))
        assert latest["session"]["resistance_fraction"] == cal["fraction"] and "Resistance set to" in latest["note"]
        # a reach session has no calibration: nulls, no note line
        rid = _start(c, exercise="reach")
        _wait(c, lambda s: (s.get("rep_count") or 0) >= 1)
        s = c.post("/api/session/stop").json()
        assert s["resistance_n"] is None and "Resistance set" not in c.get(f"/api/sessions/{rid}/note").text
    conn = db.connect(tmp_path / "c.db")
    assert db.get_calibration_state(conn, "sim-cal", "push")["sessions"] == 1
    assert db.get_calibration_state(conn, "sim-cal", "pull") is None
    conn.close()


def test_stopped_during_calibrate_saves_nulls(tmp_path):
    slow = partial(MockEngine, time_scale=1)
    with _client(tmp_path, factory=slow) as c:
        _start(c)
        assert _wait(c, lambda s: s.get("phase") == "calibrate")["calibration"]["status"] in ("waiting", "pushing")
        s = c.post("/api/session/stop").json()
        assert s["comfort_force_n"] is None and s["resistance_n"] is None


def test_forward_migration_adds_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE patients(id TEXT PRIMARY KEY, display_name TEXT, simulated INTEGER NOT NULL)")
    raw.execute("CREATE TABLE sessions(session_id TEXT PRIMARY KEY, patient_id TEXT, started_at TEXT, "
                "ended_at TEXT, exercise TEXT, n_reps INTEGER, simulated INTEGER)")
    raw.execute("INSERT INTO patients VALUES ('p', 'P (SIMULATED)', 1)")
    raw.execute("INSERT INTO sessions VALUES ('old', 'p', '2026-11-14T10:00:00', NULL, 'push', 3, 1)")
    raw.commit(), raw.close()
    conn = db.connect(path)
    old = db.get_session(conn, "old")
    assert old.comfort_force_n is None and old.resistance_n is None and old.resistance_fraction is None
    new = SessionSummary("new", "p", "2026-11-15T10:00:00", None, "push", 0, True, 20.0, 12.0, 0.6)
    db.save_session(conn, new)
    assert db.get_session(conn, "new") == new
    assert "Resistance set to 12.0 N from a comfortable push of 20.0 N" not in session_note(new, [])
    db.save_calibration_state(conn, "p", "push", {"fraction": 0.6})
    db.save_calibration_state(conn, "p", "push", {"fraction": 0.65})
    assert db.get_calibration_state(conn, "p", "push") == {"fraction": 0.65}
    conn.close()


# ---------------------------------------------------------------- step 4: go and resume
def test_go_and_resume(tmp_path):
    with _client(tmp_path, control_token="secret") as c:
        h = {"x-operator-token": "secret"}
        assert c.post("/api/session/resume").status_code == 403
        r = c.post("/api/session/resume", headers=h)
        assert r.status_code == 409 and "no session" in r.json()["detail"]
        c.post("/api/session/start", json={"patient_id": "sim-cal", "exercise": "push"}, headers=h)
        assert c.post("/api/go", headers=h).json() == {"ok": True}
        c.post("/api/hold")
        assert c.get("/api/state").json()["arm_mode"] == "hold"
        assert c.post("/api/session/resume", headers=h).json() == {"ok": True}
        assert c.get("/api/state").json()["arm_mode"] == "compliant"
        c.post("/api/session/stop", headers=h)


# ---------------------------------------------------------------- --no-calibrate (default on the real arm)
def test_no_calibrate_forces_false_whatever_the_caller_sends(tmp_path):
    seen = []

    def factory(**kw):
        seen.append(kw.get("calibrate", "absent"))
        return FAST(**kw)

    with _client(tmp_path, factory=factory, no_calibrate=True) as c:
        assert not any(e["calibrates"] for e in c.get("/api/exercises").json())
        for extra in ({}, {"calibrate": True}, {"calibrate": False}):
            r = c.post("/api/session/start", json={"patient_id": "sim-cal", "exercise": "push", "reps": 1} | extra)
            assert r.status_code == 200 and r.json()["calibrate"] is False
            st = _wait(c, lambda s: (s.get("rep_count") or 0) >= 1)
            assert st["calibration"]["status"] == "skipped"
            s = c.post("/api/session/stop").json()
            assert s["resistance_n"] is None and s["comfort_force_n"] is None
    assert seen == [False, False, False]


def test_real_engine_never_raises_limits_with_no_calibrate():
    """software.engine.Engine with calibrate=False on a push: set_test_limits(True) is never called."""
    pytest.importorskip("software.engine")
    from software.engine import Engine
    from software.sim_arm import SimArm
    from software.sim_patient import SimPatient

    calls = []

    class Arm(SimArm):
        def set_test_limits(self, on):
            calls.append(bool(on))

    phases = set()
    arm = Arm(SimPatient(strength=0.8))
    arm.connect()
    e = Engine(arm=arm, session_id="s", patient_id="p", simulated=True,
               exercise="push", reps=1, calibrate=False, on_sample=lambda s: phases.add(s.phase))
    e.start()
    time.sleep(1.5)
    snap = e.snapshot()
    e.stop()
    assert True not in calls and "calibrate" not in phases
    assert snap["calibration"]["status"] == "skipped"


def test_force_cap_30_normally_and_60_while_the_test_profile_is_on(tmp_path):
    slow = partial(MockEngine, time_scale=4)
    with _client(tmp_path, factory=slow) as c:
        with c.websocket_connect("/ws/live") as ws:
            _start(c)
            caps = set()
            for m in iter(ws.receive_json, None):
                if m["type"] != "sample":
                    continue
                caps.add((m["phase"], m["force_cap_n"]))
                if m["phase"] != "calibrate":
                    break
        assert caps == {("calibrate", 60.0), ("idle", 30.0)}        # the mock raises it for the push only
        assert c.get("/api/state").json()["force_cap_n"] == 30.0
        c.app.state.hub.arm.test_limits_on = True                    # whatever switches the arm's profile on
        assert c.get("/api/state").json()["force_cap_n"] == 60.0
        c.post("/api/session/stop")
        _start(c, exercise="reach")
        assert _wait(c, lambda s: "phase" in s)["force_cap_n"] == 30.0   # stop held the arm: normal limits again
        c.post("/api/session/stop")


def test_shutdown_route_closes_the_arm_itself(tmp_path):
    """The arm is held and closed by the route, not only by the lifespan: uvicorn may never get that far."""
    with _client(tmp_path) as c:
        c.app.state.request_exit = lambda: None          # a server that never manages to exit
        _start(c)
        assert c.app.state.hub.closed is False
        assert c.post("/api/shutdown").status_code == 200
        hub = c.app.state.hub
        assert hub.closed is True and hub.arm.mode == "idle" and hub.session is None


def test_run_flag_defaults():
    import argparse
    from server.run import no_calibrate_for

    def ns(**kw):
        return argparse.Namespace(**({"robot": None, "calibrate": None} | kw))
    assert no_calibrate_for(ns(robot="")) is True                   # --robot: off by default
    assert no_calibrate_for(ns(robot="Rizon4-1")) is True
    assert no_calibrate_for(ns(robot="", calibrate=True)) is False  # only with an explicit --calibrate
    assert no_calibrate_for(ns()) is False                          # --mock / --sim: on
    assert no_calibrate_for(ns(calibrate=False)) is True            # --no-calibrate
