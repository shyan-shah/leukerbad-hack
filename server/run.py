"""Start the rehab station server.

  python -m server.run --mock               stand-in engine, no robot, no software/ needed (SIMULATED)
  python -m server.run --sim                Shiv's engine with the simulated arm and patient (SIMULATED)
  python -m server.run --robot [SERIAL]     Shiv's engine on the real Flexiv (serial from robot/config.json if omitted)

Options: --strength 0.2 (simulated patient), --port 8000, --lan (reachable from other devices,
control routes then need the printed operator token), --db, --no-export.
Ctrl+C or any crash: the arm is put in hold, then closed.
"""
from __future__ import annotations

import argparse
import secrets
import socket
import sys
from functools import partial

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
    from robot.arm import Arm
    try:
        import software.engine  # noqa: F401
    except ImportError as e:
        sys.exit(f"--robot needs software/engine.py: {e}")
    return ((lambda: Arm(a.robot)) if a.robot else Arm.from_config), None, "REAL ROBOT"


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
    a = ap.parse_args(argv)

    arm_factory, engine_factory, label = build(a)
    token = (a.token or secrets.token_urlsafe(6)) if a.lan else None
    app = create_app(arm_factory, a.db, engine_factory=engine_factory,
                     exports_dir=None if a.no_export else DEFAULT_OUT, control_token=token)
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    print(f"\n  Rehab station server: {label}")
    print(f"  API        http://127.0.0.1:{a.port}/api/health")
    print(f"  Live feed  ws://127.0.0.1:{a.port}/ws/live    (terminal view: python -m server.watch)")
    if a.lan:
        print(f"  On the LAN http://{_lan_ip()}:{a.port}   operator token for control routes: {token}")
    print("  Ctrl+C holds then closes the arm.\n", flush=True)
    try:
        uvicorn.run(app, host=host, port=a.port, log_level="warning")
    finally:
        app.state.hub.shutdown()   # idempotent; covers crashes outside the lifespan


if __name__ == "__main__":
    main()
