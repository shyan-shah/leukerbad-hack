"""Local REST + WebSocket API (MASTER_PLAN section 4.6). Works with no internet.

The engine (software/engine.py, or server/mock.py) calls on_sample at 100 Hz and on_rep at
each rep end from its own thread. Those callbacks only store/queue; a background task saves
reps to SQLite and broadcasts on /ws/live at 30 Hz (newest sample only, every rep).

`simulated` is decided here from the arm type, never by the caller: only data from the real
robot.arm.Arm is marked real.
"""
from __future__ import annotations

import asyncio
import os
import queue
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .contract import RepResult, Sample, SessionSummary
from .export import export_all, session_row
from .note import session_note

WS_HZ = 30
REPO = Path(__file__).resolve().parents[1]


def is_real_arm(arm: Any) -> bool:
    try:
        from robot.arm import Arm
    except Exception:
        return False
    return isinstance(arm, Arm)


def default_engine_factory(**kw):
    from software.engine import Engine
    return Engine(**kw)


class StartBody(BaseModel):
    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field("", max_length=80)
    dial: float = Field(1.0, ge=-1.0, le=1.0)
    auto: bool = True


class DialBody(BaseModel):
    dial: float = Field(ge=-1.0, le=1.0)
    auto: bool | None = None


class Hub:
    """All mutable server state. Engine callbacks run on the engine thread; everything else
    on the event loop or FastAPI's thread pool."""

    def __init__(self, arm_factory, conn, engine_factory, exports_dir, engine_kwargs, is_real):
        self.arm_factory, self.conn, self.engine_factory = arm_factory, conn, engine_factory
        self.exports_dir, self.engine_kwargs, self.is_real = exports_dir, engine_kwargs, is_real
        self.arm = None
        self.engine = None
        self.session: SessionSummary | None = None
        self.db_lock = threading.Lock()
        self.ctl_lock = threading.Lock()        # one start/stop at a time
        self.rep_q: queue.Queue[RepResult] = queue.Queue()
        self.latest: Sample | None = None
        self.sent: Sample | None = None
        self.pending: list[dict] = []
        self.pending_lock = threading.Lock()
        self.clients: set[WebSocket] = set()

    # -- engine callbacks (engine thread): must be fast
    def on_sample(self, s: Sample) -> None:
        self.latest = s

    def on_rep(self, r: RepResult) -> None:
        self.rep_q.put(r)

    # -- shared
    def get_arm(self):
        if self.arm is None:
            arm = self.arm_factory()
            if hasattr(arm, "connect"):
                arm.connect()
            self.arm = arm
        return self.arm

    @property
    def simulated(self) -> bool:
        return not self.is_real(self.arm)

    def flush_reps(self) -> None:
        msgs = []
        while True:
            try:
                r = self.rep_q.get_nowait()
            except queue.Empty:
                break
            with self.db_lock:
                db.save_rep(self.conn, r)
            msgs.append({"type": "rep"} | r.to_dict())
        if msgs:
            with self.pending_lock:
                self.pending.extend(msgs)

    def snapshot(self) -> dict:
        snap = self.engine.snapshot() if self.engine else {}
        return snap

    def hold(self) -> None:
        if self.arm is not None and hasattr(self.arm, "hold"):
            self.arm.hold()

    def stop_session(self) -> SessionSummary | None:
        with self.ctl_lock:
            if self.engine is None or self.session is None:
                return None
            try:
                self.engine.stop()
            finally:
                self.engine = None
            self.flush_reps()
            with self.db_lock:
                n = db.count_reps(self.conn, self.session.session_id)
                s = SessionSummary(**(self.session.to_dict() | {
                    "ended_at": datetime.now().isoformat(timespec="seconds"), "n_reps": n}))
                db.save_session(self.conn, s)
                if self.exports_dir:
                    export_all(self.conn, self.exports_dir)
            self.session = None
            return s

    def shutdown(self) -> None:
        try:
            self.stop_session()
        finally:
            if self.arm is not None:
                for m in ("hold", "close"):
                    try:
                        getattr(self.arm, m, lambda: None)()
                    except Exception:
                        pass

    async def broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(1 / WS_HZ)
            try:
                await asyncio.to_thread(self.flush_reps)
                with self.pending_lock:
                    msgs, self.pending = self.pending, []
                s = self.latest
                if s is not None and s is not self.sent and self.engine is not None:
                    self.sent = s
                    snap = self.snapshot()
                    msgs.insert(0, {"type": "sample"} | s.to_dict() | {
                        "rep_count": snap.get("rep_count"), "auto": snap.get("auto"),
                        "arm_mode": snap.get("arm_mode")})
                if not msgs or not self.clients:
                    continue
                for ws in list(self.clients):
                    try:
                        for m in msgs:
                            await ws.send_json(m)
                    except Exception:
                        self.clients.discard(ws)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # never let the broadcaster die
                print(f"[api] broadcast error: {e!r}")


def create_app(arm_factory: Callable[[], Any], db_path: str | Path = db.DEFAULT_PATH,
               engine_factory: Callable[..., Any] | None = None, exports_dir: str | Path | None = None,
               engine_kwargs: dict | None = None, control_token: str | None = None,
               site_dir: str | Path | None = None, is_real: Callable[[Any], bool] = is_real_arm) -> FastAPI:
    """
    arm_factory()      -> arm object (connected on first session start)
    engine_factory(**) -> engine with the MASTER_PLAN 4.4 interface (default software.engine.Engine)
    exports_dir        -> if set, exports are rewritten after every session stop
    control_token      -> if set, POST start/stop/dial/go need header `x-operator-token`. /api/hold never does.
    """
    conn = db.connect(db_path)
    hub = Hub(arm_factory, conn, engine_factory or default_engine_factory, exports_dir,
              engine_kwargs or {}, is_real)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(hub.broadcast_loop())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.to_thread(hub.shutdown)
            conn.close()

    app = FastAPI(title="Rehab station API", lifespan=lifespan)
    app.state.hub = hub
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def guard(token: str | None) -> None:
        if control_token and token != control_token:
            raise HTTPException(403, "operator token required (header x-operator-token)")

    @app.get("/api/health")
    def health():
        arm_kind = None if hub.arm is None else ("flexiv" if hub.is_real(hub.arm) else "sim")
        mode = hub.snapshot().get("arm_mode") if hub.engine else getattr(hub.arm, "mode", None)
        return {"ok": True, "arm": arm_kind, "arm_mode": mode, "session": hub.session is not None}

    @app.get("/api/state")
    def state():
        if hub.session is None or hub.engine is None:
            return {"session": None}
        return {"session": {"session_id": hub.session.session_id, "patient_id": hub.session.patient_id,
                            "simulated": hub.session.simulated}} | hub.snapshot()

    @app.post("/api/session/start")
    def start(body: StartBody, x_operator_token: str | None = Header(default=None)):
        guard(x_operator_token)
        with hub.ctl_lock:
            if hub.session is not None:
                raise HTTPException(409, "a session is already running; stop it first")
            arm = hub.get_arm()
            sim = hub.simulated
            name = body.display_name or body.patient_id
            if sim and "SIMULATED" not in name.upper():
                name = f"{name} (SIMULATED)"
            sid = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
            summary = SessionSummary(session_id=sid, patient_id=body.patient_id,
                                     started_at=datetime.now().isoformat(timespec="seconds"),
                                     ended_at=None, exercise="reach_line", n_reps=0, simulated=sim)
            with hub.db_lock:
                try:
                    db.upsert_patient(conn, body.patient_id, name, sim)
                except ValueError as e:
                    raise HTTPException(409, str(e))
                db.save_session(conn, summary)
            kw = {"reach_axis": getattr(arm, "reach_axis", 0)} | hub.engine_kwargs
            engine = hub.engine_factory(arm=arm, session_id=sid, patient_id=body.patient_id, simulated=sim,
                                        dial=body.dial, auto=body.auto, on_sample=hub.on_sample,
                                        on_rep=hub.on_rep, **kw)
            hub.latest = hub.sent = None
            hub.session, hub.engine = summary, engine
            try:
                engine.start()
            except Exception:
                hub.engine, hub.session = None, None
                hub.hold()
                raise
            return {"session_id": sid, "simulated": sim, "display_name": name}

    @app.post("/api/session/stop")
    def stop(x_operator_token: str | None = Header(default=None)):
        guard(x_operator_token)
        s = hub.stop_session()
        if s is None:
            raise HTTPException(409, "no session running")
        return s.to_dict()

    @app.post("/api/dial")
    def dial(body: DialBody, x_operator_token: str | None = Header(default=None)):
        guard(x_operator_token)
        if hub.engine is None:
            raise HTTPException(409, "no session running")
        hub.engine.set_dial(body.dial, body.auto)
        return {"dial": body.dial, "auto": hub.snapshot().get("auto", body.auto)}

    @app.post("/api/hold")
    def hold():
        hub.hold()
        return {"ok": True, "arm": None if hub.arm is None else "held"}

    @app.post("/api/go")
    def go(x_operator_token: str | None = Header(default=None)):
        guard(x_operator_token)
        fn = getattr(hub.engine, "go", None)
        if fn is None:
            raise HTTPException(501, "this engine has no operator cue (go)")
        fn()
        return {"ok": True}

    @app.get("/api/patients")
    def patients():
        with hub.db_lock:
            return db.list_patients(conn)

    @app.get("/api/patients/{patient_id}/sessions")
    def sessions(patient_id: str):
        with hub.db_lock:
            if db.get_patient(conn, patient_id) is None:
                raise HTTPException(404, "unknown patient")
            return [session_row(conn, s) for s in db.list_sessions(conn, patient_id)]

    @app.get("/api/sessions/{session_id}/reps")
    def reps(session_id: str):
        with hub.db_lock:
            if db.get_session(conn, session_id) is None:
                raise HTTPException(404, "unknown session")
            return [r.to_dict() for r in db.list_reps(conn, session_id)]

    @app.get("/api/sessions/{session_id}/note", response_class=PlainTextResponse)
    def note(session_id: str):
        with hub.db_lock:
            s = db.get_session(conn, session_id)
            if s is None:
                raise HTTPException(404, "unknown session")
            earlier = [x for x in db.list_sessions(conn, s.patient_id)
                       if (x.started_at, x.session_id) < (s.started_at, s.session_id)]
            prev = db.list_reps(conn, earlier[-1].session_id) if earlier else None
            return session_note(s, db.list_reps(conn, session_id), prev)

    @app.websocket("/ws/live")
    async def live(ws: WebSocket):
        await ws.accept()
        hub.clients.add(ws)
        try:
            while True:
                await ws.receive_text()   # clients need not send; this just detects disconnect
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    site = Path(site_dir) if site_dir else REPO / "demo" / "site"
    if site.is_dir() and any(site.iterdir()):
        app.mount("/", StaticFiles(directory=str(site), html=True), name="site")
    return app
