#!/usr/bin/env bash
# JARVIS v2.0 — Master Setup Script
# Run from the jarvis_v2 directory: bash setup.sh
set -e

JARVIS_APP="$HOME/.jarvis_app"
JARVIS_DATA="$HOME/.jarvis"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════╗"
echo "║     JARVIS v2.0 — Setup          ║"
echo "╚══════════════════════════════════╝"
echo ""

# ── 1. Runtime dirs ───────────────────────────────────────
mkdir -p "$JARVIS_DATA"/{chroma_db,plans,evolved_tools,piper_models}
mkdir -p "$HOME/Pictures/Jarvis"
mkdir -p "$JARVIS_DATA/sandbox"
mkdir -p "$HOME/notes"
echo "[1/9] Runtime directories created."

# ── 2. Python venv ────────────────────────────────────────
python3 -m venv "$JARVIS_APP/venv"
source "$JARVIS_APP/venv/bin/activate"
pip install --quiet --upgrade pip wheel
echo "[2/9] Virtualenv created at $JARVIS_APP/venv"

# ── 3. Python deps ────────────────────────────────────────
pip install --quiet -r "$REPO_DIR/requirements.txt"
echo "[3/9] Python dependencies installed."

# ── 4. Playwright browsers ───────────────────────────────
playwright install chromium --with-deps 2>/dev/null || \
  echo "  [!] Playwright browser install failed — run manually: playwright install chromium"
echo "[4/9] Playwright Chromium installed."

# ── 5. System deps (CachyOS/Arch) ────────────────────────
echo "[5/9] Installing system packages..."
PKGS=(
  grim              # Wayland screenshot
  inotify-tools     # File watcher
  tesseract         # OCR
  espeak-ng         # TTS fallback
  ydotool           # Wayland input simulation
  wl-clipboard      # Wayland clipboard
  libnotify         # Desktop notifications (notify-send)
  imagemagick       # Image resize for screenshots
  pamixer           # Volume control
  brightnessctl     # Brightness control
  networkmanager    # nmcli Wi-Fi control
  bluez-utils       # bluetoothctl
  playerctl         # MPRIS media control
  mpv               # Lightning audio playback
)
MISSING=()
for pkg in "${PKGS[@]}"; do
  if ! command -v "$pkg" &>/dev/null 2>&1 && ! pacman -Q "$pkg" &>/dev/null 2>&1; then
    MISSING+=("$pkg")
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "  Installing: ${MISSING[*]}"
  sudo pacman -S --noconfirm "${MISSING[@]}" 2>/dev/null || \
    echo "  [!] Could not install: ${MISSING[*]} — install manually"
else
  echo "  All system deps already installed."
fi

# ── 6. Piper TTS model ───────────────────────────────────
PIPER_MODEL="en_US-lessac-medium"
PIPER_DIR="$JARVIS_DATA/piper_models"
if [ ! -f "$PIPER_DIR/$PIPER_MODEL.onnx" ]; then
  echo "[6/9] Downloading Piper TTS model ($PIPER_MODEL)..."
  BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/$PIPER_MODEL"
  wget -q -O "$PIPER_DIR/$PIPER_MODEL.onnx"      "$BASE_URL/$PIPER_MODEL.onnx"      || true
  wget -q -O "$PIPER_DIR/$PIPER_MODEL.onnx.json" "$BASE_URL/$PIPER_MODEL.onnx.json" || true
  echo "  Piper model downloaded."
else
  echo "[6/9] Piper model already present."
fi

# ── 7. .env file ─────────────────────────────────────────
ENV_FILE="$JARVIS_DATA/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" << 'EOF'
# JARVIS v2.0 — Environment Secrets
# DO NOT commit this file to git.

# FCC Proxy (required)
FCC_BASE_URL=http://127.0.0.1:8082
FCC_AUTH_TOKEN=freecc

# Telegram Bot (required for bot interface)
TELEGRAM_TOKEN=your_telegram_bot_token_here
ALLOWED_USER_IDS=your_telegram_user_id_here

# Voice
WAKE_WORD=hey jarvis
TTS_ENGINE=piper
PIPER_VOICE=en_US-lessac-medium

# World Model — URLs to monitor (comma-separated)
MONITOR_URLS=https://ntaonline.in/,https://github.com/trending
MONITOR_INTERVAL=1800

# Optional
FCC_DEFAULT_MODEL=nvidia_nim/nvidia/nemotron-3-super-120b-a12b
EOF
  echo "[7/9] Created $ENV_FILE — FILL IN YOUR TOKENS NOW"
else
  echo "[7/9] .env already exists, skipping."
fi

# ── 8. Systemd services ───────────────────────────────────
mkdir -p "$HOME/.config/systemd/user"
VENV_PY="$JARVIS_APP/venv/bin/python3"

# Telegram bot service
cat > "$HOME/.config/systemd/user/jarvis-telegram.service" << EOF
[Unit]
Description=JARVIS Telegram Bot v2
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$JARVIS_DATA/.env
ExecStart=$VENV_PY $REPO_DIR/telegram_bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

# Daemon service
cat > "$HOME/.config/systemd/user/jarvis-daemon.service" << EOF
[Unit]
Description=JARVIS Background Daemon v2
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$JARVIS_DATA/.env
ExecStart=$VENV_PY $REPO_DIR/daemon.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

# Voice assistant service (optional, can also run on-demand)
cat > "$HOME/.config/systemd/user/jarvis-voice.service" << EOF
[Unit]
Description=JARVIS Voice Assistant
After=graphical-session.target sound.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$JARVIS_DATA/.env
ExecStart=$VENV_PY $REPO_DIR/voice_assistant.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
EOF

# HUD server service
cat > "$HOME/.config/systemd/user/jarvis-hud.service" << EOF
[Unit]
Description=JARVIS V2 HUD Server
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$JARVIS_DATA/.env
ExecStart=$VENV_PY $REPO_DIR/gui_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
EOF

# File watcher service
cat > "$HOME/.config/systemd/user/jarvis-file.service" << EOF
[Unit]
Description=JARVIS Notes File Watcher
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$JARVIS_DATA/.env
ExecStart=$VENV_PY $REPO_DIR/file_watcher.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

# Clipboard watcher service
cat > "$HOME/.config/systemd/user/jarvis-clip.service" << EOF
[Unit]
Description=JARVIS Clipboard Watcher
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$JARVIS_DATA/.env
ExecStart=$VENV_PY $REPO_DIR/clip_watcher.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable jarvis-telegram.service jarvis-daemon.service jarvis-hud.service jarvis-file.service jarvis-clip.service
echo "[8/9] Systemd services installed."

# ── 9. Hyprland keybindings hint ─────────────────────────
echo "[9/9] Done!"
echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║           SETUP COMPLETE                  ║"
echo "╚═══════════════════════════════════════════╝"
echo ""
echo "NEXT STEPS:"
echo ""
echo "  1. Edit secrets:"
echo "     nano $JARVIS_DATA/.env"
echo ""
echo "  2. Start services:"
echo "     systemctl --user start jarvis-telegram"
echo "     systemctl --user start jarvis-daemon"
echo "     systemctl --user start jarvis-hud"
echo "     systemctl --user start jarvis-file"
echo "     systemctl --user start jarvis-clip"
echo ""
echo "  3. Check status:"
echo "     journalctl --user -u jarvis-telegram -f"
echo ""
echo "  4. Add to Hyprland config (~/.config/hypr/hyprland.conf):"
echo "     # Voice assistant hotkey"
echo "     bind = SUPER, V, exec, kill -USR1 \$(cat $JARVIS_DATA/voice.pid 2>/dev/null)"
echo "     # Quick Jarvis CLI"
echo "     bind = SUPER, J, exec, \$TERM -e $VENV_PY $REPO_DIR/jarvis_cli.py"
echo ""
echo "  5. CLI usage:"
echo "     $VENV_PY jarvis_cli.py                  # Interactive"
echo "     $VENV_PY jarvis_cli.py 'your task'      # One-shot"
echo "     $VENV_PY jarvis_cli.py --voice           # Voice mode"
echo "     $VENV_PY jarvis_cli.py --morning         # Today's briefing"
echo "     $VENV_PY gui_server.py                   # HUD at http://127.0.0.1:5050"
echo ""
