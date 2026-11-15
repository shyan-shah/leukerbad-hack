Vita Rehab pitch deck
=====================

How to open it
--------------
Quick look: double-click vita-pitch-deck.html. It is the whole deck in one file (3D library, scene and
logo are embedded) and works straight from disk.

For building the website, use index.html with the separate files below:
The page uses JavaScript modules, so it does not work by double-clicking index.html.
Serve the folder with any static web server, for example:

    cd vita-pitch-deck
    python3 -m http.server 8000

then open http://localhost:8000 in a browser.
To put it online, upload the whole folder to any static host (Netlify, Vercel, GitHub Pages).

What is in the folder
---------------------
vita-app.html              The patient app as a clickable prototype, one file, opens by double-clicking.
                           On a laptop it shows inside a 3D phone; on a real phone it fills the screen.
index.html                 The whole deck: markup, styles, slide text and the slide controls.
assets/science.js          The 3D scene (patient, robot arm, gym, emergency stop), built with three.js.
assets/vita-logo.png       The Vita logo used on the arm, the trolley and the banner.
vendor/                    three.js r160 and two of its add-ons, loaded through the import map in index.html.

The fonts (Outfit, Instrument Sans) load from Google Fonts, so the page needs an internet connection for those.

How it behaves
--------------
- Screens 900 px and wider: a slide deck, one slide at a time. Arrow keys, Space, mouse wheel or the
  buttons bottom-left change slide. F toggles full screen. The 4:00 timer starts on leaving slide 1.
- Narrower screens: a normal scrolling page.
- Slide order is the list of ids near the bottom of index.html (search for 'intro', 'basis').
- Some older sections (single-exercise slides, limits, feedback form, sources) are still in the file
  but hidden with the "hidden" attribute. They can be deleted or brought back.

Things to know before publishing
--------------------------------
- Numbers on the phone mock-ups and the payback example are illustrations, not measured data.
- The QR codes are drawings, not working codes.
- The arm is modelled to resemble a Flexiv Rizon 4; it is not an official model.
