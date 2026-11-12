# Installa su Windows cio' che serve a Claude Code per il reverse engineering:
#   - Git (con winget) e Node.js 22 (zip ufficiale in una cartella dell'utente),
#     se mancano o se Node e' troppo vecchio per REA;
#   - REA (rea-agents, npm), registrato in Claude Code con la sua skill;
#   - JDK 21 e Ghidra 12.1.4 (per i binari nativi), con GHIDRA_INSTALL_DIR.
#
# Uso (PowerShell, dalla cartella del repository):
#   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -SenzaGhidra
# Idempotente: salta cio' che e' gia' installato. Richiede winget (incluso in
# Windows 10/11 e Windows Server 2025) e Windows a 64 bit (x64).
param([switch]$SenzaGhidra)

$ErrorActionPreference = 'Stop'

$ReaVersion = '6.9.0'
$GhidraVersion = '12.1.4'
$GhidraBuildDate = '20260921'
$GhidraSha256 = 'ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db'
$NodeVersion = '22.23.5'
$NodeSha256 = '4a191082e9706866830379d577d2cc8a50c776fcd9436a8d061b063ed0d9a0e3'
$ProgrammiUtente = Join-Path $env:LOCALAPPDATA 'Programs'
$GhidraRoot = $ProgrammiUtente
$NodeAggiunto = $null
$GhidraDir = Join-Path $GhidraRoot "ghidra_${GhidraVersion}_PUBLIC"

function Test-Comando($nome) { [bool](Get-Command $nome -ErrorAction SilentlyContinue) }

# Dopo un'installazione con winget il PATH di questa finestra non cambia da solo
function Update-Path {
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
              [Environment]::GetEnvironmentVariable('Path', 'User')
  if ($script:NodeAggiunto) { $env:Path = "$script:NodeAggiunto;$env:Path" }
}

function Install-ConWinget($id) {
  winget install --id $id --exact --silent --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw "winget non ha installato $id (codice $LASTEXITCODE)" }
  Update-Path
}

# REA richiede Node ^22.23.4 || ^24.22.1 || >=26.12.1
function Test-Node {
  if (-not (Test-Comando node)) { return $false }
  $v = (node -p 'process.versions.node') -split '\.' | ForEach-Object { [int]$_ }
  $a = $v[0]; $b = $v[1]; $c = $v[2]
  function ge($y, $z) { ($b -gt $y) -or ($b -eq $y -and $c -ge $z) }
  return ($a -eq 22 -and (ge 23 4)) -or ($a -eq 24 -and (ge 22 1)) -or
         ($a -eq 26 -and (ge 12 1)) -or ($a -gt 26)
}

if (-not (Test-Comando winget)) {
  throw 'winget non trovato: installa "Programma di installazione app" dal Microsoft Store.'
}

# --- Git e Node ---------------------------------------------------------------
if (-not (Test-Comando git)) { Install-ConWinget 'Git.Git' }
# Node dal pacchetto zip ufficiale, in una cartella dell'utente: non richiede
# diritti di amministratore e non tocca un eventuale Node gia' installato
if (-not (Test-Node)) {
  $nodeNome = "node-v${NodeVersion}-win-x64"
  $nodeDir = Join-Path $ProgrammiUtente $nodeNome
  if (-not (Test-Path (Join-Path $nodeDir 'node.exe'))) {
    $zip = Join-Path $env:TEMP "$nodeNome.zip"
    Write-Host "Scarico Node ${NodeVersion}..."
    curl.exe -fL -o $zip "https://nodejs.org/dist/v${NodeVersion}/$nodeNome.zip"
    if ($LASTEXITCODE -ne 0) { throw 'Download di Node non riuscito.' }
    $hash = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
    if ($hash -ne $NodeSha256) { Remove-Item $zip; throw "Hash di Node errato: $hash" }
    New-Item -ItemType Directory -Force $ProgrammiUtente | Out-Null
    Expand-Archive -Path $zip -DestinationPath $ProgrammiUtente -Force
    Remove-Item $zip
  }
  # in testa al PATH dell'utente (per le prossime finestre) e di questa finestra
  $pathUtente = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (($pathUtente -split ';') -notcontains $nodeDir) {
    [Environment]::SetEnvironmentVariable('Path', "$nodeDir;$pathUtente", 'User')
  }
  $env:Path = "$nodeDir;$env:Path"
  $script:NodeAggiunto = $nodeDir
  if (-not (Test-Node)) { throw "Node $(node -v) non soddisfa i requisiti di REA ${ReaVersion}." }
}

# --- JDK e Ghidra (facoltativi) -------------------------------------------------
if (-not $SenzaGhidra) {
  if (-not (Test-Comando javac)) { Install-ConWinget 'EclipseAdoptium.Temurin.21.JDK' }
  if (-not (Test-Path (Join-Path $GhidraDir 'support\analyzeHeadless.bat'))) {
    $zip = Join-Path $env:TEMP "ghidra_${GhidraVersion}.zip"
    $url = "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GhidraVersion}_build/ghidra_${GhidraVersion}_PUBLIC_${GhidraBuildDate}.zip"
    Write-Host "Scarico Ghidra ${GhidraVersion}..."
    curl.exe -fL -o $zip $url
    if ($LASTEXITCODE -ne 0) { throw 'Download di Ghidra non riuscito.' }
    $hash = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
    if ($hash -ne $GhidraSha256) { Remove-Item $zip; throw "Hash di Ghidra errato: $hash" }
    New-Item -ItemType Directory -Force $GhidraRoot | Out-Null
    Expand-Archive -Path $zip -DestinationPath $GhidraRoot -Force
    Remove-Item $zip
  }
  [Environment]::SetEnvironmentVariable('GHIDRA_INSTALL_DIR', $GhidraDir, 'User')
  $env:GHIDRA_INSTALL_DIR = $GhidraDir
}

# --- REA ------------------------------------------------------------------------
$reaInstallata = if (Test-Comando rea) { (rea --version) } else { '' }
if ($reaInstallata -ne $ReaVersion) {
  npm install --global "rea-agents@${ReaVersion}"
  if ($LASTEXITCODE -ne 0) { throw 'Installazione di REA non riuscita.' }
  Update-Path
}
# registra REA in Claude Code (file .claude.json dell'utente) e installa la skill
$esitoSetup = rea setup --client claude_code --yes 2>&1
$setupRiuscito = ($LASTEXITCODE -eq 0)
if (-not $setupRiuscito) {
  # mostra il messaggio di REA e prosegue: il resto e' gia' installato
  $esitoSetup | ForEach-Object { Write-Host $_ }
  Write-Warning 'rea setup non riuscito (messaggio qui sopra): REA e'' installato ma non ancora collegato a Claude Code.'
}

# --- riepilogo --------------------------------------------------------------------
if ($setupRiuscito) { Write-Host "REA $(rea --version) installato e registrato in Claude Code." }
else { Write-Host "REA $(rea --version) installato." }
if (-not $SenzaGhidra) { Write-Host "Ghidra in $GhidraDir (GHIDRA_INSTALL_DIR impostata per l'utente)." }
if ($NodeAggiunto) {
  Write-Host "Node ${NodeVersion} in $NodeAggiunto (aggiunto al PATH dell'utente)."
  Write-Host "Se in una nuova finestra 'node -v' mostra ancora una versione vecchia, disinstalla il vecchio Node da Impostazioni > App."
}
Write-Host 'Verifica: riapri PowerShell ed esegui "rea doctor".'
if (-not (Test-Comando claude)) {
  Write-Host 'Claude Code non trovato: installa Claude Desktop da https://claude.ai/download'
}
