# Decodo (formerly Smartproxy) cheat sheet — the reference paid rung

Verified 2026-09 against help.decodo.com, github.com/Decodo/* and decodo.com pricing pages.

## Web Scraping API (what the ladder's `api` rung calls)

- Endpoint: `POST https://scraper-api.decodo.com/v2/scrape` · header `Authorization: Basic <token>` (token from the dashboard; the ladder also accepts `DECODO_USER` + `DECODO_PASS` and base64-encodes them).
- Body keys used by the ladder: `url`, `target: "universal"`, `proxy_pool: "standard" | "premium"` (default on their side is premium — the ladder sends standard first and escalates), `headless: "html"` (JS render; `"png"` for a screenshot), `markdown: true` (LLM-ready markdown instead of HTML), `geo` (full country name, e.g. `"United States"`), `locale` (`en-US`), `device_type` (`desktop`, `mobile`, `desktop_chrome`, …), `session_id` (sticky), `http_method` + `payload` (base64 POST body), `headers`/`cookies` with `force_headers`/`force_cookies`, `successful_status_codes` (treat e.g. 404 as success), `xhr: true` (capture XHR calls), `parse: true` (structured JSON for template targets).
- Response: `{"results": [{"content": "...", "status_code": 200, "url": "...", "task_id": "...", "created_at": ..., "updated_at": ...}]}`.
- Async: `POST …/v3/task` → `{id}`; `GET …/v3/task/{id}` → `status: pending|done|faulted`; `GET …/v3/task/{id}/results`. Batch: `POST …/v3/task/batch` with `{"url": [...], "target": "universal", ...}` (or `"query": [...]`), one target per batch, up to ~3,000 items by plan, 1 batch request/second, optional `callback_url` (they POST `id`, `status`, `passthrough`). Results retrievable for 24 h. The ladder uses parallel sync calls (`--api-rps`) because that path is testable end-to-end without a key; wire the batch endpoint for >5K-URL jobs.
- Rate limits: free 10 rps · Starter $19 10 rps · Professional $49 25 rps · Business $99 50 rps.
- Templates worth knowing (same auth, `target:` name, `parse: true`): `google_search`, `google_shopping`, `bing_search`, `amazon_search`, `amazon_product`, `walmart`, `target`, `reddit_post`, `reddit_subreddit`, `tiktok`, `youtube_*`, `instagram_*`. SERP: `{"target": "google_search", "query": "...", "geo": "United States", "parse": true}` ≈ same per-request price.

## Pricing (per 1K requests, entry list; $99/mo Business plan in parentheses)

standard 0.50 (0.14) · standard+JS 0.75 · premium 1.00 · premium+JS 1.50 (1.20) · free plan 2,000 requests, no card · 14-day money-back on paid plans. Set `DECODO_USD_PER_1K_*` env vars to your plan's real rates so the ledger's spend numbers are exact.

## Proxies (the ladder's `proxy` rung)

- Residential gateway: `gate.decodo.com:7000`, username `user-<USER>-country-us[-state-ny][-city-newyork][-session-<id>][-sessionduration-<min>]`, password `<PASS>`. Omit `session` → rotates every request; sticky sessions last 10 min by default (max 1,440). Residential $2–4/GB (PAYG $4; $3.75/GB at 3 GB; $2/GB at 1 TB). Datacenter from $0.60/GB, ISP from $3.33/IP. Set `DECODO_PROXY_USER/PASS` (+ optional `DECODO_PROXY_COUNTRY`, `DECODO_PROXY_HOST`) or any `LADDER_PROXY_URL`.
- Site Unblocker (their unblocker-as-proxy): $1.25 → 0.95 per 1K or $10 → 6.75/GB; use it as `LADDER_PROXY_URL` if you buy it.

## Agent-native surfaces (use instead of the ladder when they fit)

- CLI: `npm i -g @decodo/cli` or `curl -fsSL https://decodo.github.io/cli/install.sh | sh`; `DECODO_AUTH_TOKEN` env; `decodo scrape URL`, `decodo search "q" --engine google --geo us --limit 10`, `decodo screenshot URL -o f.png`, `decodo targets`; `--format ndjson --full` for agents; exit codes 0 ok / 3 auth / 5 rate limit.
- MCP server: `npx -y @decodo/mcp-server` with env `SCRAPER_API_TOKEN` and `TOOLSETS=web,search` (also `ecommerce,social_media,ai`); tools `scrape_as_markdown`, `screenshot`, `google_search_parsed`, `amazon_search_parsed`, `reddit_post`, …
- Agent skills: `/plugin marketplace add Decodo/agent-skills` → `decodo-web-scraping`, `decodo-price-monitoring`. They route every request to Decodo; this skill routes to Decodo only after the free rungs fail, which is the cost difference.
- Python SDK: `pip install decodo-sdk` — `DecodoClient(DecodoConfig(web_scraping_api=WebScrapingApiConfig(token=...)))`, `client.web_scraping_api.scrape(GoogleSearchParams(query=..., geo=..., parse=True))`, `.scrape_async()`, `.scrape_batch()`.

## Ladder flags that map to Decodo

`--budget USD` (required to spend) · `--api-pool premium` · `--js` (headless html) · `--geo "United States"` · `--locale en-US` · `--session id` · `--api-rps N` · `--api-html` (skip markdown mode) · `--min-tier api` (go straight to the API for known-hard hosts).
