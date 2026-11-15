# Vita patient app (front-end prototype)

This is the clickable prototype of the Vita patient app. A patient scans a Vita station, does the exercises their specialist set, rests between them, and sees their progress and weekly report.

It is front-end only. Every name, plan and number in it is demo data. There is no backend, no login and no real scanning yet.

## Run it

```
npm install
npm run dev      # local preview
npm run build    # static files in dist/, ready to host anywhere
```

It is a plain Vite project: HTML, CSS and JavaScript, with no framework. The only dependency is `three` (the 3D station).

## Files

| File | What it does |
|---|---|
| `index.html` | The phone frame, header and bottom tabs. On a real phone the frame disappears and the app fills the screen. |
| `src/style.css` | All styles. Colours are tokens at the top (`--brand`, `--mint`, …). |
| `src/data.js` | **Demo data to replace with the backend**: `EX` (exercise library) and `PLANS` (five example treatment plans). |
| `src/app.js` | Screens, navigation, the exercise timer and the 3-minute break. State is the object `S`; screens are the functions in `VIEWS`. |
| `src/vita3d.js` | The 3D station (patient, chair, robot arm) and how each exercise moves, with motion lines. |
| `public/vita-logo.png` | Logo, also used on the 3D robot. |

## Screens

- **Today:** the patient's plan and exercises, and a button to scan the station.
- **Exercise preview:** a 3D animation of the exercise, with "how" and "why".
- **Scan:** the camera is simulated by a button.
- **Exercise:** a rep counter and a coach line. "Finish" ends the exercise early.
- **Break:** advises 3 minutes of rest. The patient taps to choose the next exercise; nothing starts automatically.
- **Progress:** works in the demo.
  - Each finished exercise adds a measurement: a new dot on the chart, the goal bar moves up, and the repetition bars per exercise grow.
  - It also counts sessions, exercises and repetitions.
  - **Reset progress** (tap twice) starts the plan from day one, which is handy for showing it.
  - The history is kept per plan on the phone (`S.hist`, in `localStorage`). With a backend it comes from `exercise_results`.
  - The demo raises the measured value by a fixed step per exercise (`stepOf()`). The real value comes from the robot arm.
- **Report:** a weekly summary, plus the "share with my care team" switch.
- **Account** (bottom right): the patient's name and plan, their care team (specialist; the physiotherapist or rehabilitation centre where they are enrolled, which gets the report; home station; break length), and settings:
  - Share with my care team (the same switch as on Report).
  - Session reminders.
  - **Larger text:** works now, by enlarging the whole screen.
  - **Simple pictures:** drawings instead of 3D, for older phones.

  It also has help and safety text, Sign out (a demo screen) and "Start the demo again".
- **Other plans:** a demo-only screen to switch between the five example plans. Remove it once real patients exist.

## What the backend has to provide

A suggested data model, for example in Supabase (what Lovable uses):

- **patients:** id, name, specialist_id, care_provider_id (the physiotherapist or rehabilitation centre the patient is enrolled at; it receives the weekly report), home_station_id, share_with_care_team (consent, default off), reminders_on, larger_text, simple_pictures. The prototype keeps the consent and the three settings on the phone (`localStorage`, key `vita-app-v1`).
- **auth:** patient login, for example a link sent by the clinic or email plus a code. Sign-in is not built; the Account screen's Sign out button only shows a demo screen.
- **care_providers:** physiotherapy practices and rehabilitation centres. Patients are enrolled there after leaving hospital, and they receive the weekly reports.
- **specialists:** the people who set plans, each linked to a care provider.
- **exercises:** the library, matching `EX` in `data.js`: id, name, kind (Assisted / Guided / Resisted / Test), unit, default reps, how, why, coach tips, and which 3D motion to show (`fig`).
- **plans:** patient_id, name, condition, start date, length in weeks, rest between exercises (seconds; the specialist sets this, default 180).
- **plan_exercises:** plan_id, exercise_id, order, reps, robot settings (help %, resistance, range limits).
- **stations:** id, location (gym, care home, pool), and the code printed on the station that the app scans.
- **sessions:** patient_id, station_id, started_at, finished_at.
- **exercise_results:** session_id, exercise_id, reps done, measured values (reach in cm, angle in °, force in N), pain reported.
- **weekly_reports:** generated from results; sent to the patient's physiotherapist or rehabilitation centre only if the patient has consented.

Where the app needs to call the backend (search `app.js` for these):

- **Start-up:** load the logged-in patient's plan instead of `PLANS` / `PL`.
- **`data-scan`:** use a real QR scan and check the station id.
- **`finish()`:** save an `exercise_results` row. The measured values will come from the station's robot arm, not from the phone.
- **`data-share` / `data-toggle`:** save the patient's consent and settings.
- **`data-signout` / `data-signin`:** real sign-out and sign-in.
- **Session reminders:** need push notifications or SMS from the backend. The switch only stores the choice.
- **The `progress` and `report` views:** read the real numbers. They currently use `hist()` (demo history on the phone), `PL.weeks` and `PL.rows`. In the demo, `record()` in `finish()` writes a result; with a backend that becomes the API call.

## Before real patients use it

- **Health data:** this is health data under the GDPR (a special category). It needs consent, EU hosting, access control and a data processing agreement with every host.
- **Medical device rules:** a system that trains and measures patients is likely a medical device under EU rules. The pilot and certification come first.
- **Demo content:** the exercises, plans and figures are demo content. A rehabilitation specialist has to set and check the real ones.
