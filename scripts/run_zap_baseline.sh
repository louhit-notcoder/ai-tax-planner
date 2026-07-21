#!/usr/bin/env sh
set -eu
: "${STAGING_URL:?Set STAGING_URL to the authorised staging base URL}"
OUTPUT_DIR="${OUTPUT_DIR:-./security-reports/zap}"
mkdir -p "$OUTPUT_DIR"
docker run --rm --network host \
  -v "$(pwd)/$OUTPUT_DIR:/zap/wrk:rw" \
  ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t "$STAGING_URL" -r zap-baseline.html -J zap-baseline.json -w zap-baseline.md
