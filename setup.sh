#!/bin/bash
# One-time setup: system tools, Python environment, and your settings file.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo "rewind needs a Mac with Apple Silicon (Whisper runs on MLX)." >&2
  exit 1
fi

command -v ffmpeg >/dev/null || brew install ffmpeg
command -v espeak-ng >/dev/null || command -v espeak >/dev/null || brew install espeak-ng

python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

[[ -f settings.json ]] || cp settings.example.json settings.json
echo "Done. Edit settings.json for your language, then run /rewind in Claude Code."
