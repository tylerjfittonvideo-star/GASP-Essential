/* GASP! Essential · POST /api/lead  (Vercel Node function, zero dependencies)
   1. Validates the form (honeypot drops bots silently).
   2. Sends a Lead event to the Meta Conversions API (plus QualifiedLead for 10-50 seats),
      hashed per Meta spec, same event_id as the browser pixel so Meta de-duplicates.
   (X: the lead fleet sends the X Conversion API events from the Worker, where the X Ads credentials live; this only passes twclid on.)
   3. Emails the lead to the GASP inbox through Microsoft Graph (app-only, Mail.Send).
   Every lead is written to the function log first-class, so a missing or failing alert never loses it.
   If no alert went out AND no booking page is set, the visitor gets an error and the email fallback.

   Vercel env vars
     META_PIXEL_ID          dataset ID from Events Manager
     META_CAPI_TOKEN        Conversions API access token (Events Manager > Settings)
     META_API_VERSION       optional, default v24.0
     META_TEST_EVENT_CODE   optional, set only while testing in Events Manager > Test events
     MS_TENANT_ID           Entra tenant ID
     MS_CLIENT_ID           app registration (application) ID
     MS_CLIENT_SECRET       client secret value
     LEAD_MAILBOX           mailbox the alert is sent from, e.g. tyler.fitton@gaspessential.com
     LEAD_TO                optional, where the alert lands (defaults to LEAD_MAILBOX)
     BOOKING_URL            Microsoft Bookings page the visitor is sent to after submitting
     FLEET_INBOUND_TOKEN    the lead fleet's INBOUND_TOKEN (2026-10-26): every fill is handed to the fleet, which stores it in D1,
                            opens the deal on the dashboard and has Speed-to-Lead send the first reply
     FLEET_API_URL          optional, default https://gasp-fleet-api.strategicom-tools.workers.dev
*/
const crypto = require("crypto");

const env = k => (process.env[k] || "").trim();
const clean = (v, n = 120) => String(v == null ? "" : v).replace(/[\r\n\t<>]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
const sha = v => (v ? crypto.createHash("sha256").update(String(v).trim().toLowerCase()).digest("hex") : undefined);
const EMAIL = /^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
const T = () => AbortSignal.timeout(8000);
const ALLOWED = /^https:\/\/(www\.)?gaspessential\.com$|^https:\/\/[a-z0-9-]+\.vercel\.app$/i;
const nameNorm = v => String(v || "").toLowerCase().replace(/[^a-z\u00c0-\u024f]/g, "");
const QUALIFIED = ["10-25", "26-50"];
// Public, non-secret defaults so the funnel works before any env vars are set. Env vars still win.
const DEFAULT_BOOKING_URL = "https://bookings.cloud.microsoft/bookwithme/user/2238aa5817e048cf8933378da069820f@gaspessential.com/meetingtype/wUsz-P-oIUipv3nfj2f1nw2?anonymous";
const DEFAULT_PIXEL_ID = "4545759298978855";
const DEFAULT_FLEET_URL = "https://gasp-fleet-api.strategicom-tools.workers.dev";

function phoneE164Digits(p) {
  let d = String(p || "").split(/x|ext|#/i)[0].replace(/\D/g, "");
  if (d.length === 10) d = "1" + d; // US default
  return d.length >= 11 ? d : "";
}

async function sendCapi(lead, ctx) {
  const pixel = env("META_PIXEL_ID") || DEFAULT_PIXEL_ID, token = env("META_CAPI_TOKEN");
  if (!pixel || !token) return "skipped";
  const [first, ...rest] = lead.name.split(" ");
  const user_data = {
    em: [sha(lead.email)],
    fn: nameNorm(first) ? [sha(nameNorm(first))] : undefined,
    ln: rest.length && nameNorm(rest[rest.length - 1]) ? [sha(nameNorm(rest[rest.length - 1]))] : undefined,
    ph: phoneE164Digits(lead.phone) ? [sha(phoneE164Digits(lead.phone))] : undefined,
    country: [sha("us")],
    client_ip_address: ctx.ip || undefined,
    client_user_agent: ctx.ua || undefined,
    fbp: ctx.fbp || undefined,
    fbc: ctx.fbc || undefined
  };
  const base = {
    event_time: Math.floor(Date.now() / 1000),
    action_source: "website",
    event_source_url: ctx.url || undefined,
    user_data,
    custom_data: { content_name: lead.page || "site", team_size: lead.size || undefined, pain: lead.pain || undefined }
  };
  const data = [{ ...base, event_name: "Lead", event_id: ctx.eventId }];
  if (QUALIFIED.includes(lead.size)) data.push({ ...base, event_name: "QualifiedLead", event_id: ctx.eventId + "-q" });
  const body = { data, access_token: token };
  if (env("META_TEST_EVENT_CODE")) body.test_event_code = env("META_TEST_EVENT_CODE");
  const v = env("META_API_VERSION") || "v24.0";
  const r = await fetch(`https://graph.facebook.com/${v}/${encodeURIComponent(pixel)}/events`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: T()
  });
  if (!r.ok) throw new Error(`capi ${r.status} ${(await r.text()).slice(0, 300)}`);
  return "sent";
}

// The fleet is the record of truth for every fill (D1 + the deal + Speed-to-Lead). Two tries; the same event_id makes a retry a no-op there.
async function sendFleet(lead, ctx) {
  const token = env("FLEET_INBOUND_TOKEN");
  if (!token) return "skipped";
  const url = (env("FLEET_API_URL") || DEFAULT_FLEET_URL).replace(/\/+$/, "") + "/v1/inbound";
  let last = "";
  for (let i = 0; i < 2; i++) {
    try {
      const r = await fetch(url, {
        method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ ...lead, event_id: ctx.eventId }), signal: AbortSignal.timeout(4000)  // 2 x 4 s stays inside the 10 s function limit
      });
      if (r.ok) return "sent";
      last = `fleet ${r.status} ${(await r.text()).slice(0, 200)}`;
      if (r.status < 500) break;  // a 4xx won't change on retry
    } catch (e) { last = `fleet ${e.name}: ${e.message}`; }
  }
  throw new Error(last);
}

async function sendMail(lead) {
  const tenant = env("MS_TENANT_ID"), id = env("MS_CLIENT_ID"), secret = env("MS_CLIENT_SECRET"), from = env("LEAD_MAILBOX");
  if (!tenant || !id || !secret || !from) return "skipped";
  const tr = await fetch(`https://login.microsoftonline.com/${encodeURIComponent(tenant)}/oauth2/v2.0/token`, {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: id, client_secret: secret, grant_type: "client_credentials", scope: "https://graph.microsoft.com/.default" }),
    signal: T()
  });
  if (!tr.ok) throw new Error(`token ${tr.status}`);
  const { access_token } = await tr.json();
  const qualified = QUALIFIED.includes(lead.size);
  const lines = [
    `${lead.name} · ${lead.company}`,
    `${lead.email}${lead.phone ? " · " + lead.phone : ""}`,
    `Team size: ${lead.size || "n/a"}${qualified ? " (in ICP)" : ""}`,
    `Eats their week: ${lead.pain || "n/a"}`,
    `Page: ${lead.page || "site"}`,
    `Source URL: ${lead.url || "n/a"}`,
    "",
    "They were sent to the booking page. Reply to this email to reach them directly."
  ];
  const r = await fetch(`https://graph.microsoft.com/v1.0/users/${encodeURIComponent(from)}/sendMail`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access_token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      message: {
        subject: `${qualified ? "New lead" : "New lead (outside ICP)"}: ${lead.company || lead.name} · ${lead.page || "site"}`,
        body: { contentType: "Text", content: lines.join("\n") },
        toRecipients: [{ emailAddress: { address: env("LEAD_TO") || from } }],
        replyTo: [{ emailAddress: { address: lead.email, name: lead.name } }]
      },
      saveToSentItems: false
    }),
    signal: T()
  });
  if (!r.ok) throw new Error(`mail ${r.status} ${(await r.text()).slice(0, 300)}`);
  return "sent";
}

module.exports = async (req, res) => {
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); return res.status(405).json({ ok: false }); }
  const origin = String(req.headers.origin || "");
  if (origin && !ALLOWED.test(origin)) return res.status(403).json({ ok: false });
  let b;
  try { b = req.body; } catch { b = null; } // Vercel's body getter throws on malformed JSON
  if (typeof b === "string") { try { b = JSON.parse(b); } catch { b = null; } }
  if (!b || typeof b !== "object") return res.status(400).json({ ok: false, error: "body" });
  const bookingRaw = env("BOOKING_URL") || DEFAULT_BOOKING_URL;
  const booking_url = /^https:\/\//i.test(bookingRaw) ? bookingRaw : null;
  // honeypot + too-fast submits (under 3 s after page load) are treated as bots: thank them, store nothing
  if (clean(b.hp_url) || (Number(b.t) > 0 && Number(b.t) < 3000)) return res.status(200).json({ ok: true, booking_url });

  const lead = {
    name: clean(b.name, 80), email: clean(b.email, 120).toLowerCase(), phone: clean(b.phone, 30),
    company: clean(b.company, 120), size: clean(b.size, 10), pain: clean(b.pain, 40), page: clean(b.page, 40), url: clean(b.url, 300),
    twclid: clean(b.twclid, 200).replace(/[^A-Za-z0-9_-]/g, "")  // X click id (2026-10-27): the fleet sends it to X's Conversion API
  };
  if (!lead.name || !EMAIL.test(lead.email)) return res.status(400).json({ ok: false, error: "name_email" });

  const ctx = {
    eventId: clean(b.event_id, 64) || crypto.randomUUID(),
    ip: clean(String(req.headers["x-forwarded-for"] || "").split(",")[0], 64),
    ua: clean(req.headers["user-agent"], 400),
    fbp: clean(b.fbp, 120), fbc: clean(b.fbc, 300), url: lead.url
  };

  const [capi, mail, fleet] = await Promise.allSettled([sendCapi(lead, ctx), sendMail(lead), sendFleet(lead, ctx)]);
  if (capi.status === "rejected") console.error("lead capi failed:", capi.reason && capi.reason.message);
  if (capi.status === "fulfilled" && capi.value === "skipped") console.warn("lead capi skipped: META_PIXEL_ID / META_CAPI_TOKEN not set");
  const mailed = mail.status === "fulfilled" && mail.value === "sent";
  const stored = fleet.status === "fulfilled" && fleet.value === "sent";
  const delivered = mailed || stored;
  // The lead is always written to the function log too, so nothing is ever lost even if both hand-offs fail.
  console[stored ? "log" : "error"](stored ? "LEAD" : "LEAD NOT IN FLEET", JSON.stringify({ ...lead, event_id: ctx.eventId,
    fleet: fleet.status === "rejected" ? String(fleet.reason && fleet.reason.message) : fleet.value,
    mail: mail.status === "rejected" ? String(mail.reason && mail.reason.message) : mail.value }));
  if (!delivered && !booking_url) return res.status(502).json({ ok: false, error: "deliver" });
  return res.status(200).json({ ok: true, booking_url });
};
