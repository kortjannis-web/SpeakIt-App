"""Erzeugt icon.ico (Mikrofon auf dunklem Kreis)."""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((8, 8, S - 8, S - 8), fill="#1D1C1A")
d.rounded_rectangle((96, 48, 160, 144), radius=32, fill="white")
d.arc((72, 88, 184, 184), 0, 180, fill="white", width=12)
d.line((128, 184, 128, 216), fill="white", width=12)
d.line((96, 216, 160, 216), fill="white", width=12)
img.save("icon.ico", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icon.ico erstellt")
