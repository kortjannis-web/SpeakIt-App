# Baut dist\SpeakIt.exe (eine einzelne Datei zum Weitergeben).
# -BundleKeys: legt deine Groq- und Anthropic-Keys aus .env in die EXE (Empfaenger muss nichts eintragen).
param([switch]$BundleKeys)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Zuerst install.ps1 ausfuehren." }

& $py -m pip install --quiet pyinstaller
& $py make_icon.py

$bundled = "speakit\bundled.py"
if ($BundleKeys) {
    $env = @{}
    Get-Content ".env" | ForEach-Object { if ($_ -match "^\s*([A-Z_]+)\s*=\s*(.+)$") { $env[$Matches[1]] = $Matches[2].Trim() } }
    $lines = @("KEYS = {")
    foreach ($k in "GROQ_API_KEY", "ANTHROPIC_API_KEY") {
        if ($env[$k]) { $lines += "    `"$k`": `"$($env[$k])`"," }
    }
    $lines += "}"
    Set-Content -Path $bundled -Value $lines -Encoding utf8
    Write-Host "Keys werden in die EXE eingebaut."
} elseif (Test-Path $bundled) { Remove-Item $bundled }

try {
    & $py -m PyInstaller --noconfirm --clean --onefile --noconsole --name SpeakIt --icon icon.ico `
        --collect-all customtkinter --collect-all sounddevice --collect-all _sounddevice_data `
        --hidden-import pystray._win32 --hidden-import speakit.bundled run_speakit.py
} finally {
    if (Test-Path $bundled) { Remove-Item $bundled }
}
if (-not (Test-Path "dist\SpeakIt.exe")) { throw "Build fehlgeschlagen." }
Write-Host "Fertig: $PSScriptRoot\dist\SpeakIt.exe"
