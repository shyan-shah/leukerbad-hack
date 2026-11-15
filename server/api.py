"""Local REST + WebSocket API (MASTER_PLAN section 4.6). Works with no internet.

The engine (software/engine.py, or server/mock.py) calls on_sample at 100 Hz and on_rep at
each rep end from its own thread. Those callbacks only store/queue; a background task saves
reps to SQLite and broadcasts on /ws/live at 30 Hz (newest sample only, every rep).

`simulated` is decided here from the arm type, never by the caller: only data from the real
robot.arm.Arm is marked real.
"""
from __future__ import annotations

import asyncio
import inspect
import mimetypes
import os
import queue
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import clock, db, exercises
from .contract import RepResult, Sample, SessionSummary
from .export import export_all, session_row
from .note import session_note

WS_HZ = 30
REPO = Path(__file__).resolve().parents[1]
SCREENS = Path(__file__).resolve().parent / "screens"
mimetypes.add_type("text/javascript", ".js")  # Windows registry can map .js to text/plain; browsers then refuse ES modules


def is_real_arm(arm: Any) -> bool:
    try:
        from robot.arm import Arm
    except Exception:
        return False
    return isinstance(arm, Arm)


def default_engine_factory(**kw):
    """software.engine.Engine. An engine from before E1 has no `exercise`/`reps` arguments: it can
    only run "reach" (anything else is refused, never silently run as a reach) and ignores `reps`."""
    from software.engine import Engine
    params = inspect.signature(Engine.__init__).parameters
    if not any(p.kind is p.VAR_KEYWORD for p in params.values()):
        if "exercise" not in params and kw.get("exercise", "reach") != "reach":
            raise RuntimeError(f"the engine on this laptop cannot run {kw['exercise']!r} yet (only reach)")
        kw = {k: v for k, v in kw.items() if k in params or k not in ("exercise", "reps") + CALIBRATION_ARGS}
    return Engine(**kw)


CALIBRATION_ARGS = ("calibrate", "calibration_state")


def _accepts(factory, name: str) -> bool:
    """True if `factory` takes the keyword `name` (or any keyword). Unknown signatures: False."""
    try:
        params = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind is p.VAR_KEYWORD for p in params.values())


class StartBody(BaseModel):
    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field("", max_length=80)
    dial: float | None = Field(None, ge=-1.0, le=1.0)    # omitted: the exercise's own setting
    auto: bool | None = None                             # omitted: the exercise's own setting
    exercise: str = Field("reach", max_length=32)        # one of GET /api/exercises
    reps: int | None = Field(None, ge=0, le=exercises.REPS_MAX)   # omitted: the exercise default; 0: no limit
    calibrate: bool | None = None                        # comfortable-push calibration; omitted: on for push and pull


class IdsBody(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=16)


class DialBody(BaseModel):
    dial: float = Field(ge=-1.0, le=1.0)
    auto: bool | None = None


LOCAL_CLIENTS = ("127.0.0.1", "::1", "localhost", "testclient")   # "testclient": FastAPI's TestClient
PREPARE_SAMPLES = 30        # get_state() readings averaged for the empty-handle force
PREPARE_SAMPLE_DT = 0.01    # s between readings
START_TOLERANCE_M = 0.02    # prepare (zeroing) is only done this close to the configured start pose


def _start_distance(arm: Any) -> float | None:
    """Distance (m) of the hand from the start pose in robot/config.json, or None when the arm has no
    measured start pose (placeholder config, simulated arms)."""
    cfg = getattr(arm, "config", None)
    if cfg is None or not hasattr(cfg, "start_tcp_pose") or cfg.is_placeholder("start_pose"):
        return None
    pos = arm.get_state().pos
    return sum((float(a) - float(b)) ** 2 for a, b in zip(pos, cfg.start_tcp_pose[:3])) ** 0.5


def _arm_fault(arm: Any) -> str | None:
    """Fault text if the arm reports one, else None. Arms without get_state() report none."""
    get_state = getattr(arm, "get_state", None)
    if get_state is None:
        return None
    st = get_state()
    if getattr(st, "mode", None) == "fault":
        return getattr(st, "fault", None) or "fault"
    return None


def _baseline_force(arm: Any) -> list[float]:
    """Mean force over PREPARE_SAMPLES readings (N, per axis). Zeros for arms without get_state()."""
    get_state = getattr(arm, "get_state", None)
    if get_state is None:
        return [0.0, 0.0, 0.0]
    acc = [0.0, 0.0, 0.0]
    for i in range(PREPARE_SAMPLES):
        acc = [a + float(v) for a, v in zip(acc, get_state().force)]
        if i + 1 < PREPARE_SAMPLES:
            time.sleep(PREPARE_SAMPLE_DT)
    return [a / PREPARE_SAMPLES for a in acc]


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


class Hub:
    """All mutable server state. Engine callbacks run on the engine thread; everything else
    on the event loop or FastAPI's thread pool."""

    def __init__(self, arm_factory, conn, engine_factory, exports_dir, engine_kwargs, is_real):
        self.arm_factory, self.conn, self.engine_factory = arm_factory, conn, engine_factory
        self.exports_dir, self.engine_kwargs, self.is_real = exports_dir, engine_kwargs, is_real
        self.arm = None
        self.prepared = False                   # real arm: POST /api/arm/prepare succeeded since server start
        self.engine = None
        self.session: SessionSummary | None = None
        self.exercise: str | None = None        # programme id of the running session
        self.reps_target: int | None = None     # reps planned for the running session
        self.db_lock = threading.Lock()
        self.ctl_lock = threading.Lock()        # one start/stop at a time
        self.rep_q: queue.Queue[RepResult] = queue.Queue()
        self.latest: Sample | None = None
        self.sent: Sample | None = None
        self.pending: list[dict] = []
        self.pending_lock = threading.Lock()
        self.clients: set[WebSocket] = set()
        self.closed = False                     # shutdown() has held and closed the arm
        self.enabled: set[str] | None = None    # exercise ids offered now; None = every live one

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
            msgs.append({"type": "rep"} | r.to_dict() | {"exercise": self.exercise})
        if msgs:
            with self.pending_lock:
                self.pending.extend(msgs)

    def snapshot(self) -> dict:
        snap = self.engine.snapshot() if self.engine else {}
        if snap:
            snap["arm_fault"] = self.arm_fault(snap.get("arm_mode"))
            snap.setdefault("calibration", None)      # engines from before the calibration contract: null
            snap.setdefault("arming", None)
        return snap

    def arm_fault(self, arm_mode) -> str | None:
        """Why the arm stopped (the trip text, e.g. "speed 0.44 m/s above 0.40 m/s"), while it is in
        hold or fault; else None. After a trip nothing restarts by itself: stop the session, home,
        prepare, start again."""
        if arm_mode not in ("hold", "fault"):
            return None
        return getattr(self.arm, "_fault", None) or getattr(self.arm, "fault", None) or None

    def progress(self, snap: dict) -> dict:
        """exercise, reps_target and done for state and sample messages. The engine's own values win
        (E1 engines report them in snapshot()); otherwise they come from what was asked at start."""
        target = snap.get("reps_target", self.reps_target)
        done = snap.get("done")
        if done is None:
            done = target is not None and (snap.get("rep_count") or 0) >= target
        return {"exercise": snap.get("exercise") or self.exercise, "reps_target": target, "done": bool(done)}

    def hold(self) -> None:
        if self.arm is not None and hasattr(self.arm, "hold"):
            self.arm.hold()

    def stop_session(self) -> SessionSummary | None:
        with self.ctl_lock:
            if self.engine is None or self.session is None:
                return None
            engine, cal, state_after = self.engine, None, None
            try:
                cal = engine.snapshot().get("calibration")
            except Exception as e:
                print(f"[api] snapshot before stop failed: {e!r}", flush=True)
            try:
                engine.stop()
                state_after = getattr(engine, "calibration_state_after", None)
            finally:
                self.engine = None
            self.flush_reps()
            done = cal if isinstance(cal, dict) and cal.get("status") == "done" else {}
            with self.db_lock:
                n = db.count_reps(self.conn, self.session.session_id)
                s = SessionSummary(**(self.session.to_dict() | {
                    "ended_at": clock.now_iso(), "n_reps": n,
                    "comfort_force_n": _num(done.get("comfort_force_n")),
                    "resistance_n": _num(done.get("resistance_n")),
                    "resistance_fraction": _num(done.get("fraction"))}))
                db.save_session(self.conn, s)
                if isinstance(state_after, dict) and state_after:     # never overwrite a stored state with nothing
                    try:
                        db.save_calibration_state(self.conn, s.patient_id, s.exercise, state_after)
                    except (TypeError, ValueError) as e:
                        print(f"[api] calibration state not stored (not JSON): {e!r}", flush=True)
                if self.exports_dir:
                    export_all(self.conn, self.exports_dir)
            self.session = None
            return s

    def shutdown(self) -> None:
        try:
            self.stop_session()
        finally:
            if self.arm is not None and not self.closed:
                self.closed = True
                for m in ("hold", "close"):
                    try:
                        getattr(self.arm, m, lambda: None)()
                    except Exception as e:
                        print(f"[api] arm.{m}() raised during shutdown: {e!r}", flush=True)
                print("[api] arm held and closed", flush=True)

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
                        "arm_mode": snap.get("arm_mode"),
                        "arm_fault": snap.get("arm_fault"), "calibration": snap.get("calibration"),
                        "arming": snap.get("arming")} | self.progress(snap))
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
               site_dir: str | Path | None = None, is_real: Callable[[Any], bool] = is_real_arm,
               live_exercises: list[str] | None = None,
               enabled_exercises: list[str] | None = None) -> FastAPI:
    """
    arm_factory()      -> arm object (connected on first session start)
    engine_factory(**) -> engine with the MASTER_PLAN 4.4 interface (default software.engine.Engine)
    exports_dir        -> if set, exports are rewritten after every session stop
    control_token      -> if set, POST start/stop/dial/go/resume, arm/prepare, arm/home, exercises/enable|disable
                          and shutdown need header `x-operator-token`.
                          /api/hold never does.
    live_exercises     -> ids this engine can run. Default: software.exercises.LIVE, read on every request
                          (only "reach" until that file exists). server.run --mock passes the mock's own list.
    enabled_exercises  -> the subset of those offered at start-up (server.run --exercises reach). Default: all.
                          POST /api/exercises/enable and /disable change it while the server runs.
    """
    conn = db.connect(db_path)
    hub = Hub(arm_factory, conn, engine_factory or default_engine_factory, exports_dir,
              engine_kwargs or {}, is_real)
    if enabled_exercises is not None:
        hub.enabled = {str(i) for i in enabled_exercises}

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

    def runnable_ids() -> list[str]:
        """Everything this engine can run (software.exercises.LIVE)."""
        return list(live_exercises) if live_exercises is not None else exercises.live_ids()

    def live_ids() -> list[str]:
        """What is offered now: the runnable ids the operator has enabled."""
        ids = runnable_ids()
        return ids if hub.enabled is None else [i for i in ids if i in hub.enabled]

    def set_enabled(ids: list[str], on: bool) -> dict:
        runnable = runnable_ids()
        unknown = [i for i in ids if i not in runnable]
        if unknown:
            raise HTTPException(422, {"message": f"not an exercise this robot can run: {', '.join(unknown)}. "
                                                 f"Can run: {', '.join(runnable)}", "can_run": runnable})
        current = set(runnable) if hub.enabled is None else set(hub.enabled)
        hub.enabled = (current | set(ids)) if on else (current - set(ids))
        return {"ok": True, "enabled": live_ids(), "can_run": runnable}

    def guard(token: str | None) -> None:
        if control_token and token != control_token:
            raise HTTPException(403, "operator token required (header x-operator-token)")

    @app.get("/api/health")
    def health():
        arm_kind = None if hub.arm is None else ("flexiv" if hub.is_real(hub.arm) else "sim")
        mode = hub.snapshot().get("arm_mode") if hub.engine else getattr(hub.arm, "mode", None)
        return {"ok": True, "arm": arm_kind, "arm_mode": mode, "session": hub.session is not None,
                "arm_prepared": hub.prepared}

    @app.post("/api/arm/prepare")
    def prepare(x_operator_token: str | None = Header(default=None)):
        """Real arm only, nobody touching the handle: check it is connected and fault-free, zero the
        force reading and report the empty-handle force. Sessions on a real arm need this first."""
        guard(x_operator_token)
        with hub.ctl_lock:
            if hub.session is not None:
                raise HTTPException(409, "a session is running; stop it before preparing the arm")
            try:
                arm = hub.get_arm()
            except Exception as e:
                raise HTTPException(503, f"arm not connected: {e}")
            if hub.simulated:
                return {"ok": True, "simulated": True, "skipped": True,
                        "detail": "simulated arm: nothing to prepare"}
            hub.prepared = False
            fault = _arm_fault(arm)
            if fault:
                raise HTTPException(409, f"arm reports a fault: {fault}")
            from_start = _start_distance(arm)
            if from_start is not None and from_start > START_TOLERANCE_M:
                raise HTTPException(409, f"the handle is {from_start * 100:.1f} cm from the start pose; return it "
                                         "first: POST /api/arm/home, nobody touching. Not zeroed.")
            zeroed, zero_error = False, None
            try:
                arm.zero_force()
                zeroed = True
            except Exception as e:   # this Rizon 4 has no wrist sensor: ZeroFTSensor may be unsupported
                zero_error = f"{type(e).__name__}: {e}"
                print(f"[api] arm.zero_force() failed (non-fatal, the engine takes its own baseline): {zero_error}")
            fault = _arm_fault(arm)
            if fault:
                raise HTTPException(409, f"arm reports a fault after zeroing: {fault}")
            force = _baseline_force(arm)
            mag = sum(v * v for v in force) ** 0.5
            hub.prepared = True
            return {"ok": True, "simulated": False, "zeroed": zeroed, "zero_error": zero_error,
                    "baseline_force": [round(v, 3) for v in force], "baseline_n": round(mag, 3),
                    "from_start_m": None if from_start is None else round(from_start, 4)}

    @app.post("/api/arm/home")
    def home(x_operator_token: str | None = Header(default=None)):
        """Real arm only, NOBODY touching: slow straight move (0.05 m/s) to the start pose of
        robot/config.json. Blocks until the arm is there. Prepare (zero) is needed again afterwards.
        /api/hold cannot interrupt this move; the e-stop can."""
        guard(x_operator_token)
        with hub.ctl_lock:
            if hub.session is not None:
                raise HTTPException(409, "a session is running; stop it before homing the arm")
            try:
                arm = hub.get_arm()
            except Exception as e:
                raise HTTPException(503, f"arm not connected: {e}")
            if hub.simulated:
                return {"ok": True, "simulated": True, "skipped": True,
                        "detail": "simulated arm: nothing to home"}
            hub.prepared = False
            fault = _arm_fault(arm)
            if fault:
                raise HTTPException(409, f"arm reports a fault: {fault}")
            before = _start_distance(arm)
            try:
                arm.home()
            except RuntimeError as e:        # placeholder start pose, too far away, fault, ended off target
                raise HTTPException(409, f"home refused or failed: {e}")
            after = _start_distance(arm)
            return {"ok": True, "simulated": False,
                    "moved_m": None if before is None else round(before, 4),
                    "from_start_m": None if after is None else round(after, 4)}

    @app.get("/api/state")
    def state():
        if hub.session is None or hub.engine is None:
            return {"session": None}
        snap = hub.snapshot()
        return {"session": {"session_id": hub.session.session_id, "patient_id": hub.session.patient_id,
                            "simulated": hub.session.simulated, "exercise": hub.exercise}} | snap | hub.progress(snap)

    @app.get("/api/exercises")
    def list_exercises():
        """The programmes the robot can run now: id, name, kind and default reps."""
        return [exercises.info(i) for i in live_ids()]

    @app.post("/api/exercises/enable")
    def enable_exercises(body: IdsBody, x_operator_token: str | None = Header(default=None)):
        """Operator: offer these programmes (they must be ones the robot can run)."""
        guard(x_operator_token)
        return set_enabled(body.ids, True)

    @app.post("/api/exercises/disable")
    def disable_exercises(body: IdsBody, x_operator_token: str | None = Header(default=None)):
        """Operator: stop offering these programmes. A running session is not affected."""
        guard(x_operator_token)
        return set_enabled(body.ids, False)

    @app.post("/api/session/start")
    def start(body: StartBody, x_operator_token: str | None = Header(default=None)):
        guard(x_operator_token)
        live = live_ids()
        if body.exercise not in live:
            raise HTTPException(422, {"message": f"exercise {body.exercise!r} is not live on the robot. "
                                                 f"Live exercises: {', '.join(live)}", "live": live})
        default_reps = exercises.info(body.exercise)["reps"]
        reps = default_reps if body.reps is None else (body.reps or None)     # None: the engine keeps going
        with hub.ctl_lock:
            if hub.session is not None:
                raise HTTPException(409, "a session is already running; stop it first")
            try:
                arm = hub.get_arm()
            except Exception as e:
                raise HTTPException(503, f"arm not connected: {e}")
            sim = hub.simulated
            if not sim and not hub.prepared:
                raise HTTPException(409, "prepare the arm first: POST /api/arm/prepare with nobody "
                                         "touching the handle")
            name = body.display_name or body.patient_id
            if sim and "SIMULATED" not in name.upper():
                name = f"{name} (SIMULATED)"
            sid = f"{clock.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
            summary = SessionSummary(session_id=sid, patient_id=body.patient_id,
                                     started_at=clock.now_iso(),
                                     ended_at=None, exercise=body.exercise, n_reps=0, simulated=sim)
            with hub.db_lock:
                try:
                    db.upsert_patient(conn, body.patient_id, name, sim)
                except ValueError as e:
                    raise HTTPException(409, str(e))
                db.save_session(conn, summary)
            kw = {"reach_axis": getattr(arm, "reach_axis", 0)} | hub.engine_kwargs
            if body.dial is not None:       # only what the caller sent: otherwise the exercise preset decides
                kw["dial"] = body.dial
            if body.auto is not None:
                kw["auto"] = body.auto
            if _accepts(hub.engine_factory, "calibrate"):
                kw["calibrate"] = body.calibrate
            if _accepts(hub.engine_factory, "calibration_state"):
                with hub.db_lock:
                    kw["calibration_state"] = db.get_calibration_state(conn, body.patient_id, body.exercise)
            hub.latest = hub.sent = None
            hub.exercise, hub.reps_target = body.exercise, reps or default_reps
            try:
                engine = hub.engine_factory(arm=arm, session_id=sid, patient_id=body.patient_id, simulated=sim,
                                            exercise=body.exercise, reps=reps, on_sample=hub.on_sample,
                                            on_rep=hub.on_rep, **kw)
                hub.session, hub.engine = summary, engine
                engine.start()
            except Exception as e:
                hub.engine, hub.session = None, None
                try:
                    hub.hold()
                finally:
                    with hub.db_lock:       # close the row, so no session is left "running" in the history
                        db.save_session(conn, SessionSummary(**(summary.to_dict() | {
                            "ended_at": clock.now_iso()})))
                if isinstance(e, RuntimeError):   # the engine refused (e.g. empty-handle force too high)
                    raise HTTPException(409, f"session not started: {e}")
                raise
            return {"session_id": sid, "simulated": sim, "display_name": name,
                    "exercise": body.exercise, "reps": reps}

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

    @app.post("/api/shutdown")
    def shutdown(request: Request, x_operator_token: str | None = Header(default=None)):
        """Clean exit, from this laptop only: stop the session, then let the server exit so the arm is
        put in hold and closed (nominal stiffness restored). Same end state as Ctrl+C."""
        host = request.client.host if request.client else ""
        if host not in LOCAL_CLIENTS:
            raise HTTPException(403, "shutdown is only accepted from the laptop running the server")
        guard(x_operator_token)
        request_exit = getattr(app.state, "request_exit", None)
        if request_exit is None:
            raise HTTPException(501, "this server was not started by server.run; stop it with Ctrl+C")
        s = hub.stop_session()
        request_exit()      # uvicorn leaves its loop; the lifespan then runs hub.shutdown()
        return {"ok": True, "stopped_session": None if s is None else s.session_id}

    @app.post("/api/go")
    def go(x_operator_token: str | None = Header(default=None)):
        guard(x_operator_token)
        fn = getattr(hub.engine, "go", None)
        if fn is None:
            raise HTTPException(501, "this engine has no operator cue (go)" if hub.engine is not None
                                else "no session running, so there is nothing to cue (go)")
        try:
            fn()
        except RuntimeError as e:
            raise HTTPException(409, f"go refused: {e}")
        return {"ok": True}

    @app.post("/api/session/resume")
    def resume(x_operator_token: str | None = Header(default=None)):
        """Operator: continue a session the engine has paused (engine.resume()). 409 when there is no
        session, the engine cannot resume, or it refuses."""
        guard(x_operator_token)
        if hub.engine is None:
            raise HTTPException(409, "no session running, so there is nothing to resume")
        fn = getattr(hub.engine, "resume", None)
        if fn is None:
            raise HTTPException(409, "the engine on this laptop cannot resume a session; "
                                     "stop it and start a new one")
        try:
            fn()
        except RuntimeError as e:
            raise HTTPException(409, f"not resumed: {e}")
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
            s = db.get_session(conn, session_id)
            if s is None:
                raise HTTPException(404, "unknown session")
            ex = exercises.canonical(s.exercise)
            return [r.to_dict() | {"exercise": ex} for r in db.list_reps(conn, session_id)]

    @app.get("/api/sessions/{session_id}/note", response_class=PlainTextResponse)
    def note(session_id: str):
        with hub.db_lock:
            s = db.get_session(conn, session_id)
            if s is None:
                raise HTTPException(404, "unknown session")
            earlier = [x for x in db.list_sessions(conn, s.patient_id)     # same exercise only
                       if (x.started_at, x.session_id) < (s.started_at, s.session_id)
                       and exercises.canonical(x.exercise) == exercises.canonical(s.exercise)]
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

    app.mount("/screens", StaticFiles(directory=str(SCREENS), html=True), name="screens")  # before "/" so it is not shadowed
    patient_app = REPO / "demo" / "app"          # Mat and Gio's patient app; same origin as the API, so a phone can drive the arm
    if (patient_app / "index.html").is_file():
        app.mount("/app", StaticFiles(directory=str(patient_app), html=True), name="patient_app")  # before "/" so it is not shadowed
    site = Path(site_dir) if site_dir else REPO / "demo" / "site"
    if site.is_dir() and any(site.iterdir()):
        app.mount("/", StaticFiles(directory=str(site), html=True), name="site")
    return app
