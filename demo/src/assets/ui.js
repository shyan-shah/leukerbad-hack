// Page feel, on every page (also the plain reading pages):
//  - Lenis (MIT, darkroom.engineering): smooth scrolling on top of the browser's own scroll, so pinned text and anchors keep working.
//  - GSAP + SplitText (free standard licence, gsap.com): headlines that rise line by line.
//  - A few ideas from React Bits (reactbits.dev), written here in plain JS: ClickSpark, SpotlightCard, CountUp.
(function () {
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const still = new URLSearchParams(location.search).has('ch');       // screenshot mode: nothing moves
  const fine = matchMedia('(hover: hover) and (pointer: fine)').matches;

  // ---------- smooth scrolling ----------
  if (window.Lenis && !still) {
    const lenis = new Lenis({ lerp: .1, wheelMultiplier: 1, smoothWheel: true, syncTouch: false, anchors: { offset: 0 }, autoRaf: false });
    // The 3D world advances the scroll itself, in the same frame it draws (world.js). Only where there is no 3D world does it run on its own clock.
    const tick = (t) => { if (!window.__worldDrives) lenis.raf(t); requestAnimationFrame(tick); }; requestAnimationFrame(tick);
    window.__lenis = lenis;
  }

  if (!window.gsap || still) return;
  const gsap = window.gsap; document.documentElement.classList.add('gs');
  if (window.SplitText) gsap.registerPlugin(SplitText);

  // ---------- headlines rise line by line; the rest of a chapter follows ----------
  const seen = new WeakSet();
  function enter(sec) {
    if (seen.has(sec)) return; seen.add(sec);
    const copy = sec.querySelector('.copy'); if (!copy) return;
    const head = copy.querySelector('.big, .article h1'), rest = [...copy.children].filter((el) => el !== head && !el.classList.contains('article'));
    if (head && window.SplitText && !reduce) {
      SplitText.create(head, { type: 'lines', mask: 'lines', autoSplit: true, linesClass: 'ln',
        onSplit: (self) => gsap.from(self.lines, { yPercent: 108, duration: 1.05, ease: 'power4.out', stagger: .09 }) });
      gsap.set(head, { opacity: 1 });
    } else if (head) gsap.fromTo(head, { opacity: 0 }, { opacity: 1, duration: .6 });
    gsap.fromTo(rest, { opacity: 0, y: reduce ? 0 : 26 }, { opacity: 1, y: 0, duration: .9, ease: 'power3.out', stagger: .07, delay: .18, clearProps: 'transform' });
    // numbers count up, score bars fill (React Bits: CountUp)
    $$('.card .bar i', sec).forEach((b, i) => gsap.from(b, { scaleX: 0, transformOrigin: 'left', duration: 1.1, ease: 'power3.out', delay: .3 + i * .04 }));
    $$('[data-count]', sec).forEach((el) => { const to = +el.dataset.count, o = { v: 0 }; gsap.to(o, { v: to, duration: 1.4, ease: 'power2.out', delay: .3, onUpdate: () => { el.textContent = Math.round(o.v) + (el.dataset.suffix || ''); } }); });
  }
  const start = () => { const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) enter(e.target); }), { threshold: .1 }); $$('.ch').forEach((s) => io.observe(s)); };
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(start);

  if (!fine || reduce) return;

  // ---------- SpotlightCard: a soft light under the pointer on every card ----------
  $$('.card, .num, .qa details, .founder').forEach((c) => c.addEventListener('pointermove', (e) => { const r = c.getBoundingClientRect(); c.style.setProperty('--mx', (e.clientX - r.left) + 'px'); c.style.setProperty('--my', (e.clientY - r.top) + 'px'); }, { passive: true }));

  // ---------- ClickSpark: a small burst where you click ----------
  addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const dark = document.body.classList.contains('dark');
    for (let i = 0; i < 8; i++) { const s = document.createElement('i'), a = i / 8 * Math.PI * 2; s.className = 'spark'; s.style.cssText = `left:${e.clientX}px;top:${e.clientY}px;background:${dark ? '#fff' : '#17171A'};transform:rotate(${a}rad)`; document.body.append(s);
      gsap.fromTo(s, { x: Math.cos(a) * 8, y: Math.sin(a) * 8, scaleX: 1, opacity: 1 }, { x: Math.cos(a) * 30, y: Math.sin(a) * 30, scaleX: .2, opacity: 0, duration: .45, ease: 'power2.out', onComplete: () => s.remove() }); }
  }, { passive: true });
})();
