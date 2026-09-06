#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
mkdir -p "$BUILD_DIR"

# One zip per plain-code (non-container) Lambda. The worker is a container
# image (see Step 4) and is not packaged here.
for fn in submit status reconcile; do
  src="$ROOT_DIR/lambdas/$fn"
  out="$BUILD_DIR/$fn.zip"
  rm -f "$out"
  (cd "$src" && zip -qr "$out" .)
  echo "packaged $out"
done