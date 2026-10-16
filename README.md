# SpeakIt

Diktieren in jedes Textfeld unter Windows. Taste halten oder tippen, sprechen, Text erscheint.

Ablauf: Mikrofon → Groq Whisper (Text) → kostenlose Vorreinigung (Füllwörter, Doppler) → bei 2x Tippen Feinschliff, bei 3x Tippen Struktur-Notiz mit To-dos (KI: Groq gratis oder Claude Haiku) → Einfügen per Strg+V.

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

Der Groq-Key reicht auch für Feinschliff, Struktur, Übersetzen und Umschreiben: Groq bietet neben Whisper Sprachmodelle an (Standard `openai/gpt-oss-120b`), im Gratis-Tarif kostenlos mit Minuten- und Tageslimit. Eine zusätzliche App oder ein weiterer Key ist nicht nötig.

**Anthropic (optional)**: console.anthropic.com → Billing: Guthaben aufladen und Monatslimit setzen → API Keys → Create Key (`sk-ant-…`). Unter Einstellungen → "KI-Anbieter" lässt sich Claude Haiku statt Groq wählen. Ist für beide Anbieter ein Key hinterlegt, springt der andere automatisch ein, wenn einer ausfällt oder das Limit erreicht ist.

## Bedienung

| Aktion | Wirkung |
|---|---|
| Taste halten | Aufnahme läuft, beim Loslassen wird eingefügt |
| Taste kurz tippen | Aufnahme startet, nochmal tippen stoppt |
| 2x schnell tippen | Feinschliff durch die KI (roter Punkt) |
| 3x schnell tippen | Struktur: Kernaussage, Stichpunkte, To-dos (violetter Punkt) |
| Umschalt + F9 (einstellbar) | Markierten Text per Sprachanweisung umschreiben ("kürzer", "freundlicher", "auf Englisch"), blauer Punkt |
| Esc während Aufnahme | Abbrechen |

Im Modus "Halten" gilt: kurz tippen, dann halten = Feinschliff; zweimal tippen, dann halten = Struktur.

**Struktur-Notiz** (3x tippen) aus "ähm also ich muss bis Freitag noch das Angebot an Müller schicken und äh das Logo fehlt noch":
```
**Kernaussage:** Angebot für Müller bis Freitag fertigstellen.

**Punkte**
- Logo fehlt noch

**To-dos**
- [ ] Angebot an Müller bis Freitag schicken
- [ ] Logo besorgen
```
Für Word oder Outlook unter Einstellungen → "Struktur-Format" auf Klartext stellen (• und ☐ statt Markdown).

**Übersetzen**: Schalter links in der Seitenleiste (oder im Tray). Jedes Diktat wird direkt in der gewählten Sprache eingefügt (Englisch, Französisch, Spanisch, …).

- Die Taste ist komplett belegt (`M` oder `F11` tippt nichts mehr). Bei Kombinationen wird nur die letzte Taste geschluckt.
- **Copilot-Taste**: Einstellungen → "Copilot-Taste" (sendet Win + Umschalt + F23, F23 wird geschluckt).
- Das Overlay unten zeigt Pegel und Sekundenticker, danach den Status.
- Sprachbefehle im Diktat: "neue Zeile", "neuer Absatz", "Punkt", "Komma", "Fragezeichen".

## Design

Orange Tropfen als Symbol (App, Tray, Fenster). In Buttons und im gewählten Menüpunkt fließt orange Flüssigkeit ein und beim Verlassen sofort wieder ab. Die Titelleiste ist dezent orange (Windows 11).

## Anzeige beim Sprechen

Unten mittig fährt eine kleine Kapsel aus der Mitte auf: oranger Punkt (schwabbelt leicht mit der Lautstärke), runde Pegelbalken, Sekundenticker, orange Kontur. Beim Verarbeiten füllt sich eine orange Flüssigkeit (Wellen, Schwappen, Spritzer) bis zur Decke. Ist sie voll, ist der Text eingefügt und die Kapsel klappt wieder zu.

## Fenster

- **Schalter links oben**: SpeakIt an/aus. Aus heißt, die Taste wird nicht mehr abgefangen. Auch im Tray ("SpeakIt aktiv").
- **Nachbearbeitung** (zweiter Schalter): die KI glättet den Text. Standard: nur nach **Doppeltipp** auf die Taste (im Modus "Halten": kurz tippen, dann halten), der Punkt in der Anzeige wird dann rot. **Dreifachtipp** macht eine Struktur-Notiz (violetter Punkt). Einfaches Drücken bleibt schnell und kostenlos. In den Einstellungen unter "Feinschliff (KI)" auf "Bei jeder Aufnahme" umstellbar (dann ergibt 2x Tippen die Struktur). Unter 6 Wörtern wird nie geglättet, und es gehen nur Begriffe mit, die im Diktat vorkommen oder ähnlich klingen. Aus = kein Mehrfach-Tippen, nur Rohtext.
- **Übersetzen** (dritter Schalter): Zielsprache wählen, jedes Diktat kommt übersetzt an.
- **Verlauf**: letzte Diktate, durchsuchen, als Markdown exportieren, kopieren, "Original" ansehen. "Glätten" und "Struktur" wandeln ein altes Diktat nachträglich um und kopieren das Ergebnis. Jedes Wort ist anklickbar (oder mehrere markieren): richtiges Wort eintragen, Kontext wählen, SpeakIt ersetzt es künftig automatisch.
- **Kontexte**: Themen mit Begriffen und festen Korrekturen (Re:Zero, Fantasy, Webdesign, SEO & GEO, Business, KI & Cloud, eigene). Aktive gehen an Whisper und Claude, inaktive kennt Claude und nutzt sie nur bei passendem Thema.
- **Statistik**: Diktate, Wörter, Sprechzeit, Token, Kosten für Heute, Monat, Gesamt. Heute setzt sich um 0 Uhr zurück, Monat am 1., Gesamt nie. Links unten steht es immer. Tests: `python -m unittest tests.test_stats tests.test_modes`.
- **Einstellungen**: Taste oder Tastenkombination, Umschreiben-Taste, Modus, KI-Anbieter (Groq/Claude) und Groq-Modell, Struktur-Format, Übersetzen, Sprache, Mikrofon, Anbieter, 8 Klang-Presets (Sanft, Blub, Tropfen, Klack, Marimba, Glas, Pop, Pad), Autostart, Keys.
- **Tutorial**: öffnet sich beim ersten Start, danach über "Tutorial anzeigen" links unten.

## Kosten (Listenpreise aus dem Gedächtnis, vor Nutzung prüfen)

- Groq whisper-large-v3-turbo: ca. 0,04 $ pro Stunde Audio (Gratis-Tarif mit Limits)
- Groq gpt-oss-120b (Feinschliff/Struktur, Standard): ca. 0,15 $ pro Mio. Eingabe-Token, 0,60 $ pro Mio. Ausgabe-Token, im Gratis-Tarif 0 $
- Claude Haiku 4.5 (optional): ca. 1 $ pro Mio. Eingabe-Token, 5 $ pro Mio. Ausgabe-Token
- Pro Diktat gehen Prompt und Begriffslisten mit (ca. 2.000 bis 3.000 Token): grob 0,3 bis 0,5 Cent pro Minute Sprechen

## Installation in einem Schritt (empfohlen, kostenlos)

PowerShell öffnen (Windows-Taste, "PowerShell" tippen, Enter) und einfügen:
```
irm https://raw.githubusercontent.com/kortjannis-web/SpeakIt-App/master/setup.ps1 | iex
```
Das installiert bei Bedarf Git und Python (über winget), lädt SpeakIt nach `%LOCALAPPDATA%\SpeakIt-App`, richtet Startmenü und Autostart ein und startet die App. Updates holt sich die App danach selbst von GitHub (beim Start und alle 6 Stunden), aktiv beim nächsten Start oder sofort über den Tray: "Update aktivieren (Neustart)".

Warum nicht die EXE? Die EXE ist nicht digital signiert. Ist in Windows 11 die "Intelligente App-Steuerung" an, wird sie komplett blockiert. Der Weg über Python läuft auch dort.

## Download: eine EXE, läuft auch mit Smart App Control

https://github.com/kortjannis-web/SpeakIt-App/releases/latest/download/SpeakIt-Installer.exe

Doppelklick. Beim ersten Mal richtet sie SpeakIt ein (Git, Python, Startmenü, Autostart, sichtbares Fenster mit Fortschritt). Danach startet dieselbe EXE SpeakIt direkt. Updates holt sich die App selbst von GitHub.

## Download als EXE und Auto-Update

Download für alle (ohne Keys, Empfänger trägt eigene Keys ein):
https://github.com/kortjannis-web/SpeakIt-App/releases/latest/download/SpeakIt.exe

Jeder Push auf `master` baut per GitHub Actions automatisch eine neue `SpeakIt.exe` und veröffentlicht sie als Release (Version `1.0.<Laufnummer>`). Reine README-Änderungen lösen keinen Build aus. Die installierte App prüft beim Start und danach alle 6 Stunden, lädt eine neuere Version im Hintergrund und setzt sie beim nächsten Start ein. Sofort geht es über den Tray: "Update installieren (Neustart)".

## EXE selbst bauen

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
- Updates kommen automatisch (siehe oben). Mitgelieferte Keys werden beim ersten Start in `%APPDATA%\SpeakIt\.env` gesichert und bleiben nach Updates erhalten.

## Technik
- Python 3.10+, `keyboard` (Low-Level-Hook mit Unterdrückung), `sounddevice`, `customtkinter`, `pystray`
- Hook wird nach Standby neu installiert, Stille wird lokal erkannt und nie an die API geschickt
- Keys nur in `.env` (per `.gitignore` ausgeschlossen)
