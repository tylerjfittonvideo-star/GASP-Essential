/* GASP! Essential site · menu + inner-page depth environment (vanilla; no framework) */
(() => {
  const d = document, root = d.documentElement;
  root.classList.add("js");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

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
    window.__menu = set;
  }

  const nav = d.querySelector(".nav");
  if (nav && d.body.dataset.journey === undefined) { const f = () => nav.classList.toggle("scrolled", scrollY > 40); addEventListener("scroll", f, { passive: true }); f(); }
  if (d.body.dataset.journey !== undefined) return;   // home runs its own 3D engine

  /* ---------- rack-focus reveals ---------- */
  const items = [...d.querySelectorAll("[data-focus]")];
  d.querySelectorAll("[data-stagger]").forEach(g => [...g.children].forEach((c, i) => { c.setAttribute("data-focus", ""); c.style.setProperty("--i", i); items.push(c); }));
  if (reduce || !("IntersectionObserver" in window)) items.forEach(el => el.classList.add("in"));
  else {
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .18, rootMargin: "0px 0px -8% 0px" });
    items.forEach(el => io.observe(el));
  }

  /* ---------- background world: you travel forward through it as you scroll ---------- */
  const bg = d.querySelector(".bg"); if (!bg) return;
  const world = bg.querySelector(".world");
  const mobile = matchMedia("(max-width:720px)").matches, XS = mobile ? .45 : 1;
  const LITE = mobile || matchMedia("(pointer:coarse)").matches, FS = LITE ? .5 : 1;
  if (LITE) root.classList.add("lite");
  const CUT = LITE ? 250 : 500;   // behind-camera cutoff; 250 caps near-plane magnification on phones (playbook 3.13)
  const nodes = [];
  const place = (cls, html, x, y, z, ry = 0, rx = 0, rz = 0, kind = "") => {
    const n = d.createElement("div"); n.className = "node";
    n.style.transform = `translate3d(${x * XS}px,${y}px,${z}px) rotateY(${ry}deg) rotateX(${rx}deg) rotateZ(${rz}deg)`;
    const e = d.createElement("div"); e.className = cls; e.innerHTML = html; n.append(e); world.append(n);
    if (kind) nodes.push({ el: e, z, kind, op: -1, b: -1 });
    return e;
  };
  const words = (d.body.dataset.ghosts || "GASP!").split(",");
  const depth = 14000;
  words.forEach((w, i) => { const side = i % 2 ? -1 : 1;
    place("ghost" + (i % 2 ? " w" : ""), w.trim(), side * (900 + (i % 3) * 300), -300 + (i % 3) * 500, -1400 - i * (depth / words.length), -side * 18, 0, side * 3, "ghost").style.fontSize = (520 + (i % 2) * 280) * FS + "px"; });
  for (let i = 0; i < (LITE ? 0 : 9); i++) { const z = -900 - i * 1600, side = i % 2 ? 1 : -1;
    const g = place("gate", `<b>${String(i + 1).padStart(2, "0")}</b>`, side * 260, (i % 3 - 1) * 180, z, side * 8, 0, side * 2, "gate"); }
  let seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < (LITE ? 30 : 130); i++) {
    const mz = 300 - rnd() * (depth + 2000);
    const m = place("mote" + (rnd() < .3 ? " p" : ""), "", (rnd() - .5) * 5200, (rnd() - .5) * 3600, mz, 0, 0, 0, LITE ? "mote" : "");
    const s = 5 + rnd() * 14; m.style.width = m.style.height = s + "px";
  }
  if (reduce) { world.style.transform = "translate3d(0,0,-400px)"; nodes.forEach(o => { o.el.style.opacity = o.kind === "gate" ? .25 : .3; }); return; }

  let ticking = false;
  const frame = () => {
    ticking = false;
    const max = Math.max(1, d.documentElement.scrollHeight - innerHeight);
    const p = scrollY / max, camZ = -p * depth;
    const sway = Math.sin(p * Math.PI * 3), yaw = sway * 4, x = sway * 160, y = Math.cos(p * Math.PI * 2) * 90;
    world.style.transform = `rotateY(${-yaw}deg) translate3d(${-x}px,${-y}px,${-camZ}px)`;
    for (const o of nodes) {
      const dz = o.z - camZ;                                   // 0 = focal plane, - = ahead
      if (o.kind === "mote") { const hide = dz > CUT; if (hide !== o.op) { o.el.style.visibility = hide ? "hidden" : "visible"; o.op = hide; } continue; }
      const op = dz > (LITE && o.kind === "ghost" ? 0 : CUT) ? 0 :   /* phones: ghost words leave before the focal plane, so a wide word never magnifies */ o.kind === "gate" ? Math.max(0, .55 - Math.max(0, -dz) / 8000 - Math.max(0, dz) / 600) : Math.max(0, .5 - Math.abs(dz) / 12000);
      let b = Math.round(Math.min(14, (o.kind === "gate" ? 0 : 3) + Math.abs(dz) / 500) * 2) / 2;
      if (Math.abs(op - o.op) > .01) { o.el.style.opacity = op.toFixed(2); o.el.style.visibility = op < .02 ? "hidden" : "visible"; o.op = op; }
      if (LITE) b = 0;
      if (b !== o.b) { o.el.style.filter = b <= .5 ? "none" : `blur(${b}px)`; o.b = b; }
    }
  };
  addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(frame); } }, { passive: true });
  addEventListener("resize", frame);
  frame();
})();
