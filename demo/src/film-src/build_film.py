#!/usr/bin/env python3
"""Makes assets/science.film.js: the deck's 3D scene with hooks so the pitch film can drive it frame by frame."""
import pathlib
root = pathlib.Path(__file__).resolve().parent.parent
s = (root / 'assets/science.js').read_text()
def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (s.count(a), a)
    s = s.replace(a, b)
rep("function arrive(dt) { walker.g.visible = arriving;", "function arrive(dt) { walker.g.visible = arriving && !(window.FILM && window.FILM.arrHold);")
rep("function pick() { const dk", "function pick() { if (window.FILM) return; const dk")
rep("requestAnimationFrame(frame); if (document.hidden || !seen) { last = now; return; }",
    "if (!window.FILM) { requestAnimationFrame(frame); if (document.hidden || !seen) { last = now; return; } }")
rep("else if (arrOn && !FREEZE && arrT < ARR_END) arrT += dt;", "else if (arrOn && !FREEZE && arrT < ARR_END && !(window.FILM && window.FILM.arrHold)) arrT += dt;")
rep("trailN = 0; const v = VIEWS[ex]; view.taz", "trailN = 0; const v = window.FILM ? [view.taz, view.tel, view.tdist] : VIEWS[ex]; view.taz")
rep("const v = VIEWS.arrive;", "const v = window.FILM ? [view.taz, view.tel, view.tdist] : VIEWS.arrive;")
rep("if (T > 2.5 && !FREEZE)", "if (T > 2.5 && !FREEZE && !window.FILM)")
rep("voff = lerp(voff, BARE ? 0 :", "voff = lerp(voff, window.FILM ? window.FILM.voff : BARE ? 0 :")
rep("FREEZE ? 1 : 1 - Math.exp(-dt * 3)); if (!narrow)", "FREEZE || snap ? 1 : 1 - Math.exp(-dt * 3)); if (!narrow)")
rep("snap = false; renderer.render(scene, cam);", "snap = false; if (!(window.FILM && window.FILM.skip)) renderer.render(scene, cam);")
rep("requestAnimationFrame((n) => { last = n; frame(n); });", """if (window.FILM) { window.film3d = { view, VIEWS, step(dt) { frame(last + dt * 1000); },
  set(o) { if (o.ex && o.ex !== ex) choose(o.ex); if ('fac' in o) facT = o.fac; if ('stop' in o) { stopOn = o.stop; stopT = 0; } if ('arrive' in o) { arrOn = o.arrive; arrT = 0; } if (o.snap) snap = true; },
  get state() { return { ex, exT, arrT, arriving, halted, facP }; } }; dispatchEvent(new Event('film3d')); }
else requestAnimationFrame((n) => { last = n; frame(n); });""")
(root / 'assets/science.film.js').write_text(s)
print('ok', len(s))
