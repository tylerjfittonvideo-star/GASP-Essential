/* GASP! Essential · Meta pixel (browser side). Server side lives in api/lead.js (Conversions API).
   Set PIXEL_ID to the dataset ID from Events Manager. Empty = nothing loads, nothing tracks.
   The pixel ID is public by design; the CAPI access token stays in Vercel env only. */
(() => {
  const PIXEL_ID = "4545759298978855"; // GASP Essential portfolio dataset (formerly "Social Cut Web")
  if (!PIXEL_ID || window.fbq) return;
  !function (f, b, e, v, n, t, s) {
    if (f.fbq) return; n = f.fbq = function () { n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments); };
    if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = "2.0"; n.queue = [];
    t = b.createElement(e); t.async = !0; t.src = v; s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s);
  }(window, document, "script", "https://connect.facebook.net/en_US/fbevents.js");
  fbq("init", PIXEL_ID);
  fbq("track", "PageView");
  const page = document.currentScript && document.currentScript.dataset.page;
  if (page) fbq("track", "ViewContent", { content_name: page });
})();

/* LinkedIn Insight Tag (ad account 557804967). Page views + retargeting; lead.js fires the
   "GASP | Lead | Site form" conversion (id 30134252) after a successful submit. */
(() => {
  const PARTNER_ID = "10261612";
  if (!PARTNER_ID || window.lintrk) return;
  window._linkedin_partner_id = PARTNER_ID;
  window._linkedin_data_partner_ids = window._linkedin_data_partner_ids || [];
  window._linkedin_data_partner_ids.push(PARTNER_ID);
  window.lintrk = function (a, b) { window.lintrk.q.push([a, b]); };
  window.lintrk.q = [];
  const s = document.getElementsByTagName("script")[0];
  const b = document.createElement("script");
  b.type = "text/javascript"; b.async = true;
  b.src = "https://snap.licdn.com/li.lms-analytics/insight.min.js";
  s.parentNode.insertBefore(b, s);
})();

/* X Pixel (ads account 18ce55y43fm, pixel ri1ae). Page views feed the auto-created "Site visits" and "Landing page views"
   events; lead.js fires Lead / QualifiedLead after a successful submit. The server half is the X Conversion API, sent by the
   lead fleet (gasp-agency-primary fleet-api/src/xads.js) with the same conversion_id, so X counts each fill once.
   An ad click lands with ?twclid=: it is kept 30 days in a first-party cookie so a fill on a later page still credits the ad. */
(() => {
  const PIXEL_ID = "ri1ae";
  const click = new URLSearchParams(location.search).get("twclid");
  if (click && /^[A-Za-z0-9_-]{6,200}$/.test(click)) document.cookie = `gasp_twclid=${click}; Max-Age=2592000; Path=/; SameSite=Lax; Secure`;
  if (!PIXEL_ID || window.twq) return;
  !function (e, t, n, s, u, a) {
    e.twq || (s = e.twq = function () { s.exe ? s.exe.apply(s, arguments) : s.queue.push(arguments); },
      s.version = "1.1", s.queue = [], u = t.createElement(n), u.async = !0, u.src = "https://static.ads-twitter.com/uwt.js",
      a = t.getElementsByTagName(n)[0], a.parentNode.insertBefore(u, a));
  }(window, document, "script");
  twq("config", PIXEL_ID);
})();
