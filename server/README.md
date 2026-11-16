# server/: the station server, screens and real-arm tools

One local process on the station laptop. The phone app, the big screen and the physio dashboard all talk to it; nothing needs the internet.

| File or folder | What it is |
|---|---|
| `run.py` | Start it: `python -m server.run --mock` (no robot), `--sim` (simulated arm), `--robot --lan` (real arm) |
| `api.py` | FastAPI app: sessions, levels, arm prepare and home, live WebSocket feed at 30 Hz |
| `API.md` | Every route and message, with real examples |
| `contract.py`, `db.py`, `export.py`, `note.py` | Data records, SQLite storage, JSON/CSV exports, automatic session note |
| `exercises.py` | Which programmes the station offers |
| `mock.py`, `simulate.py` | Stand-in engine for building screens; 14 days of history clearly labelled SIMULATED |
| `screens/` | `patient.html` (big screen), `physio.html` (therapist dashboard), `operator.html` (operator console with HOLD) |
| `hw/` | Scripts used to bring the real arm up: read-only probe, joint moves with automatic stops, zeroing, drift check, path trace. Results in `hw/results/` |
| `tests/` | API, storage, screens and end-to-end tests |
