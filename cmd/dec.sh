#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <input-vxl-file> <output-dir>" >&2
  echo "  <input-vxl-file>  VXL-encoded .txt file to decode" >&2
  echo "  <output-dir>      directory where decoded source will be written" >&2
  exit 1
}

[[ $# -lt 2 ]] && usage

INPUT="$1"
OUT_DIR="$2"

# Locate project root (parent of cmd/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "$OUT_DIR"

cd "$PROJECT_ROOT"
python3 -m vxl.decoder "$INPUT" --files -o "$OUT_DIR"

echo "Decoded → $OUT_DIR"
