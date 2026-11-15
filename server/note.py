"""Plain-text session note drafted from device data for a therapist to review.

Deterministic template: no AI, no clinical advice, no diagnosis.
"""
from __future__ import annotations

from statistics import fmean

from .contract import RepResult, SessionSummary
from .exercises import canonical
from .stats import METRICS, mode_of, session_means

HEADER = "Drafted automatically from device data for therapist review. Not a clinical assessment."
FORCE_CAP_NOTE = "Readings capped at about 30 N by the robot's safety limit."

# programme id -> the "Exercise:" line
EXERCISE_LINE = {
    "reach": "straight-line forward reach on the robot arm (assisted as needed)",
    "push": "push forward against resistance, straight line on the robot arm",
    "pull": "row: pull towards the body against resistance, straight line on the robot arm",
    "armtest": "push strength test: the handle is held still while the person pushes (isometric)",
    "circle": "circle, led by the robot arm",
}

# metric -> (label, multiplier, unit, decimals)
_FMT = {
    "rom_m": ("Range of motion", 100, "cm", 1),
    "path_err_mean_m": ("Path error, mean", 100, "cm", 1),
    "path_err_max_m": ("Path error, max", 100, "cm", 1),
    "sparc": ("Smoothness (SPARC)", 1, "", 2),
    "peak_force_n": ("Peak force", 1, "N", 1),
    "mean_force_n": ("Mean force", 1, "N", 1),
    "contribution": ("Own contribution", 100, "%", 0),
    "duration_s": ("Time per rep", 1, "s", 1),
}


def _fmt(metric: str, v: float | None) -> str:
    if v is None:
        return "n/a"
    _, mul, unit, dec = _FMT[metric]
    return f"{v * mul:.{dec}f}{(' ' + unit) if unit and unit != '%' else unit}"


def _change(metric: str, now: float, before: float) -> str:
    _, mul, unit, dec = _FMT[metric]
    d = (now - before) * mul
    if round(d, dec) == 0:
        return "no change"
    better = (d > 0) == METRICS[metric]
    sign = "+" if d > 0 else ""
    u = unit if unit == "%" else (" " + unit if unit else "")
    if unit == "%":
        u = " pts"
    return f"{sign}{d:.{dec}f}{u} ({'better' if better else 'worse'})"


def _summary_line(ex: str, reps: list[RepResult], m: dict) -> str:
    """One line per exercise: reps, range, peak force, then contribution (reach) or resistance (push, pull)."""
    head = (f"Summary: {len(reps)} reps, range {m['mean_rom_m'] * 100:.1f} cm (mean), "
            f"peak force {max(r.peak_force_n for r in reps):.1f} N (best)")
    if ex in ("push", "pull"):
        return head + (f", resistance level {max(-m['mean_dial'], 0.0) * 100:.0f}% of maximum "
                       f"(mean dial {m['mean_dial']:+.2f}), mean force {m['mean_mean_force_n']:.1f} N")
    return head + f", own contribution {m['mean_contribution'] * 100:.0f}% (mean)"


def _armtest_lines(reps: list[RepResult], previous: list[RepResult] | None) -> list[str]:
    peaks = [r.peak_force_n for r in reps]
    lines = [f"Tries: {len(reps)}",
             f"Peak force: best {max(peaks):.1f} N, mean {fmean(peaks):.1f} N over the tries"]
    if previous:
        d = max(peaks) - max(r.peak_force_n for r in previous)
        lines.append("Change vs previous strength test (best): "
                     + ("no change" if round(d, 1) == 0 else f"{d:+.1f} N ({'higher' if d > 0 else 'lower'})"))
    lines.append("")
    lines.append(f"{'Try':<6}{'Peak':>10}{'Mean':>10}{'Held':>9}")
    for r in reps:
        lines.append(f"{r.idx + 1:<6}{r.peak_force_n:>8.1f} N{r.mean_force_n:>8.1f} N{r.duration_s:>7.1f} s")
    lines += ["", FORCE_CAP_NOTE,
              "Force is measured along the push direction with the handle held still; it is a device "
              "reading, not a clinically validated strength score.",
              "Therapist comments: ______________________________"]
    return lines


def calibration_line(summary: SessionSummary) -> str:
    return (f"Resistance set to {summary.resistance_n:.1f} N from a comfortable push of "
            f"{summary.comfort_force_n:.1f} N (team heuristic, adjusts to the patient)")


def session_note(summary: SessionSummary, reps: list[RepResult],
                 previous: list[RepResult] | None = None) -> str:
    """`previous` is the rep list of the patient's previous session of the same exercise, if any."""
    ex = canonical(summary.exercise)
    lines = [HEADER]
    if summary.simulated:
        lines.append("SIMULATED DATA: not from a real patient.")
    lines += [
        "",
        f"Patient: {summary.patient_id}    Session: {summary.session_id}",
        f"Started: {summary.started_at}    Ended: {summary.ended_at or 'in progress'}",
        f"Exercise: {EXERCISE_LINE.get(ex, ex)}",
        "",
    ]
    if not reps:
        lines.append("No repetitions recorded.")
        return "\n".join(lines) + "\n"
    if ex == "armtest":
        return "\n".join(lines + _armtest_lines(reps, previous)) + "\n"

    m = session_means(reps)
    lines.append(_summary_line(ex, reps, m))
    if summary.resistance_n is not None and summary.comfort_force_n is not None:
        lines.append(calibration_line(summary))
    p = session_means(previous) if previous else None
    n_done = sum(r.completed for r in reps)
    lines.append(f"Repetitions: {len(reps)} started, {n_done} completed")
    lines.append(f"Dial: started {m['dial_start']:+.2f} ({mode_of(m['dial_start'])}), "
                 f"ended {m['dial_end']:+.2f} ({mode_of(m['dial_end'])}). "
                 "+1 = full assistance, 0 = free movement, -1 = maximum resistance.")
    modes = {}
    for r in reps:
        modes[r.mode] = modes.get(r.mode, 0) + 1
    lines.append("Reps by mode: " + ", ".join(f"{k} {v}" for k, v in sorted(modes.items())))
    lines.append("")

    header = f"{'Measure':<22}{'Mean':>10}{'Best':>10}"
    if p:
        header += f"   {'Change vs previous session (mean)'}"
    lines.append(header)
    for metric, higher_better in METRICS.items():
        vals = [getattr(r, metric) for r in reps]
        best = max(vals) if higher_better else min(vals)
        mean = m[f"mean_{metric}"]
        row = f"{_FMT[metric][0]:<22}{_fmt(metric, mean):>10}{_fmt(metric, best):>10}"
        if p and p[f"mean_{metric}"] is not None:
            row += "   " + _change(metric, mean, p[f"mean_{metric}"])
        lines.append(row)
    lines.append("")

    flags = []
    if m["rescued_count"]:
        flags.append(f"{m['rescued_count']} rep(s) needed extra assistance after a stall")
    if len(reps) - n_done:
        flags.append(f"{len(reps) - n_done} rep(s) did not reach the end of the path")
    lines.append("Flags: " + ("; ".join(flags) if flags else "none"))
    lines.append("")
    lines.append("Own contribution is a team-defined index (share of the movement work done by the "
                 "person), not a clinically validated measure.")
    lines.append("Therapist comments: ______________________________")
    return "\n".join(lines) + "\n"
