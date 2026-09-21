#!/bin/bash
set -e
cd /home/user/vectorizer
# Loop to survive snapshot restores that delete vendor and reset branch
while true; do
  echo "Restoring branch..."
  git fetch origin arena/01a0aab7-vectorizer:refs/remotes/origin/arena/01a0aab7-vectorizer 2>&1 | tail -n 2 || true
  git reset --hard refs/remotes/origin/arena/01a0aab7-vectorizer 2>&1 | tail -n 2 || true
  echo "Installing deps (persistent app/deps + vendor fallback)..."
  mkdir -p app/deps
  python3 -m pip install -r requirements.txt --target app/deps --quiet || true
  python3 -m pip install fontawesome-free --target app/deps --quiet || true
  mkdir -p vendor
  python3 -m pip install -r requirements.txt --target vendor --quiet || true
  python3 -m pip install fontawesome-free --target vendor --quiet || true
  mkdir -p app/static/fontawesome
  cp app/deps/fontawesome-free/static/fontawesome_free/js/all.min.js app/static/fontawesome/all.min.js 2>/dev/null || cp vendor/fontawesome-free/static/fontawesome_free/js/all.min.js app/static/fontawesome/all.min.js 2>/dev/null || true
  mkdir -p app/static/fontawesome/webfonts
  cp -r app/static/webfonts/* app/static/fontawesome/webfonts/ 2>/dev/null || true
  mkdir -p app/static/lucide
  cp qa/node_modules/lucide/dist/umd/lucide.min.js app/static/lucide/lucide.min.js 2>/dev/null || true
  echo "Starting uvicorn on 0.0.0.0:8000..."
  PYTHONPATH=/home/user/vectorizer/app/deps:/home/user/vectorizer/vendor python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*"
  echo "Uvicorn exited, restarting in 2s..."
  sleep 2
done
