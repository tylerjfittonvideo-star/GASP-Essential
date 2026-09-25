# Cost model — what a page costs at each rung (verified 2026-09-23/25)

All prices in USD. "per 1K" = per 1,000 requests/pages. Entry-plan list prices; volume discounts noted.
Sources: provider pricing pages and the comparisons in `research-2026-09.md`.

## The ladder, priced

| Rung | Solves | Cost | Speed (measured here) | Needs |
|---|---|---|---|---|
| 0 cache / 304 | repeat runs | $0 | 180+ pages/s | nothing |
| 1 direct (curl_cffi, Chrome TLS/JA4) | static HTML, JSON APIs, JSON-LD, `__NEXT_DATA__` | $0 | 30 pages/s at concurrency 10; 4 pages/s with polite per-host limits | `pip install curl_cffi` |
| 1b markdown negotiation (`Accept: text/markdown`) | Cloudflare-hosted sites with Markdown for Agents on | $0 | same as direct, ~80–99 % fewer tokens | nothing |
| 2 browser (Patchright/Playwright, assets blocked) | JS shells, infinite scroll, client-rendered lists | $0 (CPU) | 1–5 s/page, 4 in parallel | Chrome/Chromium |
| 2b browser:stealth (Scrapling + Camoufox) | Cloudflare Turnstile/interstitial | $0 (CPU) | 5–20 s/page | `setup.sh full` + Camoufox |
| 3 jina r.jina.ai | JS pages when no local browser (CI) | $0 (20 rpm; free key 500 rpm) | 2–8 s/page | optional `JINA_API_KEY` |
| 4 proxy (Decodo residential) | IP blocks, geo content, 429s | $2–4/GB → ≈ $1–2 per 1K at 500 KB/page | direct speed | `DECODO_PROXY_USER/PASS` |
| 4b proxy (datacenter) | mild IP limits | $0.60/GB → ≈ $0.30 per 1K | direct speed | proxy creds |
| 5 api Decodo standard | anything direct fails on, no JS | $0.50 per 1K ($0.14 at $99/mo) | 1–3 s/page, 10–50 rps by plan | `DECODO_AUTH_TOKEN` + `--budget` |
| 5 api Decodo standard + JS | JS pages at scale | $0.75 per 1K | 3–8 s/page | same |
| 5 api Decodo premium (+JS) | DataDome / Akamai / PerimeterX / Kasada | $1.00 / $1.50 per 1K ($1.20 at $99) | 3–10 s/page | same |
| 6 LLM extraction (Haiku 4.5) | unstructured prose → typed fields | ≈ $0.008/page (6K in, 300 out); ×0.5 Batches | 1–3 s/page | `ANTHROPIC_API_KEY` |

Rule of thumb for a 10,000-page job: direct-only ≈ $0; 20 % needing JS via API ≈ $1.50; everything through premium+JS ≈ $15; adding Haiku extraction ≈ $80 (or $40 batched). Extraction, not fetching, is the expensive rung — which is why the ladder pulls JSON-LD/hydration data and CSS schemas first.

## Provider sheet (entry tier unless noted)

| Provider | Standard $/1K | JS / premium $/1K | Free tier | Model |
|---|---|---|---|---|
| Decodo Web Scraping API | 0.50 (0.14 @ $99) | 0.75 std+JS · 1.00 prem · 1.50 prem+JS (1.20 @ $99) | 2K req, no card | per request, success-based |
| Decodo Site Unblocker | 1.25 → 0.95 | — | trial | per 1K or $10→6.75/GB |
| Zyte API | 0.06–1.27 tiered | 0.48–16.08 browser | — | per successful request, site-tiered |
| Bright Data Web Unlocker | 1.50 → 1.00 | included | 5K/mo | per success |
| Oxylabs Web Unblocker | — | — | trial | $9.40→5.00/GB only |
| ScraperAPI | 0.29 ($29/100K credits) | ×5–10 credits | 5K credits | credits |
| Scrape.do | 0.12 ($29/250K) | credits | 1K/mo | per success |
| ScrapingBee | 0.25 ($19/75K) | ×5–75 credits | 1K trial | credits |
| Scrapfly | 0.10 @ $100 | 2.50+ | — | credits |
| Firecrawl | 0.99 | JSON mode ×5, stealth ×5 | 1K credits | credits, 1/page |
| Spider.cloud | ≈0.10 | ≈0.15 chrome | — | $1/GB + $0.0001/CPU-min |
| Jina Reader | 0 (20 rpm) | 0 | 10M tokens | ~$0.02/1M tokens |
| Apify | 1.50 | — | $5/mo usage | compute units $0.20 |
| Residential proxies | Decodo $2–4/GB · DataImpulse $1/GB · IPRoyal $4.90/GB · Webshare ~$3.50/GB | | | per GB |

Cost that matters is **per successful page**: a $1/GB pool that fails 40 % costs more than a $3/GB pool that fails 5 %.

## LLM extraction math (Claude API list prices, 2026-06 table)

| Model | $/1M in | $/1M out | ≈ per page (6K in / 300 out) | with Batches (×0.5) | with cached instructions |
|---|---|---|---|---|---|
| claude-haiku-4-5 | 1.00 | 5.00 | $0.0075 | $0.0038 | −10 % on the instruction block |
| claude-sonnet-5 | 2.00 | 10.00 | $0.015 | $0.0075 | same |
| claude-opus-5 | 5.00 | 25.00 | $0.038 | $0.019 | same |

Levers in order: (1) do not send HTML — trafilatura markdown is ~82 % fewer tokens (58.9K → 10.4K on a Wikipedia article, measured); (2) generate a CSS schema once (Sonnet, ≈$0.02) then extract for free; (3) `--batch` for anything that can wait an hour; (4) `--max-chars` cap; (5) Haiku first, Sonnet only when Haiku misses fields.

## Break-even guidance

- Proxy vs API: at 500 KB/page a residential proxy costs about the same as Decodo standard ($1–2 vs $0.50 per 1K) and does not solve JS or WAFs — use proxies only for geo/IP-rate problems, otherwise go straight to the API rung.
- Local browser vs API JS: a Mac renders ~1 page/s per 4 workers for free; the API does 10–50 rps for $0.75/1K. Below ~5K JS pages/day the laptop wins; above that, or in CI, pay the API.
- Decodo plan choice: free (2K) → $19 Starter (38K, 10 rps) → $49 (163K, 25 rps) → $99 Business (707K, 50 rps, $0.14/1K standard). Buy the plan whose per-1K rate × expected volume is lowest; unused requests do not roll over.
