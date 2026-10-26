/* GASP! bots · the little agents that are always working.
   Usage:  <canvas class="gbot" data-bot="relay" aria-hidden="true"></canvas>  + bots.js loaded with defer
   Each scene is drawn as a grey brightness map (320 × 200 units), then printed as the site's orange
   dot screen: 30° grid, dot area ∝ brightness, 3-frame boil. Only animates while on screen;
   reduced-motion visitors get one still frame. Scenes: plug relay budget guard leads brand content
   socialcut build cheer pickme nightshift. */
(() => {
  const LW = 320, LH = 200, FY = 176, TAU = Math.PI * 2;
  const OR = "#E84B1C";
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const sm = t => { t = clamp(t); return t * t * (3 - 2 * t); };
  const seg = (t, a, b) => sm((t - a) / (b - a));
  const lerp = (a, b, k) => a + (b - a) * k;
  const hop = k => Math.sin(clamp(k) * Math.PI);
  const G = v => { const n = Math.round(clamp(v) * 255); return `rgb(${n},${n},${n})`; };

  /* ---------- drawing kit (all values are brightness 0..1) ---------- */
  function rr(c, x, y, w, h, r, v) { c.fillStyle = G(v); c.beginPath(); c.roundRect(x, y, w, h, r); c.fill(); }
  function circ(c, x, y, r, v) { if (r <= 0) return; c.fillStyle = G(v); c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill(); }
  function ln(c, pts, w, v) { c.strokeStyle = G(v); c.lineWidth = w; c.lineCap = "round"; c.lineJoin = "round"; c.beginPath(); pts.forEach(([x, y], i) => i ? c.lineTo(x, y) : c.moveTo(x, y)); c.stroke(); }
  function poly(c, pts, v) { c.fillStyle = G(v); c.beginPath(); pts.forEach(([x, y], i) => i ? c.lineTo(x, y) : c.moveTo(x, y)); c.closePath(); c.fill(); }
  function glow(c, x, y, rx, ry, v) {
    c.save(); c.globalCompositeOperation = "lighter"; c.translate(x, y); c.scale(1, ry / rx);
    const g = c.createRadialGradient(0, 0, 0, 0, 0, rx); g.addColorStop(0, G(v)); g.addColorStop(1, "rgb(0,0,0)");
    c.fillStyle = g; c.beginPath(); c.arc(0, 0, rx, 0, TAU); c.fill(); c.restore();
  }
  function floor(c) { for (let x = 8; x < LW - 6; x += 7) circ(c, x, FY + 5, 1.1, .3); }
  function tick(c, x, y, s, v, w = 3.4) { ln(c, [[x - 6 * s, y], [x - 2 * s, y + 4.5 * s], [x + 7 * s, y - 5.5 * s]], w * s, v); }
  function heart(c, x, y, s, v) { circ(c, x - 4 * s, y - 2 * s, 4.6 * s, v); circ(c, x + 4 * s, y - 2 * s, 4.6 * s, v); poly(c, [[x - 8.6 * s, y], [x + 8.6 * s, y], [x, y + 9 * s]], v); }
  function bang(c, x, y, s, v) { poly(c, [[x - 1 * s, y - 10 * s], [x + 5 * s, y - 10 * s], [x + 2 * s, y + 3 * s], [x - 3 * s, y + 3 * s]], v); circ(c, x - 1.6 * s, y + 8 * s, 2.6 * s, v); }
  function bubble(c, x, y, w, h, kind, T) {
    c.strokeStyle = G(1); c.lineWidth = 3; c.beginPath(); c.roundRect(x, y, w, h, h / 2.4); c.stroke();
    poly(c, [[x + 9, y + h - 1], [x + 5, y + h + 8], [x + 17, y + h - 1]], 1);
    const cx = x + w / 2, cy = y + h / 2;
    if (kind === "dots") for (let k = 0; k < 3; k++) circ(c, cx + (k - 1) * 9, cy - Math.max(0, Math.sin(T * TAU * 1.6 - k * .9)) * 2.6, 2.7, 1);
    if (kind === "check") tick(c, cx, cy, 1, 1);
    if (kind === "heart") heart(c, cx, cy - 1, .9, 1);
    if (kind === "bang") bang(c, cx + 1, cy - 2, 1, 1);
    if (kind === "q") { c.strokeStyle = G(1); c.lineWidth = 3; c.lineCap = "round"; c.beginPath(); c.arc(cx, cy - 3, 4.5, Math.PI * 1.05, Math.PI * 2.45); c.stroke(); circ(c, cx, cy + 7, 1.9, 1); }
  }
  /* the job: a page that fills in as it moves down the line */
  function doc(c, x, y, s = 1, lines = 1, checked = false, v = 1) {
    c.save(); c.translate(x, y); c.scale(s, s);
    rr(c, -15, -19, 30, 38, 6, 0); rr(c, -12, -16, 24, 32, 4, v);
    for (let k = 0; k < lines; k++) rr(c, -7, -10 + k * 6.5, k % 2 ? 9 : 14, 3.4, 1.7, 0);
    if (checked) { circ(c, 10, 14, 7.5, 0); tick(c, 10.5, 14, .62, 1, 3.6); }
    c.restore();
  }
  /* the mascot. (x, fy) = feet; s = scale; L/R = hand targets in scene units (null = resting) */
  function bot(c, x, fy, s, o = {}) {
    const { bob = 0, look = 0, act = false, L = null, R = null, eyes = "happy" } = o;
    c.save(); c.translate(x, fy); c.scale(s, s);
    const hy = -90 + bob;
    rr(c, -20, -36, 40, 36, 10, .36);                                  // body
    const hands = [];
    for (const [sx, tgt] of [[-19, L], [19, R]]) {                       // arms
      let hx, hy2;
      if (tgt) { hx = (tgt[0] - x) / s; hy2 = (tgt[1] - fy) / s; } else { hx = sx + Math.sign(sx) * 6; hy2 = -12; }
      c.strokeStyle = G(.62); c.lineWidth = 5; c.lineCap = "round"; c.beginPath(); c.moveTo(sx, -29);
      c.quadraticCurveTo((sx + hx) / 2 + Math.sign(sx) * 4, (-29 + hy2) / 2 + 8, hx, hy2); c.stroke();
      hands.push([hx, hy2]);
    }
    rr(c, -33, hy, 66, 50, 17, .93);                                    // head
    ln(c, [[0, hy], [0, hy - 11]], 3, .93); circ(c, 0, hy - 15, 5, act ? 1 : .78);  // antenna
    c.strokeStyle = G(0); c.lineWidth = 5; c.lineCap = "round";
    for (const ex of [-13, 13]) {                                        // eyes
      const cx = ex + look, cy = hy + 29;
      if (eyes === "o") circ(c, cx, cy - 3, 5, 0);
      else { c.beginPath(); c.arc(cx, cy, 7, Math.PI * 1.06, Math.PI * 1.94); c.stroke(); }   // happy: ^ ^
    }
    for (const [hx, hy2] of hands) circ(c, hx, hy2, 4.6, .9);           // hands over the head
    c.restore();
  }
  const fadeOut = (t, a = .9, b = .98) => t > a ? 1 - seg(t, a, b) : 1;

  /* ---------- scenes: P = loop seconds, still = phase for reduced motion ---------- */
  const S = {};

  /* Workspace deployment: walks the plug over, plugs in, your apps light up */
  S.plug = { P: 5.6, still: .72, draw(c, t, T) {
    floor(c);
    rr(c, 262, 52, 42, FY - 52, 9, .12);
    rr(c, 270, 140, 24, 19, 5, .88); rr(c, 276, 145, 3, 9, 1.5, 0); rr(c, 285, 145, 3, 9, 1.5, 0);
    const lit = [.46, .54, .62].map(a => t < .88 ? seg(t, a, a + .05) : 1 - seg(t, .88, .93));
    rr(c, 275, 64, 14, 14, 4, .18 + .82 * lit[0]);
    circ(c, 282, 98, 7.5, .18 + .82 * lit[1]);
    poly(c, [[282, 113], [290, 127], [274, 127]], .18 + .82 * lit[2]);
    const walkIn = seg(t, .05, .36), walkOut = seg(t, .88, 1);
    const bx = t < .88 ? lerp(88, 222, walkIn) : lerp(222, 88, walkOut);
    const walking = (t > .05 && t < .36) || t > .88;
    const px = bx + 28, py = FY - 27;
    ln(c, [[0, FY - 3], [px * .5, FY + 3], [px, py + 1]], 3, .5);           // cable
    rr(c, px, py - 5, 13, 11, 3, .95); rr(c, px + 13, py - 3, 6, 2.4, 1, .95); rr(c, px + 13, py + 1.5, 6, 2.4, 1, .95);
    glow(c, bx, FY + 2, 46, 9, lit[2] > .5 ? .3 : .12);
    bot(c, bx, FY, 1, { act: lit[0] > .5, bob: walking ? -Math.abs(Math.sin(T * TAU * 2.2)) * 4 : Math.sin(T * TAU * .8) * 1.2, look: 3, R: [px + 3, py] });
    if (t > .36 && t < .5) { const k = seg(t, .36, .5); for (let i = 0; i < 7; i++) { const a = i / 7 * TAU; circ(c, 271 + Math.cos(a) * k * 18, py + Math.sin(a) * k * 18, 2.4 * (1 - k) + .4, 1 - k * .6); } }
    if (t > .68 && t < .88) bubble(c, bx - 4, FY - 128, 40, 23, "check", T);
  } };

  /* Managed agents: take it in, do the work, check it, ship it */
  S.relay = { P: 5.4, still: .46, draw(c, t, T) {
    const AX = [70, 160, 250], s = .74, HY = FY - 20;
    let jx, jy, busy = null;
    if (t < .12) { const k = seg(t, 0, .12); jx = lerp(-30, AX[0], k); jy = HY - hop(k) * 12; busy = 0; }
    else if (t < .27) { jx = AX[0]; jy = HY; busy = 0; }
    else if (t < .37) { const k = seg(t, .27, .37); jx = lerp(AX[0], AX[1], k); jy = HY - hop(k) * 16; }
    else if (t < .57) { jx = AX[1]; jy = HY; busy = 1; }
    else if (t < .67) { const k = seg(t, .57, .67); jx = lerp(AX[1], AX[2], k); jy = HY - hop(k) * 16; }
    else if (t < .84) { jx = AX[2]; jy = HY; busy = 2; }
    else { const k = seg(t, .84, 1); jx = lerp(AX[2], 352, k); jy = HY - hop(k) * 12; }
    floor(c);
    AX.forEach((x, i) => glow(c, x, FY + 2, 46, 9, busy === i ? .34 : .1));
    AX.forEach((x, i) => {
      const act = busy === i;
      bot(c, x, FY, s, { act, bob: act ? Math.sin(T * TAU * 1.1 + i) * 3 : Math.sin(T * 2 + i) * .8, look: clamp((jx - x) / 30, -4, 4) });
      if (act) bubble(c, x + 8, FY - 126, 40, 23, i === 2 ? "check" : "dots", T);
    });
    const lines = t < .37 ? 1 : t < .57 ? 1 + Math.floor(3 * seg(t, .4, .55)) : 4;
    doc(c, jx, jy, 1.05, lines, t >= .74);
  } };

  /* Managed AI spend: stacks to the cap, then the rest goes in the jar */
  S.budget = { P: 6.2, still: .7, draw(c, t, T) {
    floor(c);
    const SX = 172, CH = 7, capY = FY - 6 * CH - 4;
    for (let x = 132; x < 312; x += 11) rr(c, x, capY - 1, 6, 2.2, 1, .95);
    c.strokeStyle = G(.66); c.lineWidth = 3; c.beginPath(); c.roundRect(252, FY - 46, 38, 46, 9); c.stroke(); rr(c, 248, FY - 51, 46, 6, 3, .66);
    const f = fadeOut(t);
    const coin = (x, y, v) => { rr(c, x - 14, y - 3, 28, 7, 3, .6 * v); c.fillStyle = G(v); c.beginPath(); c.ellipse(x, y - 3, 14, 3.8, 0, 0, TAU); c.fill(); };
    const bx = 84, hand = [bx + 28, FY - 60];
    const T0 = [.05, .13, .21, .29, .37, .45, .62, .72];
    T0.forEach((a, k) => {
      if (t < a) return;
      const kk = seg(t, a, a + .07);
      const tx = k < 6 ? SX : 271, ty = k < 6 ? FY - k * CH - 4 : FY - 8 - (k - 6) * CH;
      coin(lerp(hand[0], tx, kk), lerp(hand[1], ty, kk) - hop(kk) * 34, f);
    });
    const next = T0.find(a => a > t); if (next !== undefined && next - t < .05 && t < .8) coin(hand[0], hand[1] - 4, 1);
    glow(c, bx, FY + 2, 44, 9, .2);
    const atCap = t > .52 && t < .9;
    bot(c, bx, FY, 1, { act: atCap, bob: Math.sin(T * TAU * .9) * 1.4, look: atCap ? 4 : 2, R: hand });
    if (t > .52 && t < .62) bubble(c, bx - 6, FY - 128, 40, 23, "bang", T);
    if (t > .64 && t < .88) bubble(c, bx - 6, FY - 128, 40, 23, "check", T);
  } };

  /* Security + governance: every job is checked against the rules at the gate, then waved through */
  S.guard = { P: 5.8, still: .58, draw(c, t, T) {
    floor(c);
    const a = t < .52 ? 0 : t < .6 ? seg(t, .52, .6) * 1.3 : t < .86 ? 1.3 : 1.3 - seg(t, .86, .94) * 1.3;
    const dx = t < .3 ? lerp(-24, 84, seg(t, 0, .3)) : t < .6 ? 84 : lerp(84, 360, seg(t, .6, .88));
    rr(c, 184, FY - 60, 11, 60, 3, .72);
    c.save(); c.translate(189.5, FY - 52); c.rotate(a);
    for (let i = 0; i < 8; i++) rr(c, -90 + i * 11, -4.5, 11.5, 9, i === 0 ? 4 : 0, i % 2 ? .95 : .3);
    c.restore();
    circ(c, 189.5, FY - 52, 5, .95);
    const ask = t > .3 && t < .45, ok = t > .45 && t < .6;
    glow(c, 254, FY + 2, 44, 9, ok ? .32 : .12);
    bot(c, 254, FY, .95, { act: ask || ok, look: clamp((dx - 254) / 30, -4, 4), bob: Math.sin(T * TAU * .8) * 1.2, R: ok ? [284, FY - 104] : null });
    if (ask) bubble(c, 248, FY - 124, 40, 23, "dots", T);
    if (ok) bubble(c, 214, FY - 124, 40, 23, "check", T);
    doc(c, dx, FY - 20, 1.1, 3, t > .45);
  } };

  /* Lead generation: every card gets a look; the good ones get kept */
  S.leads = { P: 6, still: .26, draw(c, t, T) {
    floor(c);
    const LX = 132, LY = FY - 36;
    let under = false;
    for (let i = 0; i < 4; i++) {
      const x = 350 - ((t * 380 + i * 95) % 380), q = i % 2 === 0, passed = x < LX, near = Math.abs(x - LX) < 15;
      if (near) under = true;
      let y = LY, v = passed ? (q ? 1 : .4) : near ? .95 : .55;
      if (passed && !q) { y += (LX - x) * .55; v *= clamp(1 - (LX - x) / 60); }
      if (passed && q) { y -= (LX - x) * .35; v *= clamp((x - 70) / 50); }
      if (v <= .01) continue;
      rr(c, x - 17, y - 22, 34, 44, 6, v); circ(c, x, y - 9, 6, 0);
      rr(c, x - 9, y + 3, 18, 3.4, 1.7, 0); rr(c, x - 6, y + 10, 12, 3.4, 1.7, 0);
      if (passed && q) { circ(c, x + 14, y - 20, 7.5, 0); tick(c, x + 14.5, y - 20, .62, 1, 3.6); }
    }
    glow(c, 64, FY + 2, 44, 9, under ? .3 : .14);
    bot(c, 64, FY, .95, { act: under, look: 4, bob: Math.sin(T * TAU * .9) * 1.2, R: [LX - 25, LY + 25] });
    ln(c, [[LX - 24, LY + 24], [LX - 12, LY + 12]], 5, .9);
    c.strokeStyle = G(1); c.lineWidth = 4; c.beginPath(); c.arc(LX, LY, 16, 0, TAU); c.stroke();
    if (under) circ(c, LX - 6, LY - 7, 2.6, 1);
  } };

  /* Brand + design: paints the bang, steps back, loves it */
  S.brand = { P: 6.2, still: .7, draw(c, t, T) {
    floor(c);
    rr(c, 186, 28, 118, FY - 30, 8, .1);
    ln(c, [[200, FY - 4], [192, FY + 4]], 3, .42); ln(c, [[290, FY - 4], [298, FY + 4]], 3, .42);
    const rev = t < .06 ? 0 : t < .66 ? seg(t, .06, .66) : t < .92 ? 1 : 1 - seg(t, .92, .99);
    const top = 40, bot0 = 152, front = top + rev * (bot0 - top);
    c.save(); c.beginPath(); c.rect(186, 28, 118, front - 28); c.clip();
    poly(c, [[244, 42], [280, 42], [263, 116], [234, 116]], .97); circ(c, 245, 136, 11, .97);
    c.restore();
    const painting = t > .06 && t < .66;
    let tx, ty;
    if (painting) { const yy = clamp(front, top + 2, bot0 - 4), l = yy < 118 ? lerp(244, 234, (yy - 42) / 74) : 236, r = yy < 118 ? lerp(280, 263, (yy - 42) / 74) : 254;
      tx = lerp(l, r, (Math.sin(T * TAU * 2.3) + 1) / 2); ty = yy; } else { tx = 196; ty = 116; }
    rr(c, 126, FY - 14, 46, 14, 4, .3);                                // step stool
    glow(c, 150, FY + 2, 44, 9, .18);
    const hx = tx - 30, hy = ty + 24;
    bot(c, 150, FY - 14, 1, { act: painting, look: 4, bob: painting ? Math.sin(T * TAU * 2.3) * 1.5 : 0, R: [hx, hy] });
    ln(c, [[hx, hy], [tx - 3, ty + 3]], 3, .8); circ(c, tx, ty, 4.6, 1);
    if (t > .7 && t < .9) bubble(c, 140, FY - 142, 40, 23, "heart", T);
  } };

  /* Content production: rolling camera, posts pop out into the queue */
  S.content = { P: 6.2, still: .66, draw(c, t, T) {
    floor(c);
    ln(c, [[132, FY - 56], [116, FY]], 3, .5); ln(c, [[132, FY - 56], [148, FY]], 3, .5); ln(c, [[132, FY - 56], [132, FY]], 3, .5);
    rr(c, 112, FY - 82, 40, 26, 6, .9); rr(c, 120, FY - 88, 14, 6, 2, .9);
    circ(c, 158, FY - 69, 10, 1); circ(c, 158, FY - 69, 5, 0);
    circ(c, 119, FY - 76, 2.8, Math.floor(T * 2) % 2 ? 0 : .9);
    const f = fadeOut(t);
    for (let k = 0; k < 5; k++) { c.strokeStyle = G(.22); c.lineWidth = 1.5; c.beginPath(); c.roundRect(186 + k * 25, FY - 75, 19, 31, 4); c.stroke(); }
    for (let k = 0; k < 5; k++) {
      const a = .1 + k * .13; if (t < a) continue;
      const kk = seg(t, a, a + .08), x = lerp(166, 195.5 + k * 25, kk), y = lerp(FY - 69, FY - 59.5, kk) - hop(kk) * 22, s = lerp(.4, 1, kk);
      c.save(); c.translate(x, y); c.scale(s, s); rr(c, -9.5, -15.5, 19, 31, 4, .95 * f);
      poly(c, [[-3, -5], [5, 0], [-3, 5]], 0); c.restore();
    }
    glow(c, 74, FY + 2, 44, 9, .2);
    bot(c, 74, FY, 1, { act: true, look: 3, bob: Math.sin(T * TAU * .9) * 1.2, R: [112, FY - 70] });
    if (t > .76 && t < .9) bubble(c, 64, FY - 128, 40, 23, "check", T);
  } };

  /* Social Cut: one wide video in, a stack of vertical posts out */
  S.socialcut = { P: 5.6, still: .66, draw(c, t, T) {
    floor(c);
    const busy = t > .32 && t < .62, shake = busy ? Math.sin(T * 70) * .8 : 0;
    const wx = t < .08 ? 94 : lerp(94, 160, seg(t, .08, .32));
    if (t < .34) { rr(c, wx - 23, FY - 57, 46, 28, 5, .95); poly(c, [[wx - 4, FY - 49], [wx + 6, FY - 43], [wx - 4, FY - 37]], 0); }
    c.save(); c.translate(shake, 0);
    rr(c, 138, FY - 80, 70, 80, 11, .42); rr(c, 134, FY - 60, 7, 34, 2, 0); rr(c, 205, FY - 32, 9, 20, 2, 0);
    const ga = busy ? T * 5 : 0, gx = 173, gy = FY - 46;
    for (let i = 0; i < 8; i++) { c.save(); c.translate(gx, gy); c.rotate(ga + i * TAU / 8); rr(c, -3, -17, 6, 7, 1.5, .92); c.restore(); }
    circ(c, gx, gy, 12, .92); circ(c, gx, gy, 4, 0);
    c.restore();
    const f = fadeOut(t);
    for (let k = 0; k < 3; k++) {
      const a = .46 + k * .08; if (t < a) continue;
      const kk = seg(t, a, a + .07), x = lerp(212, 236 + k * 26, kk), y = lerp(FY - 22, FY - 19, kk) - hop(kk) * 26;
      rr(c, x - 9, y - 16, 18, 32, 4, .95 * f); poly(c, [[x - 3, y - 5], [x + 5, y], [x - 3, y + 5]], 0);
    }
    const cheer = t > .66 && t < .9;
    glow(c, 64, FY + 2, 44, 9, cheer ? .32 : .14);
    const j = cheer ? hop((T * 2.2) % 1) * 7 : 0;
    bot(c, 64, FY - j, 1, { act: cheer, look: 3, R: t < .32 ? [wx - 24, FY - 43 + j] : cheer ? [90, FY - 116] : null, L: cheer ? [38, FY - 116] : null });
  } };

  /* Custom solutions: builds the thing, plants the flag */
  S.build = { P: 6.4, still: .82, draw(c, t, T) {
    floor(c);
    const B = [[170, FY - 18], [200, FY - 18], [230, FY - 18], [185, FY - 36], [215, FY - 36], [200, FY - 54]];
    const land = B.map((_, k) => .06 + k * .1), f = fadeOut(t);
    B.forEach(([x, y], k) => {
      if (t < land[k] - .06) return;
      const kk = seg(t, land[k] - .06, land[k]), yy = y - (1 - kk) * 70;
      rr(c, x, yy, 28, 18, 3, .9 * f); rr(c, x + 5, yy + 7.5, 18, 3, 1.5, 0);
    });
    if (t > .68) { const k = seg(t, .68, .76); ln(c, [[214, FY - 54], [214, FY - 54 - 26 * k]], 2.6, .9 * f); if (k > .9) poly(c, [[215, FY - 80], [232, FY - 74], [215, FY - 68]], .95 * f); }
    let sw = 0; for (const L of land) { const d = t - L; if (d > 0 && d < .06) sw = Math.sin(d / .06 * Math.PI); }
    const hx = 140, hy = FY - 42;
    glow(c, 112, FY + 2, 44, 9, .2);
    bot(c, 112, FY, .95, { act: sw > 0, look: 4, bob: Math.sin(T * TAU * .9) * 1.2, R: [hx, hy] });
    c.save(); c.translate(hx, hy); c.rotate(.5 + sw * .9); ln(c, [[0, 0], [0, -24]], 3.4, .8); rr(c, -8, -31, 16, 9, 2, 1); c.restore();
    if (t > .78 && t < .9) bubble(c, 102, FY - 124, 40, 23, "bang", T);
  } };

  /* About (pro sports): game night, foam finger up */
  S.cheer = { P: 4, still: .25, draw(c, t, T) {
    [[48, 6, 44], [160, -2, 36], [272, 6, 44]].forEach(([x, y, r], i) => glow(c, x, y, r, r, .5 + .12 * Math.sin(T * 3 + i)));
    for (let i = 0; i * 15 < LW + 10; i++) circ(c, 4 + i * 15, FY - 4 + Math.sin(T * 6 + i * 1.7) * 1.4, 6, .22);
    const slot = Math.floor(T * 4);
    for (let n = 0; n < 2; n++) { const r = Math.abs(Math.sin(slot * 12.9898 + n * 78.233) * 43758.5453) % 1, x = 12 + r * 296, y = FY - 22 - ((r * 7) % 1) * 30, k = (T * 4) % 1, s = 6 * (1 - k);
      if (Math.abs(x - 160) < 40) continue; ln(c, [[x - s, y], [x + s, y]], 2, 1 - k); ln(c, [[x, y - s], [x, y + s]], 2, 1 - k); }
    const j = hop((t * 2) % 1) * 12;
    glow(c, 160, FY + 2, 50, 10, .3);
    const fx = 196, fy = FY - j - 116;
    bot(c, 160, FY - j, 1.1, { act: true, R: [fx, fy + 6], L: [126, FY - j - 104 + Math.sin(T * TAU * 2) * 10] });
    c.save(); c.translate(fx, fy); c.rotate(.18); rr(c, -11, -6, 22, 20, 6, 1); rr(c, -5, -34, 10, 32, 5, 1); rr(c, -11, 4, 22, 3, 1.5, 0); c.restore();
  } };

  /* Closing question: three eager hires, hands up */
  S.pickme = { P: 3.6, still: .12, draw(c, t, T) {
    floor(c);
    const X = [70, 160, 250], a = Math.floor(t * 3) % 3, k = (t * 3) % 1;
    X.forEach((x, i) => {
      const act = i === a, up = act ? seg(k, 0, .16) * (1 - seg(k, .86, 1)) : 0, j = act ? hop((k * 2.4) % 1) * 7 * up : 0;
      glow(c, x, FY + 2, 44, 9, act ? .3 : .1);
      bot(c, x, FY - j, .82, { act, bob: act ? 0 : Math.sin(T * 2 + i) * .7, R: up > .05 ? [x + 18 + 18 * up, FY - j - 50 - 46 * up] : null });
    });
  } };

  /* Footer: 2am, still shipping */
  S.nightshift = { P: 6, still: .3, draw(c, t, T) {
    rr(c, 210, 14, 96, 66, 7, .26); rr(c, 214, 18, 88, 58, 5, 0);
    circ(c, 278, 40, 11, .95); circ(c, 283, 36, 10, 0);
    [[230, 32], [250, 58], [292, 64]].forEach(([x, y], i) => circ(c, x, y, 1.8, .35 + .65 * Math.max(0, Math.sin(T * 2.4 + i * 2.1))));
    const tap = Math.sin(T * TAU * 3.2);
    bot(c, 112, FY - 12, 1, { act: true, look: 3, bob: Math.sin(T * TAU * .5) * 1, L: [152, FY - 47 + Math.max(0, tap) * -3], R: [168, FY - 47 + Math.max(0, -tap) * -3] });
    rr(c, 150, FY - 86, 50, 40, 5, .55); circ(c, 175, FY - 66, 4.5, .95); rr(c, 146, FY - 47, 60, 6, 2, .8);
    rr(c, 54, FY - 41, 214, 8, 3, .5); rr(c, 66, FY - 33, 6, 33, 2, .34); rr(c, 250, FY - 33, 6, 33, 2, .34);
    rr(c, 218, FY - 59, 15, 18, 3, .8); c.strokeStyle = G(.8); c.lineWidth = 2.6; c.beginPath(); c.arc(234, FY - 50, 5, -Math.PI / 2, Math.PI / 2); c.stroke();
    for (let s = 0; s < 2; s++) { const p = (T * .55 + s * .5) % 1, y0 = FY - 62 - p * 24, pts = [];
      for (let k = 0; k < 4; k++) { const y = y0 - k * 4; pts.push([222 + s * 7 + Math.sin(y * .35 + T * 3) * 2, y]); } ln(c, pts, 2, .55 * (1 - p)); }
    const p = (T / 1.5) % 1; if (p < .8) tick(c, 175, FY - 94 - p * 40, 1, 1 - p / .8, 3.6);
  } };

  /* ---------- the printer: brightness map -> orange dot screen ---------- */
  const OFFS = [[0, 0], [1 / 3, 1 / 4], [-1 / 4, 1 / 3]];
  const css = document.createElement("style");
  css.textContent = ".gbot{display:block;width:100%;height:auto;aspect-ratio:16/10;max-width:100%}";
  document.head.appendChild(css);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const live = new Set();

  class Bot {
    constructor(cv) {
      this.cv = cv; this.scene = S[cv.dataset.bot] || S.relay; this.on = false; this.last = 0;
      this.phase = Math.random() * this.scene.P;
      this.ctx = cv.getContext("2d");
      this.off = document.createElement("canvas"); this.oc = this.off.getContext("2d", { willReadFrequently: true });
      this.size();
    }
    size() {
      const w = this.cv.getBoundingClientRect().width || 320, dpr = Math.min(2, devicePixelRatio || 1);
      const W = Math.max(64, Math.round(w * dpr)), H = Math.round(W * LH / LW);
      if (W === this.W) return;
      this.W = W; this.H = H; this.cv.width = W; this.cv.height = H;
      this.cell = this.cv.dataset.dots ? W / Number(this.cv.dataset.dots) : Math.max(3.6 * dpr, W / 118);
      const q = Math.min(2, Math.max(1, W / LW)); this.sw = Math.round(LW * q); this.sh = Math.round(LH * q);
      this.off.width = this.sw; this.off.height = this.sh; this.q = q;
      const a = Math.PI / 6, ca = Math.cos(a), sa = Math.sin(a), n = Math.ceil(Math.hypot(W, H) / 2 / this.cell) + 1;
      this.grids = OFFS.map(([ox, oy], g) => {
        const pts = []; let seed = 1013 + g * 7919;
        const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
        for (let i = -n; i <= n; i++) for (let j = -n; j <= n; j++) {
          const u = (i + ox) * this.cell, v = (j + oy) * this.cell, x = u * ca - v * sa + W / 2, y = u * sa + v * ca + H / 2;
          if (x < -this.cell || y < -this.cell || x > W + this.cell || y > H + this.cell) continue;
          const sx = clamp(Math.floor(x / W * this.sw), 0, this.sw - 1), sy = clamp(Math.floor(y / H * this.sh), 0, this.sh - 1);
          pts.push(x, y, (sy * this.sw + sx) * 4, 1 + (rnd() * 2 - 1) * .06);
        }
        return new Float32Array(pts);
      });
      this.render(performance.now());
    }
    render(now) {
      const sc = this.scene, fix = this.cv.dataset.t, frozen = reduce || fix !== undefined, ft = fix !== undefined ? +fix : sc.still;
      const T = frozen ? ft * sc.P : now / 1000 + this.phase, t = frozen ? ft : (T % sc.P) / sc.P;
      const oc = this.oc; oc.setTransform(1, 0, 0, 1, 0, 0); oc.fillStyle = "#000"; oc.fillRect(0, 0, this.sw, this.sh);
      oc.setTransform(this.q, 0, 0, this.q, 0, 0); sc.draw(oc, t, T);
      const d = oc.getImageData(0, 0, this.sw, this.sh).data, g = this.grids[frozen ? 0 : Math.floor(now / 140) % 3], k = this.cell * .72, c = this.ctx;
      c.clearRect(0, 0, this.W, this.H); c.fillStyle = OR; c.beginPath();
      for (let i = 0; i < g.length; i += 4) {
        const b = d[g[i + 2]]; if (b < 6) continue;
        const r = k * Math.sqrt(b / 255) * g[i + 3]; if (r < .4) continue;
        c.moveTo(g[i] + r, g[i + 1]); c.arc(g[i], g[i + 1], r, 0, TAU);
      }
      c.fill(); this.drawn = true;
    }
  }

  const io = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => { const b = e.target._gbot; if (b) b.on = e.isIntersecting; }), { rootMargin: "80px" }) : null;
  const ro = "ResizeObserver" in window ? new ResizeObserver(es => es.forEach(e => e.target._gbot && e.target._gbot.size())) : null;
  function mount(cv) { if (cv._gbot) return; const b = new Bot(cv); cv._gbot = b; live.add(b); if (io) io.observe(cv); else b.on = true; if (ro) ro.observe(cv); }
  function loop(now) {
    for (const b of live) if (b.on && !b.cv.dataset.idle && now - b.last > 33) { b.last = now; b.render(now); }
    requestAnimationFrame(loop);
  }
  function init() { document.querySelectorAll("canvas[data-bot]").forEach(mount); if (!reduce) requestAnimationFrame(loop); }
  function set(cv, name) { const b = cv._gbot; cv.dataset.bot = name; if (!b || !S[name] || b.scene === S[name]) return; b.scene = S[name]; b.phase = Math.random() * b.scene.P; b.render(performance.now()); }
  window.GaspBots = { mount, set, scenes: Object.keys(S) };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
