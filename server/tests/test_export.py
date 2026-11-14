import csv
import json

import pytest

from server import db
from server.export import export_all
from server.simulate import make_history


@pytest.fixture
def out(tmp_path):
    conn = db.connect(tmp_path / "e.db")
    make_history(conn, days=3, reps_per_session=5)
    files = export_all(conn, tmp_path / "exports")
    yield tmp_path / "exports", files, conn
    conn.close()


def test_files_exist_and_parse(out):
    d, files, _ = out
    assert len(files) == 4
    for name in ("patients.json", "sessions.json", "latest_session.json"):
        json.loads((d / name).read_text(encoding="utf-8"))
    with open(d / "reps.csv", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 15


def test_counts_match_database(out):
    d, _, conn = out
    sessions = json.loads((d / "sessions.json").read_text(encoding="utf-8"))
    assert len(sessions) == conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 3
    assert all(s["n_reps"] == 5 for s in sessions)
    patients = json.loads((d / "patients.json").read_text(encoding="utf-8"))
    assert len(patients) == 1 and patients[0]["n_sessions"] == 3


def test_every_row_has_simulated(out):
    d, _, _ = out
    for name in ("patients.json", "sessions.json"):
        assert all(row["simulated"] is True for row in json.loads((d / name).read_text(encoding="utf-8")))
    with open(d / "reps.csv", encoding="utf-8") as f:
        assert all(row["simulated"] == "true" for row in csv.DictReader(f))
    latest = json.loads((d / "latest_session.json").read_text(encoding="utf-8"))
    assert latest["simulated"] is True and all(r["simulated"] for r in latest["reps"])
    assert "SIMULATED DATA" in latest["note"]


def test_latest_is_last_session(out):
    d, _, _ = out
    latest = json.loads((d / "latest_session.json").read_text(encoding="utf-8"))
    assert latest["session"]["session_id"] == "sim-anna-d03-s1"
    assert "Change vs previous session" in latest["note"]


def test_empty_database(tmp_path):
    conn = db.connect(tmp_path / "empty.db")
    export_all(conn, tmp_path / "x")
    assert json.loads((tmp_path / "x" / "latest_session.json").read_text()) is None
    conn.close()
