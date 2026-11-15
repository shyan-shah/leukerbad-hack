"""CheckedArm: robot.arm.Arm with a connect() that never clears faults or enables the robot.

`Arm.connect()` calls `ClearFault()` and `Enable()` unconditionally. In Auto (Remote) mode this
Rizon 4 comes up already enabled, and we never want the server to enable or un-fault it by
itself. `CheckedArm.connect()` only connects, checks and attaches; it refuses with a clear
RuntimeError unless the robot is fault-free, operational, in IDLE mode, with the e-stop
released and the expected tool selected (`tcp_pose` and the force reading depend on the tool).

Everything else (clamps, trips, watchdog, close restoring K_x_nom) is Arm's own code.
"""
from __future__ import annotations

from robot.arm import Arm, Limits, load_config

DEFAULT_TOOL = "Flange"      # nothing mounted; change when our handle is registered on the robot


class CheckedArm(Arm):
    def __init__(self, serial: str, limits: Limits = Limits(), config_path=None,
                 tool: str | None = DEFAULT_TOOL) -> None:
        super().__init__(serial, limits, config_path)
        self.expected_tool = tool

    @classmethod
    def from_config(cls, limits: Limits = Limits(), config_path=None,
                    tool: str | None = DEFAULT_TOOL) -> "CheckedArm":
        return cls(load_config(config_path).serial, limits, config_path, tool)

    def connect(self) -> None:
        """Connect, check, attach. Never ClearFault(), never Enable()."""
        if "XXXXXX" in self.serial or (self.serial == self.config.serial
                                       and self.config.is_placeholder("serial")):
            raise RuntimeError(f"serial {self.serial!r} is a placeholder; set it in robot/config.json "
                               "or pass it: python -m server.run --robot Rizon4-062157")
        import flexivrdk  # lazy: only the real arm needs the RDK

        robot = flexivrdk.Robot(self.serial)
        problems = []
        if robot.fault():
            problems.append("the robot reports a fault (clear it with robot/recover.py, see robot/RUNBOOK.md)")
        if not robot.operational():
            problems.append("the robot is not operational (not enabled, or the e-stop is pressed)")
        mode = str(robot.mode())
        if not mode.endswith("IDLE"):
            problems.append(f"the robot is in {mode}, not IDLE (another program is driving it?)")
        if not robot.estop_released():
            problems.append("the e-stop is pressed")
        if self.expected_tool is not None:
            tool = flexivrdk.Tool(robot).name()
            if tool != self.expected_tool:
                problems.append(f"the selected tool is {tool!r}, expected {self.expected_tool!r} "
                                "(a wrong tool gives a false force and a different tcp_pose)")
        if problems:
            raise RuntimeError("arm not ready: " + "; ".join(problems)
                               + ". The server never clears faults or enables the robot.")
        self._attach(robot, flexivrdk, tuple(robot.info().K_x_nom))
