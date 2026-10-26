/* GASP! Essential site · v4 motion (vanilla). Normal scrolling; three 3D moments:
   1 · the construction bang turns in space (pointer + scroll, spring-smoothed)
   2 · tiles fly up out of depth as they enter (scroll-linked)
   3 · one sticky stage where the payoff word flies at the camera
   Transform + opacity only. Reduced motion = static page. */
(() => {
  const d = document, root = d.documentElement;
  root.classList.add("js");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $$ = (s, r = d) => [...r.querySelectorAll(s)];
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = t => 1 - Math.pow(1 - t, 3);

  /* ---------- personalised links from the intro emails: ?name=Sam&co=Acme ---------- */
  const q = new URLSearchParams(location.search);
  const clean = v => (v || "").replace(/[<>{}$]/g, "").replace(/\s+/g, " ").trim().slice(0, 40);
  const bad = s => !s || /^\$|lead\.|first.?name|company/i.test(s);
  const name = clean(q.get("name")), co = clean(q.get("co"));
  const hi = d.getElementById("hi"); if (hi && !bad(name)) hi.textContent = `${name}, hire your`;
  const cq = d.getElementById("closeq"); if (cq && !bad(co)) cq.innerHTML = `Who would ${co} hire <em>first?</em>`;

  /* ---------- menu ---------- */
  const btn = d.querySelector(".menu-btn"), menu = d.querySelector(".menu");
  if (btn && menu) {
    const set = open => {
      root.classList.toggle("menu-open", open);
      btn.setAttribute("aria-expanded", String(open));
      btn.querySelector("span").textContent = open ? "Close" : "Menu";
      menu.toggleAttribute("inert", !open);
      if (open) menu.querySelector("a").focus({ preventScroll: true });
    };
    menu.setAttribute("inert", "");
    btn.addEventListener("click", () => set(!root.classList.contains("menu-open")));
    addEventListener("keydown", e => { if (e.key === "Escape" && root.classList.contains("menu-open")) { set(false); btn.focus(); } });
  }
  const nav = d.querySelector(".nav");
  const navF = () => nav && nav.classList.toggle("scrolled", scrollY > 40);

  /* ---------- simple rises ---------- */
  $$("[data-rise-group]").forEach(g => [...g.children].forEach((c, i) => { c.setAttribute("data-rise", ""); c.style.setProperty("--i", i); }));
  const rises = $$("[data-rise]");
  if (reduce || !("IntersectionObserver" in window)) rises.forEach(el => el.classList.add("in"));
  else { const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .15, rootMargin: "0px 0px -6% 0px" }); rises.forEach(el => io.observe(el)); }

  if (reduce) { addEventListener("scroll", navF, { passive: true }); navF(); $$("[data-fly]").forEach(el => el.style.opacity = 1); return; }

  /* ---------- 1 · construction bang ---------- */
  const rig = d.querySelector(".bang3d .rig");
  let px = 0, py = 0, rx = 0, ry = 0;
  if (rig && matchMedia("(hover:hover)").matches) addEventListener("pointermove", e => { px = e.clientX / innerWidth - .5; py = e.clientY / innerHeight - .5; }, { passive: true });

  /* ---------- 2 · tiles fly out of depth ---------- */
  const flyers = $$("[data-fly]").map(el => { const g = el.parentElement, i = [...g.children].indexOf(el), cols = getComputedStyle(g).gridTemplateColumns.split(" ").length || 1; return { el, lag: (i % cols) * .12 + Math.floor(i / cols) * .04, v: -1 }; });

  /* ---------- 3 · depth stage ---------- */
  const depths = $$(".depth").map(s => ({ s, q: s.querySelector(".q"), big: s.querySelector(".big") }));

  let t0 = performance.now();
  const frame = now => {
    const vh = innerHeight;
    if (rig) {
      const sp = clamp(scrollY / vh);                          // hero scroll-out
      const tx = py * -10 + sp * 26, ty = px * 16 + Math.sin(now / 2600) * 6 - sp * 20;
      rx += (tx - rx) * .08; ry += (ty - ry) * .08;              // spring-ish smoothing
      rig.style.transform = `rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) translateZ(${(-sp * 220).toFixed(1)}px)`;
      rig.parentElement.style.opacity = (1 - sp * .9).toFixed(3);
    }
    for (const f of flyers) {
      const r = f.el.getBoundingClientRect();
      if (r.top > vh * 1.2 || r.bottom < -vh * .2) { if (f.v !== 0 && r.top > vh) { f.el.style.opacity = 0; f.v = 0; } continue; }
      const p = ease(clamp((vh - r.top) / (vh * .55) - f.lag));
      if (Math.abs(p - f.v) < .002) continue; f.v = p;
      f.el.style.opacity = p.toFixed(3);
      f.el.style.transform = p > .999 ? "" : `translate3d(0,${((1 - p) * 70).toFixed(1)}px,${((1 - p) * -320).toFixed(1)}px) rotateX(${((1 - p) * 26).toFixed(2)}deg)`;
    }
    for (const o of depths) {
      const r = o.s.getBoundingClientRect(), span = r.height - vh;
      const p = clamp(-r.top / Math.max(1, span));
      const a = ease(clamp(p / .35)), b = ease(clamp((p - .3) / .45)), out = clamp((p - .88) / .12);
      if (o.q) { o.q.style.opacity = (a * (1 - b * .55) * (1 - out)).toFixed(3); o.q.style.transform = `translateZ(${((1 - a) * -400 + b * 120).toFixed(1)}px)`; }
      if (o.big) { o.big.style.opacity = (b * (1 - out)).toFixed(3); o.big.style.transform = `translateZ(${((1 - b) * -2200 + out * 500).toFixed(1)}px) rotateX(${((1 - b) * 22).toFixed(2)}deg)`; }
    }
    requestAnimationFrame(frame);
  };
  addEventListener("scroll", navF, { passive: true }); navF();
  requestAnimationFrame(frame);

  /* Amicro #11 magnetic on the primary CTA */
  $$(".btn[data-magnet]").forEach(b => { if (!matchMedia("(hover:hover)").matches) return;
    b.addEventListener("pointermove", e => { const r = b.getBoundingClientRect(); b.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * .3}px,${(e.clientY - r.top - r.height / 2) * .3}px)`; });
    b.addEventListener("pointerleave", () => { b.style.transform = ""; }); });
})();
