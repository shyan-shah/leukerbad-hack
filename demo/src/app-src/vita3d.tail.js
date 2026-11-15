
// ---------- how each exercise moves: where the robot holds her hand (or the cuff on her shin) at a moment t of one repetition ----------
const X0 = .33, Z0 = .2, SHW = V(.02, .955, .175), TAU = Math.PI * 2;
const there = (t, a, b, c) => (t < a ? ease(t / a) : t < b ? 1 : t < c ? 1 - ease((t - b) / (c - b)) : 0);      // out, hold, back, rest
const press = (t) => (t < .12 ? 0 : t < .45 ? ease((t - .12) / .33) : t < .72 ? 1 : t < .88 ? 1 - ease((t - .72) / .16) : 0);      // a strength test: build up, hold, let go
const MOV = {
  reach: { view: [.62, .2, 4.3], at(t) { const k = there(t, .42, .56, .92); return { x: lerp(X0, .74, k), y: lerp(.95, .98, k) + Math.sin(k * Math.PI) * .025, z: Z0, lean: k * .38 }; } },
  circle: { view: [1.02, .24, 4.2], at(t) { const a = t * TAU; return { x: .55, y: .99 + Math.sin(a) * .13, z: Z0 + Math.cos(a) * .13, lean: .14 }; } },
  trace: { view: [1.02, .2, 4.2], at(t) { const a = t * TAU; return { x: .55, y: .99 + Math.sin(a * 2) * .085, z: Z0 + Math.sin(a) * .18, lean: .14 }; } },
  lift: { view: [.42, .15, 4.4], at(t) { const k = there(t, .4, .6, .93), a = lerp(.87, 2.05, k); return { x: SHW.x + .52 * Math.sin(a), y: SHW.y - .52 * Math.cos(a), z: Z0, lean: -.04 * k, look: .25 * k }; } },
  push: { view: [.55, .17, 4.2], at(t) { const k = there(t, .4, .5, .9); return { x: lerp(.4, .68, k), y: .97, z: Z0, lean: .06 + .24 * k }; } },
  pull: { view: [.55, .17, 4.2], at(t) { const k = there(t, .4, .5, .9); return { x: lerp(.68, .4, k), y: .97, z: Z0, lean: .3 - .26 * k }; } },
  pushhold: { view: [.55, .17, 4.2], push: V(1, 0, 0), at(t) { const f = press(t), s = f * Math.sin(t * 190) * .0025; return { x: .56 + f * .012 + s, y: .97, z: Z0, lean: .16 + f * .09, load: f }; } },
  rot: { view: [1.0, .34, 3.9], pole: V(-.45, -1, .1), at(t) { const k = there(t, .4, .55, .92), p = lerp(.05, 1.0, k); return { x: .08 + .25 * Math.cos(p), y: .8, z: .2 + .25 * Math.sin(p), lean: .03 }; } },
  knee: { view: [.36, .13, 4.3], leg: true, at(t) { const k = there(t, .4, .55, .92); return { th: lerp(.15, 1.25, k), lean: -.03 * k, look: -.3, load: k }; } },
  kneebend: { view: [.36, .13, 4.3], leg: true, at(t) { const k = there(t, .4, .55, .92); return { th: lerp(.55, -.28, k), lean: -.02, look: -.3 }; } },
  kneehold: { view: [.36, .13, 4.3], leg: true, push: V(Math.cos(.9), Math.sin(.9), 0), at(t) { const f = press(t); return { th: .9 + f * .02 + f * Math.sin(t * 190) * .004, lean: -.03 - f * .03, look: -.3, load: f }; } },
};
const LEGBASE = V(.8, 0, -.42), H = V(), S = V(), Eh = V(), look = V(), cT = new THREE.Color(), RING = { ok: '#58E6F2', load: '#FF7A5E' };
cuff.visible = false;
function pose(fig, t, lv) { const d = MOV[fig] || MOV.reach, s = lv ? liveAt(fig, lv) : d.at(t), isLeg = !!d.leg;      // lv: the arm's real position (see "live" below) instead of a moment t of the loop
  base.position.copy(isLeg ? LEGBASE : BASE0); SHO.set(base.position.x, .9, base.position.z);
  torso.rotation.z = -s.lean; head.rotation.z = s.look || 0; torso.updateMatrixWorld(true);
  const th = isLeg ? s.th : .07; ANK.set(KNEE_R.x + SHIN * Math.sin(th), KNEE_R.y - SHIN * Math.cos(th), .1); CUFFP.set(KNEE_R.x + CUFF_AT * Math.sin(th), KNEE_R.y - CUFF_AT * Math.cos(th), .1);
  between(shinR, KNEE_R, ANK); footR.position.copy(ANK); footR.rotation.z = th; cuff.visible = isLeg; cuff.position.copy(CUFFP); cuff.quaternion.copy(shinR.quaternion);
  if (!isLeg) H.set(s.x, s.y, s.z); const handAt = isLeg ? REST_R : H; shown.copy(isLeg ? CUFFP : H);
  S.copy(SH_R); torso.localToWorld(S); elbow(Eh, S, handAt, UP, FORE, d.pole || POLE_R); tC.copy(handAt).sub(Eh).normalize(); armR.hand.position.copy(Eh).addScaledVector(tC, FORE - (isLeg ? .01 : .05)); armR.hand.scale.setScalar(isLeg ? 1 : .86); armR.sh.position.copy(S);
  between(armR.up, S, Eh); between(armR.fore, Eh, armR.hand.position); armR.el.position.copy(Eh); armR.cf.position.copy(armR.hand.position).addScaledVector(tC, -.042); armR.cf.quaternion.copy(armR.fore.quaternion);
  const ex = Eh.x, ez = Eh.z;
  S.copy(SH_L); torso.localToWorld(S); elbow(Eh, S, REST_L, UP, FORE, POLE_L); armL.sh.position.copy(S); armL.hand.position.copy(REST_L); between(armL.up, S, Eh); between(armL.fore, Eh, REST_L); armL.el.position.copy(Eh); tC.copy(REST_L).sub(Eh).normalize(); armL.cf.position.copy(REST_L).addScaledVector(tC, -.042); armL.cf.quaternion.copy(armL.fore.quaternion);
  // the robot: its wrist sits just beside the point it holds; shoulder and elbow follow from that
  const P = isLeg ? CUFFP : H, gap = isLeg ? .07 : 0; U.set(SHO.x - P.x, 0, SHO.z - P.z).normalize(); W.copy(P).addScaledVector(U, WR + gap); elbow(E, SHO, W, L1, L2, POLE_ROB);
  Nrm.copy(W).sub(SHO).cross(POLE_ROB).normalize();
  between(rob.l1, tB.copy(SHO).addScaledVector(Nrm, OFF), tC.copy(E).addScaledVector(Nrm, OFF)); between(rob.l2, E, W); rob.elb.position.copy(E); rob.wr.position.copy(W);
  rob.capS.position.copy(SHO).addScaledVector(Nrm, OFF * .5); rob.capS.quaternion.setFromUnitVectors(YA, Nrm); rob.capE.position.copy(E).addScaledVector(Nrm, OFF * .5); rob.capE.quaternion.copy(rob.capS.quaternion); rob.capW.position.copy(W); rob.capW.quaternion.copy(rob.capS.quaternion);
  between(rob.l3, W, tA.copy(P).addScaledVector(U, .04 + gap)); rob.flange.position.copy(P).addScaledVector(U, .034 + gap); rob.flange.quaternion.setFromUnitVectors(YA, U); rob.ring.position.copy(P).addScaledVector(U, .048 + gap); rob.ring.quaternion.copy(rob.flange.quaternion);
  rob.grip.visible = rob.top.visible = gripHand.visible = !isLeg; rob.grip.position.copy(P); rob.top.position.set(P.x, P.y + .078, P.z); if (!isLeg) { gripHand.position.copy(P); gripHand.rotation.y = Math.atan2(ez - P.z, P.x - ex); }
  rob.ring.material.color.set(RING.ok).lerp(cT.set(RING.load), clamp(s.load || 0)); led.material.color.copy(rob.ring.material.color);
  if (lv) liveGuides(fig, d, s, lv); else guides(fig, d, t, s);
  // the camera: each exercise has its own angle, with a slow sway so the scene feels alive
  const v = d.view, az = v[0] + Math.sin(swayAt(lv) / 4500) * .05, el = v[1], dist = v[2] * zoom * (cam.aspect < 1 ? 1.12 : 1); look.set(.44, .68, -.06);
  cam.position.set(look.x + Math.sin(az) * Math.cos(el) * dist, look.y + Math.sin(el) * dist, look.z + Math.cos(az) * Math.cos(el) * dist); cam.lookAt(look); }

// ---------- motion lines: dark dots show the whole movement, a green tail shows where the hand (or foot) has just been, an arrow shows where it goes next ----------
const OFFH = V(0, -.07, .09), OFFL = V(.02, 0, .13), GD = 46, TD = 20, dotGeo = new THREE.SphereGeometry(1, 12, 8), mtx = new THREE.Matrix4(), quiet = (m) => { m.castShadow = m.receiveShadow = false; m.frustumCulled = false; m.renderOrder = 10; m.material.depthTest = false; scene.add(m); return m; };      // drawn on top, so the body never hides them
const gDots = quiet(new THREE.InstancedMesh(dotGeo, new THREE.MeshBasicMaterial({ color: '#1E282A' }), GD)), tDots = quiet(new THREE.InstancedMesh(dotGeo, new THREE.MeshBasicMaterial({ color: '#1997B3' }), TD));
const arrowMat = new THREE.MeshBasicMaterial({ color: '#1E282A' }), arrow = quiet(new THREE.Mesh(new THREE.ConeGeometry(.028, .07, 20), arrowMat));
const pA = V(), pB = V(), pC = V(), paths = {};
function pt(d, t, out) { const s = d.at(((t % 1) + 1) % 1); return d.leg ? out.set(KNEE_R.x + SHIN * Math.sin(s.th), KNEE_R.y - SHIN * Math.cos(s.th), .1).add(OFFL) : out.set(s.x, s.y, s.z).add(OFFH); }
function pathOf(fig, d) { if (paths[fig]) return paths[fig]; const a = [];
  if (d.push) { pt(d, 0, pA); for (let i = 0; i < GD; i++) a.push(pA.clone().addScaledVector(d.push, i / (GD - 1) * .15)); }
  else for (let i = 0; i < GD; i++) a.push(pt(d, i / GD, V()));
  return (paths[fig] = a); }
function guides(fig, d, t, s) { const a = pathOf(fig, d);
  a.forEach((p, i) => { mtx.makeScale(.0088, .0088, .0088).setPosition(p); gDots.setMatrixAt(i, mtx); }); gDots.instanceMatrix.needsUpdate = true;
  if (d.push) {      // a strength test: the arrow at the end of the line shows which way to push, and turns red while she pushes
    tDots.count = 0; const k = s.load || 0; arrow.visible = true; arrow.position.copy(a[GD - 1]).addScaledVector(d.push, .03); arrow.quaternion.setFromUnitVectors(YA, d.push); arrow.scale.setScalar(1 + k * .35); arrowMat.color.set('#1E282A').lerp(cT.set('#E8472B'), k); return; }
  tDots.count = TD; for (let i = 0; i < TD; i++) { pt(d, t - i * .011, pB); const r = .014 * (1 - i / TD) + .004; mtx.makeScale(r, r, r).setPosition(pB); tDots.setMatrixAt(i, mtx); } tDots.instanceMatrix.needsUpdate = true;
  pt(d, t + .02, pA); pt(d, t + .07, pC); const dir = pC.sub(pA), len = dir.length(); arrow.visible = len > .006; arrowMat.color.set('#0E657A'); arrow.scale.setScalar(1);
  if (arrow.visible) { dir.multiplyScalar(1 / len); arrow.position.copy(pA).addScaledVector(dir, .03); arrow.quaternion.setFromUnitVectors(YA, dir); } }

// ---------- live: during a session on the arm the picture sits where the handle really is. The app passes metres from the start of the path (along it, sideways, up); nothing here runs on a clock ----------
// for each figure: where the path starts in the scene, which way it runs (+1 away from her, -1 towards her), how far she leans at its start and its end
const LIVE = { reach: { x: X0, y: .95, dir: 1, lean: [0, .38] }, push: { x: .4, y: .97, dir: 1, lean: [.06, .3] }, pull: { x: .4, y: .97, dir: -1, lean: [.3, .04] }, pushhold: { x: .56, y: .97, dir: 1, lean: [.16, .25], test: true } };
const shown = V(), lvTrail = Array.from({ length: TD }, () => V()), lvS = {}, lvT = { key: null, at: 0 };
function liveAt(fig, lv) { const c = LIVE[fig] || LIVE.reach, len = clamp(lv.len || .3, .02, .45), a = clamp(lv.a || 0, -.08, len + .05), load = clamp(lv.load || 0);      // clamped, so a bad sample cannot fling her arm
  const x0 = c.dir > 0 ? c.x : c.x + clamp(lv.far || len, .02, .45);      // a pull starts at the far end and comes towards her
  lvS.x = clamp(x0 + c.dir * a, .24, .86); lvS.y = c.y + clamp(lv.up || 0, -.12, .12); lvS.z = Z0 + clamp(lv.side || 0, -.12, .12);      // true scale: the scene is in metres
  lvS.lean = lerp(c.lean[0], c.lean[1], c.test ? load : clamp(a / len)); lvS.load = c.test ? load : 0; lvS.x0 = x0; lvS.len = len; lvS.dir = c.dir; return lvS; }
function liveGuides(fig, d, s, lv) { const c = LIVE[fig] || LIVE.reach, y = c.y + OFFH.y, z = Z0 + OFFH.z, test = !!c.test;
  // dark dots: the straight line the arm allows, from the start of the path to its end (a strength test: the short line that shows which way to push)
  for (let i = 0; i < GD; i++) { mtx.makeScale(.0088, .0088, .0088).setPosition(test ? c.x + i / (GD - 1) * .15 : s.x0 + s.dir * s.len * i / (GD - 1), y, z); gDots.setMatrixAt(i, mtx); } gDots.instanceMatrix.needsUpdate = true;
  if (test) { tDots.count = 0; arrow.visible = true; arrow.position.set(c.x + .18, y, z); arrow.quaternion.setFromUnitVectors(YA, d.push); arrow.scale.setScalar(1 + s.load * .35); arrowMat.color.set('#1E282A').lerp(cT.set('#E8472B'), s.load); return; }      // the arrow turns red with the real force
  // green tail: where the hand really was over the last half second. It stays as it is while the picture is stopped
  const now = performance.now(); pB.set(s.x, s.y, s.z).add(OFFH);
  if (lvT.key !== lv.key) { lvT.key = lv.key; lvT.at = now; lvTrail.forEach((p) => p.copy(pB)); }
  else if (!lv.frozen && now - lvT.at >= 28) { lvT.at = now; for (let i = TD - 1; i > 0; i--) lvTrail[i].copy(lvTrail[i - 1]); lvTrail[0].copy(pB); }
  tDots.count = TD; for (let i = 0; i < TD; i++) { const r = .014 * (1 - i / TD) + .004; mtx.makeScale(r, r, r).setPosition(i ? lvTrail[i - 1] : pB); tDots.setMatrixAt(i, mtx); } tDots.instanceMatrix.needsUpdate = true;
  // arrow: which way the movement goes next along the line (lv.go: +1 to the end of the path, -1 back to its start); none while the arm rests or is stopped
  arrow.visible = !!lv.go && !lv.frozen; if (!arrow.visible) return; pA.set(s.dir * lv.go, 0, 0); arrowMat.color.set('#0E657A'); arrow.scale.setScalar(1); arrow.position.copy(pB).addScaledVector(pA, .05); arrow.quaternion.setFromUnitVectors(YA, pA); }
// the slow camera sway stops with the picture, and carries on from the same angle afterwards
let swayOff = 0, swayHeld = null;
function swayAt(lv) { const n = performance.now(); if (lv && lv.frozen) { if (swayHeld === null) swayHeld = n - swayOff; return swayHeld; } if (swayHeld !== null) { swayOff = n - swayHeld; swayHeld = null; } return n - swayOff; }

let W0 = 0, H0 = 0, zoom = .84;
function fit(w, h) { if (w === W0 && h === H0) return; W0 = w; H0 = h; renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); }
const thumbs = {};
window.vita3d = {
  // draw the exercise into a box of the app: the canvas moves to whichever screen is showing
  // with lv the figure is placed from the arm's real position: { key, a, side, up (metres from the path start), len, far, load (0 to 1), go, frozen }
  show(el, fig, t, lv) { if (canvas.parentNode !== el) { el.appendChild(canvas); el.classList.add('has3d'); } const w = Math.max(1, el.clientWidth), h = Math.max(1, el.clientHeight); fit(w, h); pose(fig, t, lv); renderer.render(scene, cam); },
  shown,      // where the hand (or the cuff) was last drawn, in scene metres: read by the checks
  // a still picture for the lists, made once per exercise
  thumb(fig) { if (thumbs[fig]) return thumbs[fig]; const w0 = W0, h0 = H0; fit(232, 170); zoom = .62; pose(fig, .45); zoom = .84; renderer.render(scene, cam); thumbs[fig] = canvas.toDataURL('image/jpeg', .86); if (w0) fit(w0, h0); return thumbs[fig]; },
};
const ready = () => dispatchEvent(new Event('vita3d'));
if (logoReady()) ready(); else logoWait.push(() => { for (const k in thumbs) delete thumbs[k]; ready(); }); setTimeout(ready, 0);
