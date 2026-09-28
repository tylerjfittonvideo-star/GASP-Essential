/* GASP! Essential · home journey: stepped 3D flight between stations with depth of field.
   motion (Emil Kowalski's list): animate() drives every move. */
(() => {
  const d = document, root = d.documentElement;
  const q = new URLSearchParams(location.search);
  const clean = v => (v || "").replace(/[<>{}$]/g, "").replace(/\s+/g, " ").trim().slice(0, 40);
  const bad = s => !s || /^\$|lead\.|first.?name|company/i.test(s);
  const name = clean(q.get("name")), co = clean(q.get("co"));
  if (!bad(name)) { const h = d.getElementById("hi"); if (h) h.textContent = `Hey there ${name}!`; }
  if (!bad(co)) { const p = d.getElementById("pitch"); if (p) p.textContent = `If ${co}'s week is full of work that should run itself, that's exactly what I build. One email is enough to find out if there's a fit.`; }

  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !window.Motion) { root.classList.add("static", "ready"); return; }
  const { animate } = window.Motion;

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const seg = (p, a, b) => clamp((p - a) / (b - a));
  const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const sstep = t => t * t * t * (t * (t * 6 - 15) + 10);
  const D = Math.PI / 180;
  const mobile = matchMedia("(max-width:720px)").matches, XS = mobile ? .45 : 1, K = mobile ? .6 : 1;
  const $ = (s, r = d) => r.querySelector(s), $$ = (s, r = d) => [...r.querySelectorAll(s)];
  /* phones: depth blur on huge set pieces exhausts WebKit GPU memory, so those fade by opacity only */
  const LITE = mobile || matchMedia("(pointer:coarse)").matches, FS = LITE ? .5 : 1;
  if (LITE) root.classList.add("lite");

  /* flight plan: position (y+ down) + rotation; st = station index, hold = timeline units */
  const P = (x, y, z, yaw = 0, pitch = 0, roll = 0, st = -1, hold = 0) => ({ x: x * XS, y, z, yaw, pitch, roll, st, hold });
  const plan = [
    P(    0,     0,      0,   0,   0,   0, 0, 1.3),   // mark + promise
    P(  420,  -620,  -1500,  18, -10,  -5),
    P( -200, -1350,  -3000, -10,   0,   0, 1, 2.0),   // where the eye comes from
    P(  900,  -500,  -4500, -28,  14,   7),
    P( 1300,   350,  -6000, -32,   0,   0, 2, 1.6),   // a system
    P(  700,  1200,  -7300, -12, -16,  -4),
    P(  150,  1750,  -8600,   0,   0,   0, 3, 1.0),   // lanes: a staircase down
    P( -800,  2300, -10000,  20,   0,   0, 4, 1.0),
    P(  350,  2850, -11400, -16,   0,   0, 5, 1.0),
    P( -600,  3400, -12800,  14,   0,   0, 6, 1.0),
    P( -300,  1400, -10600,   4,  22,   0),           //   pull back and up
    P(    0,  -650,  -9600,   0,  30,   0, 7, 1.4),   // the ramp, seen from above the staircase
    P(  500,   300, -13600,  22, -10,  -6),
    P(-1100,   500, -16200,  12,   0,   0, 8, 1.2),   // products
    P( -200,  1100, -18000,   8,  -8,   4),
    P(    0,   700, -20000,   0,   0,   0, 9, 1.4),   // close
  ];
  const TRAVEL = 1.15;
  const stations = plan.map((p, i) => p.st >= 0 ? i : -1).filter(i => i >= 0);
  const tl = []; let T = 0;
  stations.forEach((pi, k) => {
    tl.push({ kind: "hold", k, a: T, b: T + plan[pi].hold }); T += plan[pi].hold;
    if (k < stations.length - 1) { const len = TRAVEL * (1 + (stations[k + 1] - pi - 2) * .35); tl.push({ kind: "fly", k, from: pi, to: stations[k + 1], a: T, b: T + len }); T += len; }
  });
  const keys = ["x", "y", "z", "yaw", "pitch", "roll"];
  const cr = (p0, p1, p2, p3, t) => .5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t);
  const at = u => { const i = Math.min(plan.length - 2, Math.floor(u)), t = u - i, g = j => plan[clamp(j, 0, plan.length - 1)], o = {};
    keys.forEach(k => o[k] = cr(g(i - 1)[k], g(i)[k], g(i + 1)[k], g(i + 2)[k], t)); return o; };
  const poseAt = s => { for (const t of tl) { if (s <= t.b || t === tl[tl.length - 1]) {
    if (t.kind === "hold") return { pose: plan[stations[t.k]], k: t.k, local: seg(s, t.a, t.b), flying: false };
    const e = sstep(seg(s, t.a, t.b)); return { pose: at(t.from + (t.to - t.from) * e), k: e < .5 ? t.k : t.k + 1, local: e < .5 ? 1 : 0, flying: true, e }; } } };
  const rot = ([x, y, z], yaw, pitch, roll) => { let c, s;
    c = Math.cos(-yaw * D); s = Math.sin(-yaw * D); [x, z] = [x * c + z * s, -x * s + z * c];
    c = Math.cos(-pitch * D); s = Math.sin(-pitch * D); [y, z] = [y * c - z * s, y * s + z * c];
    c = Math.cos(-roll * D); s = Math.sin(-roll * D); [x, y] = [x * c - y * s, x * s + y * c]; return [x, y, z]; };

  const world = $("#world");
  const nodes = $$(".node[data-st]").map(n => { const p = plan[stations[+n.dataset.st]];
    n.style.transform = `translate3d(${p.x}px,${p.y}px,${p.z}px) rotateY(${p.yaw}deg) rotateX(${p.pitch}deg) rotateZ(${p.roll}deg)`;
    return { el: n.firstElementChild, p, blur: -1, op: -1 }; });

  /* set pieces */
  const set = $("#set"), pieces = [];
  const piece = (html, cls, x, y, z, ry = 0, rx = 0, rz = 0, track = true) => {
    const n = d.createElement("div"); n.className = "node";
    n.style.transform = `translate3d(${x * XS}px,${y}px,${z}px) rotateY(${ry}deg) rotateX(${rx}deg) rotateZ(${rz}deg)`;
    const e = d.createElement("div"); e.className = cls; e.innerHTML = html; n.append(e); set.append(n);
    if (track) pieces.push({ el: e, p: { x: x * XS, y, z }, blur: -1, op: -1, ghost: true }); return e; };
  piece("ESSENTIAL", "ghost w", 0, 60, -1100).style.fontSize = 520 * FS + "px";
  if (!LITE) piece("SIX YEARS", "ghost w", -1500, -1900, -3900, 24, 0, -6).style.fontSize = 420 * FS + "px";
  piece("A", "ghost", 2300, 200, -7600, -40).style.fontSize = 1400 * FS + "px";
  /* lane numerals removed: they competed with the lane headlines (critique 2026-09-28); the chapter squares already count lanes */
  if (!LITE) piece("STL", "ghost w", 1400, -1600, -12500, -30, 0, 8).style.fontSize = 600 * FS + "px";
  if (!LITE) piece("BUILT", "ghost w", 900, -900, -17200, -20, 0, -4).style.fontSize = 560 * FS + "px";
  piece("RUN", "ghost", -1700, 900, -22600, 18).style.fontSize = 900 * FS + "px";
  for (let i = 0; i < (LITE ? 0 : 14); i++) { const z = -1600 - i * 1500, yd = [10, 20, 30, 40, 50, 40, 30, 20, 10, 20, 30, 40, 50, 40][i];
    piece(`<b class="l">${yd}</b><b class="r">${yd}</b>`, "yard", 0, 4600, z, 0, 90, 0, false); }
  let gi = 0;
  if (!LITE) tl.filter(t => t.kind === "fly").forEach(t => [.3, .62].forEach(f => {
    const g = at(t.from + (t.to - t.from) * f), n = d.createElement("div"); n.className = "node";
    n.style.transform = `translate3d(${g.x}px,${g.y}px,${g.z}px) rotateY(${g.yaw}deg) rotateX(${g.pitch}deg) rotateZ(${g.roll}deg)`;
    const e = d.createElement("div"); e.className = "gate"; e.innerHTML = `<b>${String(++gi).padStart(2, "0")}</b>`; n.append(e); set.append(n);
    pieces.push({ el: e, p: { x: g.x, y: g.y, z: g.z }, blur: -1, op: -1, gate: true }); }));
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < (LITE ? 24 : 190); i++) {
    const z = 400 - rnd() * 22500, x = (rnd() - .5) * 5600, y = -2800 + rnd() * 7000, s = 6 + rnd() * 16;
    const m = piece("", "mote" + (rnd() < .3 ? " p" : ""), x, y, z, 0, 0, 0, LITE); m.style.width = m.style.height = s + "px"; }

  /* beats: data-driven per station (data-beat on the .st) */
  const logo = $("#st1 .logo");
  const kinds = nodes.map(o => o.el.dataset.beat || "");
  const groups = nodes.map(o => $$("[data-b], li", o.el));
  const soft = (el, v, px = 12) => { el.style.filter = v > .99 || LITE ? "none" : `blur(${(1 - v) * px * K}px)`; };
  let opened = false;
  animate(logo, { ...(LITE ? {} : { filter: ["blur(28px)", "blur(0px)"] }), opacity: [0, 1], transform: ["scale(1.14)", "scale(1)"] }, { duration: 1.8, ease: [.22, 1, .36, 1], delay: .25 }).then(() => opened = true);
  const beats = (k, l) => nodes.forEach((o, j) => {
    const type = kinds[j], els = groups[j], state = j < k ? 1 : j > k ? 0 : -1;   // -1 = playing now
    if (type === "reveal") {
      const qq = $(".q", o.el), big = $(".big", o.el), after = $(".after", o.el);
      const a = state === 1 ? 1 : state === 0 ? .35 : ease(seg(l, 0, .25)), r = state === 1 ? 1 : state === 0 ? 0 : ease(seg(l, .25, .6)), s = state === 1 ? 1 : state === 0 ? 0 : ease(seg(l, .62, .9));
      qq.style.opacity = String(a * (1 - r * .5)); const w = 50 * (1 - r); big.style.clipPath = `inset(0% ${w}% 0% ${w}%)`; after.style.opacity = String(s);
      return;
    }
    const n = els.length; if (!n) return;
    els.forEach((el, i) => {
      let v;
      if (type === "build") { const a0 = .06 + i * (.8 / n); v = state === 1 ? 1 : state === 0 ? 0 : ease(seg(l, a0, a0 + .8 / n - .01)); soft(el, v, 14); el.style.opacity = String(.08 + .92 * v); el.style.transform = `translateY(${(1 - v) * 18}px)`; }
      else { const a0 = .06 + i * (.6 / n); v = state === 1 ? 1 : state === 0 ? 0 : ease(seg(l, a0, a0 + .3)); el.style.opacity = String(v); el.style.transform = `translateY(${(1 - v) * 14}px)`; if (type === "greet") soft(el, v); }
    });
  });

  /* frame */
  const render = s => { const r = poseAt(s); draw(r.pose, r.k, r.local, r.flying, r.e); };
  const draw = (c, k, local, flying, e) => {
    const env = flying ? .18 + .82 * Math.min(seg(e, 0, .22), 1 - seg(e, .78, 1)) : .18;
    root.style.setProperty("--env", env.toFixed(3));
    world.style.transform = `rotateZ(${-c.roll}deg) rotateX(${-c.pitch}deg) rotateY(${-c.yaw}deg) translate3d(${-c.x}px,${-c.y}px,${-c.z}px)`;
    for (const o of nodes.concat(pieces)) {
      const v = rot([o.p.x - c.x, o.p.y - c.y, o.p.z - c.z], c.yaw, c.pitch, c.roll), dz = v[2], dist = Math.hypot(dz, v[0] * .35, v[1] * .35);
      const b = Math.round(Math.min(16, (o.gate ? 0 : o.ghost ? 1.5 : 0) + (o.gate || o.ghost ? (1 - env) * 7 : 0) + (o.gate ? 0 : dist / (o.ghost ? 300 : 110))) * K * 2) / 2;
      const op0 = dz > (LITE ? (o.ghost ? 0 : 250) : 700) ? 0 :   /* phones: ghost words leave before the focal plane so a jump arc never magnifies one */ o.gate ? clamp(1 - Math.max(0, -dz) / 6000 - Math.max(0, dz) / 500) : o.ghost ? clamp(1 - dist / 11000) : clamp(1.15 - Math.max(0, -dz) / 5200 - Math.max(0, dz) / 700);
      const op = o.gate || o.ghost ? op0 * (.25 + .75 * env) : (o === nodes[k] ? op0 : op0 * clamp((env - .18) / .82));   // neighbours vanish while a slide holds, return mid-flight
      const bb = LITE ? 0 : b;
      if (bb !== o.blur) { o.el.style.filter = bb <= .5 ? "none" : `blur(${bb}px)`; o.blur = bb; }
      if (Math.abs(op - o.op) > .01) { o.el.style.opacity = op.toFixed(2); o.el.style.visibility = op < .02 ? "hidden" : "visible"; o.op = op; }
    }
    nodes.forEach((o, i) => o.el.classList.toggle("off", i !== k || flying));
    beats(k, local);
  };

  /* stepper: one gesture = one full move */
  root.classList.add("stepper");
  const holds = tl.filter(t => t.kind === "hold"), N = holds.length, FLY = 1.5;
  const BEATS = [1.6, 4.2, 2.2, 1.4, 1.4, 1.4, 1.4, 1.8, 1.4, 1.3];
  let s = 0, cur = 0, busy = false, anim = null, pending = null;
  const cue = $("#cue");
  if (matchMedia("(pointer:coarse)").matches) $("#cueword").textContent = "Swipe";
  const chaps = $$(".chapters a");
  const mark = () => { cue.classList.toggle("gone", cur > 0);
    chaps.forEach(a => { const on = cur >= +a.dataset.go && cur <= +a.dataset.to; on ? a.setAttribute("aria-current", "step") : a.removeAttribute("aria-current");
      $$(".ticks b", a).forEach((t, j) => t.classList.toggle("on", on && cur - +a.dataset.go === j)); }); };
  const unlock = () => setTimeout(() => { busy = false; if (pending != null) { const p = pending; pending = null; go(p); } }, 350);
  const tween = (to, dur) => new Promise(res => { const a = animate(s, to, { duration: dur, ease: "linear", onUpdate: v => { s = v; render(s); } }); anim = a;
    a.then(() => { if (anim === a) { s = to; render(s); } res(); }); });
  /* chapter jumps: one direct camera move to the target, arcing up over the world, instead of replaying every leg and hold in between */
  const jump = (i, to) => new Promise(res => {
    const A = { ...poseAt(s).pose }, B = plan[stations[i]], from = cur;
    const dist = Math.hypot(B.x - A.x, B.y - A.y, B.z - A.z), lift = Math.min(1400, 300 + dist * .07), dur = 1.5 + Math.min(.7, dist / 25000);
    const a = animate(0, 1, { duration: dur, ease: "linear", onUpdate: t => {
      const e = sstep(t), arc = Math.sin(Math.PI * e), c = {};
      keys.forEach(k => c[k] = A[k] + (B[k] - A[k]) * e);
      c.y -= lift * arc; c.pitch += 16 * arc;                 // rise and look down on the path, then settle onto the target
      draw(c, e < .5 ? from : i, e < .5 || i < from ? 1 : 0, true, e); } });
    anim = a; a.then(() => { if (anim === a) { s = to; render(s); } res(); });
  });
  async function go(i, queue = false) {
    i = clamp(i, 0, N - 1); if (busy) { if (queue) pending = i; return; } if (i === cur) return;
    busy = true; if (anim) anim.stop();
    const fwd = i > cur, hops = Math.abs(i - cur);
    if (hops > 1) { const to = fwd ? holds[i].a : holds[i].b; await jump(i, to); cur = i; mark(); unlock(); if (fwd) tween(holds[i].b, BEATS[i]); return; }
    if (fwd && s < holds[cur].b - .001) await tween(holds[cur].b, .3);
    const span = Math.abs((fwd ? holds[i].a : holds[i].b) - s) / TRAVEL;
    const dur = Math.min(3.2, FLY * Math.max(1, hops === 1 ? span * .8 : 1 + (hops - 1) * .4));
    if (fwd) { await tween(holds[i].a, dur); cur = i; mark(); unlock(); tween(holds[i].b, BEATS[i]); }
    else { await tween(holds[i].b, dur); cur = i; mark(); unlock(); }
  }
  const next = () => go(cur + 1), prev = () => go(cur - 1);
  const menuOpen = () => root.classList.contains("menu-open");
  let acc = 0, lastWheel = 0;
  addEventListener("wheel", e => { if (menuOpen()) return; e.preventDefault();
    const now = performance.now(); if (now - lastWheel > 220) acc = 0; lastWheel = now;
    if (busy) { acc = 0; return; } acc += e.deltaY; if (Math.abs(acc) > 40) { acc > 0 ? next() : prev(); acc = 0; } }, { passive: false });
  let ty = null;
  addEventListener("touchstart", e => { ty = e.touches[0].clientY; }, { passive: true });
  addEventListener("touchmove", e => { if (!menuOpen()) e.preventDefault(); }, { passive: false });
  addEventListener("touchend", e => { if (ty == null || menuOpen()) return; const dy = ty - e.changedTouches[0].clientY; ty = null; if (Math.abs(dy) > 45) dy > 0 ? next() : prev(); }, { passive: true });
  addEventListener("keydown", e => { if (menuOpen()) return;
    if (["ArrowDown", "PageDown", " ", "ArrowRight"].includes(e.key) && !e.target.closest("a,button")) { e.preventDefault(); next(); }
    else if (["ArrowUp", "PageUp", "ArrowLeft"].includes(e.key)) { e.preventDefault(); prev(); }
    else if (e.key === "Home") go(0); else if (e.key === "End") go(N - 1); });
  cue.addEventListener("click", next);
  /* chapter nav: jump straight to a section in one direct flight (see jump) */
  chaps.forEach(a => a.addEventListener("click", e => { e.preventDefault(); go(+a.dataset.go, true); history.replaceState(null, "", a.getAttribute("href")); }));
  const deep = chaps.find(a => a.getAttribute("href") === location.hash);
  render(0); mark(); root.classList.add("ready");
  if (deep && +deep.dataset.go > 0) setTimeout(() => go(+deep.dataset.go, true), 500);
  else setTimeout(() => { if (cur === 0 && !busy) { busy = true; tween(holds[0].b, BEATS[0]).then(() => busy = false); } }, 1500);
  addEventListener("resize", () => render(s));
  window.__gasp = { T, render, holds, go: i => go(i) };

  /* Amicro #11 magnetic on the primary CTA */
  const book = $("#book");
  if (book && matchMedia("(hover:hover)").matches) {
    book.addEventListener("pointermove", e => { const r = book.getBoundingClientRect(); book.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * .35}px,${(e.clientY - r.top - r.height / 2) * .35}px)`; });
    book.addEventListener("pointerleave", () => { book.style.transform = ""; });
  }
})();
