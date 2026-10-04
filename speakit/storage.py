"""Kontexte (Begriffe + Korrekturen) und Verlauf mit Token-Statistik."""
import json
import re
import sqlite3
import threading
import time
import uuid

from .config import CONTEXTS_PATH, HISTORY_PATH

# ---------------------------------------------------------------- Kosten
GROQ_PER_HOUR = 0.04
OPENAI_PER_MIN = 0.003
HAIKU_IN, HAIKU_OUT = 1.0 / 1e6, 5.0 / 1e6


def stt_cost(provider: str, secs: float) -> float:
    if provider == "openai":
        return secs / 60 * OPENAI_PER_MIN
    return max(secs, 10) / 3600 * GROQ_PER_HOUR


def llm_cost(tok_in: int, tok_out: int) -> float:
    return tok_in * HAIKU_IN + tok_out * HAIKU_OUT


# ---------------------------------------------------------------- Kontexte
def _split(text: str) -> list[str]:
    return [t.strip() for t in re.split(r"[\n,;]", text) if t.strip()]


DEFAULT_CONTEXTS = [
    {
        "id": "general", "name": "Allgemein", "active": True,
        "terms": ["TOPsichtbar", "Claude Code", "Claude", "Anthropic", "SpeakIt", "Hostinger", "GitHub"],
        "repl": [["claude code", "Claude Code"]],
    },
    {
        "id": "rezero", "name": "Re:Zero", "active": True,
        "terms": _split(
            "Re:Zero, Subaru Natsuki, Subaru, Emilia, Rem, Ram, Beatrice, Puck, Roswaal, Reinhard, Felt, "
            "Wilhelm, Julius, Echidna, Satella, Betelgeuse, Sirius, Regulus, Lye, Capella, Elsa, Otto, Garfiel, "
            "Anastasia, Priscilla, Crusch, Petra, Frederica, Hexenkult, Unseen Hands, Invisible Providence, "
            "Rückkehr durch den Tod, Lugunica, Sanctuary, Pleiades, Flügel, Erzbischof, Sünde, Autorität, Hexe"
        ),
        "repl": [["Iketna", "Echidna"], ["Ikidna", "Echidna"], ["Petekus", "Betelgeuse"], ["Petelgeuse", "Betelgeuse"]],
    },
    {
        "id": "fantasy", "name": "Fantasy & Alchemie", "active": True,
        "terms": _split(
            "Magie, Zauberspruch, Mana, Grimoire, Rune, Artefakt, Alchemie, Alchemist, Homunculus, "
            "Philosophenstein, Transmutation, Elixier, Quintessenz, Athanor, Destillation, Nekromant, "
            "Beschwörung, Elementar, Paladin, Druide, Kleriker, Barde, Hexenmeister, Zauberer, Magier, "
            "Zwerg, Elf, Ork, Troll, Drache, Greif, Basilisk, Phönix, Golem, Lich, Wyvern, Chimäre, "
            "Pentagramm, Ritual, Familiar, Zauberstab, Schwertmeister, Rollenspiel, Dungeon, Quest, Mana-Pool"
        ),
        "repl": [["Maggi", "Magie"]],
    },
    {
        "id": "webdesign", "name": "Webdesign & Entwicklung", "active": True,
        "terms": _split(
            "Hero Section, Header, Footer, Column, Spalte, Grid, Flexbox, Breakpoint, Mobile First, Responsive, "
            "Viewport, Call to Action, CTA, Sticky Header, Dropdown, Hamburger-Menü, Modal, Accordion, Carousel, "
            "Slider, Card, Badge, Tooltip, Navbar, Sidebar, Landingpage, Wireframe, Mockup, Prototyp, Figma, "
            "Tailwind CSS, Next.js, React, TypeScript, Framer Motion, shadcn/ui, Padding, Margin, Border Radius, "
            "Z-Index, Overflow, Opacity, Gradient, Backdrop Blur, Favicon, Alt-Text, Lazy Loading, "
            "Core Web Vitals, SEO, Meta-Description, Sitemap, Schema Markup, JSON-LD, Canonical, Kontaktformular, "
            "Impressum, Datenschutz, Cookie-Banner, Coolify, Traefik, Dockerfile, VPS, DNS, A-Record, SSL, "
            "Repository, Commit, Deployment, Pull Request, Vercel, Hover-Effekt, Scroll-Animation, Parallax, "
            "Lightbox, Testimonials, Pricing Section, FAQ-Section, Above the Fold, Whitespace, Typografie, "
            "Kontrast, Barrierefreiheit, Komponente, Section, Button, Container"
        ),
        "repl": [["Herosection", "Hero Section"], ["Hero Sektion", "Hero Section"]],
    },
]


class Contexts:
    def __init__(self):
        self.lock = threading.RLock()
        self.items: list[dict] = []
        self.load()

    def load(self):
        with self.lock:
            data = None
            if CONTEXTS_PATH.exists():
                try:
                    data = json.loads(CONTEXTS_PATH.read_text(encoding="utf-8"))["contexts"]
                except Exception:
                    data = None
            self.items = data or json.loads(json.dumps(DEFAULT_CONTEXTS))
            if not any(c["id"] == "general" for c in self.items):
                self.items.insert(0, json.loads(json.dumps(DEFAULT_CONTEXTS[0])))
            if not CONTEXTS_PATH.exists():
                self.save()

    def save(self):
        with self.lock:
            CONTEXTS_PATH.write_text(
                json.dumps({"contexts": self.items}, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def get(self, cid):
        return next((c for c in self.items if c["id"] == cid), None)

    def add(self, name: str) -> dict:
        with self.lock:
            c = {"id": uuid.uuid4().hex[:8], "name": name.strip() or "Neu", "active": True, "terms": [], "repl": []}
            self.items.append(c)
            self.save()
            return c

    def delete(self, cid):
        if cid == "general":
            return
        with self.lock:
            self.items = [c for c in self.items if c["id"] != cid]
            self.save()

    def update(self, cid, name=None, terms=None, repl=None, active=None):
        with self.lock:
            c = self.get(cid)
            if not c:
                return
            if name is not None:
                c["name"] = name.strip() or c["name"]
            if terms is not None:
                c["terms"] = terms
            if repl is not None:
                c["repl"] = repl
            if active is not None and cid != "general":
                c["active"] = active
            self.save()

    def add_correction(self, cid, wrong: str, right: str):
        """Lernen: 'falsch' wird künftig zu 'richtig', 'richtig' kommt in die Begriffe."""
        with self.lock:
            c = self.get(cid) or self.get("general")
            wrong, right = wrong.strip(), right.strip()
            if wrong and right and wrong.lower() != right.lower():
                c["repl"] = [r for r in c["repl"] if r[0].lower() != wrong.lower()] + [[wrong, right]]
            if right and right not in c["terms"]:
                c["terms"].append(right)
            self.save()

    # ---- Auswahl für die APIs ----
    def _active(self):
        return [c for c in self.items if c["active"] or c["id"] == "general"]

    def whisper_terms(self, max_chars=700) -> list[str]:
        """Whisper beachtet nur das Ende des Prompts, wichtigste Begriffe stehen daher zuletzt."""
        ordered = []
        for c in self._active():
            ordered += c["terms"]
        out, size = [], 0
        for t in reversed(ordered):
            size += len(t) + 2
            if size > max_chars:
                break
            out.append(t)
        return list(reversed(out))

    def llm_context(self) -> dict:
        act = self._active()
        other = [c for c in self.items if c not in act]
        return {
            "active": [c["name"] for c in act if c["id"] != "general"],
            "terms": [t for c in act for t in c["terms"]][:600],
            "other_terms": [f"{c['name']}: " + ", ".join(c["terms"][:60]) for c in other if c["terms"]],
            "repl_hints": [f"{a} -> {b}" for c in self.items for a, b in c["repl"]][:200],
        }

    def active_repl(self):
        return [(a, b) for c in self._active() for a, b in c["repl"]]


def apply_replacements(text: str, repl) -> str:
    for a, b in repl:
        text = re.sub(r"(?<!\w)" + re.escape(a) + r"(?!\w)", lambda _m, b=b: b, text, flags=re.IGNORECASE)
    return text


# ---------------------------------------------------------------- Verlauf
class History:
    def __init__(self):
        self.lock = threading.Lock()
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS dictations (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, "
                "raw TEXT, text TEXT, audio_s REAL, tok_in INTEGER, tok_out INTEGER, cost REAL)"
            )

    def _db(self):
        return sqlite3.connect(HISTORY_PATH)

    def add(self, raw, text, audio_s, tok_in, tok_out, cost) -> int:
        with self.lock, self._db() as db:
            cur = db.execute(
                "INSERT INTO dictations (ts, raw, text, audio_s, tok_in, tok_out, cost) VALUES (?,?,?,?,?,?,?)",
                (time.time(), raw, text, audio_s, tok_in, tok_out, cost),
            )
            return cur.lastrowid

    def recent(self, limit=40, offset=0) -> list[dict]:
        with self.lock, self._db() as db:
            rows = db.execute(
                "SELECT id, ts, raw, text, audio_s, tok_in, tok_out, cost FROM dictations "
                "ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset),
            ).fetchall()
        keys = ("id", "ts", "raw", "text", "audio_s", "tok_in", "tok_out", "cost")
        return [dict(zip(keys, r)) for r in rows]

    def delete(self, did):
        with self.lock, self._db() as db:
            db.execute("DELETE FROM dictations WHERE id=?", (did,))

    def stats(self, since: float = 0) -> dict:
        with self.lock, self._db() as db:
            r = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(audio_s),0), COALESCE(SUM(tok_in),0), COALESCE(SUM(tok_out),0), "
                "COALESCE(SUM(cost),0), COALESCE(SUM(LENGTH(text)-LENGTH(REPLACE(text,' ',''))+1),0) "
                "FROM dictations WHERE ts>=?", (since,),
            ).fetchone()
        return dict(count=r[0], audio_s=r[1], tok_in=r[2], tok_out=r[3], cost=r[4], words=r[5])
