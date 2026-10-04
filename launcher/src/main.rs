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
/// Beim Build aus dem Secret SPEAKIT_ENV eingebaut (Inhalt einer .env), sonst leer.
const KEYS: Option<&str> = option_env!("SPEAKIT_ENV");

fn app_dir() -> PathBuf {
    match env::var_os("SPEAKIT_DIR") {
        Some(d) => PathBuf::from(d),
        None => PathBuf::from(env::var_os("LOCALAPPDATA").unwrap_or_default()).join("SpeakIt-App"),
    }
}

/// Eingebaute Keys in die .env schreiben, falls dort noch kein Groq-Key steht.
fn write_keys(dir: &PathBuf) {
    let Some(keys) = KEYS.filter(|k| !k.trim().is_empty()) else { return };
    let env = dir.join(".env");
    let has_key = fs::read_to_string(&env).unwrap_or_default().lines().any(|l| {
        l.trim_start().starts_with("GROQ_API_KEY=") && l.split_once('=').is_some_and(|(_, v)| !v.trim().is_empty())
    });
    if !has_key {
        let _ = fs::write(&env, keys);
    }
}

fn start(dir: &PathBuf, pyw: &PathBuf) {
    write_keys(dir);
    let _ = Command::new(pyw).args(["-m", "speakit"]).current_dir(dir).creation_flags(NO_WINDOW).spawn();
}

fn main() {
    let dir = app_dir();
    let pyw = dir.join(".venv").join("Scripts").join("pythonw.exe");
    if pyw.exists() && dir.join(".git").exists() {
        start(&dir, &pyw);
        return;
    }
    // Einrichtung in einem sichtbaren PowerShell-Fenster, damit der Fortschritt zu sehen ist
    let script = env::temp_dir().join("speakit_setup.ps1");
    if fs::write(&script, SETUP).is_err() {
        return;
    }
    let cmd = format!(
        "try {{ & '{}' -NoStart }} catch {{ Write-Host ''; Write-Host ('Fehler: ' + $_) -ForegroundColor Red; Read-Host 'Enter zum Schliessen' }}",
        script.display()
    );
    let _ = Command::new("powershell.exe")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &cmd])
        .status();
    let _ = fs::remove_file(&script);
    if pyw.exists() {
        start(&dir, &pyw);
    }
}
