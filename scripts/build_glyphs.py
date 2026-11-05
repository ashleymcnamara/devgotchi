"""bake art/pixel.ttf into art/glyphs.json so the screens draw text as pixels instead of embedding the font.

usage: python3 scripts/build_glyphs.py   (needs Pillow; the bot only reads the json)
"""
import json, string
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ART = Path(__file__).resolve().parent.parent / "art"
NATIVE = 8  # pixel.ttf draws one clean pixel per unit at this size
CHARS = string.ascii_letters + string.digits + " .,!?+-/:'#%()<>=*_~"

font = ImageFont.truetype(str(ART / "pixel.ttf"), NATIVE)
out = {"size": NATIVE, "glyphs": {}}
for ch in CHARS:
    im = Image.new("1", (NATIVE * 3, NATIVE * 3), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    ox, base = NATIVE, NATIVE * 2
    d.text((ox, base), ch, font=font, fill=1, anchor="ls")
    a = im.load()
    runs = []
    for y in range(im.height):
        x = 0
        while x < im.width:
            if a[x, y]:
                x0 = x
                while x < im.width and a[x, y]:
                    x += 1
                runs.append([x0 - ox, y - base, x - x0])
            x += 1
    out["glyphs"][ch] = {"adv": round(font.getlength(ch)), "runs": runs}
(ART / "glyphs.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
print(len(out["glyphs"]), "glyphs")
