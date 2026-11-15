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

# id -> name, kind, default reps: a copy of software/exercises.py, used when that registry cannot be
# imported or has no (or a partial) entry. Kinds: assist, resist, test (isometric), guided (robot-led).
BUILTIN: dict[str, dict[str, Any]] = {
    "reach":   {"name": "Forward reach (assisted)", "kind": "assist", "reps": 10},
    "push":    {"name": "Push (resisted)", "kind": "resist", "reps": 10},
    "pull":    {"name": "Row (resisted)", "kind": "resist", "reps": 10},
    "armtest": {"name": "Push strength test", "kind": "test", "reps": 3},
    "circle":  {"name": "Circle (robot-led)", "kind": "guided", "reps": 8},
}
# Push against a constant band at four fixed levels (software/simple.py BandEngine): level -> newtons.
# A copy of software.simple.LEVELS (a test keeps the two equal), so the list works without software/.
BAND_LEVELS: dict[int, float] = {1: 10.0, 2: 15.0, 3: 20.0, 4: 28.0}
BAND_IDS: tuple[str, ...] = tuple(f"push_{n}" for n in BAND_LEVELS)
for _n, _f in BAND_LEVELS.items():
    BUILTIN[f"push_{_n}"] = {"name": f"Push \u00b7 Level {_n} ({_f:.0f} N)", "kind": "resist", "reps": 10}
GROUPS = {"pull": "row"}                # id -> group shown as one card in the app (default: the id itself)
FALLBACK_LIVE = ("reach",)


def band_level(exercise_id: str | None) -> int | None:
    """Level of a band exercise id ("push_3" -> 3), else None."""
    s = str(exercise_id or "")
    return int(s[5:]) if s in BAND_IDS else None


def is_band(exercise_id: str | None) -> bool:
    return band_level(exercise_id) is not None
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
    """{"id", "name", "kind", "reps", "calibrates", "group", "level", "level_force_n"} for one programme
    (registry values win over the built-in table). ``group`` is the card it belongs to in the app; ``level``
    and ``level_force_n`` are set for the band exercises push_1 .. push_4 and None for the others."""
    base = BUILTIN.get(exercise_id, {"name": exercise_id, "kind": "unknown", "reps": 10})
    out = {"id": exercise_id, **base}
    calibrates = None
    mod = _module()
    entry = _registry(mod).get(exercise_id) if mod is not None else None
    if entry is not None:
        name, kind = _get(entry, "name", "label", "title"), _get(entry, "kind", "type")
        reps = _get(entry, "reps", "default_reps", "n_reps", "tries")
        if name:
            out["name"] = str(name)
        if kind:
            out["kind"] = str(kind)
        calibrates = _get(entry, "calibrates", "calibrate")
        try:
            if reps is not None and int(reps) > 0:
                out["reps"] = int(reps)
        except (TypeError, ValueError):
            pass
    # comfortable-push calibration at the start of the session: on for resist exercises (push, pull)
    out["calibrates"] = bool(calibrates) if calibrates is not None else out["kind"] == "resist"
    lv = band_level(exercise_id)
    out["group"] = "push" if lv else GROUPS.get(exercise_id, exercise_id)
    out["level"] = lv
    out["level_force_n"] = BAND_LEVELS[lv] if lv else None
    if lv:
        out["calibrates"] = False       # no comfortable push on the band: the level is the resistance
    return out


def catalog() -> list[dict[str, Any]]:
    """The live programmes, for GET /api/exercises."""
    return [info(i) for i in live_ids()]
