// The science page. The rehabilitation station: a seated patient and a robot arm on a trolley, doing one of six exercises.
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

if (FREEZE) document.documentElement.classList.add('still'); const BARE = qs.has('bare'); if (BARE) document.documentElement.classList.add('bare');      // ?bare hides the page and centres the scene (for a clean picture)
const canvas = $('#stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
let dpr = Math.min(devicePixelRatio, 1.75); renderer.setPixelRatio(dpr);
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene(); scene.background = new THREE.Color('#ECF3F4');
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
const cam = new THREE.PerspectiveCamera(30, 1, .1, 50);
const key = new THREE.DirectionalLight('#ffffff', 2.4); key.position.set(1.6, 3.4, 2.6); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 6; key.shadow.bias = -.0004; key.shadow.normalBias = .02;
Object.assign(key.shadow.camera, { left: -2, right: 2, top: 2.2, bottom: -1, near: .5, far: 9 }); scene.add(key);
const rim = new THREE.DirectionalLight('#CFE5E9', 1.2); rim.position.set(-3, 2, -3); scene.add(rim);

const mat = (color, o = {}) => new THREE.MeshPhysicalMaterial({ color, roughness: .42, clearcoat: .6, clearcoatRoughness: .3, ...o });
const glow = (color) => new THREE.MeshBasicMaterial({ color });
const M = { shell: mat('#F3F5F6', { roughness: .3, clearcoat: 1 }), joint: mat('#2B3133', { roughness: .35 }), arm: mat('#E6E9EC', { roughness: .34, metalness: .12, clearcoat: .85, clearcoatRoughness: .22 }), cap: mat('#CDD2D6', { roughness: .45, metalness: .2 }), accent: mat('#58C4D4'), coral: mat('#D9483F'), skin: mat('#F3CDAE', { clearcoat: .2, roughness: .6 }), hair: mat('#EBEEF0', { roughness: .7, clearcoat: 0 }),
  cardi: mat('#D9483F', { roughness: .7, clearcoat: 0, sheen: 1, sheenColor: new THREE.Color('#FF9E8F') }), trousers: mat('#3F5A70', { roughness: .8, clearcoat: 0 }), wood: mat('#D6AE82', { roughness: .6 }), cushion: mat('#A9CDD3', { roughness: .8, clearcoat: 0 }), shoe: mat('#F3F5F6', { roughness: .6 }), trolley: mat('#EAEFEF', { roughness: .5 }) };
// the Vita logo, used on the robot arm, the trolley and the banner
const LOGO_BG = '#0A4552', logoImg = new Image(), logoWait = []; logoImg.onload = () => logoWait.forEach((f) => f()); logoImg.src = new URL('./vita-logo.png', import.meta.url).href;
const logoReady = () => logoImg.complete && logoImg.naturalWidth > 0;
function logoTex(w, h, draw) { const c = document.createElement('canvas'); c.width = w; c.height = h; const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  const paint = () => { const x = c.getContext('2d'); x.fillStyle = LOGO_BG; x.fillRect(0, 0, w, h); if (logoReady()) draw(x); t.needsUpdate = true; }; paint(); logoWait.push(paint); return t; }
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
{ const f = new THREE.Mesh(new THREE.CircleGeometry(2.3, 96), new THREE.MeshStandardMaterial({ color: '#E0ECED', roughness: .95 })); f.rotation.x = -Math.PI / 2; f.receiveShadow = true; scene.add(f);
  box(1.9, .02, 1.5, mat('#C8E1E3', { roughness: .9, clearcoat: 0 }), .42, .01, -.05, scene, .01).castShadow = false;
  [.1, -.1].forEach((z) => { box(.24, .006, .1, mat('#B4CFD2', { roughness: .9, clearcoat: 0 }), .47, .023, z, scene, .003).castShadow = false; }); }      // where the feet go, the same every session

// ---------- the chair and the patient ----------
box(.48, .06, .48, M.cushion, .02, .44, 0, scene, .03); box(.46, .03, .46, M.wood, .02, .4, 0, scene, .012);
box(.05, .52, .44, M.wood, -.2, .74, 0, scene, .02).rotation.z = .1; box(.04, .3, .38, M.cushion, -.165, .76, 0, scene, .02).rotation.z = .1;
[[-.18, -.2], [-.18, .2], [.22, -.2], [.22, .2]].forEach(([x, z]) => cyl(.02, .016, .4, M.wood, x, .2, z));
const AN0 = scene.children.length;
const HIP = V(0, .5, 0), torso = new THREE.Group(); torso.position.copy(HIP); scene.add(torso);
const head = new THREE.Group(); head.position.set(.03, .64, 0); torso.add(head);
const body = {}; { const t = body.torso = capsule(.135, .26, M.cardi, torso); t.position.set(.01, .25, 0); t.scale.set(.86, 1, 1.12); cyl(.045, .05, .07, M.skin, .02, .5, 0, torso);
  body.head = ball(.105, M.skin, 0, 0, 0, head); const hair = ball(.112, M.hair, -.025, .02, 0, head); hair.scale.set(1, .92, 1.02); ball(.05, M.hair, -.11, .08, 0, head);
  [-.042, .042].forEach((z) => ball(.012, M.joint, .098, .01, z, head)); ball(.016, M.skin, .105, -.015, 0, head).castShadow = false;
  const smile = add(new THREE.Mesh(new THREE.TorusGeometry(.02, .0035, 8, 20, Math.PI), mat('#B4584C', { clearcoat: 0 })), head); smile.position.set(.101, -.033, 0); smile.rotation.set(Math.PI, Math.PI / 2, 0); smile.castShadow = false; }
// Anna in detail: glasses, brows, cheeks, ears with pearl earrings, fuller hair, a collar and buttons, hips and knees
{ const gold = mat('#B98A3E', { metalness: .85, roughness: .28 }), pearl = mat('#FBF7EE', { roughness: .18, clearcoat: 1 }), blush = new THREE.MeshStandardMaterial({ color: '#F08F86', transparent: true, opacity: .5, roughness: .9 }), white = glow('#ffffff'), lens = new THREE.MeshPhysicalMaterial({ color: '#DDEFF5', transparent: true, opacity: .22, roughness: .05 });
  const rod = (a, b, r, m) => { const o = add(new THREE.Mesh(new THREE.CylinderGeometry(r, r, a.distanceTo(b), 12), m), head); between(o, a, b); o.castShadow = false; return o; };
  [-1, 1].forEach((sd) => { const z = sd * .043;
    const rim = add(new THREE.Mesh(new THREE.TorusGeometry(.028, .0034, 10, 40), gold), head); rim.position.set(.101, .008, z); rim.rotation.y = Math.PI / 2; rim.castShadow = false;
    const gl = add(new THREE.Mesh(new THREE.CircleGeometry(.027, 32), lens), head); gl.position.set(.101, .008, z); gl.rotation.y = Math.PI / 2; gl.castShadow = false;
    rod(V(.1, .012, sd * .071), V(.0, .014, sd * .104), .0026, gold);                                   // the arm of the glasses
    ball(.0042, white, .1088, .0148, z + .004, head).castShadow = false;                                  // a sparkle in the eye
    const brow = capsule(.0048, .022, M.hair, head); brow.position.set(.0945, .047, z); brow.rotation.x = Math.PI / 2 + sd * .22; brow.castShadow = false;
    const ch = ball(.021, blush, .082, -.03, sd * .066, head); ch.scale.set(.5, .8, 1); ch.castShadow = false;
    const ear = ball(.024, M.skin, .0, -.004, sd * .102, head); ear.scale.set(.62, 1, .5); ball(.0085, pearl, .002, -.036, sd * .106, head);
    ball(.06, M.hair, -.005, .05, sd * .074, head);                                                       // hair over the ears
    ball(.036, M.hair, .05, .092, sd * .05, head); });
  rod(V(.101, .012, -.016), V(.101, .012, .016), .003, gold); ball(.04, M.hair, .058, .098, 0, head); ball(.07, M.hair, -.01, .085, 0, head); ball(.034, M.hair, -.15, .1, 0, head);
  const collar = add(new THREE.Mesh(new THREE.TorusGeometry(.056, .017, 14, 40), M.shell), torso); collar.position.set(.022, .487, 0); collar.rotation.x = Math.PI / 2; collar.scale.set(1, 1.12, 1);
  [.385, .305, .225, .145].forEach((y) => ball(.0105, pearl, .1265, y, 0, torso));
  const hem = add(new THREE.Mesh(new THREE.TorusGeometry(.125, .016, 12, 48), M.cardi), torso); hem.position.set(.01, .04, 0); hem.rotation.x = Math.PI / 2; hem.scale.set(.88, 1.14, 1);
  const pelvis = ball(.126, M.trousers, .012, .5, 0); pelvis.scale.set(1.02, .62, 1.24);
  ball(.066, M.trousers, .44, .52, -.1); ball(.066, M.trousers, .44, .52, .1); ball(.05, M.shell, .47, .1, -.1).scale.set(1, .9, 1); box(.214, .02, .098, M.accent, .52, .014, -.1, scene, .008); }
// legs: the left one rests; the right one can be lifted against the robot
const KNEE_R = V(.44, .52, .1), SHIN = .42, CUFF_AT = .24, ANK = V(), CUFFP = V();
{ const hip = V(.06, .52, -.09), knee = V(.44, .52, -.1), ank = V(.47, .1, -.1); between(capsule(.07, .38, M.trousers), hip, knee); between(capsule(.055, .36, M.trousers), knee, ank); box(.2, .07, .09, M.shoe, .52, .055, -.1, scene, .03); }
body.thigh = capsule(.07, .38, M.trousers); between(body.thigh, V(.06, .52, .09), KNEE_R);
const shinR = capsule(.055, .36, M.trousers), footR = new THREE.Group(); scene.add(footR); box(.2, .07, .09, M.shoe, .05, -.045, 0, footR, .03); box(.214, .02, .098, M.accent, .05, -.084, 0, footR, .008); ball(.05, M.shell, 0, 0, 0, footR).scale.set(1, .9, 1);
const cuff = add(new THREE.Mesh(new THREE.CylinderGeometry(.068, .068, .08, 36), M.accent));
const SH_R = V(.02, .455, .175), SH_L = V(.02, .455, -.175), UP = .29, FORE = .27;      // shoulders, measured from the hips
const mkArm = () => ({ up: capsule(.048, UP, M.cardi), fore: capsule(.04, FORE, M.cardi), hand: ball(.045, M.skin, 0, 0, 0), sh: ball(.062, M.cardi, 0, 0, 0), el: ball(.0485, M.cardi, 0, 0, 0), cf: cyl(.0445, .0445, .03, M.shell, 0, 0, 0) });
// her fingers, closed around the handle: four fingers wrap one way, the thumb the other
const gripHand = new THREE.Group(); scene.add(gripHand);
{ const arc = (R, tube, y, from, len) => { const m = add(new THREE.Mesh(new THREE.TorusGeometry(R, tube, 12, 28, len), M.skin), gripHand); m.rotation.set(Math.PI / 2, 0, from); m.position.y = y; const a = from + len; ball(tube, M.skin, R * Math.cos(a), y, R * Math.sin(a), gripHand); ball(tube, M.skin, R * Math.cos(from), y, R * Math.sin(from), gripHand); };
  [.031, .0105, -.01, -.0295].forEach((y, i) => arc(.0295, i === 3 ? .0085 : .0098, y, 2.75, 3.75 - (i === 3 ? .25 : 0)));
  arc(.0305, .0108, .046, .55, 2.5); }
const armR = mkArm(), armL = mkArm(), REST_L = V(.3, .6, -.11), REST_R = V(.3, .6, .11), POLE_R = V(-.2, -1, .55), POLE_L = V(-.2, -1, -.55);

const AN1 = scene.children.length;
// ---------- the robot: a trolley that can be rolled into place, a column, two long links and a wrist ----------
const base = new THREE.Group(); scene.add(base); const BASE0 = V(.95, 0, -.36); base.position.copy(BASE0);
box(.5, .56, .5, M.trolley, 0, .34, 0, base, .05); box(.52, .03, .52, M.joint, 0, .635, 0, base, .012); box(.3, .012, .16, M.accent, -.255, .44, 0, base, .004).rotation.z = Math.PI / 2;
[[-.2, -.2], [-.2, .2], [.2, -.2], [.2, .2]].forEach(([x, z]) => { cyl(.045, .045, .04, M.joint, x, .045, z, base).rotation.x = Math.PI / 2; });
cyl(.1, .115, .05, M.joint, 0, .675, 0, base); cyl(.066, .098, .2, M.arm, 0, .8, 0, base); cyl(.0985, .0985, .03, M.arm, 0, .705, 0, base);
const led = cyl(.079, .079, .016, glow('#58E6F2'), 0, .715, 0, base); led.castShadow = false;
cyl(.04, .045, .03, mat('#F1C36A'), .17, .665, -.17, base); const stopBtn = cyl(.03, .034, .03, mat('#D9483F', { clearcoat: 1 }), .17, .69, -.17, base), stopHalo = add(new THREE.Mesh(new THREE.TorusGeometry(.062, .007, 8, 40), glow('#FF4A3A')), base); stopHalo.rotation.x = Math.PI / 2; stopHalo.position.set(.17, .655, -.17); stopHalo.castShadow = false; stopHalo.visible = false;      // the stop button
const L1 = .44, L2 = .4, WR = .13, SHO = V();
// modelled on the real arm: silver-white shells, drum joints with the links mounted on their sides, thin cyan light rings at the seams
const OFF = .058, rob = { capS: capsule(.068, .085, M.arm), l1: capsule(.056, L1 - .1, M.arm), elb: ball(.05, M.arm, 0, 0, 0), capE: capsule(.062, .08, M.arm), l2: capsule(.049, L2 - .1, M.arm), wr: ball(.04, M.arm, 0, 0, 0), capW: capsule(.05, .034, M.arm),
  l3: capsule(.039, WR - .07, M.arm), flange: cyl(.046, .046, .022, M.cap, 0, 0, 0), ring: cyl(.052, .052, .008, glow('#58E6F2'), 0, 0, 0), grip: capsule(.021, .1, M.coral), top: ball(.027, M.joint, 0, 0, 0) };
rob.ring.castShadow = false;
{ const cy = glow('#58E6F2'), seam = (parent, r, y) => { const e = add(new THREE.Mesh(new THREE.TorusGeometry(r, .0028, 8, 56), cy), parent); e.rotation.x = Math.PI / 2; e.position.y = y; e.castShadow = false; };
  const disc = (parent, r, y) => { const d = cyl(r, r, .004, M.cap, 0, y, 0, parent); d.castShadow = false; [0, 1, 2, 3, 4, 5].forEach((i) => { const b = ball(.0032, M.joint, Math.cos(i * 1.047) * r * .78, y + Math.sign(y) * .002, Math.sin(i * 1.047) * r * .78, parent); b.castShadow = false; }); };
  seam(rob.capS, .0685, -.012); seam(rob.capE, .0625, .012); seam(rob.capW, .0505, 0); seam(rob.l2, .0495, -.1); seam(rob.l2, .0495, .1); seam(rob.l3, .0395, 0); seam(base, .083, .83);
  disc(rob.capS, .04, .1085); disc(rob.capS, .04, -.1085); disc(rob.capE, .036, .1); disc(rob.capE, .036, -.1); disc(rob.capW, .028, .065); disc(rob.capW, .028, -.065); }
{ const t = logoTex(1024, 730, (x) => { const w = 610, h = w * logoImg.naturalHeight / logoImg.naturalWidth; for (let i = 0; i < 3; i++) { x.save(); x.translate((i + .5) * 1024 / 3, 365); x.rotate(-Math.PI / 2); x.drawImage(logoImg, -w / 2, -h / 2, w, h); x.restore(); } });      // a branded sleeve on the upper arm, readable from every side
  const band = add(new THREE.Mesh(new THREE.CylinderGeometry(.0578, .0578, .24, 56, 1, true), new THREE.MeshPhysicalMaterial({ map: t, roughness: .4, clearcoat: .7, clearcoatRoughness: .3 })), rob.l1); band.castShadow = false;
  [-.123, .123].forEach((y) => { const e = add(new THREE.Mesh(new THREE.TorusGeometry(.0578, .003, 8, 48), glow('#58E6F2')), rob.l1); e.rotation.x = Math.PI / 2; e.position.y = y; e.castShadow = false; });
  const pt = logoTex(1040, 300, (x) => x.drawImage(logoImg, 0, 0, 1040, 300)), pm = new THREE.MeshPhysicalMaterial({ map: pt, roughness: .45, clearcoat: .5 });      // and a nameplate on two sides of the trolley
  [[0, .2525, 0], [.2525, 0, Math.PI / 2]].forEach(([x, z, ry]) => { const b = box(.37, .125, .006, mat(LOGO_BG), x, .36, z, base, .003); b.rotation.y = ry; const m = new THREE.Mesh(new THREE.PlaneGeometry(.34, .098), pm); m.position.set(x + (ry ? .0035 : 0), .36, z + (ry ? 0 : .0035)); m.rotation.y = ry; base.add(m); });
  const qc = document.createElement('canvas'); qc.width = qc.height = 250; const qx = qc.getContext('2d'); qx.fillStyle = '#fff'; qx.fillRect(0, 0, 250, 250); qx.fillStyle = '#0F191B';      // a mock code to scan with the app
  const fin = (x, y) => { for (const [ox, oy] of [[0, 0], [14, 0], [0, 14]]) { const a = x - ox, b = y - oy; if (a >= 0 && a < 7 && b >= 0 && b < 7) return a === 0 || a === 6 || b === 0 || b === 6 || (a >= 2 && a <= 4 && b >= 2 && b <= 4); if (a >= -1 && a < 8 && b >= -1 && b < 8) return false; } return (x * 7 + y * 13 + x * y * 3) % 5 < 2; };
  for (let y = 0; y < 21; y++) for (let x = 0; x < 21; x++) if (fin(x, y)) qx.fillRect(20 + x * 10, 20 + y * 10, 10.4, 10.4); const qt = new THREE.CanvasTexture(qc); qt.colorSpace = THREE.SRGBColorSpace; qt.anisotropy = 8;
  const qm = new THREE.Mesh(new THREE.PlaneGeometry(.1, .1), new THREE.MeshPhysicalMaterial({ map: qt, roughness: .5 })); qm.position.set(.13, .52, .2535); base.add(qm); box(.112, .112, .005, mat('#58E6F2'), .13, .52, .2505, base, .008); }
const POLE_ROB = V(0, 1, 0), E = V(), W = V(), U = V(), Nrm = V();

const OV0 = scene.children.length;
// ---------- what the exercise looks like in the air ----------
const TRAIL = 150, trailPos = new Float32Array(TRAIL * 3), trailGeo = new THREE.BufferGeometry(); trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: '#0A4552', transparent: true, opacity: .7 })); trail.frustumCulled = false; scene.add(trail); let trailN = 0;
const GN = 96, guidePos = new Float32Array(GN * 3), guideGeo = new THREE.BufferGeometry(); guideGeo.setAttribute('position', new THREE.BufferAttribute(guidePos, 3));
const guide = new THREE.Line(guideGeo, new THREE.LineDashedMaterial({ color: '#7E8D91', dashSize: .025, gapSize: .018 })); guide.frustumCulled = false; scene.add(guide);
const ringGeo = new THREE.TorusGeometry(.07, .007, 10, 64);
const goal = new THREE.Mesh(ringGeo, glow('#2F9DB6')); goal.rotation.y = Math.PI / 2; scene.add(goal);
const past = new THREE.Mesh(ringGeo, glow('#8F9FA3')); past.rotation.y = Math.PI / 2; past.scale.setScalar(.8); scene.add(past);
const chase = new THREE.Mesh(new THREE.SphereGeometry(.03, 24, 20), glow('#F1C36A')); scene.add(chase);      // the dot to follow
const chaseHalo = new THREE.Mesh(new THREE.RingGeometry(.04, .052, 40), new THREE.MeshBasicMaterial({ color: '#F1C36A', transparent: true, opacity: .6, side: THREE.DoubleSide })); chaseHalo.rotation.y = Math.PI / 2; scene.add(chaseHalo);
const labels = [];
function label(color) { const c = document.createElement('canvas'); c.width = 512; c.height = 112; const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthTest: false, toneMapped: false })); sp.scale.set(.46, .1, 1); sp.renderOrder = 5; scene.add(sp);
  const o = { sp, text: '', color, draw() { const g = c.getContext('2d'); g.clearRect(0, 0, 512, 112); g.font = '600 46px Outfit, "Instrument Sans", system-ui, sans-serif'; const w = Math.min(492, g.measureText(o.text).width + 56);
    g.fillStyle = o.color; g.beginPath(); g.roundRect((512 - w) / 2, 14, w, 84, 42); g.fill(); g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(o.text, 256, 59); t.needsUpdate = true; }, set(tx) { if (tx !== o.text) { o.text = tx; o.draw(); } } };
  labels.push(o); return o; }
const goalL = label('#0A4552'), pastL = label('#7E8D91'), liveL = label('#D9483F');
if (document.fonts) document.fonts.ready.then(() => labels.forEach((l) => l.draw()));

// ---------- the exercises ----------
// at(t) gives, for a moment t (0 to 1) of one repetition: where the robot holds the patient, how the body leans, the number that is measured,
// what the coach says, and what the robot is doing (state: 'ok' green, 'hold' amber, 'load' red).
const X0 = .33, Z0 = .2, SHW = V(.02, .955, .175);
const there = (t, a, b, c) => (t < a ? ease(t / a) : t < b ? 1 : t < c ? 1 - ease((t - b) / (c - b)) : 0);      // out, hold, back, rest
const EX = {
  reach: { name: 'Forward reach', why: 'Reaching for a cup, a shelf, a door handle', period: 5.4, label: 'Reach', unit: 'cm', delta: '+3 cm on last week', repsLab: 'repetitions', reps: 12, mode: 'helps when she slows', modeVal: '20%', modeLab: 'robot help', series: [31, 33, 36, 38, 41],
    note: 'Reach is up 3 cm in a week. She tires after about 9 repetitions: two sets of 8 may suit her better than one of 12.',
    marks: [{ p: [.74, .98, Z0], text: 'Goal 41 cm', ring: goal, dy: .16 }, { p: [X0 + .38, .978, Z0], text: 'Last week 38 cm', ring: past, dy: -.12 }], off: [0, -.075, .1], span: .42,
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
let stopOn = false, stopT = 0, halted = false, reachK = 0, arrOn = false, arrT = 0, arriving = false; const ARR_END = 10.2, ARRQ = qs.get('arr');      // the arrival: she walks in, scans the station, sits down
      // the emergency-stop slide: a staff member presses the red button, the arm holds still
let blendT = 9, blendFrom = null, ex = 'reach', exT = 0, paused = false, lastSay = '', lastVal = -1, sayAt = -1, snap = true, wasLeg = false;
const el = { val: $('#mVal'), unit: $('#mUnit'), lab: $('#mLab'), say: $('#say'), mode: $('#mode'), name: $('#mName') };
function choose(name) { dispatchEvent(new CustomEvent('exchange', { detail: name })); ex = name; exT = 0; trailN = 0; lastVal = -1; const d = EX[name];
  el.unit.textContent = d.unit; el.lab.textContent = d.label; el.mode.textContent = d.mode; el.name.textContent = d.name;
  for (let i = 0; i < GN; i++) { const u = i / (GN - 1) * d.span; let p; if (d.path) p = d.path(u); else { const s = d.at(u); p = [s.x, s.y, s.z]; } guidePos[i * 3] = p[0] + d.off[0]; guidePos[i * 3 + 1] = p[1] + d.off[1]; guidePos[i * 3 + 2] = p[2] + d.off[2]; }
  guideGeo.attributes.position.needsUpdate = true; guide.computeLineDistances(); guide.visible = !d.noTrail; trail.visible = !d.noTrail && !d.leg; drawGuide(d); setMuscles(name);
  goal.visible = past.visible = goalL.sp.visible = pastL.sp.visible = false;
  d.marks.forEach((m, i) => { const L = i ? pastL : goalL; L.set(m.text); L.sp.visible = true; L.sp.position.set(m.p[0] + (m.dx || 0), m.p[1] + m.dy, m.p[2]); if (m.ring) { m.ring.visible = true; m.ring.position.set(m.p[0], m.p[1], m.p[2]); } });
  chase.visible = chaseHalo.visible = !!d.chase; cuff.visible = !!d.leg; rob.grip.visible = rob.top.visible = !d.leg; }
$('#pause').addEventListener('click', (e) => { paused = !paused; e.currentTarget.textContent = paused ? 'Play' : 'Pause'; });

// ---------- bold motion lines: dark dots for the planned path, a bright tail for where the hand has just been ----------
guide.material.visible = false; trail.material.visible = false;
const dotGeo = new THREE.SphereGeometry(1, 14, 10), mtx = new THREE.Matrix4(), GD = GN / 2, TD = 50;
const gDots = new THREE.InstancedMesh(dotGeo, glow('#1E282A'), GD), tDots = new THREE.InstancedMesh(dotGeo, glow('#1997B3'), TD); gDots.frustumCulled = tDots.frustumCulled = false; scene.add(gDots, tDots);
const tip = new THREE.Mesh(new THREE.ConeGeometry(.02, .05, 20), glow('#1E282A')); scene.add(tip);
function drawGuide(d) { for (let i = 0; i < GD; i++) { const k = i * 2 * 3; mtx.makeScale(.0065, .0065, .0065).setPosition(guidePos[k], guidePos[k + 1], guidePos[k + 2]); gDots.setMatrixAt(i, mtx); } gDots.instanceMatrix.needsUpdate = true; gDots.visible = guide.visible;
  const n = (GN - 1) * 3, m = (GN - 4) * 3; tip.visible = guide.visible && d.span < 1 && !d.marks.some((k) => k.ring); tip.position.set(guidePos[n], guidePos[n + 1], guidePos[n + 2]); tip.quaternion.setFromUnitVectors(YA, tA.set(guidePos[n] - guidePos[m], guidePos[n + 1] - guidePos[m + 1], guidePos[n + 2] - guidePos[m + 2]).normalize()); }
function drawTrail() { const n = Math.min(TD, Math.floor(trailN / 3)); tDots.visible = trail.visible; tDots.count = n; for (let i = 0; i < n; i++) { const k = i * 9, r = .013 * (1 - i / TD) + .003; mtx.makeScale(r, r, r).setPosition(trailPos[k], trailPos[k + 1], trailPos[k + 2]); tDots.setMatrixAt(i, mtx); } tDots.instanceMatrix.needsUpdate = true; }

// ---------- the body part each exercise works: it glows, brighter the harder it works ----------
const PARTS = { sh: armR.sh, up: armR.up, fore: armR.fore, hand: armR.hand, torso: body.torso, head: body.head, thigh: body.thigh };
Object.values(PARTS).forEach((m) => { m.material = m.material.clone(); m.material.emissive = new THREE.Color('#FF9A1F'); m.material.emissiveIntensity = 0; });
const TARGET = {
  reach: { name: 'Shoulder, triceps and trunk', parts: { sh: 1, up: 1, torso: .45 }, act: (s) => s.value / 41 },
  stretch: { name: 'Shoulder capsule, being stretched', parts: { sh: 1, up: .35 }, act: (s) => (s.value - 60) / 58 },
  circle: { name: 'Rotator cuff and shoulder blade', parts: { sh: 1, up: .5 }, act: (s, t) => .65 + Math.sin(t * Math.PI * 2) * .3 },
  follow: { name: 'Forearm, hand and movement control', parts: { fore: 1, hand: 1, head: .6 }, act: (s, t) => .65 + Math.sin(t * Math.PI * 8) * .3 },
  push: { name: 'Chest, shoulder and triceps', parts: { torso: .7, sh: 1, up: 1 }, act: (s) => s.value / 38 },
  leg: { name: 'Thigh muscle (quadriceps)', parts: { thigh: 1 }, act: (s) => (s.value - 8) / 64 },
};
// Each exercise lists its muscles: id on the map, name, what it does, how hard it works (0 to 1) at a moment of the repetition, and 1 if it is being stretched rather than working.
const osc = (t, n, ph = 0) => .5 + .5 * Math.sin(t * Math.PI * 2 * n + ph);
TARGET.reach.mus = [['delt', 'Front deltoid', 'lifts the arm', (a) => a], ['tri', 'Triceps', 'straightens the elbow', (a) => a * .85], ['cuff', 'Shoulder-blade muscles', 'slide the shoulder forward', (a) => a * .6], ['abs', 'Trunk muscles', 'steady the lean', (a) => a * .5]];
TARGET.stretch.mus = [['cap', 'Shoulder capsule', 'is stretched', (a) => a, 1], ['lat', 'Latissimus', 'lengthens', (a) => a * .8, 1], ['pec', 'Chest muscle', 'lengthens', (a) => a * .5, 1], ['delt', 'Deltoid', 'stays relaxed', () => .04]];
TARGET.circle.mus = [['cuff', 'Rotator cuff', 'keeps the joint centred', () => .6], ['delt', 'Deltoid', 'lifts the arm', (a, t) => .3 + .65 * osc(t, 1, Math.PI / 2)], ['pec', 'Chest muscle', 'pulls the arm inward', (a, t) => .12 + .75 * Math.max(0, Math.sin(t * Math.PI * 2))], ['lat', 'Latissimus', 'pulls it outward', (a, t) => .12 + .75 * Math.max(0, -Math.sin(t * Math.PI * 2))]];
TARGET.follow.mus = [['brain', 'Brain: movement control', 'compares and corrects', (a, t) => .5 + .45 * osc(t, 9)], ['fore', 'Forearm muscles', 'make fine corrections', (a, t) => .35 + .55 * osc(t, 7, 1)], ['delt', 'Deltoid', 'holds the arm up', () => .5], ['cuff', 'Rotator cuff', 'steadies the shoulder', () => .45]];
TARGET.push.mus = [['pec', 'Chest muscle', 'pushes forward', (a) => a], ['tri', 'Triceps', 'locks the elbow', (a) => a * .95], ['delt', 'Front deltoid', 'holds the arm up', (a) => .25 + a * .6], ['abs', 'Trunk muscles', 'brace the body', (a) => a * .6]];
TARGET.leg.mus = [['quad', 'Quadriceps', 'straightens the knee', (a) => a], ['hipf', 'Hip flexors', 'hold the thigh steady', (a) => .15 + a * .35], ['ham', 'Hamstrings', 'lengthen and let go', (a) => a * .6, 1], ['abs', 'Trunk muscles', 'keep her upright', (a) => .2 + a * .2, 0, 1]];
const IDS = ['back', 'abs', 'lat', 'pec', 'cuff', 'cap', 'hipf', 'ham', 'quad', 'calf', 'tib', 'tri', 'bic', 'fore', 'delt'], ACT = {}; IDS.forEach((id) => { ACT[id] = { a: 0, t: 0, st: 0, on: false, name: '' }; });
const rowsOf = (tg) => tg.mus.map((m) => `<div class="mrow"><p><b>${m[1]}</b><span>${m[2]}</span></p><div class="bar${m[4] ? ' st' : ''}"><i></i></div></div>`).join('');
$$('[data-mus]').forEach((c) => { c.innerHTML = rowsOf(TARGET[c.dataset.mus]); });

// ---------- the muscles on the model: each one is its own shape lying on the body, it fills with colour and swells as it works ----------
const SR = V(), ER = V(), HR = V(), M3 = {}, mGeo = new THREE.SphereGeometry(1, 28, 20), cHot = new THREE.Color('#E8472B'), cBlue = new THREE.Color('#3F86DB'), eHot = new THREE.Color('#FF5A1F'), eBlue = new THREE.Color('#2F6FD0');
const m3 = (id, parent, sx, sy, sz, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(mGeo, new THREE.MeshStandardMaterial({ color: '#E8472B', emissive: '#FF5A1F', emissiveIntensity: .5, roughness: .5, transparent: true, opacity: 0, depthWrite: false }));
  m.position.set(x, y, z); m.userData.s = [sx, sy, sz]; m.scale.set(sx, sy, sz); m.renderOrder = 3; m.visible = false; (parent || scene).add(m); M3[id] = m; return m; };
m3('pec', torso, .042, .062, .072, .098, .345, .075); m3('lat', torso, .04, .115, .06, -.08, .26, .1); m3('abs', torso, .035, .1, .085, .1, .16, 0); m3('cuff', torso, .04, .055, .05, -.08, .43, .12);
m3('cap', null, .072, .072, .072); m3('delt', null, .058, .072, .058); m3('bic', null, .034, .1, .036); m3('tri', null, .034, .11, .036); m3('fore', null, .033, .09, .034);
m3('quad', null, .036, .15, .058, .25, .58, .095).quaternion.setFromUnitVectors(YA, XA); m3('ham', null, .03, .14, .05, .24, .462, .095).quaternion.setFromUnitVectors(YA, XA); m3('hipf', null, .05, .04, .05, .09, .588, .09);
const ud = V(), f3 = V(), fd = V(), ff = V();
function muscles3D() { ud.copy(ER).sub(SR).normalize(); f3.copy(YA).addScaledVector(ud, -ud.y).normalize(); fd.copy(HR).sub(ER).normalize(); ff.copy(YA).addScaledVector(fd, -fd.y).normalize();
  M3.cap.position.copy(SR); M3.delt.position.copy(SR).addScaledVector(ud, .04).addScaledVector(f3, .012); M3.delt.position.z += .012; M3.delt.quaternion.setFromUnitVectors(YA, ud);
  M3.bic.position.copy(SR).lerp(ER, .55).addScaledVector(f3, .03); M3.bic.quaternion.copy(M3.delt.quaternion); M3.tri.position.copy(SR).lerp(ER, .5).addScaledVector(f3, -.03); M3.tri.quaternion.copy(M3.delt.quaternion);
  M3.fore.position.copy(ER).addScaledVector(fd, .1).addScaledVector(ff, .02); M3.fore.quaternion.setFromUnitVectors(YA, fd);
  for (const id in M3) { const m = M3[id], A = ACT[id], s = m.userData.s, a = A.a, st = A.st === 1, r = st ? 1 - a * .15 : 1 + a * .28; m.visible = a > .015; if (!m.visible) continue;
    m.material.opacity = Math.min(.97, .35 + a * .8); m.material.color.copy(st ? cBlue : cHot); m.material.emissive.copy(st ? eBlue : eHot); m.material.emissiveIntensity = .25 + a * .6; m.scale.set(s[0] * r, s[1] * (st ? 1 + a * .08 : 1), s[2] * r); } }

// ---------- the muscle map: a side view of the body that copies the pose of the model, with every muscle drawn as its own belly ----------
const NS = 'http://www.w3.org/2000/svg', map = $('#map'), mk = (tag, at, parent) => { const e = document.createElementNS(NS, tag); for (const k in at) e.setAttribute(k, at[k]); (parent || map).appendChild(e); return e; };
const FLESH = '#E1E6E9', BONE = '#F4F6F7', BONEL = '#CFC6AE', flesh = (w, p) => mk('line', { stroke: FLESH, 'stroke-width': w, 'stroke-linecap': 'round' }, p), bone = (p) => { const o = mk('line', { stroke: BONEL, 'stroke-width': 3.6, 'stroke-linecap': 'round' }, p), i = mk('line', { stroke: BONE, 'stroke-width': 2.4, 'stroke-linecap': 'round' }, p); return [o, i]; };
const seg = (els, a, b) => (Array.isArray(els) ? els : [els]).forEach((e) => { e.setAttribute('x1', a[0].toFixed(1)); e.setAttribute('y1', a[1].toFixed(1)); e.setAttribute('x2', b[0].toFixed(1)); e.setAttribute('y2', b[1].toFixed(1)); });
mk('path', { d: 'M-22 -47 H27 M-19 -47 L-23 -100', stroke: '#DAE5E6', 'stroke-width': 3, 'stroke-linecap': 'round', fill: 'none' });      // the chair
const gT = mk('g', {}), gL = mk('g', {}), gA = mk('g', {}), gTxt = mk('g', {});
mk('ellipse', { cx: 1, cy: -75, rx: 12, ry: 27, fill: FLESH }, gT); mk('circle', { cx: 3, cy: -114, r: 10.5, fill: FLESH }, gT); mk('path', { d: 'M-6 -98 Q-9 -76 -5 -52', stroke: BONEL, 'stroke-width': 2.2, 'stroke-dasharray': '2.4 1.4', fill: 'none' }, gT);
[-90, -84, -78, -72].forEach((y) => mk('path', { d: `M-5 ${y} Q4 ${y + 5} 10 ${y + 1}`, stroke: BONEL, 'stroke-width': .9, fill: 'none', opacity: .8 }, gT)); mk('ellipse', { cx: 3, cy: -54, rx: 9, ry: 5.5, fill: BONE, stroke: BONEL, 'stroke-width': .8 }, gT);
const brain = mk('path', { d: 'M-4 -116 q1 -7 8 -6 q7 1 6 7 q-1 5 -7 4 q-2 4 -5 1 q-3 -1 -2 -6z', fill: '#E6C9C0', stroke: '#C9A79C', 'stroke-width': .5 }, gT);
const L = { thigh: flesh(15, gL), shin: flesh(11.5, gL), foot: flesh(5.5, gL), femur: bone(gL), tibia: bone(gL), ten: mk('line', { stroke: '#D9CDB4', 'stroke-width': 1.3, 'stroke-linecap': 'round' }, gL), knee: mk('circle', { r: 3.2, fill: BONE, stroke: BONEL, 'stroke-width': .8 }, gL) };
const Ar = { up: flesh(11, gA), fo: flesh(9, gA), hum: bone(gA), rad: bone(gA), sh: mk('circle', { r: 3.4, fill: BONE, stroke: BONEL, 'stroke-width': .8 }, gA), el: mk('circle', { r: 2.8, fill: BONE, stroke: BONEL, 'stroke-width': .8 }, gA), hand: mk('circle', { r: 4, fill: FLESH, stroke: BONEL, 'stroke-width': .6 }, gA), cap: mk('circle', { r: 6, fill: 'none', stroke: '#E6C9C0', 'stroke-width': 1.2 }, gA) };
// where each muscle starts and ends, how thick its belly is, and which way the belly sits (ox, oy)
const HIP2 = [6, -52], K2 = [44, -52], c2 = { S: [0, 0], E: [0, 0], H: [0, 0], A: [0, 0], u: [1, 0], f: [0, -1], fd: [1, 0], ff: [0, -1], sd: [0, 1], bk: [-1, 0], fr: [1, 0] };
const along = (p, d, k, n, j) => [p[0] + d[0] * k + n[0] * j, p[1] + d[1] * k + n[1] * j];
const MAP = [
  { id: 'back', g: gT, w: 2.2, p: () => [-9.5, -88, -8.5, -57, -1, 0] }, { id: 'abs', g: gT, w: 2.6, p: () => [11, -77, 9.5, -54, 1, 0] }, { id: 'lat', g: gT, w: 3.4, p: () => [-8, -63, 1, -93, -1.5, 0] },
  { id: 'pec', g: gT, w: 3.4, p: () => [11.5, -83, 3, -94.5, 1.2, -.6] }, { id: 'cuff', g: gT, w: 2.4, p: () => [-10.5, -97, 1, -96.5, 0, -1] },
  { id: 'hipf', g: gL, w: 2.4, p: () => [-1, -60, 14, -55.5, -.5, -1], lp: [-6, -10] }, { id: 'ham', g: gL, w: 3.2, p: (c) => [2, -46.5, ...along(K2, c.sd, 6, c.bk, 3.2), 0, 1.6] }, { id: 'quad', g: gL, w: 4, p: () => [7, -58, 45.5, -57, 0, -1.8] },
  { id: 'calf', g: gL, w: 2.8, p: (c) => [...along(K2, c.sd, 3, c.bk, 3), ...along(K2, c.sd, 36, c.bk, 2), c.bk[0] * 1.6, c.bk[1] * 1.6] }, { id: 'tib', g: gL, w: 1.5, p: (c) => [...along(K2, c.sd, 7, c.fr, 3.4), ...along(K2, c.sd, 33, c.fr, 2.6), c.fr[0] * .6, c.fr[1] * .6] },
  { id: 'tri', g: gA, w: 3, p: (c) => [...along(c.S, c.u, 2, c.f, -3), ...along(c.E, c.u, 0, c.f, -3.2), -c.f[0] * 1.5, -c.f[1] * 1.5] }, { id: 'bic', g: gA, w: 3, p: (c) => [...along(c.S, c.u, 3, c.f, 2.5), ...along(c.E, c.fd, 5, c.f, 1), c.f[0] * 1.5, c.f[1] * 1.5] },
  { id: 'fore', g: gA, w: 2.6, p: (c) => [...along(c.E, c.fd, 2, c.ff, 2.6), ...along(c.E, c.fd, 22, c.ff, 1.4), c.ff[0], c.ff[1]] }, { id: 'delt', g: gA, w: 4.2, p: (c) => [c.S[0] - 1.5, c.S[1] - 4.5, ...along(c.S, c.u, 15, c.f, 1), c.f[0] * 1.6, c.f[1] * 1.6] },
];
MAP.forEach((m) => { m.el = mk('path', { 'stroke-width': .45, 'stroke-linejoin': 'round' }, m.g); m.fib = mk('path', { fill: 'none', stroke: '#fff', 'stroke-width': .45, opacity: .5 }, m.g);
  m.txt = mk('text', { 'font-size': 4.1, 'font-weight': 600, 'text-anchor': 'middle', fill: '#1E282A', stroke: '#fff', 'stroke-width': 1.3, 'paint-order': 'stroke', 'font-family': 'Outfit, sans-serif' }, gTxt); });
const BASE = [230, 201, 192], HOT = [232, 71, 43], BLU = [63, 134, 219], rgb = (a, st, dark = 1) => { const c = st === 1 ? BLU : HOT, m = a < .01 ? 0 : .18 + a * .82; return `rgb(${BASE.map((v, i) => Math.round(lerp(v, c[i], m) * dark)).join(',')})`; };
const p2 = (v) => [v.x * 100, -v.y * 100], n2 = (a, b) => { const x = b[0] - a[0], y = b[1] - a[1], l = Math.hypot(x, y) || 1; return [x / l, y / l]; }, upn = (d) => (d[0] >= 0 ? [d[1], -d[0]] : [-d[1], d[0]]);
function drawMap(lean) { const c = c2; c.S = p2(SR); c.E = p2(ER); c.H = p2(HR); c.A = p2(ANK); c.u = n2(c.S, c.E); c.f = upn(c.u); c.fd = n2(c.E, c.H); c.ff = upn(c.fd); c.sd = n2(K2, c.A); c.bk = [-c.sd[1], c.sd[0]]; c.fr = [c.sd[1], -c.sd[0]];
  gT.setAttribute('transform', `rotate(${(lean * 57.3).toFixed(1)} 0 -50)`);
  seg(L.thigh, HIP2, K2); seg(L.femur, HIP2, K2); seg(L.shin, K2, c.A); seg(L.tibia, K2, c.A); seg(L.foot, along(c.A, c.sd, 3, c.fr, -1), along(c.A, c.sd, 3, c.fr, 13)); seg(L.ten, [45.5, -57], along(K2, c.sd, 8, c.fr, 3.4)); L.knee.setAttribute('cx', 45.5); L.knee.setAttribute('cy', -54.5);
  seg(Ar.up, c.S, c.E); seg(Ar.hum, c.S, c.E); seg(Ar.fo, c.E, c.H); seg(Ar.rad, c.E, c.H); [['sh', c.S], ['el', c.E], ['hand', c.H], ['cap', c.S]].forEach(([k, p]) => { Ar[k].setAttribute('cx', p[0].toFixed(1)); Ar[k].setAttribute('cy', p[1].toFixed(1)); });
  Ar.cap.setAttribute('stroke', rgb(ACT.cap.a, ACT.cap.st)); Ar.cap.setAttribute('stroke-width', (1.2 + ACT.cap.a * 2.4).toFixed(2)); brain.setAttribute('fill', rgb(brainA, 0));
  MAP.forEach((m) => { const A = ACT[m.id], a = A.a, st = A.st, q = m.p(c), x1 = q[0], y1 = q[1], x2 = q[2], y2 = q[3], d = n2([x1, y1], [x2, y2]), nx = -d[1], ny = d[0], w = m.w * 2 * (st === 1 ? 1 - a * .3 : 1 + a * .6), mx = (x1 + x2) / 2 + q[4], my = (y1 + y2) / 2 + q[5], F = (v) => v.toFixed(1);
    m.el.setAttribute('d', `M${F(x1)} ${F(y1)}Q${F(mx + nx * w)} ${F(my + ny * w)} ${F(x2)} ${F(y2)}Q${F(mx - nx * w)} ${F(my - ny * w)} ${F(x1)} ${F(y1)}Z`); m.el.setAttribute('fill', rgb(a, st)); m.el.setAttribute('stroke', rgb(a, st, .8));
    m.fib.setAttribute('d', `M${F(x1)} ${F(y1)}Q${F(mx + nx * w * .38)} ${F(my + ny * w * .38)} ${F(x2)} ${F(y2)}M${F(x1)} ${F(y1)}Q${F(mx - nx * w * .38)} ${F(my - ny * w * .38)} ${F(x2)} ${F(y2)}`);
    if (A.on) { const ol = Math.hypot(q[4], q[5]) || 1, k = w / 2 + 4.2, lx = (x1 + x2) / 2 + (m.lp ? m.lp[0] : q[4] / ol * k), ly = (y1 + y2) / 2 + (m.lp ? m.lp[1] : q[5] / ol * k) + 1.4; m.txt.setAttribute('x', F(lx)); m.txt.setAttribute('y', F(ly)); } }); }
const tName = $('#tName'), musHud = $('#musHud'); let actS = 0, bars = [], mv = [], brainA = 0, brainT = 0;
function setMuscles(name) { const tg = TARGET[name]; tName.textContent = tg.name; musHud.innerHTML = rowsOf(tg); mv = tg.mus.map(() => 0); IDS.forEach((id) => { ACT[id].on = false; ACT[id].t = 0; });
  tg.mus.forEach((m) => { const A = ACT[m[0]]; if (A) { A.on = true; A.st = m[4] || 0; A.name = m[5] ? '' : m[1].replace('Front d', 'D').replace(' muscles', '').replace(' muscle', ''); } });
  bars = tg.mus.map((m, i) => [...$$(`[data-mus="${name}"] .mrow:nth-child(${i + 1}) i`), musHud.querySelector(`.mrow:nth-child(${i + 1}) i`)]);
  MAP.forEach((m) => { m.txt.textContent = ACT[m.id].on ? ACT[m.id].name : ''; }); map.setAttribute('viewBox', name === 'leg' ? '-24 -93 116 86' : '-27 -134 116 86'); }
// ---------- the joints: a marker on each working joint, an arc that opens with the angle, and the angle in degrees ----------
// Shoulder: how far the arm is lifted away from the body. Elbow: the angle between upper arm and forearm (180 = straight). Knee: how far the shin is lifted from hanging down.
const JC = '#0E708F', JN = { S: 'Shoulder', E: 'Elbow', K: 'Knee' }, JOFF = { S: V(-.2, .1, 0), E: V(.02, -.13, .05), K: V(-.08, .15, 0) }, AN = 22;
TARGET.reach.jts = ['S', 'E']; TARGET.stretch.jts = ['S']; TARGET.circle.jts = ['S']; TARGET.follow.jts = ['E', 'S']; TARGET.push.jts = ['E', 'S']; TARGET.leg.jts = ['K']; TARGET.stretch.valJ = 'S'; TARGET.leg.valJ = 'K';
const ringTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d'); g.beginPath(); g.arc(64, 64, 42, 0, 7); g.fillStyle = 'rgba(255,255,255,.6)'; g.fill(); g.lineWidth = 12; g.strokeStyle = JC; g.stroke(); g.beginPath(); g.arc(64, 64, 11, 0, 7); g.fillStyle = JC; g.fill(); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; })();
const gJ = mk('g', {}); map.insertBefore(gJ, gTxt); const J3 = {}, jtsEl = $('#jts'), axis = V(), jq = new THREE.Quaternion(), jv = V();
['S', 'E', 'K'].forEach((k) => { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: ringTex, transparent: true, depthTest: false, toneMapped: false })); sp.renderOrder = 6; scene.add(sp);
  const geo = new THREE.BufferGeometry(), idx = []; geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(AN * 6), 3)); for (let i = 0; i < AN - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); } geo.setIndex(idx);
  const arc = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: JC, transparent: true, opacity: .78, side: THREE.DoubleSide, depthTest: false })); arc.renderOrder = 5; arc.frustumCulled = false; scene.add(arc);
  const lab = label('#0E7C86'); lab.sp.scale.set(.38, .083, 1);
  J3[k] = { sp, arc, lab, p: V(), d1: V(), d2: V(), arc2: mk('path', { fill: JC, 'fill-opacity': .28, stroke: JC, 'stroke-width': 1.1, 'stroke-linejoin': 'round' }, gJ), dot: mk('circle', { r: 3.6, fill: '#fff', stroke: JC, 'stroke-width': 1.5 }, gJ), pin: mk('circle', { r: 1.3, fill: JC }, gJ),
    txt: mk('text', { 'font-size': 5, 'font-weight': 700, 'text-anchor': 'middle', fill: '#0B576F', stroke: '#fff', 'stroke-width': 1.5, 'paint-order': 'stroke', 'font-family': 'Outfit, sans-serif' }, gJ) }; });
function joints(s) { const tg = TARGET[ex], out = [];
  J3.S.p.copy(SR); J3.S.d1.set(-Math.sin(sm.lean), -Math.cos(sm.lean), 0); J3.S.d2.copy(ER).sub(SR).normalize();
  J3.E.p.copy(ER); J3.E.d1.copy(SR).sub(ER).normalize(); J3.E.d2.copy(HR).sub(ER).normalize();
  J3.K.p.copy(KNEE_R); J3.K.d1.set(0, -1, 0); J3.K.d2.copy(ANK).sub(KNEE_R).normalize();
  for (const key in J3) { const j = J3[key], on = tg.jts.includes(key), show = on ? '' : 'none'; j.sp.visible = j.arc.visible = j.lab.sp.visible = false; j.arc2.style.display = j.dot.style.display = j.pin.style.display = j.txt.style.display = show; if (!on) continue;
    const ang = Math.acos(clamp(j.d1.dot(j.d2), -1, 1)), deg = tg.valJ === key ? s.value : Math.round(ang * 57.2958);
    j.sp.position.copy(j.p); j.sp.scale.setScalar(.088 * (1 + Math.sin(T * 4) * .07));
    axis.copy(j.d1).cross(j.d2); if (axis.lengthSq() < 1e-8) axis.set(0, 0, 1); axis.normalize(); const pos = j.arc.geometry.attributes.position;
    for (let i = 0; i < AN; i++) { jq.setFromAxisAngle(axis, ang * i / (AN - 1)); jv.copy(j.d1).applyQuaternion(jq); pos.setXYZ(i * 2, j.p.x + jv.x * .075, j.p.y + jv.y * .075, j.p.z + jv.z * .075); pos.setXYZ(i * 2 + 1, j.p.x + jv.x * .115, j.p.y + jv.y * .115, j.p.z + jv.z * .115); } pos.needsUpdate = true;
    j.lab.set(JN[key] + ' ' + deg + '°'); j.lab.sp.position.copy(j.p).add(JOFF[key]); out.push(`<span><b>${JN[key]}</b> ${deg}°</span>`);
    // the same joint on the muscle map
    const p = p2(j.p), a1 = n2([0, 0], [j.d1.x, -j.d1.y]), a2 = n2([0, 0], [j.d2.x, -j.d2.y]), r = 10, sw = a1[0] * a2[1] - a1[1] * a2[0] > 0 ? 1 : 0, F = (v) => v.toFixed(1); let bx = a1[0] + a2[0], by = a1[1] + a2[1]; const bl = Math.hypot(bx, by); if (bl < .05) { bx = -a1[1]; by = a1[0]; } else { bx /= bl; by /= bl; }
    j.arc2.setAttribute('d', `M${F(p[0])} ${F(p[1])}L${F(p[0] + a1[0] * r)} ${F(p[1] + a1[1] * r)}A${r} ${r} 0 0 ${sw} ${F(p[0] + a2[0] * r)} ${F(p[1] + a2[1] * r)}Z`);
    [j.dot, j.pin].forEach((e) => { e.setAttribute('cx', F(p[0])); e.setAttribute('cy', F(p[1])); }); j.txt.textContent = deg + '°'; j.txt.setAttribute('x', F(p[0] + bx * (r + 6.5))); j.txt.setAttribute('y', F(p[1] + by * (r + 6.5) + 1.7)); }
  const h = out.join(''); if (h !== jtsEl._h) { jtsEl._h = h; jtsEl.innerHTML = h; } }

// the seated patient and everything drawn around her go into two groups, so they can be hidden while she is still walking in
const annaG = new THREE.Group(), ovG = new THREE.Group(); { const kids = scene.children.slice(), a = kids.slice(AN0, AN1), o = kids.slice(OV0); scene.add(annaG, ovG); a.forEach((c) => annaG.add(c)); o.forEach((c) => ovG.add(c)); }
// ---------- the page drives the scene: the part of the text in the middle of the screen decides the exercise and the camera ----------
const VIEWS = { arrive: [.74, .3, 6.4], stop: [.9, .27, 4.5], gym: [.8, .36, 12.8], wide: [.72, .27, 5.5], reach: [.62, .2, 4.7], stretch: [.42, .15, 4.7], circle: [1.02, .24, 4.5], follow: [1.02, .2, 4.5], push: [.55, .17, 4.4], leg: [.36, .13, 4.5] };
const view = { az: .72, el: .27, dist: 5.5, taz: .72, tel: .27, tdist: 5.5, drag: false, x: 0, y: 0, idle: 0 };
const stage = $('.stage'), secs = $$('[data-ex]'), links = $$('[data-go]'); let active = null, VW = 1, VH = 1, phone = false, seen = true;
const prog = $('#prog'), mainEl = $('main');
function pick() { const dk = document.documentElement.classList.contains('deck'); if (dk) { const c = document.querySelector('.cur'); seen = !c || c.classList.contains('ch'); } else prog.style.transform = 'scaleX(' + clamp(scrollY / Math.max(1, mainEl.offsetHeight - innerHeight)).toFixed(4) + ')'; const mid = phone ? stage.offsetHeight + (innerHeight - stage.offsetHeight) * .4 : innerHeight * .5; let best = null, bd = 1e9;
  secs.forEach((s) => { const r = s.getBoundingClientRect(), d = r.top <= mid && r.bottom >= mid ? 0 : Math.min(Math.abs(r.top - mid), Math.abs(r.bottom - mid)); if (d < bd) { bd = d; best = s; } }); if (dk) best = secs.find((s) => s.classList.contains('cur')) || active;
  if (!best || best === active) return; active = best; secs.forEach((s) => s.classList.toggle('on', s === best)); links.forEach((a) => a.classList.toggle('on', a.dataset.go === best.id));
  if (best.dataset.ex !== ex) choose(best.dataset.ex); const v = VIEWS[best.dataset.view || best.dataset.ex]; view.taz = v[0]; view.tel = v[1]; view.tdist = v[2]; facT = best.dataset.view === 'gym' || best.dataset.fac ? 1 : 0; stopOn = !!best.dataset.stop; stopT = 0; arrOn = !!best.dataset.arrive; arrT = 0; }
canvas.addEventListener('pointerdown', (e) => { if (e.pointerType !== 'mouse') return; view.drag = true; view.x = e.clientX; view.y = e.clientY; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointermove', (e) => { if (!view.drag) return; view.taz -= (e.clientX - view.x) * .006; view.tel = clamp(view.tel + (e.clientY - view.y) * .004, .04, .9); view.x = e.clientX; view.y = e.clientY; view.idle = 0; });
addEventListener('pointerup', () => { view.drag = false; });
const size = () => { VW = canvas.clientWidth || 1; VH = canvas.clientHeight || 1; phone = innerWidth < 900; renderer.setSize(VW, VH, false); cam.aspect = VW / VH; cam.updateProjectionMatrix(); active = null; pick(); };
new ResizeObserver(size).observe(canvas); addEventListener('scroll', pick, { passive: true }); addEventListener('slidechange', pick);
if ('IntersectionObserver' in window) new IntersectionObserver((e) => { seen = e[0].isIntersecting; }).observe(stage);
choose(ex); { const go = qs.get('s') && $('#' + qs.get('s')); if (go) { let p = go.previousElementSibling; while (p) { p.style.display = 'none'; p = p.previousElementSibling; } } } size();      // ?s=leg puts one part at the top (for screenshots)

// ---------- the facility: a corner of a local gym that builds itself around the station ----------
const FAC = [], facAnim = []; var facT; let facP = 0;      // facT is set by pick(), which first runs before this point
const fm = (c, o = {}) => mat(c, { roughness: .8, clearcoat: 0, ...o });
const FM = { wall: fm('#EFF2F3', { roughness: .95 }), floor: fm('#D4DBDF'), trim: mat('#FFFFFF', { roughness: .5 }), glass: new THREE.MeshBasicMaterial({ color: '#CDE7F0' }), dark: mat('#2F3638', { roughness: .5 }), steel: mat('#C9CECF', { roughness: .3, metalness: .6 }),
  mirror: mat('#CFE4EA', { roughness: .18, metalness: 0, clearcoat: 1, clearcoatRoughness: .05 }), teal: fm('#2E8C8A'), navy: fm('#2F3F55'), sun: mat('#F0B95B', { roughness: .6 }), leaf: fm('#58C4D4'), leaf2: fm('#7DADB5'), pot: fm('#DBE1E4'), belt: fm('#3B4345', { roughness: .95 }),
  hairB: fm('#6B4A36'), hairD: fm('#2E2A28'), skin2: mat('#E5B48E', { clearcoat: .2, roughness: .6 }), lilac: fm('#8E86C9'), sky: fm('#7FB6D9'), white: fm('#F8F9F9') };
const blobTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'), g = x.createRadialGradient(32, 32, 2, 32, 32, 32); g.addColorStop(0, 'rgba(30,40,42,.3)'); g.addColorStop(1, 'rgba(30,40,42,0)'); x.fillStyle = g; x.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();
function fac(x, z, ry, delay, mode, build, blob, bz = 1) { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = ry; scene.add(g); build(g); g.traverse((o) => { if (o.isMesh) o.castShadow = false; });
  if (blob) { const b = new THREE.Mesh(new THREE.PlaneGeometry(blob * 2, blob * 2 * bz), new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false })); b.rotation.x = -Math.PI / 2; b.position.y = .006; b.renderOrder = 1; g.add(b); }
  g.visible = false; FAC.push({ g, delay, mode }); return g; }
function sign(w, h, parent, x, y, z, draw) { const c = document.createElement('canvas'); c.width = 512; c.height = Math.round(512 * h / w); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  const paint = () => { draw(c.getContext('2d'), c.width, c.height); t.needsUpdate = true; }; paint(); logoWait.push(paint); if (document.fonts && document.fonts.ready) document.fonts.ready.then(paint);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: t, toneMapped: false })); m.position.set(x, y, z); parent.add(m); return m; }
const logo = (x, cx, cy, s) => { x.fillStyle = '#58C4D4'; x.beginPath(); x.ellipse(cx - s * .45, cy, s * .32, s * .8, -.45, 0, 7); x.fill(); x.fillStyle = '#2F606B'; x.beginPath(); x.ellipse(cx + s * .45, cy, s * .32, s * .8, .45, 0, 7); x.fill(); x.fillStyle = '#D9483F'; x.beginPath(); x.arc(cx, cy - s * .95, s * .26, 0, 7); x.fill(); };
// a simple person: the body is laid between a few points every frame, the same way Anna's limbs are
function person(parent, o) { const g = new THREE.Group(); parent.add(g); const lm = (r, len, m) => capsule(r, len, m, g), arm = o.long ? o.top : o.skin, shin = o.shorts ? o.skin : o.legs, two = (f) => [f(-1), f(1)];
  const p = { g, torso: lm(.132, .23, o.top), hip: ball(.135, o.legs, 0, 0, 0, g), ua: two(() => lm(.052, .16, o.top)), fa: two(() => lm(.041, .16, arm)), th: two(() => lm(.076, .29, o.legs)), sh: two(() => lm(.057, .33, shin)),
    sho: two(() => ball(.056, o.top, 0, 0, 0, g)), elb: two(() => ball(.043, arm, 0, 0, 0, g)), kn: two(() => ball(.062, shin, 0, 0, 0, g)), hands: two(() => ball(.047, o.skin, 0, 0, 0, g)), head: new THREE.Group(),
    feet: two(() => { const f = new THREE.Group(); g.add(f); box(.2, .068, .095, o.shoe, 0, .004, 0, f, .03); box(.215, .024, .104, o.sole || FM.dark, 0, -.034, 0, f, .01); if (o.shorts) cyl(.052, .05, .07, FM.white, -.05, .065, 0, f); return f; }) };
  p.torso.scale.set(.82, 1, 1.18); p.hip.scale.set(.8, .62, 1.14); g.add(p.head); p.head.scale.setScalar(1.1); const h = p.head, dark = o.hair;
  ball(.1, o.skin, 0, 0, 0, h); cyl(.04, .046, .09, o.skin, 0, -.115, 0, h); [-.098, .098].forEach((z) => ball(.022, o.skin, -.008, -.006, z, h));
  [-.042, .042].forEach((z) => { ball(.0125, M.joint, .0955, .012, z, h); const sp = new THREE.Mesh(new THREE.SphereGeometry(.004, 10, 8), new THREE.MeshBasicMaterial({ color: '#fff' })); sp.position.set(.106, .017, z + .004); h.add(sp);
    const br = box(.008, .008, .032, dark, .094, .043, z, h, .003); br.rotation.x = z > 0 ? .18 : -.18; const ch = ball(.02, mat('#F2A08F', { clearcoat: 0, roughness: .8 }), .083, -.026, z * 1.45, h); ch.scale.set(.35, .8, 1); });
  ball(.014, o.skin, .104, -.012, 0, h); const sm = add(new THREE.Mesh(new THREE.TorusGeometry(.02, .0035, 8, 20, Math.PI), mat('#A8483F', { clearcoat: 0 })), h); sm.position.set(.099, -.036, 0); sm.rotation.set(Math.PI, Math.PI / 2, 0);
  ball(.108, dark, -.022, .03, 0, h).scale.set(1, .92, 1.04); [-.055, 0, .055].forEach((z, i) => ball(.042, dark, .058 - Math.abs(z) * .25, .084 - Math.abs(z) * .2, z, h).scale.set(1, .55, 1));
  if (o.style === 'tail') { ball(.05, dark, -.125, .035, 0, h); ball(.042, dark, -.168, -.02, 0, h); ball(.032, dark, -.185, -.085, 0, h); const t = add(new THREE.Mesh(new THREE.TorusGeometry(.03, .01, 8, 18), M.coral), h); t.position.set(-.108, .05, 0); t.rotation.y = Math.PI / 2; }
  if (o.style === 'bun') { ball(.058, dark, -.07, .128, 0, h); [-.085, .085].forEach((z) => ball(.04, dark, -.03, -.03, z, h).scale.set(1, 1.5, .6)); }
  if (o.style === 'short') [-.09, .09].forEach((z) => ball(.035, dark, .0, .03, z, h).scale.set(1.2, 1.1, .5));
  if (o.band) { const b = add(new THREE.Mesh(new THREE.TorusGeometry(.104, .013, 10, 36), o.band), h); b.rotation.x = Math.PI / 2; b.position.set(-.012, .052, 0); b.rotation.y = .12; }
  if (o.collar) { p.collar = add(new THREE.Mesh(new THREE.TorusGeometry(.05, .022, 10, 24), o.collar), g); p.collar.rotation.x = Math.PI / 2; }
  if (o.badge) { p.badge = new THREE.Group(); g.add(p.badge); box(.01, .075, .055, FM.white, 0, 0, 0, p.badge, .005); box(.012, .018, .04, FM.teal, .002, .018, 0, p.badge, .003); box(.012, .006, .035, FM.steel, .002, -.008, 0, p.badge, .002); }
  if (o.stripe) { p.stripe = two(() => lm(.054, .012, o.stripe)); }
  return p; }
const pS = V(), pM = V(), pD = V(), poleA = V(-.5, -.6, 0), poleL = V(1, .25, 0);
function pose(p, P, N, hands, feet) { between(p.torso, P, N); pD.copy(N).sub(P).normalize(); p.head.position.copy(N).addScaledVector(pD, .17); p.hip.position.copy(P); p.hip.position.y -= .03;
  if (p.collar) p.collar.position.copy(N).addScaledVector(pD, .045); if (p.badge) { p.badge.position.copy(P).lerp(N, .7); p.badge.position.x += .1; p.badge.position.z += .065; }
  for (let i = 0; i < 2; i++) { const sg = i ? 1 : -1;
    pS.copy(N); pS.y -= .085; pS.z += sg * .16; p.sho[i].position.copy(pS); elbow(pM, pS, hands[i], .25, .24, poleA); between(p.ua[i], pS, pM); between(p.fa[i], pM, hands[i]); p.elb[i].position.copy(pM); p.hands[i].position.copy(hands[i]);
    if (p.stripe) { p.stripe[i].position.copy(pS).lerp(pM, .78); p.stripe[i].quaternion.copy(p.ua[i].quaternion); }
    pS.copy(P); pS.y -= .02; pS.z += sg * .09; elbow(pM, pS, feet[i], .44, .44, poleL); between(p.th[i], pS, pM); between(p.sh[i], pM, feet[i]); p.kn[i].position.copy(pM); p.feet[i].position.set(feet[i].x + .05, feet[i].y - .035, feet[i].z); } }
const vv = () => [V(), V()];

// Anna on her feet: she walks to the station, scans the code with her wPhone, turns and sits down. Then the seated model takes over.
const walker = person(scene, { top: M.cardi, legs: M.trousers, skin: M.skin, hair: M.hair, shoe: M.shell, sole: M.accent, style: 'bun', collar: M.shell, long: true }); walker.g.visible = false;
{ const gold = mat('#B98A3E', { metalness: .85, roughness: .28 }); [-.042, .042].forEach((z) => { const r = add(new THREE.Mesh(new THREE.TorusGeometry(.027, .0034, 10, 36), gold), walker.head); r.position.set(.1, .012, z); r.rotation.y = Math.PI / 2; r.castShadow = false; }); box(.004, .004, .03, gold, .1, .014, 0, walker.head, .001); }
const wPhone = new THREE.Group(); walker.g.add(wPhone); box(.012, .135, .068, mat('#1E282A', { roughness: .3 }), 0, 0, 0, wPhone, .006); box(.003, .118, .058, glow('#BFE9F3'), .0075, 0, 0, wPhone, .002);
const beam = new THREE.Mesh(new THREE.CylinderGeometry(.006, .03, 1, 16, 1, true), new THREE.MeshBasicMaterial({ color: '#58E6F2', transparent: true, opacity: .4, side: THREE.DoubleSide, depthWrite: false })); scene.add(beam); beam.visible = false;
const qrGlow = add(new THREE.Mesh(new THREE.TorusGeometry(.085, .008, 8, 4), glow('#58E6F2')), base); qrGlow.position.set(.13, .52, .258); qrGlow.rotation.z = Math.PI / 4; qrGlow.castShadow = false; qrGlow.visible = false;
const wP = V(), wN = V(), wH = vv(), wF = vv(), wA = V(), wB = V();
function arrive(dt) { walker.g.visible = arriving; if (!arriving) { beam.visible = qrGlow.visible = false; return; }
  const t = arrT, sst = (a, b, x) => { const k = clamp((x - a) / (b - a)); return k * k * (3 - 2 * k); }, QX = base.position.x + .13, QZ = base.position.z + .2535;
  const A0 = [1.3, 2.7], A1 = [QX, QZ + .62], A2 = [.47, .06];      // the door side, in front of the code, in front of the chair
  let x, z, th, walk = 0, dist = 0; const TH1 = Math.PI / 2, TH2 = Math.atan2(A1[1] - A2[1], A2[0] - A1[0]);
  if (t < 3) { const k = sst(0, 3, t); x = lerp(A0[0], A1[0], k); z = lerp(A0[1], A1[1], k); th = Math.atan2(A0[1] - A1[1], A1[0] - A0[0]); th = lerp(th, TH1, sst(2.3, 3, t)); walk = Math.sin(Math.PI * clamp(t / 3)) > .12 ? 1 : .4; dist = k * 2.2; }
  else if (t < 5.2) { x = A1[0]; z = A1[1]; th = TH1; }
  else if (t < 6.8) { const k = sst(5.2, 6.8, t); x = lerp(A1[0], A2[0], k); z = lerp(A1[1], A2[1], k); th = lerp(TH1, TH2, sst(5.2, 5.7, t)); walk = 1; dist = k * .95; }
  else { const k = sst(6.8, 7.6, t); x = A2[0]; z = A2[1]; th = lerp(TH2, 0, k); walk = k < 1 ? .45 : 0; dist = k * .3; }
  const sit = sst(7.6, 8.9, t), g = walker.g; g.position.set(lerp(x, 0, sit), 0, lerp(z, 0, sit)); g.rotation.y = th;
  const ph = dist * 10.5, bob = Math.abs(Math.cos(ph)) * .012 * walk, lean = Math.sin(Math.PI * sit) * .2, scan = sst(2.7, 3.3, t) * (1 - sst(4.7, 5.3, t));
  wP.set(lerp(0, .06, sit), lerp(.9, .56, sit) + bob, 0); wN.set(wP.x + .05 + lean + scan * .05, wP.y + .44 - lean * .08, 0);
  for (let i = 0; i < 2; i++) { const a = ph + i * Math.PI, sg = i ? 1 : -1;
    wF[i].set(lerp(Math.sin(a) * .13 * walk, .47 - g.position.x, sit), .08 + Math.max(0, Math.cos(a)) * .045 * walk * (1 - sit), sg * lerp(.09, .1, sit));
    wH[i].set(lerp(.05 - Math.sin(a) * .09 * walk, .3, sit), lerp(.84, .63, sit), sg * lerp(.2, .11, sit)); }
  const hold = Math.max(scan, 1 - sst(5.6, 6.4, t)) * (t > 2.4 ? 1 : 0) || (t <= 2.4 ? .0 : 0), up = scan;      // the wPhone is in her right hand until she has scanned
  const carry = t < 6.4 ? 1 : 0; wH[1].x = lerp(wH[1].x, .31, up); wH[1].y = lerp(carry ? lerp(wH[1].y, .9, .5 * (1 - sit)) : wH[1].y, .98, up); wH[1].z = lerp(wH[1].z, .1, up);
  pose(walker, wP, wN, wH, wF); walker.head.rotation.z = -.08 - scan * .32 - Math.sin(Math.PI * sit) * .2; walker.head.rotation.y = 0;
  wPhone.visible = t < 6.4; wPhone.position.set(wH[1].x + .035, wH[1].y + .05, wH[1].z); wPhone.rotation.z = -.35 - up * .75;
  const on = t > 3.3 && t < 4.4; beam.visible = on; qrGlow.visible = t > 4.4 && t < 5.6; if (qrGlow.visible) qrGlow.scale.setScalar(1 + Math.sin((t - 4.4) * 10) * .08);
  if (on) { wA.copy(wPhone.position); g.localToWorld(wA); wB.set(QX, .52, QZ + .01); between(beam, wA, wB); beam.scale.set(1, wA.distanceTo(wB), 1); beam.material.opacity = .28 + Math.sin(t * 14) * .12; } }

// floor and two walls
fac(.45, -.3, 0, 0, 'grow', (g) => { box(7.7, .04, 6.3, FM.floor, 0, -.024, 0, g, .02); for (let i = -3; i <= 3; i++) box(.012, .004, 6.2, fm('#DCCFBB'), i * 1.02, -.003, 0, g, .001); });
fac(.45, -3.4, 0, .1, 'rise', (g) => { box(7.7, 2.7, .12, FM.wall, 0, 1.35, 0, g, .02); box(7.7, .12, .14, FM.trim, 0, .06, .01, g, .01);
  for (let i = 0; i < 4; i++) { const x = -2.55 + i * 1.7; box(1.46, 1.46, .05, FM.trim, x, 1.5, .05, g, .02); const gl = new THREE.Mesh(new THREE.PlaneGeometry(1.34, 1.34), FM.glass); gl.position.set(x, 1.5, .078); g.add(gl); box(.035, 1.34, .02, FM.trim, x, 1.5, .08, g, .005); box(1.34, .035, .02, FM.trim, x, 1.75, .08, g, .005); }
  const cl = new THREE.Group(); cl.position.set(3.45, 2.2, .07); g.add(cl); const face = cyl(.17, .17, .03, FM.trim, 0, 0, 0, cl); face.rotation.x = Math.PI / 2; const rim2 = add(new THREE.Mesh(new THREE.TorusGeometry(.17, .014, 10, 40), FM.dark), cl);
  const hh = new THREE.Group(), mh = new THREE.Group(); cl.add(hh, mh); box(.016, .09, .006, FM.dark, 0, .04, .02, hh, .003); box(.011, .13, .006, M.coral, 0, .06, .024, mh, .003); facAnim.push((T) => { mh.rotation.z = -T * .8; hh.rotation.z = -1 - T * .8 / 12; }); });
fac(-3.4, -.3, 0, .16, 'rise', (g) => { box(.12, 2.7, 6.3, FM.wall, 0, 1.35, 0, g, .02); box(.14, .12, 6.3, FM.trim, .01, .06, 0, g, .01);
  for (let i = 0; i < 3; i++) { box(.03, 1.75, 1.08, FM.trim, .065, 1.2, -2.25 + i * 1.14, g, .01); box(.02, 1.66, 1, FM.mirror, .085, 1.2, -2.25 + i * 1.14, g, .008); }
  [1.55, 2.35].forEach((z) => box(.07, 2.2, .07, M.wood, .1, 1.15, z, g, .02)); for (let i = 0; i < 9; i++) { const r = cyl(.018, .018, .8, M.wood, .12, .3 + i * .22, 1.95, g); r.rotation.x = Math.PI / 2; } });

// the Vita banner beside the station
fac(2.45, -1.3, .62, .34, 'pop', (g) => { box(.5, .03, .22, FM.dark, 0, .015, 0, g, .01); cyl(.012, .012, 1.75, FM.steel, 0, .9, -.03, g); box(.74, 1.7, .016, FM.white, 0, .95, 0, g, .008);
  sign(.72, 1.68, g, 0, .95, .0095, (x, w, h) => { x.fillStyle = LOGO_BG; x.fillRect(0, 0, w, h); if (logoReady()) { const lw = w * .86, lh = lw * logoImg.naturalHeight / logoImg.naturalWidth; x.drawImage(logoImg, (w - lw) / 2, h * .26, lw, lh); }
    x.textAlign = 'center'; x.font = '500 46px Outfit, sans-serif'; x.fillStyle = '#CFE0E3'; x.fillText('Rehab station', w * .5, h * .5);
    x.fillStyle = '#F0B95B'; x.beginPath(); x.roundRect(w * .14, h * .76, w * .72, h * .09, 60); x.fill(); x.fillStyle = '#1E282A'; x.font = '600 40px Outfit, sans-serif'; x.fillText('Book in the app', w * .5, h * .818); }); }, .5, .5);

// the physiotherapist, watching the session with a tablet
fac(-1.6, -.35, -.15, .4, 'pop', (g) => { const p = person(g, { top: FM.teal, legs: FM.navy, skin: FM.skin2, hair: FM.hairB, shoe: FM.white, sole: FM.teal, style: 'tail', collar: FM.white, badge: true }), tab = box(.03, .2, .28, FM.dark, 0, 0, 0, g, .01); const scr = box(.006, .17, .25, fm('#BFDDE3'), 0, 0, 0, g, .004);
  const P = V(), N = V(), H = vv(), F = vv(); F[0].set(0, .08, -.1); F[1].set(.03, .08, .1);
  facAnim.push((T) => { const sw = Math.sin(T * .9) * .012; P.set(sw, .93, 0); N.set(sw * 2 + .03, 1.38, 0); H[0].set(.27, 1.1 + sw, -.1); H[1].set(.27, 1.1 + sw, .1); pose(p, P, N, H, F); p.head.rotation.z = -.16 + Math.sin(T * .6) * .1; p.head.rotation.y = Math.sin(T * .37) * .25;
    tab.position.set(.3, 1.13 + sw, 0); tab.rotation.z = -.9; scr.position.set(.29, 1.145 + sw, 0); scr.rotation.z = -.9; }); }, .34);

// a gym employee beside the station: no therapist needed, they only have to reach the red button
fac(1.1, -.88, -Math.PI / 2, .5, 'pop', (g) => { const p = person(g, { top: M.accent, legs: FM.dark, skin: M.skin, hair: FM.hairD, shoe: FM.white, sole: FM.dark, style: 'short', collar: FM.white, badge: true }), P = V(), N = V(), H = vv(), F = vv(); F[0].set(0, .08, -.1); F[1].set(.04, .08, .1);
  facAnim.push((T) => { p.g.visible = stopOn; if (!stopOn) return; const k = reachK, sw = Math.sin(T * .9) * .01, bx = base.position.z - .17 + .88, bz = 1.1 - (base.position.x + .17);
    P.set(sw + k * .02, .93 - k * .08, 0); N.set(sw * 2 + .03 + k * .19, 1.38 - k * .15, k * .02); H[1].set(.06, .86 + sw, .2); H[0].set(lerp(.08, bx - .02, k), lerp(.86, stopBtn.position.y + .075, k), lerp(-.2, bz, k)); pose(p, P, N, H, F);
    p.head.rotation.z = -.1 - k * .35; p.head.rotation.y = (1 - k) * (.45 + Math.sin(T * .5) * .2); }); }, .3);

// treadmills by the window, one in use
[[2.3, 1, .46], [3.55, 0, .52]].forEach(([x, used, delay]) => fac(x, -2.3, Math.PI / 2, delay, 'pop', (g) => { box(1.55, .14, .66, FM.dark, 0, .09, 0, g, .04); box(1.3, .02, .5, FM.belt, -.05, .17, 0, g, .008);
  [-.29, .29].forEach((z) => { const u = cyl(.022, .022, 1.1, FM.steel, .62, .7, z, g); u.rotation.z = -.12; const r = cyl(.02, .02, .55, FM.steel, .4, 1.08, z, g); r.rotation.z = Math.PI / 2 - .12; }); box(.08, .26, .6, FM.dark, .7, 1.26, 0, g, .03).rotation.z = .35; box(.01, .16, .34, fm('#BFDDE3'), .665, 1.27, 0, g, .004).rotation.z = .35;
  const strips = [0, 1, 2].map(() => box(.03, .004, .48, fm('#555F61'), 0, .182, 0, g, .001));
  if (used) { const p = person(g, { top: FM.sun, legs: FM.dark, skin: M.skin, hair: FM.hairD, shoe: M.coral, sole: FM.white, style: 'short', shorts: true, band: M.coral }), P = V(), N = V(), H = vv(), F = vv();
    facAnim.push((T) => { const ph = T * 4.4; P.set(-.05, 1.1 + Math.abs(Math.cos(ph)) * .018, 0); N.set(.0, 1.55 + Math.abs(Math.cos(ph)) * .018, 0);
      for (let i = 0; i < 2; i++) { const a = ph + i * Math.PI, sg = i ? 1 : -1; F[i].set(-.05 + Math.sin(a) * .24, .26 + Math.max(0, Math.cos(a)) * .1, sg * .1); H[i].set(.06 - Math.sin(a) * .2, 1.14 + Math.abs(Math.sin(a)) * .03, sg * .24); } pose(p, P, N, H, F); }); }
  facAnim.push((T) => strips.forEach((s, i) => { s.position.x = .55 - ((T * (used ? 1.05 : 0) + i * .43) % 1.25); })); }, .75, .62));

// an exercise bike with a rider
fac(.1, -2.6, Math.PI / 2, .5, 'pop', (g) => { box(.95, .06, .12, FM.dark, .25, .03, 0, g, .02); [-.15, .68].forEach((x) => box(.1, .06, .5, FM.dark, x, .03, 0, g, .02)); const fr = cyl(.035, .035, .95, FM.white, .08, .5, 0, g); fr.rotation.z = .18; box(.26, .06, .2, FM.dark, 0, .98, 0, g, .03);
  const post = cyl(.03, .03, 1.0, FM.white, .56, .62, 0, g); post.rotation.z = -.16; const bar = cyl(.02, .02, .46, FM.dark, .64, 1.13, 0, g); bar.rotation.x = Math.PI / 2; box(.05, .14, .2, FM.dark, .66, 1.2, 0, g, .02);
  const fly = new THREE.Group(); fly.position.set(.52, .36, 0); g.add(fly); const disc = cyl(.24, .24, .07, FM.teal, 0, 0, 0, fly); disc.rotation.x = Math.PI / 2; [0, 1, 2].forEach((i) => { const s = box(.44, .03, .075, FM.white, 0, 0, 0, fly, .01); s.rotation.z = i * Math.PI / 3; });
  const crank = new THREE.Group(); crank.position.set(.2, .4, 0); g.add(crank); const cd = cyl(.09, .09, .05, FM.steel, 0, 0, 0, crank); cd.rotation.x = Math.PI / 2; box(.34, .03, .03, FM.steel, 0, 0, 0, crank, .01);
  const p = person(g, { top: FM.lilac, legs: FM.navy, skin: mat('#C98F6B', { clearcoat: .2, roughness: .6 }), hair: FM.hairD, shoe: FM.white, sole: FM.lilac, style: 'bun', stripe: FM.white }), P = V(), N = V(), H = vv(), F = vv(), ped = [box(.12, .025, .09, FM.dark, 0, 0, 0, g, .01), box(.12, .025, .09, FM.dark, 0, 0, 0, g, .01)];
  facAnim.push((T) => { const ph = -T * 3.2; fly.rotation.z = ph * 1.6; crank.rotation.z = ph; P.set(0, 1.09, 0); N.set(.2, 1.5, 0);
    for (let i = 0; i < 2; i++) { const a = ph + i * Math.PI, sg = i ? 1 : -1; F[i].set(.2 + Math.cos(a) * .16, .44 + Math.sin(a) * .16, sg * .13); ped[i].position.set(F[i].x + .03, F[i].y - .075, sg * .13); H[i].set(.62, 1.15, sg * .2); } pose(p, P, N, H, F); p.head.rotation.z = .12; }); }, .6, .6);

// dumbbell rack, bench, desk, gym balls, mats, plants, water
fac(-3.0, -1.1, Math.PI / 2, .44, 'pop', (g) => { [-.62, .62].forEach((x) => box(.05, .78, .34, FM.dark, x, .39, 0, g, .015)); [.28, .6].forEach((y, r) => { box(1.3, .03, .3, FM.steel, 0, y, 0, g, .01);
  [M.coral, FM.sun, FM.teal, FM.lilac, FM.sky].forEach((m, i) => { const x = -.5 + i * .25, s = 1 - i * .08 + r * .1, b = cyl(.016, .016, .2, FM.steel, x, y + .075, 0, g); b.rotation.x = Math.PI / 2; [-.09, .09].forEach((z) => { const e = cyl(.05 * s, .05 * s, .07, m, x, y + .075, z, g); e.rotation.x = Math.PI / 2; }); }); }); }, .8, .45);
fac(-1.55, 1.25, .5, .58, 'pop', (g) => { box(1.15, .09, .34, FM.dark, 0, .44, 0, g, .04); [-.42, .42].forEach((x) => { box(.05, .4, .3, FM.steel, x, .2, 0, g, .015); }); }, .65, .5);
fac(-2.85, .55, 0, .5, 'pop', (g) => { box(.6, .74, 1.3, FM.white, 0, .37, 0, g, .03); box(.64, .04, 1.36, M.wood, 0, .76, 0, g, .015); box(.24, .015, .34, FM.steel, .08, .79, -.2, g, .006); box(.012, .22, .34, FM.dark, -.04, .9, -.2, g, .006).rotation.z = .2;
  const s = sign(.86, .22, g, .305, .46, 0, (x, w, h) => { x.fillStyle = '#2E8C8A'; x.fillRect(0, 0, w, h); x.fillStyle = '#fff'; x.font = '600 62px Outfit, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText('Reception', w / 2, h / 2 + 4); }); s.rotation.y = Math.PI / 2; cyl(.05, .04, .1, M.coral, .1, .83, .4, g); }, .85, .9);
[[3.45, .35, .31, M.coral, .6], [3.75, -.45, .25, FM.sun, .64], [3.0, -.25, .2, FM.sky, .68]].forEach(([x, z, r, m, d]) => fac(x, z, 0, d, 'pop', (g) => { const b = ball(r, m, 0, r, 0, g); facAnim.push((T) => { b.scale.y = 1 + Math.sin(T * 1.3 + x * 3) * .012; }); }, r * 1.3));
fac(2.5, 1.35, -.35, .62, 'pop', (g) => { box(1.75, .014, .62, FM.lilac, 0, .007, 0, g, .006); const r = cyl(.075, .075, .62, FM.teal, 1.05, .075, 0, g); r.rotation.x = Math.PI / 2; const r2 = cyl(.075, .075, .62, M.coral, 1.22, .075, 0, g); r2.rotation.x = Math.PI / 2; const f = cyl(.07, .07, .42, FM.sky, -.3, .08, 0, g); f.rotation.x = Math.PI / 2; });
[[-2.95, 2.45, .54, 1], [3.95, -2.95, .6, 1.15], [-2.95, -2.95, .66, .9]].forEach(([x, z, d, s]) => fac(x, z, x, d, 'pop', (g) => { cyl(.19, .14, .34, FM.pot, 0, .17, 0, g); const top = new THREE.Group(); top.position.y = .34; g.add(top);
  for (let i = 0; i < 9; i++) { const a = i * 2.4, t = .25 + (i % 3) * .2, l = ball(1, i % 2 ? FM.leaf : FM.leaf2, Math.cos(a) * t * .28, .3 + (i % 4) * .13, Math.sin(a) * t * .28, top); l.scale.set(.06, .3, .13); l.rotation.set(Math.sin(a) * t, -a, -Math.cos(a) * t); }
  g.scale.setScalar(s); facAnim.push((T) => { top.rotation.z = Math.sin(T * .8 + x) * .03; top.rotation.x = Math.cos(T * .6 + z) * .03; }); }, .4));
fac(-3.02, -2.25, 0, .6, 'pop', (g) => { box(.34, 1.0, .34, FM.white, 0, .5, 0, g, .03); cyl(.13, .13, .36, FM.sky, 0, 1.2, 0, g).material = mat('#9CCBE6', { roughness: .1, transmission: .4, transparent: true, opacity: .85 }); box(.1, .08, .02, FM.dark, .18, .7, 0, g, .01); }, .4);

const back = (k) => { const c = k - 1; return 1 + 2.4 * c * c * c + 1.4 * c * c; };
function facility(dt, T) { facT = facT || 0; facP = FREEZE ? facT : clamp(facP + (facT > facP ? dt / 2.2 : -dt / .8)); if (facP <= 0 && !FAC[0].g.visible) return;
  for (const f of FAC) { const k = clamp((facP - f.delay) / .3), g = f.g; g.visible = k > .001; if (!g.visible) continue; const b = f.base || (f.base = g.scale.x);
    if (f.mode === 'pop') g.scale.setScalar(Math.max(.001, back(k)) * b); else if (f.mode === 'rise') g.scale.y = Math.max(.001, ease(k)); else { const s = Math.max(.001, ease(k)); g.scale.set(s, 1, s); } }
  for (const fn of facAnim) fn(T); }

// ---------- every frame ----------
const H = V(), Ht = V(), S = V(), Eh = V(), look = V(), sm = { lean: 0, th: .07, look: 0 }, COLS = { ok: '#58E6F2', hold: '#F5B43C', load: '#FF7A5E' }, cT = new THREE.Color();
let last = performance.now(), T = 0, fAcc = 0, fN = 0, cyc = 0; let voff = -.09;
function frame(now) {
  requestAnimationFrame(frame); if (document.hidden || !seen) { last = now; return; }
  const raw = (now - last) / 1000, dt = Math.min(.05, raw); last = now; T += dt;
  { const sst = (a, b, x) => { const k = clamp((x - a) / (b - a)); return k * k * (3 - 2 * k); };      // 0-2.2 s the exercise runs, the hand goes out, 2.9 s the button is down, 5.8 s it is released
    if (stopOn && !FREEZE) stopT = (stopT + dt) % 8; halted = stopOn && (FREEZE ? +FREEZE > .5 : stopT > 2.9 && stopT < 5.8); reachK = !stopOn ? 0 : FREEZE ? (+FREEZE > .5 ? 1 : 0) : sst(2.1, 2.9, stopT) * (1 - sst(3.6, 4.3, stopT));
    stopBtn.position.y = lerp(stopBtn.position.y, halted ? .678 : .69, clamp(dt * 20)); stopHalo.visible = halted; if (halted) stopHalo.scale.setScalar(1 + Math.sin(T * 6) * .12); }
  { const was = arriving; if (ARRQ && arrOn) arrT = +ARRQ; else if (arrOn && !FREEZE && arrT < ARR_END) arrT += dt; arriving = arrOn && (ARRQ ? true : !FREEZE && arrT < ARR_END);
    if (was && !arriving) { blendT = 0; blendFrom = H.clone(); exT = 0; cyc = 0; trailN = 0; const v = VIEWS[ex]; view.taz = v[0]; view.tel = v[1]; view.tdist = v[2]; }
    if (arriving) { exT = 0; const v = VIEWS.arrive; view.taz = v[0]; view.tel = v[1]; view.tdist = v[2]; } annaG.visible = ovG.visible = !arriving; if (was !== arriving) document.documentElement.classList.toggle('arr', arriving); arrive(dt); }
  if (blendT < 1.4 && !arriving) blendT += dt; if (!paused && !halted && !arriving && blendT >= 1.4) exT += dt;
  if (T > 2.5 && !FREEZE) { fAcc += raw; if (++fN >= 45) { const avg = fAcc / fN; fAcc = fN = 0; if (avg > 1 / 44 && dpr > 1) { dpr = Math.max(1, dpr - .25); renderer.setPixelRatio(dpr); } } }
  const d = EX[ex];
  const t = FREEZE ? +FREEZE : (exT / d.period) % 1, s = d.at(t), f = (r) => (FREEZE || snap ? 1 : 1 - Math.exp(-dt * r));
  const isLeg = !!d.leg, travel = isLeg !== wasLeg || exT < .6 ? 5 : 18; wasLeg = isLeg;      // changing exercise: the arm travels to its new place
  if (arriving) { const g = (arrT - 8.3) / 1.5;      // she sits first (7.6-8.9 s); then the arm comes to her hand in a slow arc
    if (g <= 0) { Ht.set(.6, .82, -.34); H.lerp(Ht, f(4)); } else { const k = g >= 1 ? 1 : g * g * (3 - 2 * g); Ht.set(lerp(.6, .31, k), lerp(.82, .62, k) + Math.sin(Math.PI * k) * .09, lerp(-.34, .11, k)); H.copy(Ht); } }
  else if (blendT < 1.4) { const k0 = blendT / 1.4, k = k0 * k0 * (3 - 2 * k0); H.copy(blendFrom).lerp(Ht.set(s.x, s.y, s.z), k); }      // together they lift the handle to the start of the first rep
  else { Ht.set(s.x, s.y, s.z); H.lerp(Ht, f(travel)); }
  tA.set(d.base ? d.base[0] : BASE0.x, 0, d.base ? d.base[1] : BASE0.z); base.position.lerp(tA, f(3.5)); SHO.set(base.position.x, .9, base.position.z);

  // the patient: the body leans into the movement, the head follows the hand
  sm.lean = lerp(sm.lean, s.lean, f(9)); sm.look = lerp(sm.look, s.look || 0, f(4)); torso.rotation.z = -sm.lean; torso.position.y = HIP.y + Math.sin(T * 1.4) * .003; head.rotation.z = sm.look; torso.updateMatrixWorld(true);
  sm.th = lerp(sm.th, isLeg ? s.th : .07, f(isLeg ? 16 : 5)); ANK.set(KNEE_R.x + SHIN * Math.sin(sm.th), KNEE_R.y - SHIN * Math.cos(sm.th), .1); CUFFP.set(KNEE_R.x + CUFF_AT * Math.sin(sm.th), KNEE_R.y - CUFF_AT * Math.cos(sm.th), .1);
  between(shinR, KNEE_R, ANK); footR.position.copy(ANK); footR.rotation.z = sm.th; cuff.position.copy(CUFFP); cuff.quaternion.copy(shinR.quaternion);
  const handAt = isLeg ? REST_R : H;
  S.copy(SH_R); torso.localToWorld(S); elbow(Eh, S, handAt, UP, FORE, POLE_R); tC.copy(handAt).sub(Eh).normalize(); armR.hand.position.copy(Eh).addScaledVector(tC, FORE - (isLeg ? .01 : .05)); armR.hand.scale.setScalar(isLeg ? 1 : .86); armR.sh.position.copy(S);
  between(armR.up, S, Eh); between(armR.fore, Eh, armR.hand.position); SR.copy(S); ER.copy(Eh); HR.copy(armR.hand.position); armR.el.position.copy(Eh); armR.cf.position.copy(armR.hand.position).addScaledVector(tC, -.042); armR.cf.quaternion.copy(armR.fore.quaternion);
  S.copy(SH_L); torso.localToWorld(S); elbow(Eh, S, REST_L, UP, FORE, POLE_L); armL.sh.position.copy(S); armL.hand.position.copy(REST_L); between(armL.up, S, Eh); between(armL.fore, Eh, REST_L); armL.el.position.copy(Eh); tC.copy(REST_L).sub(Eh).normalize(); armL.cf.position.copy(REST_L).addScaledVector(tC, -.042); armL.cf.quaternion.copy(armL.fore.quaternion);

  // the robot: its wrist sits just beside the point it holds, on its own side; shoulder and elbow follow from that
  const P = isLeg && travel > 10 ? CUFFP : H, gap = isLeg ? .07 : 0; U.set(SHO.x - P.x, 0, SHO.z - P.z).normalize(); W.copy(P).addScaledVector(U, WR + gap); elbow(E, SHO, W, L1, L2, POLE_ROB);
  Nrm.copy(W).sub(SHO).cross(POLE_ROB).normalize();      // the axis the shoulder and the elbow turn about
  between(rob.l1, tB.copy(SHO).addScaledVector(Nrm, OFF), tC.copy(E).addScaledVector(Nrm, OFF)); between(rob.l2, E, W); rob.elb.position.copy(E); rob.wr.position.copy(W);      // the upper link rides on the side of both drums
  rob.capS.position.copy(SHO).addScaledVector(Nrm, OFF * .5); rob.capS.quaternion.setFromUnitVectors(YA, Nrm); rob.capE.position.copy(E).addScaledVector(Nrm, OFF * .5); rob.capE.quaternion.copy(rob.capS.quaternion); rob.capW.position.copy(W); rob.capW.quaternion.copy(rob.capS.quaternion);
  between(rob.l3, W, tA.copy(P).addScaledVector(U, .04 + gap)); rob.flange.position.copy(P).addScaledVector(U, .034 + gap); rob.flange.quaternion.setFromUnitVectors(YA, U); rob.ring.position.copy(P).addScaledVector(U, .048 + gap); rob.ring.quaternion.copy(rob.flange.quaternion);
  rob.grip.position.copy(P); rob.top.position.set(P.x, P.y + .078, P.z); gripHand.visible = !isLeg && rob.grip.visible; if (gripHand.visible) { gripHand.position.copy(P); gripHand.rotation.y = Math.atan2(ER.z - P.z, P.x - ER.x); }
  const pulse = .75 + Math.sin(T * 3) * .25; rob.ring.material.color.lerp(cT.set(halted ? '#FF3B2E' : COLS[s.state]), f(halted ? 30 : 8)); led.material.color.copy(rob.ring.material.color).multiplyScalar(pulse);

  // the path of the hand, the goal, the dot to follow, the live number
  if (trail.visible && !paused) { if (trailN < TRAIL) trailN++; trailPos.copyWithin(3, 0, (trailN - 1) * 3); trailPos[0] = H.x + d.off[0]; trailPos[1] = H.y + d.off[1]; trailPos[2] = H.z + d.off[2]; trailGeo.setDrawRange(0, trailN); trailGeo.attributes.position.needsUpdate = true; }
  drawTrail();
  { const tg = TARGET[ex], a = clamp(tg.act(s, t)); actS = lerp(actS, a, f(8)); const beat = .85 + Math.sin(T * 5) * .15; for (const k in PARTS) { const w = tg.parts[k] || 0, m = PARTS[k].material; m.emissiveIntensity = lerp(m.emissiveIntensity, w * (k === 'head' ? .15 + actS * .8 : .06 + actS * .16) * beat, f(6)); } const k10 = f(10); brainT = 0; tg.mus.forEach((m, i) => { const v = clamp(m[3](a, t, s)); mv[i] = lerp(mv[i], v, k10); const tr = 'scaleX(' + (.03 + mv[i] * .97).toFixed(3) + ')'; bars[i].forEach((b) => { b.style.transform = tr; }); if (ACT[m[0]]) ACT[m[0]].t = v; else brainT = v; });
    brainA = lerp(brainA, brainT, k10); for (const id in ACT) ACT[id].a = lerp(ACT[id].a, ACT[id].t, k10); muscles3D(); drawMap(sm.lean); joints(s); }
  if (goal.visible) { goal.scale.setScalar(1 + Math.sin(T * 4) * .05 + (s.hit ? .25 : 0)); goal.material.color.set(s.hit ? '#2F9DB6' : '#58C4D4'); }
  if (d.chase) { const p = d.path(t); chase.position.set(p[0] + .07, p[1] + .02, p[2] + .05); chaseHalo.position.copy(chase.position); chaseHalo.scale.setScalar(1 + Math.sin(T * 5) * .15); }
  liveL.sp.visible = !!s.live; if (s.live) { liveL.sp.position.set(H.x + .12, H.y + .2, H.z); liveL.set(s.value + ' ' + s.live); }

  // the numbers on the screen
  if (s.value !== lastVal) { lastVal = s.value; el.val.textContent = s.value; }
  const sayNow = arriving ? (arrT < 3 ? 'Anna arrives for her session.' : arrT < 4.4 ? 'Scanning the station…' : arrT < 7.4 ? 'Station found. Hi Anna, your plan is loaded.' : 'Take a seat. We start with the forward reach.') : halted ? 'Emergency stop pressed. The arm holds still.' : s.say; if (sayNow !== lastSay && T - sayAt > .3) { lastSay = sayNow; sayAt = T; el.say.style.opacity = 0; setTimeout(() => { el.say.textContent = sayNow; el.say.style.opacity = 1; }, FREEZE ? 0 : 180); }

  // the camera
  facility(dt, T); if (active && active.dataset.cycle && !FREEZE && !paused && !arriving) { cyc += dt; if (cyc > 5.5) { cyc = 0; const nx = ORDER[(ORDER.indexOf(ex) + 1) % ORDER.length], v = VIEWS[nx]; choose(nx); view.taz = v[0]; view.tel = v[1]; view.tdist = v[2]; } } else cyc = 0; view.idle += dt; const drift = FREEZE ? 0 : Math.sin(T * .22) * .1 * clamp((view.idle - 1.5) / 2); view.az = lerp(view.az, view.taz + drift, f(2.6)); view.el = lerp(view.el, view.tel, f(2.6)); view.dist = lerp(view.dist, view.tdist, f(2.6));
  const narrow = phone, dist = view.dist * (narrow ? (cam.aspect < 1.15 ? 1.12 : .9) : 1.16); look.set(narrow ? .42 : .5, narrow ? .66 : .74, -.05);
  cam.position.set(look.x + Math.sin(view.az) * Math.cos(view.el) * dist, look.y + Math.sin(view.el) * dist, look.z + Math.cos(view.az) * Math.cos(view.el) * dist); cam.lookAt(look);
  voff = lerp(voff, BARE ? 0 : document.documentElement.classList.contains('nohud') ? -.17 : -.09, FREEZE ? 1 : 1 - Math.exp(-dt * 3)); if (!narrow) cam.setViewOffset(VW, VH, VW * voff, VH * -.03, VW, VH); else cam.clearViewOffset();
  snap = false; renderer.render(scene, cam);
}
requestAnimationFrame((n) => { last = n; frame(n); });
