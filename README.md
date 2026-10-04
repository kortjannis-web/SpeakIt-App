# SpeakIt

Diktieren in jedes Textfeld unter Windows. Taste halten oder tippen, sprechen, Text erscheint.

Ablauf: Mikrofon → Groq Whisper (Text) → Claude Haiku (Füllwörter weg, Zeichensetzung, Kontextkorrektur) → Einfügen per Strg+V.

## Installation aus dem Quellcode (einmalig)

1. PowerShell im Projektordner:
   ```
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
2. SpeakIt startet, das Fenster öffnet sich, ein Mikrofon-Symbol erscheint im Tray (unten rechts, ggf. hinter dem Pfeil).
3. Unter **Einstellungen** die API-Keys eintragen, Taste wählen, Speichern.

Ab dann startet es bei jeder Windows-Anmeldung unsichtbar im Hintergrund.

Über Admin-Fenster diktieren (Windows blockt sonst Hotkeys): `install.ps1 -Admin` in einer Administrator-PowerShell.

## API-Keys

**Groq (Sprache zu Text)**: console.groq.com → API Keys → Create API Key (`gsk_…`). Der Gratis-Tarif reicht für private Nutzung, ein Modell muss nicht gewählt werden.

**Anthropic (Textnachbearbeitung)**: console.anthropic.com → Billing: Guthaben aufladen und Monatslimit setzen → API Keys → Create Key (`sk-ant-…`).

Ohne Anthropic-Key funktioniert SpeakIt weiter, nur ohne Glättung und Kontextkorrektur.

## Bedienung

| Aktion | Wirkung |
|---|---|
| Taste halten | Aufnahme läuft, beim Loslassen wird eingefügt |
| Taste kurz tippen | Aufnahme startet, nochmal tippen stoppt |
| Esc während Aufnahme | Abbrechen |

- Die Taste ist komplett belegt (`M` oder `F11` tippt nichts mehr). Bei Kombinationen wird nur die letzte Taste geschluckt.
- **Copilot-Taste**: Einstellungen → "Copilot-Taste" (sendet Win + Umschalt + F23, F23 wird geschluckt).
- Das Overlay unten zeigt Pegel und Sekundenticker, danach den Status.
- Sprachbefehle im Diktat: "neue Zeile", "neuer Absatz", "Punkt", "Komma", "Fragezeichen".

## Fenster

- **Verlauf**: letzte Diktate, kopieren, "Original" ansehen. Wort anklicken oder mehrere markieren → "Korrigieren …": falsch/richtig eintragen, Kontext wählen. SpeakIt ersetzt das künftig automatisch und gibt es Whisper und Claude als Hinweis mit.
- **Kontexte**: Themen mit Begriffen und festen Korrekturen (Re:Zero, Fantasy, Webdesign, SEO & GEO, Business, KI & Cloud, eigene). Aktive Kontexte gehen an Whisper und Claude. Inaktive kennt Claude trotzdem und nutzt sie nur, wenn das Thema offensichtlich passt.
- **Statistik**: Diktate, Wörter, Sprechzeit, Token, geschätzte Kosten für Heute, Monat, Gesamt. Links unten steht es immer.
- **Einstellungen**: Taste, Modus, Sprache, Mikrofon, Anbieter, Töne, Autostart, Keys.

## Kosten (Listenpreise aus dem Gedächtnis, vor Nutzung prüfen)

- Groq whisper-large-v3-turbo: ca. 0,04 $ pro Stunde Audio (Gratis-Tarif mit Limits)
- Claude Haiku 4.5: ca. 1 $ pro Mio. Eingabe-Token, 5 $ pro Mio. Ausgabe-Token
- Pro Diktat gehen Prompt und Begriffslisten mit (ca. 2.000 bis 3.000 Token): grob 0,3 bis 0,5 Cent pro Minute Sprechen

## EXE zum Weitergeben

```
powershell -ExecutionPolicy Bypass -File build.ps1
```
Ergebnis: `dist\SpeakIt-ohne-Keys.exe` (oder `-mit-Keys`). Beim ersten Öffnen installiert sich die Datei selbst (nach `%LOCALAPPDATA%\Programs\SpeakIt`), legt Autostart und Startmenü-Eintrag an und startet. Daten liegen in `%APPDATA%\SpeakIt`.

**Mit eingebauten Keys** (Empfänger muss nichts eintragen):
```
powershell -ExecutionPolicy Bypass -File build.ps1 -BundleKeys
```
Achtung: Keys in einer EXE lassen sich auslesen. Lege dafür eigene Keys an (Groq und Anthropic) mit niedrigem Ausgabenlimit und lösche sie, wenn du die Datei nicht mehr verteilen willst. Gib die Datei nur an Menschen, denen du vertraust.

**Hinweise für Empfänger**
- Windows SmartScreen warnt bei unbekannten Programmen: "Weitere Informationen" → "Trotzdem ausführen".
- Manche Virenscanner melden Tastatur-Hooks fälschlich. Dann Ausnahme für `SpeakIt.exe` setzen.
- Deinstallieren: Einstellungen → "Deinstallieren" (Daten in `%APPDATA%\SpeakIt` bleiben, Ordner nach Wunsch löschen).
- Update: neue EXE einmal öffnen. Läuft die alte noch, vorher im Tray beenden.

## Technik
- Python 3.10+, `keyboard` (Low-Level-Hook mit Unterdrückung), `sounddevice`, `customtkinter`, `pystray`
- Hook wird nach Standby neu installiert, Stille wird lokal erkannt und nie an die API geschickt
- Keys nur in `.env` (per `.gitignore` ausgeschlossen)
