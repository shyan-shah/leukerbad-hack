"""CheckedArm (server/hw/checked_arm.py), run.py reach options and POST /api/shutdown. No robot."""
import argparse
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from robot.arm import Arm
from server import run as run_mod
from server.api import create_app, is_real_arm
from server.hw.checked_arm import CheckedArm
from server.mock import MockArm, MockEngine

K_NOM = [10000.0, 10000.0, 10000.0, 1500.0, 1500.0, 1500.0]


class FakeRobot:
    def __init__(self, serial, fault=False, operational=True, mode="Mode.IDLE", estop=True):
        self.serial, self._fault, self._op, self._mode, self._estop = serial, fault, operational, mode, estop
        self.calls = []

    def fault(self): return self._fault
    def operational(self): return self._op
    def mode(self): return self._mode
    def estop_released(self): return self._estop
    def info(self): return SimpleNamespace(K_x_nom=K_NOM)

    def states(self):
        return SimpleNamespace(tcp_pose=[0.5, 0.0, 0.3, 0.0, 0.0, 1.0, 0.0], tcp_vel=[0.0] * 6,
                               ext_wrench_in_world=[0.0] * 6, q=[0.0] * 7)

    def __getattr__(self, name):          # Enable, ClearFault, SwitchMode, Stop, ...
        if name[0].isupper():
            return lambda *a, **k: self.calls.append(name)
        raise AttributeError(name)


def fake_rdk(monkeypatch, tool="Flange", **state):
    made = []

    def robot(serial):
        made.append(FakeRobot(serial, **state))
        return made[-1]

    mod = SimpleNamespace(Robot=robot, Tool=lambda r: SimpleNamespace(name=lambda: tool),
                          Mode=SimpleNamespace(NRT_CARTESIAN_MOTION_FORCE="cart", NRT_PRIMITIVE_EXECUTION="prim"))
    monkeypatch.setitem(sys.modules, "flexivrdk", mod)
    return made


def test_connect_attaches_without_enable_or_clearfault(monkeypatch):
    made = fake_rdk(monkeypatch)
    arm = CheckedArm("Rizon4-TEST01")
    arm.connect()
    try:
        assert isinstance(arm, Arm) and is_real_arm(arm)        # data from it is marked real
        assert made[0].serial == "Rizon4-TEST01"
        assert "Enable" not in made[0].calls and "ClearFault" not in made[0].calls
        assert arm.get_state().mode == "idle"
    finally:
        arm.close()
    assert "Stop" in made[0].calls


@pytest.mark.parametrize("state, tool, text", [
    (dict(fault=True), "Flange", "reports a fault"),
    (dict(operational=False), "Flange", "not operational"),
    (dict(mode="Mode.NRT_CARTESIAN_MOTION_FORCE"), "Flange", "not IDLE"),
    (dict(estop=False), "Flange", "e-stop is pressed"),
    (dict(), "Seat_Assembly_tool", "selected tool is 'Seat_Assembly_tool'"),
])
def test_connect_refuses_unready_robot(monkeypatch, state, tool, text):
    made = fake_rdk(monkeypatch, tool=tool, **state)
    arm = CheckedArm("Rizon4-TEST01")
    with pytest.raises(RuntimeError, match=text):
        arm.connect()
    assert made[0].calls == []                                  # nothing was commanded
    with pytest.raises(RuntimeError, match="not connected"):
        arm.get_state()


def test_other_tool_can_be_expected_and_placeholder_serial_refused(monkeypatch):
    fake_rdk(monkeypatch, tool="Handle")
    arm = CheckedArm("Rizon4-TEST01", tool="Handle")
    arm.connect()
    arm.close()
    with pytest.raises(RuntimeError, match="placeholder"):
        CheckedArm("Rizon4-XXXXXX").connect()


def test_unready_arm_is_503_on_start_and_prepare(monkeypatch, tmp_path):
    fake_rdk(monkeypatch, operational=False)
    app = create_app(lambda: CheckedArm("Rizon4-TEST01"), tmp_path / "a.db", engine_factory=MockEngine,
                     site_dir=tmp_path / "nosite")
    with TestClient(app) as c:
        for route, body in (("/api/arm/prepare", None), ("/api/session/start", {"patient_id": "p1"})):
            r = c.post(route, json=body)
            assert r.status_code == 503 and "not operational" in r.json()["detail"]
        assert c.get("/api/health").json()["session"] is False


# ---------------------------------------------------------------- run.py reach options

def _ns(**kw):
    return argparse.Namespace(**({"reach_m": None, "reach_sign": None} | kw))


def test_reach_sign_defaults_to_config_then_plus_one(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"reach_axis": 1, "reach_sign": -1}), encoding="utf-8")
    assert run_mod.config_reach(cfg) == (1, -1)
    assert run_mod.config_reach(tmp_path / "missing.json") == (0, 1)
    monkeypatch.setattr(run_mod, "ROBOT_CONFIG", cfg)
    assert run_mod.reach_kwargs(_ns()) == {"reach_sign": -1}
    assert run_mod.reach_kwargs(_ns(reach_sign=1, reach_m=0.10)) == {"reach_sign": 1, "reach_m": 0.10}


def test_engine_gets_reach_kwargs(tmp_path):
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return MockEngine(**kw, time_scale=200)

    app = create_app(MockArm, tmp_path / "a.db", engine_factory=factory, site_dir=tmp_path / "nosite",
                     engine_kwargs={"reach_sign": -1, "reach_m": 0.10})
    with TestClient(app) as c:
        assert c.post("/api/session/start", json={"patient_id": "p1"}).status_code == 200
    assert seen["reach_sign"] == -1 and seen["reach_m"] == 0.10 and seen["reach_axis"] == 0


def test_run_rejects_out_of_range_reach():
    with pytest.raises(SystemExit):
        run_mod.main(["--mock", "--reach-m", "0.5"])


# ---------------------------------------------------------------- POST /api/shutdown

def _mock_app(tmp_path, **kw):
    return create_app(MockArm, tmp_path / "a.db", engine_factory=lambda **k: MockEngine(**k, time_scale=200),
                      site_dir=tmp_path / "nosite", **kw)


def test_shutdown_stops_session_and_requests_exit(tmp_path):
    app = _mock_app(tmp_path)
    asked = []
    app.state.request_exit = lambda: asked.append(True)
    with TestClient(app) as c:
        sid = c.post("/api/session/start", json={"patient_id": "p1"}).json()["session_id"]
        r = c.post("/api/shutdown")
        assert r.status_code == 200 and r.json() == {"ok": True, "stopped_session": sid}
        assert asked == [True] and c.get("/api/health").json()["session"] is False
        arm = app.state.hub.arm
    assert app.state.hub.closed is True and arm.mode in ("idle", "hold")     # lifespan held and closed it


def test_shutdown_501_without_run_and_403_from_other_hosts(tmp_path):
    app = _mock_app(tmp_path)
    with TestClient(app) as c:
        assert c.post("/api/shutdown").status_code == 501
    app = _mock_app(tmp_path)
    asked = []
    app.state.request_exit = lambda: asked.append(True)
    with TestClient(app, client=("192.168.1.50", 50000)) as c:
        assert c.post("/api/shutdown").status_code == 403
    assert asked == []


def test_shutdown_needs_token_in_lan_mode(tmp_path):
    app = _mock_app(tmp_path, control_token="secret")
    asked = []
    app.state.request_exit = lambda: asked.append(True)
    with TestClient(app) as c:
        assert c.post("/api/shutdown").status_code == 403
        assert c.post("/api/shutdown", headers={"x-operator-token": "secret"}).status_code == 200
    assert asked == [True]
