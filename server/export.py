"""Write JSON and CSV exports for Mat and Gio (website, deck) from the database.

Run:  python -m server.export      (reads server/data/rehab.db, writes server/exports/)
Every row keeps its `simulated` flag.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import fields
from pathlib import Path

from . import db
from .contract import RepResult
from .exercises import canonical
from .note import session_note
from .stats import session_means

DEFAULT_OUT = "server/exports"


def session_row(conn, s) -> dict:
    return s.to_dict() | session_means(db.list_reps(conn, s.session_id))


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def export_all(conn, out_dir: str | Path = DEFAULT_OUT) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    patients = db.list_patients(conn)
    _write_json(out / "patients.json", patients)
    written.append(str(out / "patients.json"))

    sessions = db.all_sessions(conn)
    _write_json(out / "sessions.json", [session_row(conn, s) for s in sessions])
    written.append(str(out / "sessions.json"))

    cols = ["patient_id"] + [f.name for f in fields(RepResult)] + ["exercise"]
    with open(out / "reps.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for s in sessions:
            for r in db.list_reps(conn, s.session_id):
                d = r.to_dict() | {"patient_id": s.patient_id, "exercise": canonical(s.exercise)}
                w.writerow([str(d[c]).lower() if isinstance(d[c], bool) else d[c] for c in cols])
    written.append(str(out / "reps.csv"))

    latest = None
    if sessions:
        s = max(sessions, key=lambda x: (x.started_at, x.session_id))
        reps = db.list_reps(conn, s.session_id)
        same = [x for x in db.list_sessions(conn, s.patient_id)      # previous session of the same exercise
                if x.started_at < s.started_at and canonical(x.exercise) == canonical(s.exercise)]
        prev = db.list_reps(conn, same[-1].session_id) if same else None
        latest = {"session": session_row(conn, s),
                  "reps": [r.to_dict() | {"exercise": canonical(s.exercise)} for r in reps],
                  "note": session_note(s, reps, prev), "simulated": s.simulated}
    _write_json(out / "latest_session.json", latest)
    written.append(str(out / "latest_session.json"))
    return written


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Export the database to JSON and CSV for the website and deck.")
    ap.add_argument("--db", default=db.DEFAULT_PATH)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    conn = db.connect(a.db)
    for p in export_all(conn, a.out):
        print("wrote", p)
    conn.close()


if __name__ == "__main__":
    main()
