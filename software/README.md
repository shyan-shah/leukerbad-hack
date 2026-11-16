# software/: the exercise engines and the simulated arm

| File | What it is |
|---|---|
| `simple.py` | **BandEngine: Push** at four levels. The arm acts as an elastic band; stiffness set once per set; reps counted from position; smooth hands-off return to the start. This is what runs in the demo |
| `simple_more.py` | **RowEngine** and **StrengthEngine**, built on BandEngine |
| `sim_arm.py` | Simulated arm with the same interface as `robot/arm.py`, including friction, pose-dependent sensor offset, drift, noise and stiffness latency measured on the real robot |
| `sim_patient.py` | Simulated patient (strength, tremor, presence) |
| `metrics.py`, `reps.py`, `paths.py` | Per-rep metrics (range, path error, smoothness, force, contribution), rep detection, path geometry |
| `engine.py`, `controller.py`, `adapt.py`, `assess.py`, `strength_model.py` | The first, adaptive engine (assist-as-needed dial, calibration push). Kept for reference; replaced by the band engines for the demo after real-arm testing |
| `EXERCISES.md` | Every programme: parameters, phases, what is measured |
| `PLAN_B.md` | Fallback control modes if the robot licence had not allowed Cartesian impedance |
| `tests/` | Engine, metric and soak tests on the simulated arm |
