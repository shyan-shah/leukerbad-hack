"""Recover the Flexiv Rizon 4 after a fault, a trip or a crashed program (package K5).

What it does, in order:
  1. connects to the robot (nobody may be holding the handle),
  2. prints the fault and enable state,
  3. ClearFault() if the robot is faulted,
  4. Enable() and waits for operational(),
  5. restores nominal Cartesian stiffness (robot.info().K_x_nom). Stiffness set by
     SetCartesianImpedance stays on the robot after a program ends, so a crash while
     an axis was at 0 N/m leaves that axis floppy for the next program,
  6. Stop() so the robot ends in IDLE, enabled, at nominal stiffness.

Usage (from the repo root, arm laptop, pinned flexivrdk 1.7.x installed):
  python robot/recover.py --check                 # status only, changes nothing
  python robot/recover.py                         # full recovery, asks for confirmation
  python robot/recover.py --serial Rizon4-XXXXXX  # override the serial from robot/config.json

Exit codes: 0 ready, 1 setup problem (no RDK, no serial, cannot connect),
2 fault will not clear, 3 will not become operational, 4 stiffness restore failed.

This file only talks to the robot through flexivrdk. It imports nothing from software/ or server/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")
OPERATIONAL_TIMEOUT_S = 20.0  # TODO(confirm on arm): how long Enable() takes to reach operational
POLL_S = 0.2


def load_serial(cli_serial: str | None) -> str:
    """Serial from --serial, else from robot/config.json (written by K1/K4)."""
    if cli_serial:
        return cli_serial
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"[recover] cannot read {CONFIG_PATH}: {exc}") from None
        serial = cfg.get("serial")  # same key robot/arm.py uses; "Rizon4-XXXXXX" is the placeholder
        if serial and "XXXX" not in serial:
            return serial
    raise SystemExit(
        "[recover] no robot serial. Pass --serial Rizon4-XXXXXX or set \"serial\" in robot/config.json."
    )


def import_rdk():
    """Lazy import so --help works on any laptop."""
    try:
        import flexivrdk  # noqa: PLC0415
    except ImportError:
        raise SystemExit(
            "[recover] flexivrdk is not installed. Run: pip install -r robot/requirements.txt\n"
            "          (pinned 1.7.x. Never a plain 'pip install flexivrdk': 2.x is the wrong robot family.)"
        ) from None
    return flexivrdk


def _fmt(values) -> str:
    return "[" + ", ".join(f"{float(v):.3f}" for v in values) + "]"


def _call(robot, name: str):
    """Call an optional zero-argument RDK getter; return '<n/a>' if this RDK version lacks it."""
    fn = getattr(robot, name, None)
    if not callable(fn):
        return "<n/a>"
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001  (status printing must never crash recovery)
        return f"<error: {exc}>"


def print_status(robot, label: str) -> None:
    print(f"\n--- {label} ---")
    # All of these getters exist in flexivrdk 1.7.0 (checked 14 Nov, docs/BRINGUP_FINDINGS.md section 5).
    for name in ("connected", "fault", "operational", "estop_released", "enabling_button_pressed", "busy", "mode"):
        print(f"  {name:<24} {_call(robot, name)}")
    try:
        st = robot.states()
        print(f"  {'tcp_pose':<24} {_fmt(st.tcp_pose)}")
        print(f"  {'ext_wrench_in_world':<24} {_fmt(st.ext_wrench_in_world)}")
        print(f"  {'q':<24} {_fmt(st.q)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  states()                 <unavailable: {exc}>")


def confirm_safe(assume_yes: bool) -> None:
    print(
        "[recover] Before continuing:\n"
        "  - NOBODY is touching the arm or the handle.\n"
        "  - The e-stop holder is at the e-stop with a hand on it.\n"
        "  - The workspace is clear.\n"
        "  The arm will be enabled and briefly switched to Cartesian mode to restore stiffness.\n"
    )
    if assume_yes:
        print("[recover] --yes given, skipping the prompt.")
        return
    answer = input("Type 'yes' to continue: ").strip().lower()
    if answer != "yes":
        raise SystemExit("[recover] aborted by operator. Nothing changed.")


def clear_fault(robot) -> bool:
    if not robot.fault():
        print("[recover] no fault.")
        return True
    print("[recover] robot is faulted, calling ClearFault() ...")
    # flexivrdk 1.7.0: ClearFault(timeout_sec=30) -> bool (signature checked; not yet called on this arm).
    result = robot.ClearFault()
    if result is False or robot.fault():
        print(
            "[recover] FAULT DID NOT CLEAR. Usually a hardware or safety fault (e-stop pressed, "
            "collision, joint limit). Release the e-stop, read the fault in Flexiv Elements, then see "
            "robot/RUNBOOK.md section 'Faults'. A power cycle may be needed."
        )
        return False
    print("[recover] fault cleared.")
    return True


def enable(robot) -> bool:
    if robot.operational():
        print("[recover] already operational.")
        return True
    print("[recover] Enable() ...")
    robot.Enable()
    deadline = time.monotonic() + OPERATIONAL_TIMEOUT_S
    while time.monotonic() < deadline:
        if robot.operational():
            print("[recover] operational.")
            return True
        if robot.fault():
            print("[recover] robot faulted again while enabling.")
            return False
        time.sleep(POLL_S)
    print(
        f"[recover] NOT OPERATIONAL after {OPERATIONAL_TIMEOUT_S:.0f} s. Check: e-stop released, "
        "robot in Remote mode over Ethernet in Elements, no fault shown in Elements, brakes released."
    )
    return False


def restore_nominal_stiffness(robot, flexivrdk) -> bool:
    k_nom = list(robot.info().K_x_nom)
    print(f"[recover] K_x_nom = {_fmt(k_nom)}")
    try:
        # SetCartesianImpedance only applies in a Cartesian mode, so switch, set, then Stop().
        # TODO(confirm on arm): on SwitchMode the robot holds its current pose (no jump) until a command arrives.
        robot.SwitchMode(flexivrdk.Mode.NRT_CARTESIAN_MOTION_FORCE)
        robot.SetCartesianImpedance(k_nom)
        # TODO(confirm on arm): nominal stiffness persists after Stop() and into the next program.
        robot.Stop()
    except Exception as exc:  # noqa: BLE001
        print(f"[recover] STIFFNESS RESTORE FAILED: {exc}")
        _safe_stop(robot)
        return False
    print("[recover] nominal stiffness restored, robot stopped (IDLE).")
    return True


def _safe_stop(robot) -> None:
    try:
        robot.Stop()
    except Exception as exc:  # noqa: BLE001
        print(f"[recover] Stop() also failed: {exc}. Use the e-stop if the arm is moving.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clear fault, re-enable and restore nominal stiffness on the Rizon 4.")
    parser.add_argument("--serial", help="robot serial, e.g. Rizon4-XXXXXX (default: robot/config.json)")
    parser.add_argument("--check", action="store_true", help="print status only, change nothing")
    parser.add_argument("--yes", action="store_true", help="skip the safety confirmation prompt")
    parser.add_argument("--skip-stiffness", action="store_true", help="clear fault and enable only")
    args = parser.parse_args(argv)

    serial = load_serial(args.serial)
    flexivrdk = import_rdk()

    print(f"[recover] connecting to {serial} ...")
    try:
        robot = flexivrdk.Robot(serial)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[recover] CANNOT CONNECT: {exc}\n"
            "  Check: Ethernet cable, laptop IP 192.168.2.x / 255.255.255.0 / no gateway, Python allowed "
            "through the Windows firewall, robot in Remote mode, RDK licence, serial string exact."
        )
        return 1

    print_status(robot, "status before")
    if args.check:
        return 0

    confirm_safe(args.yes)
    try:
        if not clear_fault(robot):
            return 2
        if not enable(robot):
            return 3
        if not args.skip_stiffness and not restore_nominal_stiffness(robot, flexivrdk):
            return 4
    except KeyboardInterrupt:
        print("\n[recover] Ctrl+C, stopping robot.")
        _safe_stop(robot)
        return 130
    except Exception:
        _safe_stop(robot)
        raise

    print_status(robot, "status after")
    print(f"\n[recover] READY. Next: python -m server.run --robot {serial}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
