"""Struktur-Modus, Übersetzen, Umschreiben, Anbieter-Wahl und Mehrfach-Tippen.  Start: python -m unittest tests.test_modes

Läuft auch ohne Windows: Tastatur-, Audio- und UI-Module werden durch Attrappen ersetzt.
"""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _stub(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules.setdefault(name, m)
    return sys.modules[name]


class _Dummy:
    def __init__(self, *a, **k):
        self.enabled = True
        self.cancel_armed = None

    def __getattr__(self, _name):
        return lambda *a, **k: None


# Windows-only Abhängigkeiten von speakit.app ersetzen
_stub("pyperclip", copy=lambda *_: None, paste=lambda: "")
_stub("pystray", Menu=_Dummy, MenuItem=_Dummy, Icon=_Dummy)
_stub("speakit.hotkey", HotkeyManager=_Dummy, pretty=lambda n: "+".join(n))
_stub("speakit.audio", Recorder=_Dummy, has_speech=lambda _p: True, to_wav=lambda _p: b"")
_stub("speakit.ui", UI=_Dummy)
_stub("speakit.icon", drop_icon=lambda *a: None)
_stub("speakit.paste", active_window_title=lambda: "", copy_selection=lambda _h: ("", ""),
      paste_text=lambda *a, **k: None)
_stub("speakit.sounds", play=lambda *a: None, plop=lambda: None)
_stub("speakit.updater", start_background=lambda **k: None, start_source_updates=lambda **k: None)

from speakit import cleanup, llm, storage  # noqa: E402
from speakit.config import DEFAULTS  # noqa: E402


class Cfg(dict):
    data = property(lambda self: self)

    def set(self, **kw):
        self.update(kw)


def cfg(**kw):
    return Cfg({**DEFAULTS, **kw})


class Provider(unittest.TestCase):
    def test_order_prefers_choice_and_skips_missing_keys(self):
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "g", "ANTHROPIC_API_KEY": "a"}, clear=True):
            self.assertEqual(llm.order("groq"), ["groq", "claude"])
            self.assertEqual(llm.order("claude"), ["claude", "groq"])
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "g"}, clear=True):
            self.assertEqual(llm.order("claude"), ["groq"])
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(llm.order("groq"), [])

    def test_fallback_to_second_provider(self):
        calls = []

        def groq(*a):
            calls.append("groq")
            raise llm.LlmError("Groq 429: rate limit")

        def claude(*a):
            calls.append("claude")
            return "<transcript>Hallo Welt.</transcript>", 10, 3

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "g", "ANTHROPIC_API_KEY": "a"}, clear=True), \
                mock.patch.object(llm, "_groq", groq), mock.patch.object(llm, "_claude", claude):
            text, prov, t_in, t_out = llm.complete("s", "u", cfg(), 100, 5)
        self.assertEqual(calls, ["groq", "claude"])
        self.assertEqual((text, prov, t_in, t_out), ("Hallo Welt.", "claude", 10, 3))

    def test_strip_wrappers(self):
        self.assertEqual(llm.strip_wrappers("```markdown\n- a\n- b\n```"), "- a\n- b")
        self.assertEqual(llm.strip_wrappers(" <text>x</text> "), "x")


class Process(unittest.TestCase):
    def run_mode(self, mode, raw, answer="OK", **kw):
        seen = {}

        def fake(system, user, c, max_tokens, timeout):
            seen.update(system=system, user=user)
            return answer, "groq", 50, 20

        with mock.patch.object(llm, "complete", fake):
            out = cleanup.process(mode, raw, kw.pop("c", cfg()), {"terms": ["Claude Code"]}, "", **kw)
        return out, seen

    def test_raw_never_calls_ai(self):
        with mock.patch.object(llm, "complete", side_effect=AssertionError):
            self.assertEqual(cleanup.process("raw", "hallo", cfg(), {}, ""), ("hallo", "", 0, 0))

    def test_short_clean_skips_ai(self):
        with mock.patch.object(llm, "complete", side_effect=AssertionError):
            self.assertEqual(cleanup.process("clean", "kurz und gut", cfg(), {}, "")[1], "")

    def test_structure_prompt_and_markdown(self):
        note = "**Kernaussage:** Test.\n\n**To-dos**\n- [ ] Angebot schicken"
        (text, prov, *_), seen = self.run_mode("structure", "ich muss noch das angebot schicken", note)
        self.assertEqual((text, prov), (note, "groq"))
        self.assertIn("Kernaussage", seen["system"])
        self.assertIn("To-dos", seen["system"])
        self.assertIn("<transcript>", seen["user"])

    def test_structure_plain_format(self):
        note = "**Kernaussage:** Test.\n\n**Punkte**\n- eins\n  - zwei\n\n**To-dos**\n- [ ] drei"
        (text, *_), _ = self.run_mode("structure", "eins zwei drei", note, c=cfg(structure_format="plain"))
        self.assertEqual(text, "Kernaussage: Test.\n\nPunkte\n• eins\n  • zwei\n\nTo-dos\n☐ drei")

    def test_translate_overrides_no_translation_rule(self):
        (_t, prov, *_), seen = self.run_mode("raw", "hallo", "Hello", target_lang="Englisch")
        self.assertEqual(prov, "groq")  # 1x tippen mit Übersetzen nutzt die KI
        self.assertIn("auf Englisch", seen["system"])
        self.assertNotIn("nichts übersetzen", seen["system"])
        (_t, _p, *_), seen = self.run_mode("structure", "hallo welt", "x", target_lang="Spanisch")
        self.assertNotIn("Sprache des Transkripts", seen["system"])

    def test_rewrite_uses_selection_and_instruction(self):
        (text, prov, *_), seen = self.run_mode("rewrite", "mach das kürzer", "Kurz.", selection="Ein langer Text.")
        self.assertEqual((text, prov), ("Kurz.", "groq"))
        self.assertIn("<text>Ein langer Text.</text>", seen["user"])
        self.assertIn("<anweisung>mach das kürzer</anweisung>", seen["user"])

    def test_failure_returns_original(self):
        with mock.patch.object(llm, "complete", side_effect=llm.LlmError("down")):
            self.assertEqual(cleanup.process("structure", "a b c", cfg(), {}, ""), ("a b c", "", 0, 0))
            self.assertEqual(cleanup.process("rewrite", "kürzer", cfg(), {}, "", selection="Text")[0], "Text")

    def test_implausibly_long_answer_rejected(self):
        (text, *_), _ = self.run_mode("clean", "eins zwei drei vier fünf sechs", "x" * 500)
        self.assertEqual(text, "eins zwei drei vier fünf sechs")


class HistoryModes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        storage.HISTORY_PATH = Path(self.tmp.name) / "h.db"
        self.h = storage.History()

    def tearDown(self):
        self.tmp.cleanup()

    def test_mode_search_convert_export(self):
        a = self.h.add("roh eins", "Erster Text", 3, 0, 0, 0.0, ts=1_700_000_000)
        self.h.add("roh 100%", "Zweiter Text", 3, 10, 5, 0.001, ts=1_700_000_060, mode="clean")
        self.assertEqual([r["text"] for r in self.h.recent(query="erster")], ["Erster Text"])
        self.assertEqual([r["text"] for r in self.h.recent(query="100%")], ["Zweiter Text"])
        self.assertEqual(len(self.h.recent(query="%")), 1)  # % ist kein Platzhalter
        self.h.update_text(a, "**Kernaussage:** Eins.", "structure+Englisch", 7, 3, 0.002)
        row = next(r for r in self.h.recent() if r["id"] == a)
        self.assertEqual((row["mode"], row["tok_in"], row["tok_out"]), ("structure+Englisch", 7, 3))
        self.assertEqual(storage.mode_label(row["mode"]), "Struktur · Englisch")
        md = storage.export_markdown(self.h.recent())
        self.assertTrue(md.startswith("# SpeakIt-Verlauf"))
        self.assertLess(md.index("Kernaussage"), md.index("Zweiter Text"))  # älteste zuerst
        self.assertIn("(Struktur · Englisch)", md)

    def test_old_database_gets_mode_column(self):
        import sqlite3
        path = Path(self.tmp.name) / "alt.db"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE dictations (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, raw TEXT, text TEXT, "
                   "audio_s REAL, tok_in INTEGER, tok_out INTEGER, cost REAL)")
        db.execute("INSERT INTO dictations (ts, raw, text, audio_s, tok_in, tok_out, cost) VALUES (1,'r','t',1,0,0,0)")
        db.commit()
        db.close()
        storage.HISTORY_PATH = path
        self.assertEqual(storage.History().recent()[0]["mode"], "")

    def test_cost_per_provider(self):
        self.assertAlmostEqual(storage.llm_cost(1_000_000, 0, "groq"), 0.15)
        self.assertAlmostEqual(storage.llm_cost(1_000_000, 0, "claude"), 1.0)
        self.assertEqual(storage.llm_cost(0, 0, ""), 0)


class Taps(unittest.TestCase):
    """Mehrfach-Tippen: 1x Rohtext, 2x Feinschliff, 3x Struktur, auch im Modus Halten."""

    def make(self, **kw):
        from speakit import app as app_mod
        a = app_mod.App.__new__(app_mod.App)
        import threading
        a.cfg = cfg(**kw)
        a.lock = threading.Lock()
        a.recording = False
        a.press_started = False
        a.press_t = a.start_t = a.last_tap_t = a.tap_t = 0.0
        a.taps, a.level, a.kind = 0, 0, "dictate"
        a.ui = _Dummy()
        a.stopped = []

        def start(kind="dictate"):
            a.recording, a.kind = True, kind
            a.level = a._base_level() if kind == "dictate" else 0
            return True

        def stop():
            a.recording = False
            a.stopped.append("rewrite" if a.kind == "rewrite" else app_mod.LEVELS[a.level])

        def cancel(locked=False):
            a.recording = False

        a._start, a._stop, a.cancel = start, stop, cancel
        return a, app_mod

    def tap(self, a, mod, t, hold=0.05, kind="dictate"):
        with mock.patch.object(mod.time, "time", return_value=t):
            a.on_press(kind)
        with mock.patch.object(mod.time, "time", return_value=t + hold):
            a.on_release(kind)

    def test_toggle_levels(self):
        for taps, expected in ((1, "raw"), (2, "clean"), (3, "structure")):
            a, mod = self.make(mode="both")
            for i in range(taps):
                self.tap(a, mod, 100 + i * 0.2)
            self.assertTrue(a.recording)
            self.tap(a, mod, 110)  # später nochmal tippen = Stopp
            self.assertEqual(a.stopped, [expected], taps)
        a, mod = self.make(mode="both")
        for i in range(4):  # ein 4. schneller Tipp stoppt (höchste Stufe erreicht)
            self.tap(a, mod, 100 + i * 0.2)
        self.assertEqual(a.stopped, ["structure"])

    def test_slow_second_tap_stops(self):
        a, mod = self.make(mode="both")
        self.tap(a, mod, 100)
        self.tap(a, mod, 101)
        self.assertEqual(a.stopped, ["raw"])

    def test_tap_tap_hold_in_both_mode(self):
        a, mod = self.make(mode="both")
        self.tap(a, mod, 100)
        self.tap(a, mod, 100.2)
        self.tap(a, mod, 100.4, hold=3)  # dritter Druck gehalten, Loslassen stoppt
        self.assertEqual(a.stopped, ["structure"])

    def test_hold_mode_tap_then_hold(self):
        for taps, expected in ((0, "raw"), (1, "clean"), (2, "structure")):
            a, mod = self.make(mode="hold")
            for i in range(taps):
                self.tap(a, mod, 100 + i * 0.2)  # kurzer Tipp bricht ab und zählt
            self.assertFalse(a.recording)
            self.tap(a, mod, 100 + taps * 0.2, hold=2)
            self.assertEqual(a.stopped, [expected], taps)

    def test_always_trigger_shifts_levels(self):
        a, mod = self.make(mode="both", clean_trigger="always")
        self.tap(a, mod, 100)
        self.tap(a, mod, 110)
        self.assertEqual(a.stopped, ["clean"])
        a, mod = self.make(mode="both", clean_trigger="always")
        self.tap(a, mod, 100)
        self.tap(a, mod, 100.2)
        self.tap(a, mod, 110)
        self.assertEqual(a.stopped, ["structure"])

    def test_cleanup_off_disables_taps(self):
        a, mod = self.make(mode="both", cleanup=False)
        self.tap(a, mod, 100)
        self.tap(a, mod, 100.2)
        self.assertEqual(a.stopped, ["raw"])

    def test_rewrite_key_has_no_levels(self):
        a, mod = self.make(mode="both")
        self.tap(a, mod, 100, kind="rewrite")
        self.tap(a, mod, 100.2, kind="rewrite")
        self.assertEqual(a.stopped, ["rewrite"])


if __name__ == "__main__":
    unittest.main()
