"""Offline check of the installed flexivrdk against the calls robot/arm.py and robot/recover.py make.

    python -m server.hw.api_check

No robot connection. Prints the signature (first docstring line) of every RDK call we use and the
field lists of RobotStates, RobotInfo, Tool and ToolParams, and flags anything missing.
Known result for flexivrdk 1.7.0: everything exists; SendCartesianMotionForce takes
(pose, wrench, max_linear_vel, max_angular_vel, max_linear_acc, max_angular_acc), with no `velocity`
argument (that one is 1.9 only).
"""
import sys

ROBOT_CALLS = ["__init__", "fault", "ClearFault", "Enable", "operational", "SwitchMode",
               "SendCartesianMotionForce", "SetCartesianImpedance", "SetMaxContactWrench",
               "ExecutePrimitive", "primitive_states", "states", "info", "Stop", "mode",
               "connected", "estop_released", "operational_status"]
MODES = ["NRT_CARTESIAN_MOTION_FORCE", "NRT_PRIMITIVE_EXECUTION", "IDLE"]
STATE_FIELDS = ["tcp_pose", "tcp_vel", "ext_wrench_in_world", "q"]
INFO_FIELDS = ["K_x_nom", "license_type", "software_ver", "serial_num"]


def first_line(obj, name: str) -> str:
    if not hasattr(obj, name):
        return "MISSING"
    doc = (getattr(obj, name).__doc__ or "").strip().splitlines()
    return doc[0] if doc else "(no docstring)"


def main() -> int:
    try:
        import flexivrdk as f
    except ImportError as e:
        print(f"flexivrdk is not installed in this Python: {e}\nUse C:\\venvs\\flexiv17 (flexivrdk==1.7.0 + numpy).")
        return 2
    print("module:", f.__file__)
    missing = []
    for n in ROBOT_CALLS:
        line = first_line(f.Robot, n)
        print(f"Robot.{n}: {line}")
        if line == "MISSING":
            missing.append(f"Robot.{n}")
    for m in MODES:
        ok = hasattr(f.Mode, m)
        print(f"Mode.{m}: {'ok' if ok else 'MISSING'}")
        if not ok:
            missing.append(f"Mode.{m}")
    for cls, wanted in (("RobotStates", STATE_FIELDS), ("RobotInfo", INFO_FIELDS),
                        ("Tool", ["Add", "Switch", "name", "list", "params"]),
                        ("ToolParams", ["mass", "CoM"])):
        c = getattr(f, cls, None)
        fields = [m for m in dir(c) if not m.startswith("_")] if c else []
        print(f"{cls}: {fields if c else 'MISSING'}")
        missing += [f"{cls}.{w}" for w in wanted if w not in fields]
    sig = first_line(f.Robot, "SendCartesianMotionForce")
    print("\nSendCartesianMotionForce has a `velocity` argument:", "velocity:" in sig,
          "(arm.py passes 6 positional arguments, which is right when this is False)")
    print("MISSING:", missing or "nothing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
