#!/bin/bash
set -e
cd /home/user/vectorizer
echo "Restoring branch..."
git fetch origin arena/01a0aab7-vectorizer:refs/remotes/origin/arena/01a0aab7-vectorizer 2>&1 | tail -n 2
git reset --hard origin/arena/01a0aab7-vectorizer
echo "Installing vendor..."
python3 -m pip install -r requirements.txt --target vendor --quiet
python3 -m pip install fontawesome-free --target vendor --quiet
cp vendor/fontawesome-free/static/fontawesome_free/js/all.min.js app/static/fontawesome/all.min.js 2>/dev/null || true
mkdir -p app/static/fontawesome/webfonts
cp -r app/static/webfonts/* app/static/fontawesome/webfonts/ 2>/dev/null || true
echo "Starting uvicorn..."
PYTHONPATH=/home/user/vectorizer/vendor python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*"
