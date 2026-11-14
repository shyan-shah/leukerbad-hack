# Exports for the website and deck

**Every row with `simulated: true` (or `simulated` = `true` in the CSV) must be labelled "simulated" wherever it is shown: on every chart, table, slide and page.**

Right now everything in this folder is **simulated**: one fictional patient, "Anna (SIMULATED)", over 14 days. We wrote that history to show what the physio dashboard would look like over time. It is not from a real person and not from the robot. When the real arm runs sessions, those rows will have `simulated: false`.

Regenerate (Shyan or anyone with Python): `python -m server.simulate --fresh` then `python -m server.export`.

## Files

### `patients.json`
One entry per patient.

| Field | Meaning |
|-------|---------|
| `id` | patient code, e.g. `sim-anna` |
| `display_name` | name to show. Simulated patients always contain "(SIMULATED)" |
| `simulated` | true or false |
| `n_sessions` | number of sessions |

### `sessions.json`
One entry per session, with averages over its repetitions. Good for "progress over time" charts.

| Field | Meaning |
|-------|---------|
| `session_id`, `patient_id` | codes |
| `started_at`, `ended_at` | date and time (ISO format, e.g. `2026-11-13T09:30:00`) |
| `exercise` | always `reach_line` (straight forward reach) for now |
| `n_reps` | repetitions in the session |
| `simulated` | true or false |
| `dial_start`, `dial_end`, `mean_dial` | the assistance dial: **+1** = the arm does the work, **0** = free movement, **-1** = maximum resistance. Falling over time = needing less help |
| `mean_rom_m` | range of motion, metres (multiply by 100 for cm). Higher is better |
| `mean_path_err_mean_m`, `mean_path_err_max_m` | how far the hand wandered off the straight line, metres. Lower is better |
| `mean_sparc` | smoothness (SPARC). Always negative; closer to zero is smoother |
| `mean_peak_force_n`, `mean_mean_force_n` | force the person pushed with, newtons. Higher = stronger |
| `mean_contribution` | share of the movement the person did themselves, 0 to 1. **Our own index, not a clinically validated measure**; say so if you show it |
| `mean_duration_s` | seconds per repetition. Lower is faster |
| `completed_share` | share of reps that reached the end of the path, 0 to 1 |
| `rescued_count` | reps where the arm had to step in after the person stalled |

### `reps.csv`
One row per repetition (opens in Excel or Google Sheets). Same measures as above, per rep, plus `mode` (`assist`, `transparent`, `resist`), `idx` (rep number in the session), `t_start` (seconds into the session), `completed`, `rescued`.

### `latest_session.json`
The most recent session: `session` (as in sessions.json), `reps` (as in reps.csv), `note` (the automatic session note as plain text, ready to paste), and `simulated`.

## Wording to use

- Contribution: "share of the movement done by the patient (our own measure)".
- Smoothness: "SPARC smoothness (Balasubramanian et al., 2015)".
- Never describe simulated numbers as results, outcomes or evidence. They show what the product would display.
