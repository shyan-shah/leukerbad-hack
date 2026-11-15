"""Offline tests for robot/test_limits_stage.py. No robot needed.

Run: python -m pytest robot/tests/test_limits_stage.py -q
"""

import json
import sys
import time
from types import SimpleNamespace

import pytest

from robot import test_limits_stage as tl
from robot.tests.test_arm_offline import K_NOM, FakeRobot

DEFAULT_CONTACT = [30.0, 30.0, 30.0, 5.0, 5.0, 5.0]


def _result(tmp_path):
    files = list(tmp_path.glob("test_limits_*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- dry run on SimArm

@pytest.mark.parametrize("stage", ["a", "b", "c", "d"])
def test_sim_stage_passes(stage, tmp_path, capsys):
    pytest.importorskip("numpy")
    code = tl.main(["--stage", stage, "--sim", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert f"RESULT STAGE {stage}: PASS" in out and "SIMULATED" in out
    r = _result(tmp_path)
    assert r["sim"] and r["restored"] and r["stopped"] is None and r["tripped"] is None


@pytest.mark.parametrize("stage,push,word", [("d", 70.0, "65 N ceiling"), ("b", 30.0, "25 N ceiling")])
def test_sim_push_over_the_stage_ceiling_stops_the_arm(stage, push, word, tmp_path, capsys):
    pytest.importorskip("numpy")
    code = tl.main(["--stage", stage, "--sim", "--sim-push", str(push), "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1 and f"RESULT STAGE {stage}: FAIL" in out
    r = _result(tmp_path)
    assert word in r["stopped"] and r["restored"]


def test_without_go_nothing_is_connected(capsys):
    assert tl.main(["--stage", "a"]) == 2
    assert "flexivrdk" not in sys.modules
    assert "Nothing was connected" in capsys.readouterr().out


# --------------------------------------------------------------------------- the real-arm path on a fake RDK

class FakeLiveRobot(FakeRobot):
    """FakeRobot plus what the script reads. `push_n` is applied along world -x (the reach direction in
    robot/config.json) from 0.2 s to 0.6 s after the 1500 N/m stiffness is first sent."""

    def __init__(self, push_n=0.0, mode="Mode.IDLE", fault_at_push=False):
        super().__init__()
        self.push_n, self._mode, self.fault_at_push = push_n, mode, fault_at_push
        self.t_stiff = None

    def SetCartesianImpedance(self, k, *a):
        self.calls.append(("SetCartesianImpedance", (list(k),)))
        if k[0] == tl.TEST_K_MAX and self.t_stiff is None:
            self.t_stiff = time.monotonic()

    def _pushing(self):
        return self.t_stiff is not None and 0.2 <= time.monotonic() - self.t_stiff <= 0.6

    def states(self):
        s = super().states()
        s.ext_wrench_in_world = [-self.push_n if self._pushing() else 0.0, 0, 0, 0, 0, 0]
        s.tau = [1.0, 20.0, 3.0, 10.0, 1.0, 2.0, 0.5]
        return s

    def fault(self):
        return self.is_fault or (self.fault_at_push and self._pushing())

    def operational(self):
        return True

    def mode(self):
        return self._mode

    def estop_released(self):
        return True

    def info(self):
        return SimpleNamespace(K_x_nom=list(K_NOM), tau_max=[123.0, 123.0, 64.0, 64.0, 39.0, 39.0, 39.0])

    def primitive_states(self):
        return {"terminated": True}


def _run_real(monkeypatch, tmp_path, robot, stage):
    fake = SimpleNamespace(Robot=lambda serial: robot, Tool=lambda r: SimpleNamespace(name=lambda: "RehabHandle"),
                           Mode=SimpleNamespace(NRT_CARTESIAN_MOTION_FORCE="cart", NRT_PRIMITIVE_EXECUTION="prim"))
    monkeypatch.setitem(sys.modules, "flexivrdk", fake)
    monkeypatch.setattr(tl, "COUNTDOWN_S", 0)
    monkeypatch.setattr(tl, "RESTORE_WAIT_S", 0)
    monkeypatch.setattr(tl, "SWITCH_S", 0.15)
    monkeypatch.setattr(tl, "SETTLE_S", 0.1)
    monkeypatch.setitem(tl.STAGES, stage, dict(tl.STAGES[stage], push_s=0.7 if tl.STAGES[stage]["push_s"] else 0.0))
    return tl.main(["--stage", stage, "--go", "--out", str(tmp_path)])


def _assert_restored(robot):
    assert robot.last("SetCartesianImpedance")[0] == list(K_NOM)
    assert robot.last("SetMaxContactWrench")[0] == DEFAULT_CONTACT
    assert robot.calls[-1][0] == "Stop"
    assert robot.count("Enable") == 0 and robot.count("ClearFault") == 0


def test_refuses_when_the_robot_is_not_idle(monkeypatch, tmp_path):
    robot = FakeLiveRobot(mode="Mode.NRT_CARTESIAN_MOTION_FORCE")
    with pytest.raises(SystemExit, match="REFUSED.*not IDLE"):
        _run_real(monkeypatch, tmp_path, robot, "a")
    assert robot.calls == []


def test_refuses_a_faulted_robot(monkeypatch, tmp_path):
    robot = FakeLiveRobot()
    robot.is_fault = True
    with pytest.raises(SystemExit, match="REFUSED.*fault"):
        _run_real(monkeypatch, tmp_path, robot, "a")
    assert robot.calls == []


def test_stage_a_switches_three_times_and_restores(monkeypatch, tmp_path, capsys):
    robot = FakeLiveRobot()
    code = _run_real(monkeypatch, tmp_path, robot, "a")
    out = capsys.readouterr().out
    assert code == 0, out
    contact = [a[0][0] for n, a in robot.calls if n == "SetMaxContactWrench"]
    assert contact.count(65.0) == 3 and contact[-1] == 30.0
    assert robot.calls[0] == ("SwitchMode", ("prim",)) and robot.calls[1][0] == "ExecutePrimitive"   # zero first
    assert "J2:   20.0 of  123.0 Nm" in out
    _assert_restored(robot)


def test_stage_b_reads_the_push_and_restores(monkeypatch, tmp_path, capsys):
    robot = FakeLiveRobot(push_n=12.0)
    code = _run_real(monkeypatch, tmp_path, robot, "b")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "peak force along the reach: 12.0 N (in the reach direction)" in out
    _assert_restored(robot)


def test_stage_d_stops_at_65_n_then_restores(monkeypatch, tmp_path, capsys):
    robot = FakeLiveRobot(push_n=70.0)
    code = _run_real(monkeypatch, tmp_path, robot, "d")
    out = capsys.readouterr().out
    assert code == 1 and "STOPPED THE ROBOT: force reading 70.0 N" in out
    names = [n for n, _ in robot.calls]
    first_stop = names.index("Stop")
    assert "SendCartesianMotionForce" in names[first_stop:]      # re-entered Cartesian mode only to restore
    assert _result(tmp_path)["restored"] is True
    _assert_restored(robot)


def test_robot_fault_mid_stage_stops_and_reports_not_restored(monkeypatch, tmp_path, capsys):
    robot = FakeLiveRobot(push_n=12.0, fault_at_push=True)
    robot_fault = robot.fault
    robot.fault = lambda: robot_fault() or robot.count("Stop") > 0     # the fault stays until someone clears it
    code = _run_real(monkeypatch, tmp_path, robot, "b")
    out = capsys.readouterr().out
    assert code == 1 and "robot fault" in out and "could NOT be sent" in out
    assert robot.count("Stop") >= 1 and robot.count("ClearFault") == 0
    assert _result(tmp_path)["restored"] is False


def test_error_in_the_stage_still_restores(monkeypatch, tmp_path, capsys):
    robot = FakeLiveRobot(push_n=12.0)
    monkeypatch.setattr(tl, "stage_push", lambda run: (_ for _ in ()).throw(RuntimeError("boom")))
    code = _run_real(monkeypatch, tmp_path, robot, "b")
    out = capsys.readouterr().out
    assert code == 1 and "boom" in out
    _assert_restored(robot)


def test_ctrl_c_holds_and_restores(monkeypatch, tmp_path, capsys):
    robot = FakeLiveRobot(push_n=12.0)
    monkeypatch.setattr(tl, "stage_push", lambda run: (_ for _ in ()).throw(KeyboardInterrupt()))
    code = _run_real(monkeypatch, tmp_path, robot, "b")
    assert code == 1 and "Ctrl+C" in capsys.readouterr().out
    _assert_restored(robot)


def test_the_3_cm_check_ignores_the_release():
    """Real arm, 15 Nov, stage d: after a sudden let-go the force was under 40 N with the handle still 31 mm out."""
    def row(along, disp_mm):
        return dict(along=along, f=abs(along), disp=disp_mm / 1000.0)
    rise = [row(f, f / 1.5) for f in (5, 20, 39, 53)]            # 39 N -> 26 mm
    hold = [row(52, 35), row(50, 34), row(53, 35)]
    release = [row(30, 31), row(5, 20), row(0, 2)]               # force gone, handle still coming back
    assert tl.loaded_disp_le40(rise + hold + release) == pytest.approx(0.026)
    assert tl.loaded_disp_le40(rise + hold) == pytest.approx(0.026)
    # a handle that really gives too far under 40 N on the way up is still caught
    assert tl.loaded_disp_le40([row(38, 33), row(53, 36)] + release) == pytest.approx(0.033)
    assert tl.loaded_disp_le40([]) == 0.0


def test_recheck_of_a_saved_run(tmp_path, capsys):
    pytest.importorskip("numpy")
    assert tl.main(["--stage", "d", "--sim", "--out", str(tmp_path)]) == 0
    f = next(tmp_path.glob("test_limits_d_*.json"))
    before = f.read_text(encoding="utf-8")
    capsys.readouterr()
    assert tl.main(["--recheck", str(f)]) == 0
    assert "RECHECK STAGE d: PASS" in capsys.readouterr().out
    r = json.loads(before)
    r["stopped"] = "force reading 66.0 N"          # a run the script had to stop is never turned into a PASS
    g = tmp_path / "stopped.json"
    g.write_text(json.dumps(r), encoding="utf-8")
    assert tl.main(["--recheck", str(g)]) == 1
    assert f.read_text(encoding="utf-8") == before
