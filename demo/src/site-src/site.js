(() => {
  // every page opens at its top (the host can carry the old scroll position over)
  try { history.scrollRestoration = 'manual'; } catch (e) {}
  if (!location.hash) { scrollTo(0, 0); addEventListener('load', () => scrollTo(0, 0)); }
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const clamp = (v) => Math.min(1, Math.max(0, v)), ease = (t) => { t = clamp(t); return t * t * (3 - 2 * t); };
  // header glass once scrolled
  const hd = document.querySelector('header'); const onS = () => hd.classList.toggle('scrolled', scrollY > 8); addEventListener('scroll', onS, { passive: true }); onS();
  // reveal: starts just before an element enters, short stagger
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px 6% 0px' });
  document.querySelectorAll('.rv').forEach((el, i) => { el.style.transitionDelay = (i % 4) * 60 + 'ms'; io.observe(el); });

  // ---- Anna's eight weeks (How it works page) ----
  let wT = 0, wC = 0, jVis = false, drawJourney = () => {}, journeyTick = () => {};
  if (document.getElementById('jNum')) {
  const REACH = [29, 30, 31.5, 33, 35, 36.5, 38, 40, 41], SUP = [70, 66, 60, 54, 46, 40, 33, 26, 20];
  const X = (i) => 20 + i * 45, Y = (cm) => 140 - (cm - 26) / (46 - 26) * 140 + 10;
  const at = (arr, w) => { const i = Math.min(arr.length - 2, Math.floor(w)), f = w - i; return arr[i] + (arr[i + 1] - arr[i]) * f; };
  const chaps = [...document.querySelectorAll('.chap')], jNum = document.getElementById('jNum'), jWeek = document.getElementById('jWeek'), jDelta = document.getElementById('jDelta'),
    jLine = document.getElementById('jLine'), jArea = document.getElementById('jArea'), jDot = document.getElementById('jDot'), jHalo = document.getElementById('jHalo'), jBar = document.getElementById('jBar'), jSup = document.getElementById('jSup');
  drawJourney = (w) => {
    let d = `M${X(0)},${Y(REACH[0])}`; const n = Math.floor(w);
    for (let i = 1; i <= n; i++) d += ` L${X(i)},${Y(REACH[i]).toFixed(1)}`;
    const cx = X(w), cy = Y(at(REACH, Math.min(w, 8))); if (w > n) d += ` L${cx.toFixed(1)},${cy.toFixed(1)}`;
    jLine.setAttribute('d', d); jArea.setAttribute('d', d + ` L${cx.toFixed(1)},160 L${X(0)},160 Z`);
    jDot.setAttribute('cx', cx.toFixed(1)); jDot.setAttribute('cy', cy.toFixed(1)); jHalo.setAttribute('cx', cx.toFixed(1)); jHalo.setAttribute('cy', cy.toFixed(1));
    const cm = at(REACH, w), gain = Math.round(cm - REACH[0]), sup = Math.round(at(SUP, w));
    jNum.textContent = Math.round(cm); jWeek.textContent = 'Week ' + Math.round(w);
    jDelta.textContent = gain > 0 ? `+${gain} cm since week 0` : 'Starting point';
    jBar.style.width = sup + '%'; jSup.textContent = sup + '%';
  };
  // growth plays on its own: week 0 -> 8 in one continuous line; the story beside it follows the weeks
  const wtabs = document.getElementById('wtabs'), wbtn = [...wtabs.querySelectorAll('button')], progs = wbtn.map((b) => b.querySelector('.prog')),
    STOPS = wbtn.map((b) => +b.dataset.week), jPlay = document.getElementById('jPlay'), pts = [...document.querySelectorAll('#jPts circle')];
  pts.forEach((c, i) => c.setAttribute('cy', Y(REACH[i + 1]).toFixed(1)));
  const HOLD0 = 2600, PER = 2100, HOLDEND = 4200, REW = 1100, GROW = HOLD0 + 8 * PER, TOTAL = GROW + HOLDEND + REW;
  let wi = -1, playing = !reduce, tStart = null;
  const ease = (x) => x < .5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2;
  const wAt = (t) => t < HOLD0 ? 0 : t < GROW ? (t - HOLD0) / PER : t < GROW + HOLDEND ? 8 : 8 * (1 - ease((t - GROW - HOLDEND) / REW));
  function showChap(k) { if (k === wi) return; wi = k; wbtn.forEach((b, i) => b.setAttribute('aria-selected', i === k)); chaps.forEach((c, i) => c.classList.toggle('on', i === k)); }
  const chapFor = (w) => { let k = 0; STOPS.forEach((s, i) => { if (w >= s - .001) k = i; }); return k; };
  function setPlay(on) { playing = on && !reduce; tStart = null; jPlay.classList.toggle('playing', playing); jPlay.setAttribute('aria-label', playing ? 'Pause the animation' : 'Play the eight weeks');
    if (!playing) progs.forEach((p) => (p.style.transform = 'scaleX(0)')); }
  function paint(w) { drawJourney(w); pts.forEach((c, i) => c.classList.toggle('on', w >= i + 1 - .02)); }
  journeyTick = (now) => {
    if (playing) {
      if (tStart === null) tStart = now - (wC >= 7.99 ? 0 : HOLD0 + wC * PER);
      let t = now - tStart; if (t >= TOTAL) { tStart = now; t = 0; }
      wC = wAt(t); wT = wC; paint(wC); const k = t >= GROW + HOLDEND ? wi : chapFor(wC); showChap(k);
      progs.forEach((p, i) => { let f = 0;
        if (i === k && t < GROW + HOLDEND) { const a = i === 0 ? 0 : HOLD0 + STOPS[i] * PER, b = i < STOPS.length - 1 ? HOLD0 + STOPS[i + 1] * PER : GROW + HOLDEND; f = Math.min(1, Math.max(0, (t - a) / (b - a))); }
        p.style.transform = `scaleX(${f.toFixed(3)})`; });
    } else if (Math.abs(wT - wC) > .002) { wC = reduce ? wT : wC + (wT - wC) * .08; paint(wC); }
  };
  wbtn.forEach((b, k) => b.addEventListener('click', () => { setPlay(false); showChap(k); wT = STOPS[k]; }));
  wtabs.addEventListener('keydown', (e) => { const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0; if (!d) return; e.preventDefault(); const k = (wi + d + wbtn.length) % wbtn.length; setPlay(false); showChap(k); wT = STOPS[k]; wbtn[k].focus(); });
  jPlay.addEventListener('click', () => setPlay(!playing));
  setPlay(playing); showChap(0); paint(0);
  new IntersectionObserver((es) => es.forEach((e) => { jVis = e.isIntersecting; if (!jVis) tStart = null; }), { threshold: .3 }).observe(document.querySelector('.jgrid'));
  }

  // ---- exercises: click a row (or let it play) and the stage switches ----
  let fig = 'reach', figAt = 0;
  if (document.querySelector('.exi')) {
  const items = [...document.querySelectorAll('.exi')], label = document.getElementById('exLabel'), count = document.getElementById('exCount'); let xi = 0, xAuto = !reduce, xTimer, xVis = false;
  function setEx(i) { xi = i; const best = items[i];
    items.forEach((it) => { it.classList.toggle('on', it === best); it.querySelector('.exb').setAttribute('aria-expanded', it === best); });
    fig = best.dataset.fig; figAt = performance.now(); document.querySelectorAll('.mus[data-mus]').forEach((m) => m.classList.toggle('on', m.dataset.mus === fig)); label.textContent = best.querySelector('h3').textContent; count.textContent = (i + 1) + ' / ' + items.length;
    clearTimeout(xTimer); if (xAuto && xVis) xTimer = setTimeout(() => setEx((xi + 1) % items.length), 9000); }
  items.forEach((it, k) => it.querySelector('.exb').addEventListener('click', () => { xAuto = false; setEx(k); }));
  new IntersectionObserver((es) => es.forEach((e) => { const was = xVis; xVis = e.isIntersecting; if (xVis && !was) setEx(xi); else if (!xVis) clearTimeout(xTimer); }), { threshold: .35 }).observe(document.querySelector('.ex'));
  }

  // ---- exercises: one session, played as a timeline (sets, rests, switches) ----
  if (document.getElementById('sess')) {
    const PLANS = {
      short: { warm: 60, sw: 45, ex: [['Forward reach', 3, 60, 45, '10 reps'], ['Shoulder rotation', 3, 50, 45, '12 reps'], ['Knee extension', 3, 60, 60, '10 reps']] },
      full: { warm: 90, sw: 60, ex: [['Forward reach', 4, 60, 75, '10 reps'], ['Arm lift', 3, 60, 75, '10 reps'], ['Shoulder circles', 3, 50, 45, '8 each way'], ['Knee extension', 4, 70, 90, '12 reps']] },
    };
    const bar = document.getElementById('sBar'), head = document.getElementById('sHead'), sx = document.getElementById('sX'), sum = document.getElementById('sSum'),
      sNow = document.getElementById('sNow'), sSub = document.getElementById('sSub'), sClock = document.getElementById('sClock'), sDot = document.getElementById('sDot'),
      tabsS = [...document.querySelectorAll('.stabs button')];
    let segs = [], total = 0, t0 = null, sVis = false, cur = -1;
    const mmss = (s) => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
    function build(name) {
      const P = PLANS[name]; segs = [{ k: 's', d: P.warm, a: 'Warm-up', b: 'Easy movements, arm fully supporting' }];
      P.ex.forEach(([n, sets, work, rest, reps], j) => {
        if (j) segs.push({ k: 's', d: P.sw, a: 'Next exercise', b: 'The arm moves to ' + n.toLowerCase() });
        for (let i = 1; i <= sets; i++) {
          segs.push({ k: 'w', d: work, a: n, b: `Set ${i} of ${sets} · ${reps}`, ex: j });
          if (i < sets) segs.push({ k: 'r', d: rest, a: 'Rest', b: `${rest} s before set ${i + 1} of ${n.toLowerCase()}`, ex: j });
        }
      });
      total = segs.reduce((a, g) => a + g.d, 0); let acc = 0;
      bar.querySelectorAll('.sg').forEach((e) => e.remove()); sx.innerHTML = '';
      segs.forEach((g) => { g.t = acc; acc += g.d; const e = document.createElement('i'); e.className = 'sg k-' + g.k; e.style.flexGrow = g.d; bar.insertBefore(e, head); g.el = e; });
      P.ex.forEach(([n], j) => { const a = segs.find((g) => g.ex === j), b = [...segs].reverse().find((g) => g.ex === j);
        const l = document.createElement('span'); l.textContent = n; l.style.left = (a.t / total * 100) + '%'; l.style.width = ((b.t + b.d - a.t) / total * 100) + '%'; sx.appendChild(l); });
      const work = segs.filter((g) => g.k === 'w').reduce((a, g) => a + g.d, 0), nSets = segs.filter((g) => g.k === 'w').length;
      sum.innerHTML = `<div><b>${Math.round(total / 60)} min</b><span>in total</span></div><div><b>${P.ex.length}</b><span>exercises</span></div><div><b>${nSets}</b><span>sets</span></div><div><b>${Math.round(work / 60)} min</b><span>of active work</span></div>`;
      cur = -1; t0 = null;
    }
    function setPlan(name) { tabsS.forEach((b) => b.setAttribute('aria-selected', b.dataset.plan === name)); build(name); if (reduce) paintS(total * .38); }
    function paintS(s) {
      head.style.left = (s / total * 100) + '%'; sClock.textContent = mmss(s);
      const i = Math.max(0, segs.findIndex((g) => s < g.t + g.d)), g = segs[i] || segs[segs.length - 1];
      segs.forEach((x, k) => x.el.classList.toggle('done', k < i));
      if (i !== cur) { cur = i; sNow.textContent = g.a; sSub.textContent = g.b; sDot.className = 'sdot k-' + g.k; segs.forEach((x, k) => x.el.classList.toggle('now', k === i)); }
    }
    const SPEED = 75; // session seconds per real second
    const tick = (now) => { requestAnimationFrame(tick); if (!sVis || reduce || document.hidden) { t0 = null; return; }
      if (t0 === null) t0 = now - (parseFloat(head.dataset.s || 0) / SPEED) * 1000;
      let s = (now - t0) / 1000 * SPEED; if (s > total + 150) { t0 = now; s = 0; } head.dataset.s = Math.min(s, total); paintS(Math.min(s, total)); };
    tabsS.forEach((b) => b.addEventListener('click', () => { head.dataset.s = 0; setPlan(b.dataset.plan); }));
    setPlan('short'); paintS(0); requestAnimationFrame(tick);
    new IntersectionObserver((es) => es.forEach((e) => { sVis = e.isIntersecting; }), { threshold: .3 }).observe(document.getElementById('sess'));
  }

  // ---- vision: fixed weight vs Vita, rep by rep ----
  if (document.getElementById('vdemo')) {
    const ZLO = 75, ZHI = 88, FIX = [52, 57, 61, 66, 70, 75, 80, 86, 92, 98, 100], VEFF = [79, 81, 80, 82, 81, 80, 83, 81, 82, 80, 81, 82];
    const VKG = VEFF.map((_, i) => 13 - i * .3 - (i > 7 ? (i - 7) * .15 : 0));
    const N = 12, lanes = [['vlF', FIX], ['vlV', VEFF]].map(([id, eff]) => { const bx = document.querySelector('#' + id + ' .vbars'); bx.innerHTML = '';
      const bars = Array.from({ length: N }, (_, i) => { const b = document.createElement('i'); b.innerHTML = '<span></span><small>' + (i + 1) + '</small>'; bx.appendChild(b); return b; }); return { eff, bars }; });
    const zone = (e) => e < ZLO ? 'z-lo' : e > ZHI ? 'z-hi' : 'z-in';
    document.querySelectorAll('#vdemo .vzone').forEach((z) => { z.style.bottom = ZLO + '%'; z.style.height = (ZHI - ZLO) + '%'; });
    const vsF = document.getElementById('vsF'), vsV = document.getElementById('vsV'), vrF = document.getElementById('vrF'), vrV = document.getElementById('vrV');
    let rep = 0, timer, vVis = false;
    function reset() { rep = 0; lanes.forEach((l) => l.bars.forEach((b) => { b.className = ''; b.firstChild.style.height = '0%'; })); vsF.textContent = vsV.textContent = '0'; vrF.textContent = '10 kg'; vrV.textContent = VKG[0].toFixed(1) + ' kg'; document.getElementById('vlF').classList.remove('failed'); }
    function step() {
      if (rep >= N) { timer = setTimeout(() => { reset(); step(); }, 3800); return; }
      lanes.forEach((l, k) => { const e = l.eff[rep], b = l.bars[rep];
        if (e === undefined) { b.className = 'skip'; return; }
        b.className = 'on ' + zone(e) + (k === 0 && e >= 100 ? ' fail' : ''); b.firstChild.style.height = e + '%'; });
      const f = FIX.slice(0, rep + 1).filter((e) => e >= ZLO && e <= ZHI).length, v = VEFF.slice(0, rep + 1).filter((e) => e >= ZLO && e <= ZHI).length;
      vsF.textContent = f; vsV.textContent = v;
      vrF.textContent = rep < FIX.length ? (FIX[rep] >= 100 ? 'Rep ' + (rep + 1) + ' · too heavy, set ends' : 'Rep ' + (rep + 1) + ' · 10 kg · effort ' + FIX[rep] + '%') : 'Set ended at rep ' + FIX.length;
      if (rep >= FIX.length - 1) document.getElementById('vlF').classList.add('failed');
      vrV.textContent = 'Rep ' + (rep + 1) + ' · ' + VKG[rep].toFixed(1) + ' kg · effort ' + VEFF[rep] + '%';
      rep++; timer = setTimeout(step, 620);
    }
    reset();
    if (reduce) { for (let i = 0; i < N; i++) step(); clearTimeout(timer); }
    document.getElementById('vAgain').addEventListener('click', () => { clearTimeout(timer); reset(); step(); });
    new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting && !vVis && !reduce) { vVis = true; reset(); step(); } }), { threshold: .4 }).observe(document.getElementById('vdemo'));
  }

  // ---- exercises: "muscles at work" map, the same drawing as the pitch deck (side view, each muscle its own belly; orange works, blue is stretched) ----
  const MUSDEF = {
    reach: { name: 'Shoulder, triceps and trunk', pose: { S: [2, -97], E: [27, -92], H: [53, -90] }, mus: [['delt', 'Front deltoid', 'lifts the arm', .9], ['tri', 'Triceps', 'straightens the elbow', .75], ['cuff', 'Shoulder-blade muscles', 'slide the shoulder forward', .55], ['abs', 'Trunk muscles', 'steady the lean', .4]] },
    circle: { name: 'Rotator cuff and shoulder blade', pose: { S: [2, -97], E: [26, -104], H: [50, -110] }, mus: [['cuff', 'Rotator cuff', 'keeps the joint centred', .65], ['delt', 'Deltoid', 'lifts the arm', .8], ['pec', 'Chest muscle', 'pulls the arm inward', .5], ['lat', 'Latissimus', 'pulls it outward', .45]] },
    lift: { name: 'Deltoid and rotator cuff', vb: '-27 -150 116 100', pose: { S: [2, -97], E: [19, -118], H: [36, -138] }, mus: [['delt', 'Deltoid', 'lifts the arm', .95], ['cuff', 'Rotator cuff', 'keeps the joint centred', .6], ['back', 'Upper back', 'turns the shoulder blade', .45], ['lat', 'Latissimus', 'lengthens', .5, 1]] },
    rot: { name: 'Rotator cuff and shoulder capsule', pose: { S: [2, -97], E: [4, -70], H: [29, -68] }, mus: [['cuff', 'Rotator cuff', 'turns the arm out and back', .9], ['cap', 'Shoulder capsule', 'is gently stretched', .6, 1], ['pec', 'Chest muscle', 'turns it back in', .45], ['delt', 'Back of the deltoid', 'helps turn it out', .35]] },
    knee: { name: 'Thigh muscle (quadriceps)', leg: 1, pose: { S: [2, -97], E: [8, -72], H: [30, -63], A: [80, -57] }, mus: [['quad', 'Quadriceps', 'straightens the knee', .95], ['hipf', 'Hip flexors', 'hold the thigh steady', .45], ['ham', 'Hamstrings', 'lengthen and let go', .55, 1], ['abs', 'Trunk muscles', 'keep you upright', .3, 0, 1]] },
    pushhold: { name: 'Chest, shoulder and triceps', pose: { S: [2, -97], E: [25, -90], H: [47, -96] }, mus: [['pec', 'Chest muscle', 'pushes forward', .95], ['tri', 'Triceps', 'locks the elbow', .85], ['delt', 'Front deltoid', 'holds the arm up', .65], ['abs', 'Trunk muscles', 'brace the body', .55]] },
  };
  function muscleMap(svg, def) {
    const NS = 'http://www.w3.org/2000/svg', mk = (tag, at, parent) => { const e = document.createElementNS(NS, tag); for (const k in at) e.setAttribute(k, at[k]); (parent || svg).appendChild(e); return e; };
    const FLESH = '#ECE5D6', BONE = '#FBF8F0', BONEL = '#CFC6AE', F = (v) => v.toFixed(1);
    const flesh = (w, p) => mk('line', { stroke: FLESH, 'stroke-width': w, 'stroke-linecap': 'round' }, p), bone = (p) => [mk('line', { stroke: BONEL, 'stroke-width': 3.6, 'stroke-linecap': 'round' }, p), mk('line', { stroke: BONE, 'stroke-width': 2.4, 'stroke-linecap': 'round' }, p)];
    const seg = (els, a, b) => [].concat(els).forEach((e) => { e.setAttribute('x1', F(a[0])); e.setAttribute('y1', F(a[1])); e.setAttribute('x2', F(b[0])); e.setAttribute('y2', F(b[1])); });
    const n2 = (a, b) => { const x = b[0] - a[0], y = b[1] - a[1], l = Math.hypot(x, y) || 1; return [x / l, y / l]; }, upn = (d) => (d[0] >= 0 ? [d[1], -d[0]] : [-d[1], d[0]]), along = (p, d, k, n, j) => [p[0] + d[0] * k + n[0] * j, p[1] + d[1] * k + n[1] * j];
    mk('path', { d: 'M-22 -47 H27 M-19 -47 L-23 -100', stroke: '#DCE5D8', 'stroke-width': 3, 'stroke-linecap': 'round', fill: 'none' });
    const gT = mk('g', {}), gL = mk('g', {}), gA = mk('g', {}), gTxt = mk('g', {});
    mk('ellipse', { cx: 1, cy: -75, rx: 12, ry: 27, fill: FLESH }, gT); mk('circle', { cx: 3, cy: -114, r: 10.5, fill: FLESH }, gT); mk('path', { d: 'M-6 -98 Q-9 -76 -5 -52', stroke: BONEL, 'stroke-width': 2.2, 'stroke-dasharray': '2.4 1.4', fill: 'none' }, gT);
    [-90, -84, -78, -72].forEach((y) => mk('path', { d: `M-5 ${y} Q4 ${y + 5} 10 ${y + 1}`, stroke: BONEL, 'stroke-width': .9, fill: 'none', opacity: .8 }, gT)); mk('ellipse', { cx: 3, cy: -54, rx: 9, ry: 5.5, fill: BONE, stroke: BONEL, 'stroke-width': .8 }, gT);
    const P = def.pose, HIP2 = [6, -52], K2 = [44, -52], c = { S: P.S, E: P.E, H: P.H, A: P.A || [47, -15] };
    c.u = n2(c.S, c.E); c.f = upn(c.u); c.fd = n2(c.E, c.H); c.ff = upn(c.fd); c.sd = n2(K2, c.A); c.bk = [-c.sd[1], c.sd[0]]; c.fr = [c.sd[1], -c.sd[0]];
    seg(flesh(15, gL), HIP2, K2); seg(flesh(11.5, gL), K2, c.A); seg(flesh(5.5, gL), along(c.A, c.sd, 3, c.fr, -1), along(c.A, c.sd, 3, c.fr, 13)); seg(bone(gL), HIP2, K2); seg(bone(gL), K2, c.A);
    seg(mk('line', { stroke: '#D9CDB4', 'stroke-width': 1.3, 'stroke-linecap': 'round' }, gL), [45.5, -57], along(K2, c.sd, 8, c.fr, 3.4)); mk('circle', { cx: 45.5, cy: -54.5, r: 3.2, fill: BONE, stroke: BONEL, 'stroke-width': .8 }, gL);
    seg(flesh(11, gA), c.S, c.E); seg(flesh(9, gA), c.E, c.H); seg(bone(gA), c.S, c.E); seg(bone(gA), c.E, c.H);
    [[c.S, 3.4], [c.E, 2.8]].forEach(([p, r]) => mk('circle', { cx: F(p[0]), cy: F(p[1]), r, fill: BONE, stroke: BONEL, 'stroke-width': .8 }, gA)); mk('circle', { cx: F(c.H[0]), cy: F(c.H[1]), r: 4, fill: FLESH, stroke: BONEL, 'stroke-width': .6 }, gA);
    const capRing = mk('circle', { cx: F(c.S[0]), cy: F(c.S[1]), r: 6, fill: 'none', stroke: '#E6C9C0', 'stroke-width': 1 }, gA);
    const MAP = [
      { id: 'back', g: gT, w: 2.2, p: () => [-9.5, -88, -8.5, -57, -1, 0] }, { id: 'abs', g: gT, w: 2.6, p: () => [11, -77, 9.5, -54, 1, 0] }, { id: 'lat', g: gT, w: 3.4, p: () => [-8, -63, 1, -93, -1.5, 0] },
      { id: 'pec', g: gT, w: 3.4, p: () => [11.5, -83, 3, -94.5, 1.2, -.6] }, { id: 'cuff', g: gT, w: 2.4, p: () => [-10.5, -97, 1, -96.5, 0, -1] },
      { id: 'hipf', g: gL, w: 2.4, p: () => [-1, -60, 14, -55.5, -.5, -1], lp: [-6, -10] }, { id: 'ham', g: gL, w: 3.2, p: () => [2, -46.5, ...along(K2, c.sd, 6, c.bk, 3.2), 0, 1.6] }, { id: 'quad', g: gL, w: 4, p: () => [7, -58, 45.5, -57, 0, -1.8] },
      { id: 'calf', g: gL, w: 2.8, p: () => [...along(K2, c.sd, 3, c.bk, 3), ...along(K2, c.sd, 36, c.bk, 2), c.bk[0] * 1.6, c.bk[1] * 1.6] }, { id: 'tib', g: gL, w: 1.5, p: () => [...along(K2, c.sd, 7, c.fr, 3.4), ...along(K2, c.sd, 33, c.fr, 2.6), c.fr[0] * .6, c.fr[1] * .6] },
      { id: 'tri', g: gA, w: 3, p: () => [...along(c.S, c.u, 2, c.f, -3), ...along(c.E, c.u, 0, c.f, -3.2), -c.f[0] * 1.5, -c.f[1] * 1.5] }, { id: 'bic', g: gA, w: 3, p: () => [...along(c.S, c.u, 3, c.f, 2.5), ...along(c.E, c.fd, 5, c.f, 1), c.f[0] * 1.5, c.f[1] * 1.5] },
      { id: 'fore', g: gA, w: 2.6, p: () => [...along(c.E, c.fd, 2, c.ff, 2.6), ...along(c.E, c.fd, 22, c.ff, 1.4), c.ff[0], c.ff[1]] }, { id: 'delt', g: gA, w: 4.2, p: () => [c.S[0] - 1.5, c.S[1] - 4.5, ...along(c.S, c.u, 15, c.f, 1), c.f[0] * 1.6, c.f[1] * 1.6] },
    ];
    const ACT = {}; def.mus.forEach((m, i) => { ACT[m[0]] = { a: m[3], st: m[4] || 0, ph: i * 1.3, name: m[5] ? '' : m[1].replace('Front d', 'D').replace('Back of the d', 'D').replace(' muscles', '').replace(' muscle', '').replace('Shoulder-blade', 'Shoulder blade').replace('Shoulder capsule', '') } });
    MAP.forEach((m) => { m.el = mk('path', { 'stroke-width': .45, 'stroke-linejoin': 'round' }, m.g); m.fib = mk('path', { fill: 'none', stroke: '#fff', 'stroke-width': .45, opacity: .5 }, m.g);
      m.txt = mk('text', { 'font-size': 4.3, 'font-weight': 600, 'text-anchor': 'middle', fill: '#1E2A26', stroke: '#fff', 'stroke-width': 1.3, 'paint-order': 'stroke', 'font-family': 'Outfit, sans-serif' }, gTxt); m.txt.textContent = ACT[m.id] ? ACT[m.id].name : ''; });
    const BASE = [230, 201, 192], HOT = [232, 71, 43], BLU = [63, 134, 219], lerp = (a, b, k) => a + (b - a) * k, rgb = (a, st, dark = 1) => { const col = st === 1 ? BLU : HOT, m = a < .01 ? 0 : .18 + a * .82; return `rgb(${BASE.map((v, i) => Math.round(lerp(v, col[i], m) * dark)).join(',')})`; };
    svg.setAttribute('viewBox', def.vb || (def.leg ? '-24 -93 116 86' : '-27 -134 116 86'));
    return function draw(t, k) {
      MAP.forEach((m) => { const A = ACT[m.id], a = A ? A.a * k * (.78 + .22 * Math.sin(t * 3.4 + A.ph)) : 0, st = A ? A.st : 0, q = m.p(), x1 = q[0], y1 = q[1], x2 = q[2], y2 = q[3], d = n2([x1, y1], [x2, y2]), nx = -d[1], ny = d[0], w = m.w * 2 * (st === 1 ? 1 - a * .3 : 1 + a * .6), mx = (x1 + x2) / 2 + q[4], my = (y1 + y2) / 2 + q[5];
        m.el.setAttribute('d', `M${F(x1)} ${F(y1)}Q${F(mx + nx * w)} ${F(my + ny * w)} ${F(x2)} ${F(y2)}Q${F(mx - nx * w)} ${F(my - ny * w)} ${F(x1)} ${F(y1)}Z`); m.el.setAttribute('fill', rgb(a, st)); m.el.setAttribute('stroke', rgb(a, st, .8));
        m.fib.setAttribute('d', `M${F(x1)} ${F(y1)}Q${F(mx + nx * w * .38)} ${F(my + ny * w * .38)} ${F(x2)} ${F(y2)}M${F(x1)} ${F(y1)}Q${F(mx - nx * w * .38)} ${F(my - ny * w * .38)} ${F(x2)} ${F(y2)}`);
        if (A && A.name) { const ol = Math.hypot(q[4], q[5]) || 1, kk = w / 2 + 4.4; m.txt.setAttribute('x', F((x1 + x2) / 2 + (m.lp ? m.lp[0] : q[4] / ol * kk))); m.txt.setAttribute('y', F((y1 + y2) / 2 + (m.lp ? m.lp[1] : q[5] / ol * kk) + 1.4)); } });
      const cp = ACT.cap; if (cp) { const a = cp.a * k * (.78 + .22 * Math.sin(t * 3.4 + cp.ph)); capRing.setAttribute('stroke', rgb(a, 1)); capRing.setAttribute('stroke-width', F(1.2 + a * 2.4)); }
    };
  }
  const musEls = [...document.querySelectorAll('.mus[data-mus]')], musDraw = new Map();
  musEls.forEach((el) => { const def = MUSDEF[el.dataset.mus]; if (!def) return;
    el.querySelector('.mname').textContent = def.name;
    el.querySelector('.mrows').innerHTML = def.mus.map((m) => `<div class="mrow${m[4] ? ' st' : ''}"><p><b>${m[1]}</b><span>${m[2]}</span></p><span class="mbar"><i style="--w:${Math.round(m[3] * 100)}%"></i></span></div>`).join('');
    musDraw.set(el, { draw: muscleMap(el.querySelector('.mmap'), def), k: 0 }); });
  if (musEls.length) {
    const musLoop = (now) => { requestAnimationFrame(musLoop); if (document.hidden) return; const t = reduce ? 0 : now / 1000;
      musDraw.forEach((o, el) => { const open = el.classList.contains('on'); const target = open ? 1 : 0; if (!open && o.k < .01) return; o.k += (target - o.k) * .08; o.draw(t, o.k); }); };
    musDraw.forEach((o) => o.draw(0, 0)); requestAnimationFrame(musLoop);
  }

  // ---- 3D: one canvas. The pinned hero first (wave, grab, pull up), then the exercise stage further down ----
  const heroEl = document.getElementById('hero'), hs = document.getElementById('heroStage'), sheet = document.getElementById('sheet'), handle = document.getElementById('handle'), bubble = document.getElementById('bubble'), hint = document.getElementById('hint'), exs = document.getElementById('exStage');
  const vis = new Map(); const vo = new IntersectionObserver((es) => es.forEach((e) => vis.set(e.target, e.isIntersecting)), { rootMargin: '80px' }); if (exs) vo.observe(exs);
  let sy = 0, sx = 0, firstHero = true;
  const hcopy = document.querySelector('.hcopy');
  function placeSheet(p, r, H) {
    // the robot pulls the sheet up and keeps holding its handle; the arm shows above the sheet, the trolley stays behind it
    let y, x, st = r ? r.top[1] : H * .2;
    const rest = H * (innerWidth < 900 ? .9 : .89);
    if (!r) { y = rest + (st - rest) * ease(Math.min(1, p / .8)); x = innerWidth * .62; }
    else if (p < .36) { const k = ease(p / .3); y = rest + (r.grab[1] - rest) * k; x = r.grab[0]; }
    else { y = r.hand[1]; x = r.hand[0]; }
    sy = firstHero ? y : sy + (y - sy) * .6; sx = firstHero ? x : sx + (x - sx) * .6; firstHero = false;
    sheet.style.transform = `translateY(${sy.toFixed(1)}px)`; sheet.classList.toggle('full', p > .74);
    sheet.style.setProperty('--st', st.toFixed(0) + 'px'); sheet.style.setProperty('--hx', (sx / innerWidth * 100).toFixed(1) + '%');
    const hx = Math.min(innerWidth - 80, Math.max(80, sx));
    handle.style.transform = `translate(${hx.toFixed(1)}px, ${sy.toFixed(1)}px)`;
    hs.style.clipPath = `inset(0 0 ${Math.max(0, H - sy - 16).toFixed(0)}px 0)`;
    if (hcopy) hcopy.style.opacity = (1 - ease(Math.min(1, Math.max(0, (p - .4) / .3)))).toFixed(3);
    hint.style.opacity = p > .02 ? 0 : 1;
  }
  // ---- the rep race on the problem panel: plays when the panel is fully up ----
  const race = document.getElementById('race');
  if (race) {
    const t1 = [...document.querySelectorAll('#rT1 i')], t2 = [...document.querySelectorAll('#rT2 i')], n1 = document.getElementById('rN1'), n2 = document.getElementById('rN2'), endTag = document.getElementById('rEnd');
    const stats = [...document.querySelectorAll('.pst b[data-to]')];
    let raf = 0, played = false;
    const fmt = (b, v) => { const to = +b.dataset.to, d = to % 1 ? 1 : 0; b.textContent = (b.dataset.pre || '') + v.toFixed(d) + (b.dataset.suf || ''); };
    function play() {
      cancelAnimationFrame(raf); endTag.classList.remove('show'); const t0 = performance.now(), DUR = 4200;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / DUR), e = 1 - Math.pow(1 - k, 2);
        const a = Math.min(32, Math.round(300 * e)), b = Math.round(300 * e);
        n1.textContent = a; n2.textContent = b + (k >= 1 ? '+' : '');
        const on1 = Math.round(a / 5), on2 = Math.round(b / 5);
        t1.forEach((el, i) => el.classList.toggle('on', i < on1)); t2.forEach((el, i) => el.classList.toggle('on', i < on2));
        if (a >= 32) endTag.classList.add('show');
        stats.forEach((s) => fmt(s, +s.dataset.to * Math.min(1, k * 2.2)));
        if (k < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    }
    document.getElementById('raceAgain').addEventListener('click', play);
    new MutationObserver(() => { if (sheet.classList.contains('full') && !played) { played = true; reduce ? (n1.textContent = 32, n2.textContent = '300+', t1.forEach((el, i) => el.classList.toggle('on', i < 6)), t2.forEach((el) => el.classList.add('on')), endTag.classList.add('show')) : play(); } }).observe(sheet, { attributes: true, attributeFilter: ['class'] });
  }

  const T = 3200;
  function frame(now) {
    requestAnimationFrame(frame); if (document.hidden) return; const v = window.vita3d;
    const rr = heroEl ? heroEl.getBoundingClientRect() : null, H = innerHeight, p = rr ? clamp(-rr.top / (heroEl.offsetHeight - H)) : 1;
    if (rr && rr.bottom > 0) {
      const r = v && v.hero ? v.hero(hs, p, reduce ? 0 : now, reduce) : null; placeSheet(p, r, hs.clientHeight || H);
      if (r && r.waving && !reduce) { bubble.classList.add('on'); bubble.style.transform = `translate(${(r.hand[0] - 30).toFixed(0)}px, ${(r.hand[1] - 92).toFixed(0)}px)`; } else bubble.classList.remove('on');
    } else if (v && exs && vis.get(exs)) v.show(exs, fig, reduce ? .55 : ((now - figAt) / T) % 1);
    if (jVis) journeyTick(now);
  }
  if (heroEl || exs || document.getElementById('jNum')) requestAnimationFrame(frame);

  // ---- safety: the stop button (push to latch, turn to release) ----
  const tile = document.getElementById('stopTile');
  if (tile) {
  const estop = document.getElementById('estop'), stopText = document.getElementById('stopText'), stopSpeed = document.getElementById('stopSpeed'), stopHelp = document.getElementById('stopHelp'), stopHint = document.getElementById('stopHint'); let busy = false, tick;
  const speedTo = (to, ms) => { const from = parseFloat(stopSpeed.textContent), t0 = performance.now(); cancelAnimationFrame(tick);
    const step = (t) => { const k = Math.min(1, (t - t0) / ms), v = from + (to - from) * (1 - Math.pow(1 - k, 3)); stopSpeed.textContent = v.toFixed(2) + ' m/s'; if (k < 1) tick = requestAnimationFrame(step); }; tick = requestAnimationFrame(step); };
  estop.addEventListener('click', () => {
    if (busy) return;
    if (!tile.classList.contains('stopped')) {
      tile.classList.add('stopped'); estop.setAttribute('aria-pressed', 'true'); estop.setAttribute('aria-label', 'Emergency stop pressed. Press again to release');
      stopText.textContent = 'Stopped · the arm holds still'; speedTo(0, 220);
      stopHelp.textContent = 'Stopped at once. The arm holds its position instead of letting go.'; stopHint.textContent = 'Latched · press to release';
    } else {
      busy = true; tile.classList.add('releasing');
      setTimeout(() => { tile.classList.remove('stopped', 'releasing'); busy = false; estop.setAttribute('aria-pressed', 'false'); estop.setAttribute('aria-label', 'Emergency stop');
        stopText.textContent = 'Running · forward reach, rep 7 of 12'; speedTo(0.12, 900);
        stopHelp.textContent = 'Released. A staff member checks in, then training carries on.'; stopHint.textContent = 'Push to stop · turn to release'; }, 520);
    }
  });
  }

  // ---- for locations: payback calculator ----
  const calc = document.getElementById('calc');
  if (calc) {
  const hrs = document.getElementById('hrs'), hrsOut = document.getElementById('hrsOut'), payOut = document.getElementById('payOut'), revOut = document.getElementById('revOut');
  function upd() {
    const h = +hrs.value, price = +calc.querySelector('input[name=price]:checked').value * 1000, rev = h * 2 * 25 * 22, m = price / rev;
    hrsOut.textContent = h + ' h'; hrs.style.setProperty('--fill', ((h - 1) / 9 * 100) + '%');
    payOut.innerHTML = (m < 10 ? m.toFixed(1) : Math.round(m)) + '<small>months</small>'; revOut.textContent = '$' + rev.toLocaleString('en-US') + ' / mo';
    const LIFE = 35000, yrs = LIFE / (h * 22 * 12), lifeOut = document.getElementById('lifeOut'), perOut = document.getElementById('perOut');
    if (lifeOut) { lifeOut.textContent = (yrs >= 20 ? Math.round(yrs) : yrs.toFixed(1)) + ' years'; document.getElementById('lifeSub').textContent = '35,000 hours at ' + h + ' h a day';
      perOut.textContent = '$' + (price / (LIFE * 2)).toFixed(2); }
  }
  hrs.addEventListener('input', upd); calc.querySelectorAll('input[name=price]').forEach((r) => r.addEventListener('change', upd)); upd();
  }

  // ---- contact form: Netlify Forms, sent without leaving the page ----
  const f = document.getElementById('cform'), msg = document.getElementById('fmsg');
  if (f) f.addEventListener('submit', async (e) => { e.preventDefault();
    if (!f.name.value.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.value.trim())) { msg.className = 'formmsg err'; msg.textContent = 'Please fill in your name and a valid email address.'; return; }
    const b = f.querySelector('button[type=submit]'); b.disabled = true; b.textContent = 'Sending…'; msg.textContent = '';
    try { const r = await fetch('/', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(new FormData(f)).toString() });
      if (!r.ok) throw new Error(r.status);
      f.innerHTML = '<div class="sent"><div class="t"><svg class="i" aria-hidden="true"><use href="#i-check"/></svg></div><h3>Thank you.</h3><p>We received your message and will reply by email.</p></div>'; }
    catch (err) { b.disabled = false; b.textContent = 'Send message'; msg.className = 'formmsg err'; msg.textContent = 'Sending did not work. Please try again in a moment.'; } });
})();
