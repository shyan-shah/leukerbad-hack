"""Terminal live readout: enough on its own for the Sunday checkpoint.

  python -m server.watch [--url ws://127.0.0.1:8000/ws/live]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

RED = "\x1b[41;97m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
OFF = "\x1b[0m"


def bar(value: float, lo: float, hi: float, width: int = 41, mark: str = "#") -> str:
    x = 0.0 if hi == lo else (min(max(value, lo), hi) - lo) / (hi - lo)
    i = round(x * (width - 1))
    return "[" + "".join(mark if j == i else ("|" if j == width // 2 else "-") for j in range(width)) + "]"


class View:
    def __init__(self) -> None:
        self.sample: dict | None = None
        self.reps: list[dict] = []
        self.lo: list[float] | None = None
        self.hi: list[float] | None = None

    def update(self, m: dict) -> None:
        if m.get("type") == "rep":
            self.reps = (self.reps + [m])[-10:]
        elif m.get("type") == "sample":
            self.sample = m
            p = m["pos"]
            self.lo = [min(a, b) for a, b in zip(self.lo or p, p)]
            self.hi = [max(a, b) for a, b in zip(self.hi or p, p)]

    def progress(self) -> float:
        if not self.sample or self.lo is None:
            return 0.0
        spans = [h - l for h, l in zip(self.hi, self.lo)]
        ax = max(range(3), key=lambda i: spans[i])
        return 0.0 if spans[ax] < 0.02 else (self.sample["pos"][ax] - self.lo[ax]) / spans[ax]

    def render(self) -> str:
        s = self.sample
        if s is None:
            return "Waiting for a session... (start one with POST /api/session/start)\n"
        sim = f"{RED} SIMULATED {OFF} " if s.get("simulated") else f"{BOLD} REAL ROBOT {OFF} "
        f = s["force"]
        fmag = math.sqrt(sum(x * x for x in f))
        mode = "assist" if s["dial"] > 0.05 else "resist" if s["dial"] < -0.05 else "transparent"
        lines = [
            f"{sim} exercise: {s.get('exercise') or 'reach'}   arm: {s.get('arm_mode')}   "
            f"phase: {s.get('phase')}   reps: {s.get('rep_count')}"
            f"{'/' + str(s['reps_target']) if s.get('reps_target') else ''}   "
            f"auto dial: {'on' if s.get('auto') else 'OFF'}   t={s['t']:.1f}s",
            "",
            f"Dial  {s['dial']:+.2f} {mode:<11}  resist {bar(s['dial'], -1, 1)} assist",
            f"Reach {self.progress() * 100:5.0f}%             start  {bar(self.progress(), 0, 1, mark='o')} end",
            f"Force {fmag:5.1f} N             0 N    {bar(fmag, 0, 30, mark='>')} 30 N",
            "",
            f"{'rep':>4} {'mode':<12}{'dial':>6}{'ROM cm':>8}{'err cm':>8}{'SPARC':>7}{'peak N':>8}"
            f"{'contrib':>9}{'time s':>8}  done",
        ]
        for r in self.reps:
            lines.append(
                f"{r['idx']:>4} {r['mode']:<12}{r['dial']:>+6.2f}{r['rom_m'] * 100:>8.1f}"
                f"{r['path_err_mean_m'] * 100:>8.1f}{r['sparc']:>7.2f}{r['peak_force_n']:>8.1f}"
                f"{r['contribution'] * 100:>8.0f}%{r['duration_s']:>8.1f}  "
                f"{'yes' if r['completed'] else 'NO '}{' rescued' if r.get('rescued') else ''}")
        if not self.reps:
            lines.append(f"{DIM}  (no reps yet){OFF}")
        return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Live terminal view of the rehab station.")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/live")
    a = ap.parse_args(argv)
    from websockets.sync.client import connect

    os.system("")  # enables ANSI colours in the Windows console
    view = View()
    while True:
        try:
            with connect(a.url, open_timeout=3) as ws:
                last = 0.0
                for raw in ws:
                    import json
                    view.update(json.loads(raw))
                    now = time.monotonic()
                    if now - last > 0.1:
                        sys.stdout.write("\x1b[H\x1b[2J" + view.render())
                        sys.stdout.flush()
                        last = now
        except KeyboardInterrupt:
            return
        except Exception as e:
            sys.stdout.write(f"\x1b[H\x1b[2JNo connection to {a.url} ({e.__class__.__name__}). Retrying...\n")
            sys.stdout.flush()
            time.sleep(1.0)


if __name__ == "__main__":
    main()
