// The rehabilitation station: a seated patient and a robot arm on a trolley, doing one of six exercises.
// Each exercise says where the robot holds the patient at every moment of a repetition (the hand, or a cuff on the shin).
// The robot arm and the patient's limbs are solved from that point, so everything stays attached.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => { t = clamp(t); return t * t * (3 - 2 * t); };
const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const qs = new URLSearchParams(location.search), FREEZE = qs.get('t');      // ?ex=leg&t=.5 holds one moment still (for screenshots)

const canvas = $('#stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
let dpr = Math.min(devicePixelRatio, 1.75); renderer.setPixelRatio(dpr);
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene(); scene.background = new THREE.Color('#EEF4EC');
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
const cam = new THREE.PerspectiveCamera(30, 1, .1, 50);
const key = new THREE.DirectionalLight('#ffffff', 2.4); key.position.set(1.6, 3.4, 2.6); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 6; key.shadow.bias = -.0004; key.shadow.normalBias = .02;
Object.assign(key.shadow.camera, { left: -2, right: 2, top: 2.2, bottom: -1, near: .5, far: 9 }); scene.add(key);
const rim = new THREE.DirectionalLight('#CFE9D8', 1.2); rim.position.set(-3, 2, -3); scene.add(rim);

const mat = (color, o = {}) => new THREE.MeshPhysicalMaterial({ color, roughness: .42, clearcoat: .6, clearcoatRoughness: .3, ...o });
const glow = (color) => new THREE.MeshBasicMaterial({ color });
const M = { shell: mat('#F7F6F2', { roughness: .3, clearcoat: 1 }), joint: mat('#2B3330', { roughness: .35 }), accent: mat('#5F9E77'), coral: mat('#D9483F'), skin: mat('#F3CDAE', { clearcoat: .2, roughness: .6 }), hair: mat('#F2EFE9', { roughness: .7, clearcoat: 0 }),
  cardi: mat('#D9483F', { roughness: .7, clearcoat: 0, sheen: 1, sheenColor: new THREE.Color('#FF9E8F') }), trousers: mat('#3F5A70', { roughness: .8, clearcoat: 0 }), wood: mat('#D6AE82', { roughness: .6 }), cushion: mat('#A9D3B2', { roughness: .8, clearcoat: 0 }), shoe: mat('#F7F6F2', { roughness: .6 }), trolley: mat('#EDEFEA', { roughness: .5 }) };
const add = (m, parent = scene) => { m.castShadow = true; m.receiveShadow = true; parent.add(m); return m; };
const box = (w, h, d, m, x, y, z, parent, r = .03) => { const o = add(new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 4, Math.min(r, w / 2.1, h / 2.1, d / 2.1)), m), parent); o.position.set(x, y, z); return o; };
const cyl = (r1, r2, h, m, x, y, z, parent) => { const o = add(new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, 40), m), parent); o.position.set(x, y, z); return o; };
const ball = (r, m, x, y, z, parent) => { const o = add(new THREE.Mesh(new THREE.SphereGeometry(r, 36, 28), m), parent); o.position.set(x, y, z); return o; };
const capsule = (r, len, m, parent) => add(new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 12, 28), m), parent);
const YA = V(0, 1, 0), XA = V(1, 0, 0), tA = V(), tB = V(), tC = V(), tmpQ = new THREE.Quaternion();
const between = (mesh, a, b) => { mesh.position.copy(a).add(b).multiplyScalar(.5); mesh.quaternion.setFromUnitVectors(YA, tA.copy(b).sub(a).normalize()); };      // lay a limb between two joints
function elbow(out, s, w, l1, l2, pole) {      // where the middle joint of a two-part limb sits, bending towards the pole
  const dir = tA.copy(w).sub(s), d = clamp(dir.length(), Math.abs(l1 - l2) + .01, l1 + l2 - .002); dir.normalize();
  const a = (l1 * l1 - l2 * l2 + d * d) / (2 * d), h = Math.sqrt(Math.max(0, l1 * l1 - a * a)), perp = tB.copy(pole).addScaledVector(dir, -pole.dot(dir)).normalize();
  return out.copy(s).addScaledVector(dir, a).addScaledVector(perp, h);
}

// ---------- the room ----------
{ const f = new THREE.Mesh(new THREE.CircleGeometry(2.3, 96), new THREE.MeshStandardMaterial({ color: '#E3EDE0', roughness: .95 })); f.rotation.x = -Math.PI / 2; f.receiveShadow = true; scene.add(f);
  box(1.9, .02, 1.5, mat('#CFE3C8', { roughness: .9, clearcoat: 0 }), .42, .01, -.05, scene, .01).castShadow = false;
  [.1, -.1].forEach((z) => { box(.24, .006, .1, mat('#B5D2B4', { roughness: .9, clearcoat: 0 }), .47, .023, z, scene, .003).castShadow = false; }); }      // where the feet go, the same every session

// ---------- the chair and the patient ----------
box(.48, .06, .48, M.cushion, .02, .44, 0, scene, .03); box(.46, .03, .46, M.wood, .02, .4, 0, scene, .012);
box(.05, .52, .44, M.wood, -.2, .74, 0, scene, .02).rotation.z = .1; box(.04, .3, .38, M.cushion, -.165, .76, 0, scene, .02).rotation.z = .1;
[[-.18, -.2], [-.18, .2], [.22, -.2], [.22, .2]].forEach(([x, z]) => cyl(.02, .016, .4, M.wood, x, .2, z));
const HIP = V(0, .5, 0), torso = new THREE.Group(); torso.position.copy(HIP); scene.add(torso);
const head = new THREE.Group(); head.position.set(.03, .64, 0); torso.add(head);
{ const t = capsule(.135, .26, M.cardi, torso); t.position.set(.01, .25, 0); t.scale.set(.86, 1, 1.12); cyl(.045, .05, .07, M.skin, .02, .5, 0, torso);
  ball(.105, M.skin, 0, 0, 0, head); const hair = ball(.112, M.hair, -.025, .02, 0, head); hair.scale.set(1, .92, 1.02); ball(.05, M.hair, -.11, .08, 0, head);
  [-.042, .042].forEach((z) => ball(.012, M.joint, .098, .01, z, head)); ball(.016, M.skin, .105, -.015, 0, head).castShadow = false;
  const smile = add(new THREE.Mesh(new THREE.TorusGeometry(.02, .0035, 8, 20, Math.PI), mat('#B4584C', { clearcoat: 0 })), head); smile.position.set(.101, -.033, 0); smile.rotation.set(Math.PI, Math.PI / 2, 0); smile.castShadow = false; }
// legs: the left one rests; the right one can be lifted against the robot
const KNEE_R = V(.44, .52, .1), SHIN = .42, CUFF_AT = .24, ANK = V(), CUFFP = V();
{ const hip = V(.06, .52, -.09), knee = V(.44, .52, -.1), ank = V(.47, .1, -.1); between(capsule(.07, .38, M.trousers), hip, knee); between(capsule(.055, .36, M.trousers), knee, ank); box(.2, .07, .09, M.shoe, .52, .055, -.1, scene, .03); }
between(capsule(.07, .38, M.trousers), V(.06, .52, .09), KNEE_R);
const shinR = capsule(.055, .36, M.trousers), footR = new THREE.Group(); scene.add(footR); box(.2, .07, .09, M.shoe, .05, -.045, 0, footR, .03);
const cuff = add(new THREE.Mesh(new THREE.CylinderGeometry(.068, .068, .08, 36), M.accent));
const SH_R = V(.02, .455, .175), SH_L = V(.02, .455, -.175), UP = .29, FORE = .27;      // shoulders, measured from the hips
const mkArm = () => ({ up: capsule(.048, UP, M.cardi), fore: capsule(.04, FORE, M.cardi), hand: ball(.045, M.skin, 0, 0, 0), sh: ball(.062, M.cardi, 0, 0, 0) });
const armR = mkArm(), armL = mkArm(), REST_L = V(.3, .6, -.11), REST_R = V(.3, .6, .11), POLE_R = V(-.2, -1, .55), POLE_L = V(-.2, -1, -.55);

// ---------- the robot: a trolley that can be rolled into place, a column, two long links and a wrist ----------
const base = new THREE.Group(); scene.add(base); const BASE0 = V(.95, 0, -.36); base.position.copy(BASE0);
box(.5, .56, .5, M.trolley, 0, .34, 0, base, .05); box(.52, .03, .52, M.joint, 0, .635, 0, base, .012); box(.3, .012, .16, M.accent, -.255, .44, 0, base, .004).rotation.z = Math.PI / 2;
[[-.2, -.2], [-.2, .2], [.2, -.2], [.2, .2]].forEach(([x, z]) => { cyl(.045, .045, .04, M.joint, x, .045, z, base).rotation.x = Math.PI / 2; });
cyl(.1, .115, .05, M.joint, 0, .675, 0, base); cyl(.075, .085, .2, M.shell, 0, .8, 0, base); ball(.088, M.joint, 0, .9, 0, base);
const led = cyl(.079, .079, .016, glow('#5FE0A0'), 0, .715, 0, base); led.castShadow = false;
cyl(.04, .045, .03, mat('#F1C36A'), .17, .665, .17, base); cyl(.03, .034, .03, mat('#D9483F', { clearcoat: 1 }), .17, .69, .17, base);      // the stop button
const L1 = .44, L2 = .4, WR = .13, SHO = V();
const rob = { capS: cyl(.06, .06, .2, M.shell, 0, 0, 0), l1: capsule(.052, L1 - .1, M.shell), elb: ball(.074, M.joint, 0, 0, 0), capE: cyl(.05, .05, .17, M.shell, 0, 0, 0), l2: capsule(.045, L2 - .1, M.shell), wr: ball(.058, M.joint, 0, 0, 0),
  l3: capsule(.034, WR - .07, M.shell), flange: cyl(.05, .05, .022, M.joint, 0, 0, 0), ring: cyl(.052, .052, .008, glow('#5FE0A0'), 0, 0, 0), grip: capsule(.021, .1, M.coral), top: ball(.027, M.joint, 0, 0, 0) };
rob.ring.castShadow = false;
const POLE_ROB = V(0, 1, 0), E = V(), W = V(), U = V(), Nrm = V();

// ---------- what the exercise looks like in the air ----------
const TRAIL = 150, trailPos = new Float32Array(TRAIL * 3), trailGeo = new THREE.BufferGeometry(); trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: '#2E6B4F', transparent: true, opacity: .7 })); trail.frustumCulled = false; scene.add(trail); let trailN = 0;
const GN = 96, guidePos = new Float32Array(GN * 3), guideGeo = new THREE.BufferGeometry(); guideGeo.setAttribute('position', new THREE.BufferAttribute(guidePos, 3));
const guide = new THREE.Line(guideGeo, new THREE.LineDashedMaterial({ color: '#7E9189', dashSize: .025, gapSize: .018 })); guide.frustumCulled = false; scene.add(guide);
const ringGeo = new THREE.TorusGeometry(.07, .007, 10, 64);
const goal = new THREE.Mesh(ringGeo, glow('#2FB67A')); goal.rotation.y = Math.PI / 2; scene.add(goal);
const past = new THREE.Mesh(ringGeo, glow('#8FA39A')); past.rotation.y = Math.PI / 2; past.scale.setScalar(.8); scene.add(past);
const chase = new THREE.Mesh(new THREE.SphereGeometry(.03, 24, 20), glow('#F1C36A')); scene.add(chase);      // the dot to follow
const chaseHalo = new THREE.Mesh(new THREE.RingGeometry(.04, .052, 40), new THREE.MeshBasicMaterial({ color: '#F1C36A', transparent: true, opacity: .6, side: THREE.DoubleSide })); chaseHalo.rotation.y = Math.PI / 2; scene.add(chaseHalo);
const labels = [];
function label(color) { const c = document.createElement('canvas'); c.width = 512; c.height = 112; const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthTest: false, toneMapped: false })); sp.scale.set(.46, .1, 1); sp.renderOrder = 5; scene.add(sp);
  const o = { sp, text: '', color, draw() { const g = c.getContext('2d'); g.clearRect(0, 0, 512, 112); g.font = '600 46px Outfit, "Instrument Sans", system-ui, sans-serif'; const w = Math.min(492, g.measureText(o.text).width + 56);
    g.fillStyle = o.color; g.beginPath(); g.roundRect((512 - w) / 2, 14, w, 84, 42); g.fill(); g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(o.text, 256, 59); t.needsUpdate = true; }, set(tx) { if (tx !== o.text) { o.text = tx; o.draw(); } } };
  labels.push(o); return o; }
const goalL = label('#2E6B4F'), pastL = label('#7E9189'), liveL = label('#D9483F');
if (document.fonts) document.fonts.ready.then(() => labels.forEach((l) => l.draw()));

// ---------- the exercises ----------
// at(t) gives, for a moment t (0 to 1) of one repetition: where the robot holds the patient, how the body leans, the number that is measured,
// what the coach says, and what the robot is doing (state: 'ok' green, 'hold' amber, 'load' red).
const X0 = .33, Z0 = .2, SHW = V(.02, .955, .175);
const there = (t, a, b, c) => (t < a ? ease(t / a) : t < b ? 1 : t < c ? 1 - ease((t - b) / (c - b)) : 0);      // out, hold, back, rest
const EX = {
  reach: { name: 'Forward reach', why: 'Reaching for a cup, a shelf, a door handle', period: 5.4, label: 'Reach', unit: 'cm', delta: '+3 cm on last week', repsLab: 'repetitions', reps: 12, mode: 'helps when she slows', modeVal: '20%', modeLab: 'robot help', series: [31, 33, 36, 38, 41],
    note: 'Reach is up 3 cm in a week. She tires after about 9 repetitions: two sets of 8 may suit her better than one of 12.',
    marks: [{ p: [.74, .98, Z0], text: 'Goal 41 cm', ring: goal, dy: .16 }, { p: [X0 + .38, .978, Z0], text: 'Last week 38 cm', ring: past, dy: -.12 }], off: [0, .1, 0], span: .42,
    at(t) { const k = there(t, .42, .56, .92); return { x: lerp(X0, .74, k), y: lerp(.95, .98, k) + Math.sin(k * Math.PI) * .025, z: Z0, lean: k * .38, value: Math.round(k * 41), state: 'ok', hit: t >= .42 && t < .56,
      say: t < .42 ? 'Reach forward, nice and slow.' : t < .56 ? 'Hold… 41 centimetres. Three more than last week!' : t < .92 ? 'And back again. Well done, Anna.' : 'Ready? Once more.' }; } },
  stretch: { name: 'Assisted stretch', why: 'Loosening a stiff shoulder after surgery or bed rest', period: 9, label: 'Shoulder lift', unit: '°', delta: '+6° on last week', repsLab: 'stretches', reps: 5, mode: 'moves the arm for her', modeVal: '9 N', modeLab: 'stops at', series: [96, 101, 107, 112, 118],
    note: 'Passive shoulder lift reached 118°, up 6° in a week. Resistance was felt at the same point on all five stretches; no pain reported.',
    marks: [{ p: [.02 + .52 * Math.sin(2.13), .955 - .52 * Math.cos(2.13), Z0], text: 'Stops here: 118°', dy: .15, dx: .12 }], off: [0, 0, .07], span: .4,
    at(t) { const k = there(t, .4, .6, .93), a = lerp(.87, 2.13, k); return { x: SHW.x + .52 * Math.sin(a), y: SHW.y - .52 * Math.cos(a), z: Z0, lean: -.04 * k, value: Math.round(lerp(60, 118, k)), state: t >= .36 && t < .6 ? 'hold' : 'ok', look: .25 * k,
      say: t < .36 ? 'Let your arm go loose. I’ll lift it for you.' : t < .6 ? 'I feel some resistance, so we stop here. 118 degrees.' : t < .93 ? 'And slowly back down.' : 'Breathe out. One more in a moment.' }; } },
  circle: { name: 'Shoulder circles', why: 'Keeping the shoulder supple: dressing, combing hair', period: 4.6, label: 'Smoothness', unit: '%', delta: '+5% on last week', repsLab: 'circles', reps: 8, mode: 'follows her hand', modeVal: '26 cm', modeLab: 'circle width', series: [62, 70, 75, 81, 86],
    note: 'Circles are rounder and steadier than last week (86% smooth). The movement still catches at the top of the circle.', marks: [], off: [0, 0, 0], span: 1,
    at(t) { const a = t * Math.PI * 2; return { x: .55, y: .99 + Math.sin(a) * .13, z: Z0 + Math.cos(a) * .13, lean: .14, value: Math.round(86 + Math.sin(a * 3) * 2), state: 'ok', say: t < .5 ? 'Big, slow circles. I’ll follow you.' : 'Lovely and even. Keep going.' }; } },
  follow: { name: 'Follow the dot', why: 'Coordination and control: pouring, buttoning, writing', period: 7, label: 'Accuracy', unit: '%', delta: '+7% on last week', repsLab: 'rounds', reps: 4, mode: 'light as a feather', modeVal: '1.4 cm', modeLab: 'average miss', series: [61, 68, 74, 81, 88],
    note: 'She stays within 1.4 cm of the target on average (88%). Control is weakest when crossing from right to left.', marks: [], off: [0, 0, 0], span: 1, chase: true,
    path(t) { const a = t * Math.PI * 2; return [.55, .99 + Math.sin(a * 2) * .085, Z0 + Math.sin(a) * .18]; },
    at(t) { const p = this.path(t - .018), w = Math.sin(t * 40) * .006; return { x: p[0], y: p[1] + w, z: p[2] - w, lean: .14, value: Math.round(88 + Math.sin(t * 19) * 3), state: 'ok', say: t < .5 ? 'Follow the yellow dot with your hand.' : 'Right on it! Stay with the dot.' }; } },
  push: { name: 'Strength test', why: 'Pushing up from a chair, opening a heavy door', period: 6.4, label: 'Push force', unit: 'N', delta: '+5 N on last week', repsLab: 'attempts', reps: 3, mode: 'holds completely still', modeVal: '38 N', modeLab: 'best today', series: [24, 27, 30, 33, 38],
    note: 'Peak push force 38 N, up from 33 N. Left and right have not been compared yet: test the left arm next session.', marks: [], off: [0, 0, 0], span: 1, noTrail: true,
    at(t) { const f = t < .12 ? 0 : t < .45 ? ease((t - .12) / .33) : t < .72 ? 1 : t < .88 ? 1 - ease((t - .72) / .16) : 0, shake = f * Math.sin(t * 190) * .0025; return { x: .56 + f * .012 + shake, y: .97, z: Z0, lean: .16 + f * .09, value: Math.round(f * 38 + (f === 1 ? Math.sin(t * 60) * .6 : 0)), state: f > .05 ? 'load' : 'ok', live: f > .03 ? 'N' : '',
      say: t < .12 ? 'The handle stays still. Get ready to push.' : t < .45 ? 'Push against me, as hard as feels comfortable.' : t < .72 ? 'Hold it… 38 newtons. Stronger than last week!' : 'And relax. Very good.' }; } },
  leg: { name: 'Knee extension', why: 'Standing up, climbing stairs, steadier walking', period: 6, label: 'Knee angle', unit: '°', delta: '+7° on last week', repsLab: 'repetitions', reps: 10, mode: 'adds gentle resistance', modeVal: '1.5 kg', modeLab: 'resistance', series: [48, 55, 60, 65, 72], leg: true, base: [.8, -.42],
    note: 'Right knee now extends to 72° against 1.5 kg. Movement is steady going up, quicker coming down: cue her to lower slowly.',
    marks: [{ p: [KNEE_R.x + CUFF_AT * Math.sin(1.25), KNEE_R.y - CUFF_AT * Math.cos(1.25), .1], text: 'Goal 72°', dy: .2, dx: .14 }], off: [0, 0, .09], span: .4,
    at(t) { const k = there(t, .4, .55, .92), th = lerp(.15, 1.25, k); return { x: KNEE_R.x + CUFF_AT * Math.sin(th), y: KNEE_R.y - CUFF_AT * Math.cos(th), z: .1, th, lean: -.03 * k, value: Math.round(lerp(8, 72, k)), state: k > .05 && t < .55 ? 'load' : 'ok', look: -.3,
      say: t < .4 ? 'Lift your foot and straighten the knee.' : t < .55 ? 'Hold… 72 degrees. That’s your best yet!' : t < .92 ? 'Lower it slowly. Slowly…' : 'Good. Rest a second.' }; } },
};
const ORDER = ['reach', 'stretch', 'circle', 'follow', 'push', 'leg'];
let ex = EX[qs.get('ex')] ? qs.get('ex') : 'reach', exT = 0, paused = false, tour = !FREEZE && !qs.get('ex'), lastSay = '', lastVal = -1, lastReps = -1, sayAt = -1, snap = true, wasLeg = false;
const el = { val: $('#mVal'), unit: $('#mUnit'), lab: $('#mLab'), delta: $('#mDelta'), reps: $('#reps'), repsLab: $('#repsLab'), help: $('#help'), helpLab: $('#helpLab'), sess: $('#sess'), say: $('#say'), line: $('#line'), dots: $('#dots'), mode: $('#mode'), note: $('#note'), list: $('#list'), tour: $('#tour') };
el.list.innerHTML = ORDER.map((k) => `<button type="button" data-ex="${k}" aria-pressed="false"><b>${EX[k].name}</b><span>${EX[k].why}</span></button>`).join('');
function choose(name) { ex = name; exT = 0; trailN = 0; lastVal = lastReps = -1; const d = EX[name];
  $$('[data-ex]').forEach((b) => { const on = b.dataset.ex === name; b.setAttribute('aria-pressed', on); if (on && b.scrollIntoView && innerWidth < 860) b.scrollIntoView({ inline: 'center', block: 'nearest' }); });
  el.unit.textContent = d.unit; el.lab.textContent = d.label; el.delta.textContent = d.delta; el.repsLab.textContent = d.repsLab; el.help.textContent = d.modeVal; el.helpLab.textContent = d.modeLab; el.sess.textContent = 'Session 5 · ' + d.name.toLowerCase(); el.mode.textContent = d.mode; el.note.textContent = d.note;
  const lo = Math.min(...d.series) - 4, hi = Math.max(...d.series) + 2, pts = d.series.map((v, i) => [8 + i * 60, 66 - (v - lo) / (hi - lo) * 58]);
  el.line.setAttribute('points', pts.map((p) => p.join(',')).join(' ')); el.dots.innerHTML = pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="${i === 4 ? 6 : 4}" fill="${i === 4 ? '#D9483F' : '#5F9E77'}"/><text x="${p[0]}" y="${p[1] - 11}" text-anchor="middle" font-size="12" font-weight="600" fill="#55645E">${d.series[i]}</text>`).join('');
  // the dashed line of the movement, and the marks along it
  for (let i = 0; i < GN; i++) { const u = i / (GN - 1) * d.span; let p; if (d.path) p = d.path(u); else { const s = d.at(u); p = [s.x, s.y, s.z]; } guidePos[i * 3] = p[0] + d.off[0]; guidePos[i * 3 + 1] = p[1] + d.off[1]; guidePos[i * 3 + 2] = p[2] + d.off[2]; }
  guideGeo.attributes.position.needsUpdate = true; guide.computeLineDistances(); guide.visible = !d.noTrail; trail.visible = !d.noTrail && !d.leg;
  goal.visible = past.visible = goalL.sp.visible = pastL.sp.visible = false;
  d.marks.forEach((m, i) => { const L = i ? pastL : goalL; L.set(m.text); L.sp.visible = true; L.sp.position.set(m.p[0] + (m.dx || 0), m.p[1] + m.dy, m.p[2]); if (m.ring) { m.ring.visible = true; m.ring.position.set(m.p[0], m.p[1], m.p[2]); } });
  chase.visible = chaseHalo.visible = !!d.chase; cuff.visible = !!d.leg; rob.grip.visible = rob.top.visible = !d.leg; }
const setTour = (on) => { tour = on; el.tour.textContent = on ? 'Tour: on' : 'Tour: off'; el.tour.setAttribute('aria-pressed', on); };
el.list.addEventListener('click', (e) => { const b = e.target.closest('[data-ex]'); if (!b) return; setTour(false); choose(b.dataset.ex); });
el.tour.addEventListener('click', () => setTour(!tour)); setTour(tour);
$('#pause').addEventListener('click', (e) => { paused = !paused; e.currentTarget.textContent = paused ? 'Play' : 'Pause'; });
choose(ex);

// ---------- looking around: drag to turn, and it drifts a little by itself ----------
const view = { az: .62, el: .2, taz: .62, tel: .2, dist: 4.6, drag: false, x: 0, y: 0, idle: 0 };
canvas.addEventListener('pointerdown', (e) => { view.drag = true; view.x = e.clientX; view.y = e.clientY; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointermove', (e) => { if (!view.drag) return; view.taz -= (e.clientX - view.x) * .006; view.tel = clamp(view.tel + (e.clientY - view.y) * .004, .04, .9); view.x = e.clientX; view.y = e.clientY; view.idle = 0; });
addEventListener('pointerup', () => { view.drag = false; });
canvas.addEventListener('wheel', (e) => { e.preventDefault(); view.dist = clamp(view.dist + e.deltaY * .002, 3, 6.5); }, { passive: false });
const size = () => { const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); }; size(); addEventListener('resize', size);

// ---------- every frame ----------
const H = V(), Ht = V(), S = V(), Eh = V(), look = V(), sm = { lean: 0, th: .07, look: 0 }, COLS = { ok: '#5FE0A0', hold: '#F5B43C', load: '#FF7A5E' }, cT = new THREE.Color();
let last = performance.now(), T = 0, fAcc = 0, fN = 0;
function frame(now) {
  requestAnimationFrame(frame); if (document.hidden) { last = now; return; }
  const raw = (now - last) / 1000, dt = Math.min(.05, raw); last = now; T += dt; if (!paused) exT += dt;
  if (T > 2.5 && !FREEZE) { fAcc += raw; if (++fN >= 45) { const avg = fAcc / fN; fAcc = fN = 0; if (avg > 1 / 44 && dpr > 1) { dpr = Math.max(1, dpr - .25); renderer.setPixelRatio(dpr); } } }
  let d = EX[ex]; if (tour && !paused && exT > d.period * (d.period > 8 ? 1 : 2)) { choose(ORDER[(ORDER.indexOf(ex) + 1) % ORDER.length]); d = EX[ex]; }
  const t = FREEZE ? +FREEZE : (exT / d.period) % 1, rep = FREEZE ? 2 : Math.floor(exT / d.period) % d.reps + 1, s = d.at(t), f = (r) => (FREEZE || snap ? 1 : 1 - Math.exp(-dt * r));
  const isLeg = !!d.leg, travel = isLeg !== wasLeg || exT < .6 ? 5 : 18; wasLeg = isLeg;      // changing exercise: the arm travels to its new place
  Ht.set(s.x, s.y, s.z); H.lerp(Ht, f(travel));
  tA.set(d.base ? d.base[0] : BASE0.x, 0, d.base ? d.base[1] : BASE0.z); base.position.lerp(tA, f(3.5)); SHO.set(base.position.x, .9, base.position.z);

  // the patient: the body leans into the movement, the head follows the hand
  sm.lean = lerp(sm.lean, s.lean, f(9)); sm.look = lerp(sm.look, s.look || 0, f(4)); torso.rotation.z = -sm.lean; torso.position.y = HIP.y + Math.sin(T * 1.4) * .003; head.rotation.z = sm.look; torso.updateMatrixWorld(true);
  sm.th = lerp(sm.th, isLeg ? s.th : .07, f(isLeg ? 16 : 5)); ANK.set(KNEE_R.x + SHIN * Math.sin(sm.th), KNEE_R.y - SHIN * Math.cos(sm.th), .1); CUFFP.set(KNEE_R.x + CUFF_AT * Math.sin(sm.th), KNEE_R.y - CUFF_AT * Math.cos(sm.th), .1);
  between(shinR, KNEE_R, ANK); footR.position.copy(ANK); footR.rotation.z = sm.th; cuff.position.copy(CUFFP); cuff.quaternion.copy(shinR.quaternion);
  const handAt = isLeg ? REST_R : H;
  S.copy(SH_R); torso.localToWorld(S); elbow(Eh, S, handAt, UP, FORE, POLE_R); tC.copy(handAt).sub(Eh).normalize(); armR.hand.position.copy(Eh).addScaledVector(tC, FORE - .01); if (!isLeg) armR.hand.position.x -= .012; armR.sh.position.copy(S);
  between(armR.up, S, Eh); between(armR.fore, Eh, armR.hand.position);
  S.copy(SH_L); torso.localToWorld(S); elbow(Eh, S, REST_L, UP, FORE, POLE_L); armL.sh.position.copy(S); armL.hand.position.copy(REST_L); between(armL.up, S, Eh); between(armL.fore, Eh, REST_L);

  // the robot: its wrist sits just beside the point it holds, on its own side; shoulder and elbow follow from that
  const P = isLeg && travel > 10 ? CUFFP : H, gap = isLeg ? .07 : 0; U.set(SHO.x - P.x, 0, SHO.z - P.z).normalize(); W.copy(P).addScaledVector(U, WR + gap); elbow(E, SHO, W, L1, L2, POLE_ROB);
  Nrm.copy(W).sub(SHO).cross(POLE_ROB).normalize();      // the axis the shoulder and the elbow turn about
  between(rob.l1, SHO, E); between(rob.l2, E, W); rob.elb.position.copy(E); rob.wr.position.copy(W);
  rob.capS.position.copy(SHO); rob.capS.quaternion.setFromUnitVectors(YA, Nrm); rob.capE.position.copy(E); rob.capE.quaternion.setFromUnitVectors(YA, Nrm);
  between(rob.l3, W, tA.copy(P).addScaledVector(U, .04 + gap)); rob.flange.position.copy(P).addScaledVector(U, .034 + gap); rob.flange.quaternion.setFromUnitVectors(YA, U); rob.ring.position.copy(P).addScaledVector(U, .048 + gap); rob.ring.quaternion.copy(rob.flange.quaternion);
  rob.grip.position.copy(P); rob.top.position.set(P.x, P.y + .078, P.z);
  const pulse = .75 + Math.sin(T * 3) * .25; rob.ring.material.color.lerp(cT.set(COLS[s.state]), f(8)); led.material.color.copy(rob.ring.material.color).multiplyScalar(pulse);

  // the path of the hand, the goal, the dot to follow, the live number
  if (trail.visible && !paused) { if (trailN < TRAIL) trailN++; trailPos.copyWithin(3, 0, (trailN - 1) * 3); trailPos[0] = H.x + d.off[0]; trailPos[1] = H.y + d.off[1]; trailPos[2] = H.z + d.off[2]; trailGeo.setDrawRange(0, trailN); trailGeo.attributes.position.needsUpdate = true; }
  if (goal.visible) { goal.scale.setScalar(1 + Math.sin(T * 4) * .05 + (s.hit ? .25 : 0)); goal.material.color.set(s.hit ? '#2FB67A' : '#5F9E77'); }
  if (d.chase) { const p = d.path(t); chase.position.set(p[0] + .07, p[1] + .02, p[2] + .05); chaseHalo.position.copy(chase.position); chaseHalo.scale.setScalar(1 + Math.sin(T * 5) * .15); }
  liveL.sp.visible = !!s.live; if (s.live) { liveL.sp.position.set(H.x + .12, H.y + .2, H.z); liveL.set(s.value + ' ' + s.live); }

  // the numbers on the screen
  if (s.value !== lastVal) { lastVal = s.value; el.val.textContent = s.value; }
  if (rep !== lastReps) { lastReps = rep; el.reps.textContent = rep + ' / ' + d.reps; }
  if (s.say !== lastSay && T - sayAt > .3) { lastSay = s.say; sayAt = T; el.say.style.opacity = 0; setTimeout(() => { el.say.textContent = s.say; el.say.style.opacity = 1; }, FREEZE ? 0 : 180); }

  // the camera
  view.idle += dt; const drift = FREEZE ? 0 : Math.sin(T * .22) * .1 * clamp((view.idle - 1.5) / 2); view.az = lerp(view.az, view.taz + drift, f(6)); view.el = lerp(view.el, view.tel, f(6));
  const narrow = cam.aspect < 1, dist = view.dist * (narrow ? 1.5 : 1); look.set(narrow ? .42 : .5, narrow ? .62 : .74, -.05);
  cam.position.set(look.x + Math.sin(view.az) * Math.cos(view.el) * dist, look.y + Math.sin(view.el) * dist, look.z + Math.cos(view.az) * Math.cos(view.el) * dist); cam.lookAt(look);
  if (!narrow) cam.setViewOffset(innerWidth, innerHeight, innerWidth * -.03, innerHeight * -.02, innerWidth, innerHeight); else cam.clearViewOffset();
  snap = false; renderer.render(scene, cam);
}
requestAnimationFrame((n) => { last = n; frame(n); });
