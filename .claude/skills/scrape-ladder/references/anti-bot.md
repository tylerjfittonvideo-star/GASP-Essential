# Anti-bot: recognise the wall, pick the rung, know when to stop

## Fingerprints (what `probe` and `classify()` look for)

| Vendor | Response signals | Cookies / JS | What passes (2026 benchmarks) |
|---|---|---|---|
| Cloudflare (challenge / Turnstile) | 403 or 503, `cf-mitigated: challenge`, `server: cloudflare`, `cf-ray`, body "Just a moment…", "Enable JavaScript and cookies to continue", `cf-chl`, `challenge-platform` | `__cf_bm`, `cf_clearance` | Real browser on a residential IP; Camoufox (Scrapling `solve_cloudflare=True`); nodriver was the only tool with 0 blocks in the 31-target 2026 benchmark; unblocker APIs |
| Cloudflare (bot score only) | 200 with content, or 403 without challenge | `__cf_bm` | curl_cffi Chrome fingerprint usually enough; residential proxy if 403 |
| DataDome | 403, `x-datadome`, `x-dd-b`, `captcha-delivery.com` in body | `datadome` | Unblocker API (Decodo premium+JS, Bright Data, Zyte tiered). Local headless rarely passes |
| Akamai Bot Manager | 403/429/503 with `_abck`, `ak_bmsc`, `akamai-grn` reference | `_abck`, `bm_sz` | Unblocker API; sensor-data generation is not worth building |
| PerimeterX / HUMAN | 403, `x-px-block-score`, `px-captcha`, HUMAN branding | `_pxhd`, `_px3` | Unblocker API |
| Kasada | bare 429 with empty body, `x-kpsdk-*` headers | `KP_UIDz` | Unblocker API |
| Imperva / Incapsula | `_Incapsula_Resource` in body | `incap_ses_*`, `visid_incap_*` | Unblocker API or residential + real browser |
| Plain rate limit | 429 with `retry-after` | — | slow down (`--host-interval 2 --per-host 1`), then proxy |
| Geo wall | 200 with wrong-country content, 451, 403 by region | — | `--geo` on the API or proxy country |

Hard vendors (`HARD_VENDORS` in `ladder.py`): DataDome, Akamai, PerimeterX, Kasada, Imperva. The ladder skips local rungs for them and goes straight to `api` (premium + JS) if a budget exists — trying browsers first only burns time.

## Why the cheap rungs work as often as they do

- Most blocks are TLS + header fingerprint checks. curl_cffi reproduces Chrome's JA3/JA4 and HTTP/2 SETTINGS; in the 2026 anti-detect benchmark it passed 26 of 31 targets with no browser at all.
- Blocking images/fonts/CSS in the browser rung cuts page time 2–4× and does not change the DOM.
- Headless Chromium leaks `navigator.webdriver` and CDP traces; Patchright patches the CDP handshake, Camoufox patches Firefox at C++ level. Vanilla Playwright was blocked on 5/31 targets; Patchright 3/31; Camoufox 3/31; nodriver 0/31.
- Residential exits fix IP reputation, not fingerprints. A residential IP with a bad fingerprint still fails; a datacenter IP with a perfect fingerprint fails on DataDome/Akamai.

## Rules of engagement (these are the skill's guardrails, not suggestions)

1. **Public, logged-out pages only.** The defensible line in US case law (hiQ v. LinkedIn 2022; Meta v. Bright Data, N.D. Cal. Jan 2024) is scraping public pages without an account. Never log in, never use a client's credentials, never bypass a paywall or a "members only" gate.
2. **No CAPTCHA-solving services, no human-farm solvers.** When a page demands an interactive CAPTCHA, stop and report it. Decodo premium and unblocker APIs handle passive challenges on their side; that is the ceiling.
3. **robots.txt is respected by default.** `--ignore-robots` exists for sites you own or have written permission for. Log the override.
4. **Rate limits are respected.** Defaults are 4 parallel per host, 250 ms spacing; a 429 doubles the spacing automatically. Never raise per-host above 8 without the owner's OK.
5. **Personal data: minimise.** Collect only fields the task needs; no scraping of personal data behind consent walls; GDPR/CCPA apply to what you store, not just how you fetched it.
6. **Cloudflare's 2026 defaults** block declared AI training/agent bots on ad-supported pages and route "pay-per-use" for AI use. This skill identifies as a browser fetch for the user's own data collection; do not label it as an AI training crawler, and do not scrape sites whose `content-signal` header says `ai-input=no` for LLM ingestion.
7. **When a source blocks you twice after the ladder ran out, drop it and log it** (matches the vault rule in `intent-harvest`). A `host floor` is recorded so the next run does not waste the free rungs.

## Quick diagnosis flow

```
probe URL                → vendor + js_shell + hidden data + endpoints + recommendation
verdict ok               → direct, done
js_required / js_shell   → browser (local) → jina → api std+JS
blocked:cloudflare       → browser:stealth (Camoufox) → proxy → api premium
blocked:<hard vendor>    → api premium+JS only
rate_limited             → slower direct → proxy
not_found                → stop (no escalation)
```
