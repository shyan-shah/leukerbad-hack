from statistics import fmean

import pytest

from server import db
from server.simulate import make_history


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "h.db")
    make_history(c)
    yield c
    c.close()


def test_fourteen_sessions(conn):
    assert len(db.list_sessions(conn, "sim-anna")) == 14


def test_every_row_simulated(conn):
    for table in ("patients", "sessions", "reps"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE simulated != 1").fetchone()[0] == 0
    assert "(SIMULATED)" in db.get_patient(conn, "sim-anna")["display_name"]


def test_display_name_always_labelled(tmp_path):
    c = db.connect(tmp_path / "x.db")
    make_history(c, patient_id="sim-x", display_name="Bob", days=2, reps_per_session=3)
    assert db.get_patient(c, "sim-x")["display_name"] == "Bob (SIMULATED)"
    c.close()


def _dump(c):
    return [tuple(r) for r in c.execute("SELECT * FROM reps ORDER BY session_id, idx")]


def test_deterministic(tmp_path):
    a, b = db.connect(tmp_path / "a.db"), db.connect(tmp_path / "b.db")
    make_history(a)
    make_history(b)
    assert _dump(a) == _dump(b)
    a.close(), b.close()


def test_idempotent(conn):
    before = conn.execute("SELECT COUNT(*) FROM reps").fetchone()[0]
    make_history(conn)
    assert conn.execute("SELECT COUNT(*) FROM reps").fetchone()[0] == before == 14 * 30


def test_trend_improves(conn):
    sessions = db.list_sessions(conn, "sim-anna")
    first = db.list_reps(conn, sessions[0].session_id)
    last = db.list_reps(conn, sessions[-1].session_id)
    assert fmean(r.contribution for r in first) < fmean(r.contribution for r in last)
    assert fmean(r.dial for r in first) > fmean(r.dial for r in last)
    assert fmean(r.path_err_mean_m for r in first) > fmean(r.path_err_mean_m for r in last)
    assert first[0].dial > 0.6 and last[-1].dial < 0.2
