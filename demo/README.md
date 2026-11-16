# demo/ (Mat and Gio)

Vita's website, patient app and pitch deck. Built copies are ready to open or deploy; sources are in `src/`.

| Folder | What it is | Live |
|---|---|---|
| `website/` | Marketing website, 11 pages (home with 3D hero, how it works, exercises, safety, for locations, vision, pilot, about, FAQ, contact, privacy) | https://vitarehab.org (Cloudflare Worker `vitarehab-site`, `npx wrangler deploy -c wrangler.website.jsonc`) |
| `app/` | Patient app (plans, exercises, weekly report, NFC tap to start; drives the real arm when served by the station) | https://app.vitarehab.org (Cloudflare Worker `vitarehab-app`, `npx wrangler deploy -c wrangler.app.jsonc`) |
| `pitch-deck/` | Pitch deck (open `vita-pitch-deck.html`) | |
| `app-backend/` | Small SQLite + Python backend the app prototype talks to (accounts, sessions). Separate from `server/`, which drives the robot. `config.json` (API key) and `vita.db` (data) are not committed | |
| `src/` | Sources and build scripts: `site-src/` (website, `python3 site-src/build.py`), `app-src/` (app, see `HANDOFF.md`), `science.src.html` + `assets/science.js` (deck), older 3D station showcase | |

Build scripts assume they run from `src/` and write to `~/Desktop/...`; copy the result back into the matching folder here.

Figures in the deck are Swiss and sourced on the slides. Prices, payback and the example patient's progress are marked as examples to be validated.

Also here: `ios/` (native SwiftUI version of the patient app) and `hand-in-document-docs/` (11-page technical hand-in document as PDF).
