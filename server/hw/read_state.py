"""READ-ONLY probe of the Flexiv arm: state, info, pose, joints, tool, three wrench samples.

    python -m server.hw.read_state [--serial Rizon4-062157] [--tries 5]

Only getters are called. Never Enable/ClearFault/SwitchMode/Stop/Send*/Set*/Execute*.
Retries the connection (20 s apart) and writes server/hw/out/read_state.json.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import json  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

from server.hw._common import option, out_dir, serial  # noqa: E402

GETTERS = [  # explicit allowlist of state getters
    "connected", "fault", "operational", "operational_status", "estop_released",
    "enabling_button_pressed", "mode", "busy", "stopped", "recovery", "reduced",
]
STATE_FIELDS = ("tcp_pose", "flange_pose", "q", "tcp_vel", "ext_wrench_in_world", "ext_wrench_in_tcp",
                "ft_sensor_raw", "tau", "tau_ext")


def val(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    try:
        return [float(x) for x in v]
    except (TypeError, ValueError):
        return str(v)


def main() -> int:
    import flexivrdk

    sn = serial()
    tries = int(option("--tries", "5"))
    robot = None
    for i in range(1, tries + 1):
        try:
            print(f"attempt {i}/{tries}: flexivrdk.Robot({sn!r})")
            robot = flexivrdk.Robot(sn)
            break
        except Exception as e:
            print("  failed:", str(e)[:300])
            if i < tries:
                time.sleep(20)
    if robot is None:
        print("NOT CONNECTED. Check: Remote Mode = Ethernet in Elements then power cycle, cable, "
              "laptop IP 192.168.2.x, firewall, serial, flexivrdk version (1.7.0 for robot software 3.9).")
        return 2

    result = {"serial_arg": sn}
    for name in GETTERS:
        if not hasattr(robot, name):
            print(f"{name}: <not in this RDK>")
            continue
        try:
            v = getattr(robot, name)()
            result[name] = v if isinstance(v, bool) else str(v)
            print(f"{name}: {v}")
        except Exception:
            print(f"{name}: ERROR")
            traceback.print_exc()

    info = robot.info()
    result["info"] = {f: val(getattr(info, f)) for f in dir(info) if not f.startswith("_")}
    for k, v in result["info"].items():
        print(f"info.{k}: {v}")

    try:
        tool = flexivrdk.Tool(robot)
        p = tool.params()
        result["tool"] = {"name": tool.name(), "list": list(tool.list()), "mass": float(p.mass),
                          "CoM": val(p.CoM), "tcp_location": val(p.tcp_location)}
        print("tool:", result["tool"])
    except Exception as e:
        print("tool: ERROR", repr(e))

    try:
        result["primitive_states"] = {k: str(v) for k, v in robot.primitive_states().items()}
        print("primitive_states:", result["primitive_states"])
    except Exception as e:
        print("primitive_states: ERROR", repr(e))

    s = robot.states()
    result["states"] = {}
    for f in STATE_FIELDS:
        try:
            result["states"][f] = val(getattr(s, f))
            print(f"states.{f}: {result['states'][f]}")
        except Exception as e:
            print(f"states.{f}: ERROR {e!r}")

    result["wrench_samples"] = []
    for i in range(3):
        if i:
            time.sleep(5)
        w = val(robot.states().ext_wrench_in_world)
        result["wrench_samples"].append(w)
        print(f"wrench sample {i + 1} (t+{5 * i}s) ext_wrench_in_world: {w}")

    path = out_dir() / "read_state.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("written:", path)
    print("config.json snippet:", json.dumps({"serial": result["info"].get("serial_num"), "start_pose": {
        "tcp_pose": [round(x, 6) for x in result["states"]["tcp_pose"]],
        "q": [round(x, 6) for x in result["states"]["q"]]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
