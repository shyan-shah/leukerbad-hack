"""Plain-text session note drafted from device data for a therapist to review.

Deterministic template: no AI, no clinical advice, no diagnosis.
"""
from __future__ import annotations

from .contract import RepResult, SessionSummary
from .stats import METRICS, mode_of, session_means

HEADER = "Drafted automatically from device data for therapist review. Not a clinical assessment."

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


def session_note(summary: SessionSummary, reps: list[RepResult],
                 previous: list[RepResult] | None = None) -> str:
    """`previous` is the rep list of the patient's previous session, if any."""
    lines = [HEADER]
    if summary.simulated:
        lines.append("SIMULATED DATA: not from a real patient.")
    lines += [
        "",
        f"Patient: {summary.patient_id}    Session: {summary.session_id}",
        f"Started: {summary.started_at}    Ended: {summary.ended_at or 'in progress'}",
        "Exercise: straight-line forward reach on the robot arm",
        "",
    ]
    if not reps:
        lines.append("No repetitions recorded.")
        return "\n".join(lines) + "\n"

    m = session_means(reps)
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
