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
