#!/bin/bash
# Installa REA (con la skill per Claude Code) e Ghidra in un ambiente Linux (sessioni Claude Code nel cloud).
# Idempotente: salta i passi già fatti. Ghidra 12.2 richiede JDK 25: se manca
# viene installato con apt (Ubuntu/Debian).
set -euo pipefail

REA_VERSION="6.10.1"
NODE_VERSION="22.23.4"  # REA 6.10.1 richiede Node ^22.23.4 || ^24.22.1 || >=26.12.1
GHIDRA_VERSION="12.2"   # REA 6.10 richiede Ghidra 12.2 o successivo
GHIDRA_BUILD_DATE="20261016"
GHIDRA_SHA256="2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67"
JDK_MAJOR="25"         # richiesto da Ghidra 12.2
GHIDRA_DIR="/opt/ghidra_${GHIDRA_VERSION}_PUBLIC"

SKILL_DIR="$HOME/.claude/skills/reverse-engineer-anything"

node_ok() {
  command -v node >/dev/null && node -e '
  const [a, b, c] = process.versions.node.split(".").map(Number);
  const ge = (x, y, z) => b > y || (b === y && c >= z);
  process.exit((a === 22 && ge(22, 23, 4)) || (a === 24 && ge(24, 22, 1)) || (a === 26 && ge(26, 12, 1)) || a > 26 ? 0 : 1)'
}

# Node richiesto da REA: se manca o è troppo vecchio, la release ufficiale
# (hash verificato) sostituisce quella installata nella stessa cartella
if ! node_ok; then
  prefix="$(dirname "$(dirname "$(readlink -f "$(command -v node || echo /usr/local/bin/node)")")")"
  ntmp="$(mktemp -d)"
  base="https://nodejs.org/dist/v${NODE_VERSION}"
  file="node-v${NODE_VERSION}-linux-x64.tar.xz"
  curl -fsSL -o "$ntmp/$file" "$base/$file"
  curl -fsSL -o "$ntmp/SHASUMS256.txt" "$base/SHASUMS256.txt"
  (cd "$ntmp" && grep " $file\$" SHASUMS256.txt | sha256sum -c -)
  tar -xJf "$ntmp/$file" -C "$prefix" --strip-components=1
  rm -rf "$ntmp"
  hash -r
  node_ok || { echo "Node $(node -v) non soddisfa i requisiti di REA" >&2; exit 1; }
fi

if ! command -v rea >/dev/null || [ "$(rea --version)" != "$REA_VERSION" ]; then
  npm install --global "rea-agents@${REA_VERSION}"
  rm -rf "$SKILL_DIR"  # skill da reinstallare per la nuova versione
fi

# JDK richiesto da Ghidra: se javac manca o è più vecchio, si installa con apt
jdk_major() { javac -version 2>&1 | sed -n 's/^javac \([0-9]*\).*/\1/p'; }
if [ "$(jdk_major)" != "$JDK_MAJOR" ]; then
  apt-get update -q >/dev/null
  apt-get install -y -q "openjdk-${JDK_MAJOR}-jdk-headless" >/dev/null
  jdk="/usr/lib/jvm/java-${JDK_MAJOR}-openjdk-$(dpkg --print-architecture)"
  update-alternatives --set java "$jdk/bin/java" >/dev/null
  update-alternatives --set javac "$jdk/bin/javac" >/dev/null
  [ "$(jdk_major)" = "$JDK_MAJOR" ] || { echo "JDK ${JDK_MAJOR} non disponibile" >&2; exit 1; }
fi
# REA sceglie il JDK da JAVA_HOME: le nuove shell puntano al JDK richiesto
JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
export JAVA_HOME
if [ -f /etc/profile.d/java.sh ] && ! grep -q "JAVA_HOME=$JAVA_HOME\$" /etc/profile.d/java.sh; then
  sed -i "s#^export JAVA_HOME=.*#export JAVA_HOME=$JAVA_HOME#" /etc/profile.d/java.sh
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

# skill di REA per Claude Code (solo la skill: il server MCP è in .mcp.json)
if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  rea setup --skill-client claude_code --yes >/dev/null
fi
echo "REA $(rea --version), skill in $SKILL_DIR, Ghidra in $GHIDRA_INSTALL_DIR e JDK in $JAVA_HOME pronti."
echo "Nelle shell già aperte: export JAVA_HOME=$JAVA_HOME GHIDRA_INSTALL_DIR=$GHIDRA_INSTALL_DIR"
