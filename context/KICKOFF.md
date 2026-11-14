# KICKOFF: start building now

Written Sat 14 Nov, about 15:00 Swiss. This file is the starting gun. `context/MASTER_PLAN.md` follows later today with the frozen robot interface, the API and the full package list. When it lands it supersedes this file, but nothing below will be thrown away.

**Dates:** checkpoint **Sun 15 Nov 17:00** (show it working once). Final deadline **Mon 16 Nov 13:00**.

## How to use this file

Open a fresh Claude Code session in the repo and paste:

> Run `git pull origin main`. Read `CLAUDE.md` and `context/KICKOFF.md`. Do package **<ID>** exactly as written. Only create or edit the files that package lists. Run its acceptance tests and show me the output. Then append the LOG line, commit, and push to main.

One agent per package. Packages under the same person touch different files, so run them in parallel.

## Who owns what

| Folder | Owner | Holds |
|--------|-------|-------|
| `robot/` | Kian | `arm.py` (the only code that talks to the Flexiv), safety limits, bring-up scripts |
| `software/` | Shiv | control engine: paths, assist as needed, resistance, rep detection, metrics, simulated arm and patient |
| `server/` | Shyan | data layer: data contract, SQLite storage, API, simulated history, exports for Mat and Gio |
| `demo/`, `business/` | Mat and Gio | website, screens, pitch deck, validation. They read `exports/` and later the API |
| `context/` | shared | append to LOG.md and DECISIONS.md, update your own rows in TASKS.md |

## Rules for every agent

1. `git pull origin main` before you start and again before you push. Work on `main`.
2. Only create or edit files your package lists. Never edit another person's folder. If you need something from it, write a blocker line in `context/LOG.md`.
3. You may import from another folder, never write to it.
4. Python **3.12**. Each folder has its own `requirements.txt` (`robot/`, `software/`, `server/`). Do not create a root one.
5. Tests live in `<folder>/tests/` and run from the repo root with `python -m pytest <folder>/tests -q`.
6. No CSV logging. Storage is SQLite in `server/`. If you need to save something for debugging, write it under `<folder>/scratch/` (git-ignored by you).
7. Any data that did not come from the real arm with a real person holding it carries `simulated=True` all the way to the screen. Never invent numbers, quotes or sources.
8. Units everywhere: seconds, metres, newtons, radians. Positions are in the robot base (world) frame. `force` is the force the **person applies to the handle**.
9. When done, append to `context/LOG.md`: date, time, your human's name, package ID, what works, what is next, blockers.

## Shared conventions (provisional v0, fields may be added later, not renamed)

A recording is a set of equal-length arrays sampled at 100 Hz:

- `t` shape (N,), seconds, increasing
- `pos` shape (N, 3), metres, handle position
- `force` shape (N, 3), newtons, force the person applies to the handle

A straight reach is defined by `start` (3,) and `end` (3,). `axis = (end - start) / |end - start|`. Progress `s` is the projection of `pos - start` onto `axis`, divided by the reach length (0 at start, 1 at end).

The data records every part of the system exchanges (defined in `server/contract.py` by package Y0a):

```python
@dataclass(frozen=True)
class Sample:              # one 100 Hz tick
    t: float               # s since session start
    pos: tuple[float, float, float]
    vel: tuple[float, float, float]
    force: tuple[float, float, float]
    target: tuple[float, float, float]   # where the arm is pulling toward
    dial: float            # -1 full resistance .. 0 transparent .. +1 full assistance
    rep_idx: int           # -1 between reps
    simulated: bool

@dataclass(frozen=True)
class RepResult:           # one finished repetition
    session_id: str
    idx: int
    mode: str              # "assist" | "transparent" | "resist"
    dial: float
    t_start: float
    duration_s: float
    rom_m: float           # range of motion along the reach axis
    path_err_mean_m: float
    path_err_max_m: float
    sparc: float           # smoothness, more negative = less smooth
    peak_force_n: float
    mean_force_n: float
    contribution: float    # 0..1 share of the movement done by the person
    completed: bool
    simulated: bool

@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    patient_id: str
    started_at: str        # ISO 8601
    ended_at: str | None
    exercise: str          # "reach_line"
    n_reps: int
    simulated: bool
```

---

# Kian (robot/)

**Safety first. Nobody holds the handle until the technician says so. One person has a hand on the e-stop whenever the arm is enabled.**

### K0: bring-up with the technician (human-led, agent helps with scripts)

**Files:** `robot/requirements.txt`, `robot/scratch/*.py`, `robot/BRINGUP.md`.

Facts from the Flexiv docs (v1.x manual at flexiv.com/software/rdk/manual/v1.x, examples on the `v1.x` branch of github.com/flexivrobotics/flexiv_rdk):

- **Do not run a plain `pip install flexivrdk`.** The latest version (2.x) is for a different robot family. A Rizon 4 needs the **1.9.x** line that matches the robot software version shown in Flexiv Elements (for example robot software 3.11.3 or 3.11.4 goes with `flexivrdk==1.9.4.1`). Ask the technician for the robot software version, then pin it in `robot/requirements.txt`.
- Python 3.10 or 3.12 on Windows. There is no Windows wheel for 3.14.
- The robot needs an RDK licence and must be in **Remote mode over Ethernet** (set in Elements, then power cycle). Laptop on `192.168.2.x`, netmask `255.255.255.0`, no gateway. Allow Python through the Windows firewall.
- Connect and enable: `robot = flexivrdk.Robot("Rizon4-XXXXXX")`, `robot.ClearFault()` if `robot.fault()`, `robot.Enable()`, wait for `robot.operational()`.
- Read state: `robot.states().tcp_pose` (x, y, z, qw, qx, qy, qz, world frame), `robot.states().tcp_vel`, `robot.states().ext_wrench_in_world`, `robot.states().q`.
- Zero the force sensor with nothing touching the arm: `robot.SwitchMode(flexivrdk.Mode.NRT_PRIMITIVE_EXECUTION)`, `robot.ExecutePrimitive("ZeroFTSensor", dict())`, wait for `robot.primitive_states()["terminated"]`.
- Handle weight: add it as a tool (`flexivrdk.Tool`, `ToolParams.mass`, `.CoM`) in IDLE mode, accurate to under 100 g.
- Soft spring mode: `robot.SwitchMode(flexivrdk.Mode.NRT_CARTESIAN_MOTION_FORCE)`, then send `robot.SendCartesianMotionForce(pose)` at up to 100 Hz. Change stiffness live with `robot.SetCartesianImpedance(K_x)` where `K_x` is six numbers (N/m for x, y, z then Nm/rad for rotation), each between 0 and `robot.info().K_x_nom`. Zero on an axis makes that axis free.
- **Stiffness settings stay on the robot after your program ends.** Always set `robot.info().K_x_nom` back before exiting.
- `robot.SetMaxContactWrench([fx, fy, fz, mx, my, mz])` caps contact force. `robot.Stop()` stops and goes to IDLE. If the laptop disconnects, the robot stops and holds by itself.
- Closest official example: `example_py/intermediate3_non_realtime_cartesian_pure_motion_control.py` (v1.x branch).

**Steps:**
1. Install the pinned RDK. Script `scratch/01_read.py`: connect, enable, print pose and external force at 10 Hz.
2. Mount the handle. Set the tool. Zero the sensor. Confirm the force reads about 0 N with nobody touching.
3. Script `scratch/02_hold.py`: enter Cartesian mode, hold the current pose with **low** stiffness (start at 300 N/m on x, y, z, keep rotation at nominal), `SetMaxContactWrench([20, 20, 20, 5, 5, 5])`. The technician pushes the handle first.
4. Script `scratch/03_free_axis.py`: same, with one axis at 0 N/m. Confirm it slides freely along that axis and is held on the others.
5. Write the answers below into `robot/BRINGUP.md` and a summary into `context/LOG.md`. **These answers freeze the interface, so post them as soon as you have them.**

**Questions to answer:**
1. Robot software version, exact serial string, Rizon 4 or 4s, and the RDK version you pinned.
2. `robot.info().license_type`. Does `NRT_CARTESIAN_MOTION_FORCE` switch without an error?
3. `robot.info().K_x_nom` (all six values).
4. Does changing stiffness mid-loop work smoothly? Lowest stiffness that still feels stable? Does a 0 axis really float?
5. When you push the handle toward +x, is `ext_wrench_in_world[0]` positive or negative?
6. Which speed, force and workspace limits has the technician set in Elements? Is there a safety plane we can put between the arm and the person's body?
7. A good start pose for a seated forward reach (handle at about table height, 35 to 40 cm of clear travel away from the body), as `tcp_pose` and `q`.
8. Where the e-stop is and who holds it.

**Done when:** scripts 01 to 03 run, BRINGUP.md has all eight answers, technician has signed off hand contact at low stiffness.

**LOG line:** `K0 done: pose and force reading, soft hold at <k> N/m, free axis works yes/no, force sign <+/->, answers in robot/BRINGUP.md`.

---

# Shiv (software/)

All four packages are pure functions on arrays. No robot, no API, no database. They can all start now and run in parallel. Each package also adds its dependencies to `software/requirements.txt` (numpy, pytest; keep it minimal) and creates `software/__init__.py` if missing.

### S0a: metrics

**Files:** `software/metrics.py`, `software/tests/test_metrics.py`.

```python
def rom(pos, start, end) -> float                  # max minus min of progress along the reach, in metres
def path_error(pos, start, end) -> tuple[float, float]   # (mean, max) perpendicular distance to the line, metres
def force_stats(force) -> tuple[float, float]      # (peak, mean) of the force magnitude, newtons
def sparc(speed, fs, padlevel=4, fc=10.0, amp_th=0.05) -> float
def contribution(force, vel, start, end) -> float  # 0..1
def rep_metrics(t, pos, force, start, end) -> dict # all of the above plus duration_s, keys named as in RepResult
```

- `sparc`: port the reference Python implementation, `scripts/smoothness.py` in github.com/siva82kb/SPARC (Balasubramanian et al. 2015, "On the analysis of movement smoothness", J NeuroEngineering Rehabil 12:112). Its signature is `sparc(movement, fs, padlevel=4, fc=10.0, amp_th=0.05)`. Open the file and match it exactly; put the source URL in the docstring. `speed` is the magnitude of velocity from `numpy.gradient(pos, t)`.
- `contribution`: let `f` be force projected on the reach axis and `v` velocity projected on it. Person's work `Wp = sum(max(0, f*v))*dt`, robot's work `Wr = sum(max(0, -f*v))*dt`. Return `Wp / (Wp + Wr)`, or 0.0 if both are under 1e-6. Docstring must say: "Team-defined index, not a clinically validated measure."

**Tests must cover:** a perfect straight minimum-jerk reach of 0.30 m gives `rom` about 0.30 and path error about 0; adding a 2 cm sideways bow gives max error about 0.02; a minimum-jerk speed profile has a higher (less negative) SPARC than the same profile with a 5 Hz tremor added; force always along the motion gives contribution 1.0, always against gives 0.0; empty or 1-sample input raises `ValueError`.

**Run:** `python -m pytest software/tests/test_metrics.py -q`

### S0b: rep detection

**Files:** `software/reps.py`, `software/tests/test_reps.py`.

```python
def progress(pos, start, end) -> np.ndarray        # s in 0..1 per sample (unclamped)
def segment_reps(t, pos, start, end, out_thresh=0.9, back_thresh=0.1, min_duration_s=0.5) -> list[tuple[int, int, bool]]
# each tuple: (i_start, i_end, completed). A rep starts when s rises above back_thresh, counts as completed if s reaches out_thresh, ends when s falls back under back_thresh.

class RepDetector:                                  # same logic, one sample at a time, for the live loop
    def __init__(self, start, end, out_thresh=0.9, back_thresh=0.1, min_duration_s=0.5): ...
    def update(self, t: float, pos) -> str | None   # returns "rep_start", "rep_reached", "rep_end" or None
```

**Tests:** five clean out-and-back reaches give 5 completed reps; a reach that stops at 60% is returned with `completed=False`; jitter around the thresholds does not create extra reps; `RepDetector` fed sample by sample agrees with `segment_reps`.

**Run:** `python -m pytest software/tests/test_reps.py -q`

### S0c: paths

**Files:** `software/paths.py`, `software/tests/test_paths.py`.

```python
@dataclass(frozen=True)
class LinePath:
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    def length(self) -> float
    def axis(self) -> np.ndarray
    def point_at(self, s: float) -> np.ndarray      # s clamped to 0..1
    def closest(self, pos) -> tuple[np.ndarray, float, float]   # (closest point on segment, s, perpendicular distance)

def min_jerk(s0: float, s1: float, duration_s: float, t: float) -> float   # smooth progress profile, clamped outside 0..duration
def lead_target(path, pos, lead_m: float, max_lead_m: float = 0.05) -> np.ndarray
# point on the path ahead of the hand's closest point by lead_m (negative = behind), never more than max_lead_m from that closest point, never beyond the path ends
```

**Tests:** closest point and distance for points on, beside and beyond the segment; `min_jerk` starts and ends with zero slope; `lead_target` respects `max_lead_m` and the path ends.

**Run:** `python -m pytest software/tests/test_paths.py -q`

### S0d: simulated patient

**Files:** `software/sim_patient.py`, `software/tests/test_sim_patient.py`.

A fake hand so everything can be developed with no robot. Point mass of 1.5 kg with damping 8 N s/m, pulled by two forces: the arm's spring `k * (target - pos)` per axis, and the patient's own effort.

```python
@dataclass
class SimPatient:
    strength: float = 1.0      # 0 = limp arm, 1 = healthy
    tremor_n: float = 0.0      # amplitude of 5 Hz force noise
    seed: int = 0
    def effort(self, t, pos, vel, goal) -> np.ndarray   # force the patient applies: strength * a PD pull toward goal, capped at 25 N, plus tremor

def simulate_reach(patient, start, end, n_reps, k_xyz, lead_m, dt=0.01) -> dict
# integrates the hand for n_reps out-and-back reaches with the arm's target leading by lead_m.
# returns {"t", "pos", "vel", "force", "target"} arrays, force = patient effort (the force applied to the handle)
```

**Tests:** `strength=1` with zero stiffness along the reach completes the reps alone; `strength=0` with zero stiffness does not move; `strength=0` with 400 N/m and a 5 cm lead is carried to the end; output is deterministic for a fixed seed; arrays match the shared conventions.

**Run:** `python -m pytest software/tests/test_sim_patient.py -q`

**LOG line for each:** `S0x done: <file> with N passing tests`.

---

# Shyan (server/)

Y0a first (10 minutes, everything else imports it). Then Y0b, Y0c, Y0d in parallel. The API comes in MASTER_PLAN.md.

### Y0a: data contract

**Files:** `server/__init__.py`, `server/contract.py`, `server/requirements.txt`, `server/tests/test_contract.py`.

Create the three dataclasses exactly as in "Shared conventions" above, plus `to_dict()` and `from_dict()` on each (plain JSON types only, tuples become lists). No other logic.

**Tests:** round trip through `json.dumps` and back gives an equal object for each class.

**Run:** `python -m pytest server/tests/test_contract.py -q`

### Y0b: SQLite storage

**Files:** `server/db.py`, `server/tests/test_db.py`. Standard library `sqlite3` only.

Tables: `patients(id TEXT PRIMARY KEY, display_name TEXT, simulated INTEGER NOT NULL)`, `sessions` (columns of `SessionSummary`), `reps` (columns of `RepResult`, primary key `(session_id, idx)`). Every table has `simulated`.

```python
def connect(path="data/rehab.db") -> sqlite3.Connection   # creates the folder and tables if missing
def upsert_patient(conn, id, display_name, simulated) -> None
def save_session(conn, s: SessionSummary) -> None          # insert or update
def save_rep(conn, r: RepResult) -> None
def list_patients(conn) -> list[dict]
def list_sessions(conn, patient_id) -> list[SessionSummary]
def list_reps(conn, session_id) -> list[RepResult]
```

`data/` is git-ignored (add `data/` and `exports/` handling to a `server/.gitignore` only, do not touch a root one).

**Tests:** use a temp file; save and reload gives equal objects; saving the same rep twice does not duplicate; a real session cannot be saved under a simulated patient or the reverse (raise `ValueError`).

**Run:** `python -m pytest server/tests/test_db.py -q`

### Y0c: simulated history

**Files:** `server/simulate.py`, `server/tests/test_simulate.py`.

```python
def make_history(conn, patient_id="sim-anna", display_name="Anna (SIMULATED)", days=14, sessions_per_day=1, reps_per_session=30, seed=7) -> None
```

Writes one fictional patient whose numbers improve over 14 days: dial drifts from about +0.9 toward about -0.2, contribution from about 0.2 to about 0.9, path error and SPARC improve, peak force rises, with day-to-day noise and one bad day. Everything `simulated=True`. The display name always contains "(SIMULATED)". The trend is a plausible illustration that we wrote, not clinical data, and the module docstring says so.

If Shiv's `software/sim_patient.py` exists by the time you start, generate reps by calling it. If not, generate the per-rep numbers directly with numpy and leave a `TODO(S0d)` note.

**Tests:** 14 sessions exist; every row has `simulated=1`; same seed gives identical data; first-day mean contribution is lower than last-day.

**Run:** `python -m pytest server/tests/test_simulate.py -q` then `python -m server.simulate` to fill `data/rehab.db`.

### Y0d: exports for Mat and Gio

**Files:** `server/export.py`, `server/tests/test_export.py`, `exports/README.md`.

```python
def export_all(conn, out_dir="exports") -> list[str]   # returns the files written
```

Writes `exports/patients.json`, `exports/sessions.json` (one row per session with per-session means of every metric), `exports/reps.csv` (one row per rep), and `exports/latest_session.json`. Every row keeps `simulated`. `exports/README.md` explains each file and column in plain English for non-coders, and states in its first line that rows with `simulated: true` must be labelled "simulated" wherever they are shown. Commit the generated export files so Mat and Gio can use them without running Python.

**Tests:** files exist and parse; row counts match the database; every row has the `simulated` field.

**Run:** `python -m pytest server/tests/test_export.py -q` then `python -m server.export`.

**LOG line for each:** `Y0x done: <what exists>, Mat and Gio can use exports/ yes/no`.

---

# Mat and Gio (business/, demo/)

No code needed for these two.

### B0: talk to therapists in Leukerbad today

Saturday afternoon is the best window. Sunday will be quieter.

**Know before you go:** Leukerbad Clinic's own website lists **musculoskeletal, internal medicine and oncology rehab, not stroke or neurology**, and no robots. It does list isokinetic strength testing equipment. So do not open with "stroke". Open with shoulder and arm rehab, and ask about neuro patients second. The director of therapies is listed on leukerbadclinic.ch under Clinique, Organisation, Direction. Check the name there before you go.

**Opening line:** "We are students at the robotics hackathon in town this weekend, building an arm rehab tool on a robot arm. Could we ask a therapist five minutes of questions? We are not selling anything."

**Questions (write the answers down word for word):**
1. What arm or shoulder patients do you see most? Any stroke patients?
2. In a 30 minute session, about how many repetitions of one movement does a patient get?
3. How many patients does one therapist see per day? One to one, or groups?
4. How do you measure progress today, and how long does writing the notes take?
5. Do you use any robots or measuring devices? What do you like and dislike about them?
6. If a device let one therapist supervise three or four patients doing guided repetitions safely, would that be useful? What would stop you using it?
7. Who decides on buying equipment, and roughly what budget range is normal for a therapy device?
8. Would you be willing to come and try it on Sunday or Monday and tell us what is wrong with it?

**Rules:** ask permission before quoting anyone by name. Record only what was actually said. If nobody will talk, write that down; do not fill gaps. Target: 3 conversations by Saturday evening, 5 by Sunday midday. Try the clinic, any private physio practice in the village, and therapists at the thermal baths.

**Write up in:** `business/interviews.md` (who, role, date, answers, permission to quote yes or no).

### B1: claims table

Start `business/claims.md` with columns: claim, number, source link, exact quote from the source, checked by, date. Add a row only after you have opened the source yourself. Anything not checked is written as UNVERIFIED. The master plan will hand you a long list to check; start with these two, which are the foundation of the pitch:
- how many repetitions stroke patients actually get per therapy session (look for Lang et al. 2009, "Observation of amounts of movement practice provided during stroke rehabilitation")
- what the largest trial of robot arm therapy found (RATULS, Rodgers et al., The Lancet, 2019). Read the conclusion carefully: we need to be honest about it.

### Website and deck

Wait for `exports/` to appear on main (Shyan's package Y0d), then build from those files. Anything marked simulated stays labelled simulated on every page and slide. How the live screens connect to the robot is decided on Sunday.
