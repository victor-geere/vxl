#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <input-path> <output-dir>" >&2
  echo "  <input-path>  source .ts/.tsx file or directory to encode" >&2
  echo "  <output-dir>  directory where the .txt output will be saved" >&2
  exit 1
}

[[ $# -lt 2 ]] && usage

INPUT="$1"
OUT_DIR="$2"

# Derive output filename: basename of input without extension + .txt
BASENAME="$(basename "$INPUT")"
STEM="${BASENAME%.*}"
# For directories the stem is just the directory name
[[ -d "$INPUT" ]] && STEM="$(basename "$INPUT")"
OUT_FILE="${OUT_DIR%/}/${STEM}.txt"

# Locate project root (parent of cmd/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "$OUT_DIR"

cd "$PROJECT_ROOT"
python3 -m vxl.encoder "$INPUT" -o "$OUT_FILE"

echo "Encoded → $OUT_FILE"
