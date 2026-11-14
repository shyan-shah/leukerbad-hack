# Project — Leukerbad Robotics Hackathon (14–16 Nov)

## Track
Track 4: Elderly Care & Rehabilitation (confirmed). Example problems from the slides (you can also define your own):
- **Fetch and hand over**: pick up an object and hand it over safely. Suggested kit: Flexiv Rizon 4, WUJI hand, RealSense.
- **Rehab coach**: guide exercises, count reps, give feedback. Suggested kit: VIGX exoskeleton, Zeroth mini humanoid, RealSense.
- **Check-in companion**: chat, remind, and call for help after a fall. Suggested kit: Reachy Mini, AI Cat, webcam.

## Problem
People with Alzheimer's often miss or refuse doses, or reach for a tablet without actually taking hold of it. Carers can't stand over every dose, and they need to know the patient actually received it.

## Solution
A **Flexiv Rizon 4 arm hands a pill cup to the patient** and **only lets go once it's sure they have hold of it**:
1. Arm brings the cup to a handover point at a slow, safe speed. Voice prompt: "Hi Margaret, here's your 9am tablet, please take the cup."
2. **Check A (vision):** the webcam with MediaPipe Hands sees a hand closed around the cup.
3. **Check B (force):** the Rizon's joint torque sensors register a pull on the cup beyond a set threshold.
4. **Both A and B true:** open the gripper, log the dose as given. **Only one, or neither:** keep holding, re-prompt. **Timeout (around 30 s):** retract and alert a carer.
5. Stretch: vision checks the cup reaches the mouth.

## Registration (locked 17:00, 14 Nov)
- Team lead (Shyan) fills one form for everyone: team name, track, and name, email, phone and date of birth for each member.
- **One piece of hardware per team.** Limited items are confirmed by email.
- The lead signs the Hackathon Agreement for the whole team, and it binds every member.

## Hardware available
**OUR ITEM: Flexiv Rizon 4** (confirmed 14 Nov). Webcam: own laptop.

Shared pool, about CHF 1M of hardware across the carnival. **Ask a technician before switching anything on.**
- **Arms:** Flexiv Rizon 4, Franka Emika, 2× RobCo, AgileX arm, reBot Arm B601, 2× OpenArm + leader, 13× SO-101
- **Hands:** WUJI hand, Leadtron hand, VIGX exoskeleton, Meta Quest 3
- **Humanoids:** UniX AI, Zeroth mini humanoid, PrimeBot, 2× Reachy Mini, AI Cat
- **Mobile:** 2× JoyandAI bases, ROS mobile platform, Waveshare RaspRover, Hover drone
- **Compute/sensors:** 5× RDK X5, Jetson Orin Nano, 2× Raspberry Pi 5, 3× Omnicor chips, 5× NormaCore, MetaCam Lite scanner, RealSense, 2× webcams
- **Cloud:** Google Cloud sandbox (provided by organisers)

## Stack
- **Arm:** Flexiv Rizon 4 (7 DoF, torque sensor in every joint) via Flexiv RDK (`flexivrdk`, Python) over Ethernet from one laptop.
- **Vision:** laptop webcam, OpenCV and MediaPipe Hands, all running locally.
- **Voice, logging, alerts:** Gemini on the Google Cloud sandbox. Optional: the demo must still work offline.
- **Everything runs in one Python app** on the laptop wired to the arm (see DECISIONS.md for the module split).

## Demo plan
1. Normal dose: patient grips and pulls, arm releases, dose logged.
2. Patient reaches out but doesn't grip, or touches without pulling: arm holds on and re-prompts. **This shows why both checks matter.**
3. No response: timeout, arm retracts, carer gets an alert.

## Judging criteria
