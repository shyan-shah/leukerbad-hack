#!/usr/bin/env python3
"""One-off edit: muscle card, rep counter, letterbox, light leaks, glitch hits, scan beam, end particles, re-timed leg section."""
import pathlib, shutil
root = pathlib.Path(__file__).resolve().parent.parent
p = root / 'film.html'
shutil.copy(p, root / 'site-src-backups/film.v3.html')
s = p.read_text()

def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:80])
    s = s.replace(a, b)

rep("  #ui { position: fixed;", """  #musc { position: absolute; right: 64px; top: 128px; width: 400px; padding: 26px 28px 24px; border-radius: 30px; background: #fff; box-shadow: 0 30px 80px rgba(16,38,31,.16); color: var(--ink); visibility: hidden; z-index: 5; }
  #musc .k { display: flex; align-items: center; gap: 10px; font: 500 15px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase; color: #B45F00; } #musc .k i { width: 10px; height: 10px; border-radius: 50%; background: #FF8A1F; box-shadow: 0 0 0 5px rgba(255,138,31,.22); }
  #tName { display: block; margin-top: 12px; font: 600 26px/1.15 var(--display); letter-spacing: -.02em; }
  #map { display: block; width: 100%; height: auto; aspect-ratio: 116 / 86; margin: 14px 0 4px; border-radius: 18px; background: #F5FAFA; } #map .bone { stroke: #C6D0D4; stroke-width: 15; stroke-linecap: round; } #map .jt { fill: #B9B19A; }
  #musHud { display: flex; flex-direction: column; gap: 11px; margin-top: 12px; } .mrow p { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; } .mrow b { font: 600 19px var(--display); } .mrow span { font-size: 14px; color: var(--soft); text-align: right; }
  .bar { height: 9px; border-radius: 99px; background: rgba(30,40,42,.08); margin-top: 5px; overflow: hidden; } .bar i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, #F1C36A, #FF8A1F); transform-origin: left; transform: scaleX(.03); } .bar.st i { background: linear-gradient(90deg, #9CC3F0, #4084D6); }
  #hud .rp { position: absolute; left: 38px; top: -18px; padding: 9px 16px; border-radius: 999px; background: var(--forest); color: #fff; font: 500 15px/1 var(--mono); letter-spacing: .12em; } #hud .rp b { font-weight: 500; color: var(--mint); }
  .lb { position: absolute; left: 0; width: 100%; height: 92px; background: #000; z-index: 29; transform: scaleY(0); } #lb1 { top: 0; transform-origin: 50% 0; } #lb2 { bottom: 0; transform-origin: 50% 100%; }
  #leak { position: absolute; top: -20%; left: -40%; width: 180%; height: 140%; background: linear-gradient(100deg, rgba(255,255,255,0) 38%, rgba(255,252,240,.65) 48%, rgba(52,211,153,.35) 54%, rgba(255,255,255,0) 64%); mix-blend-mode: screen; transform: translateX(-100%); }
  #scan { position: absolute; left: 0; width: 100%; height: 220px; top: -240px; background: linear-gradient(180deg, rgba(52,211,153,0), rgba(52,211,153,.18) 70%, rgba(52,211,153,.55) 97%, #34D399 100%); z-index: 3; visibility: hidden; }
  .okp { display: inline-flex; align-items: center; gap: 12px; margin-top: 30px; padding: 14px 24px 14px 16px; border-radius: 999px; background: var(--forest); color: #fff; font: 600 24px/1 var(--display); visibility: hidden; } .okp i { width: 30px; height: 30px; border-radius: 50%; background: var(--mint); position: relative; } .okp i:after { content: ''; position: absolute; left: 10px; top: 6px; width: 7px; height: 13px; border: solid #04231B; border-width: 0 3px 3px 0; transform: rotate(42deg); }
  .sp { position: absolute; left: 50%; top: 390px; width: 12px; height: 12px; margin: -6px; border-radius: 50%; background: var(--mint); opacity: 0; box-shadow: 0 0 16px rgba(52,211,153,.9); }
  #ui { position: fixed;""")
rep('<b id="tName"></b><svg id="map"></svg><p id="jts"></p><div id="musHud"></div>', '<p id="jts"></p>')
rep('<div id="hud"><div class="nm" id="mName">', '<div id="scan"></div>\n    <div id="musc"><div class="k"><i></i>Muscles at work</div><b id="tName"></b><svg id="map" viewBox="-27 -134 116 86"></svg><div id="musHud"></div></div>\n    <div id="hud"><span class="rp">REP <b id="repN">1</b></span><div class="nm" id="mName">')
rep('<h2 class="t">Scan. Your plan loads.</h2><p class="t">Set together with your therapist.</p>', '<h2 class="t">Scan. Your plan loads.</h2><p class="t">Set together with your therapist.</p><div class="okp"><i></i>Plan loaded · Anna</div>')
rep('<div id="flash"></div>', '<div id="flash"></div><div id="leak"></div>')
rep('<div id="chrome">', '<div class="lb" id="lb1"></div><div class="lb" id="lb2"></div>\n  <div id="chrome">')
rep('<img src="assets/vita-logo.png" alt="vita">', '<img src="assets/vita-logo.png" alt="vita">' + ''.join('<i class="sp"></i>' for _ in range(36)))
rep("  const slam = (sel, a) => {", """  const leak = (a, d = .75) => tl.fromTo('#leak', { xPercent: -100 }, { xPercent: 100, duration: d, ease: 'power2.inOut' }, a - d / 2);
  const glitch = (sel, a, k = 16) => tl.fromTo(sel, { textShadow: k + 'px 0 rgba(255,70,90,.85), ' + (-k) + 'px 0 rgba(40,220,255,.85)' }, { textShadow: '0px 0 rgba(255,70,90,0), 0px 0 rgba(40,220,255,0)', duration: .65, ease: 'power2.out' }, a);
  const kb = (sel, a, b) => tl.fromTo(sel, { scale: 1 }, { scale: 1.045, duration: b - a, ease: 'none' }, a);
  const slam = (sel, a) => { glitch(sel, a + .05);""")
rep("flash(1.42, .55, '#FF6B5E'); shake('#s0', 1.42, 30);", "flash(1.42, .55, '#FF6B5E'); shake('#s0', 1.42, 30); glitch('#h0a', 1.42, 22); kb('#s0', 0, 8.2);")
rep("show('#s1', 8.2, 18.2);", "show('#s1', 8.2, 18.2); kb('#s1', 8.2, 18.2);")
rep("show('#s2', 18.2, 29.7);", "show('#s2', 18.2, 29.7); kb('#s2', 18.2, 29.7);")
rep("show('#s3', 29.7, 38.6);", "show('#s3', 29.7, 38.6); kb('#s3', 29.7, 38.6); glitch('#s3 .card b', 31.15, 12);")
rep("show('#s7', 107.6, 117.2);", "show('#s7', 107.6, 117.2); kb('#s7', 107.6, 117.2);")
rep("tl.to('#chrome', { color: '#10261F', duration: .5 }, 38.9);", "tl.fromTo('.lb', { scaleY: 0 }, { scaleY: 1, duration: 1.1, ease: 'power3.inOut' }, 38.4); tl.to('.lb', { scaleY: 0, duration: .8, ease: 'power3.inOut' }, 85.1);")
rep("tl.to('#chrome', { color: '#fff', duration: .5 }, 85.4);", "")
rep("cap('#c-arr1', 45, 48.4); cap('#c-arr2', 48.6, 52.2);", "cap('#c-arr1', 45, 48.4); cap('#c-arr2', 48.6, 52.2); tl.set('#scan', { visibility: 'visible' }, 47.9); tl.fromTo('#scan', { top: -240 }, { top: 1100, duration: 1.5, ease: 'power1.inOut' }, 47.9); tl.set('#scan', { visibility: 'hidden' }, 49.5);\n  tl.set('#c-arr2 .okp', { visibility: 'visible' }, 49.6); tl.from('#c-arr2 .okp', { scale: .4, opacity: 0, duration: .6, ease: 'back.out(2.2)', transformOrigin: '0 50%' }, 49.6); tl.to('#c-arr2 .okp', { opacity: 0, duration: .4 }, 51.8);")
rep("cap('#c-ex1', 56.2, 63.6); cue(64, () => f3.set({ ex: 'circle' })); cap('#c-ex2', 64.2, 70.6);\n  cue(71, () => f3.set({ ex: 'leg' })); cap('#c-ex3', 71.2, 77.4);",
    "cap('#c-ex1', 56.2, 63.6); cue(64, () => f3.set({ ex: 'circle' })); cap('#c-ex2', 64.2, 72);\n  cue(72.2, () => f3.set({ ex: 'leg' })); cap('#c-ex3', 72.4, 78.2);\n  show('#musc', 56.7, 78.3, .6, .4); tl.from('#musc', { x: 120, duration: 1, ease: 'expo.out' }, 56.7); tl.from('#musc .mrow', { opacity: 0, x: 30, duration: .5, stagger: .1 }, 57.2);\n  [64.4, 72.4].forEach((c) => { tl.fromTo('#musc', { scale: .96 }, { scale: 1, duration: .6, ease: 'back.out(3)' }, c); tl.from('#musc .mrow', { opacity: 0, x: 30, duration: .45, stagger: .08 }, c + .1); });")
rep("[56.4, 60.2, 64.2, 67.6, 71.2, 74.6, 78.4].forEach((c) => flash(c, .5));", "[56.4, 60.2, 64.2, 67.6, 72.2, 75.2, 78.4].forEach((c) => { flash(c, .25); leak(c); });")
rep("    [67.6, .28, .36, 3.2, -.2, 1], [71.2, .48, .3, 2.9, -.2],            // circles, close\n    [71.2, .36, .13, 4.3, -.17, 1], [74.6, .46, .14, 4, -.17],           // leg, mid\n    [74.6, 1.22, .1, 3.3, -.2, 1], [78.4, 1.02, .13, 3, -.2],            // leg, close",
    "    [67.6, .28, .36, 3.2, -.2, 1], [72.2, .48, .3, 2.9, -.2],            // circles, close\n    [72.2, .36, .13, 4.3, -.17, 1], [75.2, .46, .14, 4, -.17],           // leg, mid\n    [75.2, 1.22, .1, 3.3, -.2, 1], [78.4, 1.02, .13, 3, -.2],            // leg, close")
rep("  const wipe = (a) => {", "  const wipe = (a) => { leak(a + .35, .9);")
rep("txt('#s8 h2', 118.2, null);", "txt('#s8 h2', 118.2, null); leak(118.1, 1.1);\n  $$('#s8 .sp').forEach((e, i) => { const an = i / 36 * Math.PI * 2 + (i % 3) * .2, R = 260 + (i * 97 % 7) * 70; tl.fromTo(e, { x: 0, y: 0, opacity: 1, scale: 1.4 }, { x: Math.cos(an) * R * 1.6, y: Math.sin(an) * R, opacity: 0, scale: .3, duration: 1.6 + (i % 4) * .2, ease: 'expo.out' }, 117.6); });")
rep("function gauge() {", "const PER = { reach: 5.4, circle: 4.6, leg: 6 }, repN = $('#repN');\n  function gauge() { const st = f3.state; repN.textContent = Math.floor(st.exT / (PER[st.ex] || 5)) + 1;")
p.write_text(s)

b = root / 'film-src/build_film.py'
t = b.read_text()
a = "get state() { return { ex, exT, arrT, arriving, halted, facP }; }"
if a in t:
    b.write_text(t.replace(a, "get state() { return { ex, exT, arrT, arriving, halted, facP, h: [H.x, H.y, H.z] }; }"))
print('edited')
