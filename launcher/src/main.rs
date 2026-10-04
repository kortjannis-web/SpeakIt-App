//! SpeakIt-Installer.exe: eine kleine EXE ohne Abhängigkeiten.
//! Erster Start: richtet SpeakIt über setup.ps1 ein (Git, Python, venv, Startmenü, Autostart).
//! Danach: startet SpeakIt direkt. Updates holt sich die App selbst über GitHub.
#![windows_subsystem = "windows"]

use std::env;
use std::fs;
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;

const SETUP: &str = include_str!("../../setup.ps1");
const NO_WINDOW: u32 = 0x0800_0000;

fn app_dir() -> PathBuf {
    match env::var_os("SPEAKIT_DIR") {
        Some(d) => PathBuf::from(d),
        None => PathBuf::from(env::var_os("LOCALAPPDATA").unwrap_or_default()).join("SpeakIt-App"),
    }
}

fn main() {
    let dir = app_dir();
    let pyw = dir.join(".venv").join("Scripts").join("pythonw.exe");
    if pyw.exists() && dir.join(".git").exists() {
        let _ = Command::new(&pyw).args(["-m", "speakit"]).current_dir(&dir).creation_flags(NO_WINDOW).spawn();
        return;
    }
    // Einrichtung in einem sichtbaren PowerShell-Fenster, damit der Fortschritt zu sehen ist
    let script = env::temp_dir().join("speakit_setup.ps1");
    if fs::write(&script, SETUP).is_err() {
        return;
    }
    let cmd = format!(
        "try {{ & '{}' }} catch {{ Write-Host ''; Write-Host ('Fehler: ' + $_) -ForegroundColor Red; Read-Host 'Enter zum Schliessen' }}",
        script.display()
    );
    let _ = Command::new("powershell.exe")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &cmd])
        .status();
    let _ = fs::remove_file(&script);
}
