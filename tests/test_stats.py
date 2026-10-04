"""Prüft, dass Heute und Monat sich zurücksetzen und Gesamt nie.  Start: python -m unittest tests.test_stats"""
import datetime
import tempfile
import unittest
from pathlib import Path

from speakit import storage


class StatsReset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        storage.HISTORY_PATH = Path(self.tmp.name) / "h.db"
        self.h = storage.History()

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, when, words=10):
        self.h.add("r", " ".join(["w"] * words), 6.0, 100, 20, 0.01, ts=when.timestamp())

    def stats(self, now):
        s = storage.period_starts(now)
        return {k: self.h.stats(v) for k, v in s.items()}

    def test_day_and_month_boundaries(self):
        D = datetime.datetime
        now = D(2026, 10, 4, 16, 0)
        self.add(D(2026, 9, 30, 23, 59, 59))   # Vormonat
        self.add(D(2026, 10, 1, 0, 0, 1))      # Monatsanfang
        self.add(D(2026, 10, 3, 23, 59, 59))   # gestern
        self.add(D(2026, 10, 4, 0, 0, 1))      # heute früh
        self.add(D(2026, 10, 4, 15, 59))       # heute
        s = self.stats(now)
        self.assertEqual(s["Heute"]["count"], 2)
        self.assertEqual(s["Monat"]["count"], 4)
        self.assertEqual(s["Gesamt"]["count"], 5)

    def test_rollover_at_midnight(self):
        D = datetime.datetime
        self.add(D(2026, 10, 4, 23, 30))
        before = self.stats(D(2026, 10, 4, 23, 59))
        after = self.stats(D(2026, 10, 5, 0, 1))
        self.assertEqual(before["Heute"]["count"], 1)
        self.assertEqual(after["Heute"]["count"], 0)   # Tag zurückgesetzt
        self.assertEqual(after["Monat"]["count"], 1)   # Monat läuft weiter
        self.assertEqual(after["Gesamt"]["count"], 1)

    def test_rollover_at_month_end(self):
        D = datetime.datetime
        self.add(D(2026, 10, 31, 22, 0))
        after = self.stats(D(2026, 11, 1, 0, 5))
        self.assertEqual(after["Heute"]["count"], 0)
        self.assertEqual(after["Monat"]["count"], 0)   # Monat zurückgesetzt
        self.assertEqual(after["Gesamt"]["count"], 1)  # Gesamt bleibt

    def test_total_never_resets(self):
        D = datetime.datetime
        for i in range(30):
            self.add(D(2026, 1, 1) + datetime.timedelta(days=10 * i))
        for now in (D(2026, 6, 1), D(2027, 1, 1), D(2030, 12, 31, 23, 59)):
            self.assertEqual(self.stats(now)["Gesamt"]["count"], 30)


if __name__ == "__main__":
    unittest.main()


def test_preclean():
    from speakit.precleanup import preclean
    assert preclean("ähm, also ich ich wollte, äh, sagen .") == "Also ich wollte sagen."
    assert preclean("Leute, die die Regeln kennen") == "Leute, die die Regeln kennen"
    assert preclean("Ich habe 3,5 Euro. äh ja") == "Ich habe 3,5 Euro. Ja"


def test_relevant_terms():
    from speakit.cleanup import relevant
    hit = relevant(["Claude Code", "Betelgeuse", "Magie", "Wyvern"], "ich nutze cloud code und petelgeus mit maggi")
    assert hit == ["Claude Code", "Betelgeuse", "Magie"]
