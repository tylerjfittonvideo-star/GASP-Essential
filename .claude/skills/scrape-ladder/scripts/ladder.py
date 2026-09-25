#!/usr/bin/env python3
"""
scrape-ladder engine — fetch the web at the lowest cost that works.

  cache → direct (curl_cffi, real-browser TLS) → browser (local headless) → jina (free renderer)
        → proxy (rotating residential/DC) → api (Decodo Web Scraping API, or any GET-style API)

Escalation is driven by *why* a fetch failed (JS shell, IP block, WAF vendor, 429).
Paid tiers stay OFF unless --budget is given. Every request is priced and ledgered.

Commands
  fetch     URL                 one page → md | json | html | text
  batch     URLS.txt | -        many pages, phase-wise escalation, JSONL out, resumable
  discover  DOMAIN              sitemaps (+feeds, +Common Crawl) → URL list, fast and free
  probe     URL                 what protects it, is JS needed, hidden JSON, est. $/1K
  select    URL|FILE --schema   CSS/attribute schema → JSON rows, no LLM
  job       JOB.json            discover → batch → (optional) LLM extract, unattended
  cost      [--pages N --tier T | --sheet]
  ledger    [--stats | --host H | --clear-host H | --purge-days N]

`python ladder.py <command> -h` lists flags. Environment variables are listed in SKILL.md.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import fnmatch
import glob
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urljoin, urlparse
import urllib.robotparser
import xml.etree.ElementTree as ET

VERSION = "0.1.0"
HOME = os.path.expanduser(os.environ.get("LADDER_HOME", "~/.scrape-ladder"))
CACHE_DIR = os.path.join(HOME, "cache")
DB_PATH = os.path.join(HOME, "ledger.sqlite")
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
UA = os.environ.get("LADDER_UA") or DEFAULT_UA
ROBOTS_AGENT = "scrape-ladder"
IMPERSONATE = os.environ.get("LADDER_IMPERSONATE", "chrome")
FLOOR_TTL = int(os.environ.get("LADDER_FLOOR_TTL", "21600"))  # 6 h
HARD_VENDORS = {"datadome", "perimeterx", "kasada", "imperva", "akamai"}
TIER_ORDER = ["cache", "direct", "browser", "jina", "proxy", "api"]
BINARY_CT = ("application/pdf", "image/", "audio/", "video/", "application/zip",
             "application/octet-stream", "application/vnd")
DECODO_SCRAPE = os.environ.get("DECODO_SCRAPE_ENDPOINT", "https://scraper-api.decodo.com/v2/scrape")
DECODO_TASK = os.environ.get("DECODO_TASK_ENDPOINT", "https://scraper-api.decodo.com/v3/task")

QUIET = False
VERBOSE = False


def _f(env, default):
    try:
        return float(os.environ.get(env, default))
    except (TypeError, ValueError):
        return float(default)


PRICES = {  # USD per request unless noted. Verified 2026-09 — see references/cost-model.md
    "proxy_usd_per_gb": _f("LADDER_PROXY_USD_PER_GB", 3.0),
    "decodo": {
        "standard":    _f("DECODO_USD_PER_1K_STANDARD", 0.50) / 1000,
        "standard_js": _f("DECODO_USD_PER_1K_STANDARD_JS", 0.75) / 1000,
        "premium":     _f("DECODO_USD_PER_1K_PREMIUM", 1.00) / 1000,
        "premium_js":  _f("DECODO_USD_PER_1K_PREMIUM_JS", 1.50) / 1000,
    },
    "generic_api": _f("SCRAPER_API_USD_PER_1K", 1.0) / 1000,
}

# Price sheet used by `cost --sheet`. (provider/tier, USD, unit, note)
SHEET = [
    ("cache / direct / browser (local)", 0.0, "per page", "your CPU + bandwidth only"),
    ("jina r.jina.ai (no key)", 0.0, "per page", "20 req/min; with free key 500 rpm, 10M free tokens then ~$0.02/1M"),
    ("Decodo Web Scraping API — standard", 0.50, "per 1K", "$0.14 at $99 plan; free plan 2K req"),
    ("Decodo — standard + JS render", 0.75, "per 1K", ""),
    ("Decodo — premium proxies", 1.00, "per 1K", ""),
    ("Decodo — premium + JS render", 1.50, "per 1K", "$1.20 at $99 plan"),
    ("Decodo Site Unblocker", 1.25, "per 1K", "or $10/GB; down to $0.95/1K at volume"),
    ("Decodo residential proxy", 3.75, "per GB", "$4 PAYG, $2/GB at 1 TB; ~500 KB page ≈ $1.9/1K"),
    ("Decodo datacenter proxy", 0.60, "per GB", "~500 KB page ≈ $0.30/1K"),
    ("Zyte API (HTTP)", 0.13, "per 1K", "$0.06–1.27 tiered; browser $0.48–16.08"),
    ("Bright Data Web Unlocker", 1.50, "per 1K", "5K free/month; success-based"),
    ("Oxylabs Web Unblocker", 9.40, "per GB", "per-GB only"),
    ("ScraperAPI", 0.29, "per 1K", "$29/100K credits; JS = 5–10 credits/page"),
    ("Scrape.do", 0.12, "per 1K", "$29/250K successful; free 1K/mo"),
    ("Firecrawl", 0.99, "per 1K", "1 credit/page; JSON mode 5 credits; stealth 5x"),
    ("Spider.cloud", 0.10, "per 1K", "≈$8–15 per 100K pages smart mode; $1/GB + CPU"),
    ("Apify", 1.50, "per 1K", "$5 free usage/month"),
    ("LLM extract — Haiku 4.5", 0.008, "per page", "≈6K in / 300 out tokens; ×0.5 with Batches API"),
    ("LLM extract — Sonnet 5", 0.015, "per page", "≈6K in / 300 out tokens; ×0.5 with Batches API"),
]


# ----------------------------------------------------------------------------- utils

def log(msg, level="info"):
    if QUIET and level == "info":
        return
    if level == "debug" and not VERBOSE:
        return
    print(f"[ladder] {msg}", file=sys.stderr, flush=True)


def iso(ts=None):
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hostof(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def sha1(s):
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()


def normalize_url(u):
    u = (u or "").strip()
    if not u or u.startswith("#"):
        return None
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    if not p.netloc:
        return None
    return p._replace(fragment="").geturl()


def has(mod):
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def rank(tier):
    return TIER_ORDER.index(tier) if tier in TIER_ORDER else 99


GEO_CC = {"united states": "us", "usa": "us", "united kingdom": "gb", "uk": "gb", "germany": "de", "france": "fr",
          "canada": "ca", "australia": "au", "spain": "es", "italy": "it", "netherlands": "nl", "japan": "jp",
          "brazil": "br", "india": "in", "mexico": "mx"}


def geo_to_cc(geo):
    if not geo:
        return None
    g = geo.strip().lower()
    if len(g) == 2:
        return g
    return GEO_CC.get(g)


# ----------------------------------------------------------------------------- page

@dataclass
class Page:
    url: str
    final_url: str = ""
    status: int = 0
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    text: str = ""
    content_type: str = ""
    tier: str = ""
    cost_usd: float = 0.0
    elapsed_ms: int = 0
    verdict: str = ""
    cache_hit: bool = False
    is_markdown: bool = False
    notes: list = field(default_factory=list)

    @property
    def is_html(self):
        ct = (self.content_type or "").lower()
        return (not self.is_markdown) and ("html" in ct or ct == "" or "xml" in ct)


# ----------------------------------------------------------------------------- html helpers

def _strip_tags_regex(html):
    t = re.sub(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>", " ", html or "")
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def visible_text(html):
    try:
        from selectolax.parser import HTMLParser
        t = HTMLParser(html or "")
        t.strip_tags(["script", "style", "noscript", "svg", "template", "head"])
        node = t.body or t.root
        return re.sub(r"\s+", " ", node.text(separator=" ", strip=True) if node else "").strip()
    except Exception:
        return _strip_tags_regex(html)


def css_exists(html, selector):
    try:
        from selectolax.parser import HTMLParser
        return HTMLParser(html or "").css_first(selector) is not None
    except Exception:
        return False


def looks_js_shell(html):
    if not html:
        return True
    txt = visible_text(html)
    if len(txt) >= 400:
        return False
    low = html.lower()
    return ("<script" in low) and (low.count("<script") >= 2 or 'id="__next"' in low or 'id="root"' in low
                                   or 'id="app"' in low or "enable javascript" in low or "<noscript" in low)


def extract_title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    if m:
        return re.sub(r"\s+", " ", _strip_tags_regex(m.group(1))).strip()[:300]
    return None


def title_from_md(md):
    m = re.search(r"^#\s+(.+)$", md or "", re.M)
    return m.group(1).strip()[:300] if m else None


def extract_links(html, base, limit=1000):
    out, seen = [], set()
    for h in re.findall(r'href=["\']([^"\'#]+)["\']', html or "", re.I):
        u = urljoin(base, h.strip())
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
            if len(out) >= limit:
                break
    return out


def to_markdown(html, url="", mode="clean"):
    html = html or ""
    if mode == "clean":
        try:
            import trafilatura
            md = trafilatura.extract(html, url=url or None, output_format="markdown", include_links=True,
                                     include_tables=True, include_images=False, include_comments=False,
                                     favor_recall=True)
            if md and len(md.strip()) >= 200:
                return md.strip()
        except Exception as e:
            log(f"trafilatura failed ({e}); using markdownify", "debug")
    try:
        from markdownify import markdownify
        cleaned = re.sub(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>", "", html)
        md = markdownify(cleaned, heading_style="ATX")
        return re.sub(r"\n{3,}", "\n\n", md).strip()
    except Exception:
        return _strip_tags_regex(html)


def to_text(html, url=""):
    try:
        import trafilatura
        t = trafilatura.extract(html or "", url=url or None, output_format="txt", favor_recall=True)
        if t and len(t.strip()) >= 100:
            return t.strip()
    except Exception:
        pass
    return visible_text(html)


def _balanced_json(s, start, limit=5_000_000):
    i = start
    n = min(len(s), start + limit)
    while i < n and s[i] in " \t\r\n":
        i += 1
    if i >= n or s[i] not in "{[":
        return None
    depth, in_str, esc = 0, False, False
    j = i
    while j < n:
        c = s[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    return s[i:j + 1]
        j += 1
    return None


STATE_KEYS = ["__NUXT__", "__INITIAL_STATE__", "__PRELOADED_STATE__", "__APOLLO_STATE__", "__INITIAL_DATA__",
              "__remixContext", "__STATE__", "__RELAY_STORE__", "__data__", "__PRELOADED__", "__SSR_DATA__"]


def _meta(html):
    meta, feeds = {}, []
    try:
        from selectolax.parser import HTMLParser
        t = HTMLParser(html or "")
        n = t.css_first("title")
        if n:
            meta["title"] = n.text(strip=True)[:300]
        for m in t.css("meta"):
            a = m.attributes
            k = a.get("property") or a.get("name") or a.get("itemprop")
            v = a.get("content")
            if k and v and (k.startswith(("og:", "twitter:", "article:", "product:")) or
                            k in ("description", "keywords", "author", "robots", "generator")):
                meta[k] = v[:1000]
        for l in t.css("link"):
            a = l.attributes
            rel = (a.get("rel") or "").lower()
            href = a.get("href")
            typ = (a.get("type") or "").lower()
            if rel == "canonical" and href:
                meta["canonical"] = href
            if "alternate" in rel and href and ("rss" in typ or "atom" in typ):
                feeds.append(href)
    except Exception:
        t = extract_title(html)
        if t:
            meta["title"] = t
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', html or "", re.I)
        if m:
            meta["description"] = m.group(1)
    return meta, feeds


def extract_structured(html, url=""):
    html = html or ""
    out = {"jsonld": [], "next_data": None, "state": {}, "state_present": [], "meta": {}, "feeds": []}
    for m in re.finditer(r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        raw = m.group(1).strip()
        obj = None
        for candidate in (raw, re.sub(r"[\x00-\x1f]", " ", raw)):
            try:
                obj = json.loads(candidate)
                break
            except Exception:
                continue
        if obj is None:
            continue
        if isinstance(obj, list):
            out["jsonld"].extend(obj)
        elif isinstance(obj, dict) and isinstance(obj.get("@graph"), list):
            out["jsonld"].extend(obj["@graph"])
        else:
            out["jsonld"].append(obj)
    m = re.search(r'<script[^>]*id\s*=\s*["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S | re.I)
    if m:
        try:
            out["next_data"] = json.loads(m.group(1))
        except Exception:
            out["state_present"].append("__NEXT_DATA__ (unparseable)")
    if "__next_f.push" in html:
        out["state_present"].append("__next_f (Next.js App Router RSC flight payload — see references/hidden-data.md)")
    for key in STATE_KEYS:
        m = re.search(r'(?:window\.|globalThis\.|self\.|var\s+|let\s+|const\s+)?' + re.escape(key) + r'\s*=\s*', html)
        if not m:
            continue
        blob = _balanced_json(html, m.end())
        if blob:
            try:
                out["state"][key] = json.loads(blob)
                continue
            except Exception:
                pass
        out["state_present"].append(key + " (present, not plain JSON — render in browser and read window." + key + ")")
    out["meta"], out["feeds"] = _meta(html)
    return out


def run_schema(html, schema, base_url=""):
    from selectolax.parser import HTMLParser
    tree = HTMLParser(html or "")

    def val(node, f):
        sel = f.get("selector")
        typ = f.get("type", "text")
        if typ == "list":
            return [n.text(strip=True) for n in (node.css(sel) if sel else [])]
        if typ == "nested":
            sub = node.css_first(sel) if sel else node
            return {ff["name"]: val(sub, ff) for ff in f.get("fields", [])} if sub else None
        if typ == "nested_list":
            return [{ff["name"]: val(sub, ff) for ff in f.get("fields", [])} for sub in (node.css(sel) if sel else [])]
        n = node.css_first(sel) if sel else node
        if n is None:
            return f.get("default")
        if typ == "attribute":
            v = n.attributes.get(f.get("attribute", "href"))
            if v and f.get("absolute") and base_url:
                v = urljoin(base_url, v)
            return v
        if typ == "html":
            return n.html
        if typ == "regex":
            m = re.search(f.get("pattern", ""), n.text())
            if not m:
                return f.get("default")
            return m.group(1) if m.groups() else m.group(0)
        v = n.text(strip=True)
        tr = f.get("transform")
        if tr == "lower":
            v = v.lower()
        elif tr == "upper":
            v = v.upper()
        return v

    base = schema.get("baseSelector")
    containers = tree.css(base) if base else [tree.root]
    rows = []
    for c in containers:
        row = {}
        for bf in schema.get("baseFields", []):
            row[bf["name"]] = val(c, {**bf, "selector": None})
        for f in schema.get("fields", []):
            row[f["name"]] = val(c, f)
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------- block detection

CHALLENGE_TEXT = ("just a moment", "checking your browser", "cf-chl", "challenge-platform", "__cf_chl",
                  "cf_chl_opt", "attention required! | cloudflare", "enable javascript and cookies to continue")


def vendor_of(page):
    """Name the bot-protection vendor when the response looks like a wall. Body-text signatures only count on
    error statuses or on tiny pages, so a 200 article that *mentions* DataDome is not a false positive."""
    h = page.headers or {}
    st = page.status
    body = page.text or ""
    sc = (h.get("set-cookie") or "").lower()
    server = (h.get("server") or "").lower()
    if h.get("cf-mitigated", "").lower() == "challenge":
        return "cloudflare"
    if "x-datadome" in h or "x-dd-b" in h or "x-px-block-score" in h or any(k.startswith("x-kpsdk") for k in h):
        if st in (401, 403, 429, 503):
            return "datadome" if ("x-datadome" in h or "x-dd-b" in h) else ("perimeterx" if "x-px-block-score" in h else "kasada")
    wall = st in (401, 403, 429, 503)
    tiny = len(body) < 60000 and len(visible_text(body)) < 1500 if body else True
    if not (wall or tiny):
        return None
    bl = body[:120000].lower()
    if any(s in bl for s in CHALLENGE_TEXT):
        return "cloudflare"
    if "captcha-delivery.com" in bl or "x-datadome" in h or "datadome" in sc:
        return "datadome"
    if "px-captcha" in bl or "_pxhd" in sc or "perimeterx" in bl or "humansecurity" in bl or "x-px-block-score" in h:
        return "perimeterx"
    if "kpsdk" in bl or any(k.startswith("x-kpsdk") for k in h):
        return "kasada"
    if "incap_ses" in sc or "visid_incap" in sc or "_incapsula_resource" in bl:
        return "imperva"
    if wall and ("_abck" in sc or "ak_bmsc" in sc or "akamai" in server or "akamai-grn" in bl):
        return "akamai"
    if wall and ("cf-ray" in h or "cloudflare" in server):
        return "cloudflare"
    if st == 403 and ("recaptcha" in bl or "hcaptcha" in bl or "access denied" in bl[:5000] or "bot" in bl[:3000]):
        return "unknown"
    return None


def classify(page, need=None):
    if page.verdict.startswith("error:"):
        return page.verdict
    st = page.status
    body = page.text or ""
    vendor = vendor_of(page)
    if st == 429:
        return f"blocked:{vendor}" if vendor in ("kasada", "datadome", "perimeterx") else "rate_limited"
    if vendor and (st in (401, 403, 503) or vendor != "unknown"):
        return f"blocked:{vendor}"
    if st in (401, 403):
        return "blocked:unknown"
    if st in (404, 410):
        return "not_found"
    if st == 304:
        return "not_modified"
    if st >= 500:
        return "server_error"
    if st and st not in (200, 203, 206):
        return f"http_{st}"
    ct = (page.content_type or "").lower()
    if ct.startswith(BINARY_CT):
        return "ok" if page.body else "empty"
    if not body.strip():
        return "empty"
    if page.is_markdown or "json" in ct or ct.startswith("text/plain"):
        return "ok"
    if need:
        return "ok" if css_exists(body, need) else "js_required"
    if looks_js_shell(body):
        return "js_required"
    return "ok"


# ----------------------------------------------------------------------------- ledger

class Ledger:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY, final_url TEXT, host TEXT, fetched_at REAL, status INTEGER,
        tier TEXT, verdict TEXT, etag TEXT, last_modified TEXT, content_hash TEXT, content_path TEXT,
        is_markdown INTEGER, cost_usd REAL, elapsed_ms INTEGER);
    CREATE INDEX IF NOT EXISTS pages_host ON pages(host);
    CREATE TABLE IF NOT EXISTS hosts(host TEXT PRIMARY KEY, floor_tier TEXT, reason TEXT, updated_at REAL,
        ok INTEGER DEFAULT 0, fail INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS spend(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, run_id TEXT, tier TEXT, url TEXT, usd REAL);
    """

    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.con = sqlite3.connect(path, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(self.SCHEMA)

    def row(self, url):
        return self.con.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()

    def _content_path(self, url, is_md):
        h = sha1(url)
        d = os.path.join(CACHE_DIR, h[:2])
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, h + (".md" if is_md else ".html"))

    def load_page(self, url):
        r = self.row(url)
        if not r or not r["content_path"] or not os.path.exists(r["content_path"]):
            return None
        with open(r["content_path"], "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        p = Page(url=url, final_url=r["final_url"] or url, status=r["status"] or 200, text=text,
                 content_type="text/markdown" if r["is_markdown"] else "text/html", tier="cache",
                 is_markdown=bool(r["is_markdown"]), cache_hit=True, verdict="ok")
        p.headers = {"etag": r["etag"] or "", "last-modified": r["last_modified"] or ""}
        p.notes.append(f"cached {iso(r['fetched_at'])} via {r['tier']}")
        return p

    def fresh(self, url, ttl, want="json"):
        r = self.row(url)
        if not r or r["verdict"] != "ok" or (time.time() - (r["fetched_at"] or 0)) > ttl:
            return None
        if want == "html" and r["is_markdown"]:
            return None
        return self.load_page(url)

    def conditional_headers(self, url):
        r = self.row(url)
        if not r or not r["content_path"] or not os.path.exists(r["content_path"]):
            return {}
        h = {}
        if r["etag"]:
            h["If-None-Match"] = r["etag"]
        if r["last_modified"]:
            h["If-Modified-Since"] = r["last_modified"]
        return h

    def put(self, page):
        path = None
        content_hash = None
        if page.verdict == "ok" and page.text:
            path = self._content_path(page.url, page.is_markdown)
            with open(path, "w", encoding="utf-8") as f:
                f.write(page.text)
            content_hash = sha1(page.text)
        self.con.execute(
            "INSERT INTO pages(url, final_url, host, fetched_at, status, tier, verdict, etag, last_modified, content_hash, "
            "content_path, is_markdown, cost_usd, elapsed_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET final_url=excluded.final_url, host=excluded.host, fetched_at=excluded.fetched_at, "
            "status=excluded.status, tier=excluded.tier, verdict=excluded.verdict, etag=COALESCE(excluded.etag, pages.etag), "
            "last_modified=COALESCE(excluded.last_modified, pages.last_modified), content_hash=COALESCE(excluded.content_hash, pages.content_hash), "
            "content_path=COALESCE(excluded.content_path, pages.content_path), is_markdown=excluded.is_markdown, cost_usd=excluded.cost_usd, "
            "elapsed_ms=excluded.elapsed_ms",
            (page.url, page.final_url or page.url, hostof(page.url), time.time(), page.status, page.tier, page.verdict,
             page.headers.get("etag") or None, page.headers.get("last-modified") or None, content_hash, path,
             1 if page.is_markdown else 0, page.cost_usd, page.elapsed_ms))
        self.con.commit()

    def floor(self, host):
        r = self.con.execute("SELECT floor_tier, updated_at FROM hosts WHERE host=?", (host,)).fetchone()
        if not r or not r["floor_tier"]:
            return None
        if time.time() - (r["updated_at"] or 0) > FLOOR_TTL:
            return None
        return r["floor_tier"]

    def set_floor(self, host, tier, reason):
        self.con.execute("INSERT INTO hosts(host, floor_tier, reason, updated_at) VALUES(?,?,?,?) ON CONFLICT(host) DO UPDATE SET "
                         "floor_tier=excluded.floor_tier, reason=excluded.reason, updated_at=excluded.updated_at", (host, tier, reason, time.time()))
        self.con.commit()

    def clear_floor(self, host):
        self.con.execute("UPDATE hosts SET floor_tier=NULL, reason=NULL, updated_at=? WHERE host=?", (time.time(), host))
        self.con.commit()

    def spend(self, run_id, tier, url, usd):
        if usd:
            self.con.execute("INSERT INTO spend(ts, run_id, tier, url, usd) VALUES(?,?,?,?,?)", (time.time(), run_id, tier, url, usd))
            self.con.commit()

    def stats(self):
        s = {"pages": self.con.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
             "by_tier": {r[0]: r[1] for r in self.con.execute("SELECT tier, COUNT(*) FROM pages GROUP BY tier")},
             "spend_usd_total": self.con.execute("SELECT COALESCE(SUM(usd),0) FROM spend").fetchone()[0],
             "spend_last_30d": self.con.execute("SELECT COALESCE(SUM(usd),0) FROM spend WHERE ts>?", (time.time() - 30 * 86400,)).fetchone()[0],
             "host_floors": [dict(r) for r in self.con.execute("SELECT host, floor_tier, reason, updated_at FROM hosts WHERE floor_tier IS NOT NULL")],
             "cache_dir": CACHE_DIR, "db": DB_PATH}
        total = 0
        for root, _, files in os.walk(CACHE_DIR):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        s["cache_bytes"] = total
        return s

    def purge(self, days):
        cutoff = time.time() - days * 86400
        rows = self.con.execute("SELECT url, content_path FROM pages WHERE fetched_at<?", (cutoff,)).fetchall()
        for r in rows:
            if r["content_path"] and os.path.exists(r["content_path"]):
                os.remove(r["content_path"])
        self.con.execute("DELETE FROM pages WHERE fetched_at<?", (cutoff,))
        self.con.commit()
        return len(rows)


class Budget:
    def __init__(self, limit):
        self.limit = float(limit or 0)
        self.spent = 0.0

    def can(self, cost):
        return self.limit > 0 and (self.spent + cost) <= self.limit + 1e-9

    def charge(self, cost):
        self.spent += cost


# ----------------------------------------------------------------------------- network layer

def _headers(accept_md=False, extra=None):
    h = {
        "Accept": ("text/markdown, text/html;q=0.9, application/xhtml+xml;q=0.8, */*;q=0.7" if accept_md
                   else "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
    }
    if os.environ.get("LADDER_UA"):
        h["User-Agent"] = UA
    if extra:
        h.update(extra)
    return h


class _HttpxSession:
    """Fallback when curl_cffi is missing: same .get/.post surface, no TLS impersonation."""

    def __init__(self, concurrency):
        import httpx
        self.c = httpx.AsyncClient(http2=has("h2"), follow_redirects=True, headers={"User-Agent": UA},
                                   limits=httpx.Limits(max_connections=max(2, concurrency)))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        await self.c.aclose()

    async def get(self, url, headers=None, timeout=30, allow_redirects=True, proxies=None):
        return await self.c.get(url, headers=headers, timeout=timeout)

    async def post(self, url, json=None, headers=None, timeout=30, allow_redirects=True, proxies=None):
        return await self.c.post(url, json=json, headers=headers, timeout=timeout)


def _session(concurrency, impersonate=True):
    if has("curl_cffi"):
        from curl_cffi.requests import AsyncSession
        if impersonate:
            return AsyncSession(impersonate=IMPERSONATE, max_clients=max(2, concurrency))
        return AsyncSession(max_clients=max(2, concurrency), headers={"User-Agent": f"scrape-ladder/{VERSION} (+https://github.com/tylerjfittonvideo-star)"})
    if has("httpx"):
        log("curl_cffi not installed — falling back to httpx (no browser TLS fingerprint). Run setup.sh.", "warn")
        return _HttpxSession(concurrency)
    raise SystemExit("Neither curl_cffi nor httpx is installed. Run: bash scripts/setup.sh")


def _page_from_response(url, r, tier):
    headers = {str(k).lower(): str(v) for k, v in r.headers.items()}
    ct = (headers.get("content-type") or "").lower()
    body = r.content or b""
    text = ""
    if not ct.startswith(BINARY_CT):
        try:
            text = r.text
        except Exception:
            text = body.decode("utf-8", "replace")
    p = Page(url=url, final_url=str(getattr(r, "url", url) or url), status=int(r.status_code), headers=headers,
             body=body, text=text, content_type=ct, tier=tier)
    p.is_markdown = ct.startswith("text/markdown")
    return p


class Politeness:
    def __init__(self, interval, per_host):
        self.interval = interval
        self.next = {}
        self.override = {}
        self.locks = defaultdict(asyncio.Lock)
        self.sems = defaultdict(lambda: asyncio.Semaphore(max(1, per_host)))

    async def wait(self, host):
        async with self.locks[host]:
            iv = self.override.get(host, self.interval)
            now = time.monotonic()
            t = max(now, self.next.get(host, now))
            self.next[host] = t + iv
        if t > now:
            await asyncio.sleep(t - now)

    def backoff(self, host):
        self.override[host] = min(10.0, max(self.override.get(host, self.interval), 0.5) * 2)


def _proxy_kw(proxy):
    return {"proxies": {"http": proxy, "https": proxy}} if proxy else {}


async def direct_many(urls, opts, ledger, *, proxy=None, tier="direct"):
    out = {}
    sem = asyncio.Semaphore(opts.concurrency)
    pol = Politeness(opts.host_interval, opts.per_host)
    accept_md = opts.want in ("md", "text") and not opts.no_md_negotiation
    async with _session(opts.concurrency) as s:
        async def one(u):
            host = hostof(u)
            cond = ledger.conditional_headers(u) if (ledger and not opts.refresh) else {}
            hdrs = _headers(accept_md, {**opts.extra_headers, **cond})
            if opts.cookie:
                hdrs["Cookie"] = opts.cookie
            async with sem, pol.sems[host]:
                await pol.wait(host)
                t0 = time.monotonic()
                try:
                    r = await s.get(u, headers=hdrs, timeout=opts.timeout, allow_redirects=True, **_proxy_kw(proxy))
                    p = _page_from_response(u, r, tier)
                except Exception as e:
                    p = Page(url=u, tier=tier, verdict=f"error:{type(e).__name__}", notes=[str(e)[:200]])
                p.elapsed_ms = int((time.monotonic() - t0) * 1000)
                if proxy:
                    p.cost_usd = (len(p.body) + 2048) / 1e9 * PRICES["proxy_usd_per_gb"]
                if p.status == 304:
                    cached = ledger.load_page(u) if ledger else None
                    if cached:
                        cached.tier = tier + "-304"
                        cached.elapsed_ms = p.elapsed_ms
                        p = cached
                    else:
                        p.verdict = "not_modified"
                elif not p.verdict:
                    p.verdict = classify(p, opts.need)
                if p.verdict == "rate_limited":
                    pol.backoff(host)
                out[u] = p
        await asyncio.gather(*(one(u) for u in urls))
    return out


async def jina_many(urls, opts):
    key = os.environ.get("JINA_API_KEY")
    interval = 0.13 if key else 3.05  # 500 rpm with a free key, 20 rpm without
    conc = 8 if key else 2
    out = {}
    sem = asyncio.Semaphore(conc)
    lock = asyncio.Lock()
    nxt = [time.monotonic()]
    # NB: r.jina.ai sits behind Cloudflare and challenges an impersonated Chrome that runs no JS; a plain API-client UA passes.
    hdrs = {"Accept": "application/json", "X-Respond-With": "markdown", "X-Timeout": str(min(60, max(10, opts.timeout))),
            "User-Agent": f"scrape-ladder/{VERSION}"}
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    if opts.need:
        hdrs["X-Wait-For-Selector"] = opts.need
    async with _session(conc, impersonate=False) as s:
        async def one(u):
            async with sem:
                async with lock:
                    now = time.monotonic()
                    t = max(now, nxt[0])
                    nxt[0] = t + interval
                if t > now:
                    await asyncio.sleep(t - now)
                t0 = time.monotonic()
                try:
                    r = await s.get("https://r.jina.ai/" + u, headers=hdrs, timeout=max(60, opts.timeout + 30), allow_redirects=True)
                    p = Page(url=u, tier="jina", status=int(r.status_code), headers={str(k).lower(): str(v) for k, v in r.headers.items()})
                    try:
                        data = r.json()
                    except Exception:
                        data = None
                    d = (data or {}).get("data") if isinstance(data, dict) else None
                    if r.status_code == 200 and isinstance(d, dict) and d.get("content"):
                        p.text = d["content"]
                        p.is_markdown = True
                        p.content_type = "text/markdown"
                        p.final_url = d.get("url") or u
                        if d.get("title"):
                            p.notes.append("title=" + str(d["title"])[:80])
                        low = p.text[:600].lower()
                        if any(s in low for s in CHALLENGE_TEXT):
                            p.verdict = "blocked:cloudflare"
                        elif len(p.text.strip()) < 80:
                            p.verdict = "empty"
                        else:
                            p.verdict = "ok"
                    else:
                        msg = ""
                        if isinstance(data, dict):
                            msg = data.get("readableMessage") or data.get("message") or ""
                        p.verdict = "rate_limited" if r.status_code == 429 else f"error:jina_{r.status_code}"
                        p.notes.append(str(msg or r.text[:200])[:200])
                except Exception as e:
                    p = Page(url=u, tier="jina", verdict=f"error:{type(e).__name__}", notes=[str(e)[:200]])
                p.elapsed_ms = int((time.monotonic() - t0) * 1000)
                out[u] = p
        await asyncio.gather(*(one(u) for u in urls))
    return out


def find_browser():
    env = os.environ.get("LADDER_BROWSER_PATH")
    if env and os.path.exists(env):
        return env
    cands = []
    if sys.platform == "darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium",
                  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
        cands += sorted(glob.glob(os.path.expanduser("~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium")), reverse=True)
    else:
        for base in [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), os.path.expanduser("~/.cache/ms-playwright"), "/opt/pw-browsers"]:
            if base:
                cands += sorted(glob.glob(os.path.join(base, "chromium-*/chrome-linux*/chrome")), reverse=True)
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            w = shutil.which(name)
            if w:
                cands.append(w)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def browser_engine():
    if has("patchright"):
        return "patchright"
    if has("playwright"):
        return "playwright"
    return None


def _proxy_dict(proxy):
    if not proxy:
        return None
    p = urlparse(proxy)
    d = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        d["username"] = p.username
        d["password"] = p.password or ""
    return d


def stealth_fetch(url, opts, proxy=None):
    """Scrapling StealthyFetcher (Camoufox) — solves Cloudflare Turnstile/interstitials locally. Optional dependency."""
    t0 = time.monotonic()
    pg = Page(url=url, tier="browser:stealth")
    try:
        from scrapling.fetchers import StealthyFetcher
        kw = dict(headless=True, solve_cloudflare=True, disable_resources=not opts.keep_assets,
                  timeout=max(60000, opts.timeout * 1000), network_idle=False)
        if proxy:
            kw["proxy"] = proxy
        if opts.need:
            kw["wait_selector"] = opts.need
        res = StealthyFetcher.fetch(url, **kw)
        html = getattr(res, "html_content", None)
        if html is None:
            body = getattr(res, "body", None)
            html = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else (body or str(res))
        pg.status = int(getattr(res, "status", 200) or 200)
        pg.text = html
        pg.content_type = "text/html"
        pg.final_url = getattr(res, "url", url) or url
        pg.verdict = classify(pg, opts.need)
        if pg.verdict == "js_required" and not opts.need:
            pg.verdict = "ok"
    except Exception as e:
        pg.verdict = f"error:{type(e).__name__}"
        pg.notes.append(str(e)[:200])
    pg.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return pg


async def render_many(urls, opts, *, proxy=None, stealth_for=frozenset()):
    out = {}
    stealth_urls = [u for u in urls if u in stealth_for] if has("scrapling") else []
    plain_urls = [u for u in urls if u not in stealth_urls]
    for u in stealth_urls:
        out[u] = await asyncio.to_thread(stealth_fetch, u, opts, proxy)
    if not plain_urls:
        return out
    engine = browser_engine()
    if not engine:
        for u in plain_urls:
            out[u] = Page(url=u, tier="browser", verdict="error:no_browser_engine", notes=["pip install patchright (or playwright); see setup.sh browser"])
        return out
    if engine == "patchright":
        from patchright.async_api import async_playwright
    else:
        from playwright.async_api import async_playwright
    exe = find_browser()
    launch_args = ["--disable-blink-features=AutomationControlled", "--disable-gpu", "--disable-dev-shm-usage",
                   "--no-first-run", "--no-default-browser-check"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        launch_args.append("--no-sandbox")
    insecure = os.environ.get("LADDER_BROWSER_INSECURE_TLS") == "1"
    if insecure:
        launch_args += ["--ignore-certificate-errors", "--disable-http2"]
    sem = asyncio.Semaphore(opts.browser_concurrency)
    block = set() if opts.keep_assets else {"image", "font", "media", "stylesheet", "texttrack", "manifest"}
    async with async_playwright() as p:
        kw = dict(headless=True, args=launch_args)
        if exe:
            kw["executable_path"] = exe
        try:
            browser = await p.chromium.launch(**kw)
        except Exception as e:
            for u in plain_urls:
                out[u] = Page(url=u, tier="browser", verdict="error:browser_launch", notes=[str(e)[:300]])
            return out
        ckw = dict(ignore_https_errors=insecure, locale=opts.locale or "en-US", viewport={"width": 1366, "height": 900}, user_agent=UA)
        pd = _proxy_dict(proxy)
        if pd:
            ckw["proxy"] = pd
        context = await browser.new_context(**ckw)
        if block:
            async def _route(route):
                if route.request.resource_type in block:
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", _route)

        async def one(u):
            async with sem:
                page = await context.new_page()
                t0 = time.monotonic()
                pg = Page(url=u, tier=f"browser:{engine}")
                try:
                    resp = await page.goto(u, wait_until=opts.wait_until, timeout=opts.timeout * 1000)
                    if opts.need:
                        try:
                            await page.wait_for_selector(opts.need, timeout=min(20000, opts.timeout * 1000))
                        except Exception:
                            pg.notes.append("need-selector did not appear in time")
                    else:
                        try:
                            await page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass
                    if opts.wait_ms:
                        await page.wait_for_timeout(opts.wait_ms)
                    html = await page.content()
                    pg.status = resp.status if resp else 200
                    pg.headers = {str(k).lower(): str(v) for k, v in (resp.headers.items() if resp else [])}
                    pg.final_url = page.url
                    pg.text = html
                    pg.content_type = "text/html"
                    pg.verdict = classify(pg, opts.need)
                    if pg.verdict == "js_required" and not opts.need:
                        pg.verdict = "ok"
                    elif pg.verdict == "js_required" and opts.need:
                        pg.verdict = "need_missing"
                except Exception as e:
                    pg.verdict = f"error:{type(e).__name__}"
                    pg.notes.append(str(e)[:200])
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass
                pg.elapsed_ms = int((time.monotonic() - t0) * 1000)
                out[u] = pg
        await asyncio.gather(*(one(u) for u in plain_urls))
        try:
            await browser.close()
        except Exception:
            pass
    return out


def decodo_token():
    t = os.environ.get("DECODO_AUTH_TOKEN")
    if t:
        return t.strip()
    u, p = os.environ.get("DECODO_USER"), os.environ.get("DECODO_PASS")
    if u and p:
        return base64.b64encode(f"{u}:{p}".encode()).decode()
    return None


def api_available():
    return bool(decodo_token() or os.environ.get("SCRAPER_API_URL_TEMPLATE"))


async def decodo_many(urls, opts, budget, ledger, *, js_for=frozenset(), premium_for=frozenset()):
    token = decodo_token()
    out = {}
    if not token:
        return {u: Page(url=u, tier="api", verdict="error:no_api_credentials", notes=["set DECODO_AUTH_TOKEN"]) for u in urls}
    sem = asyncio.Semaphore(max(1, min(opts.concurrency, int(opts.api_rps))))
    lock = asyncio.Lock()
    nxt = [time.monotonic()]
    interval = 1.0 / max(0.5, opts.api_rps)
    hdrs = {"Authorization": f"Basic {token}", "Content-Type": "application/json", "Accept": "application/json"}
    want_md = opts.want in ("md", "text") and opts.api_markdown

    async with _session(opts.concurrency) as s:
        async def call(u, js, pool):
            key = pool + ("_js" if js else "")
            cost = PRICES["decodo"][key]
            if not budget.can(cost):
                return Page(url=u, tier="api", verdict="budget_exhausted", notes=[f"needs ${cost:.4f}; raise --budget"])
            body = {"url": u, "target": "universal", "proxy_pool": pool}
            if js:
                body["headless"] = "html"
            if want_md:
                body["markdown"] = True
            if opts.geo:
                body["geo"] = opts.geo
            if opts.locale:
                body["locale"] = opts.locale
            if opts.session:
                body["session_id"] = opts.session
            async with lock:
                now = time.monotonic()
                t = max(now, nxt[0])
                nxt[0] = t + interval
            if t > now:
                await asyncio.sleep(t - now)
            t0 = time.monotonic()
            try:
                r = await s.post(DECODO_SCRAPE, json=body, headers=hdrs, timeout=max(opts.timeout, 120), allow_redirects=True)
            except Exception as e:
                return Page(url=u, tier="api", verdict=f"error:{type(e).__name__}", notes=[str(e)[:200]])
            p = Page(url=u, tier=f"api:decodo:{key}", elapsed_ms=int((time.monotonic() - t0) * 1000))
            if r.status_code in (401, 403):
                p.verdict = "error:api_auth"
                p.notes.append(r.text[:200])
                return p
            if r.status_code == 429:
                p.verdict = "rate_limited"
                p.notes.append("Decodo API rate limit (lower --api-rps)")
                return p
            budget.charge(cost)
            p.cost_usd = cost
            if ledger:
                ledger.spend(opts.run_id, p.tier, u, cost)
            try:
                data = r.json()
            except Exception:
                p.verdict = f"error:api_{r.status_code}"
                p.notes.append(r.text[:200])
                return p
            res = (data.get("results") or [{}])[0] if isinstance(data, dict) else {}
            content = res.get("content") or ""
            p.status = int(res.get("status_code") or r.status_code or 0)
            p.text = content if isinstance(content, str) else json.dumps(content)
            p.final_url = res.get("url") or u
            p.is_markdown = bool(want_md) and not p.text.lstrip().startswith("<")
            p.content_type = "text/markdown" if p.is_markdown else "text/html"
            p.headers = {"x-decodo-task-id": str(res.get("task_id", ""))}
            p.verdict = classify(p, None if p.is_markdown else opts.need)
            if p.verdict == "js_required" and js:
                p.verdict = "ok"
            return p

        async def one(u):
            async with sem:
                js = opts.js or (u in js_for)
                pool = "premium" if (u in premium_for or opts.api_pool == "premium") else "standard"
                p = await call(u, js, pool)
                if (p.verdict.startswith("blocked") or p.verdict in ("js_required", "empty")) and (pool == "standard" or not js):
                    p2 = await call(u, True, "premium")
                    p2.cost_usd += p.cost_usd
                    p2.notes.append(f"retried premium+js after {p.verdict}")
                    p = p2
                out[u] = p
        await asyncio.gather(*(one(u) for u in urls))
    return out


async def generic_api_many(urls, opts, budget, ledger, *, js_for=frozenset()):
    tpl = os.environ.get("SCRAPER_API_URL_TEMPLATE", "")
    cost = PRICES["generic_api"]
    out = {}
    sem = asyncio.Semaphore(max(1, min(opts.concurrency, int(opts.api_rps))))
    async with _session(opts.concurrency) as s:
        async def one(u):
            async with sem:
                if not budget.can(cost):
                    out[u] = Page(url=u, tier="api:generic", verdict="budget_exhausted", notes=["raise --budget"])
                    return
                js = opts.js or (u in js_for)
                target = tpl.replace("{url}", quote(u, safe="")).replace("{js}", "true" if js else "false")
                t0 = time.monotonic()
                try:
                    r = await s.get(target, headers=_headers(False), timeout=max(opts.timeout, 90), allow_redirects=True)
                    p = _page_from_response(u, r, "api:generic")
                    p.final_url = u
                except Exception as e:
                    p = Page(url=u, tier="api:generic", verdict=f"error:{type(e).__name__}", notes=[str(e)[:200]])
                p.elapsed_ms = int((time.monotonic() - t0) * 1000)
                if p.status not in (401, 403, 429):
                    budget.charge(cost)
                    p.cost_usd = cost
                    if ledger:
                        ledger.spend(opts.run_id, p.tier, u, cost)
                if not p.verdict:
                    p.verdict = classify(p, opts.need)
                out[u] = p
        await asyncio.gather(*(one(u) for u in urls))
    return out


# ----------------------------------------------------------------------------- robots

_ROBOTS = {}


def robots_ok(url, timeout=10):
    host = hostof(url)
    if not host:
        return True
    rp = _ROBOTS.get(host)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            txt = fetch_text(base + "/robots.txt", timeout=timeout)
            if txt is None:
                rp = False
            else:
                rp.parse(txt.splitlines())
        except Exception:
            rp = False
        _ROBOTS[host] = rp
    if rp is False:
        return True
    try:
        return rp.can_fetch(ROBOTS_AGENT, url) and rp.can_fetch("*", url) if False else rp.can_fetch(ROBOTS_AGENT, url)
    except Exception:
        return True


def fetch_text(url, timeout=15, headers=None, accept_md=False, binary=False):
    """Small sync GET used by discover/probe/robots. Returns str (or bytes if binary) or None on non-2xx."""
    try:
        if has("curl_cffi"):
            from curl_cffi import requests as cr
            r = cr.get(url, impersonate=IMPERSONATE, headers=_headers(accept_md, headers), timeout=timeout, allow_redirects=True)
            if r.status_code >= 400:
                return None
            return r.content if binary else r.text
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return data if binary else data.decode(resp.headers.get_content_charset() or "utf-8", "replace")
    except Exception:
        return None


def fetch_head(url, timeout=12, accept_md=False):
    """Returns (status, headers, text[:2000]) for cheap capability checks."""
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, impersonate=IMPERSONATE, headers=_headers(accept_md), timeout=timeout, allow_redirects=True)
        return r.status_code, {str(k).lower(): str(v) for k, v in r.headers.items()}, (r.text or "")[:2000]
    except Exception as e:
        return 0, {}, f"error:{type(e).__name__}"


# ----------------------------------------------------------------------------- options & escalation

def proxy_url_from_env(geo=None, session=None):
    u = os.environ.get("LADDER_PROXY_URL")
    if u:
        return u
    user, pw = os.environ.get("DECODO_PROXY_USER"), os.environ.get("DECODO_PROXY_PASS")
    if user and pw:
        host = os.environ.get("DECODO_PROXY_HOST", "gate.decodo.com:7000")
        name = f"user-{user}"
        cc = os.environ.get("DECODO_PROXY_COUNTRY") or geo_to_cc(geo)
        if cc:
            name += f"-country-{cc}"
        if session:
            name += "-session-" + re.sub(r"[^a-zA-Z0-9]", "", session)[:20]
        return f"http://{quote(name)}:{quote(pw)}@{host}"
    return None


class Opts:
    def __init__(self, a):
        g = lambda k, d=None: getattr(a, k, d)
        self.want = g("want", "json")
        self.need = g("need")
        self.js = bool(g("js", False))
        b = g("budget")
        self.budget = float(b) if b is not None else _f("LADDER_BUDGET_USD", 0)
        self.concurrency = int(g("concurrency", 16) or 16)
        self.per_host = int(g("per_host", 4) or 4)
        self.host_interval = float(g("host_interval", 0.25) or 0)
        self.timeout = int(g("timeout", 25) or 25)
        self.ttl = int(g("ttl", 86400) or 86400)
        self.refresh = bool(g("refresh", False))
        self.respect_robots = (not g("ignore_robots", False)) and os.environ.get("LADDER_RESPECT_ROBOTS", "1") != "0"
        self.no_jina = bool(g("no_jina", False)) or os.environ.get("LADDER_NO_JINA") == "1"
        self.no_md_negotiation = bool(g("no_md_negotiation", False))
        self.md_mode = g("md_mode", "clean") or "clean"
        self.include_html = bool(g("include_html", False))
        self.links = bool(g("links", False))
        self.structured = not g("no_structured", False)
        self.max_tier = g("max_tier", "api") or "api"
        self.min_tier = g("min_tier", "cache") or "cache"
        self.try_all = bool(g("try_all", False))
        self.browser_concurrency = int(g("browser_concurrency", 4) or 4)
        self.keep_assets = bool(g("keep_assets", False))
        self.wait_until = g("wait_until", "domcontentloaded") or "domcontentloaded"
        self.wait_ms = int(g("wait_ms", 0) or 0)
        self.geo = g("geo")
        self.locale = g("locale")
        self.session = g("session")
        self.api_pool = g("api_pool", "standard") or "standard"
        self.api_rps = float(g("api_rps", 5) or 5)
        self.api_markdown = not g("api_html", False)
        self.extra_headers = {}
        for hv in (g("header") or []):
            if ":" in hv:
                k, v = hv.split(":", 1)
                self.extra_headers[k.strip()] = v.strip()
        self.cookie = g("cookie")
        self.proxy = g("proxy") or proxy_url_from_env(self.geo, self.session)
        self.out = g("out")
        self.dump_dir = g("dump_dir")
        self.schema_obj = None
        sp = g("schema")
        if sp:
            with open(sp, "r", encoding="utf-8") as f:
                self.schema_obj = json.load(f)
        self.run_id = datetime.now().strftime("%Y%m%dT%H%M%S")


def tier_available(tier, opts, budget):
    if tier == "direct":
        return (has("curl_cffi") or has("httpx"), "install curl_cffi")
    if tier == "browser":
        return (browser_engine() is not None or has("scrapling"), "no browser engine (setup.sh browser)")
    if tier == "jina":
        return (not opts.no_jina, "disabled (--no-jina)")
    if tier == "proxy":
        return (bool(opts.proxy), "no proxy configured (LADDER_PROXY_URL or DECODO_PROXY_USER/PASS)")
    if tier == "api":
        if not api_available():
            return (False, "no API credentials (DECODO_AUTH_TOKEN)")
        if budget.limit <= 0:
            return (False, "paid tier off — pass --budget USD to allow spend")
        return (True, "")
    return (False, "unknown tier")


def wants_tier(v, tier, opts):
    if v.startswith("floor:"):
        return rank(tier) >= rank(v[6:])
    vendor = v.split(":", 1)[1] if v.startswith("blocked:") else None
    if tier == "direct":
        return v == "new"
    if tier == "browser":
        if v in ("js_required", "empty", "need_missing") or v.startswith("error:jina"):
            return True
        if vendor in ("cloudflare", "unknown"):
            return has("scrapling") or opts.try_all or sys.platform == "darwin"
        return False
    if tier == "jina":
        return v in ("js_required", "empty", "need_missing") or v.startswith("error:browser") or v == "error:no_browser_engine"
    if tier == "proxy":
        return (vendor is not None and vendor not in HARD_VENDORS) or v == "rate_limited" or v.startswith("error:")
    if tier == "api":
        return v not in ("not_found", "robots_disallow")
    return False


def _js_ish(v):
    return v in ("js_required", "empty", "need_missing") or v.startswith("error:browser") or v.startswith("error:jina")


def escalate(urls, opts, ledger, budget):
    """Fetch every URL through the ladder. Returns (results: {url: Page}, stats: [(tier, tried, ok, usd, secs)])."""
    results, stats = {}, []
    urls = [u for u in urls if u]
    if opts.respect_robots:
        allowed = []
        for u in urls:
            if robots_ok(u):
                allowed.append(u)
            else:
                results[u] = Page(url=u, tier="robots", verdict="robots_disallow", notes=["disallowed by robots.txt (use --ignore-robots only with permission)"])
        urls = allowed
    if not opts.refresh and rank(opts.min_tier) <= rank("cache"):
        for u in urls:
            p = ledger.fresh(u, opts.ttl, opts.want) if ledger else None
            if p:
                results[u] = p
    pending = {u: "new" for u in urls if u not in results}
    first_fail = {}
    if not opts.try_all and ledger:
        for u in list(pending):
            fl = ledger.floor(hostof(u))
            if fl and fl != "direct":
                pending[u] = f"floor:{fl}"
                first_fail[u] = "floor"
    if rank(opts.min_tier) > rank("direct"):
        for u in pending:
            pending[u] = f"floor:{opts.min_tier}"
    order = [t for t in TIER_ORDER if t != "cache" and rank(t) <= rank(opts.max_tier)]
    for tier in order:
        if not pending:
            break
        sel = [u for u, v in pending.items() if wants_tier(v, tier, opts)]
        if not sel:
            continue
        ok_avail, why = tier_available(tier, opts, budget)
        if not ok_avail:
            log(f"{tier}: skipped for {len(sel)} url(s) — {why}")
            for u in sel:
                if u in results:
                    results[u].notes.append(f"{tier} skipped: {why}")
            continue
        t0 = time.time()
        js_for = frozenset(u for u in sel if _js_ish(pending[u]) or pending[u] in ("floor:browser", "floor:jina"))
        premium_for = frozenset(u for u in sel if (pending[u].startswith("blocked:") and pending[u].split(":", 1)[1] in HARD_VENDORS) or pending[u] == "rate_limited")
        stealth_for = frozenset(u for u in sel if pending[u].startswith("blocked:"))
        log(f"{tier}: {len(sel)} url(s)…", "debug")
        if tier == "direct":
            res = asyncio.run(direct_many(sel, opts, ledger))
        elif tier == "browser":
            res = asyncio.run(render_many(sel, opts, proxy=None, stealth_for=stealth_for))
        elif tier == "jina":
            res = asyncio.run(jina_many(sel, opts))
        elif tier == "proxy":
            res = asyncio.run(direct_many(sel, opts, ledger, proxy=opts.proxy, tier="proxy"))
        elif tier == "api":
            if decodo_token():
                res = asyncio.run(decodo_many(sel, opts, budget, ledger, js_for=js_for, premium_for=premium_for))
            else:
                res = asyncio.run(generic_api_many(sel, opts, budget, ledger, js_for=js_for))
        else:
            continue
        ok = 0
        usd = 0.0
        for u, p in res.items():
            usd += p.cost_usd
            if p.verdict == "ok":
                ok += 1
                results[u] = p
                pending.pop(u, None)
                if ledger:
                    ledger.put(p)
            elif p.verdict in ("not_found", "robots_disallow", "budget_exhausted"):
                results[u] = p
                pending.pop(u, None)
            else:
                if tier == "direct":
                    first_fail[u] = p.verdict
                prev = results.get(u)
                if prev is not None and prev.verdict != "ok":
                    p.notes = (prev.notes + [f"{prev.tier}: {prev.verdict}"] + p.notes)[-8:]
                results[u] = p
                pending[u] = p.verdict
        stats.append((tier, len(sel), ok, usd, round(time.time() - t0, 2)))
        log(f"{tier}: {ok}/{len(sel)} ok in {stats[-1][4]}s" + (f", ${usd:.4f}" if usd else ""))
    for u, v in pending.items():
        results.setdefault(u, Page(url=u, verdict=v))
    # learn per-host floors so the next run skips tiers that are known to fail
    if ledger and not opts.try_all:
        tally = defaultdict(lambda: defaultdict(int))
        for u, p in results.items():
            ff = first_fail.get(u)
            if p.verdict == "ok" and ff and ff != "floor" and rank(p.tier.split(":")[0]) > rank("direct"):
                tally[hostof(u)][p.tier.split(":")[0]] += 1
        for host, tiers in tally.items():
            tier, n = max(tiers.items(), key=lambda kv: kv[1])
            hard = any(first_fail.get(u, "").startswith("blocked:") and first_fail[u].split(":", 1)[1] in HARD_VENDORS for u in results if hostof(u) == host)
            if n >= 2 or hard:
                ledger.set_floor(host, tier, f"direct failed, {tier} worked ({n}x)")
                log(f"host floor: {host} → {tier} for {FLOOR_TTL // 3600}h (override with --try-all)", "debug")
    return results, stats


# ----------------------------------------------------------------------------- records & output

def _slug(url):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", urlparse(url).path.strip("/") or "index").strip("-")[:60]
    return s or "index"


def build_record(p, opts):
    rec = {"url": p.url, "final_url": p.final_url or p.url, "status": p.status, "tier": p.tier, "verdict": p.verdict,
           "cost_usd": round(p.cost_usd, 6), "elapsed_ms": p.elapsed_ms, "cache_hit": p.cache_hit, "fetched_at": iso(),
           "notes": p.notes[:8]}
    if p.verdict != "ok":
        return rec
    html = p.text if p.is_html else None
    md = p.text if p.is_markdown else None
    ct = (p.content_type or "").lower()
    if html:
        rec["title"] = extract_title(html)
    elif md:
        rec["title"] = title_from_md(md)
    if opts.want in ("md", "json", "text"):
        if md is not None:
            rec["markdown"] = md
        elif html is not None:
            rec["markdown"] = to_markdown(html, rec["final_url"], opts.md_mode)
        elif "json" in ct:
            try:
                rec["markdown"] = "```json\n" + json.dumps(json.loads(p.text), indent=2, ensure_ascii=False) + "\n```"
            except Exception:
                rec["markdown"] = p.text
        elif ct.startswith("application/pdf") and has("markitdown"):
            try:
                from markitdown import MarkItDown
                rec["markdown"] = MarkItDown().convert_stream(io.BytesIO(p.body), file_extension=".pdf").text_content
            except Exception as e:
                rec["markdown"] = ""
                rec["notes"].append(f"pdf→md failed: {e}")
        else:
            rec["markdown"] = p.text
    if opts.want == "text":
        rec["text"] = to_text(html, rec["final_url"]) if html else (p.text or "")
    if opts.want == "json" and html:
        if opts.structured:
            rec["structured"] = extract_structured(html, rec["final_url"])
        if opts.links:
            rec["links"] = extract_links(html, rec["final_url"])
    if opts.schema_obj and html:
        try:
            rec["rows"] = run_schema(html, opts.schema_obj, rec["final_url"])
        except Exception as e:
            rec["notes"].append(f"schema failed: {e}")
    if opts.want == "html" or opts.include_html:
        rec["html"] = html if html is not None else p.text
    rec["chars"] = len(rec.get("markdown") or rec.get("text") or rec.get("html") or "")
    if opts.dump_dir:
        os.makedirs(opts.dump_dir, exist_ok=True)
        ext = ".html" if opts.want == "html" else ".md"
        path = os.path.join(opts.dump_dir, f"{sha1(p.url)[:10]}-{_slug(p.url)}{ext}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(rec.get("html") if ext == ".html" else (rec.get("markdown") or ""))
        rec["dump_path"] = path
    return rec


def render_single(rec, want):
    if want == "json":
        return json.dumps(rec, ensure_ascii=False, indent=2)
    if want == "html":
        return rec.get("html") or ""
    if want == "text":
        return rec.get("text") or rec.get("markdown") or ""
    return rec.get("markdown") or ""


def print_stats(stats, results, budget, elapsed):
    n = len(results)
    ok = sum(1 for p in results.values() if p.verdict == "ok")
    cache = sum(1 for p in results.values() if p.cache_hit)
    spend = sum(p.cost_usd for p in results.values())
    parts = [f"{ok}/{n} ok", f"{cache} from cache"]
    for tier, tried, okc, usd, secs in stats:
        parts.append(f"{tier} {okc}/{tried}" + (f" ${usd:.4f}" if usd else "") + f" {secs}s")
    rate = f"{(n / elapsed):.1f} pages/s" if elapsed > 0 else ""
    log(f"summary: {' | '.join(parts)} | spend ${spend:.4f}" + (f" of ${budget.limit:.2f}" if budget.limit else "") + f" | {elapsed:.1f}s {rate}")
    fails = defaultdict(int)
    for p in results.values():
        if p.verdict != "ok":
            fails[p.verdict] += 1
    if fails:
        log("unresolved: " + ", ".join(f"{k}×{v}" for k, v in sorted(fails.items(), key=lambda kv: -kv[1])))


# ----------------------------------------------------------------------------- discovery

def _local(tag):
    return tag.split("}")[-1].lower()


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f%z", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            d = datetime.strptime(s[:len(s)], fmt)
            return d.timestamp() if d.tzinfo else d.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc).timestamp()
    return None


def _xml_items(root):
    for el in root:
        loc = lastmod = None
        for c in el:
            n = _local(c.tag)
            if n == "loc":
                loc = (c.text or "").strip()
            elif n == "lastmod":
                lastmod = (c.text or "").strip()
        if loc:
            yield loc, lastmod


def _feed_items(root):
    tag = _local(root.tag)
    if tag == "rss":
        ch = next((c for c in root if _local(c.tag) == "channel"), None)
        for it in (ch or []):
            if _local(it.tag) != "item":
                continue
            link = date = None
            for c in it:
                n = _local(c.tag)
                if n == "link":
                    link = (c.text or "").strip()
                elif n in ("pubdate", "date", "updated"):
                    date = (c.text or "").strip()
            if link:
                yield link, date
    elif tag == "feed":
        for e in root:
            if _local(e.tag) != "entry":
                continue
            link = date = None
            for c in e:
                n = _local(c.tag)
                if n == "link" and (c.attrib.get("rel") in (None, "alternate")):
                    link = c.attrib.get("href")
                elif n in ("updated", "published"):
                    date = (c.text or "").strip()
            if link:
                yield link, date


def cc_urls(host, limit=2000):
    info = fetch_text("https://index.commoncrawl.org/collinfo.json", timeout=30)
    if not info:
        return [], "Common Crawl index unreachable (it is often slow or rate-limited; retry later)"
    try:
        latest = json.loads(info)[0]["id"]
    except Exception:
        return [], "could not read collinfo.json"
    q = (f"https://index.commoncrawl.org/{latest}-index?url={quote(host + '/*', safe='/*')}&output=json"
         f"&filter=status:200&fl=url,timestamp&limit={int(limit)}")
    txt = fetch_text(q, timeout=90)
    if not txt:
        return [], f"no results from {latest} index"
    out = []
    for line in txt.splitlines():
        try:
            d = json.loads(line)
            out.append((d.get("url"), d.get("timestamp")))
        except Exception:
            continue
    return out, latest


def discover(target, pattern=None, since=None, limit=0, use_cc=False, feeds=False):
    url = normalize_url(target)
    if not url:
        raise SystemExit(f"bad target: {target}")
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    found = {}
    robots = fetch_text(base + "/robots.txt", timeout=12) or ""
    sitemaps = [l.split(":", 1)[1].strip() for l in robots.splitlines() if l.strip().lower().startswith("sitemap:")]
    if not sitemaps:
        sitemaps = [base + s for s in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/sitemap/sitemap.xml", "/wp-sitemap.xml", "/sitemap.txt")]
    queue = list(dict.fromkeys(sitemaps))
    seen, fetched = set(), 0
    cap = max(limit, 0) * 5 if limit else 0
    since_ts = _parse_date(since) if since else None
    while queue and fetched < 300:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        data = fetch_text(sm, timeout=40, binary=True)
        if not data:
            continue
        fetched += 1
        if sm.endswith(".gz") or data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except Exception:
                continue
        text = data.decode("utf-8", "replace").strip()
        if text.startswith("<"):
            try:
                root = ET.fromstring(text.encode("utf-8"))
            except ET.ParseError:
                continue
            tag = _local(root.tag)
            if tag == "sitemapindex":
                subs = [(loc, lm) for loc, lm in _xml_items(root)]
                subs.sort(key=lambda x: (_parse_date(x[1]) or 0), reverse=True)
                for loc, lm in subs:
                    if since_ts and lm and (_parse_date(lm) or 0) < since_ts:
                        continue
                    queue.append(loc)
            elif tag == "urlset":
                for loc, lm in _xml_items(root):
                    found.setdefault(loc, {"lastmod": lm, "source": "sitemap"})
            elif tag in ("rss", "feed"):
                for link, d in _feed_items(root):
                    found.setdefault(link, {"lastmod": d, "source": "feed"})
        else:
            for line in text.splitlines():
                if line.strip().startswith("http"):
                    found.setdefault(line.strip(), {"lastmod": None, "source": "sitemap.txt"})
        if cap and len(found) >= cap:
            break
    log(f"discover: {fetched} sitemap/feed file(s) → {len(found)} url(s)", "debug")
    if feeds:
        home = fetch_text(base + "/", timeout=20) or ""
        _, links = _meta(home)
        cands = [urljoin(base + "/", l) for l in links] + [base + s for s in ("/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/index.xml")]
        for f in dict.fromkeys(cands):
            data = fetch_text(f, timeout=20)
            if not data or not data.strip().startswith("<"):
                continue
            try:
                root = ET.fromstring(data.encode("utf-8"))
            except ET.ParseError:
                continue
            for link, d in _feed_items(root):
                found.setdefault(link, {"lastmod": d, "source": "feed"})
    if use_cc:
        items, note = cc_urls(p.netloc, limit=max(limit, 500) if limit else 2000)
        log(f"common crawl: {len(items)} url(s) ({note})")
        for u, ts in items:
            if u:
                found.setdefault(u, {"lastmod": ts, "source": "commoncrawl"})
    items = []
    for u, meta in found.items():
        if pattern and not fnmatch.fnmatch(u, pattern):
            continue
        if since_ts and meta.get("lastmod"):
            lm = _parse_date(meta["lastmod"])
            if lm and lm < since_ts:
                continue
        items.append({"url": u, **meta})
    items.sort(key=lambda it: (_parse_date(it.get("lastmod") or "") or 0), reverse=True)
    if limit:
        items = items[:limit]
    return items


# ----------------------------------------------------------------------------- commands

def _write_out(text, path):
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        log(f"wrote {len(text)} chars → {path}")
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def cmd_fetch(a):
    url = normalize_url(a.url)
    if not url:
        raise SystemExit(f"bad url: {a.url}")
    opts = Opts(a)
    ledger = Ledger()
    budget = Budget(opts.budget)
    t0 = time.time()
    results, stats = escalate([url], opts, ledger, budget)
    p = results[url]
    print_stats(stats, results, budget, time.time() - t0)
    rec = build_record(p, opts)
    if p.verdict != "ok":
        hint = ""
        if p.verdict.startswith("blocked:") and budget.limit <= 0:
            hint = " — paid tiers are off; rerun with --budget 0.05 to allow the API tier"
        elif p.verdict in ("js_required", "empty") and not browser_engine():
            hint = " — no local browser engine; run setup.sh browser (or allow --budget for API JS rendering)"
        log(f"FAILED {url}: {p.verdict}{hint}")
        print(json.dumps(rec, indent=2), file=sys.stderr)
        sys.exit(2)
    _write_out(render_single(rec, opts.want), a.out)


def load_urls(a):
    urls = []
    fd = getattr(a, "from_discover", None)
    if fd:
        items = discover(fd, pattern=getattr(a, "pattern", None), since=getattr(a, "since", None),
                         limit=getattr(a, "limit", 0) or 0, use_cc=getattr(a, "cc", False), feeds=getattr(a, "feeds", False))
        urls += [it["url"] for it in items]
        log(f"discover {fd}: {len(items)} url(s)")
    src = getattr(a, "source", None)
    if src:
        if src == "-":
            lines = sys.stdin.read().splitlines()
        elif src.endswith(".jsonl"):
            lines = []
            with open(src, "r", encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        try:
                            lines.append(json.loads(l).get("url"))
                        except Exception:
                            pass
        elif src.endswith(".csv"):
            import csv
            lines = []
            with open(src, newline="", encoding="utf-8-sig") as f:
                rd = csv.reader(f)
                header = next(rd, [])
                idx = next((i for i, h in enumerate(header) if h.strip().lower() in ("url", "link", "website")), 0)
                if header and re.match(r"^https?://", header[idx] or ""):
                    lines.append(header[idx])
                for row in rd:
                    if len(row) > idx:
                        lines.append(row[idx])
        else:
            with open(src, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        urls += lines
    seen, out = set(), []
    for u in urls:
        n = normalize_url(u) if u else None
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def read_done(path):
    done = set()
    if not path or not os.path.exists(path):
        return done
    with open(path, "r", encoding="utf-8") as f:
        for l in f:
            try:
                rec = json.loads(l)
                if rec.get("verdict") == "ok":
                    done.add(rec.get("url"))
            except Exception:
                continue
    return done


def run_batch(urls, opts, out_path, resume=True):
    ledger = Ledger()
    budget = Budget(opts.budget)
    done = read_done(out_path) if (resume and out_path and not opts.refresh) else set()
    todo = [u for u in urls if u not in done]
    if done:
        log(f"resume: {len(done)} already ok in {out_path}, {len(todo)} to do")
    t0 = time.time()
    results, stats = escalate(todo, opts, ledger, budget) if todo else ({}, [])
    elapsed = time.time() - t0
    out_f = open(out_path, "a", encoding="utf-8") if out_path else sys.stdout
    written = 0
    failed = []
    for u in todo:
        p = results.get(u) or Page(url=u, verdict="missing")
        rec = build_record(p, opts)
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written += 1
        if p.verdict != "ok":
            failed.append(f"{u}\t{p.verdict}")
    if out_path:
        out_f.close()
    if failed and out_path:
        fp = out_path + ".failed.txt"
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(failed) + "\n")
        log(f"{len(failed)} unresolved → {fp}")
    if todo:
        print_stats(stats, results, budget, elapsed)
    log(f"wrote {written} record(s)" + (f" → {out_path}" if out_path else ""))
    return results, stats


def cmd_batch(a):
    opts = Opts(a)
    urls = load_urls(a)
    if not urls:
        raise SystemExit("no urls (give a file, '-' for stdin, or --from-discover DOMAIN)")
    log(f"batch: {len(urls)} url(s) | want={opts.want} | budget=${opts.budget:.2f} | tiers ≤ {opts.max_tier}")
    run_batch(urls, opts, a.out, resume=not a.no_resume)


def cmd_discover(a):
    items = discover(a.target, pattern=a.pattern, since=a.since, limit=a.limit or 0, use_cc=a.cc, feeds=a.feeds)
    if a.tsv:
        text = "\n".join(f"{it['url']}\t{it.get('lastmod') or ''}\t{it.get('source')}" for it in items)
    elif a.json:
        text = json.dumps(items, indent=2)
    else:
        text = "\n".join(it["url"] for it in items)
    log(f"discover: {len(items)} url(s)")
    _write_out(text + ("\n" if text else ""), a.out)


def cmd_probe(a):
    url = normalize_url(a.url)
    if not url:
        raise SystemExit("bad url")
    a.want = "html"
    opts = Opts(a)
    opts.respect_robots = False
    report = {"url": url, "robots_allowed": robots_ok(url), "checked_at": iso()}
    p = asyncio.run(direct_many([url], opts, None))[url]
    cookies = re.findall(r"(?:^|,\s*)([A-Za-z0-9_\-\.]+)=", p.headers.get("set-cookie", "") or "")
    report["direct"] = {"status": p.status, "verdict": p.verdict, "ms": p.elapsed_ms, "bytes": len(p.body),
                        "content_type": p.content_type, "server": p.headers.get("server"), "cf_ray": bool(p.headers.get("cf-ray")),
                        "vendor": vendor_of(p), "cookies": sorted(set(cookies))[:12], "final_url": p.final_url, "notes": p.notes}
    if p.text and p.is_html:
        vt = visible_text(p.text)
        report["visible_text_chars"] = len(vt)
        report["js_shell"] = looks_js_shell(p.text)
        s = extract_structured(p.text, url)
        types = []
        for o in s["jsonld"]:
            if isinstance(o, dict):
                t = o.get("@type")
                types.append(t if isinstance(t, str) else json.dumps(t))
        report["hidden_data"] = {"jsonld": len(s["jsonld"]), "jsonld_types": sorted(set(types))[:10], "next_data": s["next_data"] is not None,
                                 "state_json": list(s["state"].keys()), "present_unparsed": s["state_present"], "feeds": s["feeds"][:5],
                                 "canonical": s["meta"].get("canonical"), "generator": s["meta"].get("generator")}
    st, hdrs, _ = fetch_head(url, accept_md=True)
    report["markdown_negotiation"] = {"available": (hdrs.get("content-type") or "").startswith("text/markdown"),
                                      "x_markdown_tokens": hdrs.get("x-markdown-tokens"), "content_signal": hdrs.get("content-signal")}
    o = urlparse(url)
    base = f"{o.scheme}://{o.netloc}"
    caps = {}
    for path, name in (("/sitemap.xml", "sitemap"), ("/wp-json/wp/v2/posts?per_page=1", "wordpress_rest_api"),
                       ("/products.json?limit=1", "shopify_products_json"), ("/feed", "rss_feed")):
        st2, h2, body2 = fetch_head(base + path, timeout=10)
        ct2 = (h2.get("content-type") or "").lower()
        okc = st2 == 200 and (("xml" in ct2 or "json" in ct2 or "rss" in ct2) or body2.lstrip().startswith(("<?xml", "[", "{")))
        caps[name] = {"status": st2, "usable": bool(okc), "content_type": ct2[:40]}
    report["endpoints"] = caps
    if a.deep:
        r = None
        if browser_engine():
            r = asyncio.run(render_many([url], opts))[url]
        elif not opts.no_jina:
            r = asyncio.run(jina_many([url], opts))[url]
        if r:
            rendered = len(visible_text(r.text)) if r.is_html else len(r.text)
            report["rendered"] = {"tier": r.tier, "verdict": r.verdict, "ms": r.elapsed_ms, "visible_text_chars": rendered,
                                  "js_adds_chars": rendered - report.get("visible_text_chars", 0)}
    report["recommendation"] = recommend(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def recommend(rep):
    d = rep["direct"]
    v = d["verdict"]
    hd = rep.get("hidden_data") or {}
    caps = rep.get("endpoints") or {}
    tips = []
    if caps.get("wordpress_rest_api", {}).get("usable"):
        tips.append("WordPress REST API answers at /wp-json/wp/v2/posts — fetch JSON pages directly (fastest, free, no HTML parsing).")
    if caps.get("shopify_products_json", {}).get("usable"):
        tips.append("Shopify /products.json is open — paginate ?limit=250&page=N for the whole catalog as JSON.")
    if hd.get("next_data"):
        tips.append("__NEXT_DATA__ is embedded — read structured.next_data.props.pageProps instead of parsing HTML.")
    if hd.get("jsonld"):
        tips.append(f"JSON-LD present ({', '.join(hd.get('jsonld_types') or [])[:80]}) — read structured.jsonld; no LLM needed for those fields.")
    if hd.get("state_json"):
        tips.append(f"hydration state JSON present: {', '.join(hd['state_json'])}.")
    if rep.get("markdown_negotiation", {}).get("available"):
        tips.append("Cloudflare Markdown for Agents works here — `--want md` gets edge-converted markdown, no HTML parsing.")
    if caps.get("sitemap", {}).get("usable"):
        tips.append("sitemap.xml exists — `discover` gives the URL list with lastmod for free.")
    if v == "ok" and not rep.get("js_shell"):
        tier, est, why = "direct", "$0", "static HTML fetch works"
    elif v in ("js_required",) or rep.get("js_shell"):
        tier, est, why = "browser (local) → jina (free) → api standard+JS", "$0 local / $0.75 per 1K on Decodo", "page is a JS shell; needs rendering"
    elif v.startswith("blocked:"):
        vendor = v.split(":", 1)[1]
        if vendor in HARD_VENDORS:
            tier, est, why = "api premium+JS (Decodo) — skip local tiers", "$1.50 per 1K (≈$1.20 at $99 plan)", f"{vendor} blocks TLS-impersonated and headless clients; only unblocker APIs pass reliably"
        elif vendor == "cloudflare":
            tier, est, why = "browser:stealth (scrapling+Camoufox) locally → api premium", "$0 local / $1.00–1.50 per 1K", "Cloudflare challenge; Camoufox solves Turnstile locally, API otherwise"
        else:
            tier, est, why = "proxy → api standard", "≈$0.3–1.9 per 1K by bandwidth / $0.50 per 1K", "IP-level block; a residential exit usually clears it"
    elif v == "rate_limited":
        tier, est, why = "direct with --host-interval 2 --per-host 1, then proxy", "$0 / bandwidth", "429: slow down before paying"
    elif v == "not_found":
        tier, est, why = "none", "$0", "404 — check the URL"
    elif v.startswith("error:"):
        tier, est, why = "direct (retry) → proxy → api", "$0 → $0.50 per 1K", v
    else:
        tier, est, why = "direct", "$0", v
    return {"tier": tier, "est_cost": est, "why": why, "tips": tips}


def cmd_select(a):
    if not a.schema:
        raise SystemExit("--schema schema.json required (make one with llm_extract.py schema, or by hand — see assets/schema.example.json)")
    with open(a.schema, "r", encoding="utf-8") as f:
        schema = json.load(f)
    target = a.target
    if os.path.exists(target):
        html = open(target, "r", encoding="utf-8", errors="replace").read()
        base = a.base_url or ""
    else:
        url = normalize_url(target)
        a.want = "html"
        opts = Opts(a)
        results, stats = escalate([url], opts, Ledger(), Budget(opts.budget))
        p = results[url]
        if p.verdict != "ok":
            raise SystemExit(f"fetch failed: {p.verdict} {p.notes}")
        html, base = p.text, p.final_url or url
    rows = run_schema(html, schema, base)
    if a.csv:
        import csv
        buf = io.StringIO()
        keys = list(rows[0].keys()) if rows else []
        w = csv.DictWriter(buf, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
        text = buf.getvalue()
    else:
        text = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    log(f"select: {len(rows)} row(s)")
    _write_out(text, a.out)


def cmd_cost(a):
    if a.sheet or not a.tier:
        print(f"{'tier / provider':44} {'USD':>8}  unit      note   (verified 2026-09; see references/cost-model.md)")
        for name, usd, unit, note in SHEET:
            print(f"{name:44} {usd:8.3f}  {unit:9} {note}")
        if not a.tier:
            return
    n = a.pages
    kb = a.page_kb
    t = a.tier
    per_page = {
        "direct": 0.0, "cache": 0.0, "browser": 0.0, "jina": 0.0,
        "proxy-residential": kb * 1024 / 1e9 * PRICES["proxy_usd_per_gb"],
        "proxy-datacenter": kb * 1024 / 1e9 * 0.60,
        "decodo-standard": PRICES["decodo"]["standard"], "decodo-standard-js": PRICES["decodo"]["standard_js"],
        "decodo-premium": PRICES["decodo"]["premium"], "decodo-premium-js": PRICES["decodo"]["premium_js"],
        "decodo-unblocker": 0.00125, "zyte-http": 0.00013, "zyte-browser": 0.001, "brightdata-unlocker": 0.0015,
        "scraperapi": 0.00029, "scrapedo": 0.00012, "firecrawl": 0.00099, "spider": 0.0001,
        "llm-haiku": 0.008, "llm-haiku-batch": 0.004, "llm-sonnet": 0.015, "llm-sonnet-batch": 0.0075,
    }
    if t not in per_page:
        raise SystemExit("unknown tier; one of: " + ", ".join(per_page))
    total = per_page[t] * n
    print(json.dumps({"tier": t, "pages": n, "usd_per_page": round(per_page[t], 6), "usd_total": round(total, 4),
                      "page_kb_assumed": kb if t.startswith("proxy") else None}, indent=2))


def cmd_ledger(a):
    L = Ledger()
    if a.clear_host:
        L.clear_floor(a.clear_host)
        log(f"cleared floor for {a.clear_host}")
    if a.purge_days:
        n = L.purge(a.purge_days)
        log(f"purged {n} page(s) older than {a.purge_days} days")
    if a.host:
        rows = [dict(r) for r in L.con.execute("SELECT url, fetched_at, status, tier, verdict, cost_usd FROM pages WHERE host=? ORDER BY fetched_at DESC LIMIT 50", (a.host,))]
        for r in rows:
            r["fetched_at"] = iso(r["fetched_at"])
        print(json.dumps({"host": a.host, "floor": L.floor(a.host), "recent": rows}, indent=2))
        return
    s = L.stats()
    for h in s["host_floors"]:
        h["updated_at"] = iso(h["updated_at"])
    print(json.dumps(s, indent=2))


def cmd_job(a):
    with open(a.job, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    name = cfg.get("name", os.path.basename(a.job))
    b = cfg.get("batch", {})
    ns = argparse.Namespace(want=b.get("want", "json"), need=b.get("need"), js=b.get("js", False),
                            budget=(a.budget if a.budget is not None else b.get("budget", 0)),
                            concurrency=b.get("concurrency", 16), per_host=b.get("per_host", 4), host_interval=b.get("host_interval", 0.25),
                            timeout=b.get("timeout", 25), ttl=b.get("ttl", 86400), refresh=b.get("refresh", False),
                            ignore_robots=b.get("ignore_robots", False), no_jina=b.get("no_jina", False), md_mode=b.get("md_mode", "clean"),
                            links=b.get("links", False), max_tier=b.get("max_tier", "api"), min_tier=b.get("min_tier", "cache"),
                            geo=b.get("geo"), locale=b.get("locale"), api_pool=b.get("api_pool", "standard"), api_rps=b.get("api_rps", 5),
                            header=b.get("headers", []), cookie=b.get("cookie"), schema=cfg.get("select_schema"), dump_dir=cfg.get("dump_dir"),
                            browser_concurrency=b.get("browser_concurrency", 4), wait_ms=b.get("wait_ms", 0))
    opts = Opts(ns)
    urls = [normalize_url(u) for u in cfg.get("seeds", []) if normalize_url(u)]
    d = cfg.get("discover")
    if d and d.get("domain"):
        items = discover(d["domain"], pattern=d.get("pattern"), since=d.get("since"), limit=d.get("limit", 0) or 0, use_cc=d.get("cc", False), feeds=d.get("feeds", False))
        urls += [it["url"] for it in items]
        log(f"[{name}] discover {d['domain']}: {len(items)} url(s)")
    urls = list(dict.fromkeys(urls))
    out = cfg.get("out") or f"out/{name}.jsonl"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    log(f"[{name}] {len(urls)} url(s) → {out} | budget ${opts.budget:.2f}")
    if not urls:
        raise SystemExit("job has no urls")
    results, stats = run_batch(urls, opts, out, resume=not cfg.get("no_resume", False))
    ex = cfg.get("extract")
    if ex:
        here = os.path.dirname(os.path.abspath(__file__))
        cmd = [sys.executable, os.path.join(here, "llm_extract.py"), "extract", "--in", out, "--out", ex.get("out") or out.replace(".jsonl", ".extracted.jsonl")]
        if ex.get("fields"):
            cmd += ["--fields", ex["fields"]]
        if ex.get("schema"):
            cmd += ["--schema", ex["schema"]]
        if ex.get("model"):
            cmd += ["--model", ex["model"]]
        if ex.get("batch"):
            cmd += ["--batch"]
        if ex.get("max_usd"):
            cmd += ["--max-usd", str(ex["max_usd"])]
        log(f"[{name}] extract: {' '.join(cmd[2:])}")
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            raise SystemExit(f"extract step failed (exit {rc})")
    ok = sum(1 for p in results.values() if p.verdict == "ok")
    log(f"[{name}] done: {ok}/{len(results)} ok")


# ----------------------------------------------------------------------------- cli

def add_fetch_flags(p, batch=False):
    p.add_argument("--want", choices=["md", "json", "html", "text"], default="json" if batch else "md",
                   help="output shape (batch default json → JSONL records; fetch default md)")
    p.add_argument("--need", help="CSS selector that must be present, else the page counts as JS-required and escalates")
    p.add_argument("--js", action="store_true", help="page needs JavaScript: start at the render tiers")
    p.add_argument("--budget", type=float, default=None, help="USD allowed for paid tiers this run (default 0 = paid tiers OFF)")
    p.add_argument("--max-tier", choices=TIER_ORDER, default="api", help="never escalate past this tier")
    p.add_argument("--min-tier", choices=TIER_ORDER, default="cache", help="start here (e.g. api for known-hard hosts)")
    p.add_argument("--try-all", action="store_true", help="ignore learned per-host floors")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--per-host", type=int, default=4, help="max parallel requests per host")
    p.add_argument("--host-interval", type=float, default=0.25, help="seconds between requests to the same host")
    p.add_argument("--timeout", type=int, default=25)
    p.add_argument("--ttl", type=int, default=86400, help="serve from cache if fetched within this many seconds")
    p.add_argument("--refresh", action="store_true", help="ignore cache and conditional headers")
    p.add_argument("--ignore-robots", action="store_true", help="do not consult robots.txt (only with the site owner's permission)")
    p.add_argument("--no-jina", action="store_true", help="never send URLs to r.jina.ai (third party)")
    p.add_argument("--no-md-negotiation", action="store_true", help="do not ask Cloudflare for text/markdown")
    p.add_argument("--md-mode", choices=["clean", "full"], default="clean", help="clean = main content (trafilatura); full = whole page")
    p.add_argument("--include-html", action="store_true")
    p.add_argument("--links", action="store_true", help="include outgoing links in json records")
    p.add_argument("--no-structured", action="store_true", help="skip JSON-LD/__NEXT_DATA__/meta extraction in json records")
    p.add_argument("--schema", help="CSS schema JSON to run on each page (adds `rows`)")
    p.add_argument("--dump-dir", help="also write one .md/.html per page here")
    p.add_argument("--browser-concurrency", type=int, default=4)
    p.add_argument("--keep-assets", action="store_true", help="browser tier: do not block images/fonts/css")
    p.add_argument("--wait-until", choices=["domcontentloaded", "load", "networkidle"], default="domcontentloaded")
    p.add_argument("--wait-ms", type=int, default=0, help="browser tier: extra wait after load")
    p.add_argument("--geo", help="country for API/proxy exits, e.g. 'United States' or 'us'")
    p.add_argument("--locale")
    p.add_argument("--session", help="sticky proxy/API session id")
    p.add_argument("--api-pool", choices=["standard", "premium"], default="standard")
    p.add_argument("--api-rps", type=float, default=5, help="Decodo API requests/second (free plan 10, $49 plan 25, $99 plan 50)")
    p.add_argument("--api-html", action="store_true", help="ask the API for HTML even when --want md")
    p.add_argument("--header", action="append", help="extra request header 'Name: value' (repeatable)")
    p.add_argument("--cookie", help="Cookie header value (e.g. consent cookies)")
    p.add_argument("--proxy", help="proxy URL for the proxy tier (overrides env)")


def main():
    global QUIET, VERBOSE
    ap = argparse.ArgumentParser(prog="ladder.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-q", "--quiet", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"scrape-ladder {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="fetch one URL through the ladder")
    f.add_argument("url")
    f.add_argument("--out")
    add_fetch_flags(f)

    b = sub.add_parser("batch", help="fetch many URLs (file, '-' stdin, or --from-discover) → JSONL")
    b.add_argument("source", nargs="?", help="urls.txt | urls.csv | prior.jsonl | -")
    b.add_argument("--from-discover", metavar="DOMAIN", help="seed from sitemaps of DOMAIN")
    b.add_argument("--pattern", help="glob on full URL for --from-discover, e.g. '*/blog/*'")
    b.add_argument("--since", help="YYYY-MM-DD lastmod floor for --from-discover")
    b.add_argument("--limit", type=int, default=0)
    b.add_argument("--cc", action="store_true", help="also seed from the Common Crawl index")
    b.add_argument("--feeds", action="store_true", help="also seed from RSS/Atom feeds")
    b.add_argument("--out", help="JSONL path (append; resumable). Default stdout")
    b.add_argument("--no-resume", action="store_true")
    add_fetch_flags(b, batch=True)

    d = sub.add_parser("discover", help="list URLs from sitemaps / feeds / Common Crawl (free)")
    d.add_argument("target")
    d.add_argument("--pattern")
    d.add_argument("--since")
    d.add_argument("--limit", type=int, default=0)
    d.add_argument("--cc", action="store_true")
    d.add_argument("--feeds", action="store_true")
    d.add_argument("--tsv", action="store_true", help="url<TAB>lastmod<TAB>source")
    d.add_argument("--json", action="store_true")
    d.add_argument("--out")

    pr = sub.add_parser("probe", help="diagnose a URL: protection, JS need, hidden JSON, est. cost")
    pr.add_argument("url")
    pr.add_argument("--deep", action="store_true", help="also render (browser or jina) to measure what JS adds")
    add_fetch_flags(pr)

    se = sub.add_parser("select", help="run a CSS schema on a URL or HTML file → JSON/CSV rows (no LLM)")
    se.add_argument("target", help="URL or local .html")
    se.add_argument("--base-url", help="for local files: base for absolute links")
    se.add_argument("--csv", action="store_true")
    se.add_argument("--out")
    add_fetch_flags(se)

    j = sub.add_parser("job", help="run a JSON job file end to end (for cron / GitHub Actions / launchd)")
    j.add_argument("job")
    j.add_argument("--budget", type=float, default=None, help="override the job's budget")

    c = sub.add_parser("cost", help="price sheet and calculator")
    c.add_argument("--sheet", action="store_true")
    c.add_argument("--pages", type=int, default=1000)
    c.add_argument("--tier")
    c.add_argument("--page-kb", type=int, default=500, help="avg page size for bandwidth-priced tiers")

    l = sub.add_parser("ledger", help="cache/spend stats and per-host memory")
    l.add_argument("--host")
    l.add_argument("--clear-host")
    l.add_argument("--purge-days", type=int, default=0)

    a = ap.parse_args()
    QUIET, VERBOSE = a.quiet, a.verbose
    {"fetch": cmd_fetch, "batch": cmd_batch, "discover": cmd_discover, "probe": cmd_probe, "select": cmd_select,
     "job": cmd_job, "cost": cmd_cost, "ledger": cmd_ledger}[a.cmd](a)


if __name__ == "__main__":
    main()
