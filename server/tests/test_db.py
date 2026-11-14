import sqlite3

import pytest

from server import db
from server.contract import RepResult, SessionSummary


def _session(sid="s1", pid="p1", sim=True, n=0, ended=None):
    return SessionSummary(session_id=sid, patient_id=pid, started_at="2026-11-14T15:00:00",
                          ended_at=ended, exercise="reach_line", n_reps=n, simulated=sim)


def _rep(sid="s1", idx=0, sim=True, **kw):
    base = dict(session_id=sid, idx=idx, mode="assist", dial=0.9, t_start=1.0, duration_s=4.2,
                rom_m=0.28, path_err_mean_m=0.01, path_err_max_m=0.02, sparc=-1.7, peak_force_n=9.5,
                mean_force_n=4.1, contribution=0.4, completed=True, simulated=sim, rescued=False)
    base.update(kw)
    return RepResult(**base)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "sub" / "t.db")
    yield c
    c.close()


def test_creates_folder_and_tables(tmp_path):
    c = db.connect(tmp_path / "a" / "b" / "x.db")
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"patients", "sessions", "reps"} <= names
    c.close()


def test_save_and_reload_equal(conn):
    db.upsert_patient(conn, "p1", "Sim (SIMULATED)", True)
    s = _session()
    db.save_session(conn, s)
    r0, r1 = _rep(idx=0), _rep(idx=1, completed=False, rescued=True, mode="resist", dial=-0.4)
    db.save_rep(conn, r0)
    db.save_rep(conn, r1)
    assert db.list_sessions(conn, "p1") == [s]
    assert db.get_session(conn, "s1") == s
    assert db.list_reps(conn, "s1") == [r0, r1]
    assert db.list_patients(conn) == [{"id": "p1", "display_name": "Sim (SIMULATED)", "simulated": True,
                                       "n_sessions": 1}]


def test_session_update_in_place(conn):
    db.upsert_patient(conn, "p1", "x", True)
    db.save_session(conn, _session())
    db.save_session(conn, _session(n=5, ended="2026-11-14T15:10:00"))
    got = db.list_sessions(conn, "p1")
    assert len(got) == 1 and got[0].n_reps == 5 and got[0].ended_at == "2026-11-14T15:10:00"


def test_same_rep_twice_no_duplicate(conn):
    db.upsert_patient(conn, "p1", "x", True)
    db.save_session(conn, _session())
    db.save_rep(conn, _rep())
    db.save_rep(conn, _rep(rom_m=0.3))
    reps = db.list_reps(conn, "s1")
    assert len(reps) == 1 and reps[0].rom_m == 0.3


def test_real_session_under_simulated_patient_rejected(conn):
    db.upsert_patient(conn, "p1", "x", True)
    with pytest.raises(ValueError):
        db.save_session(conn, _session(sim=False))


def test_simulated_session_under_real_patient_rejected(conn):
    db.upsert_patient(conn, "p2", "x", False)
    with pytest.raises(ValueError):
        db.save_session(conn, _session(pid="p2", sim=True))


def test_rep_flag_must_match_session(conn):
    db.upsert_patient(conn, "p1", "x", True)
    db.save_session(conn, _session())
    with pytest.raises(ValueError):
        db.save_rep(conn, _rep(sim=False))


def test_patient_flag_cannot_flip(conn):
    db.upsert_patient(conn, "p1", "x", True)
    with pytest.raises(ValueError):
        db.upsert_patient(conn, "p1", "x", False)
    db.upsert_patient(conn, "p1", "renamed", True)  # rename is fine
    assert db.get_patient(conn, "p1")["display_name"] == "renamed"


def test_unknown_patient_and_session_rejected(conn):
    with pytest.raises(ValueError):
        db.save_session(conn, _session())
    with pytest.raises(ValueError):
        db.save_rep(conn, _rep())


def test_migrates_v0_tables(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE reps(session_id TEXT, idx INTEGER, simulated INTEGER, PRIMARY KEY(session_id, idx))")
    old.commit()
    old.close()
    c = db.connect(path)
    cols = {r[1] for r in c.execute("PRAGMA table_info(reps)")}
    assert {"rescued", "sparc", "contribution"} <= cols
    c.close()
