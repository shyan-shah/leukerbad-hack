"""Switch the robot's selected tool (default: Flange = no tool) and check the force reading improved.

    python -m server.hw.tool_switch [Flange] [--serial Rizon4-062157]

CHANGES A ROBOT SETTING. No motion is commanded, but the payload model changes, so the arm may twitch:
keep clear, e-stop held. Needs IDLE mode. If the empty-arm force reading gets worse after the switch,
the script switches back and exits with code 4.

Why: on 14 Nov the robot was left on another team's `Seat_Assembly_tool` (1.338 kg) with nothing
mounted, which read as 12.7 N of upward force. With `Flange` it read 1.7 N.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import math  # noqa: E402
import time  # noqa: E402

from server.hw._common import connect_checked, positional  # noqa: E402


def avg_wrench(robot, secs=1.0):
    n, acc = 0, [0.0] * 6
    t_end = time.monotonic() + secs
    while time.monotonic() < t_end:
        acc = [a + float(b) for a, b in zip(acc, robot.states().ext_wrench_in_world)]
        n += 1
        time.sleep(0.01)
    return [a / n for a in acc]


def mag(w):
    return math.sqrt(sum(x * x for x in w[:3]))


def main() -> int:
    target = (positional() or ["Flange"])[0]
    robot, flexivrdk, _ = connect_checked()
    tool = flexivrdk.Tool(robot)
    before = tool.name()
    q0 = [float(x) for x in robot.states().q]
    w0 = avg_wrench(robot)
    print(f"before: tool={before} force={[round(x, 2) for x in w0[:3]]} |F|={mag(w0):.2f} N")
    if before == target:
        print("already on that tool; nothing to do")
        return 0
    if not tool.exist(target):
        print(f"ABORT: tool {target!r} does not exist. Available: {list(tool.list())}")
        return 3

    tool.Switch(target)
    time.sleep(1.5)
    after = tool.name()
    w1 = avg_wrench(robot)
    q1 = [float(x) for x in robot.states().q]
    print(f"after:  tool={after} force={[round(x, 2) for x in w1[:3]]} |F|={mag(w1):.2f} N")
    print(f"max joint change {max(abs(a - b) for a, b in zip(q0, q1)):.5f} rad; fault={robot.fault()} "
          f"mode={robot.mode()}")
    print(f"tcp_pose now: {[round(float(x), 5) for x in robot.states().tcp_pose]}  (tcp_pose depends on the tool)")
    if after != target or robot.fault() or mag(w1) >= mag(w0):
        print("RESULT: worse or failed -> switching back")
        try:
            tool.Switch(before)
            time.sleep(1.0)
            print("reverted to", tool.name())
        except Exception as e:
            print("REVERT FAILED:", repr(e))
        return 4
    print(f"RESULT: OK (|F| {mag(w0):.2f} -> {mag(w1):.2f} N)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
