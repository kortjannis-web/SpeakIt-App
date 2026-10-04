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

    def update_text(self, did, text):
        with self.lock, self._db() as db:
            db.execute("UPDATE dictations SET text=? WHERE id=?", (text, did))

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
