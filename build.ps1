# Baut eine einzelne EXE zum Weitergeben: dist\SpeakIt-ohne-Keys.exe oder (mit -BundleKeys) dist\SpeakIt-mit-Keys.exe.
# -BundleKeys: legt deine Groq- und Anthropic-Keys aus .env in die EXE (Empfaenger muss nichts eintragen).
param([switch]$BundleKeys)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".venv\Scripts\python.exe"
$name = if ($BundleKeys) { "SpeakIt-mit-Keys" } else { "SpeakIt-ohne-Keys" }
if (-not (Test-Path $py)) { throw "Zuerst install.ps1 ausfuehren." }

& $py -m pip install --quiet pyinstaller
& $py make_icon.py

# Gleiche Version wie das neueste Release, damit sich diese EXE beim nächsten Release selbst aktualisiert
$version = "speakitersion.py"
$versionOld = Get-Content $version -Raw
try {
    $tag = (Invoke-RestMethod "https://api.github.com/repos/kortjannis-web/SpeakIt-App/releases/latest").tag_name
    Set-Content -Path $version -Value "VERSION = `"$($tag.TrimStart('v'))`"" -Encoding utf8
    Write-Host "Version: $tag"
} catch { Write-Host "Kein Release gefunden, Version bleibt 0.0.0 (aktualisiert sich beim ersten Release)." }

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
    & $py -m PyInstaller --noconfirm --clean --onefile --noconsole --name $name --icon icon.ico `
        --collect-all customtkinter --collect-all sounddevice --collect-all _sounddevice_data `
        --hidden-import pystray._win32 --hidden-import speakit.bundled run_speakit.py
} finally {
    if (Test-Path $bundled) { Remove-Item $bundled }
    Set-Content -Path $version -Value $versionOld.TrimEnd() -Encoding utf8
}
if (-not (Test-Path "dist\$name.exe")) { throw "Build fehlgeschlagen." }
Write-Host "Fertig: $PSScriptRoot\dist\$name.exe"
