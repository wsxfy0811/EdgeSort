#!/usr/bin/env bash
set -e

VOICE_DIR="${PICOCLAW_REALTIME_LISTENER_DIR:-/home/elf/.picoclaw/workspace/skills/realtime_voice_listener}"
VOICE_SCRIPT="$VOICE_DIR/start_realtime_listener.sh"
LOG_DIR="$HOME/.picoclaw/logs"
VOICE_LOG="$LOG_DIR/realtime_voice_listener.log"
AGENT_RUNNER="$LOG_DIR/run_picoclaw_agent_terminal.sh"
VOICE_RUNNER="$LOG_DIR/run_realtime_voice_terminal.sh"
LAUNCH_LOG="$LOG_DIR/picovoice_launcher.log"

mkdir -p "$LOG_DIR"

export PICOCLAW_AUDIO_CARD_NAME="${PICOCLAW_AUDIO_CARD_NAME:-rockchipnau8822}"
export PICOCLAW_INPUT_CARD_NAME="${PICOCLAW_INPUT_CARD_NAME:-rockchipnau8822}"
export PICOCLAW_OUTPUT_CARD_NAME="${PICOCLAW_OUTPUT_CARD_NAME:-rockchipnau8822}"
export PICOCLAW_INPUT_SAMPLE_RATE="${PICOCLAW_INPUT_SAMPLE_RATE:-48000}"
export PICOCLAW_OUTPUT_SAMPLE_RATE="${PICOCLAW_OUTPUT_SAMPLE_RATE:-48000}"
export PICOCLAW_INPUT_CHANNEL="${PICOCLAW_INPUT_CHANNEL:-best}"
export PICOCLAW_ASR_THREADS="${PICOCLAW_ASR_THREADS:-2}"
export PICOCLAW_TTS_THREADS="${PICOCLAW_TTS_THREADS:-2}"
export PICOCLAW_ASR_QUEUE_CHUNKS="${PICOCLAW_ASR_QUEUE_CHUNKS:-12}"
export PICOCLAW_ASR_BLOCK_SECONDS="${PICOCLAW_ASR_BLOCK_SECONDS:-0.05}"
export PICOCLAW_OPENCV_THREADS="${PICOCLAW_OPENCV_THREADS:-1}"
export PICOCLAW_DETECT_INTERVAL="${PICOCLAW_DETECT_INTERVAL:-0.06}"

if [ ! -f "$VOICE_SCRIPT" ]; then
  echo "Realtime voice listener script not found: $VOICE_SCRIPT" >&2
  exit 1
fi

picoclaw status >/dev/null

cat > "$VOICE_RUNNER" <<EOF
#!/usr/bin/env bash
set +e
cd "$VOICE_DIR"
echo "[\$(date '+%F %T')] voice terminal opened" >> "$LAUNCH_LOG"
echo "PicoClaw realtime voice listener"
echo "Working directory: $VOICE_DIR"
echo "Close this terminal to stop realtime voice listening."
echo
bash "$VOICE_SCRIPT"
status=\$?
echo "[\$(date '+%F %T')] voice terminal exited with \$status" >> "$LAUNCH_LOG"
exit \$status
EOF
chmod +x "$VOICE_RUNNER"

cat > "$AGENT_RUNNER" <<EOF
#!/usr/bin/env bash
set +e
echo "[\$(date '+%F %T')] agent terminal opened" >> "$LAUNCH_LOG"
echo "PicoClaw Agent terminal"
echo "Close this terminal or press Ctrl+C to exit picoclaw agent."
echo
picoclaw agent
status=\$?
echo "[\$(date '+%F %T')] agent terminal exited with \$status" >> "$LAUNCH_LOG"
exit \$status
EOF
chmod +x "$AGENT_RUNNER"

open_terminal() {
  title="$1"
  runner="$2"

  echo "[$(date '+%F %T')] opening terminal: $title -> $runner" >> "$LAUNCH_LOG"

  if command -v gnome-terminal >/dev/null 2>&1; then
    setsid gnome-terminal -- bash "$runner" >/dev/null 2>>"$LAUNCH_LOG" &
    return 0
  fi

  if command -v x-terminal-emulator >/dev/null 2>&1; then
    setsid x-terminal-emulator -T "$title" -e bash "$runner" >/dev/null 2>>"$LAUNCH_LOG" &
    return 0
  fi

  if command -v xfce4-terminal >/dev/null 2>&1; then
    setsid xfce4-terminal --title="$title" --command="bash '$runner'" >/dev/null 2>>"$LAUNCH_LOG" &
    return 0
  fi

  if command -v konsole >/dev/null 2>&1; then
    setsid konsole --new-tab -p tabtitle="$title" -e bash "$runner" >/dev/null 2>>"$LAUNCH_LOG" &
    return 0
  fi

  echo "[$(date '+%F %T')] no terminal emulator found for: $title" >> "$LAUNCH_LOG"
  return 1
}

echo "[$(date '+%F %T')] launching picovoice" >> "$LAUNCH_LOG"

if ! open_terminal "PicoClaw realtime voice listener" "$VOICE_RUNNER"; then
  echo "No terminal emulator found; running realtime voice listener in background. Log: $VOICE_LOG"
  bash "$VOICE_SCRIPT" > "$VOICE_LOG" 2>&1 &
  VOICE_PID=$!
  trap 'kill "$VOICE_PID" 2>/dev/null || true' EXIT
fi

sleep 0.6

if ! open_terminal "PicoClaw Agent" "$AGENT_RUNNER"; then
  echo "No terminal emulator found; running picoclaw agent in current terminal." >&2
  RUN_AGENT_IN_CURRENT=1
else
  RUN_AGENT_IN_CURRENT=0
fi

if [ "$RUN_AGENT_IN_CURRENT" = "1" ]; then
  picoclaw agent
fi
