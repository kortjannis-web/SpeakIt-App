# SpeakIt

Diktieren in jedes Textfeld unter Windows. Taste halten oder tippen, sprechen, Text erscheint.

Ablauf: Mikrofon → Groq Whisper (Text) → Claude Haiku (Füllwörter weg, Zeichensetzung, Begriffsliste) → Einfügen per Strg+V.

## Installation (einmalig, ca. 3 Minuten)

1. PowerShell im Projektordner öffnen und ausführen:
   ```
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
2. Es startet im Tray (Mikrofon-Symbol unten rechts, ggf. hinter dem Pfeil). Beim ersten Start öffnen sich die Einstellungen.
3. Zwei API-Keys eintragen (siehe unten), Taste wählen, Speichern.

Ab dann startet es bei jeder Windows-Anmeldung unsichtbar von selbst.

### Über Admin-Fenster diktieren (optional)
Windows blockt Hotkeys in Fenstern, die als Administrator laufen. Dafür einmal in einer **Administrator-PowerShell**:
```
powershell -ExecutionPolicy Bypass -File install.ps1 -Admin
```

## API-Keys (das musst du selbst machen)

**Groq (Sprache zu Text)**
1. https://console.groq.com registrieren, anmelden.
2. Links "API Keys" → "Create API Key" → Key kopieren (beginnt mit `gsk_`).
3. In SpeakIt unter "Groq API-Key" einfügen.

**Anthropic (Textnachbearbeitung)**
1. https://console.anthropic.com registrieren, anmelden.
2. "Billing": Guthaben aufladen (5 $ reichen lange) und ein monatliches Limit setzen.
3. "API Keys" → "Create Key" → Key kopieren (beginnt mit `sk-ant-`).
4. In SpeakIt unter "Anthropic API-Key" einfügen.

Ohne Anthropic-Key funktioniert SpeakIt weiter, nur ohne Nachbearbeitung (Rohtext von Whisper).
Setze auch bei Groq ein Ausgabenlimit, sobald du auf einen bezahlten Tarif wechselst.

## Bedienung

| Aktion | Wirkung |
|---|---|
| Taste halten | Aufnahme läuft, beim Loslassen wird eingefügt |
| Taste kurz tippen | Aufnahme startet, nochmal tippen stoppt |
| Esc während Aufnahme | Abbrechen |

- Die gewählte Taste ist komplett belegt (z. B. `M` oder `F11` tippt nichts mehr, die Taste hat nur diese Funktion).
- Bei Kombinationen (z. B. `Strg + Alt + Leertaste`) wird nur die letzte Taste geschluckt. Die Einzeltasten funktionieren normal.
- Taste ändern: Tray-Symbol → Einstellungen → Button anklicken → Taste oder Kombi drücken → loslassen.
- Sprachbefehle im Diktat: "neue Zeile", "neuer Absatz", "Punkt", "Komma", "Fragezeichen".
- Letzten Text nochmal: Tray → "Letzten Text kopieren". Bei Netzwerkfehlern landet die Aufnahme in `failed\`.

## Begriffsliste

`vocabulary.txt` (Tray → "Begriffsliste öffnen"): ein Begriff pro Zeile, wird Whisper und Claude mitgegeben. Feste Ersetzungen mit `falsch => richtig`. Das ist der größte Qualitätshebel für Namen und Fachwörter.

## Kosten (Listenpreise aus dem Gedächtnis, vor Nutzung prüfen)

- Groq whisper-large-v3-turbo: ca. 0,04 $ pro Stunde Audio (min. 10 s pro Anfrage abgerechnet)
- Claude Haiku 4.5: ca. 1 $ pro Mio. Eingabe-Tokens, 5 $ pro Mio. Ausgabe-Tokens
- 10.000 Wörter diktiert: grob 0,10 bis 0,20 $ gesamt

Details pro Diktat (Dauer, Latenz) stehen in `speakit.log`.

## Deinstallieren
```
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```

## Technik
- Python 3.10+, `keyboard` (globaler Low-Level-Hook mit Unterdrückung), `sounddevice`, `pystray`, `tkinter`
- Hook wird nach Standby automatisch neu installiert
- Stille wird lokal erkannt und nie an die API geschickt
- Keys liegen nur in `.env` (per `.gitignore` ausgeschlossen)
