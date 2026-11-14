import time
from functools import partial

import pytest
from fastapi.testclient import TestClient

from server import db
from server.api import create_app
from server.mock import MockArm, MockEngine
from server.simulate import make_history

FAST = partial(MockEngine, strength=0.8, time_scale=200)


def _app(tmp_path, **kw):
    path = tmp_path / "api.db"
    c = db.connect(path)
    make_history(c, days=2, reps_per_session=4)
    c.close()
    return create_app(MockArm, path, engine_factory=FAST, site_dir=tmp_path / "nosite", **kw)


@pytest.fixture
def client(tmp_path):
    with TestClient(_app(tmp_path, exports_dir=tmp_path / "exports")) as c:
        yield c


def _wait_reps(client, n, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get("/api/state").json()
        if (st.get("rep_count") or 0) >= n:
            return st
        time.sleep(0.02)
    raise AssertionError(f"fewer than {n} reps after {timeout}s")


START = {"patient_id": "sim-1", "display_name": "Sim", "dial": 1.0, "auto": True}


def test_health_and_empty_state(client):
    assert client.get("/api/health").json() == {"ok": True, "arm": None, "arm_mode": None, "session": False}
    assert client.get("/api/state").json() == {"session": None}


def test_history_routes(client):
    pats = client.get("/api/patients").json()
    assert pats[0]["id"] == "sim-anna" and pats[0]["simulated"] is True
    sess = client.get("/api/patients/sim-anna/sessions").json()
    assert len(sess) == 2 and "mean_contribution" in sess[0] and sess[0]["simulated"] is True
    reps = client.get(f"/api/sessions/{sess[0]['session_id']}/reps").json()
    assert len(reps) == 4 and set(reps[0]) >= {"rom_m", "sparc", "rescued", "simulated"}
    note = client.get(f"/api/sessions/{sess[1]['session_id']}/note")
    assert note.headers["content-type"].startswith("text/plain")
    assert "SIMULATED DATA" in note.text and "Change vs previous session" in note.text


def test_404s(client):
    assert client.get("/api/patients/nobody/sessions").status_code == 404
    assert client.get("/api/sessions/nope/reps").status_code == 404
    assert client.get("/api/sessions/nope/note").status_code == 404


def test_start_stop_writes_session(client, tmp_path):
    r = client.post("/api/session/start", json=START | {"simulated": False})   # caller cannot claim real
    assert r.status_code == 200
    body = r.json()
    assert body["simulated"] is True and body["display_name"] == "Sim (SIMULATED)"
    assert client.post("/api/session/start", json=START).status_code == 409
    st = _wait_reps(client, 3)
    assert st["session"]["session_id"] == body["session_id"] and st["simulated"] is True
    assert client.get("/api/health").json()["arm"] == "sim"
    s = client.post("/api/session/stop").json()
    assert s["ended_at"] and s["n_reps"] >= 3 and s["simulated"] is True
    reps = client.get(f"/api/sessions/{body['session_id']}/reps").json()
    assert len(reps) == s["n_reps"] and all(r["simulated"] for r in reps)
    assert (tmp_path / "exports" / "reps.csv").exists()
    assert client.post("/api/session/stop").status_code == 409


def test_dial_manual_and_auto(client):
    client.post("/api/session/start", json=START)
    r = client.post("/api/dial", json={"dial": -0.5, "auto": False})
    assert r.json() == {"dial": -0.5, "auto": False}
    time.sleep(0.05)
    assert client.get("/api/state").json()["dial"] == -0.5
    assert client.post("/api/dial", json={"dial": 2.0}).status_code == 422
    client.post("/api/session/stop")
    assert client.post("/api/dial", json={"dial": 0}).status_code == 409


def test_auto_dial_falls_for_strong_patient(client):
    client.post("/api/session/start", json=START)
    st = _wait_reps(client, 6)
    client.post("/api/session/stop")
    assert st["dial"] < 0.5


def test_hold_always_allowed_and_go_501(tmp_path):
    with TestClient(_app(tmp_path, control_token="secret")) as c:
        assert c.post("/api/hold").status_code == 200
        assert c.post("/api/session/start", json=START).status_code == 403
        h = {"x-operator-token": "secret"}
        assert c.post("/api/session/start", json=START, headers=h).status_code == 200
        assert c.post("/api/dial", json={"dial": 0}).status_code == 403
        assert c.post("/api/go", headers=h).status_code == 501
        assert c.post("/api/hold").status_code == 200
        assert c.app.state.hub.arm.mode == "hold"
        assert c.post("/api/session/stop", headers=h).status_code == 200


def test_bad_patient_id_rejected(client):
    assert client.post("/api/session/start", json=START | {"patient_id": "../x"}).status_code == 422


def test_websocket_gets_samples_and_reps(client):
    client.post("/api/session/start", json=START)
    seen = set()
    with client.websocket_connect("/ws/live") as ws:
        for _ in range(400):
            m = ws.receive_json()
            seen.add(m["type"])
            if m["type"] == "sample":
                assert {"pos", "dial", "phase", "q", "rep_count", "auto", "arm_mode", "simulated"} <= set(m)
                assert m["simulated"] is True
            if seen == {"sample", "rep"}:
                break
    client.post("/api/session/stop")
    assert seen == {"sample", "rep"}


def test_shutdown_holds_and_closes_arm(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        c.post("/api/session/start", json=START)
        _wait_reps(c, 1)
        arm = app.state.hub.arm
    assert arm.mode == "idle"   # close() ran after hold()
    conn = db.connect(tmp_path / "api.db")
    running = [s for s in db.list_sessions(conn, "sim-1") if s.ended_at is None]
    conn.close()
    assert running == []        # session was stopped and saved on shutdown


def test_is_real_arm_only_for_robot_arm():
    from server.api import is_real_arm
    assert is_real_arm(MockArm()) is False
    assert is_real_arm(object()) is False
    arm_mod = pytest.importorskip("robot.arm")
    real = arm_mod.Arm("Rizon4-TEST00")      # constructing does not connect
    assert is_real_arm(real) is True


def test_real_arm_session_marked_real(tmp_path):
    app = create_app(MockArm, tmp_path / "r.db", engine_factory=FAST, site_dir=tmp_path / "x",
                     is_real=lambda arm: True)
    with TestClient(app) as c:
        r = c.post("/api/session/start", json={"patient_id": "p-real", "display_name": "Volunteer A",
                                               "dial": 0.5, "auto": False}).json()
        assert r["simulated"] is False and r["display_name"] == "Volunteer A"
        assert c.get("/api/health").json()["arm"] == "flexiv"
        c.post("/api/session/stop")
        # a simulated session can never be added to a real patient
        app.state.hub.is_real = lambda arm: False
        assert c.post("/api/session/start", json={"patient_id": "p-real", "dial": 0.5}).status_code == 409


def test_serves_site_folder_without_hiding_api(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>physio view</h1>")
    app = create_app(MockArm, tmp_path / "s.db", engine_factory=FAST, site_dir=site)
    with TestClient(app) as c:
        assert "physio view" in c.get("/").text
        assert c.get("/api/health").json()["ok"] is True
        with c.websocket_connect("/ws/live"):
            pass
