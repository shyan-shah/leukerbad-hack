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
    assert client.get("/api/health").json() == {"ok": True, "arm": None, "arm_mode": None, "session": False,
                                                "arm_prepared": False}
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
    app = create_app(FakeRealArm, tmp_path / "r.db", engine_factory=FAST, site_dir=tmp_path / "x",
                     is_real=lambda arm: True)
    with TestClient(app) as c:
        assert c.post("/api/arm/prepare").status_code == 200
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


# ---------------------------------------------------------------- refused start (409) and arm prepare (Y6)

class FakeRealArm(MockArm):
    """Stands in for robot.arm.Arm in tests (used with is_real=lambda arm: True)."""
    instances: list = []

    def __init__(self) -> None:
        super().__init__()
        self.fault = None
        self.force = (0.4, -0.3, 1.2)
        self.zero_calls = 0
        self.zero_error = None
        FakeRealArm.instances.append(self)

    def zero_force(self) -> None:
        self.zero_calls += 1
        if self.zero_error:
            raise RuntimeError(self.zero_error)
        self.force = (0.0, 0.0, 0.1)

    def get_state(self):
        from types import SimpleNamespace
        return SimpleNamespace(mode="fault" if self.fault else self.mode, fault=self.fault, force=self.force)


class RefusingEngine(MockEngine):
    refuse = True

    def start(self) -> None:
        if RefusingEngine.refuse:
            raise RuntimeError("empty-handle force baseline is 6.2 N (fx +0.1, fy +0.0, fz +6.2 N; limit 3.0 N)")
        super().start()


def _real_app(tmp_path, arm_factory=FakeRealArm, **kw):
    return create_app(arm_factory, tmp_path / "real.db", engine_factory=FAST, site_dir=tmp_path / "x",
                      is_real=lambda arm: True, **kw)


def test_start_refused_by_engine_is_409_not_500(tmp_path):
    RefusingEngine.refuse = True
    app = create_app(MockArm, tmp_path / "ref.db", engine_factory=partial(RefusingEngine, time_scale=200),
                     site_dir=tmp_path / "x")
    with TestClient(app) as c:
        r = c.post("/api/session/start", json=START)
        assert r.status_code == 409
        assert "baseline is 6.2 N" in r.json()["detail"]
        assert c.get("/api/state").json() == {"session": None}
        assert c.get("/api/health").json()["session"] is False
        assert app.state.hub.arm.mode == "hold"                       # arm was put in hold
        # no session is left "running" in the history
        assert all(s["ended_at"] for s in c.get("/api/patients/sim-1/sessions").json())
        # and the next start works once the engine accepts
        RefusingEngine.refuse = False
        assert c.post("/api/session/start", json=START).status_code == 200
        assert c.post("/api/session/stop").status_code == 200


def test_start_other_engine_errors_still_raise(tmp_path):
    class Broken(MockEngine):
        def start(self) -> None:
            raise ValueError("bug")
    app = create_app(MockArm, tmp_path / "b.db", engine_factory=Broken, site_dir=tmp_path / "x")
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.post("/api/session/start", json=START).status_code == 500
        assert c.get("/api/state").json() == {"session": None}


def test_prepare_skipped_on_simulated_arm(client):
    r = client.post("/api/arm/prepare")
    assert r.status_code == 200 and r.json()["simulated"] is True and r.json()["skipped"] is True
    assert client.post("/api/session/start", json=START).status_code == 200    # no prepare needed
    client.post("/api/session/stop")


def test_real_arm_needs_prepare_before_start(tmp_path):
    FakeRealArm.instances.clear()
    with TestClient(_real_app(tmp_path)) as c:
        body = {"patient_id": "p-real", "display_name": "Volunteer A", "dial": 0.5}
        r = c.post("/api/session/start", json=body)
        assert r.status_code == 409 and "prepare the arm first" in r.json()["detail"]
        assert c.get("/api/health").json()["arm_prepared"] is False

        p = c.post("/api/arm/prepare")
        assert p.status_code == 200
        out = p.json()
        assert out["ok"] is True and out["simulated"] is False and out["zeroed"] is True
        assert out["zero_error"] is None
        assert out["baseline_force"] == [0.0, 0.0, 0.1] and out["baseline_n"] == pytest.approx(0.1)
        assert FakeRealArm.instances[-1].zero_calls == 1
        assert c.get("/api/health").json()["arm_prepared"] is True

        assert c.post("/api/session/start", json=body).status_code == 200
        # refused while a session runs
        r = c.post("/api/arm/prepare")
        assert r.status_code == 409 and "session is running" in r.json()["detail"]
        assert c.post("/api/session/stop").status_code == 200
        assert c.post("/api/arm/prepare").status_code == 200           # allowed again between sessions


def test_prepare_zero_force_failure_is_not_fatal(tmp_path):
    def factory():
        arm = FakeRealArm()
        arm.zero_error = "ZeroFTSensor did not terminate within 15 s"
        return arm
    with TestClient(_real_app(tmp_path, factory)) as c:
        out = c.post("/api/arm/prepare").json()
        assert out["ok"] is True and out["zeroed"] is False
        assert "ZeroFTSensor" in out["zero_error"]
        assert out["baseline_force"] == [0.4, -0.3, 1.2]              # un-zeroed reading is reported as is
        assert out["baseline_n"] == pytest.approx(1.3, abs=0.01)
        assert c.post("/api/session/start", json={"patient_id": "p-real", "dial": 0.5}).status_code == 200
        c.post("/api/session/stop")


def test_prepare_refuses_faulted_or_unconnected_arm(tmp_path):
    def faulted():
        arm = FakeRealArm()
        arm.fault = "robot reported a fault"
        return arm
    with TestClient(_real_app(tmp_path, faulted)) as c:
        r = c.post("/api/arm/prepare")
        assert r.status_code == 409 and "fault" in r.json()["detail"]
        assert c.get("/api/health").json()["arm_prepared"] is False
        assert c.post("/api/session/start", json={"patient_id": "p-real"}).status_code == 409

    class NoArm(FakeRealArm):
        def connect(self) -> None:
            raise RuntimeError("Failed to connect to [Rizon4-TEST00]")
    with TestClient(create_app(NoArm, tmp_path / "n.db", engine_factory=FAST, site_dir=tmp_path / "y",
                               is_real=lambda arm: True)) as c:
        r = c.post("/api/arm/prepare")
        assert r.status_code == 503 and "Failed to connect" in r.json()["detail"]


def test_prepare_needs_operator_token_in_lan_mode(tmp_path):
    with TestClient(_real_app(tmp_path, control_token="secret")) as c:
        assert c.post("/api/arm/prepare").status_code == 403
        assert c.post("/api/arm/prepare", headers={"x-operator-token": "secret"}).status_code == 200


# ---------------------------------------------------------------- start pose: prepare refuses away from it, /api/arm/home

class _Cfg:
    start_tcp_pose = (0.2126, 0.4703, 0.3749, 0.0, -0.64, 0.77, 0.0)

    def __init__(self, placeholder=False):
        self.placeholder = placeholder

    def is_placeholder(self, key):
        return self.placeholder and key == "start_pose"


class PosedArm(FakeRealArm):
    """A fake real arm with a measured start pose in its config and a hand position."""
    offset = 0.0            # m along x from the start pose when created
    home_error = None

    def __init__(self) -> None:
        super().__init__()
        self.config = _Cfg()
        self.pos = (0.2126 + type(self).offset, 0.4703, 0.3749)
        self.home_calls = 0

    def get_state(self):
        st = super().get_state()
        st.pos = self.pos
        return st

    def home(self) -> None:
        self.home_calls += 1
        if self.home_error:
            raise RuntimeError(self.home_error)
        self.pos = self.config.start_tcp_pose[:3]


def _posed(offset=0.0, **attrs):
    return type("PosedArmX", (PosedArm,), {"offset": offset, **attrs})


def test_prepare_at_the_start_pose_reports_distance(tmp_path):
    with TestClient(_real_app(tmp_path, _posed(0.012))) as c:
        out = c.post("/api/arm/prepare").json()
        assert out["ok"] is True and out["zeroed"] is True
        assert out["from_start_m"] == pytest.approx(0.012, abs=1e-4)


def test_prepare_refuses_more_than_2cm_from_the_start_pose_and_does_not_zero(tmp_path):
    FakeRealArm.instances.clear()
    with TestClient(_real_app(tmp_path, _posed(0.28))) as c:
        r = c.post("/api/arm/prepare")
        assert r.status_code == 409
        assert "28.0 cm from the start pose" in r.json()["detail"] and "/api/arm/home" in r.json()["detail"]
        arm = FakeRealArm.instances[-1]
        assert arm.zero_calls == 0
        assert c.get("/api/health").json()["arm_prepared"] is False
        assert c.post("/api/session/start", json={"patient_id": "p-real"}).status_code == 409

        h = c.post("/api/arm/home")
        assert h.status_code == 200
        assert h.json() == {"ok": True, "simulated": False, "moved_m": pytest.approx(0.28, abs=1e-4),
                            "from_start_m": pytest.approx(0.0, abs=1e-6)}
        assert arm.home_calls == 1
        assert c.get("/api/health").json()["arm_prepared"] is False      # home never counts as prepare
        assert c.post("/api/arm/prepare").status_code == 200 and arm.zero_calls == 1
        assert c.post("/api/session/start", json={"patient_id": "p-real"}).status_code == 200
        r = c.post("/api/arm/home")                                       # refused during a session
        assert r.status_code == 409 and "session is running" in r.json()["detail"]
        assert arm.home_calls == 1
        c.post("/api/session/stop")


def test_home_resets_prepared_so_zero_is_needed_again(tmp_path):
    with TestClient(_real_app(tmp_path, _posed(0.0))) as c:
        assert c.post("/api/arm/prepare").status_code == 200
        assert c.get("/api/health").json()["arm_prepared"] is True
        assert c.post("/api/arm/home").status_code == 200
        assert c.get("/api/health").json()["arm_prepared"] is False
        r = c.post("/api/session/start", json={"patient_id": "p-real"})
        assert r.status_code == 409 and "prepare the arm first" in r.json()["detail"]


def test_placeholder_start_pose_skips_the_distance_check(tmp_path):
    class Placeholder(PosedArm):
        offset = 0.30

        def __init__(self) -> None:
            super().__init__()
            self.config = _Cfg(placeholder=True)
    with TestClient(_real_app(tmp_path, Placeholder)) as c:
        out = c.post("/api/arm/prepare").json()
        assert out["ok"] is True and out["from_start_m"] is None


def test_home_errors_token_and_simulated(tmp_path, client):
    r = client.post("/api/arm/home")                                      # mock arm: nothing to do
    assert r.status_code == 200 and r.json()["skipped"] is True and r.json()["simulated"] is True

    far = _posed(0.7, home_error="start pose is 0.70 m away; jog closer before home()")
    with TestClient(_real_app(tmp_path, far)) as c:
        r = c.post("/api/arm/home")
        assert r.status_code == 409 and "0.70 m away" in r.json()["detail"]

    def faulted():
        arm = PosedArm()
        arm.fault = "robot reported a fault"
        return arm
    (tmp_path / "f").mkdir()
    with TestClient(_real_app(tmp_path / "f", faulted)) as c:
        r = c.post("/api/arm/home")
        assert r.status_code == 409 and "fault" in r.json()["detail"]

    class NoArm(PosedArm):
        def connect(self) -> None:
            raise RuntimeError("arm not ready: the robot is not operational")
    (tmp_path / "n").mkdir()
    with TestClient(_real_app(tmp_path / "n", NoArm)) as c:
        r = c.post("/api/arm/home")
        assert r.status_code == 503 and "not operational" in r.json()["detail"]

    (tmp_path / "t").mkdir()
    with TestClient(_real_app(tmp_path / "t", _posed(0.1), control_token="secret")) as c:
        assert c.post("/api/arm/home").status_code == 403
        assert c.post("/api/arm/home", headers={"x-operator-token": "secret"}).status_code == 200


def test_hold_is_answered_while_home_is_moving(tmp_path):
    import threading
    started, release = threading.Event(), threading.Event()

    class SlowHome(PosedArm):
        offset = 0.2

        def home(self) -> None:
            started.set()
            assert release.wait(5)
            super().home()
    with TestClient(_real_app(tmp_path, SlowHome)) as c:
        out = {}
        th = threading.Thread(target=lambda: out.update(r=c.post("/api/arm/home")))
        th.start()
        assert started.wait(5)
        assert c.post("/api/hold").status_code == 200                     # not blocked by the home in progress
        assert c.get("/api/health").status_code == 200
        release.set()
        th.join(5)
        assert out["r"].status_code == 200


# ---------------------------------------------------------------- enabling exercises one by one

ALL4 = ["reach", "push", "pull", "armtest"]


def test_enabled_exercises_start_with_reach_then_enable_more(tmp_path):
    with TestClient(_app(tmp_path, live_exercises=ALL4, enabled_exercises=["reach"])) as c:
        assert [e["id"] for e in c.get("/api/exercises").json()] == ["reach"]
        r = c.post("/api/session/start", json={"patient_id": "sim-1", "exercise": "push"})
        assert r.status_code == 422 and r.json()["detail"]["live"] == ["reach"]

        r = c.post("/api/exercises/enable", json={"ids": ["push"]})
        assert r.status_code == 200 and r.json() == {"ok": True, "enabled": ["reach", "push"], "can_run": ALL4}
        assert [e["id"] for e in c.get("/api/exercises").json()] == ["reach", "push"]
        assert c.post("/api/session/start", json={"patient_id": "sim-1", "exercise": "push"}).status_code == 200
        c.post("/api/session/stop")

        r = c.post("/api/exercises/enable", json={"ids": ["pull", "armtest"]})
        assert r.json()["enabled"] == ALL4
        r = c.post("/api/exercises/disable", json={"ids": ["pull"]})
        assert r.json()["enabled"] == ["reach", "push", "armtest"]
        assert c.post("/api/session/start", json={"patient_id": "sim-1", "exercise": "pull"}).status_code == 422

        r = c.post("/api/exercises/enable", json={"ids": ["circle"]})      # not something this robot can run
        assert r.status_code == 422 and r.json()["detail"]["can_run"] == ALL4
        assert c.post("/api/exercises/enable", json={"ids": []}).status_code == 422


def test_enable_defaults_to_everything_and_needs_the_token(tmp_path):
    with TestClient(_app(tmp_path, live_exercises=ALL4)) as c:               # no --exercises: all offered
        assert [e["id"] for e in c.get("/api/exercises").json()] == ALL4
        assert c.post("/api/exercises/disable", json={"ids": ["armtest"]}).json()["enabled"] == ALL4[:3]
    (tmp_path / "t").mkdir()
    with TestClient(_app(tmp_path / "t", live_exercises=ALL4, enabled_exercises=["reach"],
                         control_token="secret")) as c:
        assert c.post("/api/exercises/enable", json={"ids": ["push"]}).status_code == 403
        assert c.post("/api/exercises/enable", json={"ids": ["push"]},
                      headers={"x-operator-token": "secret"}).status_code == 200


def test_run_exercises_option(monkeypatch, capsys, tmp_path):
    from server import run
    seen = {}

    class FakeServer:
        def __init__(self, config):
            seen["app"] = config.app

        def run(self):
            pass
    monkeypatch.setattr(run.uvicorn, "Server", FakeServer)
    run.main(["--mock", "--no-export", "--db", str(tmp_path / "r.db"), "--exercises", "reach"])
    assert seen["app"].state.hub.enabled == {"reach"}
    assert "enabled now: reach" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        run.main(["--mock", "--no-export", "--db", str(tmp_path / "r2.db"), "--exercises", "reach,lift"])
