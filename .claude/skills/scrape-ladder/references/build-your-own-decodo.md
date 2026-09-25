# Build your own Decodo — what a scraping API is made of, and which parts you can self-host

Decodo (and Zyte, Bright Data, ScraperAPI, Firecrawl…) sell five things bundled behind one `POST /scrape`.
Four of them are software you can run yourself for $0 per request. One is a physical asset you cannot
ethically self-build. This skill ships the four and treats the fifth as an optional, bandwidth-priced plug-in.

| What they sell | What it really is | Our self-hosted equivalent | Cost |
|---|---|---|---|
| "Anti-bot bypass" for the easy 80 % | a TLS/HTTP2 fingerprint that looks like Chrome, sane headers, cookies, retries | `direct` rung: curl_cffi impersonation, per-host politeness, 429 backoff, learned host floors | $0 |
| JavaScript rendering | a headless Chrome farm | `browser` rung: Patchright/Playwright with your Chrome, assets blocked, 4-way parallel; Lightpanda for volume rendering of friendly sites | $0 (CPU) |
| Cloudflare challenge solving | a Firefox/Chrome build with C++-level fingerprint patches on a clean IP | `browser:stealth` rung: Scrapling + Camoufox (`setup.sh full`, `LADDER_INSTALL_CAMOUFOX=1`); nodriver is the other zero-block option | $0 (CPU) |
| "LLM-ready markdown" / parsing | HTML → markdown, JSON-LD, hydration state, CSS selectors | trafilatura (F-score 0.909), `structured`, `select` schemas, Cloudflare `Accept: text/markdown` | $0 |
| The API itself | HTTP endpoint, sync + async + batch, task ids, results retention | `ladder.py serve` — same request/response shape as Decodo's `/v2/scrape`, `/v2/task`, `/v2/task/batch` | $0 |
| **Residential / mobile IPs** | millions of consumer IPs rented from app SDK users and ISPs | **not self-buildable at scale.** Options: (1) your own IP — most sites are fine with it; (2) your own machines as exits (a Mac mini at home, a phone hotspot, a friend's office box with permission) listed in `LADDER_PROXY_LIST`; (3) rent bandwidth per GB from any provider (DataImpulse $1/GB, Webshare ~$3.50/GB, Decodo $2–4/GB) — bandwidth pricing is 3–10× cheaper than per-request unblocker APIs and works with the ladder's own browser, so the provider never sees your logic | $0 – $4/GB |

## The honest limits

- **DataDome, Akamai, PerimeterX, Kasada, Imperva** fingerprint the automation protocol and score the IP. Local Chromium from a datacenter IP fails; local Camoufox/nodriver from a residential IP often passes; nothing self-hosted passes reliably from a cloud IP. If you must scrape those sites at volume, the cheapest legitimate route is still a per-request unblocker (Decodo premium $1–1.50/1K, Bright Data $1.50/1K, Zyte tiered). The ladder keeps that rung optional and off (`--max-tier proxy` on `serve`).
- **CAPTCHAs that demand interaction** are the line. No solver services, no human farms. The skill reports them and stops.
- **Volume on one IP** gets you rate-limited, not blocked forever. The defaults (4 per host, 250 ms spacing, backoff on 429) keep a single home IP usable for thousands of pages a day on ordinary sites.
- **Never build a residential pool from other people's devices** (proxy SDKs bundled into apps, "bandwidth sharing" schemes, botnets). That is how the big providers got their pools, and it is exactly the part you do not want to own.

## Running it as your own API

```bash
# on the Mac (or a $5 VPS): self-hosted rungs only, no external API ever
python ~/.claude/skills/scrape-ladder/scripts/ladder.py serve --port 8787 --max-tier proxy
# same call your other skills/scripts would have made to Decodo, now local:
curl -X POST localhost:8787/v2/scrape -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/products","headless":"html","markdown":true}'
# → {"results":[{"content":"# …","status_code":200,"url":"…","tier":"browser:patchright","cost_usd":0,"elapsed_ms":1120}]}
curl -X POST localhost:8787/v2/task/batch -d '{"url":["https://a","https://b"],"markdown":true}'   # → {"id":…}; poll /v2/task/{id}/results
```

Request keys: `url`, `headless` (`"html"` → render), `markdown` (bool), `want` (`md|json|html|text`), `need` (CSS selector that must appear), `geo`, `locale`, `session_id`, `no_cache`, `ttl`, `min_tier`, `max_tier`, `budget` (capped by the server's `--budget`, default 0). Off-loopback binding requires `--token`; clients send `Authorization: Bearer <token>`.

Point `gasp-outbound-loop` and `intent-harvest` at `http://localhost:8787/v2/scrape` instead of any hosted API; run it under launchd (copy `assets/com.gaspessential.scrape-ladder.plist`, change the arguments to `serve --port 8787 --max-tier proxy`, add `KeepAlive true`).

## Capacity you can expect from one Mac

| Rung | Throughput | Notes |
|---|---|---|
| direct | 30–100 pages/s raw; ~4 pages/s per host at polite defaults | network-bound; raise `--concurrency` for many hosts |
| browser | ~1 page/s per 4 workers (0.8–1.5 s/page) | CPU/RAM bound; ~250 MB per parallel page; blocking assets is the main lever |
| browser:stealth | 5–20 s/page | only for Cloudflare-challenged pages |
| serve | one process, threaded; each request runs its own ladder | for >10 req/s put two instances behind a port each, or move browsers to Lightpanda |

## When renting still wins (so you can decide with numbers)

- Hard-WAF sites at >1K pages/day: unblocker API ≈ $1–1.50/1K vs. hours of your time chasing blocks.
- Geo-specific content in many countries: a per-GB residential provider with `country` targeting (`DECODO_PROXY_COUNTRY` or any provider URL in `LADDER_PROXY_LIST`).
- CI with no browser and no home IP: Jina (free) covers JS; anything blocked there needs an exit IP you rent.
Everything else — docs, blogs, directories, WordPress/Shopify stores, job boards without WAFs, government and association sites — runs on the self-hosted rungs at $0.
