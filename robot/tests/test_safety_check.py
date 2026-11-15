"""Offline tests for robot/safety_check.py and robot/read_tool_force.py. No robot needed.

Run: python -m pytest robot/tests/test_safety_check.py -q
"""

import pytest

from robot import safety_check as sc
from robot.arm import Arm
from robot.read_tool_force import tool_hint
from robot.tests.test_arm_offline import FAKE_RDK, K_NOM, FakeRobot


def test_all_fifteen_checks_are_registered_in_order():
    assert [n for n, _, _ in sc.CHECKS] == list(range(1, 16))


def test_sim_dry_run_has_no_fail(tmp_path, capsys):
    pytest.importorskip("numpy")
    code = sc.main(["--sim", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out
    files = list(tmp_path.glob("safety_check_*_sim.json"))
    assert len(files) == 1
    import json
    results = {r["num"]: r for r in json.loads(files[0].read_text(encoding="utf-8"))["results"]}
    assert len(results) == 15
    # everything the sim can reproduce must pass; 11 and 15 are documented sim limits
    for num in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14):
        assert results[num]["status"] == "PASS", results[num]
    assert results[11]["status"] in ("PASS", "N/A-SIM")
    assert results[15]["status"] == "N/A-SIM"


def test_real_arm_path_with_a_fake_robot():
    """Checks 5, 6, 9, 14 (no Ctrl+C -> FAIL) and 15 through robot.arm.Arm and the Spy."""
    arm = Arm("Rizon4-TEST01")
    spy = sc.Spy(FakeRobot())
    arm._attach(spy, FAKE_RDK, K_NOM)
    rig = sc.Rig(arm, sim=False, spy=spy, k_nom=K_NOM, ask=lambda msg: "")
    results = {r["num"]: r for r in sc.run_checks(rig, only={5, 6, 9, 15}, stop_on_fail=False)}
    assert results[1]["status"] == "PASS"            # the fake reads 0 N
    for num in (5, 6, 9, 15):
        assert results[num]["status"] == "PASS", results[num]
    assert spy.k == list(K_NOM) and spy.calls[-1] == "Stop"


def test_a_fail_on_the_real_path_stops_and_closes():
    arm = Arm("Rizon4-TEST01")
    robot = FakeRobot()
    robot.wrench = [0.0, 0.0, 6.0, 0, 0, 0]          # 6 N on an empty handle: check 1 must FAIL
    spy = sc.Spy(robot)
    arm._attach(spy, FAKE_RDK, K_NOM)
    rig = sc.Rig(arm, sim=False, spy=spy, k_nom=K_NOM, ask=lambda msg: "")   # "" = do not continue
    results = sc.run_checks(rig)
    assert [r["num"] for r in results] == [1] and results[0]["status"] == "FAIL"
    assert "TOO HIGH" in results[0]["note"]
    assert spy.calls[-1] == "Stop"                    # closed, never armed
    assert not any(n == "SwitchMode" for n, _ in robot.calls)


def test_tool_hint_directions():
    assert tool_hint((0.3, -0.2, 0.9)).startswith("OK")
    assert "TOO HIGH" in tool_hint((0.0, 0.0, 12.6)) and "1284 g" in tool_hint((0.0, 0.0, 12.6))
    assert "TOO LOW" in tool_hint((0.0, 0.0, -3.0))
    assert "centre of mass" in tool_hint((2.5, 0.0, 0.2))
