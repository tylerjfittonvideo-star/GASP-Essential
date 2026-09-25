# Deep research digest — fastest, cheapest way to turn the web into data (September 2026)

Compiled 2026-09-25 from provider pages, docs, and third-party benchmarks (links at the end). Numbers are
list prices and published benchmark results as of that date; treat anything older than a quarter as drift.

## 1. Findings that shaped the skill

1. **Fetching is nearly free; extraction with an LLM is the expensive part.** A Decodo standard request is $0.0005; a Haiku extraction of the same page is ~$0.0075 (15×). So the ladder spends its effort avoiding LLM calls: JSON endpoints → hydration JSON → JSON-LD → CSS schema generated once → markdown-to-LLM last.
2. **Most pages need no browser.** The 2026 anti-detect benchmark (31 targets, 651 verdicts) shows curl_cffi's Chrome TLS fingerprint alone passing 26/31; the "skip the browser" analysis puts 60–70 % of scraping tasks in the no-browser bucket. Rendering is the exception, not the default.
3. **Escalate by failure type, not by habit.** JS shell → render; Cloudflare challenge → stealth browser or premium API; DataDome/Akamai/PerimeterX/Kasada → premium API only (local tools lose); 429 → slow down before paying. Every wrong rung costs seconds and sometimes dollars.
4. **Free renderers exist.** r.jina.ai renders JS server-side at 20 rpm with no key (500 rpm with a free key) and returns markdown/JSON; Cloudflare's Markdown for Agents (Feb 2026) returns edge-converted markdown for `Accept: text/markdown` with a token-count header. Both cost $0 and cut tokens 80–99 %.
5. **Decodo is the right reference paid rung**: per-request success-based pricing ($0.50→0.14 per 1K standard, $1.50→1.20 premium+JS), `markdown: true` output, JS rendering, geo, sessions, sync + async + batch endpoints, a CLI, an MCP server, and agent skills — plus the cheapest residential pool at volume ($2/GB at 1 TB). Zyte is cheaper at the very bottom ($0.06–0.13 per 1K HTTP) but tiered per site; Bright Data has the best free tier (5K/mo) at $1.50 per 1K.
6. **The web is closing to declared AI crawlers, not to ordinary fetches.** Cloudflare's Sept 15 2026 defaults block AI-training and agent bots on ad-supported pages and route "pay-per-use"; 2.5M+ sites disallow AI training. Public, logged-out scraping remains legally defensible in the US (hiQ; Meta v. Bright Data), logged-in scraping against accepted terms is not.
7. **Run it without a chat session.** GitHub Actions cron (UTC, ≥5 min, 10–30 min late, disabled after 60 idle days; 2,000 free min/mo private, unlimited public), launchd on the Mac, or Vercel/other cron — the ladder's `job` command is designed for that.

## 2. Decodo (formerly Smartproxy)

| Item | Value |
|---|---|
| Web Scraping API endpoint | `POST https://scraper-api.decodo.com/v2/scrape`, Basic auth; async `POST /v3/task`, `GET /v3/task/{id}`, `GET /v3/task/{id}/results`; batch `POST /v3/task/batch` (`url:[…]` or `query:[…]`, one target, 1 req/s, up to ~3,000 items, 24 h retention, `callback_url`) |
| Key params | `url`, `target: universal`, `proxy_pool: standard/premium` (premium default), `headless: html/png`, `markdown: true`, `geo`, `locale`, `device_type`, `session_id`, `http_method`+`payload`, `headers/cookies` (+`force_*`), `parse`, `xhr`, `successful_status_codes` |
| Plans | Free $0 (2K std req, 10 rps) · Starter $19 (38K, 10 rps) · Professional $49 (163K, 25 rps) · Business $99 (707K, 50 rps) · Enterprise |
| Per-1K rates | standard $0.50 → $0.14 (Business); std+JS $0.75; premium $1.00; premium+JS $1.50 → $1.20 (Business) |
| Site Unblocker | $1.25 → $0.95 per 1K, or $10 → $6.75/GB; claims CAPTCHA handling |
| Residential proxies | 115M+ IPs; $4/GB PAYG; $3.75/GB (3 GB) → $2.75 (100 GB) → $2.50 (250 GB) → $2 (1 TB); `gate.decodo.com:7000`, `user-USER-country-us-session-x` |
| Datacenter / ISP | from $0.60/GB · from $3.33/IP/mo |
| Agent surfaces | CLI `@decodo/cli` (`decodo scrape/search/screenshot`, `DECODO_AUTH_TOKEN`, ndjson output, exit codes); MCP `@decodo/mcp-server` (`SCRAPER_API_TOKEN`, `TOOLSETS=web,search,ecommerce,social_media,ai`; `scrape_as_markdown`, `google_search_parsed`, …); `Decodo/agent-skills` plugin (`decodo-web-scraping`, `decodo-price-monitoring`); `decodo-sdk` on PyPI |
| Output formats | HTML, JSON, CSV, XHR, PNG, LLM-ready Markdown |

## 3. Scraping API market (September 2026)

| Provider | Standard $/1K | JS/premium $/1K | Free | Billing |
|---|---|---|---|---|
| Zyte API | 0.06–1.27 (site-tiered) | 0.48–16.08 browser | — | per success, $100+ commitments |
| Scrapingdog | 0.09 | 0.90–1.80 | — | per request |
| Scrape.do | 0.12 ($29/250K) | credits | 1K/mo | per success |
| Decodo | 0.50 → 0.14 | 0.75 / 1.00 / 1.50 → 1.20 | 2K | per request |
| Spider.cloud | ≈0.10 | ≈0.15 | — | $1/GB + $0.0001/CPU-min |
| ScrapingAnt / ScrapingBee / Scrapfly | 0.10 | 2.45–12 | 1K trial | credits (JS + premium multipliers up to 125×) |
| ScraperAPI | 0.15–0.29 | 1.49–3.73 | 5K credits | credits |
| ZenRows | 0.20 | 4.95 | — | credits |
| Browserbase | 0.50 | 4.00 | — | per request |
| Firecrawl | 0.99 | JSON ×5, stealth ×5 | 1K credits | credits; $16/5K, $83/100K, $333/500K |
| Bright Data Web Unlocker | 1.50 → 1.00 | included | 5K/mo | per success |
| Apify | 1.50 | — | $5/mo | compute units $0.20 |
| Oxylabs Web Unblocker | — | — | trial | $9.40 → $5.00/GB |
| Jina Reader | 0 | 0 | 10M tokens | $0.02/1M tokens with key; 20 rpm keyless / 500 rpm free key / 5,000 premium |

Cheapest entry tiers in mid-2026: Zyte pay-as-you-go HTTP ($0.13/1K), Firecrawl Hobby ($16/5K pages), Apify Starter ($19 prepaid). Search APIs for URL discovery: Serper ≈$0.30–1.00/1K, Brave $5/1K ($5 credit), Tavily $5–8/1K, Exa $7/1K + $1/1K contents, Decodo `google_search` template at the same per-request rate as scraping.

## 4. Proxy market

Residential: DataImpulse $1/GB (fastest average response in Proxyway's 2026 13-provider test), Webshare ~$3.50/GB with a free tier, IPRoyal $4.90/GB, Decodo $2–4/GB (cheapest at ≥1 TB). Datacenter: Decodo $0.60/GB; Webshare rotating DC from $2.99/mo. The metric that matters is cost per *successful* response: price and block rate are independent variables.

## 5. HTTP client benchmarks (Python)

- **curl_cffi 0.16** — TLS/JA3/JA4 + HTTP/2 impersonation with 37+ profiles, HTTP/3, async; verified here: JA4 `t13d131100_f57a46bbacb6_ab7e3b40a677`, UA Chrome/150. 30 pages in 0.99 s at concurrency 10 (30 pages/s).
- httpx with h2: 30 pages in 0.67 s (faster raw throughput, no impersonation; last release Dec 2024 — stalled).
- rnet (Rust/wreq) and primp (Rust) benchmark faster than curl_cffi but are small projects (primp quiet since May 2026); niquests offers HTTP/3 and utls impersonation; Stealth-Requests wraps curl_cffi (pinned to Chrome 136).
- Verdict: curl_cffi is the default (fingerprint + speed + maintenance); httpx is the dependency-light fallback.

## 6. Headless / anti-detect benchmarks (2026)

31 targets × 3 sweeps from one residential IP (Cloudflare Turnstile, DataDome, F5, fingerprint panels, Amazon, LinkedIn, Reddit, TikTok, Booking): nodriver 28 ok/0 blocked; CloakBrowser 26/2; curl_cffi 26/2 (HTTP only!); Patchright 25/3; Camoufox 25/3; vanilla Playwright 24/5; rebrowser-playwright 24/5 (unmaintained). Only nodriver passed the canadianinsider Cloudflare gate — automation-protocol (CDP) fingerprinting beats static patches. Camoufox (Firefox fork, C++-level patches) is strongest on hard fingerprinting and Google search but slowest. Lightpanda (Zig, CDP-compatible) reports 9× faster / 16× less memory than Chrome on JS-dependent demo pages but fails advanced anti-bot; good for volume rendering of friendly sites. Scrapling v0.4 `StealthyFetcher(solve_cloudflare=True)` solves Turnstile/interstitials locally, adds proxy rotation, XHR capture, retries.

## 7. Content extraction & token cost

- Markdown vs raw HTML: 9,541 → 1,678 tokens (−82 %) on Cloudflare docs; 16,180 → 3,150 on a blog. Measured here: Wikipedia article 235K chars HTML → trafilatura 41K chars (≈58.9K → 10.4K tokens, −82 %) in 0.07 s; markdownify 62K chars in 0.10 s.
- Extractor quality (2026): Web2MD 94 %, trafilatura 87 % (F-score 0.909, best recall on news/blogs), Readability 84 %, Jina Reader 81 %; Defuddle beats Readability on docs/math/footnotes. trafilatura is weaker on product/forum pages — fall back to `--md-mode full`.
- Crawl4AI v0.9: `JsonCssExtractionStrategy.generate_schema(url/html, query, llm_config)` generates a selector schema once with an LLM, reused with no LLM; `AsyncUrlSeeder` discovers URLs from sitemaps (100–1,000 URLs/s) and Common Crawl (50–500 URLs/s) with BM25 scoring; adaptive crawling stops when enough information is gathered.
- Claude API prices (2026-06 table): Haiku 4.5 $1/$5 per MTok, Sonnet 5 $2/$10, Opus 5 $5/$25; Batches −50 %; cache reads ≈10 %.

## 8. Zero-cost sources

- **Sitemaps + lastmod** (robots.txt `Sitemap:`), RSS/Atom; WordPress `/wp-json/wp/v2/*`; Shopify `/products.json`; JSON-LD; `__NEXT_DATA__`/`__NUXT__`/`__APOLLO_STATE__`/`__remixContext`; XHR endpoints behind pagination (page size often 100–500 vs UI 20).
- **Cloudflare Markdown for Agents**: `Accept: text/markdown` → `content-type: text/markdown`, `x-markdown-tokens`, `content-signal` (verified working on developers.cloudflare.com from this sandbox).
- **Jina Reader**: `https://r.jina.ai/<url>` with `Accept: application/json`, `X-Respond-With: markdown|html|text|screenshot|readerlm-v2`, `X-Wait-For-Selector`, `X-Target-Selector`, `X-Remove-Selector`, `X-Timeout`, `X-Proxy-Url`, `X-No-Cache`, `X-Engine: browser|direct|cf-browser-rendering`; search `https://s.jina.ai/?q=` (key required). Note: its Cloudflare front challenges an impersonated Chrome without JS; a plain API user-agent passes (found in testing).
- **Common Crawl**: `https://index.commoncrawl.org/collinfo.json` → `CC-MAIN-YYYY-WW`; CDX query `…-index?url=host/*&output=json&filter=status:200`; byte-range fetch from `data.commoncrawl.org`; no key, but often slow/rate-limited (502 from this sandbox during testing). **Wayback**: `archive.org/wayback/available?url=` and CDX — aggressive 429s from shared cloud IPs; use sparingly.

## 9. Anti-bot landscape and policy

Cloudflare fronts >20 % of web traffic; AI-driven crawl traffic was 52 % of requests in June 2026; new defaults (Sept 15 2026) block AI-training and agent bots on ad-supported pages for new zones and all free-plan zones, with Pay-Per-Use replacing Pay-Per-Crawl (Ceramic.ai, You.com first partners). Vendor tells: Cloudflare `cf-mitigated: challenge`, `__cf_bm`, `cf_clearance`; DataDome `x-datadome`, `captcha-delivery.com`; Akamai `_abck`, `ak_bmsc`, `akamai-grn`; PerimeterX/HUMAN `x-px-block-score`, `_pxhd`; Kasada bare 429 + `x-kpsdk-*`; Imperva `incap_ses`, `visid_incap`.

## 10. Legal frame (US-centric, not legal advice)

hiQ v. LinkedIn (9th Cir. 2022): scraping public pages is likely not CFAA "unauthorized access" when no gate is bypassed (hiQ still lost on contract for using accounts). Meta v. Bright Data (N.D. Cal., Jan 23 2024): terms govern logged-in use; scraping public pages while logged out, after terminating accounts, did not breach them. Van Buren narrowed the CFAA. Practical rule: public + logged-out + rate-limited + no personal-data hoarding = defensible; logged-in or paywalled = not.

## 11. Automation platforms

GitHub Actions: cron in UTC, minimum 5 min (15 min recommended on free public), 10–30 min delays at busy hours, schedules disabled after 60 days without repo activity, 2,000 free minutes/month on private repos, unlimited on public; cache Playwright only with a version-keyed cache (Playwright's own guidance says browser caching often is not worth it — the ladder uses jina for JS in CI instead). macOS launchd for the laptop; Vercel cron for hosted jobs.

## 12. Measured in this sandbox (2026-09-25)

| Test | Result |
|---|---|
| curl_cffi vs httpx, 30 pages, concurrency 10 | 0.99 s vs 0.67 s (both 30/30) |
| batch 40 pages, per-host 4, 250 ms spacing | 9.9 s (polite defaults); rerun from cache 0.2 s (184 pages/s) |
| batch 20 pages docs site, per-host 8, no spacing | see SKILL.md quick-start numbers |
| JS page (quotes.toscrape.com/js) | direct → js_required in 0.1 s; browser (Patchright + preinstalled Chromium, assets blocked) ok in 0.8–1.5 s; jina ok in 0.4 s |
| Cloudflare markdown negotiation | developers.cloudflare.com → `text/markdown`, 10.4K chars |
| WordPress / Shopify detection | techcrunch.com → wp-json usable, 4 JSON-LD objects, feed; allbirds.com → products.json usable |
| Cloudflare-blocked site from a datacenter IP | glassdoor.com → 403 `blocked:cloudflare`, correctly routed to stealth/API rungs |
| trafilatura on a 235K-char article | 41K chars in 0.07 s (≈−82 % tokens) |

## Sources

Decodo: https://decodo.com/scraping/web · https://help.decodo.com/docs/web-scraping-api-introduction · https://help.decodo.com/docs/web-scraping-api-parameters · https://help.decodo.com/docs/web-scraping-api-asynchronous-requests · https://github.com/Decodo/Web-Scraping-API · https://github.com/Decodo/cli · https://github.com/Decodo/mcp-server · https://github.com/Decodo/agent-skills · https://pypi.org/project/decodo-sdk/ · https://decodo.com/proxies/residential-proxies/pricing · https://help.decodo.com/docs/residential-proxy-user-pass-requests · https://aimultiple.com/decodo-review · https://proxidize.com/blog/decodo-pricing/
Market pricing: https://usestring.ai/comparisons/web-scraping-api-pricing (verified 2026-09-23) · https://docs.zyte.com/zyte-api/pricing.html · https://scrapeprices.com/provider/brightdata-web-unlocker · https://proxyfacts.com/blog/web-unblocker-comparison · https://scrape.do/pricing/ · https://www.firecrawl.dev/pricing · https://spider.cloud/pricing/ · https://jina.ai/reader/ · https://agentscamp.com/guides/advanced/jina-reader-api · https://use-apify.com/blog/web-scraping-pricing-guide-all-platforms · https://www.buildmvpfast.com/api-costs/ai-search · https://webscraping.ai/blog/cheapest-residential-proxies · https://dataimpulse.com/blog/cheapest-proxies/
Clients & browsers: https://scrapfly.io/blog/posts/best-python-http-clients · https://github.com/lexiforest/curl_cffi · https://ianlpaterson.com/blog/anti-detect-browser-benchmark-patchright-nodriver-curl-cffi/ · https://scrapfly.io/blog/posts/best-stealth-browsers · https://github.com/D4Vinci/Scrapling/releases/tag/v0.4 · https://scrapling.readthedocs.io/en/latest/fetching/stealthy.html · https://wavect.io/blog/lightpanda-headless-browser-ai-agents/
Extraction: https://dev.to/stevengonsalvez/browser-tools-for-ai-agents-part-4-skip-the-browser-save-80-on-tokens-304c · https://web2md.org/blog/best-web-to-markdown-tools-2026 · https://bulkmd.app/blog/readability-vs-trafilatura-extractors · https://docs.crawl4ai.com/extraction/no-llm-strategies/ · https://docs.crawl4ai.com/core/url-seeding/ · https://okhlopkov.com/web-scraping-ai-agents-2026/ · https://gist.github.com/dumkydewilde/97ab8337e30ca09c52b25343adf2aae1 · https://evomi.com/blog/parsing-next_data-and-json-ld-the-clean-way-to-extract-structured-data
Policy & legal: https://developers.cloudflare.com/fundamentals/reference/markdown-for-agents/ · https://techcrunch.com/2026/07/01/cloudflares-new-policy-pushes-ai-companies-to-pay-for-publishers-content/ · https://fastcrw.com/blog/cloudflare-ai-crawler-block-september-2026 · https://www.fbm.com/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/ · https://apiserpent.com/blog/is-scraping-linkedin-legal-2026 · https://scrapfly.io/blog/posts/how-to-bypass-anti-bot-protection
Automation: https://cronbuilder.dev/blog/github-actions-cron-schedule.html · https://devactivity.com/insights/github-actions-cron-schedules-a-hidden-free-tier-hurdle-impacting-developer-productivity/ · https://justin.poehnelt.com/posts/caching-playwright-in-github-actions/ · https://commoncrawl.org/get-started · https://index.commoncrawl.org
