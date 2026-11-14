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
