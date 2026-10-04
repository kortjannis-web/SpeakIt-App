"""Hauptfenster: Verlauf mit Wort-Korrektur, Kontexte, Statistik, Einstellungen."""
import ctypes
import datetime
import math
import os
import tkinter as tk

import customtkinter as ctk

from . import autostart, sounds
from .audio import list_mics
from .config import DATA, FROZEN, read_env_file, save_env
from .hotkey import pretty
from .icon import drop_icon
from .liquid import LiquidButton, text_width
from .overlay import dpi_scale
from .storage import WAIT, _split, cleanup_comparison, period_starts

BG, SIDE, CARD, LINE = "#F4F1EA", "#ECE8DF", "#FFFFFF", "#E3DED2"
TXT, MUT, ACC, ACC_H, GREEN, RED = "#1D1C1A", "#7B766B", "#1D1C1A", "#3A3835", "#2E7D5B", "#C2410C"
SEL = "#DDD8CB"
ORANGE = "#f59e0b"

MODES = {
    "Halten oder Tippen (beides)": "both",
    "Nur halten (Push-to-talk)": "hold",
    "Nur tippen (Start/Stopp)": "toggle",
}
LANGS = {"Deutsch": "de", "Englisch": "en", "Automatisch": ""}
COPILOT_KEY = ["windows", "shift", "f23"]
PAGES = ["Verlauf", "Kontexte", "Statistik", "Einstellungen"]
DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def style_titlebar(win, color="#fde8c4", text="#1D1C1A"):
    """Windows 11: Titelleiste und Rand dezent orange (auf Windows 10 wirkungslos, stört nicht)."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())

        def cref(h):
            h = h.lstrip("#")
            return int(h[0:2], 16) | (int(h[2:4], 16) << 8) | (int(h[4:6], 16) << 16)

        for attr, val in ((35, color), (34, color), (36, text)):
            v = ctypes.c_int(cref(val))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
    except Exception:
        pass


def day_label(ts: float) -> str:
    d = datetime.date.fromtimestamp(ts)
    today = datetime.date.today()
    if d == today:
        return "Heute"
    if d == today - datetime.timedelta(days=1):
        return "Gestern"
    return f"{DAYS[d.weekday()]}, {d:%d.%m.%Y}"


class MainWindow:
    def __init__(self, ui):
        self.ui, self.app, self.root = ui, ui.app, ui.root
        self.built = False
        self.page = "Verlauf"
        self.sel_ctx = "general"
        self._pending = None
        self.last_ctx = "general"
        self.tut = None
        self.hist_limit = 30
        self.dirty = set(PAGES)  # Seiten, deren Inhalt neu aufgebaut werden muss
        self._day = datetime.date.today()

    # ------------------------------------------------------------ Aufbau
    def build(self):
        r = self.root
        r.title("SpeakIt")
        r.configure(fg_color=BG)
        w, h = 1000, 760
        r.geometry(f"{w}x{h}+{(r.winfo_screenwidth() - w) // 2}+{(r.winfo_screenheight() - h) // 2}")
        r.minsize(900, 700)
        r.protocol("WM_DELETE_WINDOW", self.hide)
        self.f_title = ctk.CTkFont(family="Segoe UI Semibold", size=24)
        self.f_h = ctk.CTkFont(family="Segoe UI Semibold", size=14)
        self.f_n = ctk.CTkFont(family="Segoe UI", size=13)
        self.f_s = ctk.CTkFont(family="Segoe UI", size=12)

        side = ctk.CTkFrame(r, fg_color=SIDE, corner_radius=0, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self.logo_img = ctk.CTkImage(light_image=drop_icon(96), size=(30, 30))
        ctk.CTkLabel(side, text=" SpeakIt", image=self.logo_img, compound="left",
                     font=ctk.CTkFont(family="Segoe UI Semibold", size=18),
                     text_color=TXT).pack(anchor="w", padx=20, pady=(24, 20))
        self.enabled_var = ctk.BooleanVar(value=bool(self.app.cfg["enabled"]))
        pw = ctk.CTkFrame(side, fg_color=CARD, corner_radius=14, border_width=1, border_color=LINE)
        pw.pack(fill="x", padx=12, pady=(0, 14))
        self.power_label = ctk.CTkLabel(pw, text="", font=self.f_h, text_color=TXT)
        self.power_label.pack(side="left", padx=(14, 0), pady=12)
        ctk.CTkSwitch(pw, text="", variable=self.enabled_var, command=self._on_power, width=52,
                      switch_width=46, switch_height=24, progress_color=ORANGE).pack(side="right", padx=14)
        self.clean_var = ctk.BooleanVar(value=bool(self.app.cfg["cleanup"]))
        cl = ctk.CTkFrame(side, fg_color=CARD, corner_radius=14, border_width=1, border_color=LINE)
        cl.pack(fill="x", padx=12, pady=(0, 14))
        top = ctk.CTkFrame(cl, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Nachbearbeitung", font=self.f_n, text_color=TXT).pack(side="left", padx=(14, 0), pady=(10, 0))
        ctk.CTkSwitch(top, text="", variable=self.clean_var, command=self._on_clean, width=44, switch_width=40,
                      switch_height=22, progress_color=ORANGE).pack(side="right", padx=(0, 10), pady=(10, 0))
        self.clean_hint = ctk.CTkLabel(cl, text="", font=self.f_s, text_color=MUT, justify="left", wraplength=172)
        self.clean_hint.pack(anchor="w", padx=14, pady=(2, 10))
        self.nav = {}
        for name in PAGES:
            b = LiquidButton(side, text=name, command=lambda n=name: self.show_page(n), width=180, height=36,
                             bg=SIDE, fg=TXT, fg_active=TXT, font=("Segoe UI", 14), radius=12, hover=0.4,
                             anchor="w", padx=16)
            b.pack(fill="x", padx=12, pady=1)
            self.nav[name] = b
        self.side_info = ctk.CTkLabel(side, text="", font=self.f_s, text_color=MUT, justify="left")
        self.side_info.pack(side="bottom", anchor="w", padx=22, pady=(4, 18))
        self.mini = ctk.CTkFrame(side, fg_color=CARD, corner_radius=14, border_width=1, border_color=LINE)
        self.mini.pack(side="bottom", fill="x", padx=12, pady=(0, 6))
        self.mini_rows = {}
        for key in ("Heute", "Monat", "Gesamt"):
            mrow = ctk.CTkFrame(self.mini, fg_color="transparent")
            mrow.pack(fill="x", padx=12, pady=(6, 0) if key == "Heute" else (2, 0))
            ctk.CTkLabel(mrow, text=key, font=self.f_s, text_color=MUT).pack(anchor="w")
            lab = ctk.CTkLabel(mrow, text="", font=self.f_s, text_color=TXT)
            lab.pack(anchor="w")
            self.mini_rows[key] = lab
        ctk.CTkLabel(self.mini, text="", height=4).pack()
        LiquidButton(side, text="Tutorial anzeigen", command=self.open_tutorial, width=180, height=34, bg=SIDE,
                     border=LINE, fg=TXT, fg_active=TXT, font=("Segoe UI", 12), radius=12, hover=0.5).pack(
            side="bottom", fill="x", padx=12, pady=(0, 8))

        self.content = ctk.CTkFrame(r, fg_color=BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)
        self.pages = {}
        for name in PAGES:
            self.pages[name] = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_history()
        self._build_contexts()
        self._build_stats()
        self._build_settings()
        self._power_text()
        self._clean_text()
        self.built = True

    def _title(self, parent, title, sub=""):
        ctk.CTkLabel(parent, text=title, font=self.f_title, text_color=TXT).pack(anchor="w", padx=34, pady=(28, 2))
        if sub:
            ctk.CTkLabel(parent, text=sub, font=self.f_s, text_color=MUT, justify="left",
                         wraplength=640).pack(anchor="w", padx=34, pady=(0, 14))

    def _bg_of(self, w):
        """Hintergrundfarbe des Elternelements, damit die runden Ecken eines Buttons sauber aufliegen."""
        while w is not None:
            try:
                col = w.cget("fg_color")
                if isinstance(col, (tuple, list)):
                    col = col[0]
                if col and col != "transparent":
                    return col
            except Exception:
                try:
                    return w.cget("bg")
                except Exception:
                    pass
            w = getattr(w, "master", None)
        return BG

    def _btn(self, parent, text, cmd, primary=True, width=None, **kw):
        font = ("Segoe UI", 13)
        w = width or max(86, text_width(text, font) + 40)
        return LiquidButton(parent, text=text, command=cmd, width=w, height=36, bg=self._bg_of(parent),
                            fill=ACC if primary else None, border=None if primary else LINE,
                            fg="white" if primary else TXT, fg_active=TXT, font=font, radius=12, hover=0.5)

    # ------------------------------------------------------------ Anzeigen
    def show(self, page=None):
        if not self.built:
            self.build()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)  # sonst bleibt es hinter dem aktiven Fenster
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        self.root.after(60, lambda: style_titlebar(self.root))
        self.show_page(page or self.page)

    def hide(self):
        self.root.withdraw()

    @property
    def visible(self):
        return self.built and self.root.state() != "withdrawn"

    def show_page(self, name):
        self.page = name
        for n, f in self.pages.items():
            f.pack_forget()
            self.nav[n].set_selected(n == name)
        self.pages[name].pack(fill="both", expand=True)
        if datetime.date.today() != self._day:  # nach Mitternacht stimmen "Heute" und "Gestern" nicht mehr
            self._day = datetime.date.today()
            self.dirty.update(("Verlauf", "Statistik"))
        if name in self.dirty:  # nur neu aufbauen, wenn sich seit dem letzten Anzeigen etwas geändert hat
            if name == "Verlauf":
                self.refresh_history()
            elif name == "Kontexte":
                self.refresh_contexts()
            elif name == "Statistik":
                self.refresh_stats()
        self.side_info.configure(text=f"Taste: {pretty(self.app.cfg['hotkey'])}")
        self.refresh_mini()

    # ------------------------------------------------------------ Tutorial
    def open_tutorial(self):
        if not self.built:
            self.build()
        if self.tut is not None and self.tut.winfo_exists():
            self.tut.lift()
            return
        key = pretty(self.app.cfg["hotkey"])
        steps = [
            ("Willkommen bei SpeakIt",
             "SpeakIt schreibt, was du sagst. In jedes Textfeld, in jedem Programm: Mails, Chats, Editor, Browser. "
             "Dieses kurze Tutorial zeigt dir in fünf Schritten, wie es geht.", self._ill_welcome),
            ("Taste halten und sprechen",
             f"Halte {key} gedrückt, sprich und lass los. Der Text erscheint sofort dort, wo dein Cursor steht. "
             "Tippst du die Taste nur kurz an, läuft die Aufnahme weiter, bis du sie nochmal tippst. "
             "Mit Esc brichst du ab.", self._ill_key),
            ("Die kleine Anzeige",
             "Unten in der Mitte erscheint beim Sprechen eine kleine Kapsel mit Pegel und Sekundenticker. "
             "Danach füllt sich eine orange Anzeige. Ist sie bis oben voll, ist dein Text fertig und eingefügt.",
             self._ill_pill),
            ("SpeakIt läuft im Hintergrund",
             "Das Fenster kannst du schließen, SpeakIt bleibt aktiv. Du findest es unten rechts neben der Uhr: "
             "Klicke dort auf den kleinen Pfeil (1), dann auf das Mikrofon-Symbol (2). Doppelklick öffnet das Fenster, "
             "Rechtsklick zeigt das Menü mit An/Aus und Beenden.", self._ill_tray),
            ("SpeakIt lernt mit",
             "Im Verlauf klickst du ein falsch verstandenes Wort an, trägst das richtige ein und wählst einen Kontext. "
             "Hört SpeakIt zum Beispiel \"Cloud Code\", obwohl du Claude Code meinst, korrigierst du es einmal. "
             "Danach erkennt SpeakIt es dauerhaft richtig. "
             "Mit dem Schalter oben links schaltest du SpeakIt ganz aus, mit dem zweiten die Nachbearbeitung.",
             self._ill_learn),
        ]
        dlg = self.tut = ctk.CTkToplevel(self.root)
        dlg.title("SpeakIt Tutorial")
        dlg.configure(fg_color=BG)
        w, h = 720, 520
        dlg.geometry(f"{w}x{h}+{self.root.winfo_x() + 120}+{self.root.winfo_y() + 40}")
        dlg.transient(self.root)
        dlg.after(150, lambda: (dlg.lift(), dlg.focus_force()))
        dlg.after(200, lambda: style_titlebar(dlg))
        body = ctk.CTkFrame(dlg, fg_color="transparent")
        body.pack(fill="both", expand=True)
        state = {"i": 0}

        def finish():
            self.app.cfg.set(tutorial_done=True)
            dlg.destroy()
            self.tut = None

        def render():
            for ch in body.winfo_children():
                ch.destroy()
            i = state["i"]
            title, text, ill = steps[i]
            ctk.CTkLabel(body, text=f"Schritt {i + 1} von {len(steps)}", font=self.f_s, text_color=MUT).pack(
                anchor="w", padx=34, pady=(26, 0))
            ctk.CTkLabel(body, text=title, font=self.f_title, text_color=TXT).pack(anchor="w", padx=34, pady=(0, 14))
            card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
            card.pack(fill="x", padx=34)
            k = dpi_scale()
            cv = tk.Canvas(card, width=int(610 * k), height=int(170 * k), bg=CARD, highlightthickness=0)
            cv.pack(padx=12, pady=12)
            ill(cv, k)
            ctk.CTkLabel(body, text=text, font=self.f_n, text_color=TXT, wraplength=640, justify="left").pack(
                anchor="w", padx=34, pady=(18, 0))
            foot = ctk.CTkFrame(body, fg_color="transparent")
            foot.pack(side="bottom", fill="x", padx=34, pady=22)
            ctk.CTkLabel(foot, text="  ".join("●" if n == i else "○" for n in range(len(steps))),
                         font=self.f_n, text_color=MUT).pack(side="left")
            last = i == len(steps) - 1
            self._btn(foot, "Los geht's" if last else "Weiter",
                      finish if last else (lambda: (state.update(i=i + 1), render()))).pack(side="right")
            if i > 0:
                self._btn(foot, "Zurück", lambda: (state.update(i=i - 1), render()), primary=False).pack(
                    side="right", padx=10)
            else:
                self._btn(foot, "Überspringen", finish, primary=False).pack(side="right", padx=10)

        dlg.protocol("WM_DELETE_WINDOW", finish)
        render()

    # ---- Zeichnungen für das Tutorial (alles in Basis-Pixeln, k = DPI-Faktor)
    def _capsule(self, c, k, x, y, w, h, fill="#17171a", outline="#767c88"):
        r = h / 2
        c.create_oval(x, y, x + h, y + h, fill=fill, outline=fill)
        c.create_oval(x + w - h, y, x + w, y + h, fill=fill, outline=fill)
        c.create_rectangle(x + r, y, x + w - r, y + h, fill=fill, outline=fill)
        c.create_arc(x, y, x + h, y + h, start=90, extent=180, style="arc", outline=outline)
        c.create_arc(x + w - h, y, x + w, y + h, start=270, extent=180, style="arc", outline=outline)
        c.create_line(x + r, y, x + w - r, y, fill=outline)
        c.create_line(x + r, y + h, x + w - r, y + h, fill=outline)

    def _ill_welcome(self, c, k):
        c.create_oval(255 * k, 20 * k, 355 * k, 120 * k, fill=ACC, outline=ACC)
        c.create_rectangle(293 * k, 40 * k, 317 * k, 82 * k, fill="white", outline="white")
        c.create_oval(293 * k, 32 * k, 317 * k, 56 * k, fill="white", outline="white")
        c.create_oval(293 * k, 66 * k, 317 * k, 90 * k, fill="white", outline="white")
        c.create_arc(279 * k, 55 * k, 331 * k, 105 * k, start=180, extent=180, style="arc", outline="white",
                     width=int(4 * k))
        c.create_text(305 * k, 146 * k, text="Sprich. SpeakIt tippt.", fill=TXT, font=("Segoe UI Semibold", 13))

    def _ill_key(self, c, k):
        key = pretty(self.app.cfg["hotkey"])
        wd = max(110, 24 + 11 * len(key))
        x = 305 - wd / 2
        c.create_rectangle(x * k, 40 * k, (x + wd) * k, 112 * k, fill="#D8D2C4", outline="#D8D2C4")
        c.create_rectangle(x * k, 32 * k, (x + wd) * k, 100 * k, fill="#FFFFFF", outline="#8A8578", width=2)
        c.create_text(305 * k, 66 * k, text=key, fill=TXT, font=("Segoe UI Semibold", 15))
        c.create_text(120 * k, 70 * k, text="halten\nund sprechen", fill=MUT, font=("Segoe UI", 11), justify="center")
        c.create_text(490 * k, 70 * k, text="loslassen\nText erscheint", fill=MUT, font=("Segoe UI", 11), justify="center")
        c.create_text(305 * k, 140 * k, text="kurz tippen = Aufnahme läuft, nochmal tippen = Ende", fill=MUT,
                      font=("Segoe UI", 11))

    def _ill_pill(self, c, k):
        # links: Aufnahme
        self._capsule(c, k, 30 * k, 50 * k, 138 * k, 30 * k)
        c.create_oval(41 * k, 61 * k, 49 * k, 69 * k, fill="#ef4444", outline="#ef4444")
        for i, hh in enumerate([4, 8, 13, 7, 15, 10, 5, 12, 8, 14, 6, 9]):
            x = (58 + i * 5) * k
            c.create_line(x, (65 - hh / 2) * k, x, (65 + hh / 2) * k, fill="#f4f4f5", width=int(2.4 * k),
                          capstyle="round")
        c.create_text(128 * k, 65 * k, text="0:07", fill="#f4f4f5", anchor="w", font=("Segoe UI Semibold", 9))
        c.create_text(99 * k, 112 * k, text="Aufnahme", fill=MUT, font=("Segoe UI", 11))
        # Mitte: Pfeil
        c.create_text(228 * k, 62 * k, text="→", fill=MUT, font=("Segoe UI", 20))
        # Mitte/rechts: Flüssigkeit halb und voll
        for cx, level, label in ((330, 0.5, "Verarbeitung"), (510, 1.0, "fertig")):
            x0 = cx - 69
            self._capsule(c, k, x0 * k, 50 * k, 138 * k, 30 * k)
            if level < 1:
                pts = []
                for j in range(0, 33):
                    xx = x0 + 4 + (130 * j / 32)
                    yy = 78 - 28 * level - 2.2 * math.sin(j / 3.2) - 1.3 * math.sin(j / 1.7 + 1)
                    pts += [xx * k, yy * k]
                pts += [(x0 + 134) * k, 78 * k, (x0 + 4) * k, 78 * k]
                c.create_polygon(pts, fill="#f59e0b", outline="#f59e0b")
            else:
                self._capsule(c, k, x0 * k, 50 * k, 138 * k, 30 * k, fill="#f59e0b", outline="#767c88")
            c.create_text(cx * k, 112 * k, text=label, fill=MUT, font=("Segoe UI", 11))
        c.create_text(420 * k, 62 * k, text="→", fill=MUT, font=("Segoe UI", 20))

    def _ill_tray(self, c, k):
        W, H = 610, 170
        c.create_rectangle(0, 128 * k, W * k, H * k, fill="#1f2937", outline="#1f2937")  # Taskleiste
        for i in range(5):
            c.create_oval((20 + i * 34) * k, 138 * k, (40 + i * 34) * k, 158 * k, fill="#374151", outline="#374151")
        # Uhr
        c.create_text(572 * k, 143 * k, text="16:40", fill="#e5e7eb", font=("Segoe UI", 10))
        c.create_text(572 * k, 157 * k, text="04.10.2026", fill="#9ca3af", font=("Segoe UI", 8))
        # Pfeil (1)
        ax, ay = 478, 143
        c.create_text(ax * k, ay * k, text="^", fill="#e5e7eb", font=("Segoe UI Semibold", 14))
        c.create_oval((ax - 17) * k, (ay - 15) * k, (ax + 17) * k, (ay + 15) * k, outline="#ef4444", width=int(2.5 * k))
        c.create_text((ax - 52) * k, 112 * k, text="1  Hier klicken", fill="#ef4444", font=("Segoe UI Semibold", 11))
        # Flyout mit Symbolen (2)
        fx, fy, fw, fh = 372, 34, 190, 62
        c.create_rectangle(fx * k, fy * k, (fx + fw) * k, (fy + fh) * k, fill="#111827", outline="#4b5563")
        for i, col in enumerate(("#6b7280", "#6b7280", "#6b7280")):
            c.create_oval((fx + 16 + i * 38) * k, (fy + 14) * k, (fx + 40 + i * 38) * k, (fy + 38) * k, fill=col,
                          outline=col)
        mx, my = fx + 16 + 3 * 38 + 12, fy + 26
        c.create_oval((mx - 13) * k, (my - 13) * k, (mx + 13) * k, (my + 13) * k, fill="#f5f5f4", outline="#22c55e",
                      width=int(2.5 * k))
        c.create_rectangle((mx - 3) * k, (my - 8) * k, (mx + 3) * k, (my + 3) * k, fill="#1D1C1A", outline="#1D1C1A")
        c.create_arc((mx - 7) * k, (my - 4) * k, (mx + 7) * k, (my + 8) * k, start=180, extent=180, style="arc",
                     outline="#1D1C1A", width=int(1.6 * k))
        c.create_text(fx * k, (fy - 14) * k, text="2  SpeakIt (Mikrofon-Symbol)", fill="#16a34a", anchor="w",
                      font=("Segoe UI Semibold", 11))
        c.create_text(24 * k, 62 * k, anchor="w", fill=MUT, font=("Segoe UI", 11), justify="left",
                      text="Doppelklick auf das Symbol\nöffnet dieses Fenster.\nRechtsklick zeigt das Menü\nmit An/Aus und Beenden.")

    def _ill_learn(self, c, k):
        c.create_text(30 * k, 50 * k, text="… ich nutze jeden Tag", fill=TXT, anchor="w", font=("Segoe UI", 15))
        c.create_rectangle(228 * k, 38 * k, 346 * k, 62 * k, fill="#EFE9DA", outline="#EFE9DA")
        c.create_text(233 * k, 50 * k, text="Cloud Code", fill=TXT, anchor="w", font=("Segoe UI", 15))
        c.create_line(230 * k, 62 * k, 344 * k, 62 * k, fill="#ef4444", width=int(2 * k))
        c.create_text(350 * k, 50 * k, text=".", fill=TXT, anchor="w", font=("Segoe UI", 15))
        c.create_text(287 * k, 82 * k, text="↓ anklicken", fill=MUT, font=("Segoe UI", 11))
        x, y, w, h = 150, 98, 310, 58
        c.create_rectangle(x * k, y * k, (x + w) * k, (y + h) * k, fill=BG, outline=LINE)
        c.create_text((x + 14) * k, (y + 16) * k, text="Richtig:  Claude Code", fill=TXT, anchor="w",
                      font=("Segoe UI Semibold", 12))
        c.create_text((x + 14) * k, (y + 40) * k, text="Kontext:  KI, Claude & Cloud      ✓ künftig automatisch ersetzen", fill=MUT,
                      anchor="w", font=("Segoe UI", 10))

    def _on_power(self):
        on = bool(self.enabled_var.get())
        self.app.set_enabled(on)
        self._power_text()

    def _on_clean(self):
        self.app.cfg.set(cleanup=bool(self.clean_var.get()))
        self.app.refresh_tray()
        self._clean_text()

    def _clean_text(self):
        on = bool(self.clean_var.get())
        self.clean_hint.configure(
            text="An: glättet den Text und korrigiert Wörter." if on
            else f"Aus: Rohtext, bis zu 2x schneller und ca. {cleanup_comparison()['factor']:.0f}x günstiger.")

    def _power_text(self):
        on = bool(self.enabled_var.get())
        self.power_label.configure(text="SpeakIt ist an" if on else "SpeakIt ist aus",
                                   text_color=TXT if on else RED)

    def sync_enabled(self):
        """Wird vom Tray aufgerufen, wenn dort umgeschaltet wurde."""
        if self.built:
            self.enabled_var.set(bool(self.app.cfg["enabled"]))
            self.clean_var.set(bool(self.app.cfg["cleanup"]))
            self._power_text()
            self._clean_text()

    def refresh_mini(self):
        for key, since in period_starts().items():
            st = self.app.history.stats(since)
            money = f"{st['cost']:.3f}".replace(".", ",")
            words = f"{int(st['words']):,}".replace(",", ".")
            self.mini_rows[key].configure(text=f"{money} $  ·  {words} Wörter")

    def on_new_dictation(self):
        self.dirty.update(("Verlauf", "Statistik"))
        self.refresh_mini()
        if self.visible and self.page == "Verlauf":
            self.refresh_history()
        elif self.visible and self.page == "Statistik":
            self.refresh_stats()

    # ------------------------------------------------------------ Verlauf
    def _build_history(self):
        p = self.pages["Verlauf"]
        self._title(p, "Verlauf", "Klicke auf ein beliebiges Wort (oder markiere mehrere), um es zu verbessern und einem "
                                  "Kontext zuzuordnen. SpeakIt lernt dazu.")
        self.hist = ctk.CTkScrollableFrame(p, fg_color=BG, corner_radius=0)
        self.hist.pack(fill="both", expand=True, padx=22, pady=(0, 8))

    def refresh_history(self):
        self.dirty.discard("Verlauf")
        for w in self.hist.winfo_children():
            w.destroy()
        rows = self.app.history.recent(self.hist_limit)
        if not rows:
            c = ctk.CTkFrame(self.hist, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
            c.pack(fill="x", padx=12, pady=8)
            ctk.CTkLabel(c, text=f"Noch kein Diktat. Halte {pretty(self.app.cfg['hotkey'])} und sprich.",
                         font=self.f_n, text_color=MUT).pack(padx=20, pady=26)
            return
        last_day = ""
        for row in rows:
            d = day_label(row["ts"])
            if d != last_day:
                ctk.CTkLabel(self.hist, text=d, font=self.f_h, text_color=TXT).pack(anchor="w", padx=14, pady=(14, 4))
                last_day = d
            self._card(row)
        if len(rows) >= self.hist_limit:
            self._btn(self.hist, "Mehr laden", self._more, primary=False).pack(pady=14)

    def _more(self):
        self.hist_limit += 30
        self.refresh_history()

    def _card(self, row):
        c = ctk.CTkFrame(self.hist, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
        c.pack(fill="x", padx=12, pady=5)
        top = ctk.CTkFrame(c, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 0))
        t = datetime.datetime.fromtimestamp(row["ts"]).strftime("%H:%M")
        words = len((row["text"] or "").split())
        tok = (row["tok_in"] or 0) + (row["tok_out"] or 0)
        meta = f"{words} Wörter · {int(row['audio_s'])} s" + (f" · {tok} Token" if tok else "")
        ctk.CTkLabel(top, text=t, font=self.f_h, text_color=TXT).pack(side="left")
        ctk.CTkLabel(top, text="  " + meta, font=self.f_s, text_color=MUT).pack(side="left")
        tw = tk.Text(c, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, bg=CARD, fg=TXT,
                     font=("Segoe UI", -round(16 * dpi_scale())), cursor="hand2", padx=0, pady=0, spacing1=2, spacing3=2,
                     selectbackground="#CFE0FF", inactiveselectbackground="#CFE0FF", selectforeground=TXT)
        state = {"raw": False}

        def fill():
            tw.configure(state="normal")
            tw.delete("1.0", "end")
            tw.insert("1.0", row["raw"] if state["raw"] else row["text"])
            tw.configure(state="disabled")
            self._fit(tw)

        def toggle():
            state["raw"] = not state["raw"]
            raw_btn.configure(text="Bereinigt" if state["raw"] else "Original")
            fill()

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(tw.get("1.0", "end").strip())

        def delete():
            self.app.history.delete(row["id"])
            self.refresh_history()

        for text, cmd in (("✕", delete), ("Kopieren", copy)):
            LiquidButton(top, text=text, command=cmd, width=34 if text == "✕" else 78, height=28, bg=CARD,
                         border=None if text == "✕" else LINE, fg=MUT if text == "✕" else TXT, fg_active=TXT,
                         font=("Segoe UI", 12), radius=9, hover=0.5).pack(side="right", padx=(6, 0))
        raw_btn = LiquidButton(top, text="Original", command=toggle, width=74, height=28, bg=CARD, fg=MUT,
                               fg_active=TXT, font=("Segoe UI", 12), radius=9, hover=0.5)
        raw_btn.pack(side="right")
        tw.pack(fill="x", padx=16, pady=(8, 14))
        fill()
        tw.tag_configure("hov", underline=True, background="#EFE9DA")
        tw.bind("<Motion>", lambda e, w=tw: self._hover(e, w))
        tw.bind("<Leave>", lambda e, w=tw: w.tag_remove("hov", "1.0", "end"))
        tw.bind("<ButtonRelease-1>", lambda e, w=tw: self._on_select(e, w))
        tw.bind("<MouseWheel>", lambda e: (self.hist._parent_canvas.yview_scroll(int(-e.delta / 120), "units"), "break")[1])
        tw.bind("<Configure>", lambda e, w=tw: self._fit(w))
        tw._row = row

    def _fit(self, tw):
        try:
            n = tw.count("1.0", "end", "displaylines")
            lines = max(1, n[0] if n else 1)
            if int(tw.cget("height")) != lines:
                tw.configure(height=lines)
        except tk.TclError:
            pass

    def _on_select(self, e, tw):
        try:
            sel = tw.get("sel.first", "sel.last")
        except tk.TclError:
            idx = tw.index(f"@{e.x},{e.y}")
            sel = tw.get(f"{idx} wordstart", f"{idx} wordend")
        sel = sel.strip().strip(".,;:!?\"'()„“")
        if not sel:
            return
        row = getattr(tw, "_row", None)
        if self._pending:
            self.root.after_cancel(self._pending)  # Doppelklick: nur einmal öffnen
        self._pending = self.root.after(230, lambda: self.open_correction(sel, row))

    def _hover(self, e, tw):
        idx = tw.index(f"@{e.x},{e.y}")
        ws, we = tw.index(f"{idx} wordstart"), tw.index(f"{idx} wordend")
        word = tw.get(ws, we)
        tw.tag_remove("hov", "1.0", "end")
        if word.strip(" .,;:!?\"'()„“\n"):
            tw.tag_add("hov", ws, we)

    def open_correction(self, wrong, row=None):
        self._pending = None
        if not wrong:
            return
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Wort korrigieren")
        dlg.configure(fg_color=BG)
        dlg.geometry(f"460x470+{self.root.winfo_x() + 260}+{self.root.winfo_y() + 120}")
        dlg.transient(self.root)
        dlg.after(150, lambda: (dlg.lift(), dlg.focus_force()))
        dlg.after(200, lambda: style_titlebar(dlg))
        pad = {"padx": 26, "anchor": "w"}
        ctk.CTkLabel(dlg, text="Wort korrigieren", font=self.f_title, text_color=TXT).pack(pady=(22, 12), **pad)
        ctk.CTkLabel(dlg, text="Falsch verstanden", font=self.f_s, text_color=MUT).pack(**pad)
        e_wrong = ctk.CTkEntry(dlg, width=408, height=38, corner_radius=10, font=self.f_n)
        e_wrong.insert(0, wrong)
        e_wrong.pack(padx=26, pady=(2, 10))
        ctk.CTkLabel(dlg, text="Richtig", font=self.f_s, text_color=MUT).pack(**pad)
        e_right = ctk.CTkEntry(dlg, width=408, height=38, corner_radius=10, font=self.f_n)
        e_right.pack(padx=26, pady=(2, 10))
        e_right.after(250, e_right.focus_set)
        ctk.CTkLabel(dlg, text="Kontext (Thema)", font=self.f_s, text_color=MUT).pack(**pad)
        names = {c["name"]: c["id"] for c in self.app.contexts.items}
        NEW = "+ Neuer Kontext …"
        ctx_var = ctk.StringVar(value=next((n for n, i in names.items() if i == self.last_ctx), next(iter(names))))
        menu = ctk.CTkOptionMenu(dlg, values=list(names) + [NEW], variable=ctx_var, width=408, height=38,
                                 corner_radius=10, font=self.f_n, fg_color=CARD, text_color=TXT,
                                 button_color=SEL, button_hover_color=LINE, dropdown_font=self.f_n)
        menu.pack(padx=26, pady=(2, 6))
        e_new = ctk.CTkEntry(dlg, width=408, height=38, corner_radius=10, font=self.f_n,
                             placeholder_text="Name des neuen Kontexts")

        def on_ctx(v):
            if v == NEW:
                e_new.pack(padx=26, pady=(0, 6), after=menu)
            else:
                e_new.pack_forget()

        menu.configure(command=on_ctx)
        replace_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(dlg, text="Künftig automatisch ersetzen", variable=replace_var, font=self.f_n,
                      text_color=TXT, progress_color=ORANGE).pack(pady=(10, 4), **pad)
        err = ctk.CTkLabel(dlg, text="", font=self.f_s, text_color=RED)
        err.pack(**pad)

        def save():
            right, wr = e_right.get().strip(), e_wrong.get().strip()
            if not right:
                err.configure(text="Bitte das richtige Wort eintragen.")
                return
            if ctx_var.get() == NEW:
                cid = self.app.contexts.add(e_new.get() or "Neuer Kontext")["id"]
            else:
                cid = names[ctx_var.get()]
            self.last_ctx = cid
            if replace_var.get() and wr:
                self.app.contexts.add_correction(cid, wr, right)
                if row and wr in row["text"]:
                    self.app.history.update_text(row["id"], row["text"].replace(wr, right))
            else:
                self.app.contexts.add_term(cid, right)
            dlg.destroy()
            self.dirty.add("Kontexte")
            self.refresh_history()

        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(fill="x", padx=26, pady=(8, 0))
        self._btn(row, "Speichern", save).pack(side="left")
        self._btn(row, "Abbrechen", dlg.destroy, primary=False).pack(side="left", padx=10)
        dlg.bind("<Return>", lambda _e: save())

    # ------------------------------------------------------------ Kontexte
    def _build_contexts(self):
        p = self.pages["Kontexte"]
        self._title(p, "Kontexte", "Aktive Kontexte gibst du Whisper und Claude mit. Inaktive kennt Claude trotzdem "
                                   "und nutzt sie nur, wenn das Thema im Text offensichtlich passt.")
        body = ctk.CTkFrame(p, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        left = ctk.CTkFrame(body, fg_color="transparent", width=270)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.ctx_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.ctx_list.pack(fill="both", expand=True)
        self._btn(left, "+ Neuer Kontext", self._new_context, primary=False).pack(fill="x", padx=10, pady=(8, 0))
        self.ctx_edit = ctk.CTkFrame(body, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
        self.ctx_edit.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ed = self.ctx_edit
        ctk.CTkLabel(ed, text="Name", font=self.f_s, text_color=MUT).pack(anchor="w", padx=20, pady=(18, 2))
        self.e_name = ctk.CTkEntry(ed, height=38, corner_radius=10, font=self.f_n)
        self.e_name.pack(fill="x", padx=20)
        ctk.CTkLabel(ed, text="Begriffe (Komma oder eine pro Zeile)", font=self.f_s, text_color=MUT).pack(
            anchor="w", padx=20, pady=(14, 2))
        self.t_terms = ctk.CTkTextbox(ed, height=170, corner_radius=10, font=self.f_n, fg_color=BG,
                                      border_width=1, border_color=LINE, text_color=TXT)
        self.t_terms.pack(fill="x", padx=20)
        ctk.CTkLabel(ed, text="Korrekturen (falsch => richtig, eine pro Zeile)", font=self.f_s,
                     text_color=MUT).pack(anchor="w", padx=20, pady=(14, 2))
        self.t_repl = ctk.CTkTextbox(ed, height=110, corner_radius=10, font=self.f_n, fg_color=BG,
                                     border_width=1, border_color=LINE, text_color=TXT)
        self.t_repl.pack(fill="x", padx=20)
        row = ctk.CTkFrame(ed, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=16)
        self._btn(row, "Speichern", self._save_context).pack(side="left")
        self.del_btn = self._btn(row, "Löschen", self._delete_context, primary=False)
        self.del_btn.pack(side="left", padx=10)
        self.ctx_msg = ctk.CTkLabel(row, text="", font=self.f_s, text_color=GREEN)
        self.ctx_msg.pack(side="left", padx=8)

    def refresh_contexts(self):
        self.dirty.discard("Kontexte")
        for w in self.ctx_list.winfo_children():
            w.destroy()
        for c in self.app.contexts.items:
            f = ctk.CTkFrame(self.ctx_list, fg_color=CARD if c["id"] == self.sel_ctx else "transparent",
                             corner_radius=12, border_width=1 if c["id"] == self.sel_ctx else 0, border_color=LINE)
            f.pack(fill="x", pady=2)
            if c["id"] == "general":
                ctk.CTkLabel(f, text="immer", font=self.f_s, text_color=MUT, width=44).pack(side="left", padx=(10, 0))
            else:
                sw = ctk.CTkSwitch(f, text="", width=44, progress_color=ORANGE,
                                   command=lambda cid=c["id"]: self._toggle_ctx(cid, sw_vars[cid].get()))
                sw_vars = getattr(self, "_sw_vars", {})
                var = ctk.BooleanVar(value=c["active"])
                sw_vars[c["id"]] = var
                self._sw_vars = sw_vars
                sw.configure(variable=var)
                sw.pack(side="left", padx=(10, 0), pady=8)
            lb = LiquidButton(f, text=f"{c['name']}  ({len(c['terms'])})", command=lambda cid=c["id"]: self._select_ctx(cid),
                              width=150, height=36, bg=self._bg_of(f), fg=TXT, fg_active=TXT, font=("Segoe UI", 13),
                              radius=10, hover=0.4, anchor="w", padx=10)
            lb.set_selected(c["id"] == self.sel_ctx)
            lb.pack(side="left", fill="x", expand=True)
        self._load_editor()

    def _toggle_ctx(self, cid, value):
        self.app.contexts.update(cid, active=bool(value))

    def _select_ctx(self, cid):
        self.sel_ctx = cid
        self.refresh_contexts()

    def _load_editor(self):
        c = self.app.contexts.get(self.sel_ctx) or self.app.contexts.items[0]
        self.sel_ctx = c["id"]
        self.e_name.delete(0, "end")
        self.e_name.insert(0, c["name"])
        self.t_terms.delete("1.0", "end")
        self.t_terms.insert("1.0", ", ".join(c["terms"]))
        self.t_repl.delete("1.0", "end")
        self.t_repl.insert("1.0", "\n".join(f"{a} => {b}" for a, b in c["repl"]))
        self.ctx_msg.configure(text="")
        if c["id"] == "general":
            self.del_btn.pack_forget()
        elif not self.del_btn.winfo_ismapped():
            self.del_btn.pack(side="left", padx=10, after=self.del_btn.master.winfo_children()[0])

    def _new_context(self):
        c = self.app.contexts.add("Neuer Kontext")
        self.sel_ctx = c["id"]
        self.refresh_contexts()
        self.e_name.focus_set()
        self.e_name.select_range(0, "end")

    def _save_context(self):
        repl = []
        for line in self.t_repl.get("1.0", "end").splitlines():
            if "=>" in line:
                a, b = (x.strip() for x in line.split("=>", 1))
                if a and b:
                    repl.append([a, b])
        self.app.contexts.update(self.sel_ctx, name=self.e_name.get(), terms=_split(self.t_terms.get("1.0", "end")),
                                 repl=repl)
        self.refresh_contexts()
        self.ctx_msg.configure(text="Gespeichert")

    def _delete_context(self):
        self.app.contexts.delete(self.sel_ctx)
        self.sel_ctx = "general"
        self.refresh_contexts()

    # ------------------------------------------------------------ Statistik
    def _build_stats(self):
        p = self.pages["Statistik"]
        self._title(p, "Statistik", "Echte Zahlen aus deinen Diktaten. Kosten sind geschätzt "
                                    "(Listenpreise Groq und Claude Haiku, ohne Gewähr).")
        self.stat_box = ctk.CTkFrame(p, fg_color="transparent")
        self.stat_box.pack(fill="x", padx=22)

    def refresh_stats(self):
        self.dirty.discard("Statistik")
        for w in self.stat_box.winfo_children():
            w.destroy()
        starts = period_starts()
        for i, (title, since) in enumerate((("Heute", starts["Heute"]), ("Dieser Monat", starts["Monat"]),
                                            ("Gesamt", 0))):
            s = self.app.history.stats(since)
            mins = s["audio_s"] / 60
            per_min = (s["tok_in"] + s["tok_out"]) / mins if mins > 0.05 else 0
            lines = [
                ("Diktate", f"{s['count']:,}".replace(",", ".")),
                ("Wörter", f"{int(s['words']):,}".replace(",", ".")),
                ("Sprechzeit", f"{mins:.1f} min"),
                ("Token rein", f"{s['tok_in']:,}".replace(",", ".")),
                ("Token raus", f"{s['tok_out']:,}".replace(",", ".")),
                ("Ø Token / min", f"{per_min:,.0f}".replace(",", ".")),
                ("Kosten (ca.)", f"{s['cost']:.3f} $"),
            ]
            card = ctk.CTkFrame(self.stat_box, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
            card.grid(row=0, column=i, sticky="nsew", padx=6, pady=4)
            self.stat_box.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(card, text=title, font=self.f_h, text_color=TXT).pack(anchor="w", padx=18, pady=(16, 8))
            for k, v in lines:
                r = ctk.CTkFrame(card, fg_color="transparent")
                r.pack(fill="x", padx=18, pady=2)
                ctk.CTkLabel(r, text=k, font=self.f_s, text_color=MUT).pack(side="left")
                ctk.CTkLabel(r, text=v, font=self.f_n, text_color=TXT).pack(side="right")
            ctk.CTkLabel(card, text="").pack(pady=4)

    # ------------------------------------------------------------ Einstellungen
    def _build_settings(self):
        p = self.pages["Einstellungen"]
        self._title(p, "Einstellungen")
        sc = ctk.CTkScrollableFrame(p, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=22, pady=(0, 14))
        cfg = self.app.cfg
        env = read_env_file()
        card = ctk.CTkFrame(sc, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
        card.pack(fill="x", padx=12, pady=6)

        def row(label, widget_fn):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=20, pady=7)
            ctk.CTkLabel(r, text=label, font=self.f_n, text_color=TXT, width=190, anchor="w").pack(side="left")
            w = widget_fn(r)
            w.pack(side="left", fill="x", expand=True)
            return w

        pr = ctk.CTkFrame(card, fg_color="transparent")
        pr.pack(fill="x", padx=20, pady=(14, 7))
        ctk.CTkLabel(pr, text="SpeakIt aktiv", font=self.f_n, text_color=TXT, width=190, anchor="w").pack(side="left")
        ctk.CTkSwitch(pr, text="Aus = Taste wird nicht abgefangen", variable=self.enabled_var, command=self._on_power,
                      progress_color=ORANGE, font=self.f_s, text_color=MUT).pack(side="left")
        self.hotkey = list(cfg["hotkey"])
        self.hk_var = ctk.StringVar(value=pretty(self.hotkey))
        hk_row = ctk.CTkFrame(card, fg_color="transparent")
        hk_row.pack(fill="x", padx=20, pady=7)
        ctk.CTkLabel(hk_row, text="Taste oder Tastenkombination", font=self.f_n, text_color=TXT, width=190, anchor="w",
                     wraplength=180, justify="left").pack(side="left")
        self.hk_btn = LiquidButton(hk_row, textvariable=self.hk_var, command=self._capture, width=230, height=36,
                                   bg=CARD, fill=BG, border=LINE, fg=TXT, fg_active=TXT, font=("Segoe UI", 13),
                                   radius=10, hover=0.5)
        self.hk_btn.pack(side="left")
        self._btn(hk_row, "Copilot-Taste", self._copilot, primary=False, width=120).pack(side="left", padx=8)
        ctk.CTkLabel(card, text="Eine einzelne Taste (z. B. Enter, F9, M) oder eine Kombination (z. B. Strg + Alt + Leertaste): "
                                "Knopf anklicken, Taste(n) drücken, loslassen. Die Taste wird dabei komplett abgefangen.",
                     font=self.f_s, text_color=MUT, wraplength=620, justify="left").pack(anchor="w", padx=20, pady=(0, 6))

        def opt(values, current):
            def make(r):
                var = ctk.StringVar(value=current)
                w = ctk.CTkOptionMenu(r, values=values, variable=var, height=36, corner_radius=10, font=self.f_n,
                                      fg_color=BG, text_color=TXT, button_color=SEL, button_hover_color=LINE,
                                      dropdown_font=self.f_n, width=300)
                w.var = var
                return w
            return make

        self.w_mode = row("Bedienung", opt(list(MODES), next(k for k, v in MODES.items() if v == cfg["mode"])))
        self.w_lang = row("Sprache", opt(list(LANGS), next((k for k, v in LANGS.items() if v == cfg["language"]), "Deutsch")))
        try:
            mics = ["Standard"] + list_mics()
        except Exception:
            mics = ["Standard"]
        self.w_mic = row("Mikrofon", opt(mics, cfg["mic"] if cfg["mic"] in mics else "Standard"))
        self.w_prov = row("STT-Anbieter", opt(["groq", "openai"], cfg["stt_provider"]))
        sr = ctk.CTkFrame(card, fg_color="transparent")
        sr.pack(fill="x", padx=20, pady=7)
        ctk.CTkLabel(sr, text="Klang", font=self.f_n, text_color=TXT, width=190, anchor="w").pack(side="left")
        self.snd_var = ctk.StringVar(value=cfg["sound_preset"] if cfg["sound_preset"] in sounds.PRESETS else sounds.DEFAULT)
        ctk.CTkOptionMenu(sr, values=sounds.PRESETS, variable=self.snd_var, height=36, corner_radius=10, font=self.f_n,
                          fg_color=BG, text_color=TXT, button_color=SEL, button_hover_color=LINE,
                          dropdown_font=self.f_n, width=210,
                          command=lambda v: sounds.preview(v)).pack(side="left")
        self._btn(sr, "Anhören", lambda: sounds.preview(self.snd_var.get()), primary=False, width=90).pack(side="left", padx=8)

        def sw(label, value):
            var = ctk.BooleanVar(value=value)
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=20, pady=7)
            ctk.CTkLabel(r, text=label, font=self.f_n, text_color=TXT, width=190, anchor="w").pack(side="left")
            ctk.CTkSwitch(r, text="", variable=var, progress_color=ORANGE).pack(side="left")
            return var

        cr = ctk.CTkFrame(card, fg_color="transparent")
        cr.pack(fill="x", padx=20, pady=7)
        ctk.CTkLabel(cr, text="Textnachbearbeitung (Claude)", font=self.f_n, text_color=TXT, width=190, anchor="w",
                     wraplength=180, justify="left").pack(side="left")
        ctk.CTkSwitch(cr, text="Aus = bis zu 2x schneller, dafür Rohtext ohne Glättung", variable=self.clean_var,
                      command=self._on_clean, progress_color=ORANGE, font=self.f_s, text_color=MUT).pack(side="left")
        cmp_ = cleanup_comparison()
        (n_s, s_with, s_without), (n_l, l_with, l_without) = WAIT["short"], WAIT["long"]
        de = lambda x: f"{x:.2f}".replace(".", ",")  # noqa: E731
        de1 = lambda x: f"{x:.1f}".replace(".", ",")  # noqa: E731
        ctk.CTkLabel(
            card, font=self.f_s, text_color=MUT, wraplength=640, justify="left",
            text=(f"Vergleich (Schätzung, Listenpreise): 10.000 Wörter diktiert (ca. {cmp_['n']} Diktate) kosten mit Haiku "
                  f"ca. {de(cmp_['with'])} $ (Groq {de(cmp_['groq'])} $ + Haiku {de(cmp_['haiku'])} $), ohne Haiku "
                  f"ca. {de(cmp_['without'])} $. Das sind ca. {cmp_['factor']:.0f}x weniger.\n"
                  f"Wartezeit nach dem Loslassen: ein Satz ({n_s} Wörter) mit Haiku ca. {de1(s_with)} s, ohne ca. "
                  f"{de1(s_without)} s. Ein Absatz ({n_l} Wörter) mit Haiku ca. {de1(l_with)} s, ohne ca. "
                  f"{de1(l_without)} s."),
        ).pack(anchor="w", padx=20, pady=(0, 8))
        self.v_sounds = sw("Töne", cfg["sounds"])
        self.v_auto = sw("Mit Windows starten", autostart.is_enabled())

        keys = ctk.CTkFrame(sc, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
        keys.pack(fill="x", padx=12, pady=6)
        self.key_entries = {}
        for label, name in (("Groq API-Key", "GROQ_API_KEY"), ("Anthropic API-Key", "ANTHROPIC_API_KEY"),
                            ("OpenAI API-Key (optional)", "OPENAI_API_KEY")):
            r = ctk.CTkFrame(keys, fg_color="transparent")
            r.pack(fill="x", padx=20, pady=7)
            ctk.CTkLabel(r, text=label, font=self.f_n, text_color=TXT, width=190, anchor="w").pack(side="left")
            have = bool(os.environ.get(name)) and not env.get(name)
            e = ctk.CTkEntry(r, show="•", height=36, corner_radius=10, font=self.f_n, width=300,
                             placeholder_text="(mitgeliefert)" if have else "")
            if env.get(name):
                e.insert(0, env[name])
            e.pack(side="left", fill="x", expand=True)
            self.key_entries[name] = e

        row2 = ctk.CTkFrame(sc, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=10)
        self._btn(row2, "Speichern", self._save_settings).pack(side="left")
        self._btn(row2, "Datenordner öffnen", lambda: os.startfile(DATA), primary=False).pack(side="left", padx=10)
        if FROZEN:
            self._btn(row2, "Deinstallieren", self.app.uninstall, primary=False).pack(side="left")
        self.set_msg = ctk.CTkLabel(row2, text="", font=self.f_s, text_color=GREEN)
        self.set_msg.pack(side="left", padx=10)

    def _capture(self):
        self.hk_var.set("Taste(n) drücken, dann loslassen …")

        def done(keys):
            def apply():
                self.hotkey[:] = keys
                self.hk_var.set(pretty(keys))
            self.ui.call(apply)

        self.app.hk.start_capture(done)

    def _copilot(self):
        self.hotkey[:] = COPILOT_KEY
        self.hk_var.set(pretty(COPILOT_KEY))

    def _save_settings(self):
        cfg = self.app.cfg
        mic = self.w_mic.var.get()
        cfg.set(
            hotkey=list(self.hotkey), mode=MODES[self.w_mode.var.get()], language=LANGS[self.w_lang.var.get()],
            mic="" if mic == "Standard" else mic, stt_provider=self.w_prov.var.get(),
            cleanup=bool(self.clean_var.get()), sounds=self.v_sounds.get(), sound_preset=self.snd_var.get(),
        )
        save_env({k: e.get().strip() for k, e in self.key_entries.items() if e.get().strip()})
        if self.v_auto.get() != autostart.is_enabled():
            autostart.set_enabled(self.v_auto.get())
        try:
            self.app.hk.set_hotkey(self.hotkey)
            self.set_msg.configure(text="Gespeichert", text_color=GREEN)
        except ValueError:
            self.set_msg.configure(text="Taste unbekannt", text_color=RED)
        self.app.refresh_tray()
        self.side_info.configure(text=f"Taste: {pretty(cfg['hotkey'])}")
        self.dirty.update(("Verlauf", "Kontexte", "Statistik"))
