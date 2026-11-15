# demo/ (Mat and Gio)

Vita's website, patient app and pitch deck. Built copies are ready to open or deploy; sources are in `src/`.

| Folder | What it is | Live |
|---|---|---|
| `website/` | Marketing website, 11 pages (home with 3D hero, how it works, exercises, safety, for locations, vision, pilot, about, FAQ, contact, privacy) | https://vitarehab.netlify.app (Netlify project "vitarehab") |
| `app/` | Patient app prototype (plans, exercises, weekly report, station QR scan) | https://vitastation.netlify.app (Netlify project "vitastation") |
| `pitch-deck/` | Pitch deck (open `vita-pitch-deck.html`) | |
| `app-backend/` | Small SQLite + Python backend the app prototype talks to (accounts, sessions). Separate from `server/`, which drives the robot. `config.json` (API key) and `vita.db` (data) are not committed | |
| `src/` | Sources and build scripts: `site-src/` (website, `python3 site-src/build.py`), `app-src/` (app, see `HANDOFF.md`), `science.src.html` + `assets/science.js` (deck), older 3D station showcase | |

Build scripts assume they run from `src/` and write to `~/Desktop/...`; copy the result back into the matching folder here.

Numbers on the site and in the deck (payback, arm life, Anna's progress, exercise doses, the vision page's load demo) are illustrative estimates until B1/B2 (claims table) has checked them.
