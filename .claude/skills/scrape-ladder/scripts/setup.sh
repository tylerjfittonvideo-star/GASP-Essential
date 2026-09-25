#!/usr/bin/env bash
# setup.sh — install the scrape-ladder stack. Idempotent. Works on macOS, Linux, and Claude Code cloud sandboxes.
#
#   bash scripts/setup.sh            # core: curl_cffi httpx selectolax lxml trafilatura markdownify   (free tiers: direct, jina, proxy, api)
#   bash scripts/setup.sh browser    # + patchright/playwright (local headless tier). Uses existing Chrome/Chromium when found.
#   bash scripts/setup.sh full       # + scrapling (Cloudflare-solving stealth browser), markitdown (PDF/Office→md), anthropic (LLM extract)
#   bash scripts/setup.sh check      # just report what is available
set -uo pipefail
TIER="${1:-core}"
PY="${PYTHON:-python3}"

pipi() {  # pip install that tolerates PEP 668 "externally managed" systems
  "$PY" -m pip install --quiet --upgrade "$@" 2>/dev/null || "$PY" -m pip install --quiet --upgrade --break-system-packages "$@"
}

if [ "$TIER" != "check" ]; then
  echo "[setup] tier=$TIER python=$("$PY" --version 2>&1)"
  echo "[setup] core: curl_cffi httpx[http2] selectolax lxml trafilatura markdownify"
  pipi curl_cffi "httpx[http2]" selectolax lxml trafilatura markdownify || echo "[setup] core install had errors" >&2
fi

if [ "$TIER" = "browser" ] || [ "$TIER" = "full" ]; then
  echo "[setup] browser: patchright playwright"
  pipi patchright playwright || echo "[setup] browser install had errors" >&2
  # Reuse a browser that is already on the machine; download Chromium only when nothing is found.
  FOUND=""
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "/Applications/Chromium.app/Contents/MacOS/Chromium" \
           "${PLAYWRIGHT_BROWSERS_PATH:-/nonexistent}"/chromium-*/chrome-linux*/chrome "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome \
           "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium /opt/pw-browsers/chromium-*/chrome-linux*/chrome; do
    [ -x "$c" ] && FOUND="$c" && break
  done
  if [ -n "$FOUND" ]; then
    echo "[setup] using existing browser: $FOUND  (export LADDER_BROWSER_PATH to override)"
  elif [ "${PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD:-0}" = "1" ]; then
    echo "[setup] PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 and no browser found — set LADDER_BROWSER_PATH manually" >&2
  else
    echo "[setup] no browser found; downloading Chromium via playwright (≈150 MB, once)"
    "$PY" -m playwright install chromium || echo "[setup] chromium download failed" >&2
  fi
fi

if [ "$TIER" = "full" ]; then
  echo "[setup] full: scrapling markitdown[pdf] anthropic"
  pipi scrapling "markitdown[pdf]" anthropic || echo "[setup] full install had errors" >&2
  # Scrapling's Cloudflare solver needs its Camoufox build (large). Only fetch it when asked.
  if [ "${LADDER_INSTALL_CAMOUFOX:-0}" = "1" ]; then
    "$PY" -m scrapling install 2>/dev/null || scrapling install 2>/dev/null || echo "[setup] scrapling install (camoufox) failed" >&2
  else
    echo "[setup] skipped Camoufox download (set LADDER_INSTALL_CAMOUFOX=1 to enable Cloudflare solving locally)"
  fi
fi

echo "[setup] availability:"
"$PY" - <<'PY'
import importlib.util as iu, os, shutil, glob, sys
def ok(m): return iu.find_spec(m) is not None
rows = [("direct (curl_cffi TLS impersonation)", ok("curl_cffi")), ("direct fallback (httpx)", ok("httpx")),
        ("html parsing (selectolax)", ok("selectolax")), ("markdown (trafilatura)", ok("trafilatura")), ("markdown fallback (markdownify)", ok("markdownify")),
        ("browser engine (patchright)", ok("patchright")), ("browser engine (playwright)", ok("playwright")),
        ("stealth browser (scrapling)", ok("scrapling")), ("files→md (markitdown)", ok("markitdown")), ("LLM extract (anthropic)", ok("anthropic"))]
for name, v in rows: print(f"  {'ok  ' if v else 'MISS'} {name}")
cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"] + glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")) + glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") + glob.glob(os.path.expanduser("~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"))
b = os.environ.get("LADDER_BROWSER_PATH") or next((c for c in cands if os.path.isfile(c)), None) or shutil.which("google-chrome") or shutil.which("chromium")
print(f"  {'ok  ' if b else 'MISS'} browser binary: {b or 'none found (setup.sh browser)'}")
keys = [("DECODO_AUTH_TOKEN or DECODO_USER/PASS", bool(os.environ.get("DECODO_AUTH_TOKEN") or (os.environ.get("DECODO_USER") and os.environ.get("DECODO_PASS")))),
        ("DECODO_PROXY_USER/PASS or LADDER_PROXY_URL", bool(os.environ.get("LADDER_PROXY_URL") or (os.environ.get("DECODO_PROXY_USER") and os.environ.get("DECODO_PROXY_PASS")))),
        ("JINA_API_KEY (optional, raises free tier to 500 rpm)", bool(os.environ.get("JINA_API_KEY"))),
        ("ANTHROPIC_API_KEY (LLM extract only)", bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")))]
for name, v in keys: print(f"  {'set ' if v else '--  '} {name}")
PY
