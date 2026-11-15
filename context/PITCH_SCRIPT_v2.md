# Pitch script v2: the 2 minutes after the ad (draft by Kian's session, 15 Nov)

**Status: draft for Shyan, Shiv, Mat and Gio to review.** It does not replace `context/PITCH.md`
until the team agrees. Written after watching the 2-minute ad frame by frame.

## Format

4 minutes: the ad first (2:02), then 1:58 of talking. Speakers: Shyan, Kian, Shiv, Mat.

## Why the talk changed

The ad already tells the problem, the solution, how a session works and the vision. It is all
animation, and it shows reach, shoulder circles and knee extension. The real arm runs Push at
4 fixed levels (DECISIONS 20:00 and 21:10). So the talk does not repeat the ad. It answers the
question the ad leaves open: what is real today.

**On screen while talking:** the real arm. Live on stage if it is there and signed off;
otherwise a silent clip of a person doing Push on it, with the phone and the rep counter in shot.

## The script (222 words, about 1:45 spoken, 10 s spare for hand-overs)

**Shyan · the bridge · 20 s**

> Everything you just saw was animation. This is not.
> This is a standard factory robot arm, running software we wrote this weekend.
> You sit down, tap your phone on the station, pick a level, and push.
> The arm pushes back, and it counts.

**Kian · the arm and safety · 28 s**

> I look after the arm. It is a Flexiv Rizon 4, the same arm factories buy.
> For rehab we make it soft: it behaves like a spring you push against, at four levels
> from 10 to 28 newtons.
> And we fenced it in. Too much force, too much speed, or one press of the red button,
> and it stops.

**Shiv · what it measures · 25 s**

> While you push, the software reads the handle a hundred times a second: where it is, and
> how hard you are pushing.
> So it knows every repetition, how far you went and how much force you used.
> A sheet of exercises can't tell your physio any of that. This can, after every session.

**Mat · the business and the ask · 32 s**

> Rehab robots exist. The largest trial, 770 patients, found them no better than usual care,
> and not worth the cost.
> So we are not selling better recovery. Our bet is more practice, measured, for less.
> A standard arm, our software, leased to clinics, gyms and care homes, where one therapist
> can watch several stations.
> What we need next is one pilot site to prove it.
> Vita. More practice. Measured.

## Delivery

- One idea per speaker. Do not add sentences; if you run long, cut one, do not speed up.
- Hand over by stepping back, not by saying "now over to". The next speaker starts at once.
- Shyan points at the real arm on "This is not." Kian touches the red button on "red button".
- If it is live: one person pushes the handle through 3 reps during Shiv's part, so the counter
  on the screen moves while Shiv says "it knows every repetition".
- Mat ends on the ad's own last line, so the pitch closes where the ad closed.

## Only say it if it is true on the day

| Line | Must be true first |
|---|---|
| "This is not [animation]" + the arm on screen | BandEngine has run Push on the real arm with the handle mounted; `robot/SAFETY.md` signed |
| "tap your phone on the station" | The NFC tag works on the phone used (`context/NFC.md`); else say "scan the station" |
| "four levels from 10 to 28 newtons" | `software/simple.py` LEVELS unchanged (10, 15, 20, 28 N) |
| "too much force, too much speed ... it stops" | The 40 N and 0.40 m/s trips and the e-stop are checked on the arm (SAFETY.md) |
| "a hundred times a second" | The demo loop still runs at 100 Hz (`simple.py` DT = 0.01) |
| "770 patients ... not worth the cost" | Mat and Gio have the RATULS source in the claims table |

## Likely questions, short honest answers

- **Was the video real?** No. It is an animation of where the product is going. Running on the
  arm today: Push at four levels, rep counting, starting from the phone, live screens.
- **What about reach, shoulder and knee?** The assisted reach, row and strength test run in our
  simulator. On the real arm they were not reliable enough in 48 hours, so we cut them from the
  demo. They are the next step, not a claim.
- **Is it a medical device?** No. It is a research prototype, not certified. A person holds the
  emergency stop whenever someone is at the arm.
- **Why would this beat existing rehab robots?** It does not claim better recovery. It uses a
  standard arm instead of a single-purpose machine, and it measures every rep. Lower cost is the
  hypothesis a pilot has to prove.
- **Where do the numbers in the ad come from?** 1.7 billion: WHO / Global Burden of Disease 2019.
  32 movements per session: Lang et al., 312 observed therapy sessions. The 72 %, the Klimmendaal
  waiting list and the $75-150 need a source from Mat and Gio before anyone quotes them.
- **Is the progress data real?** Today's session is real. The history behind it is simulated and
  labelled.

## Notes on the ad itself (if it can still be edited)

- 72 %, "1 yr+ at Klimmendaal" and "$75-150" show no source on screen.
- The disclaimer is small and only on the last frame.
- No real robot appears. Five seconds of the real arm before the logo would help.
- It runs 2:02, so the talk has 1:58, not 2:00.
- The ad has a voice-over. Read here from a rough machine transcript (offline recogniser, garbled in
  places) plus the on-screen text; nobody on this side heard it. Its gist, in order: one second to get
  hurt, months to get back; 1.7 billion people, about one in five; recovery comes from repetition, about
  32 arm movements in a typical stroke session, recovery needs hundreds; care can't keep up (capacity,
  waiting lists past a year, cost); Vita, a station on a robot arm placed where people already are; she
  walks into the gym, scans, her plan loads, she sits down; the arm guides each movement and measures
  every rep; "it supports her when she slows down and adds gentle resistance when she is strong";
  shoulder circles, knee extensions; one red button and the arm holds still; progress and a weekly
  report; six practices a week instead of two; today rehabilitation and elderly care, later strength
  training for everyone; every rep at exactly the weight you can handle.
- The talk above repeats none of that except the closing line (on purpose). The voice-over's
  "supports her when she slows down and adds gentle resistance" describes the adaptive arm; on the
  real arm today the resistance is a fixed level the patient picks. That is the gap the "was the
  video real?" answer covers.
