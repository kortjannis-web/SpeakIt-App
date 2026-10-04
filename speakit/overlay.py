"""Kleine Pille unten mittig: Pegel + Sekundenticker beim Sprechen, Status beim Verarbeiten."""
import collections
import ctypes
import tkinter as tk

KEY = "#ff00ff"  # transparente Farbe
BG = "#17171a"
OUTLINE = "#b4b9c2"  # dünne, hellgraue Kontur
RED, GREEN, AMBER, FG, MUTED = "#ef4444", "#22c55e", "#f59e0b", "#f4f4f5", "#9ca3af"
BASE_W, BASE_H = 156, 32
BARS = 12


def dpi_scale() -> float:
    try:
        return max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96)
    except Exception:
        return 1.0


def fmt_time(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


class Overlay:
    def __init__(self, root, recorder):
        self.rec = recorder
        self.k = dpi_scale()
        self.W, self.H = int(BASE_W * self.k), int(BASE_H * self.k)
        self.state, self.text = "idle", ""
        self.t = 0
        self.hide_at = 0
        self.levels = collections.deque([0.0] * BARS, maxlen=BARS)
        self.win = tk.Toplevel(root)
        w = self.win
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=KEY)
        w.attributes("-transparentcolor", KEY)
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{sh - int(92 * self.k)}")
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

    def set_state(self, state, text="", hold_ms=0):
        self.state, self.text = state, text
        if state == "idle":
            self.win.withdraw()
            return
        self.hide_at = self.t + hold_ms // 33 if hold_ms else 0
        if state == "rec":
            self.levels.extend([0.0] * BARS)
        self.win.deiconify()
        self.win.attributes("-topmost", True)

    def tick(self):
        self.t += 1
        if self.state == "idle":
            return
        if self.hide_at and self.t >= self.hide_at:
            self.set_state("idle")
            return
        self._draw()

    def _pill(self):
        """Volle Kapsel: Füllung aus zwei Halbkreisen + Rechteck, Kontur aus Bögen + Linien."""
        c, k = self.cv, self.k
        lw = max(1, round(k * 0.8))
        x1, y1, x2, y2 = 1, 1, self.W - 1, self.H - 1
        d = y2 - y1
        r = d / 2
        c.create_oval(x1, y1, x1 + d, y2, fill=BG, outline=BG)
        c.create_oval(x2 - d, y1, x2, y2, fill=BG, outline=BG)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=BG, outline=BG)
        c.create_arc(x1, y1, x1 + d, y2, start=90, extent=180, style="arc", outline=OUTLINE, width=lw)
        c.create_arc(x2 - d, y1, x2, y2, start=270, extent=180, style="arc", outline=OUTLINE, width=lw)
        c.create_line(x1 + r, y1, x2 - r, y1, fill=OUTLINE, width=lw)
        c.create_line(x1 + r, y2, x2 - r, y2, fill=OUTLINE, width=lw)

    def _draw(self):
        c, k, t = self.cv, self.k, self.t
        c.delete("all")
        self._pill()
        cy = self.H / 2
        if self.state == "rec":
            pulse = 0.65 + 0.35 * abs(((t % 36) / 18) - 1)
            r = 4.2 * k * pulse
            cx = 17 * k
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=RED, outline=RED)
            if t % 2 == 0:
                self.levels.append(self.rec.level)
            for i, v in enumerate(self.levels):
                h = (2.5 + v * 17) * k
                x = (32 + i * 6) * k
                c.create_rectangle(x, cy - h / 2, x + 3 * k, cy + h / 2, fill=FG, outline=FG)
            c.create_text(
                (32 + BARS * 6 + 6) * k, cy, text=fmt_time(self.rec.seconds), fill=FG, anchor="w",
                font=("Segoe UI Semibold", 9),
            )
        elif self.state == "busy":
            for i in range(3):
                a = (t // 6 + i) % 3
                r = (2.6 + (1.4 if a == 0 else 0)) * k
                x = (16 + i * 11) * k
                c.create_oval(x - r, cy - r, x + r, cy + r, fill=AMBER, outline=AMBER)
            c.create_text(54 * k, cy, text=self.text or "Transkribiere", fill=MUTED, anchor="w",
                          font=("Segoe UI", 9))
        else:
            col = GREEN if self.state == "done" else RED
            r = 4 * k
            cx = 17 * k
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline=col)
            c.create_text(30 * k, cy, text=self.text[:24], fill=FG, anchor="w", font=("Segoe UI", 9))
