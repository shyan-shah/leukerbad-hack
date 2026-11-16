"""Start the rehab station server.

  python -m server.run --mock               stand-in engine, no robot, no software/ needed (SIMULATED)
  python -m server.run --sim                Shiv's engine with the simulated arm and patient (SIMULATED)
  python -m server.run --robot [SERIAL]     Shiv's engine on the real Flexiv (serial from robot/config.json if omitted)

Options: --strength 0.2 (simulated patient), --port 8000, --lan (reachable from other devices,
control routes then need the printed operator token), --db, --no-export,
--reach-m 0.30 and --reach-sign 1|-1 (the reach line; the sign defaults to "reach_sign" in
robot/config.json, else +1), --tool Flange (--robot: the tool that must be selected on the robot),
--exercises reach (comma list offered at start-up; POST /api/exercises/enable adds more later),
--no-calibrate (every session is sent calibrate=false; the default with --robot) / --calibrate.

--robot never clears faults or enables the robot (server/hw/checked_arm.py): it refuses to
connect unless the arm is fault-free, operational, in IDLE and has the expected tool selected.

Stopping: Ctrl+C, or `curl -X POST http://127.0.0.1:8000/api/shutdown` from this laptop. Both stop
the session, put the arm in hold, then close it (nominal stiffness restored, robot stopped).
Do NOT kill the process or close its window: that leaves the soft stiffness on the robot.
"""
from __future__ import annotations

import argparse
import json
import secrets
import socket
import sys
from functools import partial
from pathlib import Path

import uvicorn

from . import db
from .api import create_app
from .export import DEFAULT_OUT


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))  # no packet is sent; just picks the outbound interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


ROBOT_CONFIG = Path(__file__).resolve().parents[1] / "robot" / "config.json"


def config_reach(path: Path | None = None) -> tuple[int, int]:
    """(reach_axis, reach_sign) from robot/config.json. Sign is +1 unless the file has "reach_sign": -1."""
    try:
        raw = json.loads(Path(path or ROBOT_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, 1
    return int(raw.get("reach_axis", 0)), (-1 if float(raw.get("reach_sign", 1)) < 0 else 1)


def reach_kwargs(a: argparse.Namespace) -> dict:
    """Engine keyword arguments for the reach line (reach_axis is taken from the arm by the API)."""
    kw = {"reach_sign": a.reach_sign if a.reach_sign is not None else config_reach()[1]}
    if a.reach_m is not None:
        kw["reach_m"] = a.reach_m
    return kw


def mock_exercises(a: argparse.Namespace) -> list[str] | None:
    """--mock: every programme the mock engine can play is offered, so the app can be built before the
    real engine has it. --sim and --robot: None, meaning software.exercises.LIVE decides."""
    if not a.mock:
        return None
    from .mock import PRESETS
    return list(PRESETS)


def no_calibrate_for(a: argparse.Namespace) -> bool:
    """True when sessions must start with calibrate=false: --no-calibrate, or --robot without --calibrate."""
    if a.calibrate is None:
        return a.robot is not None
    return not a.calibrate


def exercise_sets(a: argparse.Namespace) -> tuple[list[str] | None, list[str] | None]:
    """(what this server can run, what it offers at start-up). None, None: software.exercises.LIVE decides.

    --robot: Push at four fixed levels (push_1 .. push_4, the band engine) and nothing else.
    --robot --with-row-strength: also Row at the same levels (row_1 .. row_4) and the strength test
    (strength). Without that flag they cannot be started on the real arm, not even through --exercises:
    they have not passed their real-arm checks. The older exercises (reach, push, pull,
    armtest) are offered only when named in --exercises.
    --sim: the older exercises as before; every band-engine id can be named in --exercises.
    --mock: everything the mock can play.
    --push-only is accepted and does nothing (Push only is the default)."""
    from . import exercises as ex
    more = getattr(a, "with_row_strength", False) or a.robot is None       # no robot: nothing to protect
    band = list(ex.BAND_ENGINE_IDS) if more else list(ex.BAND_IDS)
    wanted = None
    if a.exercises is not None:
        wanted = [x.strip() for x in a.exercises.split(",") if x.strip()]
    if a.mock:
        from .mock import ALL_PRESETS
        known = list(ALL_PRESETS)          # with Row and the strength test
        live, default = known, None
    else:
        known = band + [i for i in ex.live_ids() if i not in band]
        if a.robot is not None:
            live, default = (band if wanted is None else known), None
        else:
            live, default = (None if wanted is None else known), None
    if wanted is not None:
        bad = [x for x in wanted if x not in known]
        if bad or not wanted:
            raise ValueError(f"--exercises: unknown or not runnable: {', '.join(bad) or '(empty)'}. "
                             f"Can run: {', '.join(known)}")
        return live, wanted
    return live, default


def lan_ips() -> list[str]:
    """Every IPv4 address of this laptop that is not loopback, the outbound one first. A phone reaches the
    laptop on the address of the network they share (the hotspot or Wi-Fi), not on a VPN adapter's."""
    ips = [_lan_ip()]
    try:
        ips += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    out = []
    for ip in ips:
        if ip not in out and not ip.startswith("127."):
            out.append(ip)
    return out


def build(a: argparse.Namespace):
    """Return (arm_factory, engine_factory or None, label)."""
    if a.mock:
        from .mock import MockArm, MockEngine
        return MockArm, partial(MockEngine, strength=a.strength, time_scale=a.time_scale), "MOCK (SIMULATED)"
    if a.sim:
        try:
            from software.sim_arm import SimArm
            from software.sim_patient import SimPatient
            import software.engine  # noqa: F401  (fail now, not on first session)
        except ImportError as e:
            sys.exit(f"--sim needs Shiv's software/ (sim_arm, sim_patient, engine): {e}. Use --mock meanwhile.")
        return (lambda: SimArm(SimPatient(strength=a.strength))), None, "SIM (SIMULATED)"
    from .hw.checked_arm import CheckedArm   # connect() never clears faults or enables
    try:
        import software.engine  # noqa: F401
    except ImportError as e:
        sys.exit(f"--robot needs software/engine.py: {e}")
    if a.robot:
        return (lambda: CheckedArm(a.robot, tool=a.tool)), None, "REAL ROBOT"
    return (lambda: CheckedArm.from_config(tool=a.tool)), None, "REAL ROBOT"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true")
    g.add_argument("--sim", action="store_true")
    g.add_argument("--robot", nargs="?", const="", metavar="SERIAL")
    ap.add_argument("--strength", type=float, default=0.6, help="simulated patient strength 0..1")
    ap.add_argument("--time-scale", type=float, default=1.0, help="mock only: run faster than real time")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--lan", action="store_true", help="listen on all interfaces (phones, other laptops)")
    ap.add_argument("--token", default=None, help="operator token for --lan (random if omitted)")
    ap.add_argument("--db", default=db.DEFAULT_PATH)
    ap.add_argument("--no-export", action="store_true", help="do not rewrite server/exports after sessions")
    ap.add_argument("--reach-m", type=float, default=None,
                    help="reach length in metres (default: the engine's 0.30)")
    ap.add_argument("--reach-sign", type=int, choices=(1, -1), default=None,
                    help='direction of the reach along the reach axis (default: "reach_sign" in '
                         "robot/config.json, else +1)")
    ap.add_argument("--tool", default="Flange",
                    help="--robot: tool that must be selected on the robot (default Flange = nothing mounted)")
    ap.add_argument("--with-row-strength", action="store_true",
                    help="--robot: also offer Row (row_1 .. row_4) and the strength test (strength). Off by "
                         "default: with --robot only Push (push_1 .. push_4) runs. Sim and mock only so far; "
                         "pass it for their real-arm checks")
    ap.add_argument("--push-only", action="store_true",
                    help="does nothing: Push only is already the default with --robot (kept so old commands still start)")
    ap.add_argument("--exercises", default=None, metavar="IDS",
                    help="comma list of exercise ids offered at start-up (default: all the robot can run); "
                         "enable more later with POST /api/exercises/enable")
    cal = ap.add_mutually_exclusive_group()
    cal.add_argument("--no-calibrate", dest="calibrate", action="store_false", default=None,
                     help="every session starts with calibrate=false: no comfortable-push phase, so the engine "
                          "never switches on the arm's raised test limits. THE DEFAULT WITH --robot")
    cal.add_argument("--calibrate", dest="calibrate", action="store_true", default=None,
                     help="allow the comfortable-push calibration (default with --mock and --sim). With --robot "
                          "this lets the engine raise the arm's limits during the push: only when the team agrees")
    a = ap.parse_args(argv)
    no_calibrate = no_calibrate_for(a)
    try:
        live, enabled = exercise_sets(a)
    except ValueError as e:
        ap.error(str(e))
    if a.reach_m is not None and not 0.02 <= a.reach_m <= 0.35:
        ap.error("--reach-m must be between 0.02 and 0.35 m (the workspace box is 0.35 m along the reach)")

    arm_factory, engine_factory, label = build(a)
    token = (a.token or secrets.token_urlsafe(6)) if a.lan else None
    engine_kwargs = reach_kwargs(a)
    app = create_app(arm_factory, a.db, engine_factory=engine_factory,
                     exports_dir=None if a.no_export else DEFAULT_OUT, control_token=token,
                     engine_kwargs=engine_kwargs, live_exercises=live,
                     enabled_exercises=enabled, no_calibrate=no_calibrate)
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=a.port, log_level="warning",
                                           timeout_graceful_shutdown=3))   # never wait forever on a dead client
    app.state.request_exit = lambda: setattr(server, "should_exit", True)   # used by POST /api/shutdown
    print(f"\n  Rehab station server: {label}")
    if not a.mock:
        axis = config_reach()[0] if a.robot is not None else 0
        print(f"  Reach      axis {'xyz'[axis]}, sign {engine_kwargs['reach_sign']:+d}, "
              f"length {engine_kwargs.get('reach_m', 0.30):.2f} m"
              + (f"   (tool must be {a.tool})" if a.robot is not None else ""))
    print("  Calibrate  " + ("OFF (--no-calibrate" + (", the default with --robot" if a.calibrate is None else "")
                             + "): push and pull use the preset resistance at the normal limits; "
                               "every session is sent calibrate=false"
                             if no_calibrate else
                             "on for push and pull (comfortable push)"
                             + ("; THE ENGINE RAISES THE ARM'S LIMITS DURING IT" if a.robot is not None else "")))
    if live is not None and not a.mock:
        print(f"  Exercises  can run: {', '.join(live)}"
              + (("   (Push and Row at 4 fixed levels, strength test: --with-row-strength is ON; "
                  "the older ones only with --exercises)" if a.with_row_strength else
                  "   (Push at 4 fixed levels; Row and the strength test only with --with-row-strength; "
                  "the older ones only with --exercises)") if a.exercises is None else ""))
        if a.robot is not None and a.with_row_strength:
            print("  NOTE       Row and the strength test have NOT passed their real-arm checks. "
                  "Tester only, hands off whenever the screen says the arm is moving.")
    if enabled is not None:
        print(f"  Exercises enabled now: {', '.join(enabled)}   (more: POST /api/exercises/enable)")
    print(f"  API        http://127.0.0.1:{a.port}/api/health")
    print(f"  Live feed  ws://127.0.0.1:{a.port}/ws/live    (terminal view: python -m server.watch)")
    if a.lan:
        print(f"  On the LAN http://{_lan_ip()}:{a.port}   operator token for control routes: {token}")
        print(f"  On this laptop: http://127.0.0.1:{a.port}/app/?op={token}")
        print(f"  Patient app (phone on the same network; this link carries the operator token, do not share it):")
        for ip in lan_ips() or ["127.0.0.1"]:      # one per network adapter: use the one the phone is on
            print(f"             http://{ip}:{a.port}/app/?op={token}")
    else:
        print(f"  Patient app http://127.0.0.1:{a.port}/app/")
    print(f"  Stop       Ctrl+C here, or: curl -X POST http://127.0.0.1:{a.port}/api/shutdown")
    print("  Both hold then close the arm. Never kill this process or close the window.\n", flush=True)
    try:
        server.run()
    finally:
        app.state.hub.shutdown()   # idempotent; covers crashes outside the lifespan


if __name__ == "__main__":
    main()
