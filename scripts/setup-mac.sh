#!/bin/bash
# Installa su macOS gli strumenti del repository, scaricandoli da GitHub/npm:
#   - REA (rea-agents, npm) con la skill per Claude Code;
#   - SolidCraft (immagine disco della release GitHub tangency-labs/solidcraft);
#   - Open CAD Studio (immagine disco della release GitHub
#     HakanSeven12/OpenCADStudio, solo Mac con Apple Silicon);
#   - OpenSCAD (compilato dai sorgenti GitHub openscad/openscad: il progetto
#     non pubblica eseguibili per macOS su GitHub);
#   - Ghidra 12.1.4 (facoltativo, per i binari nativi con REA; richiede JDK 21).
#
# Uso:   bash scripts/setup-mac.sh [--senza-openscad] [--senza-opencadstudio] [--ghidra]
# Idempotente: salta ciò che è già alla versione indicata qui sotto.
# Prerequisiti: Homebrew (https://brew.sh) e gli strumenti da riga di comando
# di Xcode (xcode-select --install); OpenSCAD richiede Xcode completo.
set -euo pipefail

REA_VERSION="6.8.0"
SOLIDCRAFT_VERSION="0.24.0"
SOLIDCRAFT_SHA256="2c2ea4330623c2038cc6235d97454ec1d178d4e466e13daeac0dd49c13a4fc77"
OPENCADSTUDIO_VERSION="2026.43"
OPENCADSTUDIO_SHA256="4e8ba1b36b85c7f8c860b04bdd238be7f6ead3de3ef6de80c7cedb6318aefc2a"
OPENSCAD_REF="openscad-2026.10-TEST4"
GHIDRA_VERSION="12.1.4"
GHIDRA_BUILD_DATE="20260921"
GHIDRA_SHA256="ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"

CON_OPENSCAD=1
CON_OPENCADSTUDIO=1
CON_GHIDRA=0
for arg in "$@"; do
  case "$arg" in
    --senza-openscad) CON_OPENSCAD=0 ;;
    --senza-opencadstudio) CON_OPENCADSTUDIO=0 ;;
    --ghidra) CON_GHIDRA=1 ;;
    *) echo "opzione sconosciuta: $arg" >&2; exit 2 ;;
  esac
done

[ "$(uname -s)" = "Darwin" ] || { echo "Questo script è per macOS." >&2; exit 1; }
command -v brew >/dev/null || { echo "Serve Homebrew: https://brew.sh" >&2; exit 1; }
xcode-select -p >/dev/null 2>&1 || { echo "Servono gli strumenti di Xcode: xcode-select --install" >&2; exit 1; }

SRC_DIR="$HOME/.local/src"
STATE_FILE="$HOME/.config/reverse-engineering/versioni-installate.txt"
mkdir -p "$SRC_DIR" "$(dirname "$STATE_FILE")"

installed() {  # versione registrata nel riepilogo per una chiave (vuota se assente)
  grep "^$1=" "$STATE_FILE" 2>/dev/null | cut -d= -f2 || true
}

install_dmg() {  # url sha256 nome.app: scarica, verifica e copia l'app in /Applications
  local tmp app
  tmp="$(mktemp -d)"
  curl -fL -o "$tmp/app.dmg" "$1"
  echo "$2  $tmp/app.dmg" | shasum -a 256 -c - >/dev/null || { echo "hash errato per $1" >&2; rm -rf "$tmp"; exit 1; }
  hdiutil attach -nobrowse -readonly -mountpoint "$tmp/mnt" "$tmp/app.dmg" >/dev/null
  app="$(find "$tmp/mnt" -maxdepth 1 -name '*.app' | head -n 1)"
  [ -n "$app" ] || { hdiutil detach "$tmp/mnt" >/dev/null; echo "nessuna app nel dmg di $1" >&2; exit 1; }
  rm -rf "/Applications/$3"
  ditto "$app" "/Applications/$3"
  hdiutil detach "$tmp/mnt" >/dev/null
  rm -rf "$tmp"
}

app_version() {  # versione di un'app in /Applications (vuota se assente)
  /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$1/Contents/Info.plist" 2>/dev/null || true
}

# --- REA -------------------------------------------------------------------
# REA 6.8.0 richiede Node ^22.23.4 || ^24.22.1 || >=26.12.1
node_ok() {
  command -v node >/dev/null && node -e '
  const [a, b, c] = process.versions.node.split(".").map(Number);
  const ge = (x, y, z) => b > y || (b === y && c >= z);
  process.exit((a === 22 && ge(22, 23, 4)) || (a === 24 && ge(24, 22, 1)) || (a === 26 && ge(26, 12, 1)) || a > 26 ? 0 : 1)'
}
if ! node_ok; then
  brew install node@22 || brew upgrade node@22
  export PATH="$(brew --prefix node@22)/bin:$PATH"
  node_ok || { echo "Node $(node -v) non soddisfa i requisiti di REA ${REA_VERSION}" >&2; exit 1; }
fi
if ! command -v rea >/dev/null || [ "$(rea --version)" != "$REA_VERSION" ]; then
  npm install --global "rea-agents@${REA_VERSION}"
  rm -rf "$HOME/.claude/skills/reverse-engineer-anything"
fi
if [ ! -f "$HOME/.claude/skills/reverse-engineer-anything/SKILL.md" ]; then
  rea setup --skill-client claude_code --yes >/dev/null
fi

# --- Ghidra (facoltativo) ----------------------------------------------------
GHIDRA_DIR="$HOME/.local/ghidra_${GHIDRA_VERSION}_PUBLIC"
if [ "$CON_GHIDRA" = 1 ] && [ ! -x "$GHIDRA_DIR/support/analyzeHeadless" ]; then
  brew install openjdk@21
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/ghidra.zip" \
    "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_BUILD_DATE}.zip"
  echo "${GHIDRA_SHA256}  $tmp/ghidra.zip" | shasum -a 256 -c -
  unzip -q "$tmp/ghidra.zip" -d "$HOME/.local"
  rm -rf "$tmp"
fi

# --- SolidCraft --------------------------------------------------------------
if [ "$(app_version /Applications/SolidCraft.app)" != "$SOLIDCRAFT_VERSION" ]; then
  install_dmg "https://github.com/tangency-labs/solidcraft/releases/download/v${SOLIDCRAFT_VERSION}/solidcraft-macos-universal.dmg" \
    "$SOLIDCRAFT_SHA256" SolidCraft.app
fi

# --- Open CAD Studio -----------------------------------------------------------
if [ "$CON_OPENCADSTUDIO" = 1 ]; then
  if [ "$(uname -m)" != "arm64" ]; then
    echo "Open CAD Studio pubblica il pacchetto per macOS solo per Apple Silicon: saltato." >&2
    CON_OPENCADSTUDIO=0
  elif [ "$(installed opencadstudio)" != "$OPENCADSTUDIO_VERSION" ] || [ ! -d /Applications/OpenCADStudio.app ]; then
    install_dmg "https://github.com/HakanSeven12/OpenCADStudio/releases/download/v${OPENCADSTUDIO_VERSION}/OpenCADStudio-v${OPENCADSTUDIO_VERSION}-macos-arm64.dmg" \
      "$OPENCADSTUDIO_SHA256" OpenCADStudio.app
    echo "Open CAD Studio non è notarizzato: se macOS blocca il primo avvio, approvalo in Impostazioni di Sistema → Privacy e sicurezza."
  fi
fi

# --- OpenSCAD ----------------------------------------------------------------
if [ "$CON_OPENSCAD" = 1 ] && [ "$(installed openscad)" != "$OPENSCAD_REF" ]; then
  src="$SRC_DIR/$OPENSCAD_REF"
  [ -d "$src/.git" ] || git clone --depth 1 --branch "$OPENSCAD_REF" \
    --recurse-submodules --shallow-submodules https://github.com/openscad/openscad.git "$src"
  (
    cd "$src"
    ./scripts/macosx-build-homebrew.sh
    cmake -B build -DEXPERIMENTAL=1 -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j "$(sysctl -n hw.ncpu)"
  )
  app="$(find "$src/build" -maxdepth 2 -name 'OpenSCAD.app' | head -n 1)"
  [ -n "$app" ] || { echo "OpenSCAD.app non trovato in $src/build" >&2; exit 1; }
  rm -rf /Applications/OpenSCAD.app
  ditto "$app" /Applications/OpenSCAD.app
fi

# --- riepilogo ---------------------------------------------------------------
{
  echo "rea=$(rea --version)"
  echo "solidcraft=$(app_version /Applications/SolidCraft.app)"
  if [ "$CON_OPENSCAD" = 1 ]; then
    echo "openscad=$OPENSCAD_REF"
  else
    grep '^openscad=' "$STATE_FILE" 2>/dev/null || true
  fi
  if [ "$CON_OPENCADSTUDIO" = 1 ]; then
    echo "opencadstudio=$OPENCADSTUDIO_VERSION"
  else
    grep '^opencadstudio=' "$STATE_FILE" 2>/dev/null || true
  fi
  if [ -x "$GHIDRA_DIR/support/analyzeHeadless" ]; then echo "ghidra=$GHIDRA_VERSION"; fi
} > "$STATE_FILE.new"
mv "$STATE_FILE.new" "$STATE_FILE"
echo "Versioni installate ($STATE_FILE):"
cat "$STATE_FILE"
if [ -x "$GHIDRA_DIR/support/analyzeHeadless" ]; then
  echo "Per REA: export GHIDRA_INSTALL_DIR=$GHIDRA_DIR"
fi
