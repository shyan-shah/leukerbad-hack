"""Shared helpers for the hardware scripts in server/hw/ (Flexiv Rizon 4, flexivrdk 1.7.0).

Nothing here calls Enable() or ClearFault(). `connect_checked` refuses to go on unless the robot
is already fault-free, operational and in IDLE mode.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "robot" / "config.json"
OUT = Path(__file__).resolve().parent / "out"      # run logs (git-ignored)


def out_dir() -> Path:
    OUT.mkdir(exist_ok=True)
    return OUT


def flag(name: str, argv: list[str] | None = None) -> bool:
    return name in (sys.argv[1:] if argv is None else argv)


def option(name: str, default: str | None = None, argv: list[str] | None = None) -> str | None:
    """Value of `--name value` or `--name=value`, else default."""
    args = sys.argv[1:] if argv is None else argv
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def positional(argv: list[str] | None = None) -> list[str]:
    """Arguments that are not options (skips the value after --serial / --seconds / --scale)."""
    args = sys.argv[1:] if argv is None else argv
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in ("--serial", "--seconds", "--scale", "--tries", "--axis"):
            skip = True
        elif not a.startswith("--"):
            out.append(a)
    return out


def serial() -> str:
    """Robot serial: `--serial Rizon4-NNNNNN` if given, else robot/config.json."""
    s = option("--serial")
    if s:
        return s
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    s = str(cfg["serial"])
    if "XXXXXX" in s or "serial" in cfg.get("placeholders", []):
        sys.exit(f"robot/config.json still has the placeholder serial {s!r}. Set it there (Kian's file) "
                 "or pass --serial Rizon4-062157.")
    return s


def connect_checked(require_tool: str | None = None):
    """Connect and check preconditions for anything that commands the arm.

    Returns (robot, flexivrdk, K_x_nom). Exits with code 3 unless: no fault, operational, mode IDLE,
    e-stop released, and (if given) the selected tool is `require_tool`.
    """
    import flexivrdk  # lazy: only needed on the arm laptop

    robot = flexivrdk.Robot(serial())
    pre = dict(fault=bool(robot.fault()), operational=bool(robot.operational()), mode=str(robot.mode()),
               estop_released=bool(robot.estop_released()), tool=flexivrdk.Tool(robot).name())
    print("preconditions:", pre)
    if pre["fault"] or not pre["operational"] or pre["mode"] != "Mode.IDLE" or not pre["estop_released"]:
        print("ABORT: need no fault, operational, mode IDLE and e-stop released. "
              "These scripts never clear faults or enable the robot; see robot/RUNBOOK.md.")
        sys.exit(3)
    if require_tool is not None and pre["tool"] != require_tool:
        print(f"ABORT: selected tool is {pre['tool']!r}, expected {require_tool!r} "
              "(a wrong tool mass makes the arm drift at low stiffness). See tool_switch.py.")
        sys.exit(3)
    return robot, flexivrdk, [float(v) for v in robot.info().K_x_nom]


def attach_arm(limits, robot, flexivrdk, k_nom):
    """robot.arm.Arm wired to an already-connected robot.

    Uses Arm._attach instead of Arm.connect(), because connect() calls ClearFault() and Enable().
    Force sign and reach axis come from robot/config.json.
    """
    sys.path.insert(0, str(REPO))
    from robot.arm import Arm

    arm = Arm(serial(), limits)          # config: robot/config.json
    arm._attach(robot, flexivrdk, k_nom)
    return arm


def sim_arm(limits, start_pos=(0.78, 0.40, 0.44)):
    """Shiv's simulated arm with a limp patient, for dry runs with --sim (no robot needed)."""
    sys.path.insert(0, str(REPO))
    from software.sim_arm import SimArm
    from software.sim_patient import SimPatient

    arm = SimArm(SimPatient(strength=0.0), limits, start_pos=start_pos, realtime=True)
    arm.connect()
    return arm
