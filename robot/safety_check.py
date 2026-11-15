"""Interactive on-arm safety checks (package K2). MOVES THE ARM. A person touches the handle.

    python robot/safety_check.py                      real arm (serial and reach axis from robot/config.json)
    python robot/safety_check.py --serial Rizon4-062157 --tool RehabHandle --reach-sign 1
    python robot/safety_check.py --sim                dry run on software.sim_arm.SimArm, no robot, no prompts
    python robot/safety_check.py --only 7,8           re-run single checks (check 1 always runs: it is the baseline)
    python robot/safety_check.py --list

Fifteen checks, PASS or FAIL each. Every step that moves the arm, or asks a person to push it,
waits for Enter first. While the script waits, the arm is in hold (soft, k_hold).

Rules (robot/RUNBOOK.md): e-stop holder in place before "go"; the technician does every
hands-on check first; any FAIL: stop, nobody holds the handle until it is fixed and re-run.

What this script never does: Enable(), ClearFault(), change the tool, or loosen a limit in
robot/arm.py. It refuses to start unless the robot is fault-free, operational, in IDLE, with
the e-stop released and the expected tool selected. Ctrl+C at any time: hold, then close.

Checks 10, 11 and 13 need exercise behaviour (assist lead, resistance band, free reach axis).
robot/ imports nothing from software/, so the script uses its own small copies of those laws
with the constants below. They test the ARM's behaviour under those commands; the engine's own
hands-off rule must still be confirmed in an engine run (see robot/SAFETY.md).

In --sim some checks cannot be reproduced (SimArm has no robot-side speed limit and no nominal
stiffness); those report N/A-SIM instead of FAIL.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import namedtuple
from dataclasses import replace
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from robot.arm import Arm, Limits, limits_for_reach_axis  # noqa: E402
from robot.read_tool_force import tool_hint  # noqa: E402

DT = 0.01
# Copies of software/controller.py and software/engine.py values (override with --k-assist etc.).
K_WALL = 500.0
K_ASSIST = 400.0
K_RESIST = 300.0
F_PRESENT = 1.5            # N above the empty baseline: "a hand is on the handle"
OCCUPIED_WINDOW_S = 0.5
REACH_M = 0.30

EMPTY_FORCE_MAX_N = 2.0    # check 1
TEST_BOX_M = 0.03          # check 8: the side box is TIGHTENED to this for the test
RECENTER_SPEED = 0.05      # m/s

Sample = namedtuple("Sample", "t pos vel force mode fault")
Result = namedtuple("Result", "status measured note")

CHECKS: list[tuple[int, str, object]] = []


def check(num: int, title: str):
    def deco(fn):
        CHECKS.append((num, title, fn))
        return fn
    return deco


def norm(v) -> float:
    return math.sqrt(sum(float(x) ** 2 for x in v))


def sub(a, b):
    return tuple(float(x) - float(y) for x, y in zip(a, b))


class Abort(Exception):
    """Operator chose to stop after a FAIL."""


# --------------------------------------------------------------------------- sim stand-ins

class ScriptedHand:
    """SimArm 'patient' whose force is set by the check being dry-run (sim only)."""

    def __init__(self, limb_weight_n: float) -> None:
        self.present = False
        self.force = (0.0, 0.0, 0.0)
        self.damping = 0.0
        self._lift = limb_weight_n      # cancels SimArm's 8 N limb weight: this hand carries itself

    def effort(self, t, pos, vel, goal):
        import numpy as np
        f = np.array(self.force, dtype=float) - self.damping * np.asarray(vel, dtype=float)
        f[2] += self._lift
        return f


class Spy:
    """Wraps the RDK robot and records what robot/arm.py actually sends to it."""

    def __init__(self, robot) -> None:
        self._r = robot
        self.pose: list[float] | None = None
        self.k: list[float] | None = None
        self.calls: list[str] = []

    def SendCartesianMotionForce(self, pose, *a, **kw):
        self.pose = [float(v) for v in pose]
        return self._r.SendCartesianMotionForce(pose, *a, **kw)

    def SetCartesianImpedance(self, k, *a, **kw):
        self.k = [float(v) for v in k]
        self.calls.append("SetCartesianImpedance")
        return self._r.SetCartesianImpedance(k, *a, **kw)

    def Stop(self, *a, **kw):
        self.calls.append("Stop")
        return self._r.Stop(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._r, name)


# --------------------------------------------------------------------------- rig

class Rig:
    """The arm plus everything a check needs: axes, prompts, the 100 Hz command loop."""

    def __init__(self, arm, *, sim: bool, reach_sign: int = 1, hand: ScriptedHand | None = None,
                 spy: Spy | None = None, ask=input, k_nom=None,
                 k_wall=K_WALL, k_assist=K_ASSIST, k_resist=K_RESIST, reach_m=REACH_M) -> None:
        self.arm, self.sim, self.hand, self.spy, self.ask, self.k_nom = arm, sim, hand, spy, ask, k_nom
        self.axis = int(arm.reach_axis)
        self.side = 1 - self.axis
        self.up = 2
        self.sign = 1 if reach_sign >= 0 else -1
        self.u = tuple(float(self.sign) if i == self.axis else 0.0 for i in range(3))
        self.k_wall, self.k_assist, self.k_resist, self.reach_m = k_wall, k_assist, k_resist, reach_m
        self.baseline = (0.0, 0.0, 0.0)
        self.live = False                 # start_compliance() has been called at least once
        self._next = time.monotonic()

    # -- geometry
    @property
    def lim(self) -> Limits:
        return self.arm.limits

    @property
    def start(self):
        return self.arm.start_pos

    def along(self, pos) -> float:
        """Metres travelled along the reach direction from the start."""
        return (pos[self.axis] - self.start[self.axis]) * self.sign

    def on_path(self, s: float):
        return tuple(p + s * c for p, c in zip(self.start, self.u))

    def disp(self, pos) -> float:
        return math.dist(pos, self.start)

    def rel(self, force) -> float:
        """Force magnitude above the empty-handle baseline (N)."""
        return norm(sub(force, self.baseline))

    def k_axes(self, reach: float, other: float):
        k = [other, other, other]
        k[self.axis] = reach
        return tuple(k)

    def axis_name(self, i: int) -> str:
        return "xyz"[i]

    # -- what arm.py really commanded
    def commanded_target(self):
        if self.spy is not None and self.spy.pose is not None:
            return tuple(self.spy.pose[:3])
        return tuple(float(v) for v in self.arm._target)       # SimArm

    def commanded_k(self):
        if self.spy is not None and self.spy.k is not None:
            return tuple(self.spy.k[:3])
        return tuple(float(v) for v in self.arm._k)            # SimArm

    # -- prompts
    def say(self, msg: str) -> None:
        print(msg, flush=True)

    def pause(self, msg: str) -> None:
        """Plain Enter prompt. Does not touch the arm."""
        if self.sim:
            self.say(f"  [sim] {msg}")
            self.act(None)
            for _ in range(300):          # 3 s of sim time pass, as they would while a person reads
                self.arm.step(DT)
        else:
            self.ask(f"  {msg}\n  [Enter] ")

    def wait(self, msg: str) -> None:
        """Hold the arm, wait for Enter, re-arm at k_hold where the hand is."""
        if self.live:
            self.arm.hold()
        self.pause(msg)
        self.arm.start_compliance()
        self.live = True

    def cue(self, msg: str) -> None:
        self.say(f"\a\n  >>> {msg} <<<")
        self.act(None)

    def act(self, script) -> None:
        """Sim only: what the scripted hand does. None = hand off; else (force_xyz, damping)."""
        if self.hand is None:
            return
        if script is None:
            self.hand.present, self.hand.force, self.hand.damping = False, (0.0, 0.0, 0.0), 0.0
        else:
            self.hand.present, self.hand.force, self.hand.damping = True, tuple(script[0]), float(script[1])

    # -- time
    def state(self) -> Sample:
        s = self.arm.get_state()
        return Sample(s.t, s.pos, s.vel, s.force, s.mode, s.fault)

    def tick(self, dt: float = DT) -> None:
        if self.sim:
            self.arm.step(dt)
            return
        self._next += dt
        sl = self._next - time.monotonic()
        if sl > 0:
            time.sleep(sl)
        else:
            self._next = time.monotonic()

    def run(self, seconds: float, target_fn, *, until=None, sim_script=None, live=None,
            feed: bool = True, watch_after: float = 0.0) -> list[Sample]:
        """Stream targets at 100 Hz for `seconds` (or until `until(sample, samples)` is true, or
        the arm leaves compliant mode). Sample.t counts from 0. `feed=False` sends nothing.
        If the arm trips, keep recording (no commands) for `watch_after` seconds to see it stop."""
        out: list[Sample] = []
        t0 = self.state().t
        self._next = time.monotonic()
        shown = -1.0
        while True:
            s = self.state()
            s = s._replace(t=s.t - t0)
            out.append(s)
            if s.mode != "compliant":
                self.act(None)
                t_trip = s.t
                while watch_after > 0 and out[-1].t - t_trip < watch_after:
                    self.tick()
                    s = self.state()
                    out.append(s._replace(t=s.t - t0))
                break
            if s.t >= seconds or (until is not None and until(s, out)):
                break
            if sim_script is not None and self.sim:
                self.act(sim_script(s))
            if feed:
                self.arm.set_target(target_fn(s))
            if live is not None and not self.sim and s.t - shown >= 0.2:
                shown = s.t
                print("\r    " + live(s) + "   ", end="", flush=True)
            self.tick()
        if live is not None and not self.sim:
            print()
        self.act(None)
        return out

    def settle(self, k3, seconds: float = 0.4) -> None:
        """Set stiffness and give the worker time to apply it, target on the hand."""
        self.arm.set_stiffness(*k3)
        p = self.state().pos
        self.run(seconds, lambda s: p)

    def recenter(self) -> None:
        """Bring the empty handle back to the start at 5 cm/s (k_max), then back to k_hold."""
        if self.state().mode != "compliant":
            return
        self.arm.set_stiffness(*(self.lim.k_max,) * 3)
        p0, goal = self.state().pos, self.start
        T = math.dist(p0, goal) / RECENTER_SPEED
        self.run(T + 1.5, lambda s: tuple(a + (b - a) * (min(1.0, s.t / T) if T > 0 else 1.0)
                                          for a, b in zip(p0, goal)))
        self.settle((self.lim.k_hold,) * 3, 0.3)

    def recover(self) -> None:
        """After a trip or a check that left the handle away from the start."""
        self.wait("LET GO of the handle. Hands off: the arm returns to the start by itself at 5 cm/s.")
        self.recenter()

    def live_line(self, s: Sample) -> str:
        return (f"push {self.rel(s.force):5.1f} N   along reach {self.along(s.pos) * 100:+6.1f} cm   "
                f"from start {self.disp(s.pos) * 100:5.1f} cm")


def _tripped(samples: list[Sample]) -> str | None:
    bad = next((s for s in samples if s.mode != "compliant"), None)
    return None if bad is None else f"{bad.mode}: {bad.fault}"


def _release_index(rig: Rig, samples: list[Sample], i_cue: int) -> tuple[int, bool]:
    """First sample after the cue where the handle reads empty; (i_cue, False) if it never does."""
    for i in range(i_cue, len(samples)):
        if rig.rel(samples[i].force) < F_PRESENT:
            return i, True
    return i_cue, False


def _cue_at(rig: Rig, progress_m: float, after_s: float, before_s: float, msg: str):
    """`until` callback: cue when the hand passes progress_m, stop after_s later, give up after before_s."""
    box = {"i": None}

    def until(s: Sample, out: list[Sample]) -> bool:
        if box["i"] is None:
            if rig.along(s.pos) >= progress_m:
                box["i"] = len(out) - 1
                rig.cue(msg)
            return s.t >= before_s
        return s.t - out[box["i"]].t >= after_s

    return until, box


# --------------------------------------------------------------------------- the checks

@check(1, "Empty handle force near 0 with the active tool")
def c01(rig: Rig) -> Result:
    rig.pause("CHECK 1. NOBODY touches the arm or the handle. Reads the force for 1 s; no motion.")
    acc, mags = [0.0, 0.0, 0.0], []
    for _ in range(100):
        f = rig.state().force
        acc = [a + v for a, v in zip(acc, f)]
        mags.append(norm(f))
        rig.tick()
    mean = tuple(a / 100 for a in acc)
    rig.baseline = mean
    mag = norm(mean)
    raw = tuple(v * getattr(rig.arm, "force_sign", 1.0) for v in mean)   # undo arm.py's sign
    measured = (f"|F| {mag:.2f} N (x {mean[0]:+.2f}, y {mean[1]:+.2f}, z {mean[2]:+.2f}); "
                f"noise {max(mags) - min(mags):.2f} N")
    return Result("PASS" if mag < EMPTY_FORCE_MAX_N else "FAIL", measured,
                  "" if mag < EMPTY_FORCE_MAX_N else tool_hint(raw))


@check(2, "Push direction gives the expected force sign")
def c02(rig: Rig) -> Result:
    a = rig.axis_name(rig.axis)
    rig.wait(f"CHECK 2. Soft hold. Push the handle toward world +{a} with about 5-10 N for 2 s, "
             f"then let go. (6 s)")
    e = tuple(1.0 if i == rig.axis else 0.0 for i in range(3))
    out = rig.run(6.0, lambda s: rig.start, live=rig.live_line,
                  sim_script=lambda s: (tuple(6.0 * c for c in e), 0.0) if s.t < 2.0 else None)
    i = max(range(len(out)), key=lambda j: abs(out[j].pos[rig.axis] - rig.start[rig.axis]))
    d = out[i].pos[rig.axis] - rig.start[rig.axis]
    f = out[i].force[rig.axis] - rig.baseline[rig.axis]
    measured = f"moved {d * 1000:+.1f} mm along {a}, force[{a}] {f:+.1f} N at that point"
    if _tripped(out):
        return Result("FAIL", measured, f"tripped: {_tripped(out)}")
    if abs(d) < 0.003 or abs(f) < 3.0:
        return Result("FAIL", measured, "push too small to judge (need over 3 mm and 3 N): repeat")
    if (d > 0) != (f > 0):
        return Result("FAIL", measured, "force sign is opposite to the push: flip force_sign in robot/config.json")
    return Result("PASS", measured, "" if d > 0 else f"pushed toward -{a}; sign is still consistent")


@check(3, "Soft hold at K_HOLD")
def c03(rig: Rig) -> Result:
    kh = rig.lim.k_hold
    rig.wait(f"CHECK 3. Soft hold at {kh:.0f} N/m. Push the handle about 3 cm sideways, slowly, "
             f"then let go. (8 s)")
    e = tuple(1.0 if i == rig.side else 0.0 for i in range(3))
    out = rig.run(8.0, lambda s: rig.start, live=rig.live_line,
                  sim_script=lambda s: (tuple(0.03 * kh * c for c in e), 0.0) if s.t < 2.5 else None)
    i = max(range(len(out)), key=lambda j: rig.disp(out[j].pos))
    dpk, fpk = rig.disp(out[i].pos), rig.rel(out[i].force)
    tail = [rig.disp(s.pos) for s in out if s.t > out[-1].t - 0.5]
    end = sum(tail) / len(tail)
    k_meas = fpk / dpk if dpk > 1e-4 else float("nan")
    k_cmd = rig.commanded_k()
    measured = (f"pushed {dpk * 100:.1f} cm with {fpk:.1f} N = {k_meas:.0f} N/m (commanded "
                f"{k_cmd[0]:.0f}); came back to {end * 1000:.1f} mm")
    if _tripped(out):
        return Result("FAIL", measured, f"tripped: {_tripped(out)}")
    if dpk < 0.015:
        return Result("FAIL", measured, "push under 1.5 cm: repeat with a bigger push")
    ok = all(abs(k - kh) < 1e-6 for k in k_cmd) and 0.5 * kh <= k_meas <= 2.0 * kh and end <= 0.02
    return Result("PASS" if ok else "FAIL", measured,
                  "" if ok else "expected the commanded k_hold, 0.5x to 2x of it measured, and a return within 2 cm")


@check(4, "A target outside the workspace box is clamped")
def c04(rig: Rig) -> Result:
    box = rig.lim.box_half_m[rig.up]
    rig.wait(f"CHECK 4. HANDS OFF. The arm lifts the handle by itself at 5 cm/s. It is asked to go "
             f"20 cm up and must stop at the box edge ({box * 100:.0f} cm), then come back. (12 s)")
    cmd_up = []

    def target(s: Sample):
        cmd_up.append(rig.commanded_target()[rig.up] - rig.start[rig.up])
        a = 0.05 * s.t if s.t < 4.0 else 0.20 if s.t < 6.0 else max(0.0, 0.20 - 0.05 * (s.t - 6.0))
        p = list(rig.start)
        p[rig.up] += a
        return tuple(p)

    out = rig.run(11.5, target)
    hand_up = max(s.pos[rig.up] - rig.start[rig.up] for s in out)
    measured = (f"asked 20.0 cm; arm.py sent at most {max(cmd_up) * 100:.2f} cm; hand rose "
                f"{hand_up * 100:.1f} cm (box {box * 100:.0f} cm)")
    if _tripped(out):
        return Result("FAIL", measured, f"tripped: {_tripped(out)}")
    ok = box - 0.002 <= max(cmd_up) <= box + 1e-6 and hand_up <= box + 0.01
    return Result("PASS" if ok else "FAIL", measured, "" if ok else "target or hand went past the box edge")


@check(5, "A target 20 cm from the hand is clamped to 5 cm")
def c05(rig: Rig) -> Result:
    lead = rig.lim.max_lead_m
    rig.wait("CHECK 5. HANDS OFF. One target 20 cm along the reach is sent once; the arm should barely move. (1 s)")
    hand = rig.state().pos
    rig.arm.set_target(tuple(h + 0.20 * c for h, c in zip(hand, rig.u)))
    d = math.dist(rig.commanded_target(), hand)
    out = rig.run(1.0, lambda s: hand)
    moved = max(math.dist(s.pos, hand) for s in out)
    measured = f"asked 20.0 cm from the hand; arm.py sent {d * 100:.2f} cm; hand moved {moved * 1000:.1f} mm"
    ok = lead - 0.005 <= d <= lead + 0.002 and not _tripped(out)
    return Result("PASS" if ok else "FAIL", measured, "" if ok else f"expected {lead * 100:.0f} cm; {_tripped(out) or ''}")


@check(6, "Stiffness 5000 N/m is clamped")
def c06(rig: Rig) -> Result:
    km = rig.lim.k_max
    rig.wait("CHECK 6. HANDS OFF. Asks for 5000 N/m on every axis; no motion expected. (1 s)")
    rig.arm.set_stiffness(5000.0, 5000.0, 5000.0)
    out = rig.run(0.6, lambda s: rig.start)
    k = rig.commanded_k()
    rig.settle((rig.lim.k_hold,) * 3, 0.3)
    measured = f"asked 5000 N/m; arm.py sent {[round(v) for v in k]} (k_max {km:.0f})"
    ok = all(abs(v - km) < 1e-6 for v in k) and not _tripped(out)
    return Result("PASS" if ok else "FAIL", measured, "" if ok else f"{_tripped(out) or 'not clamped to k_max'}")


@check(7, "Pushing past 40 N trips to hold")
def c07(rig: Rig) -> Result:
    tf = rig.lim.trip_force
    give = rig.lim.k_max * rig.lim.max_lead_m
    rig.wait(f"CHECK 7. Stiff hold ({rig.lim.k_max:.0f} N/m). TECHNICIAN: push the handle along the reach "
             f"direction, steadily harder. Above about {give:.0f} N the handle gives way and follows your "
             f"push (the spring is capped); keep pushing harder until the arm drops into hold (about "
             f"{tf:.0f} N = {tf / 9.81:.0f} kg). Then let go. (30 s)")
    rig.settle((rig.lim.k_max,) * 3)
    out = rig.run(30.0, lambda s: rig.start, live=rig.live_line,
                  sim_script=lambda s: (tuple(min(50.0, 10.0 * s.t) * c for c in rig.u), 0.0))
    peak = max(norm(s.force) for s in out)
    far = max(rig.disp(s.pos) for s in out)
    last = out[-1]
    measured = f"peak force {peak:.1f} N; pushed {far * 100:.1f} cm; ended in {last.mode} ({last.fault})"
    rig.recover()
    if last.mode != "hold":
        return Result("FAIL", measured, "did not trip to hold" if last.mode == "compliant" else "robot fault, not a soft hold")
    if peak > tf + 5.0:
        return Result("FAIL", measured, f"force went more than 5 N past the {tf:.0f} N trip")
    by_force = (last.fault or "").startswith("force")
    return Result("PASS", measured, "" if by_force else "held, but a different trip fired before the force trip")


@check(8, "Hand 3 cm outside the box trips")
def c08(rig: Rig) -> Result:
    side = rig.axis_name(rig.side)
    lim0 = rig.lim
    box = list(lim0.box_half_m)
    box[rig.side] = TEST_BOX_M
    rig.wait(f"CHECK 8. The {side} axis is free and its box is tightened to +/-{TEST_BOX_M * 100:.0f} cm for "
             f"this test. Slide the handle sideways (along {side}) slowly, about 6 cm. It must trip "
             f"just past {(TEST_BOX_M + 0.02) * 100:.0f} cm. Then let go. (30 s)")
    rig.arm.limits = replace(lim0, box_half_m=tuple(box))     # tighter, never looser
    try:
        k = [rig.lim.k_hold] * 3
        k[rig.side] = 0.0
        rig.settle(tuple(k))

        def target(s: Sample):
            p = list(rig.start)
            p[rig.side] = s.pos[rig.side]
            return tuple(p)

        e = tuple(1.0 if i == rig.side else 0.0 for i in range(3))
        out = rig.run(30.0, target, live=rig.live_line, sim_script=lambda s: (tuple(2.0 * c for c in e), 0.0))
    finally:
        rig.arm.limits = lim0
    last = out[-1]
    off = abs(last.pos[rig.side] - rig.start[rig.side])
    measured = (f"tripped at {off * 100:.1f} cm from the centre = {(off - TEST_BOX_M) * 100:.1f} cm outside the "
                f"{TEST_BOX_M * 100:.0f} cm test box; {last.mode} ({last.fault})")
    rig.recover()
    ok = last.mode == "hold" and "outside" in (last.fault or "") and TEST_BOX_M + 0.015 <= off <= TEST_BOX_M + 0.04
    return Result("PASS" if ok else "FAIL", measured, "" if ok else "expected a box trip 2 to 3 cm outside the test box")


@check(9, "Stopping the command stream trips the watchdog within 0.3 s")
def c09(rig: Rig) -> Result:
    rig.wait("CHECK 9. HANDS OFF. The script stops sending targets; the arm must drop to hold. No motion. (2 s)")
    rig.run(0.5, lambda s: rig.start)
    t_last = rig.state().t
    s = rig.state()
    while s.mode == "compliant" and s.t - t_last < 2.0:
        rig.tick(DT if rig.sim else 0.005)
        s = rig.state()
    dt = s.t - t_last
    measured = f"hold after {dt:.2f} s without a target; {s.mode} ({s.fault})"
    ok = s.mode == "hold" and "watchdog" in (s.fault or "") and dt <= 0.3
    return Result("PASS" if ok else "FAIL", measured, "" if ok else "expected a watchdog hold within 0.3 s")


@check(10, "Letting go mid-assist stops the arm within about 10 cm")
def c10(rig: Rig) -> Result:
    lead = rig.lim.max_lead_m
    rig.wait(f"CHECK 10. Assist ({rig.k_assist:.0f} N/m, target {lead * 100:.0f} cm ahead). Hold the handle with a "
             f"RELAXED arm and let the arm carry your hand along the reach. When the terminal beeps "
             f"LET GO (at 12 cm), open your hand at once and keep clear. (up to 25 s)")
    rig.settle(rig.k_axes(rig.k_assist, rig.k_wall))
    occ = {"t": None}

    def target(s: Sample):
        if rig.rel(s.force) > F_PRESENT:
            occ["t"] = s.t
        occupied = occ["t"] is not None and s.t - occ["t"] <= OCCUPIED_WINDOW_S
        p = rig.along(s.pos)
        return rig.on_path(min(p + lead, rig.reach_m) if occupied else p)   # hands-off: target on the hand

    until, cue = _cue_at(rig, 0.12, 4.0, 20.0, "LET GO NOW")
    limp = tuple(2.0 * c for c in rig.u[:2]) + (-8.0,)      # sim: a limb resting its 8 N on the handle
    out = rig.run(30.0, target, until=until, live=rig.live_line, watch_after=2.0,
                  sim_script=lambda s: (limp, 150.0) if cue["i"] is None else None)
    if cue["i"] is None:
        rig.recover()
        return Result("FAIL", f"hand only reached {max(rig.along(s.pos) for s in out) * 100:.1f} cm",
                      f"never got to the 12 cm cue point ({_tripped(out) or 'not carried: is a hand on the handle?'})")
    i_rel, seen = _release_index(rig, out, cue["i"])
    after = out[i_rel:]
    travel = max(rig.along(s.pos) for s in after) - rig.along(out[i_rel].pos)
    travel_cue = max(rig.along(s.pos) for s in out[cue["i"]:]) - rig.along(out[cue["i"]].pos)
    v_peak = max(norm(s.vel) for s in after)
    v_end = max(norm(s.vel) for s in out if s.t > out[-1].t - 0.5)
    f_peak = max(rig.rel(s.force) for s in out[:cue["i"] + 1])
    measured = (f"travel after release {travel * 100:.1f} cm ({travel_cue * 100:.1f} cm from the cue); peak speed "
                f"after release {v_peak:.2f} m/s; end speed {v_end:.3f} m/s; peak force while carried {f_peak:.1f} N")
    note = f"stopped by a trip: {_tripped(out)}" if _tripped(out) else ""
    rig.recover()
    if not seen:
        return Result("FAIL", measured, "the handle never read empty after the cue (over "
                      f"{F_PRESENT} N above the start-pose baseline): a hands-off rule cannot see the release here")
    ok = travel <= 0.10 and v_end < 0.02
    return Result("PASS" if ok else "FAIL", measured, note if ok else "expected a stop within 10 cm of the release. " + note)


@check(11, "Letting go in resistance returns slower than 0.20 m/s and stops at the start")
def c11(rig: Rig) -> Result:
    lead = rig.lim.max_lead_m
    rig.wait(f"CHECK 11. Resistance band ({rig.k_resist:.0f} N/m, about {rig.k_resist * lead:.0f} N). Push the handle "
             f"out along the reach against the band. When the terminal beeps LET GO (at 15 cm), open your "
             f"hand at once and keep clear: the handle comes back by itself. (up to 30 s)")
    rig.settle(rig.k_axes(rig.k_resist, rig.k_wall))

    def sim_push(s: Sample):
        p = rig.along(s.pos)
        return (tuple(min(18.0, max(0.0, 400.0 * (0.22 - p))) * c for c in rig.u), 80.0)

    until, cue = _cue_at(rig, 0.15, 6.0, 20.0, "LET GO NOW")
    out = rig.run(30.0, lambda s: rig.on_path(max(rig.along(s.pos) - lead, 0.0)), until=until,
                  live=rig.live_line, watch_after=2.0,
                  sim_script=lambda s: sim_push(s) if cue["i"] is None else None)
    if cue["i"] is None:
        rig.recover()
        return Result("FAIL", f"hand only reached {max(rig.along(s.pos) for s in out) * 100:.1f} cm",
                      f"never got to the 15 cm cue point ({_tripped(out) or 'push further'})")
    i_rel, seen = _release_index(rig, out, cue["i"])
    after = out[i_rel:]
    v_peak = max(norm(s.vel) for s in after)
    tail = [rig.along(s.pos) for s in out if s.t > out[-1].t - 0.5]
    end = sum(tail) / len(tail)
    low = min(rig.along(s.pos) for s in after)
    v_end = max(norm(s.vel) for s in out if s.t > out[-1].t - 0.5)
    f_peak = max(rig.rel(s.force) for s in out[:cue["i"] + 1])
    measured = (f"peak return speed {v_peak:.2f} m/s; stopped {end * 100:+.1f} cm from the start (lowest "
                f"{low * 100:+.1f} cm); end speed {v_end:.3f} m/s; peak push {f_peak:.1f} N")
    trip = _tripped(out)
    rig.recover()
    ok = trip is None and v_peak < 0.20 and -0.01 <= end <= 0.03 and low >= -0.02 and v_end < 0.02
    note = "" if seen else "release not seen in the force; measured from the cue. "
    if trip:
        note += f"tripped on the way back: {trip}"
    elif not ok:
        note += "expected under 0.20 m/s and a stop within 3 cm of the start without overshoot"
    return Result("PASS" if ok else "FAIL", measured, note)


@check(12, "Isometric hold at K_MAX: a push up to the 30 N contact cap stays within 5 cm")
def c12(rig: Rig) -> Result:
    cap, km = rig.lim.max_contact_n, rig.lim.k_max
    rig.wait(f"CHECK 12. Isometric hold at {km:.0f} N/m. Push along the reach direction, build up over 3 s to "
             f"25-{cap:.0f} N (watch the number), hold 1 s, then EASE OFF over a second (do not snap your hand "
             f"away). Do NOT go over {cap:.0f} N. (10 s)")
    rig.settle((km,) * 3)

    def sim_push(s: Sample):
        f = 28.0 * min(1.0, s.t / 3.0) if s.t < 4.5 else 28.0 * (1.0 - (s.t - 4.5) / 1.5) if s.t < 6.0 else None
        return None if f is None else (tuple(f * c for c in rig.u), 0.0)

    out = rig.run(10.0, lambda s: rig.start, live=rig.live_line, sim_script=sim_push)
    i = max(range(len(out)), key=lambda j: rig.rel(out[j].force))
    f_pk, d_at_pk = rig.rel(out[i].force), rig.disp(out[i].pos)
    d_valid = max((rig.disp(s.pos) for s in out if rig.rel(s.force) <= cap), default=0.0)
    k_meas = f_pk / d_at_pk if d_at_pk > 1e-4 else float("nan")
    measured = (f"peak push {f_pk:.1f} N moved the handle {d_at_pk * 100:.1f} cm ({k_meas:.0f} N/m measured); "
                f"largest movement at or under {cap:.0f} N: {d_valid * 100:.1f} cm")
    trip = _tripped(out)
    rig.recover()
    if trip:
        return Result("FAIL", measured, f"tripped: {trip}")
    if f_pk < 20.0:
        return Result("FAIL", measured, "push under 20 N: not a test of the cap, repeat harder")
    ok = d_valid <= 0.05
    return Result("PASS" if ok else "FAIL", measured,
                  "" if ok else f"moved more than 5 cm ({cap:.0f} N / {km:.0f} N/m is {cap / km * 100:.1f} cm by arithmetic)")


@check(13, "Letting go during pull's set-up phase leaves the handle still")
def c13(rig: Rig) -> Result:
    rig.wait("CHECK 13. Pull set-up: the reach axis is free (0 N/m), walls on. Slide the handle along the "
             "reach toward the far end. When the terminal beeps LET GO (at 10 cm), open your hand. "
             "The handle must stay where you left it. (up to 25 s)")
    rig.settle(rig.k_axes(0.0, rig.k_wall))
    until, cue = _cue_at(rig, 0.10, 4.0, 20.0, "LET GO NOW")
    out = rig.run(30.0, lambda s: rig.on_path(min(max(rig.along(s.pos), 0.0), rig.reach_m)), until=until,
                  live=rig.live_line, watch_after=2.0,
                  sim_script=lambda s: (tuple(1.5 * c for c in rig.u), 0.0) if cue["i"] is None else None)
    if cue["i"] is None:
        rig.recover()
        return Result("FAIL", f"hand only reached {max(rig.along(s.pos) for s in out) * 100:.1f} cm",
                      f"never got to the 10 cm cue point ({_tripped(out) or 'slide further'})")
    i_rel, seen = _release_index(rig, out, cue["i"])
    p_rel = rig.along(out[i_rel].pos)
    coast = max(abs(rig.along(s.pos) - p_rel) for s in out[i_rel:])
    tail = [rig.along(s.pos) for s in out if s.t > out[-1].t - 2.0]
    drift = max(tail) - min(tail)
    measured = f"coasted {coast * 100:.1f} cm after release; moved {drift * 1000:.1f} mm in the last 2 s"
    trip = _tripped(out)
    rig.recover()
    ok = trip is None and coast <= 0.03 and drift <= 0.005
    note = "" if seen else "release not seen in the force; measured from the cue. "
    if trip:
        note += f"tripped: {trip}"
    elif not ok:
        note += "expected under 3 cm of coasting and no drift (a drifting free axis means the tool mass/CoM is off)"
    return Result("PASS" if ok else "FAIL", measured, note)


@check(14, "Ctrl+C leaves the arm in hold")
def c14(rig: Rig) -> Result:
    rig.wait("CHECK 14. HANDS OFF. When the stream is running, press Ctrl+C ONCE. (20 s)")
    rig.say("    stream running: press Ctrl+C now")
    pressed = False

    def sim_ctrl_c(s: Sample, out) -> bool:
        if rig.sim and s.t >= 0.5:
            raise KeyboardInterrupt
        return False

    try:
        rig.run(20.0, lambda s: rig.start, until=sim_ctrl_c)
    except KeyboardInterrupt:
        pressed = True
        rig.arm.hold()                       # what this script (and server.run) does on Ctrl+C
    s0 = rig.state()
    for _ in range(200):                     # 2 s with no commands at all
        rig.tick()
    s1 = rig.state()
    k = rig.commanded_k()
    moved = math.dist(s0.pos, s1.pos)
    measured = f"mode {s1.mode}; stiffness sent {[round(v) for v in k]}; moved {moved * 1000:.1f} mm in 2 s"
    if not pressed:
        return Result("FAIL", measured, "Ctrl+C was not pressed within 20 s: repeat")
    ok = s1.mode == "hold" and all(abs(v - rig.lim.k_hold) < 1e-6 for v in k) and moved <= 0.01
    return Result("PASS" if ok else "FAIL", measured, "" if ok else "expected mode hold at k_hold, not moving")


@check(15, "After close() the stiffness is back to K_x_nom")
def c15(rig: Rig) -> Result:
    rig.say("  CHECK 15. Closing the arm (hold, nominal stiffness, Stop). No prompt, no motion.")
    rig.arm.close()
    if rig.spy is None:
        return Result("N/A-SIM", "close() ran", "SimArm has no nominal stiffness to restore")
    k = rig.spy.k
    mode = getattr(rig.spy, "mode", None)
    mode_s = str(mode()) if callable(mode) else "n/a"
    measured = f"last stiffness sent {k}; last call {rig.spy.calls[-1] if rig.spy.calls else None}; robot mode {mode_s}"
    ok = (k is not None and rig.k_nom is not None and len(k) == 6
          and all(abs(a - float(b)) < 1e-6 for a, b in zip(k, rig.k_nom))
          and bool(rig.spy.calls) and rig.spy.calls[-1] == "Stop" and not rig.spy.fault())
    return Result("PASS" if ok else "FAIL", measured,
                  "evidence is the command arm.py sent and the robot accepted; flexivrdk 1.7.0 has no getter "
                  "for the active stiffness" if ok else "expected K_x_nom then Stop, no fault")


SIM_LIMITED = {10: "SimArm has no robot-side speed limit and little damping",
               11: "SimArm has no robot-side speed limit and little damping: a released band trips the speed limit"}


# --------------------------------------------------------------------------- runner

def run_checks(rig: Rig, only: set[int] | None = None, stop_on_fail: bool = True) -> list[dict]:
    """Run the checks in order. Always closes the arm. Returns one dict per check run."""
    results: list[dict] = []
    closed = False
    try:
        for num, title, fn in CHECKS:
            if only is not None and num not in only and num != 1:
                continue
            if num == 15:
                closed = True
            try:
                res = fn(rig)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001  (a crashed check is a FAIL, and the arm goes to hold)
                try:
                    rig.arm.hold()
                except Exception:  # noqa: BLE001
                    pass
                res = Result("FAIL", "check crashed", repr(exc))
            if rig.sim and res.status == "FAIL" and num in SIM_LIMITED:
                res = Result("N/A-SIM", res.measured, f"{SIM_LIMITED[num]}. {res.note}".strip())
            results.append(dict(num=num, title=title, status=res.status, measured=res.measured, note=res.note))
            rig.say(f"  ==> {num:>2}. {title}: {res.status}\n        {res.measured}"
                    + (f"\n        {res.note}" if res.note else "") + "\n")
            if res.status == "FAIL" and stop_on_fail and not rig.sim and num != 15:
                if rig.live and not closed:
                    rig.arm.hold()
                rig.say("  *** FAIL. Nobody holds the handle until this is fixed and re-run. ***")
                if rig.ask("  Type 'continue' to run the remaining checks, anything else stops: ").strip().lower() != "continue":
                    raise Abort
    except KeyboardInterrupt:
        rig.say("\n  Ctrl+C: holding, then closing.")
        try:
            rig.arm.hold()
        except Exception:  # noqa: BLE001
            pass
    except Abort:
        rig.say("  Stopped by the operator after a FAIL.")
    finally:
        if not closed:
            try:
                rig.arm.close()
            except Exception as exc:  # noqa: BLE001
                rig.say(f"  arm.close() raised {exc!r}: run python robot/recover.py")
    return results


def markdown(results: list[dict]) -> str:
    rows = ["| # | Check | Result | Measured | Note |", "|---|---|---|---|---|"]
    for r in results:
        rows.append(f"| {r['num']} | {r['title']} | {r['status']} | {r['measured']} | {r['note']} |")
    return "\n".join(rows)


def build_sim(args) -> Rig:
    from software.sim_arm import PASSIVE_LOAD_N, SimArm   # sim only: robot/ does not import software/ otherwise
    axis = {"x": 0, "y": 1}[args.reach_axis or "y"]       # Layout B: reach along world y
    hand = ScriptedHand(PASSIVE_LOAD_N)
    arm = SimArm(hand, limits_for_reach_axis(Limits(), axis), start_pos=(0.50, 0.0, 0.30), realtime=False)
    arm.reach_axis, arm.reach_sign = axis, args.reach_sign or 1
    arm.connect()
    return Rig(arm, sim=True, reach_sign=args.reach_sign or 1, hand=hand, k_wall=args.k_wall,
               k_assist=args.k_assist, k_resist=args.k_resist, reach_m=args.reach_m)


def build_real(args) -> Rig:
    raw = json.loads((Path(__file__).with_name("config.json")).read_text(encoding="utf-8"))
    serial = args.serial or str(raw["serial"])
    if "XXXX" in serial:
        raise SystemExit("robot/config.json still has the placeholder serial: pass --serial Rizon4-062157")
    if args.reach_axis is not None and {"x": 0, "y": 1}[args.reach_axis] != int(raw["reach_axis"]):
        raise SystemExit("--reach-axis differs from robot/config.json reach_axis; on the real arm the box is "
                         "laid out from the config, so set it there")
    sign = args.reach_sign or int(raw.get("reach_sign", 1))
    import flexivrdk

    robot = flexivrdk.Robot(serial)
    problems = []
    if robot.fault():
        problems.append("the robot reports a fault (robot/recover.py)")
    if not robot.operational():
        problems.append("the robot is not operational (Servo ON in Elements, e-stop released?)")
    if not str(robot.mode()).endswith("IDLE"):
        problems.append(f"the robot is in {robot.mode()}, not IDLE (is another program driving it?)")
    if not robot.estop_released():
        problems.append("the e-stop is pressed")
    tool = flexivrdk.Tool(robot).name()
    if args.tool != "any" and tool != args.tool:
        problems.append(f"the active tool is {tool!r}, expected {args.tool!r} (robot/tool_handle.md)")
    if problems:
        raise SystemExit("NOT READY: " + "; ".join(problems) + ". This script never enables or clears faults.")
    k_nom = [float(v) for v in robot.info().K_x_nom]
    arm = Arm(serial)
    spy = Spy(robot)
    arm._attach(spy, flexivrdk, k_nom)        # never Arm.connect(): no Enable(), no ClearFault()
    print(f"connected to {serial}: tool {tool!r}, K_x_nom {k_nom}, reach axis {'xy'[arm.reach_axis]} sign {sign:+d}")
    if arm.config.placeholders:
        print(f"WARNING: robot/config.json still lists placeholders: {sorted(arm.config.placeholders)}")
    return Rig(arm, sim=False, reach_sign=sign, spy=spy, k_nom=k_nom, k_wall=args.k_wall,
               k_assist=args.k_assist, k_resist=args.k_resist, reach_m=args.reach_m)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Interactive safety checks for the rehab arm (K2).")
    ap.add_argument("--sim", action="store_true", help="dry run on SimArm (no robot, no prompts)")
    ap.add_argument("--serial", help="robot serial (default robot/config.json)")
    ap.add_argument("--tool", default="RehabHandle", help="tool that must be active ('any' to skip; default RehabHandle)")
    ap.add_argument("--reach-axis", choices=["x", "y"], help="sim only (default y); the real arm uses config.json")
    ap.add_argument("--reach-sign", type=int, choices=[1, -1], help="+1 if the reach goes toward +axis (default: config.json reach_sign, else +1)")
    ap.add_argument("--only", help="comma-separated check numbers, e.g. 7,8")
    ap.add_argument("--list", action="store_true", help="list the checks and exit")
    ap.add_argument("--k-wall", type=float, default=K_WALL)
    ap.add_argument("--k-assist", type=float, default=K_ASSIST)
    ap.add_argument("--k-resist", type=float, default=K_RESIST)
    ap.add_argument("--reach-m", type=float, default=REACH_M)
    ap.add_argument("--out", help="folder for the result file (default robot/results)")
    args = ap.parse_args(argv)
    if args.list:
        for num, title, _ in CHECKS:
            print(f"{num:>2}. {title}")
        return 0
    only = {int(v) for v in args.only.split(",")} if args.only else None

    rig = build_sim(args) if args.sim else build_real(args)
    lim = rig.lim
    print(f"limits: k_max {lim.k_max:.0f} N/m, k_hold {lim.k_hold:.0f}, lead {lim.max_lead_m * 100:.0f} cm, "
          f"speed {lim.max_linear_vel} m/s, trips {lim.trip_speed} m/s / {lim.trip_force:.0f} N, contact cap "
          f"{lim.max_contact_n:.0f} N, watchdog {lim.watchdog_s} s, box (x,y,z) +/-{lim.box_half_m} m")
    if not args.sim:
        print("\nBefore 'go': e-stop holder named and in place; technician present; workspace clear;\n"
              "handle tight; nobody within reach. The arm switches to Cartesian mode after check 1.")
        if input("Type go to start: ").strip().lower() != "go":
            rig.arm.close()
            print("not started")
            return 1

    results = run_checks(rig, only)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_dir = Path(args.out) if args.out else Path(__file__).with_name("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"safety_check_{stamp}_{'sim' if args.sim else 'arm'}.json"
    out.write_text(json.dumps(dict(when=stamp, sim=args.sim, reach_axis="xy"[rig.axis], reach_sign=rig.sign,
                                   limits=lim.__dict__, k_wall=rig.k_wall, k_assist=rig.k_assist,
                                   k_resist=rig.k_resist, baseline=rig.baseline, results=results), indent=2),
                   encoding="utf-8")
    n_pass = sum(r["status"] == "PASS" for r in results)
    n_fail = sum(r["status"] == "FAIL" for r in results)
    print("\n" + markdown(results))
    print(f"\n{n_pass} PASS, {n_fail} FAIL, {len(results) - n_pass - n_fail} not applicable, of {len(results)} run "
          f"({len(CHECKS)} checks exist){'  [SIMULATED]' if args.sim else ''}")
    print(f"saved {out}\nCopy the table into robot/SAFETY.md.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
