# SpeakIt in einem Schritt installieren (ohne EXE, kostenlos, aktualisiert sich selbst ueber GitHub).
# Aufruf in PowerShell:
#   irm https://raw.githubusercontent.com/kortjannis-web/SpeakIt-App/master/setup.ps1 | iex
$ErrorActionPreference = "Stop"
$repo = "https://github.com/kortjannis-web/SpeakIt-App.git"
$dir = if ($env:SPEAKIT_DIR) { $env:SPEAKIT_DIR } else { Join-Path $env:LOCALAPPDATA "SpeakIt-App" }

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

function Has-Python {
    # Der Platzhalter aus dem Microsoft Store (WindowsApps) zaehlt nicht
    if (Get-Command py -ErrorAction SilentlyContinue) { return $true }
    $p = Get-Command python -ErrorAction SilentlyContinue
    return ($p -and $p.Source -notlike "*WindowsApps*")
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Installiere Git ..."
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Refresh-Path
}
if (-not (Has-Python)) {
    Write-Host "Installiere Python ..."
    winget install --id Python.Python.3.13 -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Refresh-Path
}

if (Test-Path (Join-Path $dir ".git")) {
    Write-Host "Aktualisiere SpeakIt ..."
    git -C $dir pull --ff-only --quiet
} else {
    Write-Host "Lade SpeakIt ..."
    git clone --quiet $repo $dir
}

& (Join-Path $dir "install.ps1") @args
