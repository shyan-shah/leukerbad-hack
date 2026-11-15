"""arm_fault in /api/state and sample messages: why the arm stopped.

On 15 Nov a real reach set tripped on speed 25 s in; the app could only show a force of "30 N+"
(the person pushing against the held arm) and no reason.
"""
from functools import partial

from fastapi.testclient import TestClient

from server.api import create_app
from server.mock import MockArm, MockEngine

FAST = partial(MockEngine, strength=0.8, time_scale=200)


def test_state_carries_the_trip_reason(tmp_path):
    app = create_app(MockArm, tmp_path / "f.db", engine_factory=FAST, site_dir=tmp_path / "nosite")
    hub = app.state.hub
    with TestClient(app) as c:
        assert c.post("/api/session/start", json={"patient_id": "p1"}).status_code == 200
        st = c.get("/api/state").json()
        assert "arm_fault" in st and st["arm_fault"] is None
        hub.arm._fault = "speed 0.44 m/s above 0.40 m/s"
        assert hub.arm_fault("compliant") is None
        assert hub.arm_fault("hold") == "speed 0.44 m/s above 0.40 m/s"
        assert hub.arm_fault("fault") == "speed 0.44 m/s above 0.40 m/s"
        hub.arm._fault = None
        assert hub.arm_fault("hold") is None            # an ordinary stop, not a trip
        assert c.post("/api/session/stop").status_code == 200
    assert c is not None


def test_no_session_no_arm_fault_key(tmp_path):
    app = create_app(MockArm, tmp_path / "g.db", engine_factory=FAST, site_dir=tmp_path / "nosite")
    with TestClient(app) as c:
        assert c.get("/api/state").json() == {"session": None}
