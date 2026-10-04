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

## Anzeige beim Sprechen

Unten mittig fährt eine kleine Kapsel aus der Mitte auf: roter Punkt, runde Pegelbalken, Sekundenticker. Beim Verarbeiten füllt sich eine orange Flüssigkeit (Wellen, Schwappen, Spritzer) bis zur Decke. Ist sie voll, ist der Text eingefügt und die Kapsel klappt wieder zu.

## Fenster

- **Schalter links oben**: SpeakIt an/aus. Aus heißt, die Taste wird nicht mehr abgefangen. Auch im Tray ("SpeakIt aktiv").
- **Nachbearbeitung** (zweiter Schalter): Claude Haiku glättet den Text. Aus ist bis zu 2x schneller und deutlich günstiger, dafür Rohtext. Der Vergleich steht in den Einstellungen.
- **Verlauf**: letzte Diktate, kopieren, "Original" ansehen. Jedes Wort ist anklickbar (oder mehrere markieren): richtiges Wort eintragen, Kontext wählen, SpeakIt ersetzt es künftig automatisch.
- **Kontexte**: Themen mit Begriffen und festen Korrekturen (Re:Zero, Fantasy, Webdesign, SEO & GEO, Business, KI & Cloud, eigene). Aktive gehen an Whisper und Claude, inaktive kennt Claude und nutzt sie nur bei passendem Thema.
- **Statistik**: Diktate, Wörter, Sprechzeit, Token, Kosten für Heute, Monat, Gesamt. Heute setzt sich um 0 Uhr zurück, Monat am 1., Gesamt nie. Links unten steht es immer. Test: `python -m unittest tests.test_stats`.
- **Einstellungen**: Taste oder Tastenkombination, Modus, Sprache, Mikrofon, Anbieter, 8 Klang-Presets (Sanft, Blub, Tropfen, Klack, Marimba, Glas, Pop, Pad), Autostart, Keys.
- **Tutorial**: öffnet sich beim ersten Start, danach über "Tutorial anzeigen" links unten.

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
