"""Exercise programmes the server offers (E2). A thin adapter over software/exercises.py (E1).

The engine side owns the registry: `software.exercises.LIVE` says which ids the robot can run
now, and a registry there may give each programme's name, kind and default reps. This module
reads both tolerantly at request time (so E1 landing, or adding "circle" to LIVE, needs no
server change) and falls back to its own table. Until software/exercises.py exists, only
"reach" is live.

Ids are exact (context/EXERCISE_MAP.md): reach, push, pull, armtest, circle.
"""
from __future__ import annotations

import importlib
from typing import Any

# id -> name, kind, default reps. Used when the engine registry has no (or a partial) entry.
BUILTIN: dict[str, dict[str, Any]] = {
    "reach":   {"name": "Forward reach", "kind": "assist", "reps": 10},
    "push":    {"name": "Push", "kind": "resist", "reps": 10},
    "pull":    {"name": "Row", "kind": "resist", "reps": 10},
    "armtest": {"name": "Push strength test", "kind": "isometric", "reps": 3},
    "circle":  {"name": "Circle", "kind": "robot-led", "reps": 5},
}
FALLBACK_LIVE = ("reach",)
LEGACY = {"reach_line": "reach"}        # sessions stored before E2
REPS_MAX = 100
_REGISTRY_NAMES = ("EXERCISES", "REGISTRY", "PRESETS", "PROGRAMMES")


def canonical(exercise: str | None) -> str:
    """Stored exercise value -> programme id ("reach_line" and empty mean "reach")."""
    return LEGACY.get(exercise or "reach", exercise or "reach")


def _module():
    try:
        return importlib.import_module("software.exercises")
    except Exception:      # not written yet, or broken: the server still runs "reach"
        return None


def _get(entry: Any, *names: str) -> Any:
    for n in names:
        v = entry.get(n) if isinstance(entry, dict) else getattr(entry, n, None)
        if v is not None:
            return v
    return None


def _registry(mod) -> dict[str, Any]:
    """id -> entry (dict or object) from the engine registry, {} if there is none."""
    for name in _REGISTRY_NAMES:
        reg = getattr(mod, name, None)
        if isinstance(reg, dict) and reg:
            return {str(k): v for k, v in reg.items()}
        if isinstance(reg, (list, tuple)) and reg:
            return {str(_get(e, "id")): e for e in reg if _get(e, "id") is not None}
    return {}


def live_ids() -> list[str]:
    """Ids the robot can run now, in registry order where known."""
    mod = _module()
    live = getattr(mod, "LIVE", None) if mod is not None else None
    if not live:
        return list(FALLBACK_LIVE)
    ids = [str(x) for x in live]
    order = list(BUILTIN)
    return sorted(ids, key=lambda i: (order.index(i) if i in order else len(order), i))


def info(exercise_id: str) -> dict[str, Any]:
    """{"id", "name", "kind", "reps"} for one programme (registry values win over the built-in table)."""
    base = BUILTIN.get(exercise_id, {"name": exercise_id, "kind": "unknown", "reps": 10})
    out = {"id": exercise_id, **base}
    mod = _module()
    entry = _registry(mod).get(exercise_id) if mod is not None else None
    if entry is not None:
        name, kind = _get(entry, "name", "label", "title"), _get(entry, "kind", "type")
        reps = _get(entry, "reps", "default_reps", "n_reps", "tries")
        if name:
            out["name"] = str(name)
        if kind:
            out["kind"] = str(kind)
        try:
            if reps is not None and int(reps) > 0:
                out["reps"] = int(reps)
        except (TypeError, ValueError):
            pass
    return out


def catalog() -> list[dict[str, Any]]:
    """The live programmes, for GET /api/exercises."""
    return [info(i) for i in live_ids()]
