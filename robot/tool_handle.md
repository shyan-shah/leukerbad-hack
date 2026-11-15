# Creating the tool "RehabHandle" in Flexiv Elements

Owner: Kian. Do this with the technician, after the handle is mounted and before anyone runs
`safety_check.py`, `tune.py` or a session.

**Why it matters.** This Rizon 4 has no wrist force/torque sensor. The force we read is the
joint torques minus the robot's model of itself and its tool. Wrong tool mass or centre of mass
= a false force on an empty handle, a handle that drifts on a free axis, and an engine that
refuses to start (over 3 N) or thinks an empty handle is held. On 14 Nov a wrong tool gave 12.6 N.

Written without the arm in front of me: the page and button names in Elements 3.9.3 may differ
slightly from the ones below. The values and the order are what matter. Tick each step.

## 1. Before mounting: weigh and measure (5 minutes, kitchen scale and ruler)

Everything that will hang off the flange counts: adapter plate, grip, the four M6 screws, any
washers, tape or padding.

- [ ] **Mass.** Weigh the complete handle with its screws. Write it in kg to 0.001:
      `m = ______ kg` (e.g. 182 g = 0.182 kg). Aim for an error under 10 g: every 100 g wrong is 1 N of false force.
- [ ] **Centre of mass (CoM).** Balance the assembled handle (no screws needed) across a ruler edge
      or a pencil, with the mounting face pointing sideways. Measure from the **mounting face**
      (the surface that touches the flange) to the balance point: `c = ______ mm`.
- [ ] **Grip middle.** Measure from the mounting face to the middle of the part the hand holds:
      `g = ______ mm`.
- [ ] **Is the handle symmetric about the flange axis?** (A straight grip in line with the flange,
      or a T-bar centred on it: yes.) If yes the CoM and the TCP are on the axis: x = y = 0.
      If the grip sticks out to one side, also measure how far the balance point and the grip
      middle are from the flange axis, and in which direction relative to the flange's marked x/y.

Coordinates are in the **flange frame**: origin at the centre of the flange face, **z pointing
out of the flange** (away from the arm), x and y in the flange face.

| Value | Symmetric handle | Your numbers |
|---|---|---|
| Mass | m | ______ kg |
| CoM x, y, z | 0, 0, c | ______ , ______ , ______ |
| TCP position x, y, z | 0, 0, g | ______ , ______ , ______ |
| TCP rotation | none (0, 0, 0) | 0, 0, 0 |
| Inertia | leave at 0 / default | |

**Units trap:** the RDK uses metres (c = 45 mm is `0.045`). Elements may show mm. Read the unit
printed next to each field before typing, and check the saved value with step 4.

## 2. Mount the handle

- [ ] Arm is stopped (IDLE) and nobody is running a program. E-stop holder in place: the arm is
      live whenever it is powered.
- [ ] Flange and plate clean. Locating pin or mark lined up so the grip points the way we want.
- [ ] Four M6 screws, **cross pattern** (1, then the opposite one, then the other two):
      finger-tight all four first, then **hand-tight plus a quarter turn** each, again in the cross
      pattern. The technician confirms the screw length (they must not bottom out in the flange).
- [ ] Pull and twist the grip by hand: no play, no rotation.

## 3. Create and select the tool in Elements

Open Studio on the arm laptop: double-click **`Start Flexiv Studio.bat`** on the desktop, REFRESH,
Connect. The robot must be idle: no program running, no RDK script connected and commanding
(say "arm is mine" first). Decline any "update robot" prompt.

- [ ] Open the tool page: **Settings → Tool** (it may be called Tool Settings, Tool Config or End Effector).
      The list should show `Flange`, `Seat_Assembly_tool`, the grippers, and so on. Do not edit or delete other teams' tools.
- [ ] **Add / New tool.** Name it exactly **`RehabHandle`** (capital R and H, no space): our scripts check this name.
- [ ] **Mass**: m, in the unit the field shows.
- [ ] **CoM** x, y, z: from the table above, measured **from the flange face**.
- [ ] **Inertia**: leave zero or default. A handle this small does not need it.
- [ ] **TCP location**: x, y, z = the grip middle from the table. Rotation 0, 0, 0 (TCP axes = flange axes).
- [ ] **Save.**
- [ ] **Select / Switch to / Activate** `RehabHandle` so it is the active tool. The arm may twitch
      slightly when the payload model changes: keep clear.
- [ ] Check the page shows `RehabHandle` as the current tool.

If Elements has no page for adding a tool, stop and tell Kian: the RDK can do it
(`flexivrdk.Tool(robot).Add(...)` then `.Switch("RehabHandle")`, both in IDLE; `Switch` was used
on 14 Nov), but that script is not written and changes a robot setting, so it needs its own "go".

## 4. Check it (read-only)

From the repo root, arm venv, nobody touching the arm:

```
C:\venvs\flexiv17\Scripts\python.exe robot\read_tool_force.py --serial Rizon4-062157
```

It prints the active tool with its mass, CoM and TCP as the robot stored them (**compare with
your table: this catches a mm/m mistake**), three empty-force readings, the pose, and a hint.

| What it prints | Meaning | Fix |
|---|---|---|
| under 2 N | Good. | Go on to step 5. |
| z reading **positive** (up), e.g. +1.5 N | Mass in Elements is **too high**, by reading / 9.81 (1.5 N = about 150 g). | Lower the mass. Did you type grams as kg x 10, or weigh it with something extra? |
| z reading **negative** (down) | Mass in Elements is **too low** by the same rule. The handle is heavier than typed. | Raise the mass. Screws, washers and tape included? |
| x or y reading over 1 N | Gravity cannot do that directly: the **CoM** is off. | Check mm versus m, the sign, and that z is measured from the flange face, not from the plate's far side. |
| Changes by more than 1 N between two poses | CoM off (a mass error stays the same in every pose; a CoM error does not). | Re-measure the balance point. |
| Active tool is not `RehabHandle` | It was saved but not selected. | Step 3, Select. |

Repeat step 4 after every change. Then run it again with the arm in a second pose (jog 15 cm
along the reach): both under 2 N and within 1 N of each other is the goal.

## 5. After the tool is active

- [ ] **Re-read the start pose**: the TCP moved from the flange face to the grip middle, so the
      old `tcp_pose` is wrong (the joint angles `q` are not). The pose printed by step 4 goes into
      `robot/config.json` (Kian's agent does this once the arm is free).
- [ ] Tell Shyan: the server must be started with `--tool RehabHandle`
      (`python -m server.run --robot Rizon4-062157 --tool RehabHandle`); with the default `Flange` it now refuses.
- [ ] If the handle is ever taken off, switch the tool back to `Flange` first. A handle tool with
      nothing mounted reads a false upward force.
- [ ] After any power cycle, run step 4 again before a session (whether the selected tool survives a power cycle is not confirmed yet).
