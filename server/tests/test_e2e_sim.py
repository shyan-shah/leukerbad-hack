"""Y4: end-to-end through the real API, database, note and exports.

Two variants:
- mock: server/mock.py engine (always runs).
- sim: Shiv's software/engine.py with software/sim_arm.py + sim_patient.py. Skipped until those
  exist on main; then it runs automatically and is the real integration test (I2).
"""
import csv
import json
import time
from functools import partial

import pytest
from fastapi.testclient import TestClient

from server import db
from server.api import create_app
from server.mock import MockArm, MockEngine

N = 10
START = {"patient_id": "sim-e2e", "display_name": "E2E", "dial": 1.0, "auto": True}


def _run(app, tmp_path, timeout):
    with TestClient(app) as c:
        r = c.post("/api/session/start", json=START)
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]
        t0 = time.time()
        while (c.get("/api/state").json().get("rep_count") or 0) < N:
            assert time.time() - t0 < timeout, "engine too slow or stuck"
            time.sleep(0.05)
        summary = c.post("/api/session/stop").json()
        reps = c.get(f"/api/sessions/{sid}/reps").json()
        note = c.get(f"/api/sessions/{sid}/note").text

    assert summary["n_reps"] >= N and len(reps) == summary["n_reps"]
    assert [r["idx"] for r in reps] == list(range(len(reps)))
    assert "SIMULATED DATA" in note and f"{len(reps)} started" in note

    conn = db.connect(tmp_path / "e2e.db")
    assert db.count_reps(conn, sid) == len(reps)
    for table in ("patients", "sessions", "reps"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE simulated != 1").fetchone()[0] == 0
    conn.close()

    out = tmp_path / "exports"
    assert json.loads((out / "latest_session.json").read_text())["session"]["session_id"] == sid
    with open(out / "reps.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(reps) and all(r["simulated"] == "true" for r in rows)
    return reps


def test_e2e_mock(tmp_path):
    app = create_app(MockArm, tmp_path / "e2e.db", exports_dir=tmp_path / "exports",
                     engine_factory=partial(MockEngine, strength=0.8, time_scale=200), site_dir=tmp_path / "x")
    reps = _run(app, tmp_path, timeout=30)
    assert reps[-1]["dial"] < reps[0]["dial"]   # auto dial came down for a strong patient


def test_e2e_sim(tmp_path):
    sim_arm = pytest.importorskip("software.sim_arm", reason="waiting for Shiv's S1")
    sim_patient = pytest.importorskip("software.sim_patient", reason="waiting for Shiv's S0d")
    pytest.importorskip("software.engine", reason="waiting for Shiv's S4")
    arm_factory = lambda: sim_arm.SimArm(sim_patient.SimPatient(strength=0.8))  # noqa: E731
    app = create_app(arm_factory, tmp_path / "e2e.db", exports_dir=tmp_path / "exports", site_dir=tmp_path / "x")
    _run(app, tmp_path, timeout=300)
