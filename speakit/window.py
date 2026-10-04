"""Hauptfenster: Verlauf mit Wort-Korrektur, Kontexte, Statistik, Einstellungen."""
import datetime
import os
import tkinter as tk

import customtkinter as ctk

from . import autostart
from .audio import list_mics
from .config import DATA, FROZEN, read_env_file, save_env
from .hotkey import pretty
from .storage import _split

BG, SIDE, CARD, LINE = "#F4F1EA", "#ECE8DF", "#FFFFFF", "#E3DED2"
TXT, MUT, ACC, ACC_H, GREEN, RED = "#1D1C1A", "#7B766B", "#1D1C1A", "#3A3835", "#2E7D5B", "#C2410C"
SEL = "#DDD8CB"

MODES = {
    "Halten oder Tippen (beides)": "both",
    "Nur halten (Push-to-talk)": "hold",
    "Nur tippen (Start/Stopp)": "toggle",
}
LANGS = {"Deutsch": "de", "Englisch": "en", "Automatisch": ""}
COPILOT_KEY = ["windows", "shift", "f23"]
PAGES = ["Verlauf", "Kontexte", "Statistik", "Einstellungen"]
DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


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
        self.selection = ""
        self.hist_limit = 30

    # ------------------------------------------------------------ Aufbau
    def build(self):
        r = self.root
        r.title("SpeakIt")
        r.configure(fg_color=BG)
        w, h = 1000, 700
        r.geometry(f"{w}x{h}+{(r.winfo_screenwidth() - w) // 2}+{(r.winfo_screenheight() - h) // 2}")
        r.minsize(880, 580)
        r.protocol("WM_DELETE_WINDOW", self.hide)
        self.f_title = ctk.CTkFont(family="Segoe UI Semibold", size=24)
        self.f_h = ctk.CTkFont(family="Segoe UI Semibold", size=14)
        self.f_n = ctk.CTkFont(family="Segoe UI", size=13)
        self.f_s = ctk.CTkFont(family="Segoe UI", size=12)

        side = ctk.CTkFrame(r, fg_color=SIDE, corner_radius=0, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="●  SpeakIt", font=ctk.CTkFont(family="Segoe UI Semibold", size=18),
                     text_color=TXT).pack(anchor="w", padx=22, pady=(26, 22))
        self.nav = {}
        for name in PAGES:
            b = ctk.CTkButton(
                side, text=name, anchor="w", height=40, corner_radius=12, font=self.f_n,
                fg_color="transparent", hover_color=SEL, text_color=TXT,
                command=lambda n=name: self.show_page(n),
            )
            b.pack(fill="x", padx=12, pady=2)
            self.nav[name] = b
        self.side_info = ctk.CTkLabel(side, text="", font=self.f_s, text_color=MUT, justify="left")
        self.side_info.pack(side="bottom", anchor="w", padx=22, pady=(4, 18))
        self.mini = ctk.CTkFrame(side, fg_color=CARD, corner_radius=14, border_width=1, border_color=LINE)
        self.mini.pack(side="bottom", fill="x", padx=12, pady=(0, 6))
        self.mini_rows = {}
        for key in ("Heute", "Monat", "Gesamt"):
            mrow = ctk.CTkFrame(self.mini, fg_color="transparent")
            mrow.pack(fill="x", padx=12, pady=(8, 0) if key == "Heute" else (4, 0))
            ctk.CTkLabel(mrow, text=key, font=self.f_s, text_color=MUT).pack(anchor="w")
            lab = ctk.CTkLabel(mrow, text="", font=self.f_s, text_color=TXT)
            lab.pack(anchor="w")
            self.mini_rows[key] = lab
        ctk.CTkLabel(self.mini, text="", height=4).pack()

        self.content = ctk.CTkFrame(r, fg_color=BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)
        self.pages = {}
        for name in PAGES:
            self.pages[name] = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_history()
        self._build_contexts()
        self._build_stats()
        self._build_settings()
        self.built = True

    def _title(self, parent, title, sub=""):
        ctk.CTkLabel(parent, text=title, font=self.f_title, text_color=TXT).pack(anchor="w", padx=34, pady=(28, 2))
        if sub:
            ctk.CTkLabel(parent, text=sub, font=self.f_s, text_color=MUT, justify="left",
                         wraplength=640).pack(anchor="w", padx=34, pady=(0, 14))

    def _btn(self, parent, text, cmd, primary=True, **kw):
        if primary:
            return ctk.CTkButton(parent, text=text, command=cmd, font=self.f_n, corner_radius=12, height=36,
                                 fg_color=ACC, hover_color=ACC_H, text_color="white", **kw)
        return ctk.CTkButton(parent, text=text, command=cmd, font=self.f_n, corner_radius=12, height=36,
                             fg_color="transparent", hover_color=SEL, text_color=TXT,
                             border_width=1, border_color=LINE, **kw)

    # ------------------------------------------------------------ Anzeigen
    def show(self, page=None):
        if not self.built:
            self.build()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)  # sonst bleibt es hinter dem aktiven Fenster
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
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
            self.nav[n].configure(fg_color=SEL if n == name else "transparent")
        self.pages[name].pack(fill="both", expand=True)
        if name == "Verlauf":
            self.refresh_history()
        elif name == "Kontexte":
            self.refresh_contexts()
        elif name == "Statistik":
            self.refresh_stats()
        self.side_info.configure(text=f"Taste: {pretty(self.app.cfg['hotkey'])}")
        self.refresh_mini()

    def refresh_mini(self):
        now = datetime.datetime.now()
        starts = {
            "Heute": now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp(),
            "Monat": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp(),
            "Gesamt": 0,
        }
        for key, since in starts.items():
            st = self.app.history.stats(since)
            money = f"{st['cost']:.3f}".replace(".", ",")
            words = f"{int(st['words']):,}".replace(",", ".")
            self.mini_rows[key].configure(text=f"{money} $  ·  {words} Wörter")

    def on_new_dictation(self):
        self.refresh_mini()
        if self.visible and self.page == "Verlauf":
            self.refresh_history()
        elif self.visible and self.page == "Statistik":
            self.refresh_stats()

    # ------------------------------------------------------------ Verlauf
    def _build_history(self):
        p = self.pages["Verlauf"]
        self._title(p, "Verlauf", "Klicke ein Wort an oder markiere mehrere, dann unten auf „Korrigieren“. "
                                  "SpeakIt merkt sich die Korrektur und lernt dazu.")
        self.bar = ctk.CTkFrame(p, fg_color=CARD, corner_radius=14, border_width=1, border_color=LINE)
        self.bar_label = ctk.CTkLabel(self.bar, text="", font=self.f_n, text_color=TXT)
        self.bar_label.pack(side="left", padx=16, pady=10)
        self._btn(self.bar, "Korrigieren …", self.open_correction).pack(side="right", padx=10, pady=8)
        self.hist = ctk.CTkScrollableFrame(p, fg_color=BG, corner_radius=0)
        self.hist.pack(fill="both", expand=True, padx=22, pady=(0, 8))

    def refresh_history(self):
        for w in self.hist.winfo_children():
            w.destroy()
        rows = self.app.history.recent(self.hist_limit)
        self._set_selection("")
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
                     font=("Segoe UI", 12), cursor="arrow", padx=0, pady=0, spacing1=2, spacing3=2,
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
            ctk.CTkButton(top, text=text, command=cmd, width=34 if text == "✕" else 74, height=28,
                          corner_radius=9, font=self.f_s, fg_color="transparent", hover_color=SEL,
                          text_color=MUT if text == "✕" else TXT, border_width=0 if text == "✕" else 1,
                          border_color=LINE).pack(side="right", padx=(6, 0))
        raw_btn = ctk.CTkButton(top, text="Original", command=toggle, width=74, height=28, corner_radius=9,
                                font=self.f_s, fg_color="transparent", hover_color=SEL, text_color=MUT)
        raw_btn.pack(side="right")
        tw.pack(fill="x", padx=16, pady=(8, 14))
        fill()
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
        self.sel_row = getattr(tw, "_row", None)
        self._set_selection(sel)

    def _set_selection(self, sel):
        self.selection = sel
        if sel:
            self.bar_label.configure(text=f"Ausgewählt:  „{sel[:60]}“")
            if not self.bar.winfo_ismapped():
                self.bar.pack(fill="x", padx=34, pady=(0, 10), before=self.hist)
        elif self.bar.winfo_ismapped():
            self.bar.pack_forget()

    def open_correction(self):
        wrong = self.selection
        if not wrong:
            return
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Wort korrigieren")
        dlg.configure(fg_color=BG)
        dlg.geometry(f"460x470+{self.root.winfo_x() + 260}+{self.root.winfo_y() + 120}")
        dlg.transient(self.root)
        dlg.after(150, lambda: (dlg.lift(), dlg.focus_force()))
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
        ctx_var = ctk.StringVar(value=next(iter(names)))
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
                      text_color=TXT, progress_color=GREEN).pack(pady=(10, 4), **pad)
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
            if replace_var.get() and wr:
                self.app.contexts.add_correction(cid, wr, right)
                row = getattr(self, "sel_row", None)
                if row and wr in row["text"]:
                    self.app.history.update_text(row["id"], row["text"].replace(wr, right))
            else:
                self.app.contexts.add_term(cid, right)
            dlg.destroy()
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
        for w in self.ctx_list.winfo_children():
            w.destroy()
        for c in self.app.contexts.items:
            f = ctk.CTkFrame(self.ctx_list, fg_color=CARD if c["id"] == self.sel_ctx else "transparent",
                             corner_radius=12, border_width=1 if c["id"] == self.sel_ctx else 0, border_color=LINE)
            f.pack(fill="x", pady=2)
            if c["id"] == "general":
                ctk.CTkLabel(f, text="immer", font=self.f_s, text_color=MUT, width=44).pack(side="left", padx=(10, 0))
            else:
                sw = ctk.CTkSwitch(f, text="", width=44, progress_color=GREEN,
                                   command=lambda cid=c["id"]: self._toggle_ctx(cid, sw_vars[cid].get()))
                sw_vars = getattr(self, "_sw_vars", {})
                var = ctk.BooleanVar(value=c["active"])
                sw_vars[c["id"]] = var
                self._sw_vars = sw_vars
                sw.configure(variable=var)
                sw.pack(side="left", padx=(10, 0), pady=8)
            ctk.CTkButton(f, text=f"{c['name']}  ({len(c['terms'])})", anchor="w", fg_color="transparent",
                          hover_color=SEL, text_color=TXT, font=self.f_n, height=36, corner_radius=10,
                          command=lambda cid=c["id"]: self._select_ctx(cid)).pack(side="left", fill="x", expand=True)
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
        for w in self.stat_box.winfo_children():
            w.destroy()
        now = datetime.datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        for i, (title, since) in enumerate((("Heute", today), ("Dieser Monat", month), ("Gesamt", 0))):
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

        self.hotkey = list(cfg["hotkey"])
        self.hk_var = ctk.StringVar(value=pretty(self.hotkey))
        hk_row = ctk.CTkFrame(card, fg_color="transparent")
        hk_row.pack(fill="x", padx=20, pady=7)
        ctk.CTkLabel(hk_row, text="Aufnahme-Taste", font=self.f_n, text_color=TXT, width=190, anchor="w").pack(side="left")
        self.hk_btn = ctk.CTkButton(hk_row, textvariable=self.hk_var, command=self._capture, width=230, height=36,
                                    corner_radius=10, font=self.f_n, fg_color=BG, hover_color=SEL, text_color=TXT,
                                    border_width=1, border_color=LINE)
        self.hk_btn.pack(side="left")
        self._btn(hk_row, "Copilot-Taste", self._copilot, primary=False, width=120).pack(side="left", padx=8)

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

        def sw(label, value):
            var = ctk.BooleanVar(value=value)
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=20, pady=7)
            ctk.CTkLabel(r, text=label, font=self.f_n, text_color=TXT, width=190, anchor="w").pack(side="left")
            ctk.CTkSwitch(r, text="", variable=var, progress_color=GREEN).pack(side="left")
            return var

        self.v_clean = sw("Textnachbearbeitung (Claude)", cfg["cleanup"])
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
            cleanup=self.v_clean.get(), sounds=self.v_sounds.get(),
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
