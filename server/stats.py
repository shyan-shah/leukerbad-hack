"""Per-session aggregates of rep metrics, shared by the API, exports and session note."""
from __future__ import annotations

from statistics import fmean

from .contract import RepResult

# metric name -> True if higher is better
METRICS: dict[str, bool] = {
    "rom_m": True,
    "path_err_mean_m": False,
    "path_err_max_m": False,
    "sparc": True,              # less negative = smoother
    "peak_force_n": True,
    "mean_force_n": True,
    "contribution": True,
    "duration_s": False,
}


def mode_of(dial: float) -> str:
    if dial > 0.05:
        return "assist"
    if dial < -0.05:
        return "resist"
    return "transparent"


def session_means(reps: list[RepResult]) -> dict:
    """Means of every metric plus dial start/end, completion share and rescue count.
    Values are None when the session has no reps."""
    out: dict = {"n_reps": len(reps)}
    if not reps:
        out.update({f"mean_{m}": None for m in METRICS})
        out.update(dial_start=None, dial_end=None, mean_dial=None, completed_share=None, rescued_count=0,
                   best_peak_force_n=None)
        return out
    for m in METRICS:
        out[f"mean_{m}"] = round(fmean(getattr(r, m) for r in reps), 4)
    out["best_peak_force_n"] = round(max(r.peak_force_n for r in reps), 4)
    out["dial_start"] = round(reps[0].dial, 3)
    out["dial_end"] = round(reps[-1].dial, 3)
    out["mean_dial"] = round(fmean(r.dial for r in reps), 3)
    out["completed_share"] = round(sum(r.completed for r in reps) / len(reps), 3)
    out["rescued_count"] = sum(r.rescued for r in reps)
    return out
