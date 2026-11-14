# Decisions

Format: `YYYY-MM-DD HH:MM | who | what | why`

2026-11-14 | Shyan | Team grows from 3 to 5; recruit 2 more | Hackathon rules require 5-person teams
2026-11-14 | Shyan | REVERSES previous entry: no need to recruit, team stays at 3 | Registration slide says 2 to 5 members allowed
2026-11-14 | Shyan | Project: medication handover for Alzheimer's patients (Track 4) | Clear safety problem, demo shows the arm refusing to let go until a grip is confirmed
2026-11-14 | Shyan | Hardware: Flexiv Rizon 4 | Allocated to us. Joint torque sensing gives a real "patient is pulling" signal
2026-11-14 | Shyan | Release only when BOTH vision (hand on cup) AND force (pull > threshold) agree | Either alone gives false positives: a hand near the cup, or the cup knocked
2026-11-14 | Shyan | One Python app on the arm laptop. robot/arm.py (Kian) exposes go_to_handover/pull_force/open_gripper/retract; software/ (Shiv) owns vision and the state machine and imports arm.py | Clean split so both can build in parallel; Shiv can stub arm.py until the Flexiv is up
2026-11-14 | Shyan | Hand over a small cup, not a loose pill | Easier to grip, see and pull
2026-11-14 | Shyan | PIVOT: drop pill handover. Project is now stroke rehab on the Flexiv: Mode A guided (assist as needed) + Mode B resistance trainer, plus therapist dashboard | Many elderly-care teams; force-controlled rehab uses the Flexiv's torque sensing, which other teams' arms lack. No gripper needed, which removes the biggest hardware risk
2026-11-14 | Shyan | Pitch framing: one dial from "helping" to "challenging" | Both modes are the same impedance controller with different settings, so it is one coherent product, not two demos
2026-11-14 | Shyan | Module split: robot/arm.py (Kian) is the only code that talks to the Flexiv; software/ (Shiv) holds exercise logic and logs; demo/ (Shyan) holds screens and dashboard, reading software's CSV logs | Parallel work with clear interfaces; Shiv stubs arm.py until the arm is up
2026-11-14 15:00 | Shyan | Team is 5: Mat and Gio join. They own demo/ and business/ (website, screens, deck, validation). Shyan, Kian, Shiv are backend and robot only | Splits pitch work from build work so three coders stay on the robot and data
2026-11-14 15:00 | Shyan | New folder server/ owned by Shyan (data contract, SQLite, API, simulated history, exports). software/ stays Shiv (control engine, metrics, sim). The seam is server/contract.py: Shiv emits Sample/RepResult/SessionSummary, Shyan stores and serves them | One folder per person so parallel agents on main never edit the same file
2026-11-14 15:00 | Shyan | REPLACES CSV logging: storage is SQLite in server/, with JSON/CSV exports generated for Mat and Gio. Every row carries a simulated flag | Dashboard and deck need queries and history; the flag keeps simulated data labelled end to end
2026-11-14 15:00 | Shyan | Pin flexivrdk to the 1.9.x release matching the robot software; Python 3.12; never unpinned pip install | Flexiv docs: RDK 2.x is for the Enlight robot family only, and there is no Windows wheel for Python 3.14
2026-11-14 15:00 | Shyan | Control uses the arm's native Cartesian impedance (NRT_CARTESIAN_MOTION_FORCE) with live per-axis stiffness; Python streams a target, no force loop in Python | Officially supported pattern in Flexiv example intermediate3; zero stiffness on one axis gives the guided tunnel; safer than a laptop-side force loop
2026-11-14 15:00 | Shyan | Real dates: checkpoint Sun 15 Nov 17:00 (show it working once), final deadline Mon 16 Nov 13:00. Live screen wiring for the demo is decided Sunday | Confirmed by Shyan; backend first
