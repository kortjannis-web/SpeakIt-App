Set-Location $PSScriptRoot
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match "speakit" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\SpeakIt.lnk"
if (Test-Path $lnk) { Remove-Item $lnk }
Unregister-ScheduledTask -TaskName "SpeakIt" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "SpeakIt beendet und Autostart entfernt. Ordner kann geloescht werden."
