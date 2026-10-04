"""LiquidButton: Button, in den beim Berühren oder Auswählen orange Flüssigkeit einfließt und
beim Verlassen wieder abfließt.

Die Welle wird nicht live berechnet: Pro Buttongröße entsteht einmal ein Satz vorgerenderter Wellenbilder
(nahtlose Schleife, darunter durchgehend Orange). Zum Füllen wird dieses Bild nur höher geschoben und mit der
Buttonform maskiert; fertig zusammengesetzte Bilder werden zwischengespeichert. Beim Abspielen wechseln nur noch
fertige Bilder."""
import math
import time
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageChops, ImageDraw, ImageTk

from .overlay import dpi_scale

ORANGE, ORANGE_BACK, HIGHLIGHT = "#f59e0b", "#fbbf24", "#fde68a"
FRAMES = 16  # Bilder der Wellenschleife
STEPS = 48  # Füllstufen für den Zwischenspeicher
SS = 3  # Überabtastung für glatte Kanten
FLOW_FPS = 10  # Wellenschleife im Ruhezustand (ausgewählt oder Hover)

_sprites = {}


class Sprite:
    """Vorgerenderte Wellenschleife und Maske für eine Buttongröße."""

    def __init__(self, w, h, r, k):
        self.w, self.h = w, h
        self.amp = max(2.0, 2.6 * k)
        self.pad = int(self.amp * 2 + 3)  # Platz über der Grundlinie der Welle
        self.margin = int(self.amp + self.pad + 2)
        mask = Image.new("L", (w * SS, h * SS), 0)
        ImageDraw.Draw(mask).rounded_rectangle((1 * SS, 1 * SS, (w - 1) * SS - 1, (h - 1) * SS - 1),
                                               radius=r * SS, fill=255)
        self.mask = mask.resize((w, h), Image.LANCZOS)
        self.frames = [self._wave(i) for i in range(FRAMES)]
        self.cache = {}

    def _wave(self, i):
        w, k = self.w, self.amp
        fh = self.pad + self.h + 2 * self.margin + 4
        img = Image.new("RGBA", (w * SS, fh * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        ph = 2 * math.pi * i / FRAMES
        n = max(24, w // 4)

        def line(phase_off, scale, y_off, layer):
            pts = []
            for j in range(n + 1):
                fx = j / n
                if layer == 0:
                    v = math.sin(ph - fx * 7 + phase_off) + 0.6 * math.sin(2 * ph + fx * 11 + 1.3)
                else:
                    v = math.sin(-ph - fx * 5 + phase_off) + 0.5 * math.sin(2 * ph - fx * 9 + 2.6)
                pts.append((fx * w * SS, (self.pad + y_off - v * k * scale / 1.6) * SS))
            return pts

        for layer, col, off in ((1, ORANGE_BACK, -1.4), (0, ORANGE, 0.0)):
            top = line(1.9 if layer else 0.0, 1.0, off, layer)
            d.polygon(top + [(w * SS, fh * SS), (0, fh * SS)], fill=col)
            if layer == 0:
                d.line(top, fill=HIGHLIGHT, width=max(1, int(1.1 * SS)), joint="curve")
        return img.resize((w, fh), Image.LANCZOS)

    def image(self, level, frame):
        """Fertig maskiertes Bild für Füllstand und Wellenphase (zwischengespeichert)."""
        q = max(0, min(STEPS, round(level * STEPS)))
        key = (q, frame % FRAMES)
        im = self.cache.get(key)
        if im is None:
            if len(self.cache) > 600:
                self.cache.clear()
            lv = q / STEPS
            base = self.h * (1 - lv)  # Mitte exakt, nur an den Enden extra Weg, damit leer und voll sauber sind
            if lv < 0.08:
                base += self.margin * (1 - lv / 0.08)
            elif lv > 0.92:
                base -= self.margin * ((lv - 0.92) / 0.08)
            top = int(round(base - self.pad))
            canvas = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
            fr = self.frames[frame % FRAMES]
            if top < 0:
                canvas.alpha_composite(fr, (0, 0), (0, -top))
            elif top < self.h:
                canvas.alpha_composite(fr, (0, top))
            canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), self.mask))
            im = ImageTk.PhotoImage(canvas)
            self.cache[key] = im
        return im


def get_sprite(w, h, r, k):
    key = (w, h, r, k)
    sp = _sprites.get(key)
    if sp is None:
        if len(_sprites) > 24:
            _sprites.clear()
        sp = _sprites[key] = Sprite(w, h, r, k)
    return sp


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
        self.lv, self.lvv, self.target = 0.0, 0.0, 0.0
        self.frame = 0
        self._phase_t = 0.0
        self._last = time.monotonic()
        self._job = None
        self._size = None
        self._sprite = None
        self._items = None
        self._var = textvariable
        if textvariable is not None:
            self.text = textvariable.get()
            textvariable.trace_add("write", lambda *_: self._set_text(textvariable.get()))
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>", self._configure_event)
        self.bind("<Destroy>", self._destroy)
        self._build()

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
        if self._items:
            self.itemconfigure(self._items["text"], text=text)

    def set_selected(self, on: bool):
        if on != self.selected:
            self.selected = on
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
        self._retarget()

    def _leave(self, e):
        self.hovering = False
        self._retarget()

    def _press(self, e):
        self.lvv += 4.5  # beim Drücken schwappt es kurz höher und federt zurück
        if self._job is not None:  # Ruhe-Takt abbrechen, damit es sofort reagiert
            self.after_cancel(self._job)
            self._job = None
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

    # ---------------------------------------------------------------- Aufbau
    def _dims(self):
        w = self.winfo_width() if self.winfo_width() > 1 else self.req_w
        h = self.winfo_height() if self.winfo_height() > 1 else self.req_h
        return max(w, 4), max(h, 4)

    @staticmethod
    def _rr(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
                x1, y2 - r, x1, y1 + r, x1, y1]

    def _build(self):
        """Statische Teile einmal anlegen: Grundfläche, Füllbild, Rand, Text."""
        self.delete("all")
        w, h = self._size = self._dims()
        self._sprite = None
        r = min(self.radius * self.k, h / 2)
        pts = self._rr(1, 1, w - 1, h - 1, r)
        base = self.fill or self.bg_color
        self.create_polygon(pts, smooth=True, fill=base, outline=base)
        img = self.create_image(0, 0, anchor="nw", state="hidden")
        if self.border:
            self.create_polygon(pts, smooth=True, fill="", outline=self.border)
        if self.anchor_mode == "w":
            txt = self.create_text(self.padx * self.k, h / 2, text=self.text, fill=self.fg, anchor="w",
                                   font=self.font)
        else:
            txt = self.create_text(w / 2, h / 2, text=self.text, fill=self.fg, font=self.font)
        self._items = {"img": img, "text": txt}
        self._render()

    def _configure_event(self, e):
        if self._size != self._dims():
            self._build()

    def _get_sprite(self):
        if self._sprite is None:
            w, h = self._size
            self._sprite = get_sprite(w, h, int(min(self.radius * self.k, h / 2)), self.k)
            self._warm(0)
        return self._sprite

    def _warm(self, i):
        """Ruhe-Schleifen (Hover und Auswahl) im Leerlauf vorab fertig rendern, ein paar Bilder pro Durchgang."""
        sp = self._sprite
        if sp is None or i >= 2 * FRAMES:
            return
        for j in range(i, min(i + 4, 2 * FRAMES)):
            sp.image(self.hover_level if j < FRAMES else self.selected_level, j % FRAMES)
        self.after(15, lambda: self._warm(i + 4))

    # ---------------------------------------------------------------- Animation
    def _step(self):
        self._job = None
        now = time.monotonic()
        dt = min(0.05, now - self._last)
        self._last = now
        n = max(1, round(dt / 0.008))  # kleine Teilschritte, damit die Feder weich bleibt
        for _ in range(n):
            a = 480 * (self.target - self.lv) - 26 * self.lvv  # leicht federnd, ein wenig Überschwingen
            self.lvv += a * dt / n
            self.lv = max(0.0, min(1.0, self.lv + self.lvv * dt / n))
        moving = abs(self.target - self.lv) > 0.003 or abs(self.lvv) > 0.02
        if not moving:
            self.lv, self.lvv = self.target, 0.0
        # Wellenschleife: schnell beim Füllen, im Ruhezustand langsam
        self._phase_t += dt * (22 if moving else FLOW_FPS)
        self.frame = int(self._phase_t) % FRAMES
        self._render()
        if moving or self.target > 0:
            self._job = self.after(33 if moving else int(1000 / FLOW_FPS), self._step)

    def _render(self):
        it = self._items
        if not it:
            return
        if self.lv < 0.012:
            self.itemconfigure(it["img"], state="hidden")
        else:
            im = self._get_sprite().image(self.lv, self.frame)
            self.itemconfigure(it["img"], image=im, state="normal")
        col = self.fg_active if self.lv > 0.4 else self.fg
        self.itemconfigure(it["text"], fill=col)


def text_width(text, font=("Segoe UI", 13)) -> int:
    """Breite in Basis-Pixeln (ohne DPI-Faktor) für Buttons, die sich nach dem Text richten."""
    try:
        k = dpi_scale()
        f = tkfont.Font(family=font[0], size=-max(8, round(font[1] * k)))
        return int(f.measure(text) / k)
    except Exception:
        return len(text) * 8
