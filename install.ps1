# SpeakIt installieren: venv, Pakete, Autostart. Optional -Admin (laeuft dann auch ueber Admin-Fenstern).
param([switch]$Admin, [switch]$NoStart)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\pythonw.exe")) {
    Write-Host "Erstelle virtuelle Umgebung ..."
    python -m venv .venv
}
Write-Host "Installiere Pakete ..."
& .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

$pyw = (Resolve-Path ".venv\Scripts\pythonw.exe").Path
$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\SpeakIt.lnk"

# alte Autostarts entfernen
if (Test-Path $lnk) { Remove-Item $lnk }
Unregister-ScheduledTask -TaskName "SpeakIt" -Confirm:$false -ErrorAction SilentlyContinue

if ($Admin) {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) { throw "Fuer -Admin dieses Skript in einer Administrator-PowerShell starten." }
    $action = New-ScheduledTaskAction -Execute $pyw -Argument "-m speakit --background" -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType Interactive
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName "SpeakIt" -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "Autostart als Administrator eingerichtet (Aufgabenplanung)."
    if (-not $NoStart) { Start-ScheduledTask -TaskName "SpeakIt" }
} else {
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = $pyw
    $s.Arguments = "-m speakit --background"
    $s.WorkingDirectory = $PSScriptRoot
    $s.WindowStyle = 7
    $s.Save()
    Write-Host "Autostart eingerichtet (Startup-Ordner)."
    if (-not $NoStart) { Start-Process $pyw -ArgumentList "-m speakit --background" -WorkingDirectory $PSScriptRoot }
}
Write-Host "Fertig. SpeakIt laeuft im Tray (Mikrofon-Symbol). Beim ersten Start oeffnen sich die Einstellungen."
