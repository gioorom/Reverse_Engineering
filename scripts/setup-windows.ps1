# Installa su Windows cio' che serve a Claude Code per il reverse engineering:
#   - Git (con winget) e Node.js 24: se Node manca, zip ufficiale in una cartella
#     dell'utente; se c'e' ma e' troppo vecchio per REA, aggiornato con
#     l'installer ufficiale;
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
$NodeVersion = '24.22.3'
$NodeZipSha256 = 'e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f'
$NodeMsiSha256 = '4a1ab5bdec5434bae58efae6c3e5077a011f6f1e76d2b47b7b10af043f7db545'
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
# Se c'e' gia' un Node di sistema (installer ufficiale) e' quello che vince nel
# PATH: va aggiornato lui. Un Node portatile lasciato da una versione precedente
# di questo script viene tolto dal PATH dell'utente.
$nodeDiSistema = Join-Path $env:ProgramFiles 'nodejs\node.exe'
if (Test-Path $nodeDiSistema) {
  $portatile = Join-Path $ProgrammiUtente 'node-v*-win-x64'
  $voci = [Environment]::GetEnvironmentVariable('Path', 'User') -split ';' |
          Where-Object { $_ -and ($_ -notlike $portatile) }
  [Environment]::SetEnvironmentVariable('Path', ($voci -join ';'), 'User')
  Update-Path
}
if (-not (Test-Node)) {
  if (Test-Path $nodeDiSistema) {
    # aggiorna il Node di sistema con l'installer ufficiale (hash verificato)
    $major = [int]((& $nodeDiSistema -p 'process.versions.node') -split '\.')[0]
    if ($major -gt 24) { throw "Node $major installato ma troppo vecchio per REA: aggiornalo da https://nodejs.org" }
    $msi = Join-Path $env:TEMP "node-v${NodeVersion}-x64.msi"
    Write-Host "Scarico Node ${NodeVersion}..."
    curl.exe -fL -o $msi "https://nodejs.org/dist/v${NodeVersion}/node-v${NodeVersion}-x64.msi"
    if ($LASTEXITCODE -ne 0) { throw 'Download di Node non riuscito.' }
    $hash = (Get-FileHash -Algorithm SHA256 $msi).Hash.ToLower()
    if ($hash -ne $NodeMsiSha256) { Remove-Item $msi; throw "Hash di Node errato: $hash" }
    Write-Host 'Aggiorno Node: conferma la richiesta di Windows (Controllo account utente).'
    $p = Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /passive /norestart" -Wait -PassThru
    Remove-Item $msi
    if ($p.ExitCode -ne 0) { throw "Aggiornamento di Node non riuscito (codice $($p.ExitCode))." }
    Update-Path
  } else {
    # nessun Node: zip ufficiale in una cartella dell'utente, senza diritti di amministratore
    $nodeNome = "node-v${NodeVersion}-win-x64"
    $nodeDir = Join-Path $ProgrammiUtente $nodeNome
    if (-not (Test-Path (Join-Path $nodeDir 'node.exe'))) {
      $zip = Join-Path $env:TEMP "$nodeNome.zip"
      Write-Host "Scarico Node ${NodeVersion}..."
      curl.exe -fL -o $zip "https://nodejs.org/dist/v${NodeVersion}/$nodeNome.zip"
      if ($LASTEXITCODE -ne 0) { throw 'Download di Node non riuscito.' }
      $hash = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
      if ($hash -ne $NodeZipSha256) { Remove-Item $zip; throw "Hash di Node errato: $hash" }
      New-Item -ItemType Directory -Force $ProgrammiUtente | Out-Null
      Expand-Archive -Path $zip -DestinationPath $ProgrammiUtente -Force
      Remove-Item $zip
    }
    $pathUtente = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (($pathUtente -split ';') -notcontains $nodeDir) {
      [Environment]::SetEnvironmentVariable('Path', "$nodeDir;$pathUtente", 'User')
    }
    $env:Path = "$nodeDir;$env:Path"
    $script:NodeAggiunto = $nodeDir
  }
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
}
Write-Host 'Verifica: riapri PowerShell ed esegui "rea doctor".'
if (-not (Test-Comando claude)) {
  Write-Host 'Claude Code non trovato: installa Claude Desktop da https://claude.ai/download'
}
