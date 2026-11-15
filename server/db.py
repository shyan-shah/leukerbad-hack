"""SQLite storage for patients, sessions and reps. Standard library only.

Every table carries `simulated`. Simulated and real data never mix:
a real session cannot be saved under a simulated patient, nor the reverse.
"""
from __future__ import annotations

import sqlite3
from dataclasses import fields
from pathlib import Path

from .contract import RepResult, SessionSummary

DEFAULT_PATH = "server/data/rehab.db"


def _sql_type(f) -> str:
    t = str(f.type)
    if t.startswith("bool"):
        return "INTEGER"
    if t.startswith("int"):
        return "INTEGER"
    if t.startswith("float"):
        return "REAL"
    return "TEXT"


_SESSION_COLS = [f.name for f in fields(SessionSummary)]
_REP_COLS = [f.name for f in fields(RepResult)]


def _create(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS patients(
        id TEXT PRIMARY KEY, display_name TEXT, simulated INTEGER NOT NULL)""")
    cols = ", ".join(
        f"{f.name} {_sql_type(f)}" + (" PRIMARY KEY" if f.name == "session_id" else "")
        for f in fields(SessionSummary))
    conn.execute(f"CREATE TABLE IF NOT EXISTS sessions({cols}, "
                 "FOREIGN KEY(patient_id) REFERENCES patients(id))")
    cols = ", ".join(f"{f.name} {_sql_type(f)}" for f in fields(RepResult))
    conn.execute(f"CREATE TABLE IF NOT EXISTS reps({cols}, PRIMARY KEY(session_id, idx), "
                 "FOREIGN KEY(session_id) REFERENCES sessions(session_id))")
    # Forward migration: add columns for fields added to the contract after the table was created.
    for table, dc in (("sessions", SessionSummary), ("reps", RepResult)):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for f in fields(dc):
            if f.name not in have:
                default = " DEFAULT 0" if _sql_type(f) == "INTEGER" else ""
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {f.name} {_sql_type(f)}{default}")
    # Forward migration (E2): sessions.exercise now holds the programme id. Every session stored
    # before that was the straight reach ("reach_line", or empty on very old rows).
    conn.execute("UPDATE sessions SET exercise = 'reach' "
                 "WHERE exercise IS NULL OR exercise = '' OR exercise = 'reach_line'")
    conn.commit()


def connect(path: str | Path = DEFAULT_PATH) -> sqlite3.Connection:
    """Open (and create if missing) the database. Safe to share across threads if callers lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _create(conn)
    return conn


def _patient_simulated(conn, patient_id: str) -> bool | None:
    row = conn.execute("SELECT simulated FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return None if row is None else bool(row["simulated"])


def upsert_patient(conn, id: str, display_name: str, simulated: bool) -> None:
    existing = _patient_simulated(conn, id)
    if existing is not None and existing != bool(simulated):
        raise ValueError(f"patient {id!r} is simulated={existing}; cannot change to {bool(simulated)}")
    conn.execute("INSERT INTO patients(id, display_name, simulated) VALUES (?, ?, ?) "
                 "ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name",
                 (id, display_name, int(bool(simulated))))
    conn.commit()


def save_session(conn, s: SessionSummary) -> None:
    psim = _patient_simulated(conn, s.patient_id)
    if psim is None:
        raise ValueError(f"unknown patient {s.patient_id!r}")
    if psim != bool(s.simulated):
        raise ValueError(f"session simulated={s.simulated} but patient {s.patient_id!r} simulated={psim}")
    row = conn.execute("SELECT patient_id, simulated FROM sessions WHERE session_id = ?",
                       (s.session_id,)).fetchone()
    if row is not None and (row["patient_id"] != s.patient_id or bool(row["simulated"]) != bool(s.simulated)):
        raise ValueError(f"session {s.session_id!r} already exists with a different patient or simulated flag")
    d = s.to_dict()
    cols = ", ".join(_SESSION_COLS)
    qs = ", ".join("?" for _ in _SESSION_COLS)
    upd = ", ".join(f"{c} = excluded.{c}" for c in _SESSION_COLS if c != "session_id")
    conn.execute(f"INSERT INTO sessions({cols}) VALUES ({qs}) ON CONFLICT(session_id) DO UPDATE SET {upd}",
                 [d[c] for c in _SESSION_COLS])
    conn.commit()


def save_rep(conn, r: RepResult, commit: bool = True) -> None:
    row = conn.execute("SELECT simulated FROM sessions WHERE session_id = ?", (r.session_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown session {r.session_id!r}")
    if bool(row["simulated"]) != bool(r.simulated):
        raise ValueError(f"rep simulated={r.simulated} but session {r.session_id!r} simulated={bool(row['simulated'])}")
    d = r.to_dict()
    cols = ", ".join(_REP_COLS)
    qs = ", ".join("?" for _ in _REP_COLS)
    conn.execute(f"INSERT OR REPLACE INTO reps({cols}) VALUES ({qs})", [d[c] for c in _REP_COLS])
    if commit:
        conn.commit()


def list_patients(conn) -> list[dict]:
    rows = conn.execute("""SELECT p.id, p.display_name, p.simulated,
                                  (SELECT COUNT(*) FROM sessions s WHERE s.patient_id = p.id) AS n_sessions
                           FROM patients p ORDER BY p.id""").fetchall()
    return [{"id": r["id"], "display_name": r["display_name"], "simulated": bool(r["simulated"]),
             "n_sessions": r["n_sessions"]} for r in rows]


def get_patient(conn, patient_id: str) -> dict | None:
    return next((p for p in list_patients(conn) if p["id"] == patient_id), None)


def _summary(row) -> SessionSummary:
    d = dict(row)
    d["simulated"] = bool(d["simulated"])
    return SessionSummary.from_dict(d)


def _rep(row) -> RepResult:
    d = dict(row)
    for k in ("simulated", "completed", "rescued"):
        d[k] = bool(d[k])
    return RepResult.from_dict(d)


def list_sessions(conn, patient_id: str) -> list[SessionSummary]:
    rows = conn.execute("SELECT * FROM sessions WHERE patient_id = ? ORDER BY started_at, session_id",
                        (patient_id,)).fetchall()
    return [_summary(r) for r in rows]


def all_sessions(conn) -> list[SessionSummary]:
    rows = conn.execute("SELECT * FROM sessions ORDER BY started_at, session_id").fetchall()
    return [_summary(r) for r in rows]


def get_session(conn, session_id: str) -> SessionSummary | None:
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    return None if row is None else _summary(row)


def list_reps(conn, session_id: str) -> list[RepResult]:
    rows = conn.execute("SELECT * FROM reps WHERE session_id = ? ORDER BY idx", (session_id,)).fetchall()
    return [_rep(r) for r in rows]


def count_reps(conn, session_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM reps WHERE session_id = ?", (session_id,)).fetchone()[0]
