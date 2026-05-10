#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/shrink_geojson.py"

if [[ ! -f "$PY_SCRIPT" ]]; then
  echo "Fehler: shrink_geojson.py nicht gefunden: $PY_SCRIPT" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <datei.geojson> [faktor] [--keep-original]"
  echo "Default: faktor=4, Originaldatei wird ersetzt"
  exit 1
fi

INPUT="$1"
FACTOR="4"
REPLACE_ORIGINAL="1"

if [[ $# -ge 2 ]]; then
  case "$2" in
    --keep-original)
      REPLACE_ORIGINAL="0"
      ;;
    *)
      FACTOR="$2"
      ;;
  esac
fi

if [[ $# -ge 3 ]]; then
  if [[ "$3" == "--keep-original" ]]; then
    REPLACE_ORIGINAL="0"
  else
    echo "Fehler: Unbekannter Parameter '$3'" >&2
    exit 1
  fi
fi

if [[ ! -f "$INPUT" ]]; then
  echo "Fehler: Datei nicht gefunden: $INPUT" >&2
  exit 1
fi

"$PY_SCRIPT" "$INPUT" "$FACTOR"

INPUT_DIR="$(dirname "$INPUT")"
INPUT_BASE="$(basename "$INPUT")"
INPUT_STEM="${INPUT_BASE%.*}"
SHRINKED_FILE="$INPUT_DIR/${INPUT_STEM}_shrinked.geojson"

if [[ ! -f "$SHRINKED_FILE" ]]; then
  echo "Fehler: Erwartete Ausgabedatei nicht gefunden: $SHRINKED_FILE" >&2
  exit 1
fi

if [[ "$REPLACE_ORIGINAL" == "1" ]]; then
  mv -f "$SHRINKED_FILE" "$INPUT"
  echo "Originaldatei ersetzt: $INPUT"
else
  echo "Originaldatei behalten, Shrink-Datei bleibt erhalten: $SHRINKED_FILE"
fi