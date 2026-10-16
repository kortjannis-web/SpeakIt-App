"""Kontexte (Begriffe + Korrekturen) und Verlauf mit Token-Statistik."""
import contextlib
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
GROQ_LLM_IN, GROQ_LLM_OUT = 0.15 / 1e6, 0.60 / 1e6  # gpt-oss-120b Listenpreis (im Gratis-Tarif 0 $)
LLM_PRICES = {"claude": (HAIKU_IN, HAIKU_OUT), "groq": (GROQ_LLM_IN, GROQ_LLM_OUT)}


def stt_cost(provider: str, secs: float) -> float:
    if provider == "openai":
        return secs / 60 * OPENAI_PER_MIN
    return max(secs, 10) / 3600 * GROQ_PER_HOUR


def llm_cost(tok_in: int, tok_out: int, provider: str = "claude") -> float:
    p_in, p_out = LLM_PRICES.get(provider, LLM_PRICES["claude"])
    return tok_in * p_in + tok_out * p_out


def cleanup_comparison(words=10000, per_dictation=125, overhead_tok=2500, wpm=140, provider="claude"):
    """Schätzung: Kosten pro `words` Wörter mit und ohne KI (overhead_tok = Prompt + Begriffslisten pro Diktat)."""
    groq = words / wpm / 60 * GROQ_PER_HOUR
    n = words / per_dictation
    text_tok = words * 1.5
    p_in, p_out = LLM_PRICES.get(provider, LLM_PRICES["claude"])
    haiku = (n * overhead_tok + text_tok) * p_in + text_tok * p_out
    return {"n": int(n), "groq": groq, "haiku": haiku, "with": groq + haiku, "without": groq,
            "factor": (groq + haiku) / groq}


# Wartezeit nach dem Loslassen in Sekunden (aus eigenen Messungen: Whisper ca. 1 bis 1,6 s, Haiku + Einfügen ca. 2,5 s)
WAIT = {"short": (15, 3.0, 1.3), "long": (120, 4.2, 1.8)}  # (Wörter, mit Haiku, ohne Haiku)


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
    {
        "id": "seogeo", "name": "SEO & GEO", "active": True,
        "terms": _split(
            "SEO, GEO, Generative Engine Optimization, Answer Engine Optimization, KI-Sichtbarkeit, "
            "AI Overviews, Perplexity, ChatGPT, Gemini, llms.txt, robots.txt, GPTBot, ClaudeBot, Crawler, "
            "Indexierung, Sitemap, Canonical, noindex, Backlink, Linkbuilding, Citation, NAP, "
            "Google Unternehmensprofil, Google Business Profile, Local SEO, Keyword, Suchintention, "
            "Long-Tail-Keyword, Meta-Title, Meta-Description, Title-Tag, Überschriftenstruktur, "
            "interne Verlinkung, Ankertext, Domain Authority, Core Web Vitals, LCP, CLS, INP, PageSpeed, "
            "Schema Markup, JSON-LD, FAQ-Schema, LocalBusiness, Entität, E-E-A-T, Search Console, "
            "Google Analytics, GA4, Clarity, Ahrefs, Semrush, Sistrix, SERP, Featured Snippet, Zero-Click, "
            "Ranking, Impressionen, Klickrate, CTR, Absprungrate, Content-Cluster, Pillar Page, "
            "Duplicate Content, Redirect, hreflang, Alt-Text, Rich Snippet, Zitierfähigkeit, Prompt-Set, "
            "Localo, Ortsseite, Antwortabsatz, Offpage, Onpage"
        ),
        "repl": [["Seo", "SEO"], ["Lokalo", "Localo"], ["Search Konsole", "Search Console"]],
    },
    {
        "id": "business", "name": "Business & Marketing", "active": True,
        "terms": _split(
            "Lead, Leadgenerierung, Funnel, Conversion, Conversion-Rate, Landingpage, Angebot, Retainer, "
            "Briefing, Relaunch, Onepager, CRM, Freshsales, Stripe, Calendly, Rechnung, Akquise, "
            "Kaltakquise, Newsletter, Klaviyo, HubSpot, Zielgruppe, Positionierung, USP, Customer Journey, "
            "ROI, KPI, Performance Marketing, Google Ads, Meta Ads, Retargeting, Social Media, "
            "Content Marketing, Testimonial, Social Proof, Case Study, Onboarding, Workflow, Pipeline, "
            "Upsell, Kundenstamm, Bestandskunde, Neukunde, Makler, Handwerker, Solaranlage, Praxis, "
            "Online-Marketing, Webdesign, Kundenwebsite, Go-live, Testdomain"
        ),
        "repl": [],
    },
    {
        "id": "ki", "name": "KI, Claude & Cloud", "active": True,
        "terms": _split(
            "KI, Künstliche Intelligenz, LLM, Sprachmodell, Claude, Claude Code, Claude Opus, Claude Sonnet, "
            "Claude Haiku, Anthropic, OpenAI, ChatGPT, GPT, Gemini, Grok, Llama, Mistral, DeepSeek, Perplexity, "
            "Copilot, Cursor, MCP, Model Context Protocol, Agent, Subagent, Prompt, Prompt Engineering, "
            "Kontextfenster, Token, Embedding, RAG, Fine-Tuning, Halluzination, Skill, Hook, Plugin, Workflow, "
            "API, API-Key, Whisper, Groq, Nano Banana, fal.ai, Midjourney, Stable Diffusion, Sora, Veo, "
            "ElevenLabs, n8n, Zapier, Make, Hugging Face, Cloud, AWS, Azure, Google Cloud, Cloudflare, Docker, "
            "Kubernetes, Coolify, Hetzner, Vercel, Supabase, Firebase, Astro, Astra DB, GitHub, VS Code, "
            "PowerShell, Python, Node.js, npm, Terminal, Repository, Branch, Commit, Deployment, Server, VPS, "
            "Transformer, Neuronales Netz, Machine Learning, Deep Learning, Training, Inferenz, Parameter, "
            "Multimodal, Reasoning, Agentic, Tool Use, Function Calling, Context Engineering, System Prompt, "
            "Temperature, Open Source, Open Weights, Benchmark, Alignment, AGI, Diffusion, Text-to-Speech, "
            "Speech-to-Text, Vektordatenbank, Pinecone, LangChain, LlamaIndex, Ollama, LM Studio, Windsurf, "
            "Codex, Devin, Lovable, Bolt, Replit, Manus, NotebookLM, Flux, Runway, Kling, Suno, Wispr Flow, "
            "Kaggle, Nvidia, CUDA, GPU, Prompt Caching, Batch API, Rate Limit, Webhook, Endpoint, JSON, SDK, "
            "CLI, Slash-Command, Statusline, CLAUDE.md, Artifact, Workbench, Agent SDK, Extended Thinking, "
            "Computer Use, Vibe Coding, Hugging Face, Replicate, OpenRouter, Mixture of Experts, Quantisierung"
        ),
        "repl": [["Cloud Code", "Claude Code"], ["Claud Code", "Claude Code"], ["Clawd", "Claude"],
                 ["Cloud Opus", "Claude Opus"], ["Cloud Sonnet", "Claude Sonnet"], ["Cloud Haiku", "Claude Haiku"]],
    },
]


class Contexts:
    def __init__(self):
        self.lock = threading.RLock()
        self.items: list[dict] = []
        self.load()

    def load(self):
        with self.lock:
            data, seen = None, None
            if CONTEXTS_PATH.exists():
                try:
                    raw = json.loads(CONTEXTS_PATH.read_text(encoding="utf-8"))
                    data, seen = raw["contexts"], raw.get("seen")
                except Exception:
                    data = None
            self.items = data or []
            # Seit der ersten Version vorhandene Standard-Kontexte gelten als bekannt
            self.seen = set(seen if seen is not None else [c["id"] for c in self.items])
            # Neue Standard-Kontexte nachziehen, aber nie wieder, was du gelöscht hast
            for d in DEFAULT_CONTEXTS:
                if d["id"] not in self.seen and not any(c["id"] == d["id"] for c in self.items):
                    self.items.append(json.loads(json.dumps(d)))
                self.seen.add(d["id"])
            if not any(c["id"] == "general" for c in self.items):
                self.items.insert(0, json.loads(json.dumps(DEFAULT_CONTEXTS[0])))
            self.save()

    def save(self):
        with self.lock:
            CONTEXTS_PATH.write_text(
                json.dumps({"contexts": self.items, "seen": sorted(self.seen)}, indent=2, ensure_ascii=False),
                encoding="utf-8",
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

    def add_term(self, cid, term: str):
        with self.lock:
            c = self.get(cid) or self.get("general")
            term = term.strip()
            if term and term not in c["terms"]:
                c["terms"].append(term)
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
def period_starts(now=None) -> dict:
    """Beginn von Heute (0 Uhr) und Monat (1., 0 Uhr). Gesamt beginnt nie neu."""
    import datetime
    now = now or datetime.datetime.now()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    return {"Heute": day.timestamp(), "Monat": month.timestamp(), "Gesamt": 0}


class History:
    def __init__(self):
        self.lock = threading.Lock()
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS dictations (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, "
                "raw TEXT, text TEXT, audio_s REAL, tok_in INTEGER, tok_out INTEGER, cost REAL)"
            )
            cols = {r[1] for r in db.execute("PRAGMA table_info(dictations)")}
            if "mode" not in cols:  # ab Ä54: raw | clean | structure | rewrite, optional "+Sprache"
                db.execute("ALTER TABLE dictations ADD COLUMN mode TEXT DEFAULT ''")

    @contextlib.contextmanager
    def _db(self):
        """Verbindung mit Commit und sicherem Schließen (sonst bleibt die Datei unter Windows gesperrt)."""
        db = sqlite3.connect(HISTORY_PATH)
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, raw, text, audio_s, tok_in, tok_out, cost, ts=None, mode="") -> int:
        with self.lock, self._db() as db:
            cur = db.execute(
                "INSERT INTO dictations (ts, raw, text, audio_s, tok_in, tok_out, cost, mode) VALUES (?,?,?,?,?,?,?,?)",
                (ts if ts is not None else time.time(), raw, text, audio_s, tok_in, tok_out, cost, mode),
            )
            return cur.lastrowid

    KEYS = ("id", "ts", "raw", "text", "audio_s", "tok_in", "tok_out", "cost", "mode")

    def recent(self, limit=40, offset=0, query="") -> list[dict]:
        """Neueste zuerst. `query` filtert (Groß/klein egal) in Text und Original."""
        where, args = "", []
        if query.strip():
            like = "%" + query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where, args = "WHERE text LIKE ? ESCAPE '\\' OR raw LIKE ? ESCAPE '\\'", [like, like]
        with self.lock, self._db() as db:
            rows = db.execute(
                f"SELECT {', '.join(self.KEYS)} FROM dictations {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
        return [dict(zip(self.KEYS, r)) for r in rows]

    def update_text(self, did, text, mode=None, add_tok_in=0, add_tok_out=0, add_cost=0.0):
        """Text ersetzen (Korrektur oder nachträgliches Umwandeln). Token und Kosten des Umwandelns kommen dazu."""
        with self.lock, self._db() as db:
            if mode is None:
                db.execute("UPDATE dictations SET text=? WHERE id=?", (text, did))
            else:
                db.execute(
                    "UPDATE dictations SET text=?, mode=?, tok_in=COALESCE(tok_in,0)+?, tok_out=COALESCE(tok_out,0)+?, "
                    "cost=COALESCE(cost,0)+? WHERE id=?", (text, mode, add_tok_in, add_tok_out, add_cost, did),
                )

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


MODE_LABELS = {"clean": "Feinschliff", "structure": "Struktur", "rewrite": "Umgeschrieben"}


def mode_label(mode: str) -> str:
    """'structure+Englisch' -> 'Struktur · Englisch'."""
    base, _, lang = (mode or "").partition("+")
    parts = [MODE_LABELS.get(base, "")] + ([lang] if lang else [])
    return " · ".join(p for p in parts if p)


def export_markdown(rows) -> str:
    """Verlauf als Markdown, gruppiert nach Tag (älteste zuerst)."""
    import datetime
    out, day = ["# SpeakIt-Verlauf", ""], None
    for r in sorted(rows, key=lambda r: r["ts"]):
        dt = datetime.datetime.fromtimestamp(r["ts"])
        if dt.date() != day:
            day = dt.date()
            out += [f"## {day:%d.%m.%Y}", ""]
        label = mode_label(r.get("mode", ""))
        out += [f"### {dt:%H:%M}" + (f" ({label})" if label else ""), "", (r["text"] or "").strip(), ""]
    return "\n".join(out).rstrip() + "\n"
