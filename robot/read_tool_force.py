"""Print the active tool and three empty-handle force readings. READ-ONLY (package K0/K4).

    python robot/read_tool_force.py [--serial Rizon4-062157] [--samples 3] [--gap 2.0]

Only calls getters: it never enables, clears faults, switches mode, changes the tool or
moves the arm. It still opens an RDK connection, so the one-laptop-at-a-time rule applies.
Nobody may touch the arm or the handle while it reads.

Why it matters: this Rizon 4 has no wrist force/torque sensor. The force we read
(`states().ext_wrench_in_world`) is estimated from the joint torques minus the robot's
model of itself and of the tool. If the tool's mass or centre of mass in Elements is wrong,
the error shows up as a false force on an empty handle. Target: under about 2 N
(the engine refuses to start above 3 N).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")
G = 9.81
EMPTY_FORCE_OK_N = 2.0


def tool_hint(raw_xyz) -> str:
    """Say which way the tool's mass / CoM is off, from the raw world-frame empty reading (N).

    Raw means ext_wrench_in_world as the robot reports it (before arm.py's force_sign).
    Base z is up. On 14 Nov a 1.34 kg tool that was selected but not mounted read +12.6 N in z,
    so a POSITIVE z reading means the mass in Elements is TOO HIGH.
    """
    fx, fy, fz = (float(v) for v in raw_xyz)
    mag = math.sqrt(fx * fx + fy * fy + fz * fz)
    horiz = math.hypot(fx, fy)
    if mag < EMPTY_FORCE_OK_N:
        return f"OK: empty force {mag:.2f} N is under {EMPTY_FORCE_OK_N:.0f} N."
    parts = [f"Empty force {mag:.2f} N is over {EMPTY_FORCE_OK_N:.0f} N."]
    if abs(fz) >= 1.0:
        grams = abs(fz) / G * 1000.0
        if fz > 0:
            parts.append(f"z reads +{fz:.2f} N (up): the tool mass in Elements is about {grams:.0f} g "
                         "TOO HIGH. Lower it by that much (re-weigh the handle with its screws).")
        else:
            parts.append(f"z reads {fz:.2f} N (down): the tool mass in Elements is about {grams:.0f} g "
                         "TOO LOW. Raise it by that much (did the weight include the plate and screws?).")
    if horiz >= 1.0:
        parts.append(f"Horizontal reading {horiz:.2f} N (x {fx:+.2f}, y {fy:+.2f}): gravity cannot cause "
                     "that directly, so the centre of mass is probably wrong. Check the CoM is measured "
                     "from the flange face along the flange axes and in METRES (30 mm = 0.030), "
                     "and check the sign of each component.")
    if abs(fz) < 1.0 and horiz < 1.0:
        parts.append("No single axis stands out: read again in a second pose. A reading that changes "
                     "with the pose means the CoM is off; one that stays the same means the mass is off.")
    return " ".join(parts)


def _serial(cli: str | None) -> str:
    if cli:
        return cli
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    s = str(cfg.get("serial", ""))
    if not s or "XXXX" in s:
        raise SystemExit("[read_tool_force] robot/config.json still has the placeholder serial. "
                         "Pass --serial Rizon4-062157.")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only: active tool and empty-handle force readings.")
    ap.add_argument("--serial", help="robot serial (default: robot/config.json)")
    ap.add_argument("--samples", type=int, default=3, help="number of readings (default 3)")
    ap.add_argument("--gap", type=float, default=2.0, help="seconds between readings (default 2)")
    args = ap.parse_args(argv)
    serial = _serial(args.serial)

    try:
        import flexivrdk
    except ImportError:
        raise SystemExit("[read_tool_force] flexivrdk is not installed in this Python. Use the arm venv "
                         "(flexivrdk==1.7.0), e.g. C:\\venvs\\flexiv17\\Scripts\\python.exe.") from None

    print(f"[read_tool_force] connecting to {serial} (read-only; nobody touches the arm) ...")
    robot = flexivrdk.Robot(serial)
    print(f"  fault {robot.fault()}   operational {robot.operational()}   mode {robot.mode()}")

    tool = flexivrdk.Tool(robot)
    name = tool.name()
    print(f"  active tool: {name!r}")
    try:
        p = tool.params()
        print(f"    mass {float(p.mass):.3f} kg   CoM {[round(float(v), 4) for v in p.CoM]} m (from the flange)")
        print(f"    tcp_location {[round(float(v), 4) for v in p.tcp_location]}  (x y z m, qw qx qy qz)")
    except Exception as exc:  # noqa: BLE001  (params are nice to have; the force reading is the point)
        print(f"    tool params unavailable: {exc}")
    try:
        print(f"  tools on the robot: {list(tool.list())}")
    except Exception:  # noqa: BLE001
        pass

    readings = []
    for i in range(max(1, args.samples)):
        if i:
            time.sleep(max(0.0, args.gap))
        s = robot.states()
        w = [float(v) for v in s.ext_wrench_in_world]
        mag = math.sqrt(sum(v * v for v in w[:3]))
        readings.append(w)
        print(f"  reading {i + 1}: Fx {w[0]:+7.3f}  Fy {w[1]:+7.3f}  Fz {w[2]:+7.3f} N   |F| {mag:6.3f} N   "
              f"M {[round(v, 3) for v in w[3:]]} Nm")
    s = robot.states()
    print(f"  tcp_pose {[round(float(v), 5) for v in s.tcp_pose]}")
    print(f"  q        {[round(float(v), 5) for v in s.q]}")

    mean = [sum(r[i] for r in readings) / len(readings) for i in range(3)]
    mag = math.sqrt(sum(v * v for v in mean))
    print(f"\n  mean empty force: x {mean[0]:+.2f}  y {mean[1]:+.2f}  z {mean[2]:+.2f} N   |F| {mag:.2f} N")
    print("  " + tool_hint(mean))
    if name == "Flange":
        print("  NOTE: the active tool is 'Flange' (no tool). If the handle is mounted, create and select "
              "'RehabHandle' first (robot/tool_handle.md).")
    return 0 if mag < EMPTY_FORCE_OK_N else 2


if __name__ == "__main__":
    sys.exit(main())
