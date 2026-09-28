# Suit-O setup. Run through "Install Suit-O.bat".
#
# 1. Waits for a running Suit-O window to close.
# 2. Makes sure Python 3.11 is installed (winget), because the voice-cloning
#    packages do not have builds for newer Python.
# 3. Rebuilds .venv on Python 3.11 when it is on another version. The old venv
#    is renamed, not deleted, until the new one works.
# 4. Installs the base requirements, then any optional parts this PC had
#    before (listed in config.local.yaml), so nothing you used goes missing.
# 5. Opens Suit-O on the Installations window.
#
# Settings (config.local.yaml) and voices (voices\) are outside .venv and are
# never touched.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Venv = Join-Path $Root ".venv"
$Want = "3.11"

function Say($text) { Write-Host "Suit-O setup: $text" }

function Fail($text) {
    Write-Host ""
    Write-Host "Suit-O setup stopped: $text" -ForegroundColor Red
    exit 1
}

function Find-Python311 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $exe = & py "-$Want" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:ProgramFiles "Python311\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Venv-Version {
    $cfg = Join-Path $Venv "pyvenv.cfg"
    if (-not (Test-Path $cfg)) { return "" }
    foreach ($line in Get-Content $cfg) {
        if ($line -match "^\s*version(_info)?\s*=\s*(\d+\.\d+)") { return $Matches[2] }
    }
    return ""
}

# 1. Wait for Suit-O to close so its venv is free.
Say "waiting for the Suit-O window to close..."
for ($i = 0; $i -lt 60; $i++) {
    $running = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "suit_o\.gui" }
    if (-not $running) { break }
    Start-Sleep -Seconds 1
}
if ($running) { Fail "Suit-O is still open. Close its window, then run Install Suit-O.bat again." }

# 2. Python 3.11.
$Python = Find-Python311
if (-not $Python) {
    Say "installing Python 3.11 (next to any other Python you have)..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Fail "winget is missing. Install Python 3.11 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
    }
    & winget install --id Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements
    $Python = Find-Python311
    if (-not $Python) { Fail "Python 3.11 did not install. Install it from python.org, then run this again." }
}
Say "using Python 3.11 at $Python"

# 3. Rebuild the venv when it is on another version.
$Current = Venv-Version
$Old = ""
if ($Current -ne $Want) {
    if (Test-Path $Venv) {
        $Old = Join-Path $Root (".venv-old-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
        Say "moving the Python $Current venv aside to $(Split-Path -Leaf $Old)..."
        Rename-Item $Venv $Old
    }
    Say "creating a new venv on Python 3.11..."
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        if ($Old) { Rename-Item $Old $Venv }
        Fail "could not create the venv."
    }
}
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvPythonw = Join-Path $Venv "Scripts\pythonw.exe"

# 4. Base requirements, then the optional parts this PC already used.
Say "installing Suit-O's base requirements..."
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    if ($Old) {
        Remove-Item -Recurse -Force $Venv -ErrorAction SilentlyContinue
        Rename-Item $Old $Venv
        Say "put the previous venv back."
    }
    Fail "pip could not install requirements.txt."
}

$Kept = & $VenvPython -c "from pathlib import Path; from suit_o.local_config import read_installed_requirements; print(' '.join(sorted(read_installed_requirements(Path('config.yaml')))))" 2>$null
if ($LASTEXITCODE -eq 0 -and $Kept) {
    foreach ($file in $Kept.Trim().Split(" ")) {
        if (-not $file) { continue }
        Say "reinstalling $file, which this PC had before..."
        & $VenvPython -m pip install -r $file
        if ($LASTEXITCODE -ne 0) { Say "could not reinstall $file. Tick it again in Installations." }
    }
}

if ($Old) {
    Say "removing the old venv..."
    Remove-Item -Recurse -Force $Old -ErrorAction SilentlyContinue
}

# 5. Open Suit-O on Installations.
Say "done. Opening Suit-O..."
Start-Process -FilePath $VenvPythonw -ArgumentList "-m", "suit_o.gui", "--installations" -WorkingDirectory $Root
exit 0
