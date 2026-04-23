#!/bin/bash
# Exit on error, undefined vars, and pipe failures
set -euo pipefail

APP_DIR="$HOME/TacklNest"
APP_FILE="app.py"
# Use the full path to the virtual env's python for stability
PY="$APP_DIR/venv/bin/python3.12"

cd "$APP_DIR"

# 1. Update code
git fetch --all
git reset --hard origin/main

# 2. Ensure virtual environment exists
if [ ! -d "venv" ]; then
    python3.12 -m venv venv
fi

# 3. Update dependencies
$PY -m pip install --upgrade pip
$PY -m pip install -r requirement.txt

# 4. Kill existing process (matching the exact command)
# '|| true' ensures the script doesn't crash if no process is running
pkill -f "$PY $APP_FILE" || true

# 5. Start the app
nohup $PY $APP_FILE > log.txt 2>&1 &

echo "Deployment successful. Tail logs with: tail -n 200 -f $APP_DIR/log.txt"