"""Soak of the pitch demo (DECISIONS 15 Nov 20:00): Push at four fixed levels on software/simple.py,
driven through the real server routes (server.api.create_app: HTTP, Hub, SQLite, the default engine
factory, the websocket feed) on one SimArm kept across 40 back-to-back sessions, like `server.run --sim`
keeps one arm. SimArm has 4.5 N Coulomb friction and the measured empty-handle reading (3 N across the
reach with pose, 3 to 7 N while moving). All of it is simulated.

Independent of simple.py: nothing is imported from it and the numbers below are the ones in its
docstring and in DECISIONS, written out again. The hand is scripted (``Hand``); what "really happened"
is read from the simulated arm itself (true position, the hand's presence, every ``home()`` call), never
from the engine.

Each session draws a level, a strength (the most the hand can push) and a tempo. The 40 are:
12 plain sets (some with pushes that stop short, some with a hands-off pause), 6 with level changes in
the middle of a set, 2 where the hand is too weak for level 4 until the level is lowered, 5 with a
let-go at full reach, 5 that are stopped with the hand still on the handle (resting at the start, holding
10 cm out, or stopped by the app the moment the last rep is counted), 2 stopped while a let-go handle is
still gliding back, 4 started with the handle 10 cm from the start pose (2 empty, 2 with a hand resting on
it), and 4 with nobody at all (one per level).

What this cannot show (sim time is stepped, SimArm(realtime=False)):
- the engine's own 100 Hz thread and the helper thread for zero and home do not run;
- ``SimArm.home()`` is instantaneous, so "never pushes against a hand" can only be checked as "home() is
  never called with a hand on the handle"; the guard that holds the arm during a move is not exercised;
- /api/state cannot be polled while POST /api/session/stop is running (it blocks, as on the arm).

The soak runs once (about 50 s); each requirement is its own test so one failure does not hide the rest.

Three requirements do not hold on simple.py as of 15 Nov 23:30 and are marked ``xfail(strict=True)`` so
main stays green; numbers in context/LOG.md (Shiv, 15 Nov 23:30). When simple.py or the server changes
and one of them starts passing, pytest reports it as a failure: remove its marker then.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from server.api import create_app
from software.sim_arm import SimArm

SEED = 20261115
N_SESSIONS = 40
DT = 0.01
START = (0.45, 0.0, 0.30)
REAL = dict(empty_force_pose_n_per_m=(10.0, 0.0, 0.0), empty_force_moving_n=(3.0, 7.0), friction_n=4.5)
LEVEL_N = {1: 10.0, 2: 15.0, 3: 20.0, 4: 28.0}     # level -> band force, N
OUT_M, BACK_M = 0.20, 0.05      # a rep: out past 20 cm, counted when back within 5 cm of the start
HAND_N = 6.0                    # a hand pressing more than this must keep the arm from moving by itself
FAR_M = 0.10                    # "the handle 10 cm from the start pose"
EMPTY_MOVE_M = 0.002            # an empty handle may not move away from the start by more than this
AT_START_M = 0.005              # "returned to the start"
FIELDS = ("rep_count", "phase", "level", "message", "countdown_s")
POLL_EVERY = 20                 # GET /api/state every 0.2 s of sim time
HAND_ON_KINDS = ("hand_rest_end", "hand_out_end", "stop_on_count")
KINDS = (["plain"] * 12 + ["level"] * 6 + ["weak_then_lower"] * 2 + ["release"] * 5
         + ["hand_rest_end", "hand_rest_end", "hand_out_end", "stop_on_count", "stop_on_count"]
         + ["glide_stop"] * 2 + ["far_empty"] * 2 + ["far_hand"] * 2 + ["empty"] * 4)
assert len(KINDS) == N_SESSIONS


def _mj(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x ** 3 * (10 - 15 * x + 6 * x * x)


class Hand:
    """A scripted hand on the handle: it follows a planned position along the reach (minimum jerk out,
    dwell, back) with at most ``cap`` newtons. SimArm adds 8 N of limb weight while it is present, so a
    hand on the handle always reads more than 6 N. ``strength`` 0 switches SimArm's own friction helper
    off: this hand pushes through the friction by itself."""
    strength = 0.0

    def __init__(self, kp: float = 1500.0, kd: float = 40.0) -> None:
        self.kp, self.kd, self.cap = kp, kd, 36.0
        self.present = False
        self.rest = 0.0
        self.move: tuple | None = None
        self.fade: tuple[float, float] | None = None
        self.release_at: float | None = None

    def grip(self, s_now: float) -> None:
        """Take the handle where it is, without a jolt."""
        self.present, self.rest, self.move, self.fade, self.release_at = True, float(s_now), None, None, None

    def push(self, t: float, depth: float, out_s: float, dwell_s: float, back_s: float | None) -> None:
        """Out to ``depth``, dwell, back to the start. ``back_s`` None: stay out there."""
        self.move = (t, self.plan(t), depth, out_s, dwell_s, back_s)

    def plan(self, t: float) -> float:
        if self.move is None:
            return self.rest
        t0, s0, depth, out_s, dwell_s, back_s = self.move
        u = t - t0
        if u < out_s:
            return s0 + (depth - s0) * _mj(u / out_s)
        if back_s is None or u < out_s + dwell_s:
            return depth
        return depth * (1.0 - _mj((u - out_s - dwell_s) / back_s))

    def release(self, t: float, over_s: float = 0.0) -> None:
        if over_s <= 0:
            self.present = False
        else:
            self.fade = (t, over_s)

    def effort(self, t, pos, vel, goal):
        if self.release_at is not None and t >= self.release_at:
            self.release_at, self.present = None, False
            return np.zeros(3)
        f = float(np.clip(self.kp * (self.plan(t) - (pos[0] - START[0])) - self.kd * vel[0], -self.cap, self.cap))
        out = np.array([f, 0.0, 0.0])
        if self.fade is not None:
            out *= max(0.0, 1.0 - (t - self.fade[0]) / self.fade[1])
            if t - self.fade[0] >= self.fade[1]:
                self.present = False
        return out


class _Tripped(Exception):
    pass


class Soak:
    def __init__(self, client, hub, arm: SimArm, hand: Hand, rng) -> None:
        self.c, self.hub, self.arm, self.hand, self.rng = client, hub, arm, hand, rng
        self.rec: dict = {}
        self.eng = None
        self.trace: list[tuple] = []        # per physics step: t, s, dist, speed, hand present, arm mode, reading
        self.n = 0
        real_step, real_home = arm.step, arm.home

        def step(dt):
            real_step(dt)
            self.trace.append((arm._t, self.s, self.dist, float(np.linalg.norm(arm._vel)), hand.present, arm._mode,
                               float(np.linalg.norm(arm._measured_force()))))

        def home():
            # what was on the handle the moment the arm set off by itself
            person = float(np.linalg.norm(arm._person_force(arm._t, arm._pos, arm._vel)))
            self.rec["homes"].append({"t": arm._t, "hand_on": bool(hand.present), "hand_force_n": round(person, 1),
                                      "from_m": round(self.dist, 4), "stage": self.stage})
            real_home()

        arm.step, arm.home = step, home     # also what the engine calls during its countdowns

    # ---------------------------------------------------------------- truth
    @property
    def s(self) -> float:
        return float(self.arm._pos[0] - START[0])

    @property
    def dist(self) -> float:
        return float(np.linalg.norm(self.arm._pos - np.array(START)))

    @property
    def stage(self) -> str:
        return "stop" if self.rec.get("stopping") else getattr(self.eng, "stage", "none")

    # ---------------------------------------------------------------- the app's view
    def poll(self, where: str | None = None) -> dict:
        st = self.c.get("/api/state").json()
        self.rec["polls"] += 1
        bad = [k for k in FIELDS if k not in st]
        if not bad:
            if not isinstance(st["rep_count"], int):
                bad.append(f"rep_count={st['rep_count']!r}")
            if st["phase"] not in ("idle", "out", "back"):
                bad.append(f"phase={st['phase']!r}")
            if st["level"] not in LEVEL_N:
                bad.append(f"level={st['level']!r}")
            if not (st["message"] is None or isinstance(st["message"], str)):
                bad.append(f"message={st['message']!r}")
            if not (st["countdown_s"] is None or isinstance(st["countdown_s"], (int, float))):
                bad.append(f"countdown_s={st['countdown_s']!r}")
        if bad:
            self.rec["first_poll_bad" if where == "first" else "bad_polls"].append((where or self.stage, bad))
        if st.get("arm_fault"):
            self.rec["arm_fault_seen"] = st["arm_fault"]
        return st

    # ---------------------------------------------------------------- driving
    def tick(self, seconds: float) -> None:
        for _ in range(int(round(seconds / DT))):
            self.eng.tick()
            self.arm.step(DT)
            self.n += 1
            if self.n % POLL_EVERY == 0:
                self.poll()
            if self.arm._mode == "hold" and self.eng.stage == "band" and not self.rec["trip"]:
                self.rec["trip"] = {"fault": self.arm._fault, "s_m": round(self.s, 3), "level": self.eng.level,
                                    "hand_on": bool(self.hand.present),
                                    "speed": round(max(r[3] for r in self.trace[-30:]), 3),
                                    "reading_n": round(max(r[6] for r in self.trace[-30:]), 1)}
                self.poll()
                raise _Tripped()

    def idle_steps(self, seconds: float) -> None:
        """No session running: only the arm's physics moves on."""
        for _ in range(int(round(seconds / DT))):
            self.arm.step(DT)

    def start(self, level: int, reps: int) -> None:
        self.hand.present = False                    # hands off for the countdown, as the screen says
        r = self.c.post("/api/session/start", json={"patient_id": f"soak-{self.rec['i']:02d}",
                                                    "exercise": f"push_{level}", "reps": max(1, reps)})
        assert r.status_code == 200, r.text
        self.rec["sid"], self.rec["levels"] = r.json()["session_id"], [level]
        self.eng = self.hub.engine
        self.poll("first")                           # before the first control tick

    def wait_band(self, limit_s: float = 30.0) -> None:
        t0 = self.arm._t
        while self.eng.stage != "band":
            if self.eng.stage == "error" or self.arm._t - t0 > limit_s:
                raise RuntimeError(f"the band never came on: stage {self.eng.stage}, "
                                   f"message {self.eng.snapshot().get('message')!r}")
            self.tick(0.05)
        self.rec["band_i0"] = len(self.trace)
        self.rec["band_from_m"] = round(self.dist, 4)

    def level(self, n: int) -> None:
        r = self.c.post("/api/level", json={"level": n})
        assert r.status_code == 200, r.text
        self.rec["levels"].append(n)

    def tempo(self) -> dict:
        r = self.rng
        t = dict(out_s=float(r.uniform(2.0, 5.0)), dwell_s=float(r.uniform(0.2, 1.0)),
                 back_s=float(r.uniform(2.0, 5.0)), rest_s=float(r.uniform(0.6, 2.0)))
        self.rec["tempo"] = {k: round(v, 2) for k, v in t.items()}
        return t

    def strength(self, level_max: int) -> None:
        """The most this hand can push: at least the level plus friction and drag, under the arm's 40 N trip."""
        lo = LEVEL_N[level_max] + 7.0
        self.hand.cap = float(self.rng.uniform(lo, max(lo + 1.0, 36.0)))
        self.rec["strength_n"] = round(self.hand.cap, 1)

    def push(self, tp: dict, depth: float | None = None, at: list | None = None, rest: bool = True) -> None:
        """One push out and back. ``at``: [(seconds into the push, callable)] run on the way."""
        depth = float(self.rng.uniform(0.26, 0.30)) if depth is None else depth
        self.hand.push(self.arm._t, depth, tp["out_s"], tp["dwell_s"], tp["back_s"])
        total, done = tp["out_s"] + tp["dwell_s"] + tp["back_s"], 0.0
        for when, fn in sorted(at or [], key=lambda x: x[0]):
            self.tick(max(0.0, when - done))
            done = max(done, when)
            fn()
        self.tick(total - done + 0.3)
        if rest:
            self.tick(tp["rest_s"])

    def let_go_at_full_reach(self, tp: dict) -> float:
        """Push to full reach, let go there (abruptly or over 0.1 s). Returns the fade time."""
        over = 0.0 if self.rng.random() < 0.5 else 0.1
        self.hand.push(self.arm._t, float(self.rng.uniform(0.27, 0.30)), tp["out_s"], 30.0, None)
        self.tick(tp["out_s"] + 0.4)
        self.rec["release_s_m"] = round(self.s, 3)
        self.hand.release(self.arm._t, over)
        self.rec["released"] = "abrupt" if over == 0 else "over 0.1 s"
        return over

    def glide_home(self, limit_s: float = 40.0) -> None:
        """Nobody on the handle: wait until it has come back and stands still."""
        i0, t0 = len(self.trace), self.arm._t
        while not (self.s < BACK_M and self.trace[-1][3] < 0.002) and self.arm._t - t0 < limit_s:
            self.tick(0.1)
        self.tick(0.5)
        self.rec["glide"] = {"peak_speed": round(max(r[3] for r in self.trace[i0:]), 3),
                             "seconds": round(self.arm._t - t0, 1), "ends_at_m": round(self.s, 3)}

    def stop(self, after_s: float = 5.0) -> None:
        rec = self.rec
        st = self.poll()
        rec["state_count"], rec["state_mode"] = st.get("rep_count"), st.get("arm_mode")
        rec["band_i1"] = len(self.trace)
        rec["hand_on_at_stop"], rec["stop_s_m"] = bool(self.hand.present), round(self.s, 4)
        rec["stop_speed"], rec["stop_reading_n"] = round(self.trace[-1][3], 3), round(self.trace[-1][6], 1)
        t0 = self.arm._t
        rec["stopping"] = True
        r = self.c.post("/api/session/stop")
        assert r.status_code == 200, r.text
        rec["stop_took_s"] = round(self.arm._t - t0, 2)          # sim seconds the engine itself waited
        rec["summary_n"], rec["summary_exercise"] = r.json()["n_reps"], r.json()["exercise"]
        reps = self.c.get(f"/api/sessions/{rec['sid']}/reps").json()
        rec["db_n"], rec["db_idx"] = len(reps), [x["idx"] for x in reps]
        rec["db_ok"] = all(x["mode"] == "resist" and x["completed"] and x["simulated"] for x in reps)
        rec["stop_message"] = self.eng.snapshot().get("message")
        rec["mode_after_stop"] = self.arm._mode
        self.idle_steps(after_s)                    # a hand still on the handle lets go in here
        self.hand.present = False
        self.idle_steps(1.0)
        rec["end_mode"], rec["end_m"] = self.arm._mode, round(self.dist, 4)

    def place_far(self) -> None:
        """Between sessions: the handle is left 10 cm from the start pose."""
        self.arm._pos = np.array([START[0] + FAR_M, START[1], START[2]])
        self.arm._vel = np.zeros(3)
        self.arm._target = self.arm._pos.copy()

    # ---------------------------------------------------------------- the 40 sessions
    def session(self, i: int, kind: str, empty_level: int | None) -> dict:
        rng = self.rng
        self.rec = rec = {"i": i, "kind": kind, "seed": SEED, "expected": 0, "polls": 0, "bad_polls": [],
                          "first_poll_bad": [], "homes": [], "trip": None, "crash": None, "start_i": len(self.trace),
                          "start_m": None}
        try:
            level = empty_level or int(rng.integers(1, 5))
            if kind == "weak_then_lower":
                level = 4
            if kind in ("far_empty", "far_hand"):
                self.place_far()
            rec["start_m"] = round(self.dist, 4)
            tp = self.tempo()
            n = int(rng.integers(3, 6))
            changes = []
            if kind == "level":
                for _ in range(int(rng.integers(1, 4))):
                    changes.append((int(rng.integers(0, n)), float(rng.uniform(0.0, 1.0)), int(rng.integers(1, 5))))
            self.strength(max([level] + [c[2] for c in changes]))
            if kind == "weak_then_lower":
                self.hand.cap = float(rng.uniform(18.0, 22.0))       # cannot stretch a 28 N band past 5 cm
                rec["strength_n"] = round(self.hand.cap, 1)
            self.start(level, n)

            if kind == "far_hand":
                # a hand rests on the handle through more than one countdown: the arm must stay where it is
                self.hand.grip(self.s)
                i0 = len(self.trace)
                self.tick(float(rng.uniform(4.0, 7.0)))
                rec["far_hand"] = {"homes_under_hand": len(rec["homes"]), "stage": self.eng.stage,
                                   "moved_m": round(max(abs(r[1] - FAR_M) for r in self.trace[i0:]), 4),
                                   "countdown_s": self.poll().get("countdown_s"),
                                   "reading_n": round(self.trace[-1][6], 1)}
                self.hand.present = False
            self.wait_band()
            self.tick(float(rng.uniform(0.5, 1.5)))                  # the band is on, nobody on the handle yet

            if kind == "empty":
                self.tick(20.0)
            else:
                self.hand.grip(self.s)
                self.tick(0.3)
                self.reps(kind, tp, n, changes)
            if kind not in HAND_ON_KINDS + ("glide_stop",) and kind != "empty":
                self.hand.present = False                             # set done: hands off, then stop
                self.tick(float(rng.uniform(1.0, 2.0)))
        except _Tripped:
            self.hand.present = False
        except Exception as e:                                        # one bad session never ends the soak
            rec["crash"] = repr(e)
            self.hand.present = False
        try:
            if self.hub.session is not None:
                self.stop()
        except Exception as e:
            rec["crash"] = (rec["crash"] or "") + f" stop: {e!r}"
            try:
                self.hub.stop_session()
            except Exception:
                pass
        self.hand.present, self.hand.release_at = False, None
        rec.setdefault("end_mode", self.arm._mode)
        rec.setdefault("end_m", round(self.dist, 4))
        self.analyse(rec)
        return rec

    def reps(self, kind: str, tp: dict, n: int, changes: list) -> None:
        rng, rec, hand = self.rng, self.rec, self.hand
        if kind == "weak_then_lower":
            for _ in range(2):
                self.push(tp)                        # 18 to 22 N against 28 N: stalls about 3 cm out, no rep
            self.level(1)
            self.tick(0.8)
        short_at = set(rng.choice(n, size=int(rng.integers(1, 3)), replace=False).tolist()) \
            if kind == "plain" and rng.random() < 0.5 else set()
        pause_at = int(rng.integers(0, n)) if kind == "plain" and rng.random() < 0.4 else None
        release_at = int(rng.integers(0, n)) if kind == "release" else None
        total = tp["out_s"] + tp["dwell_s"] + tp["back_s"]
        for k in range(n):
            last = k == n - 1
            if k in short_at:
                self.push(tp, depth=float(rng.uniform(0.08, 0.15)))   # stops short of 20 cm: not a rep
                rec["short_pushes"] = rec.get("short_pushes", 0) + 1
                continue
            if k == release_at or (last and kind == "glide_stop"):
                self.let_go_at_full_reach(tp)
                if kind == "glide_stop":
                    self.tick(float(rng.uniform(0.3, 1.0)))            # stopped while it glides back, nobody on it
                    return
                self.glide_home()
                rec["expected"] += 1                                    # it was out past 20 cm and came back
                hand.grip(self.s)
                self.tick(tp["rest_s"])
                continue
            at = [(frac * total, (lambda lv=lv: self.level(lv))) for kk, frac, lv in changes if kk == k]
            if last and kind == "stop_on_count":
                # the app leaves the run screen and stops the session the moment the last rep is counted
                hand.push(self.arm._t, float(rng.uniform(0.26, 0.30)), tp["out_s"], tp["dwell_s"], tp["back_s"])
                t0 = self.arm._t
                while self.eng.rep_count < rec["expected"] + 1 and self.arm._t - t0 < total + 5.0:
                    self.tick(DT)
                rec["expected"] += 1
                hand.release_at = t0 + total + 1.0   # the hand finishes coming back, then lets go
                return
            self.push(tp, at=at)
            rec["expected"] += 1
            if k == pause_at:
                hand.present = False                 # hands off for a moment in the middle of the set
                self.tick(float(rng.uniform(1.5, 3.0)))
                hand.grip(self.s)
                self.tick(0.3)
        if kind == "hand_out_end":
            hand.push(self.arm._t, FAR_M, 1.5, 30.0, None)             # set done, the hand holds it 10 cm out
            self.tick(2.5)
        if kind in ("hand_rest_end", "hand_out_end"):
            self.tick(float(rng.uniform(0.5, 1.5)))
            hand.release_at = self.arm._t + 1.5      # lets go 1.5 s into the "returning to start" countdown

    # ---------------------------------------------------------------- what really happened
    def analyse(self, rec: dict) -> None:
        i0, i1 = rec.get("band_i0"), rec.get("band_i1", len(self.trace))
        band = self.trace[i0:i1] if i0 is not None else []
        # reps from the true handle position
        out, truth = False, 0
        for r in band:
            if r[1] >= OUT_M:
                out = True
            elif out and r[1] <= BACK_M:
                out, truth = False, truth + 1
        rec["truth"] = truth
        rec["peak_reading_n"] = round(max((r[6] for r in band), default=0.0), 1)
        rec["peak_speed"] = round(max((r[3] for r in band), default=0.0), 3)
        # an empty handle under the band: how far it ever moved AWAY from the start
        worst, low = 0.0, None
        for r in band:
            if r[4]:
                low = None
                continue
            low = r[2] if low is None else min(low, r[2])
            worst = max(worst, r[2] - low)
        rec["empty_moved_away_m"] = round(worst, 4)
        rec["empty_steps"] = sum(1 for r in band if not r[4])
        rec["homes_under_hand"] = [h for h in rec["homes"] if h["hand_on"] and h["hand_force_n"] > HAND_N]


def run_soak(db_path, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    kinds = list(KINDS)
    rng.shuffle(kinds)
    hand = Hand()
    arm = SimArm(hand, start_pos=START, realtime=False, **REAL)
    app = create_app(lambda: arm, db_path, site_dir=str(db_path) + ".nosite",
                     live_exercises=[f"push_{n}" for n in LEVEL_N])
    feed: list[dict] = []
    sessions = []
    with TestClient(app) as c:
        with c.websocket_connect("/ws/live") as ws:
            def read():
                try:
                    while True:
                        feed.append(ws.receive_json())
                except Exception:
                    pass
            reader = threading.Thread(target=read, name="soak-feed", daemon=True)
            reader.start()
            soak = Soak(c, app.state.hub, arm, hand, rng)
            empty_levels = iter(LEVEL_N)
            for i, kind in enumerate(kinds):
                sessions.append(soak.session(i, kind, next(empty_levels) if kind == "empty" else None))
            time.sleep(0.3)                          # the last messages of the feed
        reader.join(2.0)
    return {"sessions": sessions, "feed": feed, "seed": seed}


@pytest.fixture(scope="module")
def soak(tmp_path_factory):
    out = run_soak(tmp_path_factory.mktemp("soak") / "soak.db")
    crashed = [(s["i"], s["kind"], s["crash"]) for s in out["sessions"] if s["crash"]]
    assert not crashed, crashed
    return out


def _lines(rows) -> str:
    return "\n" + "\n".join(str(r) for r in rows)


# --------------------------------------------------------------------------- the requirements

def test_forty_sessions_ran_with_every_case(soak):
    ss = soak["sessions"]
    assert len(ss) == N_SESSIONS and sorted(s["kind"] for s in ss) == sorted(KINDS)
    assert {lv for s in ss for lv in s["levels"]} == set(LEVEL_N)
    assert sum(len(s["levels"]) > 1 for s in ss) >= 8                 # level changes in the middle of a set
    assert sum("released" in s for s in ss) >= 7 and sum(s["hand_on_at_stop"] for s in ss) >= 5
    assert sum(s["start_m"] > FAR_M - 0.005 for s in ss) >= 4          # started 10 cm from the start pose
    assert sum(s["expected"] for s in ss) >= 100


def test_rep_counts_are_exact(soak):
    """What the state said before stop, the stop summary, the stored reps and the feed's rep messages all
    equal the reps the hand really made (planned, and read back from the true handle position)."""
    feed_n: dict = {}
    for m in soak["feed"]:
        if m.get("type") == "rep":
            feed_n[m["session_id"]] = feed_n.get(m["session_id"], 0) + 1
    wrong = []
    for s in soak["sessions"]:
        counts = (s["truth"], s["state_count"], s["summary_n"], s["db_n"], feed_n.get(s["sid"], 0))
        if (any(n != s["expected"] for n in counts) or s["db_idx"] != list(range(s["expected"])) or not s["db_ok"]
                or s["summary_exercise"] != f"push_{s['levels'][-1]}"):
            wrong.append((s["i"], s["kind"], "levels", s["levels"], "expected", s["expected"],
                          "truth/state/summary/db/feed", counts, s["tempo"], s["strength_n"]))
    assert not wrong, _lines(wrong)


def test_no_trips(soak):
    trips = [(s["i"], s["kind"], s["levels"], s["trip"] or s.get("arm_fault_seen"), s["tempo"], s["strength_n"])
             for s in soak["sessions"] if s["trip"] or s.get("arm_fault_seen") or s["state_mode"] != "compliant"]
    assert not trips, _lines(trips)
    assert max(s["peak_speed"] for s in soak["sessions"]) < 0.40       # the arm's speed trip
    assert max(s["peak_reading_n"] for s in soak["sessions"]) < 40.0   # ... and its force trip


def test_an_empty_handle_never_leaves_the_start(soak):
    """With the band on and nobody on the handle (before the first push, hands-off pauses, the four sessions
    with nobody, a let-go handle on its way back) it never moves away from the start, and counts nothing."""
    ss = soak["sessions"]
    assert sum(s["empty_steps"] for s in ss) > 15000                   # over 150 s of empty handle in all
    moved = [(s["i"], s["kind"], s["levels"], s["empty_moved_away_m"]) for s in ss
             if s["empty_moved_away_m"] > EMPTY_MOVE_M]
    assert not moved, _lines(moved)
    for s in ss:
        if s["kind"] == "empty":
            assert s["truth"] == s["state_count"] == s["db_n"] == 0 and s["peak_speed"] < 0.01, s


def test_the_arm_never_sets_off_by_itself_against_a_hand(soak):
    """home() (at start from 10 cm out, and at stop) is never called with a hand pressing over 6 N on the handle."""
    ss = soak["sessions"]
    under = [(s["i"], s["kind"], s["homes_under_hand"]) for s in ss if s["homes_under_hand"]]
    assert not under, _lines(under)
    far = [s for s in ss if s["kind"] == "far_hand"]
    assert len(far) == 2
    for s in far:
        f = s["far_hand"]
        # through more than one countdown with the hand on it: still counting, the handle where it was
        assert f["homes_under_hand"] == 0 and f["stage"] == "countdown" and f["moved_m"] < 0.002, s
        assert f["reading_n"] > HAND_N and f["countdown_s"] == pytest.approx(3.0, abs=0.05), s
        # ... and once the hand was off, the arm did go to the start before the band came on
        assert [h["hand_on"] for h in s["homes"]][:1] == [False] and s["band_from_m"] < AT_START_M, s
    for s in ss:
        if s["start_m"] > 0.02:                                        # every start from away goes via the start pose
            assert s["band_from_m"] < AT_START_M, (s["i"], s["kind"], s["start_m"], s["band_from_m"])


@pytest.mark.xfail(strict=True, reason="the return is given up at the first reading with a hand on the handle and never tried again: 5 of 5 sessions end in hold, 3 to 9 cm from the start (LOG, Shiv, 15 Nov 23:30)")
def test_the_return_to_start_waits_for_the_hand(soak):
    """Stopped with a hand on the handle (it lets go 1.5 to 4 s later): the return waits for it, then runs."""
    rows = [(s["i"], s["kind"], "level", s["levels"][-1], "stop at m", s["stop_s_m"], "speed", s["stop_speed"],
             "reading N", s["stop_reading_n"], "engine waited s", s["stop_took_s"], "ends", s["end_mode"],
             "m from start", s["end_m"], s["stop_message"])
            for s in soak["sessions"] if s["kind"] in HAND_ON_KINDS]
    assert len(rows) == 5
    bad = [r for r, s in zip(rows, [s for s in soak["sessions"] if s["kind"] in HAND_ON_KINDS])
           if s["end_mode"] == "hold" or s["end_m"] > AT_START_M]
    assert not bad, _lines(bad)


@pytest.mark.xfail(strict=True, reason="7 of 40 sessions end in hold away from the start: 5 stopped with a hand on the handle, 2 stopped while an empty handle was gliding back (LOG, Shiv, 15 Nov 23:30)")
def test_no_session_ends_in_hold(soak):
    rows = [(s["i"], s["kind"], "level", s["levels"][-1], "hand on at stop", s["hand_on_at_stop"], "stop at m",
             s["stop_s_m"], "speed", s["stop_speed"], "m from start", s["end_m"], s["stop_message"])
            for s in soak["sessions"] if s["end_mode"] == "hold"]
    assert not rows, _lines(rows)


def test_app_fields_are_always_present(soak):
    """rep_count, phase, level, message and countdown_s: in every /api/state poll (5 per second of sim time,
    through countdown, zero, band and after a set) and in every sample message of the websocket feed."""
    ss = soak["sessions"]
    assert sum(s["polls"] for s in ss) > 5000
    bad = [(s["i"], s["kind"], s["bad_polls"][:3], len(s["bad_polls"])) for s in ss if s["bad_polls"]]
    assert not bad, _lines(bad)
    samples = [m for m in soak["feed"] if m.get("type") == "sample"]
    assert len(samples) > 300
    missing = [(m.get("t"), [k for k in FIELDS if k not in m]) for m in samples if any(k not in m for k in FIELDS)]
    assert not missing, _lines(missing[:5])
    assert all(m["phase"] in ("idle", "out", "back") and m["level"] in LEVEL_N for m in samples)
    counting = [m for m in samples if m["countdown_s"] is not None]
    assert counting and all(isinstance(m["message"], str) and 0 <= m["countdown_s"] <= 3.0 for m in counting)


@pytest.mark.xfail(strict=True, reason="/api/state has no `phase` (nor pos, force, target) between POST /api/session/start and the engine's first tick: 40 of 40 (LOG, Shiv, 15 Nov 23:30)")
def test_state_has_the_fields_right_after_start(soak):
    """GET /api/state straight after POST /api/session/start, before the engine's first control tick."""
    bad = [(s["i"], s["first_poll_bad"]) for s in soak["sessions"] if s["first_poll_bad"]]
    assert not bad, f"{len(bad)} of {N_SESSIONS} sessions, e.g. {bad[:2]}"
