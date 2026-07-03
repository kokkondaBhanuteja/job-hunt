#!/bin/zsh
# Install a launchd agent that runs the nightly pipeline.
#
#   ./scripts/install-schedule.sh           → install + load (runs daily at 02:00)
#   ./scripts/install-schedule.sh uninstall → unload + remove
#
# The plist also runs the pipeline if your Mac was asleep at 02:00, the next time
# it wakes — see RunAtLoad + StartCalendarInterval.

set -euo pipefail

LABEL="in.tapza.jobhunt"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PROJECT_DIR="$HOME/Documents/job-hunt"
BACKEND_DIR="$PROJECT_DIR/backend"
SCRIPT="$BACKEND_DIR/scripts/run-pipeline.sh"

if [[ "${1:-install}" == "uninstall" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "uninstalled $LABEL"
    exit 0
fi

chmod +x "$SCRIPT"
mkdir -p "$(dirname "$PLIST")"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>$LABEL</string>
  <key>ProgramArguments</key> <array><string>/bin/zsh</string><string>$SCRIPT</string></array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>2</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>          <false/>
  <key>StandardOutPath</key>    <string>$BACKEND_DIR/data/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>  <string>$BACKEND_DIR/data/logs/launchd.err.log</string>
  <key>WorkingDirectory</key>   <string>$BACKEND_DIR</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"
echo "installed $LABEL → runs daily at 02:00"
echo "force-run now with:  launchctl start $LABEL"
echo "tail logs:           tail -F $BACKEND_DIR/data/logs/\$(date +%Y-%m-%d).log"
