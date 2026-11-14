# MASTER PLAN

Leukerbad Robotics Hackathon, Track 4 (Elderly Care and Rehabilitation). Written Sat 14 Nov 2026. Supersedes `context/KICKOFF.md` where they differ; KICKOFF packages (K0, S0a to S0d, Y0a to Y0d, B0, B1) stay valid and are prerequisites here.

**Dates:** checkpoint **Sun 15 Nov 17:00** (show it working once). Final deadline **Mon 16 Nov 13:00**.

**Team:** Kian `robot/`, Shiv `software/`, Shyan `server/`, Mat and Gio `demo/` and `business/`.

**Judging criteria are not published.** This plan assumes: working live demo, technical depth, real-world impact, business viability, pitch quality, roughly equal. If the organisers publish criteria, re-rank the SHOULD list first.

**Source labels used everywhere in this file:**
- **[A]** opened and read by Claude in this session.
- **[B]** read by a research agent, with a locator; not re-opened. Mat or Gio confirm before it goes on a slide.
- **[U]** UNVERIFIED: search snippet, second-hand, or blocked page. Never on a slide until checked.
- **[ASSUMPTION]** a number we chose. Never presented as a fact.

## 1. Verdict

**SHARPEN. Keep the build, change the claim.**
1. Keep: stroke arm rehab on the Flexiv, one dial from helping to challenging. Hardware is locked, two pivots already happened, and the control approach is confirmed against Flexiv's own example [A].
2. Drop the claim "robots give better recovery". The largest trial (RATULS, 770 patients) found robot training "did not improve upper limb function after stroke compared with usual care" [A], and NICE tells the NHS not to offer it [B]. A judge who knows the field will raise this in the first question.
3. New claim: rehab robots already match a therapist hour for hour, and still failed, because each one is an expensive single-purpose machine that needs its own therapist. Bionik, which sells the InMotion arm robot, sold 13 units in a year with 12 staff [A]. The gap is cost and usage, not capability.
4. So the company is the software that turns a general-purpose force-sensing arm into a rehab station that serves weak and strong patients on the same hardware, measures every repetition, and writes the note. That the cost per therapy hour comes out lower is our hypothesis to prove, not a fact we have.
5. Wedge to test this weekend: Swiss inpatient rehab clinics. The clinic in town treats musculoskeletal patients, not stroke [A], so shoulder rehab is a second hypothesis for Mat and Gio's interviews, not yet a claim.

## 2. Company one-pager

**Name (working):** Dial. [U] nobody has checked the trademark or domain; Mat or Gio search the Swiss (IGE), EU (EUIPO) and UK (IPO) registers before it goes on a slide.

**One-liner:** Dial is software that turns a standard force-sensing robot arm into an arm-rehab station: it helps a weak arm move, challenges a strong one, and measures every repetition.

**Problem.** After a stroke, about three in four patients have a weak arm (77.4% of 1,259 first strokes, Lawrence 2001 [B]). Guidelines ask for far more therapy than services deliver: NICE asks for at least 3 hours a day, 5 days a week [B]; an audit of England, Wales and Northern Ireland found 25% of eligible patients got the equivalent of 45 minutes of physiotherapy 5 days a week [B]. Observed sessions contain about 32 task-specific arm repetitions (Lang 2009 [B]). Progress is mostly judged by eye and written up by hand.

**What has been tried, honestly.** Rehab robots exist and have been tested properly.
- RATULS (Lancet 2019): arm function success in 44% of the robot group, 50% of the intensive therapy group, 42% of usual care; no significant differences; "These results do not support the use of robot-assisted training as provided in this trial in routine clinical practice" [A]. The full report found it was not cost-effective [B].
- NICE NG236 (2023), recommendation 1.13.18: "Do not offer robot-assisted arm training as part of an upper limb rehabilitation programme" [B].
- Meta-analyses: robots are about equal to dose-matched therapy, with a small edge on impairment scores for end-effector devices (Wu 2021 [B]; Mehrholz 2018 and 2020 [B]).
- More repetitions alone are not a proven fix in chronic stroke: a dose trial found no dose-response (Lang 2016 [B]). We do not claim "more reps means more recovery".
- Switzerland: "nearly every rehab clinic maintains robot-assisted devices as prestige objects, even though their benefit is not undisputed" (Suva Medical, 2021, our translation [A]).
- Commercially: Bionik sold 13 InMotion robots in fiscal 2023, about 450 ever, with 12 full-time employees [A] and revenue of about $1.8M [B].

**Insight.** The robots did not lose on outcomes. They tied, at higher cost. A single-purpose machine sits idle whenever its one patient type is not in the room, and still ties up one therapist. Equal outcomes become valuable only when the therapy hour gets cheaper. Two levers do that: commodity hardware that many patient types can use, and one therapist supervising several stations. Both are hypotheses we must prove with a clinic; neither is shown by anyone yet.

**Why now.**
- Seven-axis arms with torque sensing in every joint are catalogue products. Flexiv states the Rizon has IEC 60601 certification (manufacturer statement, certificate not seen [B]). KUKA sells a medical-grade arm for integration into medical products, and one company (Life Science Robotics, ROBERT) already ships a rehab device built on it [B]. We found no commercial rehab product on Franka, UR or Flexiv arms [B].
- One CE mark now reaches three markets: Switzerland recognises CE marking unilaterally [B] and the UK government confirmed in October 2026 it will accept CE-marked devices long term [B].
- Guideline intensity targets rose in 2023 and are not being met [B].

**Product.** Assess, prescribe, train, report.
- A short transparent-mode assessment sets the starting dial.
- One dial from +1 (the arm carries the limb along a guided path) through 0 (free movement inside a haptic tunnel) to -1 (the arm resists like an elastic band). In auto mode it adjusts after every repetition.
- Every repetition is measured: range of motion, path error, smoothness (SPARC, Balasubramanian 2015 [B]), peak force, and a contribution index (ours, not clinically validated).
- A session note is drafted from the data for the therapist to review.
- Robot-agnostic by design: one file (`robot/arm.py`) is the only code that knows which arm it is.

**Wedge.** Swiss inpatient neurological rehab: 38 clinics reporting 16,449 cases in 2024 (ANQ [B]). They are paid a daily flat rate (ST Reha; exact rates [U]), so therapist time saved stays with the clinic, and they already buy robots. Second wedge to test: musculoskeletal shoulder rehab, which is what Leukerbad Clinic does [A]. We do not launch in the NHS for stroke while NICE says not to offer robot arm training.

**Market, bottom-up.** Every row is an input Mat and Gio must confirm; three cells are our assumptions.

| Input | Value | Label |
|-------|-------|-------|
| Swiss neuro-rehab clinics | 38 | [B] ANQ 2024 report |
| US inpatient rehabilitation facilities | about 1,200 (404,000 stays, $9.6bn Medicare, 2023) | [B] MedPAC March 2025 |
| German prevention or rehab facilities, all specialties | 1,079 | [B] Destatis via AOK; neurology share [U] |
| Stations per clinic | 3 (one therapist supervising three) | [ASSUMPTION] |
| Price per station per year, hardware, software and service | CHF 30,000 | [ASSUMPTION], to test in interviews |
| Share of clinics won in 5 years | 15% outside Switzerland, 50% in Switzerland | [ASSUMPTION] |

- Beachhead (Switzerland, neuro): 38 x 3 x CHF 30,000 = **CHF 3.4M a year** if every clinic bought. At 50%, about CHF 1.7M.
- Next (US inpatient rehab): 1,200 x 3 x 30,000 = about 108M a year in the same units if every facility bought; 15% is about 16M.
- Reaching £10M ARR means roughly 400 paid stations at about £25,000 each [ASSUMPTION], about 130 clinics at three each. Switzerland alone cannot do it. The plan needs the US or Germany, and a second indication (shoulder) to raise stations per site.
- We quote no analyst "market size" figures.

**Business model and pricing.** Robot as a service: one annual fee per station covering arm, software, updates and support [ASSUMPTION: CHF 30,000]. For clinics that already own a compatible arm, software only. The price has no evidence behind it yet; question 7 of the interview script exists to test it.

**Unit economics (illustrative, all assumptions).**
- Arm cost: reseller listings put comparable arms around $30,000 to $36,000 (Rizon 4s $35,000; Franka FR3 about EUR 30,200; UR5e $34,500 to $36,500), all [U] until we hold written quotes.
- If an arm costs about 35,000 and lasts 4 years, hardware is about 9,000 a year against a 30,000 fee, before support, installation and regulatory cost.
- Clinic side: a UK specialist physiotherapist (Band 6) costs £59 per working hour (PSSRU 2025 [B]). If three stations let one therapist supervise three patients instead of one for 4 hours a day, 220 days a year, that frees 2 x 4 x 220 = 1,760 therapist hours across the three stations: about 587 hours, or about £35,000, per station per year at that rate, against a fee of about 30,000. At one therapist to two stations it is 440 hours, about £26,000 per station, roughly equal to the fee, so the case needs a ratio of three or a lower price. **This is arithmetic on an unproven supervision ratio**, and one-to-one use would erase it. Proving the ratio safely is the point of the first pilot.

**Go to market.** (1) Two Swiss pilot clinics under a research agreement, healthy volunteers then an ethics-approved study. (2) Publish the supervision-ratio and usage data. (3) CE mark. (4) Sell to the 38 Swiss neuro clinics and their groups. (5) Germany and the US through a distributor that already sells rehab equipment.

**Moat.** Honest view: thin today. It grows from (a) a per-repetition dataset of force and movement tied to outcomes, which single-purpose vendors hold but do not pool across arms; (b) the regulatory file and quality system, which take years; (c) living inside the therapist's daily workflow (notes, progress, prescriptions); (d) supporting several arms so clinics are not tied to one hardware vendor. None of these exists yet.

**Regulatory path.** Not a medical device today; a research prototype used only by healthy team members.
- EU MDR, Annex VIII Rule 9: active therapeutic devices that exchange energy are class IIa unless the exchange is potentially hazardous, then IIb [B, rule text via MDCG 2021-24]. A slow, force-limited arm argues for IIa; a notified body could argue IIb. Tyromotion's Diego factsheet states class IIa (2018, before MDR) [B]. Treat the class as unconfirmed.
- Rule 11: software that drives a device takes the device's class [B]. Rule 22 (closed-loop systems with a diagnostic function, class III) is a question to prepare for; our position is that the dial adapts assistance and makes no diagnosis.
- Standards: IEC 60601-1, IEC 80601-2-78 (rehabilitation robots), ISO 13485, IEC 62304, ISO 14971.
- Time: in a 2023 survey of notified bodies, the 6 to 12 month and 13 to 18 month bands together made up 73% of answers for average time to a new MDR certificate [B, Team-NB; whether that counts certificates or notified bodies is to be checked]; add the time to build the quality system and technical file first. Our planning figure is 24 to 30 months from funding [ASSUMPTION]. Cost [U].
- Switzerland and UK: via CE recognition [B].
- US: comparable devices (InMotion, Armeo, BURT) are listed as exempt from premarket notification under 21 CFR 890.5380 and 890.1925 [B]. **We do not claim this for ourselves**; the exemption has limits and a device on a general-purpose arm needs a written regulatory opinion or an FDA pre-submission first.

**Reimbursement.** Swiss inpatient rehab is paid per day, so no device-specific code is needed, and the clinic must see a staffing benefit. Swiss outpatient physiotherapy pays a flat fee per session (position 7311, 77 tariff points for complex cases [B]; value per point [U]); a Swiss university project noted that under this tariff "investment in modern equipment does not pay off" [B, ZHAW]. So outpatient comes later. US therapy codes pay about $29 to $35 per 15-minute unit and there is no robot-specific code [U, secondary source]. No NHS tariff.

**Competition.**

| Company | Product | Type | Price | Regulatory status | Label |
|---------|---------|------|-------|-------------------|-------|
| Hocoma (DIH) | Armeo Power, Spring | exoskeleton, dedicated | not public | US: listed exempt; EU class not found | [B] |
| Bionik | InMotion ARM | end-effector, dedicated | not disclosed | US: class II, listed exempt | [A] units and staff, [B] rest |
| Tyromotion | Diego, Amadeo | end-effector, dedicated | not public | "class IIa" per 2018 factsheet | [B] |
| Barrett | BURT | end-effector on its own arm | not public | US: listed exempt | [B] |
| Life Science Robotics | ROBERT | on a KUKA medical arm; mainly lower limb, bedside | not public | CE class [U] | [B] |
| Fourier, Motorika, Axinesis, Harmonic Bionics | various | dedicated | not public | [U] | [U] |
| Dial (us) | software on a general cobot | end-effector, general arm | CHF 30k per year [ASSUMPTION] | none; research prototype | |

The closest is ROBERT: proof that a cobot-based rehab device can reach market, and the company to study. Mat and Gio: find its price and unit sales (ask the UK distributor).

**Five-year milestones (plan, all dates are assumptions).**
- Year 1: two Swiss pilot sites; supervision-ratio and usage study with ethics approval; quality system started; second arm supported.
- Year 2: technical file, notified body application; first paid research-use stations.
- Year 3: CE mark; 20 stations; Swiss clinic groups.
- Year 4: Germany and UK private; US regulatory route settled; 120 stations.
- Year 5: 400 stations, about £10M ARR [ASSUMPTION].

**Raise.** Pre-seed about £1.5M for 18 months [ASSUMPTION]: two pilots, the study, quality system, second arm. Seed after the study shows one therapist safely supervising several stations at equal outcomes. If the study does not show that, there is no company, and we will know within a year.

**First three pilot conversations.**
1. **Leukerbad Clinic** (in town). Musculoskeletal, internal medicine and oncology rehab; no neurology, no robots listed; has isokinetic strength testing equipment [A]. Angle: measured, assisted and resisted shoulder and arm exercise. Director of therapies is named on the clinic's site [B]; confirm the name before approaching.
2. **Clinique romande de readaptation, Sion** (Suva, same canton). Details [U]; Mat or Gio check its neuro and upper-limb services on its site.
3. **A technology-forward Swiss neuro clinic**: Rehaklinik Zihlschlacht, Kliniken Valens or cereneo. What each runs today is [U]; they already own arm robots, so the question for them is usage and staffing, not novelty.

## 3. The demo that wins

**Status of screens:** who builds the live screens and how they connect is decided Sunday 12:00. Every screen element below is marked (screen, pending). The demo is designed so the physical arm carries it even with only the terminal readout.

**Cast:** Presenter (talks), Patient (team member acting, introduced as "a healthy team member acting as a patient"), Operator (laptop, hand near the e-stop).

**The single wow moment (0:50 to 1:35):** the arm is carrying a limp arm; the patient starts to try; with nobody touching a control, the arm lets go of the work rep by rep, and a minute later the same arm is pushing back. Helping to challenging, live, in one take.

| Time | What happens | What is said (gist) | Live or not |
|------|--------------|---------------------|-------------|
| 0:00 to 0:20 | Arm idle, handle visible | "Three in four stroke patients have a weak arm. Rehab robots exist. The biggest trial found they are no better than a therapist, and the NHS is told not to buy them. They tie on results and lose on cost. We think the robot should be software." | talk |
| 0:20 to 0:50 | Patient's arm limp on the handle. Dial at +1. Arm carries the hand out and back twice | "Full assistance. The arm feels how hard she pushes, 1,000 times a second. Right now she is doing almost nothing." Contribution near 0 (screen, pending; terminal readout live) | live |
| 0:50 to 1:35 | Patient starts trying. Four to five reps. Dial steps down by itself to about 0 | "Nobody is touching anything. Each rep, if she can do more, the arm does less." | live |
| 1:35 to 1:50 | Dial briefly back to assist. Patient lets go mid-reach. Arm stops within a hand's width | "If she lets go, it stops. How hard it can pull is capped in the code, and above 40 newtons it gives way." (use the forces K2 actually measured) | live, only if K2 release test passed |
| 1:50 to 2:20 | Operator sets dial to resistance. Three reps against the arm | "Same arm, same software, now a strength trainer. Peak force and range on every rep." | live |
| 2:20 to 2:40 | Session note and two-week history | "The note writes itself. This history is simulated to show the idea." The word SIMULATED is on the chart (screen, pending) | note live; history simulated and labelled |
| 2:40 to 3:00 | Close | "Dedicated robots tie with therapists and cost too much. We put the same therapy on a standard arm, for weak and strong patients alike. Next step: a pilot to prove one therapist can run three stations." | talk |

**Optional, only with the technician's explicit yes:** offer a judge the handle in transparent mode for ten seconds.

**Fallbacks.**

| Failure | Response |
|---------|----------|
| Arm faults or trips mid-demo | Operator runs `robot/recover.py` (under 30 s for a minor fault [B]); Presenter talks through the safety design meanwhile. Second fault: switch to backup video |
| Arm will not enable | Backup video immediately, then `server.run --sim` to show the software live, stated as simulated |
| Auto dial does not fall | Operator lowers the dial by hand and says so |
| Laptop or API crash | Arm holds by itself on lost connection [B]; restart script; backup video if over 30 s |
| No screens ready | Terminal readout (`server.watch`) on the projector |
| Network or internet down | Nothing in the demo needs it |
| Patient actor unavailable | Any team member; roles are rehearsed by two people each |

## 4. Technical architecture

### 4.1 Diagram

```
 person's hand
      |  handle on flange
 +----------------+        Ethernet, flexivrdk 1.9.x (pinned)
 | Flexiv Rizon 4 | <---------------------------------------------+
 +----------------+                                               |
                                                                  |
 one Python 3.12 process on the arm laptop                        |
 +----------------------------------------------------------------+---+
 |  robot/arm.py  class Arm            (Kian)   ONLY code touching RDK |
 |     safety clamps, monitors, watchdog, stiffness worker             |
 |  software/sim_arm.py class SimArm   (Shiv)   same interface, no RDK |
 |            ^ get_state()  set_target()  set_stiffness()  hold()     |
 |  software/engine.py  class Engine   (Shiv)   100 Hz thread          |
 |     paths, controller, rep detector, metrics, dial adaptation       |
 |            | on_sample(Sample)   on_rep(RepResult)                  |
 |  server/   (Shyan)                                                  |
 |     db.py SQLite   api.py FastAPI REST + WebSocket 30 Hz            |
 |     note.py session note   export.py JSON/CSV   watch.py terminal   |
 +---------------------------------------------------------------------+
            | http://<laptop>:8000   (works with no internet)
   Mat and Gio: demo/ pages, deck (from server/exports/ and the API)
```

Import direction is one way: `software/` imports `robot.arm` types and `server.contract` only. `server/` imports `software.engine`, `software.sim_arm`, `robot.arm`. `robot/` imports nothing from the other two.

### 4.2 Control approach

The arm runs its own Cartesian impedance controller (`NRT_CARTESIAN_MOTION_FORCE`). Python never closes a force loop. Each 100 Hz tick the engine sends one target point; a few times per rep it changes the per-axis stiffness. The arm is a spring between the hand and the target: `force = K * (target - hand)` per base axis. Confirmed pattern in Flexiv's own example `intermediate3_non_realtime_cartesian_pure_motion_control.py` on the v1.x branch [A].

- **Reach axis** is one base axis (x unless Kian's start pose says otherwise), so "along the path" and "across the path" are separate stiffness values.
- **Tunnel walls:** across-path stiffness `K_WALL` on the two other axes, target on the path line. The hand is pushed back to the line.
- **The dial `D`** is one number from -1 to +1:
  - `D > 0` assistance. Along-path stiffness `K_axis = D * K_ASSIST`. The target follows a smooth 4 second reference (min-jerk) from start to end. If the hand is ahead of the reference the target sits on the hand (no force). If the hand is behind, the target leads it, never by more than `MAX_LEAD`. So help appears only when the person falls behind.
  - `D = 0` transparent. `K_axis = 0`, the axis floats, walls stay.
  - `D < 0` resistance. `K_axis = -D * K_RESIST`. The target sits on the path `MAX_LEAD` behind the hand (toward the start), like an elastic band of constant pull. Never beyond the path start.
- **Auto mode (assist as needed):** after each rep, `D` drops by 0.15 if the rep was a success (completed, mean path error under 1.5 cm, duration under 6 s, contribution over 0.6, not rescued), rises by 0.10 if it failed (not completed, or contribution under 0.3, or rescued), else stays. Clamped to [-0.6, +1.0] in auto. Manual mode holds `D` where the therapist sets it.
- **Stall rescue:** during a rep on the assist side, if along-path speed stays under 1 cm/s for 1.5 s before 90% progress, the engine raises `D` to at least 0.6 for the rest of that rep and marks the rep `rescued`. On the resist side a 3 s stall drops to transparent.
- **Orientation** is locked to the start orientation at nominal rotational stiffness.

**Rep state machine (what starts and stops a rep).**
- `idle`: target on the hand at the start point, `K_HOLD`. A rep is armed when the hand has been within 2 cm of the start for 1.0 s **and the handle is occupied**.
- `out`: the reference clock starts at that moment (so a limp arm is carried without having to move first). Ends when progress reaches 0.9 (completed) or after 10 s (not completed).
- `back`: same law toward the start. Ends within 2 cm of the start, then `idle`.
- **Occupied** means the force magnitude on the handle has been above `F_PRESENT` (start value 1.5 N) within the last 0.5 s. A resting limb loads the handle with its weight and drag; an empty handle reads about zero. K3 measures both to confirm they can be told apart.
- **Hands-off rule (assist side only, `D > 0`):** if the handle is not occupied, the engine stops advancing: target on the hand, `K_HOLD`, phase `idle`, rep marked not completed. So an empty handle is never driven along the path, and letting go mid-reach stops the arm within about 0.5 s (at most about 8 cm at 0.15 m/s). On the transparent and resist side letting go is benign by design: the axis floats, or the band returns the handle to the start and stops there.
- If K3 shows a limp arm cannot be told from an empty handle, fallback: the operator starts each set with `POST /api/go` and the hands-off rule uses a 1.0 s window. Decide at I3.
- **Contribution is computed on the `out` phase only**, in every mode (on the return a person braking the band would otherwise score about half). On the resist side, success for the auto dial is: completed, path error under 1.5 cm, duration under 6 s, not rescued.

**The commanded spring force is bounded by construction:** the arm never accepts a target more than `MAX_LEAD` from the hand and never accepts stiffness above `K_MAX`, so while targets are streaming the spring pull cannot exceed `K_MAX * MAX_LEAD` = 600 N/m * 0.05 m = **30 N**, whatever the engine asks for. Two cases are outside that bound and are covered separately: in `hold` the target is a fixed point, so force grows as the person pushes away from it (300 N/m, so 40 N at 13 cm, where the force trip fires); and between a stale target and the 0.2 s watchdog. `SetMaxContactWrench` and the 40 N trip cover both. K2 measures the real peak force in all three cases; until then nobody says "cannot exceed 30 N" on stage.

**Starting values. Signatures are frozen; these numbers are not.** Kian tunes them on the arm and records the final values in `robot/TUNING.md`.

| Name | Start value | Where it lives | Note |
|------|-------------|----------------|------|
| `K_MAX` | 600 N/m | `robot/arm.py` Limits | hard clamp, must be at most `robot.info().K_x_nom` (read at connect) |
| `MAX_LEAD` | 0.05 m | Limits | hard clamp on distance from hand to target |
| `K_HOLD` | 300 N/m | Limits | soft hold stiffness on all three axes |
| `MAX_LINEAR_VEL` | 0.15 m/s | Limits | passed explicitly on **every** `SendCartesianMotionForce` call (RDK default is 0.5) |
| `MAX_LINEAR_ACC` | 0.5 m/s^2 | Limits | passed explicitly on every call (RDK default is 2.0) |
| `TRIP_SPEED` | 0.40 m/s | Limits | measured hand speed above this drops to hold |
| `TRIP_FORCE` | 40 N | Limits | measured external force above this drops to hold |
| `MAX_CONTACT` | 30 N, 5 Nm | Limits | `SetMaxContactWrench([30,30,30,5,5,5])` |
| `WATCHDOG` | 0.2 s | Limits | no `set_target` for this long drops to hold |
| workspace box | start pose +/- (0.35, 0.10, 0.10) m along (reach, side, up) | Limits | targets outside are clamped; hand more than 2 cm outside trips to hold |
| `K_WALL` | 500 N/m | `software/controller.py` | |
| `K_ASSIST` | 400 N/m | controller | max assist pull = 400 * 0.05 = 20 N |
| `K_RESIST` | 300 N/m | controller | max resistance = 300 * 0.05 = 15 N |
| reach length | 0.30 m | controller | |
| reference time | 4.0 s out, 4.0 s back | controller | |

**Layers of safety (all required before a person holds the handle):**
1. Technician-set limits in Flexiv Elements: TCP speed, force, and a safety plane between the arm and the person's torso. These are not reachable from RDK [B], so only the technician can set them.
2. In-code limits in `robot/arm.py` (table above). The caller cannot override them.
3. Loss of laptop connection: the robot stops and holds by itself [B].
4. Operator dead-man: the run script holds only while the operator's session is active; `hold()` on Ctrl+C, on any exception, and from `POST /api/hold`.
5. Physical e-stop within reach of a named person whenever the arm is enabled.
6. Technician sign-off recorded in `robot/SAFETY.md` (package K2), including the **release test**: the person lets go mid-reach in assist and in resistance; the arm must coast slowly to the path end or start and stop.
7. Healthy team members only. Nobody with an injury or impairment touches the device. The demo "patient" is an actor and is described as one.

### 4.3 Frozen interface: the arm

`robot/arm.py` (real) and `software/sim_arm.py` (simulated) expose the same names and behaviour. Extends the list in the old TASKS.md (`connect, set_stiffness, set_target, get_pose, get_force, stop`); `get_pose` and `get_force` are merged into `get_state`.

```python
# robot/arm.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ArmState:
    t: float                                  # time.monotonic(), seconds
    pos: tuple[float, float, float]           # handle (TCP) position, m, base frame
    quat: tuple[float, float, float, float]   # qw, qx, qy, qz
    vel: tuple[float, float, float]           # m/s, base frame
    force: tuple[float, float, float]         # N, force the PERSON applies to the handle, base frame
    q: tuple[float, ...]                      # 7 joint angles, rad
    mode: str                                 # "idle" | "compliant" | "hold" | "fault"
    fault: str | None                         # human-readable reason for the last trip, else None

@dataclass(frozen=True)
class Limits:
    k_max: float = 600.0
    max_lead_m: float = 0.05
    k_hold: float = 300.0
    max_linear_vel: float = 0.15
    max_linear_acc: float = 0.5
    trip_speed: float = 0.40
    trip_force: float = 40.0
    max_contact_n: float = 30.0
    max_contact_nm: float = 5.0
    watchdog_s: float = 0.2
    box_half_m: tuple[float, float, float] = (0.35, 0.10, 0.10)   # around the start pose, base axes

class Arm:
    limits: Limits
    start_pos: tuple[float, float, float]     # set by home() or start_compliance()

    def __init__(self, serial: str, limits: Limits = Limits()) -> None: ...
    def connect(self) -> None                 # connect, clear fault, enable, wait operational, read K_x_nom
    def zero_force(self) -> None              # ZeroFTSensor primitive. Nothing may touch the arm.
    def home(self) -> None                    # slow move to the start pose from BRINGUP.md. Nobody holding. Blocking.
    def start_compliance(self) -> None        # enter Cartesian mode holding the current pose at k_hold; records start_pos
    def set_stiffness(self, kx: float, ky: float, kz: float) -> None
        # N/m per base axis, each clamped to [0, k_max]. Returns immediately; applied by a worker
        # (latest value wins) because the RDK call blocks. Takes effect within about 100 ms.
    def set_target(self, pos: tuple[float, float, float]) -> None
        # non-blocking. Clamped first to the workspace box, then to max_lead_m from the current hand
        # position. The lead clamp always wins (the final target is never more than max_lead_m from the hand).
        # Orientation is always the start orientation. Feeds the watchdog.
    def get_state(self) -> ArmState           # fresh state; also runs the trip checks: speed, force, and
                                              # hand more than 2 cm outside the workspace box
    def hold(self) -> None                    # soft stop: target = current position, k_hold on all axes, mode "hold"
    def stop(self) -> None                    # hard stop: robot.Stop(), mode "idle"
    def close(self) -> None                   # hold, restore nominal stiffness (it persists on the robot), stop
```

Rules both classes obey:
- `force` sign: pushing the handle toward +x gives `force[0] > 0`. `Arm` fixes the sign internally from Kian's bring-up answer.
- After a trip (`mode == "hold"` with `fault` set) `set_target` and `set_stiffness` are ignored until `start_compliance()` is called again.
- `set_target` or `set_stiffness` before `start_compliance()` raises `RuntimeError`.
- Every RDK call inside `Arm` is under one lock.

`SimArm` adds only: `SimArm(patient: SimPatient, limits: Limits = Limits(), start_pos=(0.45, 0.0, 0.30), realtime=True)` and `step(dt)` for fast tests when `realtime=False`.

### 4.4 Frozen interface: the engine

```python
# software/engine.py
class Engine:
    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool,
                 reach_axis: int = 0, reach_sign: int = 1, reach_m: float = 0.30,
                 dial: float = 1.0, auto: bool = True,
                 on_sample=None, on_rep=None) -> None: ...
        # on_sample(Sample) at 100 Hz and on_rep(RepResult) at each rep end, called from the engine thread.
        # Callbacks must return fast (the server just puts them on a queue).
    def start(self) -> None                   # arm.start_compliance(), then the 100 Hz thread
    def stop(self) -> "SessionSummary"        # arm.hold(), thread joined
    def set_dial(self, dial: float, auto: bool | None = None) -> None
    def snapshot(self) -> dict                # latest Sample as dict plus rep_count, auto, arm_mode. Thread-safe.
```

Pure functions the engine is built from (each unit-testable with no arm):

```python
# software/controller.py
def command(dial: float, phase: str, s_hand: float, t_in_phase: float, pos, path: LinePath,
            rescued: bool) -> tuple[tuple[float, float, float], tuple[float, float, float]]
    # returns (target_pos, (kx, ky, kz)). phase is "out" or "back".

# software/adapt.py
def next_dial(dial: float, rep: RepResult, auto_floor: float = -0.6) -> float
def mode_of(dial: float) -> str               # "assist" | "transparent" | "resist"
```

### 4.5 Frozen data contract (`server/contract.py`, owner Shyan)

As in KICKOFF, plus these added fields (nothing renamed): `Sample.phase: str` ("idle" | "out" | "back"), `Sample.q: tuple[float, ...]` (7 joint angles, for a future 3D view), `RepResult.rescued: bool`. Every record keeps `simulated: bool`.

### 4.6 API (owner Shyan, `server/api.py`), all local, no internet needed

| Route | Does |
|-------|------|
| `GET /api/health` | `{"ok": true, "arm": "sim" or "flexiv", "arm_mode": ...}` |
| `GET /api/state` | `Engine.snapshot()` or `{"session": null}` |
| `POST /api/session/start` body `{patient_id, display_name, dial, auto}` | creates the session, starts the engine. `simulated` is set by the server from the arm type, never by the caller |
| `POST /api/session/stop` | stops, saves the summary, writes exports |
| `POST /api/dial` body `{dial, auto}` | manual dial or back to auto |
| `POST /api/hold` | soft stop now |
| `POST /api/go` | operator cue to arm the next rep (only used if the occupied check is unreliable) |
| `GET /api/patients` | list |
| `GET /api/patients/{id}/sessions` | list of SessionSummary plus per-session metric means |
| `GET /api/sessions/{id}/reps` | list of RepResult |
| `GET /api/sessions/{id}/note` | plain-text session note (template, not AI) |
| `WS /ws/live` | 30 Hz `{"type": "sample", ...Sample, "rep_count", "auto", "arm_mode"}` and `{"type": "rep", ...RepResult}` on each rep |

CORS is open (local network only). If `demo/site/` exists the server also serves it at `/`, so Mat and Gio's pages can be opened from any device on the same network.

Database: `server/data/rehab.db` (git-ignored). Tables `patients`, `sessions`, `reps`, columns equal to the contract fields, each with `simulated`.

Run commands:
- `python -m server.run --sim` : simulated arm and patient, full API. This is also the mock feed for Mat and Gio.
- `python -m server.run --robot Rizon4-XXXXXX` : real arm.
- `python -m server.watch` : terminal live readout (dial, progress bar, force, rep table). Enough on its own for the Sunday checkpoint.

### 4.7 Feature ranking

| Feature | Rank | Judge impact | Build risk | Decision |
|---------|------|--------------|-----------|----------|
| Assist as needed on native impedance, haptic tunnel, straight reach | MUST | very high | medium | core demo |
| Resistance on the same controller (one dial) | MUST | high | low | same code path |
| In-code safety limits, release test, sign-off | MUST | high with robotics judges | low | non-negotiable |
| Per-rep metrics: ROM, path error, SPARC, peak force, contribution | MUST | high | low | pure functions, done on stub |
| SQLite, API, exports, terminal readout, `simulated` flag end to end | MUST | medium | low | enables everything Mat and Gio do |
| Sim arm and simulated patient | MUST | low directly | low | lets three people work with one robot |
| Template session note (deterministic) | SHOULD | medium | very low | Y3 |
| 60 second assessment that picks the starting dial | SHOULD | medium | low | S5 |
| Live screens (patient view, physio view) | SHOULD, owner and wiring decided Sunday | very high | medium | API is ready for them |
| QR code so judges open the physio view on their phone | SHOULD | high | medium (hotspot with no internet can misbehave) | only after live screens work |
| Live 3D twin in the browser | STRETCH | medium | medium | `Sample.q` is already in the feed |
| Webcam trunk-compensation flag | STRETCH | medium | high | no single-webcam validation found in stroke [B]; if built, call it experimental |
| LLM-written notes on GCP | STRETCH | low | low | cached fallback labelled "cached" |
| Circle or 2D paths | CUT unless idle | low | medium | per-axis stiffness makes curved tunnels hard |
| Games, hand or grip, VR, EMG, voice | CUT | | | |

## 5. Agent work packages

How to use: open a fresh Claude Code session in the repo and paste

> Run `git pull origin main`. Read `CLAUDE.md`, then `context/MASTER_PLAN.md` sections 4 and 5, and the "Rules for every agent" in `context/KICKOFF.md`. Do package **<ID>** exactly as written. Only create or edit the files it lists. Run its acceptance tests and show me the output. Append the LOG line to `context/LOG.md`, commit, pull, push to main.

Packages under one person list different files and can run in parallel unless "Needs" says otherwise. "Stub" means it can start now with no robot.

### Kian (robot/)

**K1: `robot/arm.py`** (start now, write against the interface; test on the arm when K0 is done)
- Files: `robot/__init__.py`, `robot/arm.py`, `robot/tests/test_arm_offline.py`.
- Needs: K0 answers in `robot/BRINGUP.md` for serial, force sign, start pose, `K_x_nom`. Until then use placeholders loaded from `robot/config.json` (create it; never hard-code).
- Build section 4.3 exactly. Facts to use: KICKOFF K0 list. Pass `max_linear_vel` and `max_linear_acc` on every `SendCartesianMotionForce(pose, [0]*6, [0]*6, max_linear_vel, max_angular_vel, max_linear_acc, max_angular_acc)` call. Keep rotational stiffness at nominal. Stiffness worker: one thread, latest value wins, calls `SetCartesianImpedance`. Watchdog: one thread, calls `hold()` if no `set_target` for `watchdog_s` while compliant. `close()` restores `robot.info().K_x_nom`. `home()`: if Kian has confirmed a move primitive with the technician use it, otherwise ramp the target in a straight line at 0.05 m/s at nominal stiffness.
- Put all clamping in pure helper functions (`clamp_target(pos, hand, start, limits)`, `clamp_stiffness(k, limits, k_nom)`) so they are testable offline.
- Tests (offline, no robot, `flexivrdk` import must be lazy so tests run anywhere): for 1,000 random inputs the clamped target is always within max_lead of the hand, and inside the box whenever the hand is at least max_lead inside it; stiffness never exceeds k_max; a hand 3 cm outside the box trips; calling `set_target` before `start_compliance` raises; after a simulated trip commands are ignored.
- Run: `python -m pytest robot/tests/test_arm_offline.py -q`
- LOG: `K1 done: arm.py matches section 4.3, offline tests pass, on-arm test pending/passed`.

**K2: on-arm safety tests and sign-off** (needs K1 and the robot)
- Files: `robot/safety_check.py`, `robot/SAFETY.md`.
- `safety_check.py` is an interactive script that walks one person through, printing PASS or FAIL for each: force reads about 0 untouched; +x push gives positive `force[0]`; soft hold at `k_hold`; target outside box is clamped; target 20 cm from hand is clamped to 5 cm; stiffness 5000 is clamped; pushing above 40 N trips to hold; in hold, push the handle away slowly and record the peak force before the trip; record the peak force seen in assist and resist (must be at or under 30 N); hand pushed 3 cm outside the box trips; stopping the command stream trips the watchdog within 0.3 s; **release test** in assist (target leading 5 cm) and in resistance (target trailing 5 cm): let go: in assist the arm must stop within about 10 cm (hands-off rule, needs the engine; until S4 is on the arm, test that a target 5 cm ahead moves the empty handle slower than 0.20 m/s and stops on it); in resistance it must return slower than 0.20 m/s and stop at the start; Ctrl+C leaves the arm in hold; after `close()` the stiffness on the robot is nominal.
- The technician does every test first. Results, date, names and the Elements limits go in `SAFETY.md`.
- LOG: `K2 done: N of N safety checks pass, technician <name> signed off, limits in robot/SAFETY.md`.

**K3: tuning measurements** (needs K1 and the robot)
- Files: `robot/tune.py`, `robot/TUNING.md`.
- Measure and record: handle force magnitude with an empty handle versus a relaxed arm resting on it, still and while being carried (sets `F_PRESENT`; say plainly if they cannot be told apart); how long `SetCartesianImpedance` blocks (median and max of 50 calls); drag force felt when moving the handle at about 0.2 m/s along a 0 N/m axis (is transparent mode really light?); whether a low non-zero stiffness (50 N/m) with the target on the hand feels lighter or heavier than 0; wall feel at 300, 500, 800 N/m; assist feel at 200, 400, 600; any vibration; best `max_linear_vel`. Recommend final numbers for the section 4.2 table.
- LOG: `K3 done: final K_WALL/K_ASSIST/K_RESIST = ..., stiffness call takes ... ms, transparent drag ... N`. If any number changes, also add a DECISIONS.md line.

**K4: start pose, seating and workspace** (needs K0)
- Files: `robot/config.json`, `robot/SETUP.md` (photo-free written setup: chair position, table height, arm base position, which base axis is the reach, start pose as `tcp_pose` and `q`, safety plane location).
- Check the 0.30 m reach plus the box stays clear of joint limits and singularities: jog through the four corners at low speed and record `q` at each.
- LOG: `K4 done: reach axis <x/y>, start pose recorded, box corners reachable`.

**K5: run book** (stub now, finalise after K2)
- Files: `robot/RUNBOOK.md`, `robot/recover.py`.
- `recover.py`: connect, print fault state, `ClearFault()`, re-enable, restore nominal stiffness. `RUNBOOK.md`: power-on to ready in numbered steps, what each fault looks like and what to do, shutdown steps, who holds the e-stop.
- LOG: `K5 done: runbook covers start, fault, shutdown`.

### Shiv (software/)

**S1: `software/sim_arm.py`** (stub, needs S0d)
- Files: `software/sim_arm.py`, `software/tests/test_sim_arm.py`.
- Implement `SimArm` per section 4.3 using `SimPatient` physics (mass 1.5 kg, damping 8 N s/m, arm spring per axis with the commanded stiffness, patient effort toward the current goal). Reported `force` = patient effort plus a passive limb load when `patient.present` is true (constant 8 N downward plus 5 N s/m drag against motion), and zero when `present` is false, so the hands-off rule can be tested. Import `ArmState` and `Limits` from `robot.arm` if that file exists, otherwise define identical dataclasses locally behind a `try/except ImportError` and delete the fallback once K1 lands. Apply the same clamps (box, lead, k_max), trips and watchdog rules so the engine sees identical behaviour.
- Tests: interface has every method of section 4.3; clamps hold; with `realtime=False` and `step(0.01)` a strong patient at zero axis stiffness moves, a limp one does not; trip then ignored commands; `force` sign convention.
- Run: `python -m pytest software/tests/test_sim_arm.py -q`
- LOG: `S1 done: SimArm passes N tests, matches Arm interface`.

**S2: `software/controller.py`** (stub, needs S0c)
- Files: `software/controller.py`, `software/tests/test_controller.py`.
- Implement `command(...)` per sections 4.2 and 4.4. Constants at the top of the file with the section 4.2 start values, overridable from `robot/TUNING.md` values later by editing the constants only.
- Tests: `D=1`, hand behind the reference gives a target ahead of the hand by at most 0.05 m and `K_axis = 400`; hand ahead of the reference gives target on the hand; `D=0` gives `K_axis = 0`; `D=-1` gives target 0.05 m behind the hand and `K_axis = 300`; wall stiffness on the two other axes in every case; target never leaves the path segment; reach axis 0 and 1 and both signs work.
- Run: `python -m pytest software/tests/test_controller.py -q`
- LOG: `S2 done: controller covers assist, transparent, resist, N tests`.

**S3: `software/adapt.py`** (stub, needs Y0a)
- Files: `software/adapt.py`, `software/tests/test_adapt.py`.
- Implement `next_dial` and `mode_of` per section 4.2.
- Tests: five successes from 1.0 reach 0.25; a failure adds 0.10; clamps at 1.0 and at the auto floor; a rescued rep counts as failure.
- LOG: `S3 done`.

**S4: `software/engine.py`** (stub, needs S0a, S0b, S1, S2, S3, Y0a)
- Files: `software/engine.py`, `software/tests/test_engine.py`.
- Implement section 4.4. Loop at 100 Hz: `get_state`; if `mode` is hold or fault, emit samples with phase "idle" and do not command; else update `RepDetector`, compute `command`, `set_target`, and `set_stiffness` only when the stiffness tuple changes; the rep state machine and hands-off rule of section 4.2; stall rescue; at rep end compute `rep_metrics`, build `RepResult`, call `on_rep`, apply `next_dial` if auto. Any exception in the loop calls `arm.hold()` first, then re-raises.
- Tests with `SimArm(realtime=False)`: limp patient at `D=1` completes 5 reps with contribution under 0.3; strong patient in auto ends below `D=0.3` within 8 reps; strong patient at `D=-1` completes reps with peak force near 15 N; a tripped arm produces no commands; with `patient.present = False` no rep ever starts, and setting it False mid-reach stops target advance within 0.5 s; contribution uses the out phase only; `stop()` returns a summary with the right rep count; every emitted record has `simulated=True`.
- Run: `python -m pytest software/tests/test_engine.py -q`
- LOG: `S4 done: engine runs end to end on SimArm, N tests`.

**S5: `software/assess.py`** (SHOULD, stub, needs S4)
- Files: `software/assess.py`, `software/tests/test_assess.py`.
- `starting_dial(reps: list[RepResult]) -> float`: from 3 transparent reps (completed share, ROM, contribution) choose a starting dial; documented simple rule, labelled "team heuristic, not a clinical assessment".
- LOG: `S5 done`.

### Shyan (server/)

**Y1: contract v1 and API** (stub, needs Y0a, Y0b; can be written before S4 exists by coding to section 4.4)
- Files: `server/contract.py` (add the three fields of section 4.5 with defaults so old rows load), `server/db.py` (add columns), `server/api.py`, `server/tests/test_api.py`.
- FastAPI app factory `create_app(arm_factory, db_path)`. Engine callbacks push to a thread-safe queue; a background task drains it, saves reps, and broadcasts on the WebSocket at 30 Hz (send the newest sample, drop the rest). `simulated` comes from `isinstance(arm, SimArm)`, never from the request.
- Tests with FastAPI `TestClient` and a fake engine: every route in section 4.6 returns the documented shape; start then stop writes a session; a WebSocket client receives sample and rep messages.
- Run: `python -m pytest server/tests/test_api.py -q`
- LOG: `Y1 done: API routes of section 4.6 pass N tests`.

**Y2: run and watch** (stub, needs Y1, S4)
- Files: `server/run.py`, `server/watch.py`.
- `run.py` per section 4.6 (`--sim` with `--strength 0.2` etc. to set the simulated patient; `--robot SERIAL`; `--port`). Ctrl+C and any crash call `arm.hold()` then `arm.close()`. `watch.py` connects to the WebSocket and draws one updating terminal view: dial bar, progress, force, last 10 reps as a table, a red SIMULATED tag when `simulated` is true.
- Acceptance: `python -m server.run --sim` in one terminal, `python -m server.watch` in another, start a session with `curl -X POST localhost:8000/api/session/start -H "content-type: application/json" -d "{\"patient_id\":\"sim-1\",\"display_name\":\"Sim (SIMULATED)\",\"dial\":1,\"auto\":true}"`; reps appear and the dial falls.
- LOG: `Y2 done: sim end to end runs, watch shows reps`.

**Y3: session note** (stub, needs Y0b)
- Files: `server/note.py`, `server/tests/test_note.py`.
- `session_note(summary, reps, previous: list | None) -> str`: plain-text note built from a fixed template: reps completed, dial start and end, mean and best of each metric, change versus the previous session, flags (rescued reps, trips). First line states "Drafted automatically from device data for therapist review" and, when simulated, "SIMULATED DATA". No AI, no clinical advice, no diagnosis words.
- LOG: `Y3 done`.

**Y4: end-to-end test on the sim** (needs Y2)
- Files: `server/tests/test_e2e_sim.py`.
- Starts the app with `SimArm(realtime=False)`, runs 10 reps, asserts 10 rows in `reps`, a note is returned, exports are written, every row is simulated.
- LOG: `Y4 done: e2e sim test passes`.

**Y5: handover for Mat and Gio** (needs Y1)
- Files: `server/API.md`, `server/exports/README.md` (update).
- Plain-English guide: how to start the mock feed, every route and message with a real example copied from a running server, a 20 line HTML file that connects to the WebSocket and prints the dial, and the rule that `simulated: true` must be shown as "simulated".
- LOG: `Y5 done: Mat and Gio can build against server/API.md`.

### Mat and Gio (business/, demo/)

No code required. Each package can be given to an AI assistant as a research or writing task; the human does the phone calls and visits.

**B0, B1:** as in KICKOFF (interviews today, claims table).

**B2: verify the claims list** (start now)
- File: `business/claims.md`. Take every row of section 7 marked [B] or [U], open the source, paste the exact sentence, change the label to "checked by <name>". If the source says something different, write what it actually says and tell Shyan. Deadline Sunday 12:00 for rows marked "slide".

**B3: market model** (start now)
- File: `business/market_model.md` (or a spreadsheet exported to it). Build the bottom-up table in section 2 with one row per input, its source label, and the three [ASSUMPTION] cells highlighted. Replace assumptions with interview answers where you get them.

**B4: deck** (start Sunday morning; needs B2 rows)
- Files: `demo/deck/`. Ten slides following section 2 in order: problem, why robots failed, insight, product (the dial), demo, market, model, regulation, competition, team and ask. One number per slide, each with its source in small print. Simulated charts carry the word SIMULATED on the chart.

**B5: three-minute script, rehearsal, backup video** (Sunday afternoon onward)
- Files: `demo/script.md`, `demo/backup_video.*`. Script from section 3. Record the backup video as soon as the arm does one clean run (Sunday evening at the latest).

**B6: website and screens** (start when `server/exports/` and `server/API.md` exist)
- Files: `demo/site/`. Start with a static page from the export files. How live screens connect is decided Sunday.

**B7: pilot outreach drafts** (Sunday)
- File: `business/outreach.md`. Draft, do not send without Shyan: three short emails to the pilot targets in section 2. Never claim interest, users or results that do not exist.

## 6. Timeline (Swiss time)

| When | Kian | Shiv | Shyan | Mat and Gio | Checkpoint |
|------|------|------|-------|-------------|------------|
| Sat 15:00 to 17:00 | K0 bring-up with technician | S0a to S0d | Y0a, then Y0b to Y0d | B0 interviews in the village, B1 | |
| Sat 17:00 | post K0 answers in LOG | | | | **I0:** RDK connects, licence allows Cartesian mode. If not, see risk R1 |
| Sat 17:00 to 20:00 | K1 arm.py, K4 start pose | S1, S2, S3 | Y1 API, Y3 note | B2, B3 | |
| Sat 20:00 | | | | | **I1:** exports on main; all S0 and Y0 tests green |
| Sat 20:00 to 23:00 | K1 on the arm, K3 tuning | S4 engine | Y2 run and watch | B2 | |
| Sat 23:00 | | | | | **I2:** `server.run --sim` plus `server.watch` shows reps and a falling dial. Real arm holds softly with the handle, floats on one axis |
| Sat 23:00 to Sun 08:00 | sleep. Agents may run test-only work unattended; nobody runs the arm alone or tired | | | | |
| Sun 08:00 to 10:00 | K2 safety checks with technician | fix from I2, S5 | Y4 e2e, Y5 handover | B4 deck | |
| Sun 10:00 | | | | | **I3:** `server.run --robot` full loop, a team member does 5 assisted reps, reps land in the database |
| Sun 10:00 to 12:00 | tune with Shiv on the arm | tune adaptation on the arm | fix data path, real exports | B4, B6 | |
| **Sun 12:00** | | | | | **Internal scope freeze.** Anything not working on the real arm is cut. Decide live-screen owner and wiring now |
| Sun 12:00 to 15:00 | reliability: 10 runs in a row | reliability | live feed for screens | B5 script, B6 | |
| Sun 15:00 | | | | | **I4:** three clean full demo runs in a row |
| **Sun 17:00** | | | | | **Official checkpoint: show it working once** |
| Sun 17:00 to 21:00 | K5 run book, fixes | SHOULD items only if I4 was clean | SHOULD items | record backup video, deck v1 | |
| Sun 21:00 | | | | | **I5:** backup video exists; deck v1 done |
| Sun 21:00 to 23:00 | fixes only | fixes only | fixes only | deck v2, claims final | Feature freeze 23:00 |
| Mon 08:00 to 09:00 | cold start from RUNBOOK | | fresh database, real exports | | **Code freeze 09:00** |
| Mon 09:00 to 12:00 | five full rehearsals with a timer, operator and "patient" roles fixed | | | pitch rehearsal, Q and A from section 8 | |
| Mon 12:00 to 13:00 | nothing changes. Arm warm, e-stop holder named, backup video open | | | | **Mon 13:00 deadline** |

## 7. Validation appendix plan

Owner of every row: Mat and Gio (package B2). "Slide" rows are due **Sun 12:00**; the rest **Sun 21:00**. For each: open the source, paste the exact sentence into `business/claims.md`, write who checked it. If the source says something else, record what it says and tell Shyan.

| # | Claim as we will say it | Source | Label | Action | Slide |
|---|-------------------------|--------|-------|--------|-------|
| 1 | RATULS: success 44% robot, 50% intensive therapy, 42% usual care; does not support routine use | Rodgers et al., Lancet 2019;394:51-62, doi 10.1016/S0140-6736(19)31055-4 | [A] abstract | read the full paper for how many therapists per patient the robot arm needed | yes |
| 2 | RATULS: not cost-effective; robot group had a small impairment gain | Rodgers et al., Health Technol Assess 2020;24(54), doi 10.3310/hta24540 | [B] | open, quote the cost-effectiveness sentence and per-patient costs | yes |
| 3 | NICE: "Do not offer robot-assisted arm training" (rec. 1.13.18) | nice.org.uk/guidance/ng236, Recommendations | [B] page blocked our tool | open in a browser, copy the sentence and number | yes |
| 4 | NICE: at least 3 hours a day, 5 days a week (rec. 1.2.16) | same | [B] | same | yes |
| 5 | 25% of eligible patients got 45 min physio 5 days a week (2022/23) | SSNAP Annual Report 2023 infographic, hqip.org.uk | [B] | open the PDF, copy the figure and its exact definition | yes |
| 6 | About 32 task-specific arm repetitions per session | Lang et al., Arch Phys Med Rehabil 2009;90:1692-8 | [B] abstract | quote; note it applies to sessions that included such practice | yes |
| 7 | No dose-response in chronic stroke | Lang et al., Ann Neurol 2016;80:342-54 | [B] abstract | quote; we cite it against ourselves | Q and A |
| 8 | 77.4% of first strokes have upper-limb weakness | Lawrence et al., Stroke 2001;32:1279-84 | [B] abstract | quote | yes |
| 9 | Robots about equal to dose-matched therapy; small edge for end-effector devices | Wu et al., Phys Ther 2021;101:pzab010; Mehrholz et al., Cochrane 2018 CD006876.pub5 | [B] abstracts | quote both conclusions | yes |
| 10 | Bionik sold 13 robots in FY2023, about 450 ever, 12 full-time staff | Bionik 10-K FY2023, sec.gov (CIK 1508381) | [A] | none | yes |
| 11 | Bionik FY2023 revenue $1,805,202 | same filing, financial statements | [B] | open the filing, find the revenue line | yes |
| 12 | "Nearly every Swiss rehab clinic keeps robot devices as prestige objects; benefit not undisputed" | S. Hellweg, Suva Medical, 31.03.2021 | [A] German original | get a native speaker to confirm our translation | yes |
| 13 | 38 Swiss neuro-rehab clinics, 16,449 cases (2024) | ANQ national comparison report, neurological rehabilitation, 2024 | [B] | open the PDF, quote the sentence | yes |
| 14 | About 1,200 US inpatient rehab facilities, 404,000 stays | MedPAC Report to Congress, March 2025, ch. 8 | [B] | quote | yes |
| 15 | 1,079 German prevention or rehab facilities (all specialties) | Destatis via aok.de | [B] | find the neurology-only number at Destatis | maybe |
| 16 | Global: 11.9M new strokes a year, 93.8M living after stroke | Feigin et al., WSO Global Stroke Fact Sheet 2025, Int J Stroke 20:132-44 | [B] full text | quote | yes |
| 17 | Switzerland: about 16,000 strokes a year | Swiss Heart Foundation backgrounder, Sept 2020 | [B] | quote; look for a newer figure | yes |
| 18 | UK stroke survivors | sources disagree (1.4M Stroke Association 2025 vs "almost 1 million" King 2020) | [B] | pick one, cite it, or drop UK numbers | no |
| 19 | SPARC smoothness definition and defaults | Balasubramanian et al., J NeuroEng Rehabil 2015;12:112; code at github.com/siva82kb/SPARC | [B] | none for the deck; Shiv matches the code | appendix |
| 20 | MDR Rule 9: class IIa unless potentially hazardous, then IIb | MDCG 2021-24 Rev.1, pp. 41-43 | [B] | quote the rule; say "class to be confirmed" | yes |
| 21 | 6 to 18 months is the most common time to a new MDR certificate (73% of answers) | Team-NB survey 2023, p. 21 | [B] | quote the table; check whether the percentages count certificates or notified bodies and word the slide to match | yes |
| 22 | UK accepts CE-marked devices long term | gov.uk news, 21 Oct 2026 | [B] | quote | maybe |
| 23 | Switzerland recognises CE marking unilaterally | bag.admin.ch, Medizinprodukterecht | [B] | quote; check whether the updated EU agreement is in force | maybe |
| 24 | Comparable US devices are listed as exempt from premarket notification | FDA GUDID records for InMotion, Armeo, BURT; 21 CFR 890.5380, 890.1925, 890.9 | [B] | quote; never say this about our device | Q and A |
| 25 | Flexiv Rizon "achieved IEC 60601 certification in 2023" | flexiv.com news article | [B] manufacturer statement | email Flexiv for the certificate number; say "Flexiv states" | maybe |
| 26 | Rizon 4: 7 axes, 4 kg payload, 0.1 N force sensing accuracy | flexiv.com/product/rizon | [B] | quote | yes |
| 27 | Arm prices around $30k to $36k | reseller pages | [U] | ask Flexiv (business@flexiv.com), Franka and a UR distributor for written quotes; until then say "tens of thousands, quotes pending" | no until quoted |
| 28 | UK Band 6 physiotherapist costs £59 per working hour | PSSRU Unit Costs of Health and Social Care 2025, table 11.1.2 | [B] | quote | yes |
| 29 | Swiss outpatient physio: 77 tariff points per complex session | fedlex, physiotherapy tariff valid from 1 Jan 2026, position 7311 | [B] | quote; find the value of a point in Valais | maybe |
| 30 | Swiss tariffs make outpatient robot investment not pay off | ZHAW news release on Revigo | [B] | quote and date | Q and A |
| 31 | ROBERT is a commercial rehab device on a KUKA medical arm | unitedrobotics.group blog; KUKA | [B] | find price, CE class in EUDAMED, units sold (ask the UK distributor) | yes |
| 32 | Leukerbad Clinic: musculoskeletal, internal medicine, oncology rehab; isokinetic device; no robots listed | leukerbadclinic.ch, Prestations, Therapies | [A] | confirm in person | Q and A |
| 33 | No single-webcam trunk tracking validated in stroke | research agent's search | [B] absence of evidence | only matters if the webcam stretch feature is built | no |
| 34 | A cost study says the RATULS model doubles costs at 1,820 robot hours a year | Gower et al., Scientific Reports 2025, doi 10.1038/s41598-025-24656-7 | [U] search snippet only | open it; it may be the best evidence for or against our cost argument | maybe |
| 35 | Every price, ratio, timeline and ARR figure of ours | us | [ASSUMPTION] | label "assumption" on the slide | yes |

**Rules for the deck.** No row marked [U] appears on a slide. [B] rows appear only after a human has opened them. Nothing from the simulated history is shown without the word "simulated". No quote from a therapist without their permission. No statement of customer interest unless someone said it and it is written in `business/interviews.md`.

**Interview and survey plan (Mat and Gio).** Script and questions are in KICKOFF package B0.

| Who | Where | Target by Sat evening | Target by Sun 12:00 |
|-----|-------|-----------------------|---------------------|
| Physiotherapists and occupational therapists | Leukerbad Clinic, private practices in the village, thermal baths therapy staff | 3 conversations | 5 |
| A therapy lead or clinic manager | Leukerbad Clinic (name on its site) | request a meeting | 1 conversation |
| Hackathon mentors, technicians or judges with medical or rehab background | venue | 1 | 2 |
| Therapists reachable online (team's own contacts in the UK and Switzerland) | phone or message | send 10 requests | 3 replies |

Numbers to bring back, each with who said it: repetitions per session, patients per therapist per day, minutes spent on notes, devices owned and how many hours a week they are used, what they paid, who decides purchases, reaction to one therapist supervising several stations, the first objection. Zero answers is a valid result; write it down as zero.

## 8. Red team

### The ten hardest questions

1. **YC partner: "NICE says do not offer this. RATULS was negative. Why are you building it?"**
   Because that evidence is our thesis. The robots tied with therapists; they lost on cost: a dedicated machine and a therapist for each patient. We are not claiming better recovery. We are testing whether the same therapy can be delivered on standard hardware with one therapist across several stations. If the pilot cannot show that, we stop.

2. **YC partner: "Bionik sold 13 robots a year. Why is this a venture-scale business?"**
   Dedicated rehab robots sell slowly because each serves one patient type in one room. Our bet is usage: one station for weak and strong patients, neuro and shoulder, so it is busy all day. We have not proven that. Switzerland alone is about CHF 3.4M a year at full penetration on our assumptions; the business needs the US or Germany and a second indication. That is in the plan as a risk, not hidden.

3. **YC partner: "What is your moat if Flexiv or Fourier copies it?"**
   Today, little. Over time: the regulatory file and quality system (years), a cross-arm dataset linking per-repetition data to outcomes, and being the software therapists write their notes in. Supporting several arms is the reason an arm maker is a partner before it is a competitor.

4. **Robotics judge: "Is this just the arm's built-in impedance mode with a moving setpoint?"**
   Yes, on purpose. Closing a force loop in Python over a non-real-time link with a person attached would be the wrong design. The arm's own 1 kHz controller does the physics; we choose the target and stiffness. What we add: the path tunnel, the fall-behind-only assistance law, per-rep adaptation, and a commanded pull that is bounded by construction (stiffness clamp times lead clamp), with measured peak forces in our safety sheet.

5. **Robotics judge: "What happens if your laptop hangs, or she lets go?"**
   Laptop hang: the robot stops and holds on lost connection, and our watchdog trips to a soft hold after 0.2 s without a command. Letting go: when the handle reads empty the engine stops advancing within half a second; the target is never more than 5 cm from the hand and speed is capped at 0.15 m/s on every command. Both are tests in `robot/SAFETY.md` that the technician ran first. Above that sit the technician's limits in the controller and the e-stop.

6. **Robotics judge: "How do you know the patient is contributing and not the robot?"**
   We measure the external force at the handle and the hand's velocity. Work done in the direction of travel is the person's; work against it is the arm dragging the limb. The ratio is our contribution index. It is ours, simple, and not clinically validated; we say so on screen.

7. **Stroke physiotherapist: "End-effector robots let patients cheat with the trunk and shoulder. And reaching in a straight line is not function."**
   Agreed on both. Trunk compensation is real (Cirstea and Levin 2000 [B]) and a handle cannot see it; a camera-based flag is on our list but is not validated with a single webcam, so we do not claim it. Straight reaching is where a weekend allows us to be safe; functional tasks and therapist-defined paths are the roadmap. Tell us which movement you would want first.

8. **Stroke physiotherapist: "Would I trust it alone with a patient while I see two others?"**
   Not on our say-so. That is the study: start one to one, measure interventions needed per session, then two stations, with you deciding. If therapists will not leave it, the cost argument fails and we will have learned that cheaply.

9. **Regulator: "What class is it and what is your intended purpose?"**
   Intended purpose: active and assisted upper-limb exercise under therapist supervision, with measurement. We expect class IIa under MDR Rule 9 and accept that a notified body may argue IIb; the software takes the same class under Rule 11. We would design to IEC 60601-1 and IEC 80601-2-78 under ISO 13485, 62304 and 14971. This weekend it is a research prototype used only by healthy team members.

10. **Regulator: "The arm is not a medical device. Who is the manufacturer, and does your adaptive dial make it a closed-loop system under Rule 22?"**
    We would be the legal manufacturer of the whole system, with the arm as a component, as others have done with a medical-grade arm. Flexiv states it holds IEC 60601 certification for the Rizon; we have not seen the certificate and would need it and a supplier agreement. On Rule 22: the dial adjusts mechanical assistance from movement performance and makes no diagnosis; we would put that argument to a notified body early, and we do not assume the answer.

### Top eight risks

| # | Risk | Mitigation | Trigger and fallback |
|---|------|-----------|----------------------|
| R1 | RDK licence does not allow Cartesian mode, or RDK and robot software versions do not match | K0 checks this first; pin the matching 1.9.x version | **Sat 17:00:** if `SwitchMode(NRT_CARTESIAN_MOTION_FORCE)` fails, ask the organisers for a licence or a firmware-matched robot the same evening. If still blocked Sun 08:00, ask the technician which compliant behaviour the licence does allow (for example a floating primitive or joint impedance mode) and rebuild the demo around it, or request a different torque-controlled arm. Sim-only demo is the last resort and is stated as simulated |
| R2 | Someone is hurt or frightened by the arm | Section 4.2 layers; technician first; healthy team only; low stiffness first; e-stop holder named | Any unexpected motion: stop, no person on the handle until the cause is found and K2 is rerun |
| R3 | Transparent mode feels heavy or assistance feels jerky | K3 measures drag and stiffness-change timing; engine changes stiffness only on events | **Sun 10:00:** if transparent drag is over about 5 N, never show `D = 0` as "free"; demo assist to light assist to resist. If stiffness changes jerk, fix stiffness per rep and adapt by lead only |
| R4 | Integration slips; arm, engine and server meet too late | Sim arm with the same interface; I2 on sim Sat 23:00; I3 on the arm Sun 10:00 | **Sun 12:00:** cut every SHOULD. **Sun 15:00:** if auto adaptation is unreliable on the arm, operator steps the dial by hand |
| R5 | Arm faults during the pitch | `recover.py`, run book, five rehearsals, cold-start practice | Second fault in a run: backup video |
| R6 | A claim on a slide is wrong or cannot be sourced | Section 7 labels; no [U] on slides | Any claim not checked by Sun 21:00 is deleted from the deck |
| R7 | Judges see "another rehab robot that NICE rejected" | Open the pitch with the negative evidence ourselves | If interviews by Sun 12:00 show therapists reject the supervision idea, reposition as a measurement and progression tool for one-to-one sessions and say why |
| R8 | Three people's agents collide on main, or simulated data leaks in as real | One folder per person, one-way imports, `simulated` set by the server from the arm type, pull before push | A broken main: the person who broke it reverts their own commit; nobody edits another folder to fix it |

