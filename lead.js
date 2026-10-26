/* GASP! Essential · lead form. Posts to /api/lead (Conversions API + email alert), fires the
   matching browser Lead event with the same event_id so Meta counts it once, then hands the
   visitor to the booking page. */
(() => {
  const form = document.querySelector("form.lead");
  if (!form) return;
  const t0 = performance.now();
  const msg = form.querySelector(".msg");
  const btn = form.querySelector('button[type="submit"]');
  const cookie = k => (document.cookie.match(new RegExp("(?:^|; )" + k + "=([^;]*)")) || [])[1] || "";
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
  const say = (t, err) => { msg.textContent = t; msg.classList.toggle("err", !!err); };
  const qs = new URLSearchParams(location.search);
  const fbc = cookie("_fbc") || (qs.get("fbclid") ? `fb.1.${Date.now()}.${qs.get("fbclid")}` : "");
  const QUALIFIED = ["10-25", "26-50"];
  const EMAIL = /^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
  const event_id = uid(); // one id per form view, reused on retry so Meta never double counts
  const page = form.dataset.page || "site";

  form.querySelectorAll("[required]").forEach(el => {
    el.setAttribute("aria-describedby", "lead-msg");
    el.addEventListener("input", () => el.removeAttribute("aria-invalid"));
    el.addEventListener("change", () => el.removeAttribute("aria-invalid"));
  });

  const done = (f, booking) => {
    form.classList.add("done"); say("");
    const ok = document.createElement("div");
    ok.className = "ok"; ok.setAttribute("role", "status"); ok.tabIndex = -1;
    const h = document.createElement("h3");
    const first = (f.name || "").trim().split(/\s+/)[0];
    h.textContent = booking ? `${first ? first + ", pick" : "Pick"} a time.` : "Got it. I'll reply today.";
    ok.appendChild(h);
    if (booking) {
      const a = document.createElement("a"); a.className = "btn"; a.href = booking; a.target = "_blank"; a.rel = "noopener";
      a.innerHTML = '<span class="t">Open the calendar</span><svg class="b" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4"/></svg>';
      const c = document.createElement("div"); c.className = "ctas"; c.appendChild(a); ok.appendChild(c);
    }
    form.prepend(ok); ok.focus({ preventScroll: false });
  };

  form.addEventListener("submit", async e => {
    e.preventDefault();
    if (btn.disabled) return;
    const f = Object.fromEntries(new FormData(form));
    let bad = null;
    for (const el of form.querySelectorAll("[required]")) {
      const ok = el.type === "email" ? EMAIL.test(el.value.trim()) : !!el.value.trim();
      if (ok) el.removeAttribute("aria-invalid"); else el.setAttribute("aria-invalid", "true");
      if (!ok && !bad) bad = el;
    }
    if (bad) { bad.focus(); say("A couple of fields still need you.", true); return; }

    btn.disabled = true; say("Sending…");
    let j;
    try {
      const r = await fetch("/api/lead", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...f, event_id, fbp: cookie("_fbp"), fbc, page, url: location.href, t: Math.round(performance.now() - t0) })
      });
      j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) throw new Error(j.error || "send");
    } catch (err) {
      btn.disabled = false;
      say("That didn't go through. Email tyler.fitton@gaspessential.com and I'll book you myself.", true);
      return;
    }
    // sent: everything below is presentation and tracking, never an error state
    try {
      if (window.fbq) {
        fbq("track", "Lead", { content_name: page }, { eventID: event_id });
        if (QUALIFIED.includes(f.size)) fbq("trackCustom", "QualifiedLead", { content_name: page }, { eventID: event_id + "-q" });
      }
    } catch (_) {}
    done(f, /^https:\/\//i.test(j.booking_url || "") ? j.booking_url : null);
  });
})();
