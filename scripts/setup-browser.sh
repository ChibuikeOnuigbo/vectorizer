#!/usr/bin/env bash
# Idempotent browser setup for QA.
#
# This sandbox blocks Google's browser CDNs (storage.googleapis.com,
# cdn.playwright.dev) and the system package mirrors, so the Playwright
# browser download fails. Instead we use the Chromium bundled inside the
# @sparticuz/chromium npm package (fetched from the npm registry, which is
# reachable): it ships chrome-headless-shell plus the shared libraries it
# needs (libnss3 & friends) and runs fine with LD_LIBRARY_PATH.
#
# Result: a real headless Chromium driven over CDP by Playwright
# (chromium.connectOverCDP).
set -e
cd "$(dirname "$0")/.."
QA_DIR=qa
mkdir -p "$QA_DIR"
cd "$QA_DIR"

# 1) npm deps (playwright + bundled chromium)
if [ ! -d node_modules/@sparticuz/chromium ] || [ ! -d node_modules/playwright ]; then
  npm install --no-fund --no-audit @sparticuz/chromium playwright
fi

# 2) expand bundled chromium + libraries into /tmp (skip if already there)
if [ ! -x /tmp/chromium ] || [ ! -e /tmp/al2023/lib/libnss3.so ]; then
  node - <<'EOF'
const fs = require("fs");
const zlib = require("zlib");
const { execSync } = require("child_process");
const bin = "node_modules/@sparticuz/chromium/bin";
// chrome-headless-shell
const chrome = zlib.brotliDecompressSync(fs.readFileSync(`${bin}/chromium.br`));
fs.mkdirSync("/tmp", { recursive: true });
fs.writeFileSync("/tmp/chromium", chrome);
fs.chmodSync("/tmp/chromium", 0o755);
// NSS + expat shared libs
fs.mkdirSync("/tmp/al2023", { recursive: true });
fs.writeFileSync("/tmp/al2023.tar", zlib.brotliDecompressSync(fs.readFileSync(`${bin}/al2023.tar.br`)));
execSync("tar -xf /tmp/al2023.tar -C /tmp/al2023");
// fonts (better text rendering)
fs.writeFileSync("/tmp/fonts.tar", zlib.brotliDecompressSync(fs.readFileSync(`${bin}/fonts.tar.br`)));
execSync("mkdir -p /tmp/fonts && tar -xf /tmp/fonts.tar -C /tmp/fonts");
console.log("browser expanded");
EOF
fi

# 3) make sure the browser is up on :9222 (reuse if already running)
if ! curl -sf http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  nohup env LD_LIBRARY_PATH=/tmp/al2023/lib /tmp/chromium \
    --no-sandbox --disable-gpu --headless \
    --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
    --user-data-dir=/tmp/chrome-profile \
    --no-first-run --no-default-browser-check \
    about:blank >/tmp/chrome.log 2>&1 &
  for i in $(seq 1 30); do
    sleep 1
    if curl -sf http://127.0.0.1:9222/json/version >/dev/null 2>&1; then break; fi
  done
fi
curl -sf http://127.0.0.1:9222/json/version | head -3
echo "QA browser ready on :9222"
