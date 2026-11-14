# Decisions

Format: `YYYY-MM-DD HH:MM | who | what | why`

2026-11-14 | Shyan | Team grows from 3 to 5; recruit 2 more | Hackathon rules require 5-person teams
2026-11-14 | Shyan | REVERSES previous entry: no need to recruit, team stays at 3 | Registration slide says 2 to 5 members allowed
2026-11-14 | Shyan | Project: medication handover for Alzheimer's patients (Track 4) | Clear safety problem, demo shows the arm refusing to let go until a grip is confirmed
2026-11-14 | Shyan | Hardware: Flexiv Rizon 4 | Allocated to us. Joint torque sensing gives a real "patient is pulling" signal
2026-11-14 | Shyan | Release only when BOTH vision (hand on cup) AND force (pull > threshold) agree | Either alone gives false positives: a hand near the cup, or the cup knocked
2026-11-14 | Shyan | One Python app on the arm laptop. robot/arm.py (Kian) exposes go_to_handover/pull_force/open_gripper/retract; software/ (Shiv) owns vision and the state machine and imports arm.py | Clean split so both can build in parallel; Shiv can stub arm.py until the Flexiv is up
2026-11-14 | Shyan | Hand over a small cup, not a loose pill | Easier to grip, see and pull
