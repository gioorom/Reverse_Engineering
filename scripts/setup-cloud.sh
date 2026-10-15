#!/bin/bash
# Installa REA e Ghidra in un ambiente Linux (sessioni Claude Code nel cloud).
# Idempotente: salta i passi già fatti. Richiede JDK 21+ (javac nel PATH).
set -euo pipefail

REA_VERSION="6.5.0"
GHIDRA_VERSION="12.1.4"
GHIDRA_BUILD_DATE="20260921"
GHIDRA_SHA256="ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"
GHIDRA_DIR="/opt/ghidra_${GHIDRA_VERSION}_PUBLIC"

if ! command -v rea >/dev/null || [ "$(rea --version)" != "$REA_VERSION" ]; then
  npm install --global "rea-agents@${REA_VERSION}"
fi

if [ ! -x "$GHIDRA_DIR/support/analyzeHeadless" ]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL -o "$tmp/ghidra.zip" \
    "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_BUILD_DATE}.zip"
  echo "${GHIDRA_SHA256}  $tmp/ghidra.zip" | sha256sum -c -
  unzip -q "$tmp/ghidra.zip" -d /opt
fi

export GHIDRA_INSTALL_DIR="$GHIDRA_DIR"
echo "REA $(rea --version) e Ghidra in $GHIDRA_INSTALL_DIR pronti."
