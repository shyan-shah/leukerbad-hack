
// ---------- website hero (site only): the robot alone on its trolley waves at you, then grabs the next section and pulls it up ----------
const HERO = { on: false, vis: new Map() };
const catcher = new THREE.Mesh(new THREE.PlaneGeometry(8, 8), new THREE.ShadowMaterial({ opacity: .14 }));
catcher.rotation.x = -Math.PI / 2; catcher.position.y = .001; catcher.receiveShadow = true; catcher.visible = false; scene.add(catcher);
// a robot hand on the tool flange: palm, four two-jointed fingers and a thumb. Local frame: fingers along +Y, palm faces +Z.
function makeHand() {
  const HAND = new THREE.Group(), fingers = [];
  const shell = M.arm, dark = M.joint, pad = glow('#5FE0A0');
  const mesh = (geo, m, x = 0, y = 0, z = 0, parent = HAND) => { const o = new THREE.Mesh(geo, m); o.position.set(x, y, z); o.castShadow = true; parent.add(o); return o; };
  const seg = (r, len) => new THREE.CapsuleGeometry(r, len, 6, 14);
  mesh(new THREE.CylinderGeometry(.05, .056, .05, 32), dark, 0, .012, 0);                       // wrist drum, on the flange
  mesh(new THREE.TorusGeometry(.053, .004, 8, 40), pad, 0, .03, 0).rotation.x = Math.PI / 2;   // light ring at the wrist
  mesh(new RoundedBoxGeometry(.13, .11, .05, 4, .018), shell, 0, .09, 0);                       // palm
  mesh(new RoundedBoxGeometry(.1, .07, .006, 3, .003), dark, 0, .09, .026);                     // dark palm plate
  [-.045, -.015, .015, .045].forEach((x, i) => {
    const len = i === 0 || i === 3 ? .036 : .044, k = new THREE.Group(); k.position.set(x, .148, 0); HAND.add(k);
    mesh(new THREE.SphereGeometry(.015, 16, 12), dark, 0, 0, 0, k);
    mesh(seg(.0125, len), shell, 0, len / 2 + .006, 0, k);
    const k2 = new THREE.Group(); k2.position.set(0, len + .014, 0); k.add(k2);
    mesh(new THREE.SphereGeometry(.0128, 16, 12), dark, 0, 0, 0, k2);
    mesh(seg(.0115, len * .8), shell, 0, len * .4 + .006, 0, k2);
    mesh(new THREE.SphereGeometry(.0085, 12, 10), pad, 0, len * .8 + .014, .006, k2);
    fingers.push([k, k2]); });
  const th = new THREE.Group(); th.position.set(-.068, .075, .01); th.rotation.z = .9; HAND.add(th);
  mesh(new THREE.SphereGeometry(.016, 16, 12), dark, 0, 0, 0, th); mesh(seg(.013, .04), shell, 0, .03, 0, th);
  const th2 = new THREE.Group(); th2.position.set(0, .058, 0); th.add(th2); mesh(new THREE.SphereGeometry(.013, 16, 12), dark, 0, 0, 0, th2); mesh(seg(.012, .03), shell, 0, .024, 0, th2); mesh(new THREE.SphereGeometry(.0085, 12, 10), pad, 0, .045, .006, th2);
  fingers.thumb = [th, th2]; return { g: HAND, f: fingers }; }
const { g: HAND, f: fingers } = makeHand(); HAND.visible = false; scene.add(HAND);
function curl(c) { fingers.forEach(([a, b], i) => { a.rotation.x = c * (1.15 + i * .05); b.rotation.x = c * 1.35; }); fingers.thumb[0].rotation.x = c * .9; fingers.thumb[1].rotation.x = c * 1.1; }
const keepHero = new Set([base, catcher, HAND, ...Object.values(rob)]), bg0 = scene.background;
function heroMode(on) {
  if (HERO.on === on) return; HERO.on = on;
  if (on) { scene.children.forEach((c) => { HERO.vis.set(c, c.visible); if (!c.isLight) c.visible = keepHero.has(c); }); scene.background = null; rob.grip.visible = rob.top.visible = false; }
  else { HERO.vis.forEach((v, c) => { c.visible = v; }); HERO.vis.clear(); scene.background = bg0; catcher.visible = false; HAND.visible = false; }
}
// the arm's tool flange goes to P; same joints as in the exercises
function robotTo(P, load) {
  base.position.copy(BASE0); SHO.set(BASE0.x, .9, BASE0.z);
  U.set(SHO.x - P.x, 0, SHO.z - P.z); if (U.lengthSq() < 1e-6) U.set(-1, 0, 0); U.normalize();
  W.copy(P).addScaledVector(U, WR); elbow(E, SHO, W, L1, L2, POLE_ROB); Nrm.copy(W).sub(SHO).cross(POLE_ROB).normalize();
  between(rob.l1, tB.copy(SHO).addScaledVector(Nrm, OFF), tC.copy(E).addScaledVector(Nrm, OFF)); between(rob.l2, E, W); rob.elb.position.copy(E); rob.wr.position.copy(W);
  rob.capS.position.copy(SHO).addScaledVector(Nrm, OFF * .5); rob.capS.quaternion.setFromUnitVectors(YA, Nrm); rob.capE.position.copy(E).addScaledVector(Nrm, OFF * .5); rob.capE.quaternion.copy(rob.capS.quaternion); rob.capW.position.copy(W); rob.capW.quaternion.copy(rob.capS.quaternion);
  between(rob.l3, W, tA.copy(P).addScaledVector(U, .04)); rob.flange.position.copy(P).addScaledVector(U, .034); rob.flange.quaternion.setFromUnitVectors(YA, U); rob.ring.position.copy(P).addScaledVector(U, .048); rob.ring.quaternion.copy(rob.flange.quaternion);
  rob.grip.visible = rob.top.visible = false;
  rob.ring.material.color.set(RING.ok).lerp(cT.set(RING.load), clamp(load)); led.material.color.copy(rob.ring.material.color);
}
const HAZ = .62, HD = V(Math.sin(HAZ), 0, Math.cos(HAZ)), HR = V(Math.cos(HAZ), 0, -Math.sin(HAZ));      // towards the viewer, and to the viewer's right
const HC = V(), HG = V(), HU = V(), HP = V(), HQ = V(), heroLook = V(), camR = V();
HC.copy(BASE0).addScaledVector(HD, .5); HC.y = 1.3;      // where it waves
HG.copy(BASE0).addScaledVector(HD, .52).addScaledVector(HR, -.5); HG.y = .42;       // where it grabs the edge of the next section
HU.copy(BASE0).addScaledVector(HD, .3).addScaledVector(HR, -.25); HU.y = 1.64;      // how high it pulls
const sstep = (a, b, x) => ease((x - a) / (b - a));
function wavePoint(out, now, still) {
  const cyc = (now / 1000) % 3.6, on = still ? 0 : (cyc < 2.4 ? Math.sin(Math.PI * cyc / 2.4) : 0);      // wave for 2.4 s, rest 1.2 s
  const a = on * .62 * Math.sin(now / 1000 * 7);
  out.tilt = a; return out.copy(HC).addScaledVector(HR, Math.sin(a) * .34).add(V(0, (Math.cos(a) - 1) * .34 + Math.sin(now / 900) * .015, 0));
}
const qWave = new THREE.Quaternion(), qGrab = new THREE.Quaternion(), qTilt = new THREE.Quaternion(), mB = new THREE.Matrix4(), bx = V(), by = V(), bz = V(), GRIP = V(0, .175, .05), gripW = V();
function basis(q, up) { by.copy(up); bz.copy(HD); bx.crossVectors(by, bz).normalize(); bz.crossVectors(bx, by); mB.makeBasis(bx, by, bz); return q.setFromRotationMatrix(mB); }
basis(qWave, V(0, 1, 0)); basis(qGrab, V(0, -1, 0));
function placeHand(P, turn, close, tilt) {
  HAND.visible = true; HAND.position.copy(P);
  HAND.quaternion.copy(qWave).slerp(qGrab, turn); qTilt.setFromAxisAngle(HD, tilt); HAND.quaternion.premultiply(qTilt);
  curl(close); HAND.updateMatrixWorld(true); return HAND.localToWorld(gripW.copy(GRIP));
}
// where the grip sits when the hand hangs down from point P (closed around the handle)
const gripBelow = (P, out) => out.copy(P).add(V(0, -.175, 0)).addScaledVector(HD, .05);
const tG = V(), tU = V();
function toScreen(p, w, h) { HQ.copy(p).project(cam); return [(HQ.x + 1) / 2 * w, (1 - HQ.y) / 2 * h]; }
function heroCam(w, h) {
  const narrow = w / h < .95, el = .14, dist = narrow ? 6.2 : 4.2, tgt = V(BASE0.x, narrow ? .6 : .8, BASE0.z);
  cam.position.set(tgt.x + Math.sin(HAZ) * Math.cos(el) * dist, tgt.y + Math.sin(el) * dist, tgt.z + Math.cos(HAZ) * Math.cos(el) * dist);
  camR.copy(HR); heroLook.copy(tgt);
  if (!narrow) heroLook.addScaledVector(camR, -dist * Math.min(.27, .125 * (w / h)));      // the robot sits in the right half next to the text
  else { heroLook.y += .78; heroLook.addScaledVector(camR, -.32); }                                                               // on a phone it stands below the text
  cam.lookAt(heroLook);
}
// p: 0..1 scroll through the pinned hero. Returns where the hand, the grab point and the top point are on screen.
function hero(el, p, now, still) {
  heroMode(true); if (canvas.parentNode !== el) { el.appendChild(canvas); el.classList.add('has3d'); }
  const w = Math.max(1, el.clientWidth), h = Math.max(1, el.clientHeight); fit(w, h); heroCam(w, h);
  catcher.visible = true;
  const reach = sstep(.02, .3, p), pull = sstep(.36, .8, p);
  const wa = wavePoint(HP, now, still || p > .02);
  if (p < .36) HP.lerp(HG, reach); else HP.copy(HG).lerp(HU, pull);
  const load = p < .3 ? 0 : p < .36 ? (p - .3) / .06 : 1;
  robotTo(HP, load);
  const turn = sstep(.04, .26, p), close = p < .02 ? .08 + .06 * Math.sin(now / 300) : p < .28 ? .05 : sstep(.28, .36, p);      // open while waving, closes on the handle
  const g = placeHand(HP, turn, close, -(HP.tilt || 0) * .8 * (1 - turn));
  renderer.render(scene, cam);
  return { hand: toScreen(g, w, h), grab: toScreen(gripBelow(HG, tG), w, h), top: toScreen(gripBelow(HU, tU), w, h), wave: toScreen(HAND.localToWorld(V(0, .24, 0)), w, h), waving: p < .02 };
}
{ const show0 = window.vita3d.show; window.vita3d.show = (el, fig, t) => { heroMode(false); show0(el, fig, t); }; window.vita3d.hero = hero; }
