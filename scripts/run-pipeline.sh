#!/bin/zsh
# Nightly pipeline: discover Naukri jobs + score them.
# Invoked by launchd via ~/Library/LaunchAgents/in.tapza.jobhunt.plist
#
# Tune the keywords/locations here — this is your single dial.

set -euo pipefail

PROJECT_DIR="$HOME/Documents/job-hunt"
LOG_DIR="$PROJECT_DIR/data/logs"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"

# Make sure uv is on PATH (launchd uses a stripped env)
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

cd "$PROJECT_DIR"

{
    echo "=== Run started: $(date) ==="

    # Add or edit (keyword, location) pairs. One pair per line.
    while IFS=$'\t' read -r kw loc; do
        echo "--- discover-naukri: $kw @ $loc ---"
        uv run hunt discover-naukri --keyword "$kw" --location "$loc" --pages 2 || true
    done <<EOF
nestjs backend	bangalore
node js backend	hyderabad
java spring boot	bangalore
python backend	remote
EOF

    echo "--- score ---"
    uv run hunt score || true

    echo "--- top 10 ---"
    uv run hunt top --min-score 70 --limit 10 || true

    echo "=== Run finished: $(date) ==="
} >> "$LOG_FILE" 2>&1
