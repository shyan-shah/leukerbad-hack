"""E2: the exercise field through the API, storage, exports, note and mock engine."""
import csv
import json
import sqlite3
import sys
import time
import types
from functools import partial

import pytest
from fastapi.testclient import TestClient

from server import db, exercises
from server.api import create_app, default_engine_factory
from server.contract import RepResult, SessionSummary
from server.mock import MockArm, MockEngine
from server.note import FORCE_CAP_NOTE, session_note

ALL = ["reach", "push", "pull", "armtest"]
FAST = partial(MockEngine, strength=0.8, time_scale=300)


@pytest.fixture
def all_live(monkeypatch):
    """The four decided programmes are live, whatever software/exercises.py says today."""
    monkeypatch.setattr(exercises, "live_ids", lambda: list(ALL))


class FakeEngine:
    """Records what the server passes; emits nothing."""
    calls: list = []

    def __init__(self, **kw):
        FakeEngine.calls.append(kw)
        self.arm = kw["arm"]

    def start(self): ...
    def stop(self): ...
    def set_dial(self, dial, auto=None): ...
    def snapshot(self): return {"rep_count": 0, "auto": False, "arm_mode": "compliant"}


def _client(tmp_path, engine=FAST, **kw):
    return TestClient(create_app(MockArm, tmp_path / "x.db", engine_factory=engine, site_dir=tmp_path / "nosite", **kw))


def _wait_reps(c, n, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = c.get("/api/state").json()
        if (st.get("rep_count") or 0) >= n:
            return st
        time.sleep(0.02)
    raise AssertionError(f"fewer than {n} reps after {timeout}s")


# ---------------------------------------------------------------- start

@pytest.mark.parametrize("ex", ALL)
def test_start_each_live_id_passes_exercise_and_reps_to_engine(tmp_path, all_live, ex):
    FakeEngine.calls.clear()
    with _client(tmp_path, FakeEngine) as c:
        r = c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": ex, "reps": 4})
        assert r.status_code == 200, r.text
        assert r.json()["exercise"] == ex and r.json()["reps"] == 4
        kw = FakeEngine.calls[-1]
        assert kw["exercise"] == ex and kw["reps"] == 4
        assert "dial" not in kw and "auto" not in kw          # not sent: the exercise preset decides
        st = c.get("/api/state").json()
        assert st["exercise"] == ex and st["reps_target"] == 4 and st["session"]["exercise"] == ex
        assert st["done"] is False
        s = c.post("/api/session/stop").json()
        assert s["exercise"] == ex
        assert c.get("/api/patients/sim-x/sessions").json()[-1]["exercise"] == ex


def test_start_defaults_to_reach_with_registry_reps_and_passes_dial_when_sent(tmp_path, all_live):
    FakeEngine.calls.clear()
    with _client(tmp_path, FakeEngine) as c:
        assert c.post("/api/session/start", json={"patient_id": "sim-x", "dial": 0.4, "auto": False}).json()["reps"] == 10
        kw = FakeEngine.calls[-1]
        assert kw["exercise"] == "reach" and kw["reps"] == 10 and kw["dial"] == 0.4 and kw["auto"] is False
        c.post("/api/session/stop")
        assert c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": "armtest"}).json()["reps"] == 3
        c.post("/api/session/stop")
        r = c.post("/api/session/start", json={"patient_id": "sim-x", "reps": 0})      # 0 = no limit
        assert r.json()["reps"] is None and FakeEngine.calls[-1]["reps"] is None
        assert c.get("/api/state").json()["reps_target"] == 10       # shown as the default; the engine keeps going


@pytest.mark.parametrize("ex", ["knee", "circle", "REACH", ""])
def test_unknown_or_not_live_exercise_is_422_with_the_live_list(tmp_path, all_live, ex):
    with _client(tmp_path, FakeEngine) as c:
        r = c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": ex})
        assert r.status_code == 422
        d = r.json()["detail"]
        assert d["live"] == ALL and "reach, push, pull, armtest" in d["message"]
        assert c.get("/api/state").json() == {"session": None}
        assert c.get("/api/patients").json() == []           # nothing was written


def test_only_reach_is_live_without_engine_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(exercises, "_module", lambda: None)
    assert exercises.live_ids() == ["reach"]
    with _client(tmp_path, FakeEngine) as c:
        assert [e["id"] for e in c.get("/api/exercises").json()] == ["reach"]
        r = c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": "push"})
        assert r.status_code == 422 and r.json()["detail"]["live"] == ["reach"]
        assert c.post("/api/session/start", json={"patient_id": "sim-x"}).status_code == 200


def test_bad_reps_rejected(tmp_path, all_live):
    with _client(tmp_path, FakeEngine) as c:
        for reps in (-1, 101, "many"):
            assert c.post("/api/session/start", json={"patient_id": "sim-x", "reps": reps}).status_code == 422


# ---------------------------------------------------------------- registry adapter and GET /api/exercises

def test_exercises_route_lists_live_programmes(tmp_path, all_live, monkeypatch):
    monkeypatch.setattr(exercises, "_module", lambda: None)      # the server's own table
    with _client(tmp_path, FakeEngine) as c:
        out = c.get("/api/exercises").json()
    assert [e["id"] for e in out] == ALL
    assert all(set(e) == {"id", "name", "kind", "reps"} for e in out)
    by = {e["id"]: e for e in out}
    assert by["armtest"]["reps"] == 3 and by["armtest"]["kind"] == "test"
    assert by["reach"]["kind"] == "assist" and by["push"]["kind"] == by["pull"]["kind"] == "resist"


@pytest.mark.parametrize("registry", [
    {"EXERCISES": {"reach": {"name": "Reach X", "kind": "assist", "reps": 8},
                   "push": types.SimpleNamespace(name="Push X", kind="resist", default_reps=6),
                   "circle": {"name": "Circle", "kind": "robot-led", "reps": 5}}},
    {"PRESETS": [{"id": "reach", "name": "Reach X", "kind": "assist", "reps": 8},
                 types.SimpleNamespace(id="push", name="Push X", kind="resist", default_reps=6)]},
])
def test_adapter_reads_engine_registry_as_dicts_or_objects(monkeypatch, registry):
    mod = types.ModuleType("software.exercises")
    mod.LIVE = {"push", "reach"}
    for k, v in registry.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, "software.exercises", mod)
    assert exercises.live_ids() == ["reach", "push"]            # circle is in the registry but not LIVE
    assert exercises.catalog() == [{"id": "reach", "name": "Reach X", "kind": "assist", "reps": 8},
                                   {"id": "push", "name": "Push X", "kind": "resist", "reps": 6}]


def test_adapter_falls_back_when_registry_missing_or_partial(monkeypatch):
    mod = types.ModuleType("software.exercises")
    mod.LIVE = ["armtest", "reach"]
    monkeypatch.setitem(sys.modules, "software.exercises", mod)
    assert exercises.catalog() == [{"id": "reach", "name": "Forward reach (assisted)", "kind": "assist", "reps": 10},
                                   {"id": "armtest", "name": "Push strength test", "kind": "test", "reps": 3}]


def test_default_factory_with_an_engine_that_has_no_exercise_argument(monkeypatch):
    """An engine from before E1: reach still starts (extra arguments dropped), anything else is refused."""
    seen = {}

    class OldEngine:
        def __init__(self, arm, session_id, patient_id, simulated, dial=1.0, auto=True, on_sample=None, on_rep=None):
            seen.update(dial=dial, auto=auto)

    mod = types.ModuleType("software.engine")
    mod.Engine = OldEngine
    monkeypatch.setitem(sys.modules, "software.engine", mod)
    base = dict(arm=None, session_id="s", patient_id="p", simulated=True)
    assert isinstance(default_engine_factory(**base, exercise="reach", reps=10), OldEngine)
    assert seen == {"dial": 1.0, "auto": True}
    with pytest.raises(RuntimeError, match="cannot run 'push'"):
        default_engine_factory(**base, exercise="push", reps=10)

    class NewEngine(OldEngine):
        def __init__(self, *a, exercise="reach", reps=None, **kw):
            super().__init__(*a, **kw)
            seen.update(exercise=exercise, reps=reps)

    mod.Engine = NewEngine
    default_engine_factory(**base, exercise="push", reps=7)
    assert seen["exercise"] == "push" and seen["reps"] == 7


def test_engine_that_cannot_run_the_exercise_gives_409_and_no_running_session(tmp_path, all_live):
    def factory(**kw):
        raise RuntimeError("the engine on this laptop cannot run 'push' yet (only reach)")
    with _client(tmp_path, factory) as c:
        r = c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": "push"})
        assert r.status_code == 409 and "cannot run 'push'" in r.json()["detail"]
        assert c.get("/api/state").json() == {"session": None}
        assert all(s["ended_at"] for s in c.get("/api/patients/sim-x/sessions").json())


# ---------------------------------------------------------------- mock engine per exercise, messages, storage, exports

@pytest.mark.parametrize("ex,n,mode", [("reach", 3, None), ("push", 3, "resist"), ("pull", 3, "resist"),
                                       ("armtest", 3, "isometric")])
def test_mock_runs_each_exercise_stored_and_exported(tmp_path, all_live, ex, n, mode):
    with _client(tmp_path, exports_dir=tmp_path / "exports") as c:
        sid = c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": ex, "reps": n}).json()["session_id"]
        phases, rep_msgs = set(), []
        with c.websocket_connect("/ws/live") as ws:
            for _ in range(4000):
                m = ws.receive_json()
                assert m["exercise"] == ex
                if m["type"] == "sample":
                    assert m["reps_target"] == n
                    phases.add(m["phase"])
                    if m["rep_count"] >= n and len(rep_msgs) >= 1:
                        break
                else:
                    rep_msgs.append(m)
        _wait_reps(c, n)
        time.sleep(0.1)
        assert c.get("/api/state").json()["rep_count"] == n          # the set stops at the target and idles
        assert c.get("/api/state").json()["done"] is True
        assert c.get("/api/state").json()["phase"] == "idle"
        summary = c.post("/api/session/stop").json()
        reps = c.get(f"/api/sessions/{sid}/reps").json()
        note = c.get(f"/api/sessions/{sid}/note").text
    assert summary["exercise"] == ex and summary["n_reps"] == n == len(reps)
    assert all(r["exercise"] == ex for r in reps)
    if mode:
        assert {r["mode"] for r in reps} == {mode}
    if ex == "armtest":
        assert all(r["rom_m"] <= 0.05 and r["peak_force_n"] <= 30.0 for r in reps)
        assert FORCE_CAP_NOTE in note and "Tries: 3" in note
    else:
        assert f"Summary: {n} reps" in note

    conn = db.connect(tmp_path / "x.db")
    assert db.get_session(conn, sid).exercise == ex
    assert {r.mode for r in db.list_reps(conn, sid)} == {r["mode"] for r in reps}
    conn.close()
    out = tmp_path / "exports"
    assert json.loads((out / "sessions.json").read_text())[-1]["exercise"] == ex
    latest = json.loads((out / "latest_session.json").read_text())
    assert latest["session"]["exercise"] == ex and all(r["exercise"] == ex for r in latest["reps"])
    with open(out / "reps.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == n and all(r["exercise"] == ex for r in rows)


def test_mock_pull_runs_the_line_in_reverse_after_setup():
    samples = []
    e = MockEngine(MockArm(), "s", "p", True, exercise="pull", reps=1, time_scale=500, on_sample=samples.append)
    e.start()
    t0 = time.time()
    while e.rep_count < 1 and time.time() - t0 < 20:
        time.sleep(0.01)
    e.stop()
    assert e.dial == -0.6 and e.auto is False
    setup = [s for s in samples if s.phase == "setup"]
    out = [s for s in samples if s.phase == "out"]
    assert setup[0].pos[0] == pytest.approx(0.45) and setup[-1].pos[0] == pytest.approx(0.73)   # to the far end
    assert out[0].pos[0] == pytest.approx(0.73, abs=0.01) and out[-1].pos[0] == pytest.approx(0.45, abs=0.01)
    assert all(s.rep_idx == -1 and s.dial == 0.0 for s in setup)      # free movement, as the real engine reports
    assert all(s.dial == -0.6 for s in out)


def test_mock_armtest_defaults_to_three_isometric_tries():
    reps, samples = [], []
    e = MockEngine(MockArm(), "s", "p", True, exercise="armtest", time_scale=500, on_rep=reps.append,
                   on_sample=samples.append)
    e.start()
    t0 = time.time()
    while e.rep_count < 3 and time.time() - t0 < 20:
        time.sleep(0.01)
    time.sleep(0.1)
    e.stop()
    assert [r.mode for r in reps] == ["isometric"] * 3 and e.snapshot()["phase"] == "idle"
    seq = [p for i, p in enumerate(s.phase for s in samples) if i == 0 or samples[i - 1].phase != p]
    assert seq == ["idle", "out", "back", "out", "back", "out", "idle"]     # same order as software/engine.py
    assert all(s.rep_idx == -1 for s in samples if s.phase == "back")


def test_previous_session_for_the_note_is_the_same_exercise(tmp_path, all_live):
    with _client(tmp_path) as c:
        ids = {}
        for ex in ("reach", "push", "reach"):
            sid = c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": ex, "reps": 2}).json()["session_id"]
            _wait_reps(c, 2)
            c.post("/api/session/stop")
            ids.setdefault(ex, []).append(sid)
            time.sleep(1.05)             # started_at has 1 s resolution
        assert "Change vs previous session" not in c.get(f"/api/sessions/{ids['push'][0]}/note").text
        assert "Change vs previous session" in c.get(f"/api/sessions/{ids['reach'][1]}/note").text


# ---------------------------------------------------------------- database migration

def test_old_database_is_migrated_to_programme_ids(tmp_path):
    path = tmp_path / "old.db"
    conn = db.connect(path)
    db.upsert_patient(conn, "sim-p", "P (SIMULATED)", True)
    conn.close()
    raw = sqlite3.connect(path)       # rows as written before E2
    raw.execute("INSERT INTO sessions(session_id, patient_id, started_at, ended_at, exercise, n_reps, simulated) "
                "VALUES ('old1', 'sim-p', '2026-11-14T10:00:00', '2026-11-14T10:05:00', 'reach_line', 0, 1)")
    raw.execute("INSERT INTO sessions(session_id, patient_id, started_at, ended_at, exercise, n_reps, simulated) "
                "VALUES ('old2', 'sim-p', '2026-11-14T11:00:00', NULL, NULL, 0, 1)")
    raw.commit()
    raw.close()
    conn = db.connect(path)           # reopening migrates
    assert [s.exercise for s in db.list_sessions(conn, "sim-p")] == ["reach", "reach"]
    db.save_session(conn, SessionSummary("new", "sim-p", "2026-11-15T10:00:00", None, "armtest", 0, True))
    conn.close()
    conn = db.connect(path)           # and leaves the new ids alone
    assert db.get_session(conn, "new").exercise == "armtest"
    conn.close()


def test_isometric_rep_round_trips_through_the_database(tmp_path):
    conn = db.connect(tmp_path / "i.db")
    db.upsert_patient(conn, "sim-p", "P", True)
    db.save_session(conn, SessionSummary("s", "sim-p", "2026-11-15T10:00:00", None, "armtest", 0, True))
    r = RepResult(session_id="s", idx=0, mode="isometric", dial=0.0, t_start=1.0, duration_s=3.0, rom_m=0.004,
                  path_err_mean_m=0.0, path_err_max_m=0.0, sparc=0.0, peak_force_n=24.5, mean_force_n=18.0,
                  contribution=1.0, completed=True, simulated=True)
    db.save_rep(conn, r)
    assert db.list_reps(conn, "s") == [r]
    conn.close()


# ---------------------------------------------------------------- note

def _rep(idx, **kw):
    base = dict(session_id="s", idx=idx, mode="resist", dial=-0.6, t_start=float(idx), duration_s=5.0, rom_m=0.27,
                path_err_mean_m=0.01, path_err_max_m=0.02, sparc=-2.0, peak_force_n=12.0 + idx, mean_force_n=8.0,
                contribution=0.9, completed=True, simulated=True)
    base.update(kw)
    return RepResult(**base)


def _summary(ex):
    return SessionSummary("s", "p", "2026-11-15T10:00:00", "2026-11-15T10:05:00", ex, 3, True)


def test_note_lines_per_exercise():
    reach = session_note(_summary("reach"), [_rep(0, mode="assist", dial=0.8), _rep(1, mode="assist", dial=0.7)])
    assert "Exercise: straight-line forward reach" in reach
    assert "Summary: 2 reps, range 27.0 cm (mean), peak force 13.0 N (best), own contribution 90% (mean)" in reach
    assert "Exercise: straight-line forward reach" in session_note(_summary("reach_line"), [_rep(0)])   # old rows
    for ex, words in (("push", "push forward against resistance"), ("pull", "pull towards the body")):
        note = session_note(_summary(ex), [_rep(0), _rep(1)])
        assert words in note
        assert "resistance level 60% of maximum (mean dial -0.60), mean force 8.0 N" in note
        assert "own contribution" not in note.split("Repetitions:")[0]


def test_armtest_note_reports_best_and_mean_peak_and_the_cap():
    tries = [_rep(i, mode="isometric", dial=0.0, duration_s=3.0, rom_m=0.004, peak_force_n=p)
             for i, p in enumerate((20.0, 26.0, 23.0))]
    note = session_note(_summary("armtest"), tries, previous=[_rep(0, peak_force_n=22.0)])
    assert "Peak force: best 26.0 N, mean 23.0 N over the tries" in note
    assert "Readings capped at about 30 N by the robot's safety limit." in note
    assert "Change vs previous strength test (best): +4.0 N (higher)" in note
    for absent in ("Range of motion", "Own contribution", "Dial:", "Reps by mode"):
        assert absent not in note
    for word in ("diagnos", "recovered", "prognosis", "recommend"):
        assert word not in note.lower()


# ---------------------------------------------------------------- sim engine end to end, once E1 lands

@pytest.mark.parametrize("ex", ALL)
def test_e2e_sim_per_exercise(tmp_path, ex):
    import inspect
    pytest.importorskip("software.exercises", reason="waiting for E1 (software/exercises.py)")
    engine = pytest.importorskip("software.engine")
    sim_arm = pytest.importorskip("software.sim_arm")
    sim_patient = pytest.importorskip("software.sim_patient")
    if ex not in exercises.live_ids():
        pytest.skip(f"{ex} is not in software.exercises.LIVE yet")
    if "exercise" not in inspect.signature(engine.Engine.__init__).parameters:
        pytest.skip("Engine has no exercise argument yet (E1)")
    n = exercises.info(ex)["reps"] if ex == "armtest" else 3
    app = create_app(lambda: sim_arm.SimArm(sim_patient.SimPatient(strength=0.8)), tmp_path / "e.db",
                     exports_dir=tmp_path / "exports", site_dir=tmp_path / "x")
    with TestClient(app) as c:
        r = c.post("/api/session/start", json={"patient_id": "sim-e2e", "exercise": ex, "reps": n})
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]
        st = _wait_reps(c, n, timeout=180)
        assert st["exercise"] == ex and st["reps_target"] == n
        time.sleep(0.3)
        assert c.get("/api/state").json()["done"] is True
        summary = c.post("/api/session/stop").json()
        reps = c.get(f"/api/sessions/{sid}/reps").json()
        note = c.get(f"/api/sessions/{sid}/note").text
    assert summary["exercise"] == ex and len(reps) >= n and all(r["exercise"] == ex for r in reps)
    if ex == "armtest":
        assert {r["mode"] for r in reps} == {"isometric"} and FORCE_CAP_NOTE in note


# ---------------------------------------------------------------- --mock offers everything the mock can play

def test_mock_server_offers_all_four_whatever_the_engine_registry_says(tmp_path, monkeypatch):
    import argparse
    from server import run as run_mod
    monkeypatch.setattr(exercises, "_module", lambda: None)             # engine registry: reach only
    assert run_mod.mock_exercises(argparse.Namespace(mock=False)) is None
    live = run_mod.mock_exercises(argparse.Namespace(mock=True))
    assert live == ALL
    with _client(tmp_path, live_exercises=live) as c:
        assert [e["id"] for e in c.get("/api/exercises").json()] == ALL
        assert c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": "armtest"}).status_code == 200
        _wait_reps(c, 3)
        assert c.post("/api/session/stop").json()["n_reps"] == 3
        assert c.post("/api/session/start", json={"patient_id": "sim-x", "exercise": "circle"}).status_code == 422
