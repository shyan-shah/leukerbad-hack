// The Vitalis world: one 3D scene behind the page. Each <section class="ch"> is a chapter; its data attributes say
// where Vita stands (data-x, data-y, data-s, data-ry), the colour of the world (data-bg, data-dark), her mood (data-mood)
// and what happens around her (data-fx, several allowed): ambient, chat, water, calendar, home, night, alarm, family, shield.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
const pop = (k) => k * (1 + Math.sin(Math.PI * k) * .18);            // grows in with a little overshoot
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const COL = { forest: '#2E6B4F', leaf: '#5F9E77', mint: '#A9D3B2', coral: '#D9483F', sun: '#F1C36A', cream: '#FFF8EC', ink: '#1E2A26', sky: '#4FB6E8', wood: '#D6AE82' };

// ---------- chapters ----------
const secs = $$('.ch');
const K = secs.map((s) => {
  const d = s.dataset, side = s.classList.contains('r') ? -1 : 1;
  return { x: d.x !== undefined ? +d.x : side * 2.8, y: d.y !== undefined ? +d.y : 0, z: d.z ? +d.z : 0, room: d.room !== undefined ? +d.room : -1, roof: d.roof !== undefined ? 1 : 0, shot: d.shot || '', zoom: d.zoom ? +d.zoom : 0, ty: d.ty !== undefined ? +d.ty : null,
    time: d.time ? +d.time.split(':')[0] * 60 + +d.time.split(':')[1] : null, s: d.s ? +d.s : 1.05, ry: d.ry ? +d.ry : -side * .35,
    story: s.classList.contains('story'), copy: s.querySelector('.copy'), bg: d.bg || '#FBF6EE', mood: d.mood || 'calm', fx: (d.fx || '').split(' ').filter(Boolean), dark: d.dark !== undefined };
});
const dots = null;
if (dots && secs.length > 1) dots.innerHTML = secs.map((s, i) => `<a href="#${s.id}" aria-label="${s.dataset.name || i + 1}"><span>${s.dataset.name || i + 1}</span></a>`).join('');
const dotEls = dots ? $$('a', dots) : [];

let centers = [], tops = [], bots = [];
const measure = () => { tops = secs.map((s) => s.offsetTop); bots = secs.map((s) => s.offsetTop + s.offsetHeight); centers = secs.map((s, i) => (tops[i] + bots[i]) / 2); };
measure(); addEventListener('resize', measure); addEventListener('load', measure); if (document.fonts) document.fonts.ready.then(measure);
const qs = new URLSearchParams(location.search), start = qs.get('ch'), startL = +(qs.get('l') || 0);   // ?ch=3 holds one chapter still (for screenshots); &l=.3 looks 0.3 screens past its middle
function still() {
  const at = centers[+start] + startL * innerHeight - innerHeight / 2, sec = secs[+start], copy = $('.copy', sec);
  $('main').style.transform = `translateY(${-at}px)`; sec.classList.add('on'); document.documentElement.classList.add('still'); document.documentElement.style.overflow = 'hidden';
  if (sec.classList.contains('story')) { copy.style.position = 'relative'; copy.style.top = clamp(at - sec.offsetTop, 0, sec.offsetHeight - innerHeight) + 'px'; }
}
if (start) { still(); addEventListener('load', () => { measure(); still(); }); addEventListener('resize', () => { measure(); still(); }); if (document.fonts) document.fonts.ready.then(() => { measure(); still(); }); }
else { const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) e.target.classList.add('on'); }), { threshold: .12 }); secs.forEach((s) => io.observe(s)); }

// ---------- small helpers for drawing ----------
const redraw = [];      // textures with words on them are drawn again once the web font is there
function tex(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d');
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  const run = () => { g.clearRect(0, 0, w, h); draw(g, w, h); t.needsUpdate = true; }; run(); redraw.push(run); return t;
}
if (document.fonts) document.fonts.ready.then(() => redraw.forEach((f) => f()));
const FONT = (px, wt = 600) => `${wt} ${px}px Outfit, 'Instrument Sans', system-ui, sans-serif`;
const rbox = (g, x, y, w, h, r, fill) => { g.beginPath(); g.roundRect(x, y, w, h, r); g.fillStyle = fill; g.fill(); };
const disc = (g, x, y, r, fill) => { g.beginPath(); g.arc(x, y, r, 0, 6.3); g.fillStyle = fill; g.fill(); };
function heart(g, cx, cy, s, fill) {
  g.beginPath(); g.moveTo(cx, cy + s * .9); g.bezierCurveTo(cx - s * 1.5, cy - s * .1, cx - s * .75, cy - s * 1.15, cx, cy - s * .4);
  g.bezierCurveTo(cx + s * .75, cy - s * 1.15, cx + s * 1.5, cy - s * .1, cx, cy + s * .9); g.fillStyle = fill; g.fill();
}
function tick(g, cx, cy, s, col = '#fff') { g.strokeStyle = col; g.lineWidth = s * .28; g.lineCap = 'round'; g.lineJoin = 'round'; g.beginPath(); g.moveTo(cx - s * .5, cy + s * .02); g.lineTo(cx - s * .12, cy + s * .4); g.lineTo(cx + s * .55, cy - s * .38); g.stroke(); }
function leafGeometry() {      // a plump leaf, smooth all round: pointed at the tip, curling back, with a soft fold along its middle
  const g = new THREE.SphereGeometry(1, 40, 40), a = g.attributes.position;
  for (let i = 0; i < a.count; i++) { const x = a.getX(i), y = a.getY(i), z = a.getZ(i), t = (y + 1) / 2, xs = x * .3 * (1 - smooth(.45, 1, t) * .55) * (1 + (1 - t) * .12);
    a.setXYZ(i, xs + .13 * Math.sin(Math.PI * t) + .14 * t, t, z * .05 * (1 - t * .5) - .3 * t * t + Math.abs(xs) * .55 * Math.sin(Math.PI * clamp(t * 1.1))); }
  g.computeVertexNormals(); return g;
}
const LEAF = leafGeometry();
const HALO = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'), gr = x.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(.4, 'rgba(255,255,255,.35)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = gr; x.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();
const EYE = new THREE.MeshStandardMaterial({ color: COL.cream, roughness: .3 });
const INK = new THREE.MeshStandardMaterial({ color: COL.ink, roughness: .35 });
const phys = (color, o = {}) => new THREE.MeshPhysicalMaterial({ color, roughness: .38, clearcoat: .8, clearcoatRoughness: .28, ...o });

// ---------- Vita ----------
// A soft speaker with a face: a knitted green body, a glazed cream top with a ring of light, and the two leaves and the red light of the Vitalis logo.
const GLOW = new THREE.MeshBasicMaterial({ color: '#FFF6E2' });
const knit = (lo, hi) => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'); x.fillStyle = lo; x.fillRect(0, 0, 64, 64);
  for (let j = 0; j < 8; j++) for (let i = -1; i < 8; i++) { const ox = i * 8 + (j % 2 ? 4 : 0) + 4, oy = j * 8 + 4, gr = x.createRadialGradient(ox, oy, 0, ox, oy, 4.4); gr.addColorStop(0, hi); gr.addColorStop(1, lo); x.fillStyle = gr; x.beginPath(); x.arc(ox, oy, 4.4, 0, 6.3); x.fill(); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(30, 9); t.anisotropy = 8; return t; };
const KNIT_COL = knit('#D2D2D2', '#FFFFFF'), KNIT_BUMP = knit('#202020', '#FFFFFF'); KNIT_COL.colorSpace = THREE.SRGBColorSpace;
const PROFILE = new THREE.SplineCurve([[0, -1.1], [.55, -1.1], [.84, -1.045], [.98, -.89], [1.04, -.6], [1.05, -.25], [1.0, .1], [.9, .38], [.72, .6], [.45, .72], [.2, .755], [0, .76]].map(([a, b]) => new THREE.Vector2(a, b))).getPoints(96);
const rAt = (y) => { let best = PROFILE[0]; for (const q of PROFILE) if (Math.abs(q.y - y) < Math.abs(best.y - y)) best = q; return best.x; };
const I0 = PROFILE.findIndex((q) => q.y > -.99), I1 = PROFILE.findIndex((q) => q.y > .2);
const VG = { foot: new THREE.LatheGeometry(PROFILE.slice(0, I0 + 1), 96), body: new THREE.LatheGeometry(PROFILE.slice(I0, I1 + 1), 96), cap: new THREE.LatheGeometry(PROFILE.slice(I1), 96) };
function makeVita() {
  const g = new THREE.Group();
  const mat = new THREE.MeshPhysicalMaterial({ color: COL.forest, map: KNIT_COL, bumpMap: KNIT_BUMP, bumpScale: 2.2, roughness: .88, sheen: 1, sheenColor: new THREE.Color('#A8E0BC'), sheenRoughness: .4 });
  const cream = phys(COL.cream, { roughness: .2, clearcoat: 1, clearcoatRoughness: .12 });
  const body = new THREE.Mesh(VG.body, mat), cap = new THREE.Mesh(VG.cap, cream), foot = new THREE.Mesh(VG.foot, cream);
  // the ring of light where the knit meets the top: it glows when she talks and turns red when something is wrong
  const ry = PROFILE[I1].y, rr = PROFILE[I1].x;
  const ringMat = new THREE.MeshBasicMaterial({ color: COL.sun }), ring = new THREE.Mesh(new THREE.TorusGeometry(rr + .004, .034, 14, 96), ringMat); ring.rotation.x = Math.PI / 2; ring.position.y = ry;
  const ringHalo = new THREE.Mesh(new THREE.TorusGeometry(rr + .006, .062, 14, 96), new THREE.MeshBasicMaterial({ color: COL.sun, transparent: true, opacity: .2, depthWrite: false })); ringHalo.rotation.x = Math.PI / 2; ringHalo.position.y = ry;
  const waves = Array.from({ length: 3 }, () => { const m = new THREE.Mesh(new THREE.TorusGeometry(rr + .1, .014, 8, 96), new THREE.MeshBasicMaterial({ color: COL.forest, transparent: true, opacity: 0, depthWrite: false })); m.rotation.x = Math.PI / 2; m.position.y = ry; g.add(m); return m; });
  const pad = new THREE.Mesh(new THREE.CylinderGeometry(.2, .22, .03, 40), phys('#EADFCB', { roughness: .35 })); pad.position.y = .765;
  // her face shines softly through the knit
  const face = new THREE.Group();
  const eyes = [-1, 1].map((sd) => {
    const e = new THREE.Group(), a = sd * .32, r = rAt(-.22) + .006; e.position.set(Math.sin(a) * r, -.22, Math.cos(a) * r); e.rotation.y = a;
    const calm = new THREE.Mesh(new THREE.CapsuleGeometry(.092, .17, 6, 18), GLOW);
    const happy = new THREE.Mesh(new THREE.TorusGeometry(.14, .052, 12, 28, Math.PI), GLOW); happy.position.y = -.05;
    const line = new THREE.Mesh(new THREE.CapsuleGeometry(.06, .2, 6, 16), GLOW); line.rotation.z = Math.PI / 2;
    e.add(calm, happy, line); face.add(e);
    const b = new THREE.Mesh(new THREE.CircleGeometry(.105, 24), new THREE.MeshBasicMaterial({ color: '#F58A76', transparent: true, opacity: .9 })), ba = sd * .63, br = rAt(-.5) + .004;
    b.position.set(Math.sin(ba) * br, -.5, Math.cos(ba) * br); b.rotation.y = ba; face.add(b);
    return { e, calm, happy, line };
  });
  const mr = rAt(-.5) + .008;
  const smile = new THREE.Mesh(new THREE.TorusGeometry(.13, .036, 10, 24, Math.PI), GLOW); smile.rotation.z = Math.PI; smile.position.set(0, -.47, mr);
  const mouth = new THREE.Mesh(new THREE.CircleGeometry(.1, 28), GLOW); mouth.position.set(0, -.52, mr); mouth.visible = false; face.add(smile, mouth);
  const leafL = new THREE.Mesh(LEAF, phys(COL.forest, { side: THREE.DoubleSide })), leafR = new THREE.Mesh(LEAF, phys(COL.leaf, { side: THREE.DoubleSide }));
  leafL.scale.set(-.86, .86, .86); leafR.scale.set(.86, .86, .86); leafL.position.set(-.03, .76, 0); leafR.position.set(.03, .76, 0); leafL.rotation.z = .5; leafR.rotation.z = -.5;
  const orbMat = new THREE.MeshPhysicalMaterial({ color: COL.coral, emissive: COL.coral, emissiveIntensity: .35, roughness: .2, clearcoat: 1 });
  const orb = new THREE.Mesh(new THREE.SphereGeometry(.18, 36, 36), orbMat); orb.position.y = 1.72;
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: HALO, color: '#FF7A66', transparent: true, opacity: .3, depthWrite: false })); halo.position.y = 1.72; halo.scale.setScalar(.9);
  g.add(body, cap, foot, ring, ringHalo, pad, face, leafL, leafR, halo, orb);
  orb.visible = halo.visible = false;      // no ball above the speaker
  g.userData = { mat, face, eyes, smile, mouth, leafL, leafR, orb, orbMat, halo, ringMat, ringHalo, waves, ringTo: new THREE.Color(COL.sun), mood: '', blink: Math.random() * 4, hop: 0, hopH: 1, talk: 0 };
  setMood(g, 'calm');
  return g;
}
function setMood(v, m) {
  const u = v.userData; if (u.mood === m) return; u.mood = m;
  u.eyes.forEach((o) => { o.calm.visible = m === 'calm' || m === 'think'; o.happy.visible = m === 'happy'; o.line.visible = m === 'sleep'; });
}

// ---------- what happens around her, one function per data-fx ----------
// Each gets the shared tools and returns run(w, p, c): w = how present it is (0..1), p = how far its chapter's story is (0..1),
// c = where Vita stands in that chapter (x, y, s), which side the text is on (inner: -1 text left of her, 1 right), the floor under her (floor),
// a scale for small screens (k), the time (T, dt) and the pointer (px, py).
// moving in: how far the speakers have been placed (read by the house)
const SETUP = { w: 0, q: 0 }, stepEls = $$('[data-step]');
const SCENES = {
  setup() { return (w, p, c) => { SETUP.w = w; SETUP.q = c.long; if (w > .01) stepEls.forEach((el, i) => el.classList.toggle('on', c.long >= [0, .5, .78][i])); }; },

  // leaves falling slowly past her, as in a light breeze: far ones small and slow, near ones bigger, each swaying as it comes down
  ambient({ scene }) {
    const g = new THREE.Group(); scene.add(g);
    const cols = [COL.mint, COL.cream, COL.leaf, COL.sun, COL.mint, COL.leaf], N = 16, rnd = (i, k) => { const v = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return v - Math.floor(v); };
    const L = Array.from({ length: N }, (_, i) => { const near = i >= N - 2, m = new THREE.Mesh(LEAF, phys(cols[i % cols.length], { roughness: .5, clearcoat: .5, side: THREE.DoubleSide, emissive: cols[i % cols.length], emissiveIntensity: .45 })); g.add(m);
      return { m, near, col: (i + .5) / (N - 2) - .5 + (rnd(i, 1) - .5) * .05, z: near ? 1.6 : -1.2 - rnd(i, 2) * 3.4, ph: rnd(i, 3), sp: .035 + rnd(i, 4) * .03, amp: .35 + rnd(i, 5) * .5, fq: .5 + rnd(i, 6) * .5, size: near ? .85 : .42 + rnd(i, 7) * .36 }; });
    return (w, p, c) => { g.visible = w > .01; if (!g.visible) return;
      L.forEach((o, i) => { const hh = 3.6 + (11 - o.z) * .05 + Math.max(0, -o.z) * .3, hw = hh * (innerWidth / innerHeight), u = (c.T * o.sp * (o.near ? 1.5 : 1) + o.ph) % 1, sw = c.T * o.fq + o.ph * 6.283;
        const x = o.near ? c.x + (i % 2 ? 2.7 : -2.1) + Math.sin(sw) * o.amp * .6 : (c.tall ? o.col * 2 : .42 + o.col * 1.25) * hw + Math.sin(sw) * o.amp + u * .8;
        o.m.position.set(x - c.px * (o.near ? .5 : .15), hh - u * 2 * hh + Math.cos(sw * 2) * .08, o.z);
        o.m.rotation.set(.5 + Math.sin(sw * .5) * .5, c.T * .15 + o.ph * 6.283, Math.sin(sw) * .75 - .3);      // it tips the way it swings
        const edge = smooth(0, .1, u) * smooth(1, .9, u); o.m.visible = !(o.near && c.tall); o.m.scale.setScalar(Math.max(.0001, w * edge * o.size)); }); };
  },

  // speech bubbles pop up around her, one after the other: what the two of them talk about
  chat({ scene }) {
    const g = new THREE.Group(); scene.add(g);
    const rr = new THREE.Shape(), w2 = .6, h2 = .45, r = .3; rr.moveTo(-w2 + r, -h2); rr.lineTo(w2 - r, -h2); rr.absarc(w2 - r, -h2 + r, r, -Math.PI / 2, 0); rr.lineTo(w2, h2 - r); rr.absarc(w2 - r, h2 - r, r, 0, Math.PI / 2); rr.lineTo(-w2 + r, h2); rr.absarc(-w2 + r, h2 - r, r, Math.PI / 2, Math.PI); rr.lineTo(-w2, -h2 + r); rr.absarc(-w2 + r, -h2 + r, r, Math.PI, Math.PI * 1.5);
    const puff = new THREE.ExtrudeGeometry(rr, { depth: .1, bevelEnabled: true, bevelThickness: .07, bevelSize: .07, bevelSegments: 8, curveSegments: 20 }); puff.translate(0, 0, -.05);
    const hs = new THREE.Shape(); hs.moveTo(0, -.3); hs.bezierCurveTo(-.6, .08, -.3, .5, 0, .2); hs.bezierCurveTo(.3, .5, .6, .08, 0, -.3);
    const heartG = new THREE.ExtrudeGeometry(hs, { depth: .06, bevelEnabled: true, bevelThickness: .06, bevelSize: .05, bevelSegments: 6, curveSegments: 28 });
    const white = phys('#FFFFFF', { roughness: .22, clearcoat: 1 });
    const kinds = ['heart',
      (x) => { x.fillStyle = COL.forest; x.fillRect(142, 52, 12, 86); disc(x, 124, 136, 26, COL.forest); x.beginPath(); x.moveTo(142, 52); x.quadraticCurveTo(190, 58, 186, 96); x.lineWidth = 12; x.strokeStyle = COL.forest; x.lineCap = 'round'; x.stroke(); },
      (x) => { for (let i = 0; i < 6; i++) disc(x, 128 + Math.cos(i * 1.047) * 34, 96 + Math.sin(i * 1.047) * 34, 22, '#FF9E8F'); disc(x, 128, 96, 20, COL.sun); },
      'dots',
      (x) => { disc(x, 128, 96, 34, COL.sun); x.strokeStyle = COL.sun; x.lineWidth = 9; x.lineCap = 'round'; for (let i = 0; i < 8; i++) { const a = i * .785; x.beginPath(); x.moveTo(128 + Math.cos(a) * 46, 96 + Math.sin(a) * 46); x.lineTo(128 + Math.cos(a) * 60, 96 + Math.sin(a) * 60); x.stroke(); } },
      (x) => { rbox(x, 84, 62, 78, 72, 14, '#4FB6E8'); x.strokeStyle = '#4FB6E8'; x.lineWidth = 11; x.beginPath(); x.arc(166, 96, 20, -1.2, 1.2); x.stroke(); rbox(x, 84, 62, 78, 16, 8, '#8FD3F2'); },
    ];
    const SPOT = [[-1.95, 1.3, .4], [1.95, 1.0, .2], [-2.4, -.3, .7], [2.35, -.5, .5], [-1.0, 2.5, -.3], [1.15, 2.45, -.5]];
    const B = kinds.map((kd, i) => { const o = new THREE.Group(), flip = i % 2 ? 1 : -1; o.add(new THREE.Mesh(puff, white));
      const tail = new THREE.Mesh(new THREE.ConeGeometry(.14, .34, 20), white); tail.position.set(flip * .3, -.55, 0); tail.rotation.z = Math.PI + flip * .5; o.add(tail);
      const u = {};
      if (kd === 'heart') { u.heart = new THREE.Mesh(heartG, phys(COL.coral, { roughness: .2, clearcoat: 1 })); u.heart.position.set(0, -.04, .12); o.add(u.heart); }
      else if (kd === 'dots') u.dots = [-.26, 0, .26].map((dx, j) => { const d = new THREE.Mesh(new THREE.SphereGeometry(.085, 20, 20), phys(j === 1 ? COL.forest : COL.leaf)); d.position.set(dx, 0, .17); o.add(d); return d; });
      else { const ic = new THREE.Mesh(new THREE.PlaneGeometry(1.1, .825), new THREE.MeshBasicMaterial({ map: tex(256, 192, kd), transparent: true, depthWrite: false, toneMapped: false })); ic.position.z = .125; o.add(ic); }
      o.userData = u; g.add(o); return o; });
    return (w, p, c) => { g.visible = w > .01; if (!g.visible) return;
      B.forEach((o, i) => { const k = smooth(0, 1, clamp(p * 7 - i + 2)) * clamp(w * 1.6), [dx, dy, dz] = SPOT[i], sc = Math.max(.0001, pop(k)) * c.k * (.78 + (i % 3) * .12), u = o.userData;
        o.position.set(c.x + dx * c.k * c.s, c.y + dy * c.k * c.s + Math.sin(c.T * 1.3 + i * 1.7) * .1, dz);
        o.rotation.set(c.py * .12 + Math.sin(c.T * .8 + i) * .06, -dx * .12 + c.px * .3 + Math.sin(c.T * .7 + i) * .16, Math.sin(c.T * .9 + i * 2) * .06 + (1 - k) * .6); o.scale.setScalar(sc);
        if (u.heart) u.heart.scale.setScalar(.82 * (1 + Math.max(0, Math.sin(c.T * 5)) ** 2 * .14));
        if (u.dots) u.dots.forEach((d, j) => { d.position.y = Math.max(0, Math.sin(c.T * 5 - j * .7)) * .13 - .03; }); }); };
  },

  // a glass that fills up while the clock moves on to half past ten, and the pills of the day
  water({ scene, shade, check }) {
    const g = new THREE.Group(); scene.add(g);
    const glass = new THREE.Group(); g.add(glass);
    glass.add(new THREE.Mesh(new THREE.CylinderGeometry(.52, .44, 1.5, 56, 1, true), new THREE.MeshPhysicalMaterial({ color: '#FFFFFF', transparent: true, opacity: .32, roughness: .05, clearcoat: 1, side: THREE.DoubleSide, depthWrite: false })));
    const rim = new THREE.Mesh(new THREE.TorusGeometry(.52, .022, 10, 56), new THREE.MeshBasicMaterial({ color: '#fff', transparent: true, opacity: .9 })); rim.rotation.x = Math.PI / 2; rim.position.y = .75; glass.add(rim);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(.44, .44, .08, 48), new THREE.MeshPhysicalMaterial({ color: '#fff', transparent: true, opacity: .6, roughness: .1 })); base.position.y = -.74; glass.add(base);
    const wg = new THREE.CylinderGeometry(.47, .41, 1, 48); wg.translate(0, .5, 0);
    const water = new THREE.Mesh(wg, new THREE.MeshPhysicalMaterial({ color: COL.sky, transparent: true, opacity: .82, roughness: .1, clearcoat: 1 })); water.position.y = -.7; glass.add(water);
    const top = new THREE.Mesh(new THREE.CircleGeometry(.47, 48), new THREE.MeshBasicMaterial({ color: '#9BD8F5' })); top.rotation.x = -Math.PI / 2; glass.add(top);
    const ripple = new THREE.Mesh(new THREE.RingGeometry(.4, .46, 48), new THREE.MeshBasicMaterial({ color: '#FFFFFF', transparent: true, opacity: 0, depthWrite: false })); ripple.rotation.x = -Math.PI / 2; glass.add(ripple);
    const sh = shade(2.2); glass.add(sh); sh.position.y = -.79;
    const drops = Array.from({ length: 4 }, () => { const m = new THREE.Mesh(new THREE.SphereGeometry(.07, 16, 16), new THREE.MeshPhysicalMaterial({ color: COL.sky, roughness: .1, clearcoat: 1 })); glass.add(m); return m; });
    const done = new THREE.Sprite(new THREE.SpriteMaterial({ map: check, transparent: true, depthWrite: false })); g.add(done);
    // the clock
    const clock = new THREE.Group(); g.add(clock);
    const faceT = tex(256, 256, (x) => { disc(x, 128, 128, 126, COL.coral); disc(x, 128, 128, 108, '#fff'); for (let i = 0; i < 12; i++) { const a = i * .5236; disc(x, 128 + Math.sin(a) * 88, 128 - Math.cos(a) * 88, i % 3 ? 4 : 8, COL.ink); } });
    clock.add(new THREE.Mesh(new THREE.CylinderGeometry(.7, .7, .12, 64).rotateX(Math.PI / 2), phys(COL.coral)));
    const cf = new THREE.Mesh(new THREE.CircleGeometry(.7, 64), new THREE.MeshBasicMaterial({ map: faceT, toneMapped: false })); cf.position.z = .065; clock.add(cf);
    const hand = (len, wd) => { const p = new THREE.Group(), m = new THREE.Mesh(new THREE.CapsuleGeometry(wd, len, 4, 10), INK); m.position.y = len / 2; p.add(m); p.position.z = .09; clock.add(p); return p; };
    const hh = hand(.28, .035), mh = hand(.42, .025); clock.add(new THREE.Mesh(new THREE.SphereGeometry(.05, 16, 16), INK).translateZ(.1));
    // the pills
    const pills = [[COL.coral, COL.cream], [COL.sun, COL.cream], [COL.leaf, COL.cream]].map(([a, b]) => { const p = new THREE.Group();
      const h1 = new THREE.Mesh(new THREE.CapsuleGeometry(.1, .2, 6, 16), phys(a)), h2 = new THREE.Mesh(new THREE.CylinderGeometry(.102, .102, .2, 20), phys(b)); h2.position.y = -.1;
      const cap = new THREE.Mesh(new THREE.SphereGeometry(.102, 20, 12, 0, 6.283, Math.PI / 2, Math.PI / 2), phys(b)); cap.position.y = -.2; h1.position.y = .0; p.add(h1, h2, cap); g.add(p); return p; });
    return (w, p, c) => { g.visible = w > .01; if (!g.visible) return;
      const k = c.k * Math.max(.0001, pop(clamp(w * 1.4))), fill = lerp(.1, 1.32, smooth(.05, .8, p));
      sh.visible = !c.room; glass.position.set(c.x + c.inner * 2.05 * c.k, c.floor + .8 * k, .5); glass.scale.setScalar(k); glass.rotation.y = c.T * .3;
      water.scale.y = fill; top.position.y = -.7 + fill + .002; top.scale.setScalar(lerp(.41, .47, fill / 1.32) / .47);
      const rq = (c.T * 1.1) % 1; ripple.visible = fill < 1.28; ripple.position.y = top.position.y + .004; ripple.scale.setScalar(.12 + rq * .82); ripple.material.opacity = (1 - rq) * .9;
      drops.forEach((d, i) => { const q = (c.T * 1.1 + i / 4) % 1; d.visible = fill < 1.28; d.position.set(Math.sin(i * 3.1) * .12, lerp(2.1, -.7 + fill, q * q), Math.cos(i * 2.3) * .1); d.scale.set(1, 1 + q * .8, 1); });
      const dk = smooth(.8, .95, p) * clamp(w * 1.4); done.position.set(glass.position.x, glass.position.y + 1.25 * k + Math.sin(c.T * 2) * .05, .6); done.scale.setScalar(Math.max(.0001, pop(dk) * .62 * c.k));
      const time = lerp(8, 10.5, smooth(0, .8, p));
      clock.position.set(c.x - c.inner * 1.85 * c.k, c.y + 1.25 * c.k + Math.sin(c.T * 1.1) * .07, -.3); clock.scale.setScalar(k); clock.rotation.set(c.py * .1, -c.inner * .3 + c.px * .2, Math.sin(c.T * .8) * .04);
      mh.rotation.z = -(time % 1) * 6.283; hh.rotation.z = -(time / 12) * 6.283;
      pills.forEach((pl, i) => { pl.position.set(c.x - c.inner * (1.7 + i * .42) * c.k, c.y - (.25 + (i % 2) * .4) * c.k + Math.sin(c.T * 1.5 + i * 2) * .08, .5 - i * .3); pl.rotation.set(c.T * .5 + i, c.T * .4, .6 + i); pl.scale.setScalar(k * 1.1); }); };
  },

  // the diary: appointments get ticked off, and the taxi she booked drives up
  calendar({ scene, shade, check }) {
    const g = new THREE.Group(); scene.add(g);
    const card = new THREE.Group(); g.add(card);
    const ROWS = [['11:00', 'Physio'], ['13:30', 'Taxi'], ['14:00', 'Doctor'], ['19:15', 'Call Sophie']];
    const T = tex(512, 640, (x) => { rbox(x, 0, 0, 512, 640, 44, '#FFFDF9'); x.save(); x.beginPath(); x.roundRect(0, 0, 512, 640, 44); x.clip(); x.fillStyle = COL.coral; x.fillRect(0, 0, 512, 150); x.restore();
      x.fillStyle = '#fff'; x.font = FONT(30, 600); x.fillText('THURSDAY', 40, 62); x.font = FONT(62, 700); x.fillText('13 November', 38, 124);
      ROWS.forEach(([t, l], i) => { const y = 228 + i * 104; x.fillStyle = COL.forest; x.font = FONT(36, 700); x.fillText(t, 40, y + 12); x.fillStyle = COL.ink; x.font = FONT(36, 500); x.fillText(l, 160, y + 12);
        x.beginPath(); x.arc(452, y, 25, 0, 6.3); x.lineWidth = 5; x.strokeStyle = 'rgba(30,42,38,.22)'; x.stroke(); if (i < 3) { x.fillStyle = 'rgba(30,42,38,.1)'; x.fillRect(40, y + 50, 432, 3); } }); });
    card.add(new THREE.Mesh(new RoundedBoxGeometry(2.08, 2.58, .12, 6, .1), phys(COL.cream)));
    const front = new THREE.Mesh(new THREE.PlaneGeometry(2, 2.5), new THREE.MeshBasicMaterial({ map: T, transparent: true, toneMapped: false })); front.position.z = .065; card.add(front);
    [-.5, .5].forEach((x) => { const r = new THREE.Mesh(new THREE.TorusGeometry(.13, .035, 10, 24), phys('#B9B4A8', { metalness: .6, roughness: .25 })); r.position.set(x, 1.3, 0); r.rotation.y = Math.PI / 2; card.add(r); });
    const ticks = ROWS.map((_, i) => { const m = new THREE.Mesh(new THREE.CircleGeometry(.13, 32), new THREE.MeshBasicMaterial({ map: check, transparent: true })); m.position.set((452 / 512 - .5) * 2, (.5 - (228 + i * 104) / 640) * 2.5, .075); card.add(m); return m; });
    // the taxi
    const taxi = new THREE.Group(); g.add(taxi);
    const tb = new THREE.Mesh(new RoundedBoxGeometry(1.5, .42, .7, 5, .16), phys(COL.sun, { clearcoat: 1 })); tb.position.y = .36;
    const cab = new THREE.Mesh(new RoundedBoxGeometry(.8, .36, .62, 5, .14), phys('#DFF1FA', { roughness: .15, clearcoat: 1 })); cab.position.set(-.05, .7, 0);
    const sign = new THREE.Mesh(new RoundedBoxGeometry(.3, .12, .16, 3, .04), phys(COL.ink)); sign.position.set(-.05, .93, 0);
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(.06, 12, 12), new THREE.MeshBasicMaterial({ color: '#FFF6C9' })); lamp.position.set(.74, .4, .2); const lamp2 = lamp.clone(); lamp2.position.z = -.2;
    const wheels = [[-.45, .34], [.45, .34], [-.45, -.34], [.45, -.34]].map(([x, z]) => { const m = new THREE.Mesh(new THREE.CylinderGeometry(.17, .17, .12, 24).rotateX(Math.PI / 2), INK); m.position.set(x, .17, z); taxi.add(m); return m; });
    const tsh = shade(2.6); taxi.add(tb, cab, sign, lamp, lamp2, tsh); tsh.position.y = .01;
    return (w, p, c) => { g.visible = w > .01; if (!g.visible) return;
      const k = c.k * Math.max(.0001, pop(clamp(w * 1.4)));
      card.position.set(c.x + c.inner * 2.25 * c.k, c.y + .35 * c.k + Math.sin(c.T * 1.1) * .07, .3); card.scale.setScalar(k * .92); card.rotation.set(c.py * .08 - .04, -c.inner * .32 + c.px * .18 + Math.sin(c.T * .6) * .05, c.inner * .03);
      ticks.forEach((m, i) => { m.scale.setScalar(Math.max(.0001, pop(smooth(0, 1, clamp(p * 6 - i * 1.25 - .3))) * 1.05)); });
      taxi.visible = !c.room; const drive = smooth(.25, .85, p), tx = lerp(c.x - c.inner * 7.5, c.x - c.inner * 1.95 * c.k, drive);
      taxi.position.set(tx, c.floor + Math.abs(Math.sin(c.T * 9)) * .012 * (1 - drive), .9); taxi.scale.set(c.inner * k * .85, k * .85, k * .85); taxi.rotation.y = c.inner * -.25;
      wheels.forEach((m) => { m.rotation.z = -tx * 5; }); };
  },

  // night: stars, a moon and the warm light of a lamp
  night({ scene, soft }) {
    const sg = new THREE.BufferGeometry(); sg.setAttribute('position', new THREE.Float32BufferAttribute(Array.from({ length: 900 }, () => (Math.random() - .5) * 34), 3));
    const stars = new THREE.Points(sg, new THREE.PointsMaterial({ color: '#fff', size: .05, transparent: true, opacity: 0, depthWrite: false })); stars.position.z = -8; scene.add(stars);
    const moon = new THREE.Mesh(new THREE.SphereGeometry(.62, 40, 40), new THREE.MeshStandardMaterial({ color: '#FFF6D6', emissive: '#FFE7A3', emissiveIntensity: .85, roughness: 1 })); scene.add(moon);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: soft, color: '#FFE7A3', transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending })); glow.scale.setScalar(5.5); scene.add(glow);
    const lamp = new THREE.PointLight('#FFC76B', 0, 9, 1.6); scene.add(lamp);
    return (w, p, c) => { stars.material.opacity = Math.max(w, c.dim) * .9; stars.rotation.z = c.T * .01; stars.visible = stars.material.opacity > .01;
      moon.visible = w > .01; moon.position.set(c.x - c.inner * (c.tall ? 1.3 : 3.3), c.tall ? 4.4 : 3.3, -3.5); moon.scale.setScalar(Math.max(.0001, w)); glow.position.copy(moon.position); glow.material.opacity = w * .55;
      lamp.intensity = w * 12; lamp.position.set(c.vx - c.inner * 1.4, c.vy + 1.2, 2.2); };
  },

  // a fall: rings of alarm around her, then the call goes out to the daughter's phone, then help is on its way
  alarm({ scene }) {
    const g = new THREE.Group(); scene.add(g);
    const rings = Array.from({ length: 4 }, () => { const m = new THREE.Mesh(new THREE.TorusGeometry(1, .02, 8, 96), new THREE.MeshBasicMaterial({ color: '#FF6B5E', transparent: true, opacity: 0, depthWrite: false })); g.add(m); return m; });
    const phone = new THREE.Group(); g.add(phone);
    phone.add(new THREE.Mesh(new RoundedBoxGeometry(1.2, 2.2, .12, 6, .16), phys('#0D1412', { roughness: .25, clearcoat: 1 })));
    const screenT = (state) => tex(320, 600, (x) => {
      rbox(x, 0, 0, 320, 600, 40, state ? COL.forest : '#1E2A26'); x.textAlign = 'center';
      if (!state) { disc(x, 160, 170, 74, COL.coral); x.fillStyle = '#fff'; x.font = FONT(84, 600); x.fillText('S', 160, 200); x.font = FONT(46, 600); x.fillText('Sophie', 160, 318); x.fillStyle = 'rgba(255,255,255,.62)'; x.font = FONT(27, 500); x.fillText('Vita is calling…', 160, 362);
        x.fillStyle = '#FF9E8F'; x.font = FONT(25, 600); x.fillText('Fall · bathroom', 160, 410); disc(x, 160, 500, 46, '#2FB67A'); x.strokeStyle = '#fff'; x.lineWidth = 9; x.lineCap = 'round'; x.beginPath(); x.arc(160, 512, 22, 3.6, 5.8); x.stroke(); }
      else { disc(x, 160, 200, 84, '#fff'); tick(x, 160, 200, 62, COL.forest); x.fillStyle = '#fff'; x.font = FONT(42, 600); x.fillText('Sophie is', 160, 372); x.fillText('on her way', 160, 422); x.fillStyle = 'rgba(255,255,255,.7)'; x.font = FONT(26, 500); x.fillText('Vita stays with Anna', 160, 480); }
      x.textAlign = 'left'; });
    const A = screenT(0), B = screenT(1), scr = new THREE.Mesh(new THREE.PlaneGeometry(1.06, 2.0), new THREE.MeshBasicMaterial({ map: A, transparent: true, toneMapped: false })); scr.position.z = .065; phone.add(scr);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: HALO, color: '#FF6B5E', transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending })); g.add(glow);
    const beam = Array.from({ length: 9 }, () => { const m = new THREE.Mesh(new THREE.SphereGeometry(.055, 12, 12), new THREE.MeshBasicMaterial({ color: '#FFB3A8', transparent: true })); g.add(m); return m; });      // the call, travelling from Vita to the phone
    return (w, p, c) => { g.visible = w > .01; if (!g.visible) return;
      const st = c.alarm, calm = smooth(.72, .8, st), speed = lerp(1.5, .5, calm), col = calm > .5 ? '#7FE0AE' : '#FF6B5E';
      rings.forEach((m, i) => { const q = (c.T * speed * .55 + i / 4) % 1; m.position.set(c.vx, c.vy - .1 * c.vs, -.4); m.scale.setScalar(c.vs * (1.5 + q * 2.4)); m.material.opacity = w * (1 - q) * lerp(.75, .3, calm); m.material.color.set(col); });
      const k = pop(smooth(.3, .44, st)) * clamp(w * 1.5) * c.k, ringing = st > .3 && st < .72;
      if (scr.material.map !== (st > .72 ? B : A)) { scr.material.map = st > .72 ? B : A; scr.material.needsUpdate = true; }
      phone.position.set(c.x + c.inner * 2.2 * c.k, c.y + .25 * c.k + Math.sin(c.T * 1.2) * .06, .8); phone.scale.setScalar(Math.max(.0001, k));
      phone.rotation.set(c.py * .08, -c.inner * .3 + c.px * .2, (ringing ? Math.sin(c.T * 34) * .05 : 0) + c.inner * .05);
      glow.position.copy(phone.position); glow.position.z = .3; glow.scale.setScalar(4.2 * k * (1 + (ringing ? Math.sin(c.T * 12) * .12 : 0))); glow.material.opacity = w * (k > .01 ? .4 : 0); glow.material.color.set(col);
      const on = smooth(.3, .4, st) * (1 - calm) * w;
      beam.forEach((m, i) => { const q = (c.T * .9 + i / beam.length) % 1; m.visible = on > .01; m.position.set(lerp(c.vx, phone.position.x, q), lerp(c.vy + .4 * c.vs, phone.position.y, q) + Math.sin(Math.PI * q) * 1.3 * c.k, .7); m.scale.setScalar(.5 + Math.sin(Math.PI * q)); m.material.opacity = on * Math.sin(Math.PI * q); }); };
  },

  // mother and daughter, the hearts between them, and the calm update the daughter gets every day
  family({ scene, shade, soft, check }) {
    const g = new THREE.Group(); scene.add(g);
    const bodyG = new THREE.LatheGeometry(new THREE.SplineCurve([[0, 0], [.2, 0], [.31, .05], [.345, .2], [.33, .45], [.285, .72], [.21, .93], [.1, 1.03], [0, 1.05]].map(([a, b]) => new THREE.Vector2(a, b))).getPoints(28), 36);
    const armG = new THREE.CapsuleGeometry(.07, .27, 6, 14), eyeG = new THREE.CapsuleGeometry(.032, .05, 4, 10), smileG = new THREE.TorusGeometry(.07, .016, 8, 20, Math.PI), blushM = new THREE.MeshBasicMaterial({ color: '#FF6F91', transparent: true, opacity: .5 });
    const pawn = (col, hairCol, style) => { const o = new THREE.Group(), m = phys(col, { roughness: .42, clearcoat: .7 }), hairM = phys(hairCol, { roughness: .6, clearcoat: .3 }), skin = phys('#F5CFAE', { roughness: .5, clearcoat: .4 });
      const body = new THREE.Mesh(bodyG, m), head = new THREE.Group(); head.position.y = 1.3; head.add(new THREE.Mesh(new THREE.SphereGeometry(.29, 32, 24), skin));
      [-.1, .1].forEach((ex) => { const e = new THREE.Mesh(eyeG, INK); e.position.set(ex, .035, .272); head.add(e); const b = new THREE.Mesh(new THREE.CircleGeometry(.045, 20), blushM); b.position.set(ex * 1.75, -.055, .236); b.rotation.y = ex * 6.2; head.add(b); });
      const smile = new THREE.Mesh(smileG, INK); smile.rotation.z = Math.PI; smile.position.set(0, -.045, .277); head.add(smile);
      const cap = (len, tilt, r = .305) => { const h = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 16, 0, 6.2832, 0, Math.PI * len), hairM); h.rotation.x = tilt; head.add(h); };
      const ball = (r, x, y, z) => { const b = new THREE.Mesh(new THREE.SphereGeometry(r, 20, 16), hairM); b.position.set(x, y, z); head.add(b); };
      if (style === 1) { cap(.5, -.5); ball(.13, 0, .3, -.12); } else { cap(.6, -.78); ball(.1, -.24, -.12, -.12); ball(.1, .24, -.12, -.12); }
      const arms = [-1, 1].map((sd) => { const pv = new THREE.Group(); pv.position.set(sd * .27, .84, 0); const a = new THREE.Mesh(armG, m); a.position.y = -.2; pv.add(a); o.add(pv); return pv; });
      const sh = shade(1.5); sh.position.y = .01; o.add(body, head, sh); o.userData = { head, arms }; g.add(o); return o; };
    const anna = pawn(COL.coral, '#F4F1EC', 1), sophie = pawn('#3D8FD1', '#4A2E1F', 2);
    const rug = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.MeshBasicMaterial({ color: '#FFFFFF', transparent: true, opacity: .45, depthWrite: false })); rug.rotation.x = -Math.PI / 2; g.add(rug);
    const hT = tex(96, 96, (x) => heart(x, 48, 46, 30, COL.coral));
    const hearts = Array.from({ length: 7 }, () => { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: hT, transparent: true, opacity: 0, depthWrite: false })); g.add(sp); return sp; });
    // the daily update
    const ROWS = ['5 glasses of water', 'Pills taken', 'Cheerful and chatty'];
    const cardT = tex(448, 340, (x) => { rbox(x, 0, 0, 448, 340, 40, '#FFFFFF'); x.fillStyle = COL.ink; x.font = FONT(40, 700); x.fillText('Mum’s day', 34, 66); x.fillStyle = 'rgba(30,42,38,.55)'; x.font = FONT(22, 500); x.fillText('Thursday · from Vita', 34, 100);
      ROWS.forEach((t, i) => { const y = 160 + i * 62; disc(x, 56, y, 22, 'rgba(30,42,38,.08)'); x.fillStyle = COL.ink; x.font = FONT(28, 500); x.fillText(t, 96, y + 10); }); });
    const card = new THREE.Group(); g.add(card);
    card.add(new THREE.Mesh(new RoundedBoxGeometry(1.86, 1.42, .08, 5, .04), phys('#FFFFFF', { roughness: .3 })));
    const cf = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 1.366), new THREE.MeshBasicMaterial({ map: cardT, transparent: true, toneMapped: false })); cf.position.z = .045; card.add(cf);
    const ticks = ROWS.map((_, i) => { const m = new THREE.Mesh(new THREE.CircleGeometry(.1, 28), new THREE.MeshBasicMaterial({ map: check, transparent: true })); m.position.set((56 / 448 - .5) * 1.8, (.5 - (160 + i * 62) / 340) * 1.366, .055); card.add(m); return m; });
    return (w, p, c) => { g.visible = w > .01; if (!g.visible) return;
      const k = c.k * Math.max(.7, c.s), ax = c.x + c.inner * 1.85 * k, sx = c.x + c.inner * 3.05 * k, sc = .98 * k, mx = c.room ? c.x : (ax + sx) / 2; anna.visible = sophie.visible = rug.visible = !c.room;
      rug.position.set((ax + sx) / 2, c.floor - .01, .5); rug.scale.set(1.5 * k * w, .62 * k * w, 1);
      [[anna, ax, 0, 1], [sophie, sx, 1, -1]].forEach(([o, x, i, face]) => { const kk = smooth(0, 1, clamp(w * 1.8 - i * .25)), hop = Math.max(0, Math.sin(c.T * 1.2 - i * 1.6)) ** 6 * .12, u = o.userData;
        o.position.set(x, c.floor + hop, .5 + i * .15); o.scale.setScalar(Math.max(.0001, sc * kk)); o.rotation.set(0, c.inner * face * .55 + Math.sin(c.T * .8 + i) * .1 + c.px * .2, Math.sin(c.T * 1.1 + i * 2) * .03);
        u.head.rotation.set(Math.sin(c.T * .9 + i) * .06 - c.py * .1, Math.sin(c.T * .6 + i * 1.7) * .2, Math.sin(c.T * 1.3 + i * 2) * .08);
        const wave = Math.sin(c.T * .5 + i * 2.6) > .5 ? 1 : 0; u.wave = lerp(u.wave || 0, wave, .08);
        u.arms[0].rotation.z = -.22 - Math.sin(c.T * 1.6 + i) * .06; u.arms[1].rotation.z = lerp(.22 + Math.sin(c.T * 1.6 + i + 1) * .06, 2.45 + Math.sin(c.T * 9) * .3, u.wave); });
      hearts.forEach((sp, i) => { const q = (c.T * .2 + i / hearts.length) % 1; sp.position.set((c.room ? c.vx : mx) + Math.sin(i * 9.1 + q * 4) * .7 * k, (c.room ? c.vy + .25 : c.floor + 1.5 * sc) + q * 1.3 * k, .9); sp.scale.setScalar(.3 * k * (.6 + .4 * Math.sin(Math.PI * q))); sp.material.opacity = w * Math.sin(Math.PI * q); });
      const ck = pop(smooth(.12, .4, p)) * clamp(w * 1.5);
      card.position.set(mx + (c.room ? 0 : c.inner * .15), (c.room ? c.y : c.floor + 2.95 * k) + Math.sin(c.T * 1.2) * .06, .6); card.scale.setScalar(Math.max(.0001, ck * k * 1.08)); card.rotation.set(c.py * .08 - .05, -c.inner * .22 + c.px * .2 + Math.sin(c.T * .7) * .06, c.inner * -.03);
      ticks.forEach((m, i) => { m.scale.setScalar(Math.max(.0001, pop(smooth(0, 1, clamp(p * 5 - 1.6 - i * .8))) * 1.1)); }); };
  },

  // privacy: a soft dome of light around her. Cameras bounce off it.
  shield({ scene }) {
    const mat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { uOp: { value: 0 }, uT: { value: 0 } },
      vertexShader: 'varying vec3 vN, vV, vP; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.); vN = normalMatrix * normal; vV = -mv.xyz; vP = position; gl_Position = projectionMatrix * mv; }',
      fragmentShader: `uniform float uOp, uT; varying vec3 vN, vV, vP;
        void main(){ float f = pow(1. - abs(dot(normalize(vN), normalize(vV))), 2.4);
          float band = exp(-pow((vP.y - sin(uT * .7) * 1.5) * 3., 2.));
          float hex = smoothstep(.06, 0., abs(fract(vP.y * 3.2) - .5) - .44) * .5 + smoothstep(.05, 0., abs(fract(atan(vP.z, vP.x) * 3.82) - .5) - .45) * .5;
          gl_FragColor = vec4(mix(vec3(.37, .78, .55), vec3(.85, 1., .9), f), uOp * (.04 + .7 * f + hex * (.05 + .28 * band) + .08 * band)); }` });
    const dome = new THREE.Mesh(new THREE.SphereGeometry(2.3, 64, 48), mat); scene.add(dome);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(2.32, .012, 8, 120), new THREE.MeshBasicMaterial({ color: '#BFF3D4', transparent: true, opacity: 0 })); ring.rotation.x = Math.PI / 2; scene.add(ring);
    const camT = tex(128, 128, (x) => { rbox(x, 22, 46, 84, 54, 14, '#FFFFFF'); rbox(x, 46, 34, 36, 20, 8, '#FFFFFF'); disc(x, 64, 73, 17, '#13201A'); disc(x, 64, 73, 8, '#FFFFFF');
      x.strokeStyle = '#FF6B5E'; x.lineWidth = 9; x.lineCap = 'round'; x.beginPath(); x.arc(64, 68, 54, 0, 6.3); x.stroke(); x.beginPath(); x.moveTo(26, 30); x.lineTo(102, 106); x.stroke(); });
    const cams = Array.from({ length: 3 }, () => { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: camT, transparent: true, opacity: 0, depthWrite: false })); scene.add(sp); return sp; });
    const flash = cams.map(() => { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: HALO, color: '#BFF3D4', transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending })); scene.add(sp); return sp; });
    return (w, p, c) => { dome.visible = ring.visible = w > .01; cams.forEach((s, i) => { s.visible = flash[i].visible = dome.visible; }); if (!dome.visible) return;
      const k = c.vs * (.6 + .4 * w) * Math.max(.0001, Math.sqrt(w)), cy = c.vy + .15 * c.vs;
      dome.position.set(c.vx, cy, 0); dome.scale.setScalar(k); dome.rotation.y = c.T * .12; mat.uniforms.uOp.value = w; mat.uniforms.uT.value = c.T;
      const sy = Math.sin(c.T * .7) * 1.5; ring.position.set(c.vx, cy + sy * k, 0); ring.scale.setScalar(k * Math.sqrt(Math.max(.0001, 1 - (sy / 2.3) ** 2))); ring.material.opacity = w * .8;
      cams.forEach((sp, i) => { const a = i * 2.2 + .5 + Math.sin(c.T * .25 + i) * .5, b = Math.abs(Math.sin(c.T * .9 + i * 2.1)), rad = (2.5 + b * 1.5) * k;      // they come in, touch the dome and are thrown back
        sp.position.set(c.vx + Math.cos(a) * rad, cy + Math.sin(a) * rad * .85, .6); sp.scale.setScalar(.62 * c.k * (.8 + b * .3)); sp.material.opacity = w * (.35 + b * .65); sp.material.rotation = Math.sin(c.T * 2 + i) * .2 * b;
        flash[i].position.set(c.vx + Math.cos(a) * 2.35 * k, cy + Math.sin(a) * 2.35 * k * .85, .5); flash[i].scale.setScalar(1.6 * k); flash[i].material.opacity = w * Math.max(0, 1 - b * 5) * .9; }); };
  },
};

// ---------- the house ----------
// Anna's home: the stage of the whole story. The roof can lift off and the near walls can sink to a cutaway.
// In every room stands a small Vita; when she answers, the floor lights up and sound ripples out.
function buildHouse(scene) {
    const tilt = new THREE.Group(), g = new THREE.Group(); scene.add(tilt); tilt.add(g);
    const M = (col, o) => (typeof col === 'string' ? phys(col, { clearcoat: .3, roughness: .5, ...o }) : col);
    const add = (m, x, y, z, parent = g) => { m.position.set(x, y, z); m.castShadow = m.receiveShadow = true; parent.add(m); return m; };
    const rb = (w, h, d, col, x, y, z, parent, r = .04) => add(new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2.1, h / 2.1, d / 2.1)), M(col)), x, y, z, parent);
    const cyl = (rt, rbt, h, col, x, y, z, parent) => add(new THREE.Mesh(new THREE.CylinderGeometry(rt, rbt, h, 36), M(col)), x, y, z, parent);
    const ball = (r, col, x, y, z, parent) => add(new THREE.Mesh(new THREE.SphereGeometry(r, 28, 22), M(col)), x, y, z, parent);
    const CREAM = M('#FBF3E4'), WOOD = M(COL.wood), WHITE = M('#FFFFFF'), FLOOR_Y = .04, WH = .95;
    // the garden it stands in
    cyl(3.02, 3.14, .18, '#BCDFA0', 0, -.11, 0).castShadow = false; cyl(3.14, 3.0, .12, '#A98F6E', 0, -.26, 0).castShadow = false;
    rb(4.44, .1, 3.44, '#E9DECB', 0, -.02, 0);
    [[-2.62, -1.25, 1], [2.68, -.75, .8], [-2.72, .45, .62]].forEach(([x, z, k]) => { cyl(.06 * k, .09 * k, .55 * k, WOOD, x, .25 * k, z); ball(.42 * k, COL.forest, x, .75 * k, z); ball(.3 * k, COL.leaf, x + .22 * k, .98 * k, z + .1 * k); ball(.26 * k, '#4D8F6A', x - .2 * k, 1.0 * k, z - .08 * k); });
    [[2.5, 1.2, .2], [2.72, .8, .15], [-2.45, 1.55, .19], [-1.2, 2.5, .17], [.9, 2.6, .2], [1.25, 2.52, .13]].forEach(([x, z, r], i) => { ball(r, i % 2 ? COL.leaf : '#4D8F6A', x, r * .7, z); ball(r * .28, i % 3 ? COL.coral : COL.sun, x + r * .5, r * 1.25, z + r * .3); });
    [[-.2, 2.25], [.25, 2.6], [-.3, 2.9]].forEach(([x, z]) => cyl(.2, .2, .03, '#E9DECB', x, -.01, z).castShadow = false);
    // rooms: x from, z from, x to, z to, the colour of the floor, where its Vita stands (x, top of the furniture, z), what she says
    const ROOMS = [
      [-2.1, -.1, .3, 1.6, '#E0B36E', [0, .32, .22], 'Shall we call Sophie?'],
      [.3, -.1, 2.1, 1.6, '#9CCD98', [.62, .5, .14], 'Time for a sip of water'],
      [-2.1, -1.6, .1, -.1, '#B9A0EA', [-.92, .3, -1.36], 'Sleep well, Anna'],
      [.1, -1.6, 1.2, -.1, '#89C5E0', [.94, .27, -.42], 'Careful, the floor is wet'],
      [1.2, -1.6, 2.1, -.1, '#DABF88', [1.92, .4, -.78], ''],
    ];
    const floors = ROOMS.map(([x1, z1, x2, z2, col]) => { const m = rb(x2 - x1, .05, z2 - z1, new THREE.MeshStandardMaterial({ color: col, emissive: COL.sun, emissiveIntensity: 0, roughness: .8, envMapIntensity: .3 }), (x1 + x2) / 2, FLOOR_Y - .025, (z1 + z2) / 2, g, .01); m.castShadow = false; return m; });
    const wall = (x1, z1, x2, z2, h, col = CREAM) => { const geo = new RoundedBoxGeometry(Math.abs(x2 - x1) + .09, h, Math.abs(z2 - z1) + .09, 2, .03); geo.translate(0, h / 2, 0); return add(new THREE.Mesh(geo, col), (x1 + x2) / 2, FLOOR_Y, (z1 + z2) / 2); };
    const OUT = M('#FFF9EE'), GLASS = new THREE.MeshBasicMaterial({ color: '#BFE6F5' });
    wall(-2.1, -1.6, 2.1, -1.6, WH, OUT); const wFront = wall(-2.1, 1.6, 2.1, 1.6, WH, OUT), wLeft = wall(-2.1, -1.6, -2.1, 1.6, WH, OUT), wRight = wall(2.1, -1.6, 2.1, 1.6, WH, OUT);
    [[-2.1, -.1, -.62, -.1], [-.18, -.1, 1.48, -.1], [1.9, -.1, 2.1, -.1], [.3, -.1, .3, .98], [.3, 1.42, .3, 1.6], [.1, -1.6, .1, -.72], [.1, -.3, .1, -.1], [1.2, -1.6, 1.2, -.1]].forEach(([a, b, c2, d]) => wall(a, b, c2, d, .5));
    const fwin = [[-1.35, .5], [-.35, .5], [1.2, .7]].map(([x, wd]) => { const o = new THREE.Group(); o.position.set(x, .52, .05); wFront.add(o); rb(wd + .1, .46, .08, CREAM, 0, 0, 0, o, .03); rb(wd, .36, .1, GLASS, 0, 0, 0, o, .02).castShadow = false; rb(.03, .36, .11, CREAM, 0, 0, 0, o, .01); rb(wd + .16, .05, .14, WOOD, 0, -.26, .02, o, .02); return o; });
    { const o = new THREE.Group(); o.position.set(.05, .52, .35); wRight.add(o); fwin.push(o); rb(.08, .46, .6, CREAM, 0, 0, 0, o, .03); rb(.1, .36, .5, GLASS, 0, 0, 0, o, .02).castShadow = false; rb(.11, .36, .03, CREAM, 0, 0, 0, o, .01); }
    // windows and the front door, in the back wall
    [[-1.25, .62], [.65, .44]].forEach(([x, w]) => { rb(w + .1, .44, .14, CREAM, x, .62, -1.6, g, .03); rb(w, .34, .16, GLASS, x, .62, -1.6, g, .02).castShadow = false; rb(.03, .34, .17, CREAM, x, .62, -1.6); });
    rb(.42, .74, .13, COL.forest, 1.65, .41, -1.6, g, .04); ball(.03, COL.sun, 1.78, .4, -1.52);
    // the roof
    const roof = new THREE.Group(); roof.position.y = FLOOR_Y + WH; g.add(roof);
    const TILE = M(COL.coral, { clearcoat: 1, roughness: .35 });
    [1, -1].forEach((sd) => { const m = rb(4.7, .09, 2.12, TILE, 0, .5, sd * .92, roof, .04); m.rotation.x = sd * .5; m.castShadow = false; });
    const tri = new THREE.Shape(); tri.moveTo(-1.62, 0); tri.lineTo(1.62, 0); tri.lineTo(0, .9); tri.closePath();
    [-2.1, 2.1].forEach((x) => { const m = new THREE.Mesh(new THREE.ShapeGeometry(tri), M('#FFF9EE', { side: THREE.DoubleSide })); m.rotation.y = Math.PI / 2; m.position.set(x, 0, 0); roof.add(m);
      const w = new THREE.Mesh(new THREE.CircleGeometry(.17, 32), new THREE.MeshBasicMaterial({ color: COL.sun, side: THREE.DoubleSide })); w.rotation.y = Math.PI / 2; w.position.set(x + Math.sign(x) * .012, .36, 0); roof.add(w); });
    const ridge = cyl(.07, .07, 4.7, M('#B93A32', { clearcoat: 1 }), 0, 1.0, 0, roof); ridge.rotation.z = Math.PI / 2; ridge.castShadow = false;
    rb(.3, .7, .3, CREAM, 1.25, .75, -.75, roof).castShadow = false; rb(.36, .08, .36, TILE, 1.25, 1.12, -.75, roof).castShadow = false;
    const smoke = Array.from({ length: 5 }, () => { const m = new THREE.Mesh(new THREE.SphereGeometry(.12, 16, 16), new THREE.MeshBasicMaterial({ color: '#FFFFFF', transparent: true, opacity: 0, depthWrite: false })); roof.add(m); return m; });
    const LAMP = new THREE.MeshStandardMaterial({ color: '#FFE2A0', emissive: '#FFC85A', emissiveIntensity: .9 });
    // living room
    cyl(.62, .62, .02, '#CFE3C8', -.95, FLOOR_Y + .01, .85).castShadow = false;
    rb(1.0, .2, .42, COL.leaf, -1.15, .2, .26, g, .08); rb(1.0, .44, .14, COL.leaf, -1.15, .32, .1, g, .06); rb(.13, .32, .42, COL.leaf, -1.68, .26, .26, g, .05); rb(.13, .32, .42, COL.leaf, -.62, .26, .26, g, .05);
    rb(.22, .1, .16, COL.sun, -1.4, .34, .28, g, .04); rb(.22, .1, .16, '#FF9E8F', -.95, .34, .28, g, .04);
    const chair = new THREE.Group(); chair.position.set(-1.72, 0, 1.15); chair.rotation.y = .9; g.add(chair); rb(.44, .2, .42, '#EE9C8C', 0, .2, 0, chair, .08); rb(.44, .42, .13, '#EE9C8C', 0, .32, -.17, chair, .06);
    cyl(.26, .26, .05, WOOD, -.9, .26, .9); cyl(.04, .06, .2, WOOD, -.9, .14, .9); cyl(.05, .04, .07, '#FFFFFF', -.82, .32, .95);
    rb(.3, .28, .3, WOOD, 0, .18, .22, g, .04);
    cyl(.02, .02, .8, '#8A8272', -1.88, .44, .16); cyl(.07, .16, .2, LAMP, -1.88, .86, .16).castShadow = false; cyl(.1, .12, .03, '#8A8272', -1.88, .055, .16);
    cyl(.1, .08, .16, '#EE9C8C', -1.86, .12, .62); ball(.17, COL.forest, -1.86, .36, .62); ball(.11, COL.leaf, -1.79, .5, .56);
    // kitchen
    rb(.98, .42, .36, WHITE, .88, .25, .14, g, .04); rb(1.04, .05, .4, WOOD, .88, .475, .14, g, .02); [1.0, 1.22].forEach((x) => cyl(.07, .07, .012, '#3A423E', x, .506, .14).castShadow = false); cyl(.05, .06, .09, COL.coral, 1.0, .55, .14);
    rb(.36, .86, .36, '#E4ECEC', 1.86, .47, 1.36, g, .05); rb(.03, .3, .02, '#9AA5A5', 1.67, .6, 1.24, g, .01);
    cyl(.34, .34, .05, WOOD, 1.25, .38, 1.1); cyl(.05, .1, .34, WOOD, 1.25, .2, 1.1);
    [[.98, 1.4], [1.72, .92]].forEach(([x, z]) => { cyl(.13, .13, .05, COL.leaf, x, .26, z); cyl(.03, .05, .22, WOOD, x, .13, z); });
    cyl(.045, .04, .11, M('#8FD3F2', { transparent: true, opacity: .85 }), 1.2, .46, 1.12); cyl(.1, .1, .015, WHITE, 1.4, .41, 1.0);
    // bedroom
    rb(.86, .16, 1.16, WOOD, -1.5, .12, -.92, g, .04); rb(.8, .14, 1.1, WHITE, -1.5, .24, -.92, g, .06); rb(.82, .1, .7, '#B5A2EE', -1.5, .3, -.72, g, .05); rb(.5, .1, .26, WHITE, -1.5, .34, -1.3, g, .05); rb(.9, .5, .08, WOOD, -1.5, .3, -1.5, g, .04);
    rb(.28, .26, .28, WOOD, -.92, .17, -1.36, g, .04); rb(.58, .84, .3, '#F3E7D3', -.3, .46, -1.38, g, .04); rb(.02, .5, .02, WOOD, -.3, .46, -1.22, g, .005);
    cyl(.42, .42, .02, '#FFE9C4', -.75, FLOOR_Y + .01, -.6).castShadow = false;
    // bathroom
    rb(.4, .3, .8, WHITE, .36, .19, -1.08, g, .12); rb(.3, .03, .68, M('#9BD8F5'), .36, .33, -1.08, g, .01).castShadow = false; cyl(.02, .02, .14, '#9AA5A5', .36, .4, -1.45);
    rb(.3, .4, .24, WHITE, .94, .24, -1.42, g, .05); cyl(.1, .1, .015, M('#9BD8F5'), .94, .448, -1.4).castShadow = false; rb(.3, .3, .03, GLASS, .94, .72, -1.55, g, .01).castShadow = false;
    rb(.44, .02, .3, COL.leaf, .78, FLOOR_Y + .01, -.9, g, .01).castShadow = false; cyl(.12, .1, .23, WOOD, .94, .155, -.42);
    // hall
    rb(.24, .34, .5, WOOD, 1.93, .22, -.78, g, .04);
    rb(.4, .02, .26, '#EE9C8C', 1.65, FLOOR_Y + .01, -1.3, g, .01).castShadow = false; cyl(.02, .02, .72, WOOD, 1.36, .4, -.3); ball(.05, WOOD, 1.36, .78, -.3); rb(.16, .22, .05, COL.coral, 1.42, .58, -.3, g, .02);
    // a Vita in every room, the ripples she sends out and her line above the room
    const spk = ROOMS.map(([x1, z1, x2, z2, , at, line], i) => {
      const v = makeVita(); setMood(v, 'happy'); v.scale.setScalar(.115); v.position.set(at[0], at[1] + .127, at[2]); v.traverse((o) => { if (o.isMesh) o.castShadow = true; }); g.add(v);
      const rings = [0, 1, 2].map(() => { const m = new THREE.Mesh(new THREE.RingGeometry(.9, 1, 64), new THREE.MeshBasicMaterial({ color: COL.coral, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide })); m.rotation.x = -Math.PI / 2; m.position.set(at[0], FLOOR_Y + .012, at[2]); g.add(m); return m; });
      return { v, rings, base: at[1] + .127, on: 0 }; });
    // Anna
    const anna = new THREE.Group(); g.add(anna);
    add(new THREE.Mesh(new THREE.LatheGeometry(new THREE.SplineCurve([[0, 0], [.1, 0], [.13, .03], [.125, .14], [.09, .27], [.04, .33], [0, .34]].map(([a, b]) => new THREE.Vector2(a, b))).getPoints(20), 28), M(COL.coral, { clearcoat: .7 })), 0, 0, 0, anna);
    ball(.095, '#F5CFAE', 0, .42, 0, anna); const hair = ball(.1, '#F4F1EC', 0, .44, -.02, anna); hair.scale.set(1, .85, 1); ball(.045, '#F4F1EC', 0, .53, -.05, anna);
    [-.035, .035].forEach((x) => { const e = new THREE.Mesh(new THREE.SphereGeometry(.012, 8, 8), INK); e.position.set(x, .43, .09); anna.add(e); });
    return { fwin, tilt, g, roof, roofY: FLOOR_Y + WH, floorY: FLOOR_Y, wFront, wLeft, wRight, smoke, floors, spk, anna, glass: GLASS, lamp: LAMP };
}

// ---------- the world ----------
let R = null, dpr = Math.min(devicePixelRatio, 1.5), fAcc = 0, fN = 0;
const canvas = $('#world');
const bgA = new THREE.Color(), bgB = new THREE.Color(), bg = new THREE.Color(), cT = new THREE.Color();
const ptr = { x: 0, y: 0, tx: 0, ty: 0 };
addEventListener('pointermove', (e) => { ptr.tx = e.clientX / innerWidth * 2 - 1; ptr.ty = e.clientY / innerHeight * 2 - 1; }, { passive: true });
const uses = (fx) => K.some((k) => k.fx.includes(fx));
let moodHold = 0, alarmOn = false, alarmP = 0, alarmSt = 0, waitTxt = '';
const waitEl = $('.wait');

// the day bar: the time of the story and where in the day you are
const clockEl = $('#clock'), dayEl = $('#daybar'), trackEl = $('#track'), fillEl = $('#fill'), knobEl = $('#knob');
const TIMED = K.map((k, i) => (k.time !== null ? i : -1)).filter((i) => i >= 0), dayAt = (i) => (i <= TIMED[0] ? 0 : i >= TIMED[TIMED.length - 1] ? 1 : TIMED.indexOf(i) / (TIMED.length - 1));
let trackW = 0, stopEls = [];
if (trackEl) { TIMED.forEach((i) => { const a = document.createElement('a'), m = K[i].time; a.href = '#' + secs[i].id; a.style.left = (dayAt(i) * 100) + '%'; a.innerHTML = `<span>${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}</span>`; a.setAttribute('aria-label', secs[i].dataset.name || ''); trackEl.append(a); stopEls.push([i, a]); });
  const mw = () => { trackW = trackEl.clientWidth; }; mw(); addEventListener('resize', mw); addEventListener('load', mw); }

// how the house is seen in each kind of chapter: how big, turned how far, tilted how far, where on screen, and which point of it sits there
const ROOM_AT = [[-.9, .72], [1.2, .7], [-1.0, -.85], [.66, -.85], [1.66, -.8]], ROOM_YAW = [.22, -.2, .26, -.1, -.3];
const shotOf = (k) => k.shot === 'none' ? { sc: .3, yaw: -1.3, tl: .34, fx: 10, fy: -1.2, cx: 0, cz: 0 }
  : k.shot === 'over' ? { sc: .84, yaw: -.42, tl: .6, fx: 2.9, fy: -.25, cx: 0, cz: 0 }
  : k.room >= 0 ? { sc: k.zoom || 1.14, yaw: ROOM_YAW[k.room], tl: .84, fx: 3.3, fy: -.3, cx: ROOM_AT[k.room][0], cz: ROOM_AT[k.room][1] }
  : { sc: .8, yaw: -.6, tl: .34, fx: 2.0, fy: -.05, cx: 0, cz: 0 };
K.forEach((k) => { k.view = shotOf(k); });
// where Anna stands in each room, and how she gets from one to the next through the doors
const SPOT = [[-.42, .8], [.72, .62], [-.72, -.62], [.78, -.8], [1.58, -.78]];
const WAY = {
  '2>1': [[-.37, -.3], [-.37, .55], [0, 1.2], [.55, 1.2]],                                            // bedroom door, past the sofa, kitchen door
  '1>4': [[1.5, .5], [1.69, .2], [1.69, -.15], [1.6, -.5]],                                           // along the counter, hall door
  '4>0': [[1.6, -.5], [1.69, -.15], [1.69, .2], [1.5, .5], [.72, .62], [.55, 1.2], [0, 1.2]],          // back through the kitchen
  '0>3': [[-.37, .55], [-.37, -.3], [-.3, -.5], [.1, -.5], [.68, -.5]],                               // through the bedroom to the bathroom
  '3>2': [[.68, -.5], [.1, -.5], [-.3, -.5]],
  '2>0': [[-.37, -.3], [-.37, .55]],
};
const pathOf = (a, b) => { const f = WAY[a + '>' + b], r = WAY[b + '>' + a]; return [SPOT[a], ...(f || (r ? [...r].reverse() : [])), SPOT[b]]; };
const along = (pts, t) => { let tot = 0; const len = pts.slice(1).map((q, i) => { const d = Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]); tot += d; return d; }); let d = t * tot;
  for (let i = 0; i < len.length; i++) { if (d <= len[i] || i === len.length - 1) { const f = clamp(d / len[i]); return [lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f), Math.atan2(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])]; } d -= len[i]; } };
// where the things of a room's story float, measured from the Vita of that room
const OFF = { water: [.75, 1.25], calendar: [1.5, 1.15], family: [.3, 1.4], alarm: [.9, 1.15], chat: [0, .15] };

try {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(dpr);
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.shadowMap.autoUpdate = false;
  const scene = new THREE.Scene();
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
  const cam = new THREE.PerspectiveCamera(35, 1, .1, 100); cam.position.set(0, 0, 11);
  const key = new THREE.DirectionalLight('#ffffff', 2.2); key.position.set(4, 6, 8); scene.add(key);
  key.castShadow = true; key.shadow.mapSize.set(innerWidth < 860 ? 1024 : 2048, innerWidth < 860 ? 1024 : 2048); key.shadow.radius = 5; key.shadow.bias = -.0005; key.shadow.normalBias = .02; Object.assign(key.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8, near: 1, far: 32 });
  const rim = new THREE.DirectionalLight('#BFE3CF', 1.4); rim.position.set(-6, 3, -6); scene.add(rim);
  const fill = new THREE.DirectionalLight('#FFF1E0', .85); fill.position.set(-1, -3, 9); scene.add(fill);      // a soft light from the front, so nothing that faces you sits in the dark

  const mk = (size, stops) => { const c = document.createElement('canvas'); c.width = c.height = size; const x = c.getContext('2d'), gr = x.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2); stops.forEach(([o, col]) => gr.addColorStop(o, col)); x.fillStyle = gr; x.fillRect(0, 0, size, size); return new THREE.CanvasTexture(c); };
  const soft = mk(64, [[0, 'rgba(255,255,255,1)'], [.4, 'rgba(255,255,255,.35)'], [1, 'rgba(255,255,255,0)']]), dark = mk(128, [[0, 'rgba(0,0,0,1)'], [1, 'rgba(0,0,0,0)']]);
  const shade = (size) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(size, size * .6), new THREE.MeshBasicMaterial({ map: dark, transparent: true, opacity: .24, depthWrite: false })); m.rotation.x = -Math.PI / 2; return m; };
  const check = tex(96, 96, (x) => { disc(x, 48, 48, 44, '#2FB67A'); tick(x, 48, 49, 34); });

  const vita = makeVita(); scene.add(vita);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.9, 2.9), new THREE.MeshBasicMaterial({ map: dark, transparent: true, opacity: .3, depthWrite: false })); shadow.rotation.x = -Math.PI / 2; scene.add(shadow);
  const H = buildHouse(scene);
  // the sun crosses the sky behind the house as the day goes by
  const sun = new THREE.Mesh(new THREE.CircleGeometry(.6, 48), new THREE.MeshBasicMaterial({ color: '#FFF4CC', transparent: true, toneMapped: false, depthWrite: false })); sun.renderOrder = -3; scene.add(sun);
  const sunGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: soft, color: '#FFE08A', transparent: true, depthWrite: false })); sunGlow.renderOrder = -4; sunGlow.scale.setScalar(7); scene.add(sunGlow);
  const bokeh = Array.from({ length: 6 }, () => { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: soft, color: '#FFFFFF', transparent: true, opacity: 0, depthWrite: false })); sp.renderOrder = -2;
    sp.userData = { a: Math.random() * 6.283, r: 2.5 + Math.random() * 6, sp: .02 + Math.random() * .04, y: (Math.random() - .5) * 7, s: 2 + Math.random() * 2.6 }; scene.add(sp); return sp; });
  const trail = Array.from({ length: 40 }, (_, i) => { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: soft, color: ['#FFFFFF', COL.sun, '#FF9E8F', COL.mint][i % 4], transparent: true, opacity: 0, depthWrite: false })); sp.userData = { life: 0, v: new THREE.Vector3() }; scene.add(sp); return sp; });

  const size = () => { const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); };
  size(); addEventListener('resize', size);
  const extra = Object.keys(SCENES).filter(uses).map((name) => ({ name, run: SCENES[name]({ scene, makeVita, setMood, soft, shade, check }) }));
  R = { renderer, scene, cam, vita, shadow, key, rim, extra, H, sun, sunGlow, bokeh, trail, tn: 0, acc: 0, say: new THREE.Vector3(), S: null, N: 0, ax: SPOT[2][0], az: SPOT[2][1], face: 0, fall: 0 };
  window.__world = { scene, cam };

  // prepare every material now, also of things that are still hidden, so nothing hitches the first time it appears while you scroll
  const was = new Map(); scene.traverse((o) => { was.set(o, o.visible); o.visible = true; }); renderer.compile(scene, cam); scene.traverse((o) => { o.visible = was.get(o); });

  const ray = new THREE.Raycaster(), v2 = new THREE.Vector2(), ui = 'a, button, input, select, summary, details, label';
  const hitVita = (e) => { v2.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight * 2 - 1)); ray.setFromCamera(v2, cam); return vita.visible && ray.intersectObject(vita, true).length > 0; };
  addEventListener('click', (e) => { if (e.target.closest(ui)) return; if (hitVita(e)) { vita.userData.hop = 1; vita.userData.hopH = 1; setMood(vita, 'happy'); moodHold = 1.2; } });
  let hoverAt = 0;
  addEventListener('pointermove', (e) => { const now = performance.now(); if (now - hoverAt < 80) return; hoverAt = now; document.body.style.cursor = !(e.target.closest && e.target.closest(ui)) && hitVita(e) ? 'pointer' : ''; }, { passive: true });
} catch (err) { console.warn('3D not available', err); canvas.style.display = 'none'; }

// Vita says something in every chapter that gives her a line (data-say). The bubble follows whichever Vita is speaking.
const sayEl = $('#say'); let sayTxt = '', sayWait = 0, sayHalf = 0, sayAt = -9;
const tmp = new THREE.Vector3(), P3 = new THREE.Vector3(), YAX = new THREE.Vector3(0, 1, 0), XAX = new THREE.Vector3(1, 0, 0);
function speak(dt, cur, mid) {
  if (!sayEl || !R) return;
  tmp.copy(R.say).project(R.cam);
  const want = (tmp.x * .5 + .5) * innerWidth, half = sayHalf + 10, px = half * 2 >= innerWidth ? innerWidth / 2 : Math.min(innerWidth - half, Math.max(half, want));
  sayEl.style.setProperty('--tail', Math.max(22 - sayHalf, Math.min(sayHalf - 22, want - px)).toFixed(1) + 'px');
  sayEl.style.transform = `translate(${px.toFixed(1)}px, ${Math.max(96, (-tmp.y * .5 + .5) * innerHeight).toFixed(1)}px) translate(-50%, -100%)`;
  const txt = K[cur].fx.includes('alarm') ? (alarmSt < .15 ? 'Anna, are you alright?' : alarmSt < .3 ? 'Anna? Can you hear me?' : alarmSt < .72 ? 'No answer. I’m calling Sophie.' : 'Help is coming. I’m here.') : secs[cur].dataset.say || '';
  if (txt !== sayTxt) { sayTxt = txt; sayWait = start ? 0 : .5; sayEl.classList.remove('on'); }
  sayWait -= dt;
  if (!txt || mid > .2) sayEl.classList.remove('on');
  else if (sayWait <= 0) { if (sayEl.textContent !== txt) { sayEl.textContent = txt; sayHalf = sayEl.offsetWidth / 2; } if (!sayEl.classList.contains('on')) sayAt = T; sayEl.classList.add('on'); }
}
$$('[data-alarm]').forEach((b) => b.addEventListener('click', () => { alarmOn = true; b.disabled = true; }));
$$('form.form').forEach((fm) => fm.addEventListener('submit', (e) => { e.preventDefault(); if (!fm.checkValidity()) return fm.reportValidity(); fm.classList.add('sent'); if (R) { R.vita.userData.hop = 1; R.vita.userData.hopH = 1; } }));

// ---------- every frame ----------
let yc = start ? centers[+start] + startL * innerHeight : scrollY + innerHeight / 2, last = performance.now(), T = start ? 5 : 0, active = -1, lastBg = '', lastClock = '', lastP = -1;
const W = {}, P = {}, L = {}, Wt = {}, Pt = {}, Lt = {}, homeOf = {};
function edges(i) {      // where the middle of the screen is inside chapter i, in screen heights, and how far its story is
  const vh = innerHeight; let dTop = (yc - tops[i]) / vh, dBot = (bots[i] - yc) / vh;
  const p = i === 0 ? clamp((dTop - .5) / .42) : clamp((dTop - .18) / .5);
  if (i === 0) dTop = Math.max(dTop, .6); if (i === K.length - 1) dBot = Math.max(dBot, .6);
  return [dTop, dBot, p];
}
function weights(dt) {
  for (const k in SCENES) { W[k] = 0; P[k] = 0; L[k] = 0; }
  K.forEach((k, i) => { if (!k.fx.length) return;
    const [dTop, dBot, p] = edges(i); if (dTop < -.4 || dBot < -.4) return;
    const v = smooth(-.1, .32, dTop) * smooth(.12, .42, dBot);      // arriving once the camera is nearly there; gone before it moves on
    const lg = clamp((dTop - .15) / Math.max(.2, (bots[i] - tops[i]) / innerHeight - .75));
    for (const fx of k.fx) if (v > W[fx]) { W[fx] = v; P[fx] = p; L[fx] = lg; homeOf[fx] = k; } });
  for (const k in W) { if (start || Wt[k] === undefined) { Wt[k] = W[k]; Pt[k] = P[k]; Lt[k] = L[k]; } else { Wt[k] = lerp(Wt[k], W[k], 1 - Math.exp(-dt * 5)); if (W[k] > 0) { Pt[k] = lerp(Pt[k], P[k], 1 - Math.exp(-dt * 2.6)); Lt[k] = lerp(Lt[k], L[k], 1 - Math.exp(-dt * 3.2)); } } }
}
function frame(now) {
  if (document.hidden) { last = now; return requestAnimationFrame(frame); }
  const raw = (now - last) / 1000, dt = Math.min(.05, raw); last = now; T += dt;
  if (R && T > 2.5 && !start) { fAcc += raw; if (++fN >= 45) { const avg = fAcc / fN; fAcc = fN = 0; if (avg > 1 / 44 && dpr > 1) { dpr = Math.max(1, dpr - .25); R.renderer.setPixelRatio(dpr); } } }
  const ln = window.__lenis; if (ln) { window.__worldDrives = true; ln.raf(now); }
  const ty = start ? centers[+start] + startL * innerHeight : (ln ? ln.animatedScroll : scrollY) + innerHeight / 2; yc = reduce || start || ln ? ty : lerp(yc, ty, 1 - Math.exp(-dt * 7));
  let cur = 0; for (let i = 0; i < tops.length; i++) if (yc >= tops[i]) cur = i;
  const dTop = (yc - tops[cur]) / innerHeight, dBot = (bots[cur] - yc) / innerHeight, E = .5;
  let a = K[cur], b = K[cur], t = 0, ia = cur, ib = cur;
  if (cur > 0 && dTop < E) { a = K[cur - 1]; ia = cur - 1; t = smooth(-E, E, dTop); } else if (cur < K.length - 1 && dBot < E) { b = K[cur + 1]; ib = cur + 1; t = smooth(-E, E, -dBot); }
  if (cur !== active) { active = cur; document.body.classList.toggle('dark', K[cur].dark); if (R) document.body.style.backgroundColor = K[cur].bg; document.documentElement.style.setProperty('--bgc', K[cur].bg); stopEls.forEach(([i, el]) => el.classList.toggle('on', i === cur)); if (dayEl) dayEl.classList.toggle('off', K[cur].time === null); }
  bgA.set(a.bg); bgB.set(b.bg); bg.lerpColors(bgA, bgB, t); const hex = '#' + bg.getHexString(); if (R) R.renderer.setClearColor(bg, 1); else if (hex !== lastBg) { lastBg = hex; document.body.style.backgroundColor = hex; }
  // the clock of the story
  let ma = a.time !== null ? a.time : b.time, mb = b.time !== null ? b.time : a.time, mins = 390;
  if (ma !== null) { if (mb < ma) mb += 1440; mins = lerp(ma, mb, t); }
  if (clockEl) { const m5 = Math.round(mins / 5) * 5 % 1440, txt = String(Math.floor(m5 / 60)).padStart(2, '0') + ':' + String(m5 % 60).padStart(2, '0'); if (txt !== lastClock) { lastClock = txt; clockEl.textContent = txt; }
    const dp = lerp(dayAt(ia), dayAt(ib), t); if (Math.abs(dp - lastP) > .0015) { lastP = dp; fillEl.style.transform = `scaleX(${dp.toFixed(4)})`; knobEl.style.transform = `translateX(${(dp * trackW).toFixed(1)}px)`; } }
  if (!start) for (let i = Math.max(0, cur - 1); i <= Math.min(K.length - 1, cur + 1); i++) if (K[i].story) K[i].copy.style.translate = `0 ${(-(yc - centers[i]) / innerHeight * .16 * innerHeight).toFixed(1)}px`;
  if (alarmOn && alarmP < 1) { alarmP = Math.min(1, alarmP + dt * (alarmP < .3 ? .03 : .7 / 6));      // ten seconds of asking, then the call
    const left = Math.ceil(10 * (1 - alarmP / .3)), wt = alarmP < .15 ? `First question. Waiting for an answer… ${left}` : alarmP < .3 ? `Second question. Waiting for an answer… ${left}` : alarmP < .72 ? 'No reaction in 10 seconds. Calling Sophie…' : '';
    if (waitEl && wt !== waitTxt) { waitTxt = wt; waitEl.textContent = wt; waitEl.classList.toggle('on', !!wt); }
    if (alarmP >= 1) $$('[data-alarm]').forEach((bt) => bt.closest('.copy').classList.add('alarmed')); }
  if (R) draw(dt, a, b, t, cur, mins % 1440);
  requestAnimationFrame(frame);
}
function draw(dt, a, b, t, cur, mins) {
  const { vita, cam, H } = R, u = vita.userData, here = K[cur];
  weights(dt);
  ptr.x = lerp(ptr.x, ptr.tx, .08); ptr.y = lerp(ptr.y, ptr.ty, .08);
  const tall = cam.aspect < .9, wide = Math.min(1, cam.aspect / 1.6), mid = Math.sin(Math.PI * t), dir = Math.sign(b.x - a.x), ease = (r) => (start ? 1 : 1 - Math.exp(-dt * r));
  const N = R.N = lerp(R.N, lerp(a.dark ? 1 : 0, b.dark ? 1 : 0, t), ease(5));
  const la = Lt.alarm || 0, stAlarm = alarmSt = Math.max(la < .55 ? la / .55 * .3 : .3 + (la - .55) / .45 * .6, alarmP),      // scrolling walks through the same steps as the button
     wAlarm = (Wt.alarm || 0) * (1 - smooth(.72, .8, stAlarm)), resolved = here.fx.includes('alarm') && stAlarm > .72;

  // ----- the house: the camera of the story. Between two rooms it pulls back a little, as if it lifts over the wall.
  const va = a.view, vb = b.view, hopOver = a !== b && a.room >= 0 && b.room >= 0 && a.room !== b.room ? 1 : 0;
  const want = { sc: lerp(va.sc, vb.sc, t) * (1 - .3 * mid * hopOver), yaw: lerp(va.yaw, vb.yaw, t), tl: lerp(va.tl, vb.tl, t) - .12 * mid * hopOver, fx: lerp(va.fx, vb.fx, t) * wide, fy: lerp(va.fy, vb.fy, t), cx: lerp(va.cx, vb.cx, t), cz: lerp(va.cz, vb.cz, t), lift: 1 - lerp(a.roof, b.roof, t) };
  if (tall) { want.fx = Math.abs(want.fx) > 6 ? want.fx : 0; want.fy += 1.45; want.sc *= .6; }
  if (!R.S || start) R.S = want; else for (const k in want) R.S[k] = lerp(R.S[k], want[k], ease(k === 'lift' ? 3.2 : 6));
  const S = R.S, intro = smooth(0, 1.2, T);
  H.g.rotation.y = S.yaw + ptr.x * .09 + Math.sin(T * .3) * .02; H.tilt.rotation.x = S.tl + ptr.y * .04; H.tilt.scale.setScalar(Math.max(.0001, S.sc * (.6 + .4 * intro)));
  tmp.set(S.cx, .3, S.cz).applyAxisAngle(YAX, H.g.rotation.y).applyAxisAngle(XAX, H.tilt.rotation.x).multiplyScalar(S.sc);
  H.tilt.position.set(S.fx - tmp.x, S.fy - tmp.y + Math.sin(T * .8) * .025, -tmp.z); H.tilt.visible = Math.abs(S.fx) < 8.5;
  // the roof floats up and away; the walls on your side sink so you can look in
  const lift = S.lift, up = lift * lift * (3 - 2 * lift);
  H.roof.position.set(0, H.roofY + up * 2.6, -up * .6); H.roof.rotation.set(-up * .35, up * .5, up * .12); H.roof.scale.setScalar(Math.max(.0001, 1 - smooth(.55, 1, lift))); H.roof.visible = lift < .995;
  H.fwin.forEach((o) => { o.visible = up < .35; }); H.wFront.scale.y = lerp(1, .15, up); H.wLeft.scale.y = H.wRight.scale.y = lerp(1, .56, up);
  H.smoke.forEach((m, k) => { const q = (T * .2 + k / H.smoke.length) % 1; m.position.set(1.25 + Math.sin(q * 5 + k) * .12, 1.2 + q * 1.2, -.75); m.scale.setScalar(.6 + q * 1.5); m.material.opacity = Math.sin(Math.PI * q) * .8 * (1 - smooth(0, .3, lift)); });
  H.glass.color.set('#BFE6F5').lerp(cT.set('#FFD98A'), N); H.lamp.emissiveIntensity = .9 + N * 2.2;
  // Anna walks to the room of the chapter, through the doors, while the camera travels
  const ra = a.room >= 0 ? a.room : 2, rb = b.room >= 0 ? b.room : 2; let tx = SPOT[t < .5 ? ra : rb][0], tz = SPOT[t < .5 ? ra : rb][1], walk = 0, dirY = R.face;
  if (ra !== rb && t > 0 && t < 1) { const q = along(pathOf(ra, rb), t); tx = q[0]; tz = q[1]; dirY = q[2]; walk = mid; }
  else if (here.room >= 0) { const sp = H.spk[here.room].v.position; dirY = Math.atan2(sp.x - tx, sp.z - tz); }
  R.ax = lerp(R.ax, tx, ease(9)); R.az = lerp(R.az, tz, ease(9)); R.face += Math.atan2(Math.sin(dirY - R.face), Math.cos(dirY - R.face)) * ease(6);
  R.fall = lerp(R.fall, here.fx.includes('alarm') && (Wt.alarm || 0) > .4 ? 1 : 0, ease(5));
  H.anna.position.set(R.ax, H.floorY + Math.abs(Math.sin(T * 9)) * .035 * walk + R.fall * .1, R.az); H.anna.rotation.set(-R.fall * 1.45, R.face, Math.sin(T * 9) * .07 * walk);
  // the Vita of the room she is in answers
  H.spk.forEach((o, k) => { const on = here.room === k && mid < .35 ? 1 : 0; o.on = lerp(o.on, on, ease(4.5)); const m = o.v.userData, q = o.on, al = k === here.room ? wAlarm : 0, talking = q > .5 && T - sayAt < 2.6;
    const placed = lerp(1, smooth(.06 + k * .09, .16 + k * .09, SETUP.q), SETUP.w);      // moving in: one speaker after the other drops into its room
    o.v.scale.setScalar(.115 * Math.max(.001, pop(placed))); o.v.position.y = o.base + Math.max(0, Math.sin(T * 4)) * .025 * q + (1 - placed) * .9; o.v.rotation.y = Math.atan2(R.ax - o.v.position.x, R.az - o.v.position.z) * q + Math.sin(T * .8 + k) * .15 * (1 - q);
    m.orbMat.emissiveIntensity = .3 + q * 1.1 + al * (1.2 + Math.sin(T * 14) * .9); m.orb.scale.setScalar(1 + q * .35 + al * (.3 + Math.sin(T * 14) * .2)); m.halo.scale.setScalar(.9 + q * 1.1 + al * 1.4);
    m.leafL.rotation.z = .5 + q * .2 + Math.sin(T * 1.5 + k) * .05; m.leafR.rotation.z = -.5 - q * .2 - Math.sin(T * 1.5 + k) * .05;
    m.ringTo.set(al > .3 ? '#FF5B4D' : resolved && k === here.room ? '#5FE0A0' : COL.sun); m.ringMat.color.lerp(m.ringTo, .12); m.ringHalo.material.color.copy(m.ringMat.color); m.ringHalo.material.opacity = .16 + q * .2 + al * .35;
    m.smile.visible = !talking; m.mouth.visible = talking; const mo = Math.sin(T * 8.5) * .5 + .5; m.mouth.scale.set(1 - mo * .2, .35 + mo * .7, 1);
    H.floors[k].material.emissiveIntensity = q * (.22 + N * .5);
    o.rings.forEach((rg, j) => { const w = (T * (.5 + al) + j / 3) % 1; rg.scale.setScalar(.12 + w * .62); rg.material.opacity = (1 - w) * .7 * q; rg.material.color.set(al > .3 ? '#FF5B4D' : COL.coral); }); });
  H.tilt.updateMatrixWorld(true);

  // ----- Vita herself, at the start and the end of the day
  let x = lerp(a.x, b.x, t) * wide, y = lerp(a.y, b.y, t), z = lerp(a.z, b.z, t), s = lerp(a.s, b.s, t), ry = lerp(a.ry, b.ry, t);
  if (tall) { x = 0; y = lerp(a.ty !== null ? a.ty : a.y + 1.5, b.ty !== null ? b.ty : b.y + 1.5, t); s *= .6; ry *= .4; }
  if (!R.sm || start) R.sm = { x, y, z, s, ry }; else { const f = ease(10); R.sm.x = lerp(R.sm.x, x, f); R.sm.z = lerp(R.sm.z, z, f); R.sm.y = lerp(R.sm.y, y, f); R.sm.s = lerp(R.sm.s, s, f); R.sm.ry = lerp(R.sm.ry, ry, f); }
  x = R.sm.x; y = R.sm.y; z = R.sm.z; s = Math.max(.0001, R.sm.s); ry = R.sm.ry; vita.visible = s > .02;
  let hop = 0; if (u.hop > 0) { u.hop = Math.max(0, u.hop - dt * 1.9); hop = Math.sin(Math.PI * (1 - u.hop)) * u.hopH; if (!u.hop) u.hopH = 1; }
  const talk = vita.visible && here.room < 0 && sayEl && sayEl.classList.contains('on') && T - sayAt < 2.4 ? 1 : 0; u.talk = lerp(u.talk, talk, .08);
  const squash = 1 + Math.sin(T * 2) * .012 - hop * .05 + Math.sin(T * 11) * .008 * u.talk;
  vita.position.set(x, y + Math.sin(T * 1.3) * .07 * s + hop * .75 * s, z);
  vita.scale.set(s * (2 - squash), s * squash, s * (2 - squash)); vita.scale.multiplyScalar(.2 + .8 * (1 + Math.sin(intro * Math.PI) * .12) * intro);
  vita.rotation.set(ptr.y * .14 + Math.sin(T * .6) * .02, ry + ptr.x * .3, Math.sin(T * .9) * .035 - dir * mid * .14);
  u.face.rotation.y = ptr.x * .1; u.face.position.y = -ptr.y * .05;
  u.blink -= dt; const bl = u.blink < .12 ? .12 : 1; if (u.blink < 0) u.blink = 2.5 + Math.random() * 3; u.eyes.forEach((o) => { o.e.scale.y = lerp(o.e.scale.y, bl, .5); });
  const flap = hop * .4 + mid * .22 + u.talk * Math.sin(T * 9) * .05;
  u.leafL.rotation.z = .5 + Math.sin(T * 1.5) * .07 + flap; u.leafR.rotation.z = -.5 - Math.sin(T * 1.5 + .7) * .07 - flap; u.leafL.rotation.x = u.leafR.rotation.x = Math.sin(T * 1.1) * .06 - hop * .15;
  u.orb.position.y = 1.72 + Math.sin(T * 2.1) * .05 + hop * .2; u.orb.scale.setScalar(1 + u.talk * (.1 + Math.sin(T * 10) * .07)); u.orbMat.emissiveIntensity = .35 + u.talk * .5;
  u.halo.position.y = u.orb.position.y; u.halo.scale.setScalar(.95 + u.talk * .5); u.halo.material.opacity = .28 + u.talk * .2;
  u.ringHalo.material.opacity = .16 + u.talk * (.22 + Math.sin(T * 10) * .1);
  const mo = Math.sin(T * 8.5) * .5 + .5; u.smile.visible = u.talk < .35; u.mouth.visible = !u.smile.visible; u.mouth.scale.set(1 - mo * .2, .35 + mo * .7, 1);
  u.waves.forEach((m, i) => { const q = (T * .75 + i / 3) % 1; m.scale.setScalar(1 + q * .3); m.position.y = .2 + q * .5; m.material.opacity = (1 - q) * u.talk * .5; m.material.color.set(here.dark ? '#FFFFFF' : COL.forest); });
  moodHold = Math.max(0, moodHold - dt); if (!moodHold) setMood(vita, here.mood);
  R.shadow.position.set(vita.position.x, y - 1.13 * s, z); R.shadow.scale.set(s * (1 - hop * .3), s * .5 * (1 - hop * .3), 1); R.shadow.material.opacity = vita.visible ? .32 * (1 - N) : 0;

  // ----- the light of the hour
  R.renderer.toneMappingExposure = lerp(1.05, .62, N);
  R.key.intensity = lerp(2.2, 1.1, N); R.key.color.set('#FFFFFF').lerp(bg, .28 * (1 - N)).lerp(cT.set('#A9BDFF'), N); R.rim.intensity = lerp(1.4, 2.6, N);
  const dayU = (mins - 360) / 870, sunUp = dayU > 0 && dayU < 1 ? Math.sin(Math.PI * dayU) : 0, sv = clamp(sunUp * 3) * (1 - N);
  R.sun.position.set(lerp(-.5, 7.5, clamp(dayU)) * wide, -2.2 + sunUp * 5.2, -7); R.sun.material.opacity = sv; R.sun.visible = sv > .01; R.sunGlow.position.copy(R.sun.position); R.sunGlow.material.opacity = sv * .75; R.sunGlow.visible = R.sun.visible;

  // ----- what happens around the Vita who is speaking
  const c = { T, dt, tall, px: ptr.x, py: ptr.y, dim: N * .8, alarm: alarmSt };
  R.extra.forEach((e) => { const h = homeOf[e.name]; c.room = false; c.k = tall ? .5 : 1;
    if (h && h.room >= 0) { H.spk[h.room].v.getWorldPosition(P3); const off = OFF[e.name] || [0, 0]; c.room = true; c.vx = P3.x; c.vy = P3.y; c.vs = .4 * S.sc; c.x = P3.x + off[0] * (tall ? .4 : 1); c.y = P3.y + off[1] * (tall ? .7 : 1); c.s = 1; c.k = tall ? .4 : .6; c.inner = -1; c.floor = c.y - .7; }
    else if (h && h.s === 0) { c.room = e.name === 'family'; c.vx = S.fx; c.vy = S.fy + .6; c.vs = 1.5 * S.sc; c.x = S.fx + (c.room ? 1.5 : 0); c.y = S.fy + (c.room ? 1.75 : 0); c.s = 1; c.inner = -1; c.floor = S.fy - 1; }
    else { const hh = h && !tall ? h : null; c.x = hh ? hh.x * wide : x; c.y = hh ? hh.y : y; c.s = hh ? hh.s : s; c.inner = tall ? 1 : c.x >= 0 ? -1 : 1; c.vx = vita.position.x; c.vy = y; c.vs = s; c.floor = c.y - 1.13 * c.s; }
    c.long = Lt[e.name] || 0; e.run(Wt[e.name] || 0, Pt[e.name] || 0, c); });
  // where the speech bubble points
  if (here.room >= 0) { H.spk[here.room].v.getWorldPosition(P3); R.say.set(P3.x, P3.y + .27 * S.sc, P3.z); } else if (here.s === 0) R.say.set(S.fx - .5, S.fy + (here.fx.includes('family') ? 1.5 : 2.0) * S.sc, 0); else R.say.set(vita.position.x, vita.position.y + 1.72 * s, z);

  R.bokeh.forEach((sp) => { const d = sp.userData; sp.position.set(Math.cos(d.a + T * d.sp) * d.r - ptr.x * .7, d.y + Math.sin(T * d.sp * 3 + d.a) * .7 + ptr.y * .4, -6); sp.scale.setScalar(d.s); sp.material.opacity = .2 * (1 - N * .75); });
  R.acc += vita.visible ? dt * mid * 46 : 0; while (R.acc > 1) { R.acc -= 1; const sp = R.trail[R.tn++ % R.trail.length], d = sp.userData; d.life = 1; sp.position.set(vita.position.x + (Math.random() - .5) * 1.8 * s, vita.position.y + (Math.random() - .6) * 1.8 * s, z - .6 + Math.random() * .4); d.v.set(-dir * (.4 + Math.random() * .8), .3 + Math.random() * .7, 0); }
  R.trail.forEach((sp) => { const d = sp.userData; if (d.life <= 0) { sp.visible = false; return; } d.life -= dt * 1.3; sp.visible = true; sp.position.addScaledVector(d.v, dt); sp.scale.setScalar(.12 + Math.sin(Math.PI * clamp(d.life)) * .3); sp.material.opacity = clamp(d.life) * .9; });
  speak(dt, cur, mid);
  cam.position.x = ptr.x * .22; cam.position.y = -ptr.y * .14; cam.lookAt(0, 0, 0);
  R.tick = (R.tick || 0) + 1; if (H.tilt.visible && (start || R.tick % 2 === 0)) R.renderer.shadowMap.needsUpdate = true;
  R.renderer.render(R.scene, cam);
}
requestAnimationFrame((n) => { last = n; frame(n); document.documentElement.classList.add('ready'); });
