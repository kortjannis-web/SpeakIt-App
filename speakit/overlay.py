"""Kleine Kapsel unten mittig.

Aufnahme: ruhiger roter Punkt, runde Pegelbalken, Sekundenticker.
Verarbeitung: orange Flüssigkeit fließt von rechts ein, schwappt (Wellen + Kipp-Feder), bildet Tropfen und
füllt die Kapsel als Fortschrittsanzeige. Ist sie voll, ist der Text fertig.
Die Kapsel fährt aus der Mitte auf und schrumpft zur Mitte wieder zu.
"""
import collections
import ctypes
import math
import random
import time
import tkinter as tk

KEY = "#ff00ff"  # transparente Farbe
BG = "#17171a"
OUTLINE = "#767c88"  # dünne graue Kontur
RED, GREEN, FG, MUTED = "#ef4444", "#22c55e", "#f4f4f5", "#9ca3af"
LIQUID, LIQUID_HI = "#f59e0b", "#fcd34d"
BASE_W, BASE_H = 138, 30  # Kapselgröße im Aufnahmemodus (Basis-Einheiten, werden mit DPI skaliert)
MAX_W = 300
BARS = 12
ROWS = 28  # Zeilen der Flüssigkeitsoberfläche


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
    return f"{sec // 60}:{sec % 60:02d}"


class Overlay:
    def __init__(self, root, recorder):
        self.rec = recorder
        self.k = dpi_scale()
        k = self.k
        self.W, self.H = int(MAX_W * k), int(BASE_H * k)
        self.mode = None  # None | rec | busy | finish | msg
        self.text, self.msg_col = "", GREEN
        self.e = 0.0  # Aufklapp-Grad 0..1
        self.target = 0.0
        self.cur_w = BASE_W * k
        self.want_w = BASE_W * k
        self.close_at = 0.0
        self.last = time.monotonic()
        self.levels = collections.deque([0.0] * BARS, maxlen=BARS)
        self.lvl_t = 0.0
        self.tau = 2.0
        self.busy_t = 0.0
        self._reset_liquid()

        self.win = tk.Toplevel(root)
        w = self.win
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=KEY)
        w.attributes("-transparentcolor", KEY)
        wa = work_area()
        if wa:
            x = (wa[0] + wa[2]) // 2 - self.W // 2
            y = wa[3] - self.H - int(6 * k)
        else:
            x = (w.winfo_screenwidth() - self.W) // 2
            y = w.winfo_screenheight() - self.H - int(60 * k)
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
    def _recording(self):
        return getattr(self.rec, "stream", None) is not None

    def _open(self, mode):
        self.mode = mode
        self.target = 1.0
        if not self.visible:
            self.e = 0.0
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.visible = True

    def set_state(self, state, text="", hold_ms=0):
        k = self.k
        if state == "idle":
            if not self._recording():
                self.mode, self.target = None, 0.0
            return
        if state == "rec":
            self.levels.extend([0.0] * BARS)
            self.want_w = BASE_W * k
            self._open("rec")
            return
        if self._recording():  # eine neue Aufnahme hat Vorrang
            return
        if state == "busy":
            if self.mode != "busy":
                self._reset_liquid()
                self.busy_t = 0.0
                self.want_w = BASE_W * k
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
        self.p = 0.0  # angezeigter Füllstand 0..1
        self.h = [0.0] * ROWS  # Auslenkung der Oberfläche pro Zeile
        self.v = [0.0] * ROWS
        self.slosh, self.slosh_v = 0.0, 0.0  # Verschiebung der ganzen Front
        self.tilt, self.tilt_v = 0.0, 0.0  # Kippen der Front
        self.drops = []
        self.kick_t = 0.0
        self.pending_drop = False

    def _physics(self, dt):
        k = self.k
        target = 1.0 if self.mode == "finish" else min(0.93, 1 - math.exp(-self.busy_t / self.tau))
        rate = 9.0 if self.mode == "finish" else 2.4
        dp = (target - self.p) * min(1.0, dt * rate)
        self.p += dp
        # Einströmen und Kicks regen die Oberfläche an
        self.kick_t -= dt
        if self.kick_t <= 0:
            self.kick_t = random.uniform(0.18, 0.5)
            self.v[random.randrange(ROWS)] += random.uniform(-260, 260)
            self.slosh_v += random.uniform(-48, 48) + dp * 1400
            self.tilt_v += random.uniform(-60, 60)
        n_sub = max(1, int(dt / 0.008))
        h = dt / n_sub
        for _ in range(n_sub):
            for i in range(ROWS):
                l = self.h[i - 1] if i > 0 else self.h[i]
                r = self.h[i + 1] if i < ROWS - 1 else self.h[i]
                a = 800 * (l + r - 2 * self.h[i]) - 5 * self.v[i] - 30 * self.h[i]
                self.v[i] += a * h
            for i in range(ROWS):
                self.h[i] += self.v[i] * h
            self.slosh_v += (-70 * self.slosh - 3.2 * self.slosh_v) * h
            self.slosh += self.slosh_v * h
            self.tilt_v += (-85 * self.tilt - 3.5 * self.tilt_v) * h
            self.tilt += self.tilt_v * h
        self.slosh = max(-14, min(14, self.slosh))
        self.tilt = max(-16, min(16, self.tilt))
        # Tropfen
        if self.mode == "busy" and self.p < 0.9 and random.random() < dt * 4.5:
            self.pending_drop = True
        for d in self.drops:
            d["vy"] += 300 * k * dt
            d["x"] += d["vx"] * dt
            d["y"] += d["vy"] * dt
            d["life"] -= dt
        self.drops = [d for d in self.drops if d["life"] > 0]

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
                    self.close_at = now + 0.18
                elif now >= self.close_at:
                    self.mode, self.target = None, 0.0
        if self.mode is None and self.target == 0.0 and self.e < 0.02:
            self.cv.delete("all")
            self.win.withdraw()
            self.visible = False
            return
        self._draw()

    def _geometry(self):
        k, e = self.k, self.e
        hd = self.H * (0.3 + 0.7 * min(1.0, e * 1.25))
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
        lw = max(1, round(k * 0.8))
        c.create_oval(x1, y1, x1 + d, y2, fill=BG, outline=BG)
        c.create_oval(x2 - d, y1, x2, y2, fill=BG, outline=BG)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=BG, outline=BG)
        if self.mode in ("busy", "finish"):
            self._draw_liquid(x1, y1, x2, y2)
        c.create_arc(x1, y1, x1 + d, y2, start=90, extent=180, style="arc", outline=OUTLINE, width=lw)
        c.create_arc(x2 - d, y1, x2, y2, start=270, extent=180, style="arc", outline=OUTLINE, width=lw)
        c.create_line(x1 + r, y1, x2 - r, y1, fill=OUTLINE, width=lw)
        c.create_line(x1 + r, y2, x2 - r, y2, fill=OUTLINE, width=lw)
        if self.e < 0.96:
            return
        cy = self.H / 2
        left = x1
        if self.mode == "rec":
            rr = 4 * k
            dx = left + 15 * k
            c.create_oval(dx - rr, cy - rr, dx + rr, cy + rr, fill=RED, outline=RED)
            self.lvl_t += 1
            if self.lvl_t % 2 == 0:
                self.levels.append(self.rec.level)
            for i, v in enumerate(self.levels):
                hh = (3 + v * 15) * k
                x = left + (29 + i * 5) * k
                c.create_line(x, cy - hh / 2, x, cy + hh / 2, fill=FG, width=max(2, round(2.4 * k)),
                              capstyle="round")
            c.create_text(left + (29 + BARS * 5 + 3) * k, cy, text=fmt_time(self.rec.seconds), fill=FG,
                          anchor="w", font=("Segoe UI Semibold", 9))
        elif self.mode == "msg":
            rr = 4 * k
            dx = left + 15 * k
            c.create_oval(dx - rr, cy - rr, dx + rr, cy + rr, fill=self.msg_col, outline=self.msg_col)
            c.create_text(left + 27 * k, cy, text=self.text, fill=FG, anchor="w", font=("Segoe UI", 9))

    def _draw_liquid(self, x1, y1, x2, y2):
        c, k = self.cv, self.k
        d = y2 - y1
        r = d / 2
        cy = (y1 + y2) / 2
        inset = 1.5 * k
        ix1, ix2 = x1 + inset, x2 - inset
        front = ix2 - (ix2 - ix1) * self.p
        if self.p < 0.004:
            front = ix2 + 1
        left_pts, right_pts, front_pts = [], [], []
        for i in range(ROWS):
            frac = i / (ROWS - 1)
            y = y1 + inset + (d - 2 * inset) * frac
            sp = self._span(y, ix1, ix2, cy, r - inset)
            if not sp:
                continue
            rip = (1.4 * math.sin(self.busy_t * 5.0 + i * 0.55) + 0.8 * math.sin(self.busy_t * 8.3 - i * 0.9)) * (1 - self.p * 0.6)
            fx = front + (self.h[i] + rip + self.slosh + self.tilt * (frac - 0.5)) * k
            lx = max(fx, sp[0])
            if lx >= sp[1]:
                continue
            left_pts.append((lx, y))
            right_pts.append((sp[1], y))
            front_pts.append((lx, y))
        if len(left_pts) >= 2:
            pts = [v for p in left_pts for v in p] + [v for p in reversed(right_pts) for v in p]
            c.create_polygon(pts, fill=LIQUID, outline=LIQUID)
            hi = [v for p in front_pts for v in p]
            c.create_line(hi, fill=LIQUID_HI, width=max(1, round(1.6 * k)), smooth=True)
        # Tropfen vor der Front
        if getattr(self, "pending_drop", False) and front_pts:
            self.pending_drop = False
            px, py = random.choice(front_pts)
            self.drops.append({"x": px - 1, "y": py, "vx": -random.uniform(35, 85) * k,
                               "vy": -random.uniform(5, 60) * k, "r": random.uniform(1.1, 2.3) * k,
                               "life": random.uniform(0.4, 0.8)})
        for dr in self.drops:
            sp = self._span(dr["y"], ix1, ix2, cy, r - inset)
            if not sp or not (sp[0] < dr["x"] < sp[1]):
                dr["life"] = 0
                continue
            rr = dr["r"]
            c.create_oval(dr["x"] - rr, dr["y"] - rr, dr["x"] + rr, dr["y"] + rr, fill=LIQUID, outline=LIQUID)
