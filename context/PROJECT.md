# Project — Leukerbad Robotics Hackathon (14–16 Nov)

> **Partly superseded (14 Nov, 15:00).** `context/MASTER_PLAN.md` is the current plan. Where this file differs, MASTER_PLAN wins. In particular: logs are SQLite in `server/`, not CSV; the arm interface is the one in MASTER_PLAN section 4.3; team is 5 with Mat and Gio on demo and business; and we no longer claim that robots or more repetitions give better recovery (see MASTER_PLAN section 1).

## Track
Track 4: Elderly Care & Rehabilitation (confirmed). Example problems from the slides (you can also define your own):
- **Fetch and hand over**: pick up an object and hand it over safely. Suggested kit: Flexiv Rizon 4, WUJI hand, RealSense.
- **Rehab coach**: guide exercises, count reps, give feedback. Suggested kit: VIGX exoskeleton, Zeroth mini humanoid, RealSense.
- **Check-in companion**: chat, remind, and call for help after a fall. Suggested kit: Reachy Mini, AI Cat, webcam.

## Problem
After a stroke, recovery depends on **hundreds of repetitions a day**, but patients get a few short physio sessions a week. Early on they can't move the arm without help. Later they need resistance to rebuild strength. Physios can't be there for every rep, and progress is mostly judged by eye.

## Solution
**One Flexiv Rizon 4 arm that takes a patient from first movement to full strength.** The patient holds a handle on the end of the arm. The arm uses its joint torque sensors to feel exactly how hard they push, and adapts.

The pitch: **one dial, from helping to challenging.** As the patient recovers, the arm moves from guiding them to resisting them.

**Mode A: Guided stroke rehab (assist as needed).**
- Patient traces a path on screen (a line to a target, then a circle) by moving the handle.
- The arm acts as a spring pulling the hand back onto the path. Its **stiffness is the assistance level**.
- Each round, if the patient stays on the path, assistance drops automatically. If they struggle, it goes back up.
- Measures: path error (cm), share of the movement done by the patient, time to target.

**Mode B: Resistance trainer.**
- Patient pushes or pulls the handle along one axis, for example a forward reach.
- The arm resists with a set stiffness or force, like a programmable physio's hand.
- Counts reps, measures peak force (N) and range of motion (cm). Raises resistance as they get stronger.

**Therapist dashboard:** each session logged, with progress over time (assistance level falling, strength rising) for a physio to review remotely.

Patient screen: live path or target, a cursor that follows the handle, and a force bar. This makes the sensing visible to judges.

## Registration (locked 17:00, 14 Nov)
- Team lead (Shyan) fills one form for everyone: team name, track, and name, email, phone and date of birth for each member.
- **One piece of hardware per team.** Limited items are confirmed by email.
- The lead signs the Hackathon Agreement for the whole team, and it binds every member.

## Hardware available
**OUR ITEM: Flexiv Rizon 4** (confirmed 14 Nov). Need: a handle on the flange. Webcam not required.

Shared pool, about CHF 1M of hardware across the carnival. **Ask a technician before switching anything on.**
- **Arms:** Flexiv Rizon 4, Franka Emika, 2× RobCo, AgileX arm, reBot Arm B601, 2× OpenArm + leader, 13× SO-101
- **Hands:** WUJI hand, Leadtron hand, VIGX exoskeleton, Meta Quest 3
- **Humanoids:** UniX AI, Zeroth mini humanoid, PrimeBot, 2× Reachy Mini, AI Cat
- **Mobile:** 2× JoyandAI bases, ROS mobile platform, Waveshare RaspRover, Hover drone
- **Compute/sensors:** 5× RDK X5, Jetson Orin Nano, 2× Raspberry Pi 5, 3× Omnicor chips, 5× NormaCore, MetaCam Lite scanner, RealSense, 2× webcams
- **Cloud:** Google Cloud sandbox (provided by organisers)

## Stack
- **Arm:** Flexiv Rizon 4 (7 DoF, torque sensor in every joint) via Flexiv RDK (`flexivrdk`, Python) over Ethernet from one laptop. Uses Cartesian impedance / motion-force control (confirm exact mode names in RDK docs with the technician).
- **End effector:** a handle on the flange (or a handle clamped in the fitted gripper). No grasping needed.
- **Exercise logic:** Python, one app on the arm laptop (module split in DECISIONS.md).
- **Screens:** patient view plus therapist dashboard, e.g. a local web page or pygame fed by the session logs.
- **Optional:** Gemini on the GCP sandbox for spoken encouragement and a session summary. The demo must work offline.

## Demo plan
1. **Guided mode, high assistance:** a "stroke patient" (team member with a limp arm) is guided along the path by the arm. Screen shows the path, cursor and the arm doing most of the work.
2. **Assist as needed:** same person tries harder, error drops, assistance falls live on screen.
3. **Resistance mode:** switch dial to "challenge", do 5 reps against resistance, screen shows reps, peak force and range of motion.
4. **Dashboard:** 2 weeks of simulated sessions showing assistance falling and strength rising. "A physio sees this from home."

## Judging criteria
