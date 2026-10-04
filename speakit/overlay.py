"""Kleine Kapsel unten mittig.

Aufnahme: ruhiger roter Punkt, runde Pegelbalken, Sekundenticker.
Verarbeitung: orange Flüssigkeit strömt von rechts ein, schwappt (Wellengleichung + Kipp-Feder), spritzt und
steigt bis zur Decke der Kapsel. Ist sie voll, ist der Text fertig und die Kapsel klappt zu.
Die Kapsel fährt aus der Mitte auf und schrumpft zur Mitte wieder zu.
"""
import collections
import ctypes
import math
import random
import time
import tkinter as tk
import tkinter.font as tkfont

KEY = "#ff00ff"  # transparente Farbe
BG = "#17171a"
OUTLINE = "#f59e0b"  # dünne orange Kontur
RED, GREEN, FG, MUTED = "#ef4444", "#22c55e", "#f4f4f5", "#9ca3af"
DOT = "#f59e0b"  # Aufnahme-Punkt
LIQUID, LIQUID_HI, LIQUID_BACK = "#f59e0b", "#fde68a", "#fbbf24"
LIQUID_DONE = "#fcd27a"  # helleres Orange, sobald der Text fertig ist
GLOW = 0.28  # Dauer des Übergangs in Sekunden
BASE_H = 30  # Kapselhöhe (Basis-Einheiten, wird mit DPI skaliert)
MAX_W = 300
BARS = 9
COLS = 56  # Spalten der Wasseroberfläche


def dpi_scale() -> float:
    try:
        return max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96)
    except Exception:
        return 1.0


def work_area():
    """Arbeitsbereich ohne Taskleiste: (links, oben, rechts, unten)."""
    try:
        rect = (ctypes.c_long * 4)()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, rect, 0)
        return tuple(rect)
    except Exception:
        return None


def fmt_time(sec: float) -> str:
    sec = int(sec)
    if sec >= 3600:
        return "1h"
    return f"{sec // 60}:{sec % 60:02d}"


class Overlay:
    def __init__(self, root, recorder):
        self.rec = recorder
        self.k = dpi_scale()
        k = self.k
        self.W, self.H = int(MAX_W * k), int(BASE_H * k)
        self.lw = max(1, round(k * 1.8) - 1)  # Konturstärke
        self.mode = None  # None | rec | busy | finish | msg
        self.text, self.msg_col = "", GREEN
        self.e = 0.0  # Aufklapp-Grad 0..1
        self.target = 0.0
        self.cur_w = 0.0
        self.want_w = 0.0
        self.close_at = 0.0
        self.last = time.monotonic()
        self.levels = collections.deque([0.0] * BARS, maxlen=BARS)
        self.lvl_t = 0.0
        self.tau = 2.0
        self.dot_col = DOT
        self.glow_t = 0.0  # Start des Fertig-Übergangs (0 = keiner)
        self.on_full = None  # Rückruf, sobald die Kapsel voll ist (Plop)
        self.busy_t = 0.0
        self._reset_liquid()

        self.win = tk.Toplevel(root)
        w = self.win
        self.timer_font = tkfont.Font(root=root, family="Segoe UI Semibold", size=11)
        self.cur_w = self.want_w = self._rec_w()  # Startbreite = Aufnahmebreite
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=KEY)
        w.attributes("-transparentcolor", KEY)
        wa = work_area()
        if wa:
            x = (wa[0] + wa[2]) // 2 - self.W // 2
            y = wa[3] - self.H - int(14 * k)
        else:
            x = (w.winfo_screenwidth() - self.W) // 2
            y = w.winfo_screenheight() - self.H - int(68 * k)
        w.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.cv = tk.Canvas(w, width=self.W, height=self.H, bg=KEY, highlightthickness=0)
        self.cv.pack()
        w.update_idletasks()
        try:  # nie den Fokus klauen, klick-durchlässig
            u = ctypes.windll.user32
            hwnd = u.GetParent(w.winfo_id()) or w.winfo_id()
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, ex | 0x08000000 | 0x80 | 0x20)
        except Exception:
            pass
        w.withdraw()
        self.visible = False

    # ------------------------------------------------------------ Steuerung
    def _rec_w(self):
        """Feste Kapselbreite im Aufnahmemodus: Punkt, Balken und Platz für die breiteste Anzeige (59:59)."""
        return (27 + BARS * 4 + 3 + 9) * self.k + self.timer_font.measure("59:59")

    def _recording(self):
        return getattr(self.rec, "stream", None) is not None

    def _open(self, mode):
        self.mode = mode
        self.target = 1.0
        if not self.visible:
            self.e = 0.0
            self.cur_w = self.want_w  # frisch geöffnet: gleich in Zielbreite, kein Nachziehen
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.visible = True

    def set_state(self, state, text="", hold_ms=0):
        k = self.k
        if state == "idle":
            if not self._recording():
                self.mode, self.target = None, 0.0
            return
        if state == "rec_clean":  # Feinschliff aktiv: Punkt wird rot
            self.dot_col = RED
            return
        if state == "rec":
            self.dot_col = DOT
            self.levels.extend([0.0] * BARS)
            self.want_w = self._rec_w()
            self._open("rec")
            return
        if self._recording():  # eine neue Aufnahme hat Vorrang
            return
        if state == "busy":
            if self.mode != "busy":
                self.glow_t = 0.0
                self._reset_liquid()
                self.busy_t = 0.0
                self.want_w = self._rec_w()
            try:
                self.tau = max(0.8, float(text) / 2)
            except ValueError:
                self.tau = 2.0
            self._open("busy")
        elif state == "done" and text == "Eingefügt":
            if self.mode == "busy":
                self.mode = "finish"
                self.close_at = 0.0
            elif self.visible:
                self.mode, self.target = None, 0.0
        else:  # kurze Meldung (done = grün, err = rot)
            self.text = text
            self.msg_col = GREEN if state == "done" else RED
            self.want_w = min(MAX_W * k, (len(text) * 6.4 + 46) * k)
            self.close_at = time.monotonic() + max(0.8, hold_ms / 1000)
            self._open("msg")

    # ------------------------------------------------------------ Flüssigkeit
    def _reset_liquid(self):
        self.p = 0.0  # Füllstand 0..1 (1 = bis zur Decke)
        self.h = [0.0] * COLS  # Wellenhöhe pro Spalte (Basis-Einheiten)
        self.v = [0.0] * COLS
        self.tilt, self.tilt_v = 0.0, 0.0  # Schwappen der ganzen Wassermasse
        self.drops = []
        self.kick_t = 0.0
        self.pour_t = 0.0
        self.pending_drop = False

    def _physics(self, dt):
        k = self.k
        target = 1.0 if self.mode == "finish" else min(0.93, 1 - math.exp(-self.busy_t / self.tau))
        rate = 16.0 if self.mode == "finish" else 2.2
        dp = (target - self.p) * min(1.0, dt * rate)
        self.p += dp
        # Einströmen von rechts: Stoß in die rechten Spalten, Wassermasse kippt nach links
        self.pour_t -= dt
        if self.pour_t <= 0 and self.mode == "busy":
            self.pour_t = random.uniform(0.35, 0.8)
            for j in range(COLS - 7, COLS):
                self.v[j] += random.uniform(120, 260)
            self.tilt_v -= random.uniform(30, 70)
        self.kick_t -= dt
        if self.kick_t <= 0:
            self.kick_t = random.uniform(0.15, 0.45)
            self.v[random.randrange(COLS)] += random.uniform(-160, 160)
            self.tilt_v += random.uniform(-25, 25) + dp * 500
        n_sub = max(1, int(dt / 0.006))
        h = dt / n_sub
        for _ in range(n_sub):
            for i in range(COLS):
                l = self.h[i - 1] if i > 0 else self.h[i]
                r = self.h[i + 1] if i < COLS - 1 else self.h[i]
                a = 1500 * (l + r - 2 * self.h[i]) - 3.2 * self.v[i] - 22 * self.h[i]
                self.v[i] += a * h
            for i in range(COLS):
                self.h[i] += self.v[i] * h
            self.tilt_v += (-36 * self.tilt - 1.2 * self.tilt_v) * h
            self.tilt += self.tilt_v * h
        self.tilt = max(-18, min(18, self.tilt))
        # Spritzer von der Oberfläche
        if self.mode == "busy" and self.p > 0.04 and random.random() < dt * 5.0:
            self.pending_drop = True
        for d in self.drops:
            d["vy"] += 520 * k * dt
            d["x"] += d["vx"] * dt
            d["y"] += d["vy"] * dt
            d["life"] -= dt
        self.drops = [d for d in self.drops if d["life"] > 0]

    def _surface(self, x1, x2, y1, y2, layer=0):
        """Oberfläche als Liste (x, y), y wächst nach unten. layer 1 = hintere, versetzte Welle."""
        k = self.k
        d = y2 - y1
        level = y2 - self.p * (d + 4 * k) - (1.6 * k if layer else 0.0)
        amp = max(0.0, min(1.0, (1 - self.p) * 3.0))  # nahe der Decke glättet sich alles
        inflow = 9 * math.exp(-self.busy_t * 1.4) if self.mode == "busy" else 0.0  # anfangs rechts höher
        hh = list(self.h)
        for _ in range(3):  # glätten, damit die Fläche weich fließt statt zackig zu sein
            hh = [(hh[max(i - 1, 0)] + 2 * hh[i] + hh[min(i + 1, COLS - 1)]) / 4 for i in range(COLS)]
        t = self.busy_t
        w = x2 - x1
        pts = []
        for i in range(COLS):
            fx = i / (COLS - 1)
            if layer == 0:
                # Hauptwelle: zwei gegenläufige Wanderwellen plus Simulation
                rip = 1.9 * math.sin(t * 3.4 - fx * 7.0) + 1.1 * math.sin(t * 5.6 + fx * 11.0 + 0.8)
                wave = hh[i] * 1.25 + self.tilt * (fx - 0.5) * 1.7 + inflow * (fx ** 2)
            else:
                # Hintere Welle: langsamer, andere Phase, flacher
                rip = 2.2 * math.sin(t * 2.3 - fx * 5.0 + 1.9) + 0.9 * math.sin(t * 4.1 + fx * 8.5 + 2.6)
                wave = hh[COLS - 1 - i] * 0.7 + self.tilt * (0.5 - fx) * 1.2
            pts.append((x1 + w * fx, level - (wave + rip) * k * amp))
        return pts

    def _extent(self, x, x1, x2, cy, r):
        """Senkrechter Bereich der Kapsel an der Stelle x."""
        if x < x1 + r:
            dx = (x1 + r) - x
        elif x > x2 - r:
            dx = x - (x2 - r)
        else:
            return cy - r, cy + r
        half = math.sqrt(max(0.0, r * r - dx * dx))
        return cy - half, cy + half

    # ------------------------------------------------------------ Zeichnen
    def tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        if not self.visible:
            return
        self.e += (self.target - self.e) * (1 - math.exp(-dt * 15))
        self.cur_w += (self.want_w - self.cur_w) * (1 - math.exp(-dt * 12))
        if self.mode == "msg" and now >= self.close_at:
            self.mode, self.target = None, 0.0
        if self.mode in ("busy", "finish"):
            self.busy_t += dt
            self._physics(dt)
            if self.mode == "finish" and self.p > 0.985:
                if self.close_at == 0.0:
                    self.glow_t = now  # voll: weich heller werden, Plop, dann zuklappen
                    self.close_at = now + GLOW + 0.12
                    if self.on_full:
                        self.on_full()
                elif now >= self.close_at:
                    self.mode, self.target = "closing", 0.0  # volle Kapsel schrumpft zur Mitte
        if self.mode in (None, "closing") and self.target == 0.0 and self.e < 0.02:
            self.cv.delete("all")
            self.win.withdraw()
            self.visible = False
            return
        self._draw()

    @staticmethod
    def _capsule(x1, y1, x2, y2, n=20):
        """Umriss einer Kapsel als Punktliste (zwei Halbkreise, durch Geraden verbunden)."""
        r = (y2 - y1) / 2
        cy = (y1 + y2) / 2
        pts = []
        for i in range(n + 1):  # rechts, von oben nach unten
            a = -math.pi / 2 + math.pi * i / n
            pts += [x2 - r + r * math.cos(a), cy + r * math.sin(a)]
        for i in range(n + 1):  # links, von unten nach oben
            a = math.pi / 2 + math.pi * i / n
            pts += [x1 + r + r * math.cos(a), cy + r * math.sin(a)]
        return pts

    def _geometry(self):
        k, e = self.k, self.e
        hd = (self.H - self.lw - 2 * k) * (0.3 + 0.7 * min(1.0, e * 1.25))
        wd = max(hd, self.cur_w * e)
        cx, cy = self.W / 2, self.H / 2
        return cx - wd / 2, cy - hd / 2, cx + wd / 2, cy + hd / 2

    def _span(self, y, x1, x2, cy, r):
        dy = y - cy
        if abs(dy) >= r:
            return None
        dx = math.sqrt(r * r - dy * dy)
        return (x1 + r - dx, x2 - r + dx)

    def _draw(self):
        c, k = self.cv, self.k
        c.delete("all")
        x1, y1, x2, y2 = self._geometry()
        d = y2 - y1
        r = d / 2
        lw = self.lw
        shape = self._capsule(x1, y1, x2, y2)
        c.create_polygon(shape, fill=BG, outline=BG)
        if self.mode in ("busy", "finish", "closing"):
            self._draw_liquid(x1, y1, x2, y2)
        # Kontur als ein geschlossener Pfad, damit zwischen Bögen und Geraden keine Lücke bleibt
        c.create_polygon(shape, fill="", outline=OUTLINE, width=lw, joinstyle="round")
        if self.e < 0.96:
            return
        cy = self.H / 2
        left = x1
        if self.mode == "rec":
            dx, dy = left + 15 * k, cy
            col = self.dot_col
            c.create_oval(dx - 4.6 * k, dy - 4.6 * k, dx + 4.6 * k, dy + 4.6 * k, fill=col, outline=col)
            self.lvl_t += 1
            if self.lvl_t % 2 == 0:
                self.levels.append(self.rec.level)
            for i, v in enumerate(self.levels):
                hh = (3 + v * 15) * k
                x = left + (27 + i * 4) * k
                c.create_line(x, cy - hh / 2, x, cy + hh / 2, fill=FG, width=max(2, round(2.4 * k)),
                              capstyle="round")
            txt = fmt_time(self.rec.seconds)
            c.create_text(left + (27 + BARS * 4 + 3) * k, cy, text=txt, fill=FG, anchor="w", font=self.timer_font)
            # Feste Breite für die breiteste Anzeige (59:59), damit die Kapsel beim Zählen nicht wackelt
            self.want_w = self._rec_w()
        elif self.mode == "msg":
            rr = 4 * k
            dx = left + 15 * k
            c.create_oval(dx - rr, cy - rr, dx + rr, cy + rr, fill=self.msg_col, outline=self.msg_col)
            c.create_text(left + 27 * k, cy, text=self.text, fill=FG, anchor="w", font=("Segoe UI", 9))

    def _layer_polys(self, cols, ix1, ix2, cy, ir):
        """Fläche unter einer Oberfläche, an den runden Enden der Kapsel sauber abgeschnitten."""
        xs = [c_[0] for c_ in cols]
        for j in range(1, 14):
            off = ir * (1 - math.cos(j / 14 * math.pi / 2))
            xs += [ix1 + off, ix2 - off]
        xs = sorted(set(xs))

        def ysurf(x):
            for a_, b_ in zip(cols, cols[1:]):
                if a_[0] <= x <= b_[0]:
                    f = (x - a_[0]) / max(1e-9, b_[0] - a_[0])
                    return a_[1] + (b_[1] - a_[1]) * f
            return cols[0][1] if x < cols[0][0] else cols[-1][1]

        top, bottom, hi = [], [], []
        for x in xs:
            ys = ysurf(x)
            lo, up = self._extent(x, ix1, ix2, cy, ir)
            yt = max(ys, lo)
            if yt >= up:
                continue
            top.append((x, yt))
            bottom.append((x, up))
            if yt > lo + 0.3:
                hi.append((x, yt))
        return top, bottom, hi

    def _draw_liquid(self, x1, y1, x2, y2):
        c, k = self.cv, self.k
        d = y2 - y1
        r = d / 2
        cy = (y1 + y2) / 2
        inset = 1.5 * k
        ix1, ix2, iy1, iy2 = x1 + inset, x2 - inset, y1 + inset, y2 - inset
        ir = r - inset
        if self.p < 0.003:
            return
        f = min(1.0, (time.monotonic() - self.glow_t) / GLOW) if self.glow_t else 0.0
        f = f * f * (3 - 2 * f)  # weich ein- und ausblenden
        liq, back_col = _mix(LIQUID, LIQUID_DONE, f), _mix(LIQUID_BACK, LIQUID_DONE, f)
        hi_col = _mix(LIQUID_HI, LIQUID_DONE, f)
        # hintere, hellere Welle zuerst, dann die vordere
        back = self._layer_polys(self._surface(ix1, ix2, iy1, iy2, 1), ix1, ix2, cy, ir)
        if len(back[0]) >= 2:
            pts = [v for p in back[0] for v in p] + [v for p in reversed(back[1]) for v in p]
            c.create_polygon(pts, fill=back_col, outline=back_col)
        top, bottom, hi = self._layer_polys(self._surface(ix1, ix2, iy1, iy2, 0), ix1, ix2, cy, ir)
        if len(top) >= 2:
            pts = [v for p in top for v in p] + [v for p in reversed(bottom) for v in p]
            c.create_polygon(pts, fill=liq, outline=liq)
            if len(hi) >= 2:
                c.create_line([v for p in hi for v in p], fill=hi_col, width=max(1, round(1.5 * k)), smooth=True)
        # Spritzer starten an der Oberfläche
        if self.pending_drop and top:
            self.pending_drop = False
            px, py = random.choice(top)
            self.drops.append({"x": px, "y": py - k, "vx": random.uniform(-45, 45) * k,
                               "vy": -random.uniform(90, 190) * k, "r": random.uniform(1.1, 2.2) * k,
                               "life": random.uniform(0.35, 0.7)})
        for dr in self.drops:
            lo, up = self._extent(dr["x"], ix1, ix2, cy, ir)
            if not (ix1 < dr["x"] < ix2) or dr["y"] < lo or dr["y"] > up:
                dr["life"] = 0
                continue
            ys = min(top, key=lambda s: abs(s[0] - dr["x"]))[1] if top else up
            if dr["vy"] > 0 and dr["y"] >= ys:  # zurück im Wasser: Tropfen verschwindet
                dr["life"] = 0
                continue
            rr = dr["r"]
            c.create_oval(dr["x"] - rr, dr["y"] - rr, dr["x"] + rr, dr["y"] + rr, fill=liq, outline=liq)


def _mix(a, b, f):
    """Farbe a nach b überblenden (f 0..1)."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(ca, cb))
