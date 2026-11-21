#!/usr/bin/env bash
# Download and unpack an official Blender Linux build for CI.
#
#   tools/ci/download_blender.sh VERSION DEST      e.g. 5.3.0 ~/blender
#
# Tries download.blender.org first, then official mirrors (the main server
# sometimes refuses or throttles CI machines). Each source gets curl
# retries; the archive is checked against Blender's published SHA-256 list
# before it is unpacked. Afterwards DEST/blender is the executable.
set -euo pipefail

VERSION="$1"
DEST="$2"
SERIES="${VERSION%.*}"                       # 5.3.0 -> 5.3
FILE="blender-${VERSION}-linux-x64.tar.xz"
SUMS="blender-${VERSION}.sha256"
SOURCES=(
  "https://download.blender.org/release"
  "https://mirrors.ocf.berkeley.edu/blender/release"
  "https://ftp.nluug.nl/pub/graphics/blender/release"
  "https://mirror.clarkson.edu/blender/release"
  "https://ftp.halifax.rwth-aachen.de/blender/release"
)
CURL=(curl --fail --location --silent --show-error --retry 4 --retry-all-errors
      --retry-delay 15 --connect-timeout 30 --max-time 900
      --user-agent "solid-snapshot-ci")

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ok=""
for base in "${SOURCES[@]}"; do
  url="$base/Blender$SERIES"
  echo "Trying $url/$FILE"
  if "${CURL[@]}" -o "$WORK/$SUMS" "$url/$SUMS" && "${CURL[@]}" -o "$WORK/$FILE" "$url/$FILE"; then
    expected="$(grep " $FILE\$" "$WORK/$SUMS" | cut -d' ' -f1)"
    actual="$(sha256sum "$WORK/$FILE" | cut -d' ' -f1)"
    if [ -n "$expected" ] && [ "$expected" = "$actual" ]; then
      ok="yes"
      echo "Checksum OK ($actual)"
      break
    fi
    echo "Checksum mismatch from $base (expected '$expected', got '$actual'), trying next source"
  else
    echo "Download failed from $base, trying next source"
  fi
done
[ -n "$ok" ] || { echo "Could not download $FILE from any source" >&2; exit 1; }

mkdir -p "$DEST"
tar -xJf "$WORK/$FILE" -C "$DEST" --strip-components=1
"$DEST/blender" --version | head -1
