"""LiquidButton: Button, in den beim Berühren oder Auswählen orange Flüssigkeit einfließt und
beim Verlassen sofort wieder abfließt. Leichte Wasser-Physik (Schwappen, zwei Wellenschichten)."""
import math
import random
import time
import tkinter as tk
import tkinter.font as tkfont

from .overlay import dpi_scale

ORANGE, ORANGE_BACK, HIGHLIGHT = "#f59e0b", "#fbbf24", "#fde68a"


class LiquidButton(tk.Canvas):
    def __init__(self, parent, text="", command=None, width=110, height=36, bg="#FFFFFF", fill=None, border=None,
                 fg="#1D1C1A", fg_active="#1D1C1A", font=("Segoe UI", 13), radius=12, hover=0.5,
                 selected_level=0.75, anchor="center", padx=14, textvariable=None):
        self.k = dpi_scale()
        k = self.k
        super().__init__(parent, width=int(width * k), height=int(height * k), bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.req_w, self.req_h = int(width * k), int(height * k)
        self.text, self.command = text, command
        self.fill, self.border, self.fg, self.fg_active = fill, border, fg, fg_active
        self.bg_color = bg
        self.font = (font[0], -max(8, round(font[1] * k)))  # Pixelgröße, passend zur Skalierung
        self.radius, self.hover_level, self.selected_level = radius, hover, selected_level
        self.anchor_mode, self.padx = anchor, padx
        self.selected = False
        self.hovering = False
        self.lv, self.target = 0.0, 0.0
        self.act = 0.0  # Unruhe der Oberfläche
        self.tilt, self.tilt_v = 0.0, 0.0  # Schwappen
        self.t = random.random() * 10
        self._last = time.monotonic()
        self._job = None
        self._var = textvariable
        if textvariable is not None:
            self.text = textvariable.get()
            textvariable.trace_add("write", lambda *_: self._set_text(textvariable.get()))
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Destroy>", self._destroy)
        self._draw()

    # ---------------------------------------------------------------- Steuerung
    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self._set_text(kw.pop("text"))
        if "command" in kw:
            self.command = kw.pop("command")
        if cnf or kw:
            super().configure(cnf, **kw)

    config = configure

    def _set_text(self, text):
        self.text = text
        self._draw()

    def set_selected(self, on: bool):
        if on != self.selected:
            self.selected = on
            self.act = max(self.act, 0.9)
            self.tilt_v += random.choice((-1, 1)) * 110
            self._retarget()

    def _retarget(self):
        t = 0.0
        if self.hovering:
            t = self.hover_level
        if self.selected:
            t = max(t, self.selected_level)
        self.target = t
        self._kick()

    def _enter(self, e):
        self.hovering = True
        self.act = max(self.act, 0.8)
        self.tilt_v += (e.x / max(1, self.winfo_width()) - 0.5) * 2 * 120
        self._retarget()

    def _leave(self, e):
        self.hovering = False
        self.act = max(self.act, 0.8)
        self.tilt_v -= (e.x / max(1, self.winfo_width()) - 0.5) * 2 * 90
        self._retarget()

    def _press(self, e):
        self.act = 1.0
        self.tilt_v += random.choice((-1, 1)) * 140
        self._kick()

    def _release(self, e):
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if inside and self.command:
            self.command()

    def invoke(self):
        if self.command:
            self.command()

    def _destroy(self, e):
        if e.widget is self and self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _kick(self):
        if self._job is None:
            self._last = time.monotonic()
            self._job = self.after(33, self._step)

    # ---------------------------------------------------------------- Animation
    def _step(self):
        self._job = None
        now = time.monotonic()
        dt = min(0.08, now - self._last)
        self._last = now
        self.t += dt * 0.8
        self.lv += (self.target - self.lv) * (1 - math.exp(-dt * 8.0))
        speed = abs(self.target - self.lv)
        self.act = max(self.act * math.exp(-dt * 3.5), min(1.0, speed * 1.6))
        self.tilt_v += (-55 * self.tilt - 3.0 * self.tilt_v) * dt
        self.tilt = max(-9.0, min(9.0, self.tilt + self.tilt_v * dt))
        if abs(self.lv) < 0.004 and self.target == 0.0:
            self.lv = 0.0
        self._draw()
        if self.lv > 0.01 or speed > 0.003 or self.act > 0.06 or abs(self.tilt) > 0.15:
            self._job = self.after(33, self._step)

    # ---------------------------------------------------------------- Zeichnen
    @staticmethod
    def _rr(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
                x1, y2 - r, x1, y1 + r, x1, y1]

    @staticmethod
    def _extent(x, x1, x2, y1, y2, r):
        """Senkrechter Bereich der abgerundeten Form an der Stelle x."""
        if x < x1 + r:
            dx = (x1 + r) - x
        elif x > x2 - r:
            dx = x - (x2 - r)
        else:
            return y1, y2
        dy = r - math.sqrt(max(0.0, r * r - dx * dx))
        return y1 + dy, y2 - dy

    def _surface(self, x1, x2, y1, y2, layer):
        k = self.k
        h = y2 - y1
        level = y2 - self.lv * (h + 3 * k) - (1.2 * k if layer else 0.0)
        amp = (0.8 + 3.0 * self.act) * k * min(1.0, (1 - self.lv) * 5 + 0.3)
        n = max(8, min(22, int((x2 - x1) / (10 * k))))
        pts = []
        for i in range(n):
            fx = i / (n - 1)
            if layer == 0:
                w = math.sin(self.t * 5.0 + fx * 7) + 0.6 * math.sin(self.t * 8.3 - fx * 11 + 1.3)
                tl = self.tilt * (fx - 0.5)
            else:
                w = math.sin(self.t * 3.6 - fx * 5 + 1.9) + 0.5 * math.sin(self.t * 6.1 + fx * 9 + 2.6)
                tl = self.tilt * (0.5 - fx) * 0.7
            pts.append((x1 + (x2 - x1) * fx, level - (w * amp + tl * k)))
        return pts

    def _layer(self, cols, x1, x2, y1, y2, r):
        xs = [c[0] for c in cols]
        for j in range(1, 5):
            off = r * (1 - math.cos(j / 5 * math.pi / 2))
            xs += [x1 + off, x2 - off]
        xs = sorted(set(xs))

        def ys(x):
            for a, b in zip(cols, cols[1:]):
                if a[0] <= x <= b[0]:
                    f = (x - a[0]) / max(1e-9, b[0] - a[0])
                    return a[1] + (b[1] - a[1]) * f
            return cols[0][1] if x < cols[0][0] else cols[-1][1]

        top, bottom, hi = [], [], []
        for x in xs:
            lo, up = self._extent(x, x1, x2, y1, y2, r)
            yt = max(ys(x), lo)
            if yt >= up:
                continue
            top.append((x, yt))
            bottom.append((x, up))
            if yt > lo + 0.4:
                hi.append((x, yt))
        return top, bottom, hi

    def _draw(self):
        c, k = self, self.k
        c.delete("all")
        w = max(self.winfo_width(), 2) if self.winfo_width() > 1 else self.req_w
        h = max(self.winfo_height(), 2) if self.winfo_height() > 1 else self.req_h
        r = min(self.radius * k, h / 2)
        x1, y1, x2, y2 = 1, 1, w - 1, h - 1
        base = self.fill or self.bg_color
        pts = self._rr(x1, y1, x2, y2, r)
        c.create_polygon(pts, smooth=True, fill=base, outline=base)
        if self.lv > 0.005:
            ir = max(2.0, r - 0.5)
            back = self._layer(self._surface(x1, x2, y1, y2, 1), x1, x2, y1, y2, ir)
            if len(back[0]) >= 2:
                c.create_polygon([v for p in back[0] for v in p] + [v for p in reversed(back[1]) for v in p],
                                 fill=ORANGE_BACK, outline=ORANGE_BACK)
            top, bottom, hi = self._layer(self._surface(x1, x2, y1, y2, 0), x1, x2, y1, y2, ir)
            if len(top) >= 2:
                c.create_polygon([v for p in top for v in p] + [v for p in reversed(bottom) for v in p],
                                 fill=ORANGE, outline=ORANGE)
                if len(hi) >= 2 and self.lv < 0.98:
                    c.create_line([v for p in hi for v in p], fill=HIGHLIGHT, width=max(1, round(1.2 * k)),
                                  smooth=True)
        if self.border:
            c.create_polygon(pts, smooth=True, fill="", outline=self.border)
        col = self.fg_active if self.lv > 0.4 else self.fg
        if self.anchor_mode == "w":
            c.create_text(self.padx * k, h / 2, text=self.text, fill=col, anchor="w", font=self.font)
        else:
            c.create_text(w / 2, h / 2, text=self.text, fill=col, font=self.font)


def text_width(text, font=("Segoe UI", 13)) -> int:
    """Breite in Basis-Pixeln (ohne DPI-Faktor) für Buttons, die sich nach dem Text richten."""
    try:
        k = dpi_scale()
        f = tkfont.Font(family=font[0], size=-max(8, round(font[1] * k)))
        return int(f.measure(text) / k)
    except Exception:
        return len(text) * 8
