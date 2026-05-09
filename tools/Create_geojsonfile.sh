#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/download_mapcounties_geojson.py" \
  --config "$SCRIPT_DIR/config.json" \
  --output "$SCRIPT_DIR/test.geojson" \
  "$@"
