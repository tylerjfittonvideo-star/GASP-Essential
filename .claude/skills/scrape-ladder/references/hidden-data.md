# Hidden data — get JSON instead of parsing HTML (the biggest speed/cost win)

Order of preference. Each step is cheaper and more stable than the one below it. `probe` reports which apply.

## 1. Official / CMS JSON endpoints (free, structured, paginated)

| Platform | Tell | Endpoint | Notes |
|---|---|---|---|
| WordPress (43 % of the web) | `generator: WordPress`, `/wp-json/` answers | `/wp-json/wp/v2/posts?per_page=100&page=N&_fields=id,date,link,title,excerpt,content` | Also `pages`, `media`, `categories`; `?search=` works; `X-WP-TotalPages` header tells you when to stop |
| Shopify | `_shopify_*` cookies, `cdn.shopify.com` | `/products.json?limit=250&page=N`, `/collections/<h>/products.json`, `/products/<handle>.js` | Full variants, prices, images. Some stores disable it |
| Ghost | `ghost` generator | `/ghost/api/content/posts/?key=…` (key is in page source) | |
| Drupal | `X-Generator: Drupal` | `/jsonapi/node/article` | |
| Webflow / Wix / Squarespace | generator meta | Squarespace: append `?format=json` to any page | |
| Discourse forums | `/latest.json`, `/t/<slug>/<id>.json` | | |
| GitHub / GitLab / npm / PyPI / HN / Reddit | public APIs | Reddit: append `.json`; HN: `https://hn.algolia.com/api/v1/…` | Reddit now needs OAuth for volume — treat as "official API" tier |
| Sitemaps | `robots.txt` `Sitemap:` | `discover DOMAIN --since YYYY-MM-DD` | `lastmod` lets you fetch only what changed |
| RSS/Atom | `<link rel=alternate type=application/rss+xml>` | `discover --feeds` | new items only, tiny payloads |

## 2. XHR / fetch endpoints the page itself calls

Open DevTools → Network → filter Fetch/XHR while paging, sorting, filtering. Look for JSON responses, `graphql` POSTs, or `/api/` paths. Copy as cURL, strip cookies you do not need, replay with curl_cffi. Typical wins: page size parameter accepts 100–500 instead of 20; search endpoint returns everything the UI would take 50 clicks to show.

In the ladder: `probe --deep` shows how many characters JS adds; if the number is large and the page is a shell, the data is coming from an XHR — find it before renting a browser.

## 3. Hydration payloads embedded in the HTML (no JS needed)

| Framework | Where | Ladder field |
|---|---|---|
| Next.js Pages Router | `<script id="__NEXT_DATA__">` → `props.pageProps` | `structured.next_data` |
| Next.js App Router (13.4+) | `self.__next_f.push([1,"…"])` RSC flight lines; `ID:JSON` per line, strings escaped | `structured.state_present` flags it; parse with a small regex over `__next_f` chunks or render in browser and read `window.__next_f` |
| Nuxt 2 | `window.__NUXT__ = {…}` (often a function `(function(a,b){return {…}}(…))`) | `structured.state.__NUXT__` when plain JSON; else render and `JSON.stringify(window.__NUXT__)` |
| Nuxt 3 | `<script id="__NUXT_DATA__" type="application/json">` devalue-encoded array | parse with a devalue decoder or read `useNuxtApp().payload` in browser |
| Remix | `window.__remixContext` | `structured.state.__remixContext` |
| Redux / Vuex SSR | `window.__PRELOADED_STATE__`, `__INITIAL_STATE__` | `structured.state.*` |
| Apollo GraphQL SSR | `window.__APOLLO_STATE__` | `structured.state.__APOLLO_STATE__` (normalised cache keyed by `Type:id`) |
| SvelteKit | `<script type="application/json" data-sveltekit-fetched>` | grep for `data-sveltekit-fetched` |
| Angular Universal | `<script id="serverApp-state" type="application/json">` | grep for `serverApp-state` |

`ladder.py fetch URL --want json` returns all of these under `structured`, already parsed where possible.

## 4. Structured data markup (SEO-driven, extremely stable)

- JSON-LD `<script type="application/ld+json">` → `structured.jsonld` (Product, Offer, Article, JobPosting, Event, LocalBusiness, BreadcrumbList, FAQPage…). Prices, availability, ratings, author, datePublished are usually here.
- OpenGraph / Twitter cards → `structured.meta` (`og:title`, `og:image`, `article:published_time`).
- Microdata (`itemprop=`) → use a CSS schema with `type: attribute, attribute: content` on `[itemprop=price]`.

## 5. CSS schema (deterministic, free, reusable)

`assets/schema.example.json` shows the format (Crawl4AI-compatible subset). Make one by hand, or once with `llm_extract.py schema --url … --describe "…"` (≈$0.02 with Sonnet), then run `ladder.py select` or `batch --schema` for free forever. Prefer semantic selectors (`article`, `[data-testid]`, `[itemprop]`, `aria-*`) to generated class names — they survive redesigns.

## 6. Markdown for LLM extraction (last resort, but cheap when done right)

- Ask Cloudflare for markdown first: `Accept: text/markdown` on any Cloudflare zone with Markdown for Agents returns `text/markdown` with an `x-markdown-tokens` header (Feb 2026 feature). The ladder does this automatically when `--want md`.
- Otherwise trafilatura (`--md-mode clean`) — F-score 0.909 in the 2026 extractor benchmarks, ~82 % token reduction vs raw HTML measured here.
- Send only the markdown to Haiku with a JSON schema (`llm_extract.py extract --fields …`), cap with `--max-chars`, and use `--batch` for anything that can wait an hour.

## Pagination patterns

`?page=N` · `?offset=N&limit=M` (probe max limit: 100, 250, 500) · cursor tokens in JSON (`next_cursor`, `after`) · `rel="next"` links in HTML/headers · infinite scroll = an XHR with an offset (find it, do not scroll a browser). Stop conditions: empty page, repeated first id, `X-WP-TotalPages`, `total_count`.
