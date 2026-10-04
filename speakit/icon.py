"""App-Symbol: ein einfacher oranger Tropfen mit weißem Mikrofon (Kapsel, Halbkreis, Strich)."""
import math

from PIL import Image, ImageDraw

ORANGE = "#f59e0b"


def drop_icon(size=256, color=ORANGE, mic="#ffffff") -> Image.Image:
    s = size * 4  # vierfach zeichnen und herunterrechnen, damit die Kanten glatt sind
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, r = s / 2, s * 0.325
    cy = s * 0.625
    tip = (cx, s * 0.045)
    ang = math.acos(r / (cy - tip[1]))  # Tangentenpunkte der Spitze am Kreis
    px, py = r * math.sin(ang), r * math.cos(ang)
    d.polygon([tip, (cx - px, cy - py), (cx + px, cy - py)], fill=color)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    # Mikrofon: Kapsel oben, Halbkreis darunter, Strich nach unten
    w = r * 0.23
    d.rounded_rectangle((cx - w, cy - r * 0.62, cx + w, cy + r * 0.06), radius=w, fill=mic)
    lw = max(2, int(r * 0.10))
    d.arc((cx - r * 0.46, cy - r * 0.40, cx + r * 0.46, cy + r * 0.40), start=0, end=180, fill=mic, width=lw)
    d.line((cx, cy + r * 0.40, cx, cy + r * 0.64), fill=mic, width=lw)
    d.ellipse((cx - lw / 2, cy + r * 0.64 - lw / 2, cx + lw / 2, cy + r * 0.64 + lw / 2), fill=mic)
    return img.resize((size, size), Image.LANCZOS)


def save_ico(path, color=ORANGE):
    drop_icon(256, color).save(path, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
