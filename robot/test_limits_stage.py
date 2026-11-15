"""Staged on-arm test of Arm.set_test_limits (the 1500 N/m, 65 N contact, 75 N trip profile).
A PERSON PUSHES THE HANDLE in stages b, c and d. E-stop holder in place for every stage.

    python -u -m robot.test_limits_stage --stage a --go      real arm (serial, reach axis and sign from robot/config.json)
    python -u -m robot.test_limits_stage --stage a --sim     dry run on software.sim_arm.SimArm, no robot
    python -u -m robot.test_limits_stage --stage a           prints the plan only, connects to nothing

One stage per run, in order, each only after the one before it printed PASS:
  a  nobody touching: the profile is switched on (stiffness to 1500 N/m) and off 3 times, 3 s each.
     The handle must not jump more than 2 mm at any switch.
  b  gentle push along the reach, about 10 N, held 5 s.
  c  push of 30 to 40 N: the reading must pass 30 N, the handle must give under 3 cm.
  d  push towards 60 N: the reading must pass 50 N; under 3 cm for readings up to 40 N.
     The script stops the robot at 65 N.

There are no Enter prompts: the script counts down and prints PUSH NOW / EASE OFF, so it can be
started from another program. Ctrl+C at any time: hold, restore, Stop.

What it does, in order: refuses unless the robot is fault-free, operational, in IDLE with the e-stop
released; never Enable(), never ClearFault(), never home(); ZeroFTSensor with nobody touching;
start_compliance() at the pose the arm is in; the stage; then ALWAYS (normal end, FAIL, Ctrl+C or
error) the default limits and K_x_nom are sent again and the robot is stopped.

Stop() at once, whatever the stage: a robot fault, handle speed over 0.25 m/s, handle more than 5 cm
from where it started, or a force reading over the stage's ceiling (a 10 N, b 25 N, c 50 N, d 65 N).
After such a stop the script waits 3 s, re-enters Cartesian mode for a moment at the pose the arm is
in to send the default contact limit and K_x_nom, then stops again. With a robot fault it cannot do
that and says so.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from robot.arm import (CONFIG_PATH, TEST_K_MAX, TEST_MAX_CONTACT_N, TEST_TRIP_FORCE, Arm, Limits,
                       limits_for_reach_axis, load_config)

DT = 0.01
STOP_SPEED = 0.25          # m/s: Stop()
STOP_DISP_M = 0.05         # m from the start of the stage: Stop()
JUMP_MAX_M = 0.002         # stage a: largest allowed movement at a switch
EMPTY_MAX_N = 3.0          # after zeroing the empty handle must read under this
RELEASED_N = 3.0           # "the person has let go"
COUNTDOWN_S = 5
RESTORE_WAIT_S = 3         # hands-off wait before the limits are restored after a Stop()
SWITCH_S = 3.0             # stage a: seconds in each profile
SETTLE_S = 1.5             # stages b to d: profile on, nobody pushing yet

STAGES = {
    "a": dict(title="nobody touching: profile on and off 3 times", ceiling=10.0, push_s=0.0,
              cue="", sim_push=0.0, sim_ramp=1.0),
    "b": dict(title="gentle push, about 10 N, held 5 s", ceiling=25.0, push_s=5.0,
              cue="PUSH NOW along the reach, GENTLY, about 10 N (1 kg), and hold it", sim_push=10.0, sim_ramp=1.0),
    "c": dict(title="push of 30 to 40 N", ceiling=50.0, push_s=8.0,
              cue="PUSH NOW along the reach: build up slowly to 30-40 N (3 to 4 kg), hold 2 s. NOT over 45 N",
              sim_push=36.0, sim_ramp=2.5),
    "d": dict(title="push towards 60 N (stop at 65 N)", ceiling=TEST_MAX_CONTACT_N, push_s=10.0,
              cue="PUSH NOW along the reach: build up slowly towards 60 N (6 kg), hold 2 s. The robot is "
                  "STOPPED at 65 N", sim_push=58.0, sim_ramp=3.5),
}


class StopNow(Exception):
    """The script stopped the robot (fault, speed, displacement or force ceiling)."""


class Tripped(Exception):
    """robot/arm.py tripped to hold by itself."""


def norm(v) -> float:
    return math.sqrt(sum(float(x) ** 2 for x in v))


class Recorder:
    """Wraps the RDK robot and keeps what robot/arm.py last sent to it."""

    def __init__(self, robot) -> None:
        self._r = robot
        self.k: list[float] | None = None
        self.contact: list[float] | None = None
        self.calls: list[str] = []

    def SetCartesianImpedance(self, k, *a, **kw):
        self.k = [float(v) for v in k]
        self.calls.append("SetCartesianImpedance")
        return self._r.SetCartesianImpedance(k, *a, **kw)

    def SetMaxContactWrench(self, w, *a, **kw):
        self.contact = [float(v) for v in w]
        self.calls.append("SetMaxContactWrench")
        return self._r.SetMaxContactWrench(w, *a, **kw)

    def Stop(self, *a, **kw):
        self.calls.append("Stop")
        return self._r.Stop(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._r, name)


class ScriptedHand:
    """Sim only: a hand whose force on the handle is set by the stage."""

    strength = 1.0

    def __init__(self, lift_n: float) -> None:
        self.present, self.force, self._lift = False, (0.0, 0.0, 0.0), lift_n

    def effort(self, t, pos, vel, goal):
        import numpy as np
        f = np.array(self.force, dtype=float)
        f[2] += self._lift            # cancels SimArm's limb weight: this hand carries itself
        return f


class Run:
    """The arm plus the guard that every sample goes through."""

    def __init__(self, arm, stage: str, *, sim: bool, axis: int, sign: int, hand=None, rec=None,
                 k_nom=None, tau_max=None, sim_push: float | None = None) -> None:
        self.arm, self.stage, self.sim, self.axis, self.sign = arm, stage, sim, axis, sign
        self.hand, self.rec, self.k_nom, self.tau_max = hand, rec, k_nom, tau_max
        self.cfg = dict(STAGES[stage])
        if sim_push is not None:
            self.cfg["sim_push"] = sim_push
        self.ceiling = self.cfg["ceiling"]
        self.baseline = (0.0, 0.0, 0.0)
        self.guard = False                 # speed / displacement / ceiling checks on (after start_compliance)
        self.rows: list[dict] = []
        self.tau_peak: list[float] | None = None
        self.stopped: str | None = None
        self.tripped: str | None = None
        self.started = False               # start_compliance() ran: there is something to restore
        self._t0: float | None = None
        self._next = time.monotonic()
        self._n = 0
        self._shown = -1.0

    def say(self, msg: str) -> None:
        print(msg, flush=True)

    def countdown(self, msg: str, seconds: int | None = None) -> None:
        self.say(msg)
        if self.sim:
            return
        for i in range(COUNTDOWN_S if seconds is None else seconds, 0, -1):
            self.say(f"    {i}")
            time.sleep(1.0)

    def act(self, f_along: float | None) -> None:
        if self.hand is None:
            return
        if not f_along:
            self.hand.present, self.hand.force = False, (0.0, 0.0, 0.0)
        else:
            f = [0.0, 0.0, 0.0]
            f[self.axis] = f_along * self.sign
            self.hand.present, self.hand.force = True, tuple(f)

    def tick(self) -> None:
        if self.sim:
            self.arm.step(DT)
            return
        self._next += DT
        sl = self._next - time.monotonic()
        if sl > 0:
            time.sleep(sl)
        else:
            self._next = time.monotonic()

    def _read_tau(self) -> None:
        if self.rec is None:
            return
        try:
            with self.arm._lock:
                tau = [abs(float(v)) for v in self.rec.states().tau]
        except Exception:  # noqa: BLE001  (this RDK or this fake has no states().tau)
            return
        self.tau_peak = tau if self.tau_peak is None else [max(a, b) for a, b in zip(self.tau_peak, tau)]

    def stop_now(self, reason: str) -> None:
        self.arm.stop()                    # robot.Stop() first, words after
        self.stopped = reason
        self.act(None)
        self.say(f"\a\n  *** STOPPED THE ROBOT: {reason} ***")
        raise StopNow(reason)

    def sample(self, label: str) -> dict:
        s = self.arm.get_state()
        if self._t0 is None:
            self._t0 = s.t
        raw = norm(s.force)
        f = tuple(a - b for a, b in zip(s.force, self.baseline))
        start = self.arm.start_pos
        row = dict(t=s.t - self._t0, label=label, pos=tuple(s.pos), speed=norm(s.vel), raw=raw, vec=tuple(s.force),
                   f=norm(f), along=f[self.axis] * self.sign,
                   disp=math.dist(s.pos, start) if start is not None else 0.0, mode=s.mode)
        self.rows.append(row)
        self._n += 1
        if self._n % 5 == 0:
            self._read_tau()
        if s.mode == "fault":
            self.stop_now(f"robot fault: {s.fault}")
        if self.guard:
            if row["speed"] > STOP_SPEED:
                self.stop_now(f"handle speed {row['speed']:.2f} m/s, over {STOP_SPEED} m/s")
            if row["disp"] > STOP_DISP_M:
                self.stop_now(f"handle {row['disp'] * 100:.1f} cm from the start, over {STOP_DISP_M * 100:.0f} cm")
            if raw > self.ceiling:
                self.stop_now(f"force reading {raw:.1f} N, over the {self.ceiling:.0f} N ceiling of stage {self.stage}")
            if s.mode != "compliant":
                self.tripped = f"{s.mode}: {s.fault}"
                self.act(None)
                self.say(f"\n  *** robot/arm.py tripped: {self.tripped} ***")
                raise Tripped(self.tripped)
        return row

    def stream(self, seconds: float, label: str, push=None, until=None) -> list[dict]:
        """Hold the target on the start at 100 Hz for `seconds` (or until `until(rows)`)."""
        i0 = len(self.rows)
        self._next = time.monotonic()
        t_start = None
        while True:
            row = self.sample(label)
            if t_start is None:
                t_start = row["t"]
            el = row["t"] - t_start
            if el >= seconds or (until is not None and until(self.rows[i0:])):
                break
            if self.sim:
                self.act(push(el) if push is not None else None)
            self.arm.set_target(self.arm.start_pos)
            if row["t"] - self._shown >= 0.5:
                self._shown = row["t"]
                self.say(f"    {label:<8} {el:4.1f} s   along reach {row['along']:+6.1f} N   |F| {row['f']:5.1f} N   "
                         f"moved {row['disp'] * 1000:5.1f} mm   {row['speed']:.2f} m/s")
            self.tick()
        return self.rows[i0:]


# --------------------------------------------------------------------------- the stages

def stage_a(run: Run) -> list[tuple[str, bool, str]]:
    arm, checks, jumps, forces = run.arm, [], [], []
    for i in (1, 2, 3):
        for on in (True, False):
            p0 = run.sample("switch")["pos"]
            arm.set_test_limits(on)
            if on:
                arm.set_stiffness(*(arm.limits.k_max,) * 3)     # 1500 N/m; switching off drops to k_hold by itself
                if not arm.test_limits_on or arm.limits.k_max != TEST_K_MAX:
                    checks.append(("profile switched on", False, f"limits are {arm.limits}"))
            rows = run.stream(SWITCH_S, f"{'on' if on else 'off'} {i}")
            jump = max(math.dist(r["pos"], p0) for r in rows)
            jumps.append(jump)
            forces.append(max(r["f"] for r in rows))
            run.say(f"  switch {i} {'ON ' if on else 'OFF'}: moved at most {jump * 1000:.2f} mm, force at most {forces[-1]:.1f} N")
            if on and run.rec is not None:
                ok = run.rec.contact is not None and abs(run.rec.contact[0] - TEST_MAX_CONTACT_N) < 1e-6
                if not ok:
                    checks.append(("contact limit 65 N sent with the profile", False, f"last sent {run.rec.contact}"))
    checks.append((f"position jump under {JUMP_MAX_M * 1000:.0f} mm at all 6 switches", max(jumps) < JUMP_MAX_M,
                   f"largest {max(jumps) * 1000:.2f} mm; per switch " + ", ".join(f"{j * 1000:.2f}" for j in jumps)))
    checks.append(("force with nobody touching (logged)", True, f"largest {max(forces):.1f} N"))
    return checks


def stage_push(run: Run) -> list[tuple[str, bool, str]]:
    arm, cfg = run.arm, run.cfg
    p0 = run.sample("switch")["pos"]
    arm.set_test_limits(True)
    arm.set_stiffness(*(arm.limits.k_max,) * 3)
    run.say(f"  test profile ON: {arm.limits.k_max:.0f} N/m, contact {arm.limits.max_contact_n:.0f} N, trip "
            f"{arm.limits.trip_force:.0f} N. HANDS OFF for {SETTLE_S} s.")
    settle = run.stream(SETTLE_S, "settle")
    jump = max(math.dist(r["pos"], p0) for r in settle)
    run.say(f"\a\n  >>> {cfg['cue']}. ({cfg['push_s']:.0f} s) <<<")
    peak, ramp, T = cfg["sim_push"], cfg["sim_ramp"], cfg["push_s"]
    push = run.stream(T, "push", push=lambda t: peak * min(1.0, t / ramp))
    run.say("\a\n  >>> EASE OFF over a second, then LET GO. <<<")

    def released(rows) -> bool:
        return len(rows) >= 30 and all(r["f"] < RELEASED_N for r in rows[-30:])

    ease = run.stream(5.0, "ease", push=lambda t: peak * max(0.0, 1.0 - t), until=released)
    let_go = released(ease)
    arm.set_test_limits(False)
    run.stream(1.0, "default")

    rows = push + ease
    top = max(rows, key=lambda r: abs(r["along"]))
    f_top, d_top, d_max = abs(top["along"]), top["disp"], max(r["disp"] for r in rows)
    d_le40 = max((r["disp"] for r in rows if r["f"] <= 40.0), default=0.0)
    way = "in the reach direction" if top["along"] >= 0 else "AGAINST the reach direction"
    checks = [(f"no jump when the profile came on (under {JUMP_MAX_M * 1000:.0f} mm)", jump < JUMP_MAX_M, f"{jump * 1000:.2f} mm"),
              ("peak force along the reach (logged)", True,
               f"{f_top:.1f} N {way}; |F| peak {max(r['f'] for r in rows):.1f} N; {f_top / d_top if d_top > 1e-4 else float('nan'):.0f} N/m measured"),
              ("displacement (logged)", True, f"{d_top * 1000:.1f} mm at the peak, largest {d_max * 1000:.1f} mm, "
                                               f"largest for readings up to 40 N {d_le40 * 1000:.1f} mm")]
    if run.stage == "b":
        checks.append(("a push was seen: 5 to 25 N", 5.0 <= f_top <= 25.0, f"{f_top:.1f} N"))
        checks.append(("displacement under 2 cm", d_max < 0.02, f"{d_max * 1000:.1f} mm"))
    else:
        need = 30.0 if run.stage == "c" else 50.0
        checks.append((f"the reading passed {need:.0f} N", f_top > need, f"{f_top:.1f} N"))
        checks.append(("displacement under 3 cm for readings up to 40 N", d_le40 < 0.03, f"{d_le40 * 1000:.1f} mm"))
    checks.append(("the person let go before the profile went off", let_go,
                   "yes" if let_go else "still over 3 N after 5 s: the default limits came back with a hand on the handle"))
    return checks


# --------------------------------------------------------------------------- set-up and restore

def build_sim(args) -> Run:
    from software.sim_arm import PASSIVE_LOAD_N, SimArm     # sim only: robot/ does not import software/ otherwise
    cfg = load_config()
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    hand = ScriptedHand(PASSIVE_LOAD_N)
    arm = SimArm(hand, limits_for_reach_axis(Limits(), cfg.reach_axis), start_pos=cfg.start_tcp_pose[:3], realtime=False)
    arm.reach_axis, arm.auto_cue = cfg.reach_axis, False
    arm.connect()
    return Run(arm, args.stage, sim=True, axis=cfg.reach_axis, sign=int(raw.get("reach_sign", 1)), hand=hand,
               sim_push=args.sim_push)


def build_real(args) -> Run:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    serial = args.serial or str(raw["serial"])
    import flexivrdk                                          # only here: the dry run needs no RDK

    robot = flexivrdk.Robot(serial)
    problems = []
    if robot.fault():
        problems.append("the robot reports a fault")
    if not robot.operational():
        problems.append("the robot is not operational")
    if not str(robot.mode()).endswith("IDLE"):
        problems.append(f"the robot is in {robot.mode()}, not IDLE (is the server or another program driving it?)")
    if not robot.estop_released():
        problems.append("the e-stop is pressed")
    if problems:
        raise SystemExit("REFUSED: " + "; ".join(problems) + ". This script never enables the robot or clears a fault.")
    info = robot.info()
    k_nom = [float(v) for v in info.K_x_nom]
    tau_max = getattr(info, "tau_max", None)
    tau_max = [float(v) for v in tau_max] if tau_max is not None else None
    try:
        tool = flexivrdk.Tool(robot).name()
    except Exception as exc:  # noqa: BLE001
        tool = f"unknown ({exc!r})"
    arm = Arm(serial)
    rec = Recorder(robot)
    arm._attach(rec, flexivrdk, k_nom)                        # never Arm.connect(): no Enable(), no ClearFault()
    sign = int(raw.get("reach_sign", 1))
    print(f"connected to {serial}: fault-free, operational, IDLE. Tool {tool!r}. K_x_nom {k_nom}. "
          f"Reach axis {'xy'[arm.reach_axis]}, sign {sign:+d}. Joint torque limits "
          f"{tau_max if tau_max is not None else 'not exposed by this RDK'}.", flush=True)
    return Run(arm, args.stage, sim=False, axis=arm.reach_axis, sign=sign, rec=rec, k_nom=k_nom, tau_max=tau_max)


def restore(run: Run) -> tuple[bool, str]:
    """Default limits, K_x_nom, Stop. Returns (confirmed, what was sent)."""
    arm = run.arm
    try:
        arm.set_test_limits(False)
    except Exception as exc:  # noqa: BLE001
        run.say(f"  set_test_limits(False) raised {exc!r}")
    if run.sim:
        arm.close()
        lim = arm.limits
        ok = not arm.test_limits_on and lim.k_max == Limits().k_max and lim.trip_force == Limits().trip_force
        return ok, f"SimArm closed; limits in force: k_max {lim.k_max:.0f} N/m, trip {lim.trip_force:.0f} N (the sim has no K_x_nom)"
    rec = run.rec
    if not run.started:
        arm.close()
        return True, "nothing was changed on the robot before the stage ended (no Cartesian mode entered); Stop sent"
    faulted = True
    try:
        faulted = bool(rec.fault())
    except Exception:  # noqa: BLE001
        pass
    if faulted:
        try:
            arm.close()
        except Exception as exc:  # noqa: BLE001
            run.say(f"  arm.close() raised {exc!r}")
        return False, ("ROBOT FAULT: K_x_nom and the 30 N contact limit could NOT be sent. They are sent again by the "
                       "next start_compliance() and close() of robot/arm.py (any server run, or stage a of this script) "
                       "once the fault is cleared (robot/RUNBOOK.md)")
    if not arm._in_cartesian:                                 # after a Stop(): the impedance can only be set in Cartesian mode
        run.countdown("  HANDS OFF THE HANDLE. Re-entering Cartesian mode where the arm is, to restore the limits, in:", RESTORE_WAIT_S)
        arm.start_compliance()                                # default profile: 30 N contact limit, k_hold, target = where it is
    arm.close()                                               # hold, K_x_nom, Stop
    lim = arm.limits
    want_c = [lim.max_contact_n] * 3 + [lim.max_contact_nm] * 3
    ok = (not arm.test_limits_on and rec.k is not None and all(abs(a - b) < 1e-6 for a, b in zip(rec.k, run.k_nom))
          and rec.contact is not None and all(abs(a - b) < 1e-6 for a, b in zip(rec.contact, want_c))
          and lim.max_contact_n == Limits().max_contact_n and bool(rec.calls) and rec.calls[-1] == "Stop")
    return ok, (f"last stiffness sent {rec.k} (K_x_nom {run.k_nom}); last contact limit sent {rec.contact}; "
                f"last call {rec.calls[-1] if rec.calls else None}. The RDK has no getter for either: this is what was "
                f"sent and accepted")


def torque_lines(run: Run) -> list[str]:
    if run.sim:
        return ["joint torque: not available in the sim"]
    if run.tau_peak is None:
        return ["joint torque: states().tau not exposed by this RDK"]
    if run.tau_max is None:
        return ["joint torque peaks (Nm), no limits exposed by info(): " + ", ".join(f"J{i + 1} {t:.1f}" for i, t in enumerate(run.tau_peak))]
    out = ["joint torque, peak |tau| against info().tau_max:"]
    for i, (t, m) in enumerate(zip(run.tau_peak, run.tau_max)):
        pct = 100.0 * t / m if m > 0 else float("nan")
        out.append(f"    J{i + 1}: {t:6.1f} of {m:6.1f} Nm = {pct:3.0f} %{'   <-- over 80 %' if pct > 80 else ''}")
    return out


def plan(stage: str) -> str:
    c = STAGES[stage]
    return (f"STAGE {stage}: {c['title']}\n"
            f"  default limits : k_max {Limits().k_max:.0f} N/m, contact {Limits().max_contact_n:.0f} N, force trip {Limits().trip_force:.0f} N\n"
            f"  test profile   : k_max {TEST_K_MAX:.0f} N/m, contact {TEST_MAX_CONTACT_N:.0f} N, force trip {TEST_TRIP_FORCE:.0f} N\n"
            f"  Stop() at once : robot fault, speed over {STOP_SPEED} m/s, more than {STOP_DISP_M * 100:.0f} cm from the start, "
            f"force reading over {c['ceiling']:.0f} N\n"
            f"  order          : zero the force sensor (nobody touching), compliance where the arm is, the stage, "
            f"restore default limits and K_x_nom, Stop. No homing.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Staged on-arm test of Arm.set_test_limits.")
    ap.add_argument("--stage", required=True, choices=sorted(STAGES))
    ap.add_argument("--go", action="store_true", help="really connect to the robot and run the stage")
    ap.add_argument("--sim", action="store_true", help="dry run on SimArm (no robot)")
    ap.add_argument("--serial", help="robot serial (default robot/config.json)")
    ap.add_argument("--sim-push", type=float, help="sim only: the scripted push in N (to dry-run the stops)")
    ap.add_argument("--out", help="folder for the result file (default robot/results)")
    args = ap.parse_args(argv)
    print(plan(args.stage), flush=True)
    if not args.sim and not args.go:
        print("\nNothing was connected. Add --go to run it on the arm (e-stop holder in place), or --sim for a dry run.")
        return 2

    run = build_sim(args) if args.sim else build_real(args)
    arm, checks, crash = run.arm, [], None
    try:
        run.countdown("\nNOBODY TOUCHES THE ARM OR THE HANDLE. Zeroing the force sensor (ZeroFTSensor) in:")
        arm.zero_force()
        arm.start_compliance()                                # where the arm is now; nothing is homed
        run.started = True
        base = run.stream(1.0, "empty")
        run.baseline = tuple(sum(r["vec"][i] for r in base) / len(base) for i in range(3))   # reported forces are above this
        empty = max(r["raw"] for r in base)
        checks.append((f"empty handle reads under {EMPTY_MAX_N:.0f} N after zeroing", empty < EMPTY_MAX_N, f"{empty:.2f} N"))
        if empty < EMPTY_MAX_N:
            run.guard = True
            checks += stage_a(run) if args.stage == "a" else stage_push(run)
        else:
            run.say("  The handle does not read empty: is somebody touching it? Stage not run.")
    except (StopNow, Tripped):
        pass
    except KeyboardInterrupt:
        crash = "Ctrl+C"
        run.say("\n  Ctrl+C: holding, restoring, stopping.")
        try:
            arm.hold()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001  (any error: Stop first, then restore below)
        crash = repr(exc)
        try:
            arm.stop()
        except Exception:  # noqa: BLE001
            pass
        run.say(f"\n  ERROR {crash}: robot stopped.")
    finally:
        try:
            restored, restore_text = restore(run)
        except KeyboardInterrupt:
            restored, restore_text = restore(run)
        except Exception as exc:  # noqa: BLE001
            restored, restore_text = False, f"restore raised {exc!r}: run stage a again once the robot is fault-free and IDLE"

    rows = [r for r in run.rows if r["label"] not in ("empty",)]
    passed = (bool(checks) and all(ok for _, ok, _ in checks) and run.stopped is None and run.tripped is None
              and crash is None and restored)
    status = "PASS" if passed else "FAIL"
    tag = "  [SIMULATED: says nothing about the real arm]" if args.sim else ""
    lines = [f"\n===== STAGE {args.stage}: {STAGES[args.stage]['title']} ====={tag}"]
    if rows:
        top = max(rows, key=lambda r: abs(r["along"]))
        lines.append(f"peak force along the reach: {abs(top['along']):.1f} N "
                     f"({'in' if top['along'] >= 0 else 'against'} the reach direction); |F| peak {max(r['f'] for r in rows):.1f} N")
        lines.append(f"displacement: largest {max(r['disp'] for r in rows) * 1000:.1f} mm; peak speed {max(r['speed'] for r in rows):.3f} m/s")
    lines.append(f"trip or fault: {run.stopped and 'SCRIPT STOPPED THE ROBOT: ' + run.stopped or run.tripped or crash or 'none'}")
    lines += torque_lines(run)
    for name, ok, text in checks:
        lines.append(f"  [{'ok' if ok else 'NO'}] {name}: {text}")
    lines.append(f"  [{'ok' if restored else 'NO'}] default limits and K_x_nom restored: {restore_text}")
    lines.append(f"RESULT STAGE {args.stage}: {status}{tag}")
    if status == "FAIL" and not args.sim:
        lines.append("Do NOT go on to the next stage. Nobody pushes with the test profile until this stage passes.")
    print("\n".join(lines), flush=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(__file__).with_name("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"test_limits_{args.stage}_{stamp}_{'sim' if args.sim else 'arm'}.json"
    out.write_text(json.dumps(dict(
        when=stamp, stage=args.stage, sim=args.sim, status=status, stopped=run.stopped, tripped=run.tripped,
        error=crash, restored=restored, restore=restore_text, checks=[dict(name=n, ok=o, measured=t) for n, o, t in checks],
        tau_peak=run.tau_peak, tau_max=run.tau_max, reach_axis="xy"[run.axis], reach_sign=run.sign,
        samples=[[round(r["t"], 3), r["label"], round(r["along"], 2), round(r["f"], 2), round(r["disp"] * 1000, 2),
                  round(r["speed"], 4)] for r in run.rows[::5]],
        samples_columns=["t_s", "segment", "force_along_reach_N", "force_N", "displacement_mm", "speed_m_s"]), indent=1),
        encoding="utf-8")
    print(f"saved {out}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
