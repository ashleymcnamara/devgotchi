"""one-off: cut the kit art into the small PNGs the renderer embeds.

needs Pillow + numpy (dev only, the bot never runs this):
    python scripts/build_art.py ~/Desktop/devogachi-readme-pixel-kit
art/pixel.ttf is Silkscreen Bold (SIL Open Font License, see art/OFL.txt).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

KIT = Path(sys.argv[1]).expanduser()
OUT = Path(__file__).resolve().parent.parent / "art"
CROP = (118, 0, 1138, 1242)  # egg bounds in mockup pixels; devgotchi.py uses the same box
ROW1, ROW2, COL1, COL2 = 870, 1098, 511, 745  # README slices; all divisible into whole pixels at 1/3 scale


INK, PAPER = (38, 37, 63), (255, 250, 253)
# chunky lowercase for the label plate: rows 0-2 ascender, 3-7 x-height, 8-9 descender
LOWER = {
    "d": ["...##", "...##", "...##", ".####", "##.##", "##.##", "##.##", ".####"],
    "e": [".....", ".....", ".....", ".###.", "##.##", "#####", "##...", ".####"],
    "v": [".....", ".....", ".....", "##.##", "##.##", "##.##", ".###.", "..#.."],
    "g": [".....", ".....", ".....", ".####", "##.##", "##.##", "##.##", ".####", "...##", "####."],
    "o": [".....", ".....", ".....", ".###.", "##.##", "##.##", "##.##", ".###."],
    "t": ["....", ".##.", ".##.", "####", ".##.", ".##.", ".##.", "..##"],
    "c": [".....", ".....", ".....", ".####", "##...", "##...", "##...", ".####"],
    "h": ["##...", "##...", "##...", "####.", "##.##", "##.##", "##.##", "##.##"],
    "i": ["..", "##", "..", "##", "##", "##", "##", "##"],
}
# stickers: fill colours by letter; the ink outline and white sticker edge are grown around them
STICKER_PAL = {"c": (255, 92, 138), "C": (214, 51, 108), "w": (255, 255, 255), "y": (255, 212, 71),
               "Y": (232, 160, 32), "o": (247, 120, 40), "k": INK}
HEART = [".cc...cc.",
         "cwcc.cccc",
         "cwcccccCc",
         "ccccccCCc",
         ".cccccCc.",
         "..cccCc..",
         "...cCc...",
         "....c...."]
DUCK = [".....yyy.....",
        "....yyyyy....",
        "....yykyyoo..",
        "....yyyyyooo.",
        ".....yyyy....",
        "y...yyyyyy...",
        "yy.yyyyyyyy..",
        "yyyyyyYYYyyy.",
        "yyyyyYYYyyyy.",
        ".yyyyyyyyyY..",
        "..YYYYYYYY..."]


def grow(m, n=1):
    for _ in range(n):
        g = m.copy()
        g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
        m = g
    return m


def heal(a, box, icon):
    """paint over the old icon by interpolating each row between the untouched pixels either side"""
    x0, y0, x1, y1 = box
    c = a[y0:y1, x0:x1]
    m = grow(icon(c), 3)
    xs = np.arange(c.shape[1])
    for j in range(c.shape[0]):
        k = ~m[j]
        if m[j].any() and k.sum() >= 2:
            for ch in range(3):
                c[j, m[j], ch] = np.interp(xs[m[j]], xs[k], c[j, k, ch])


def sticker(a, rows, cx, cy, cell):
    """a die-cut sticker: the art, a 1-cell ink outline, then a 1-cell white edge"""
    fill = np.pad(np.array([[ch != "." for ch in r] for r in rows]), 2)
    line, edge = grow(fill), grow(fill, 2)
    h, w = fill.shape
    x0, y0 = cx - w * cell // 2, cy - h * cell // 2
    for j in range(h):
        for i in range(w):
            if fill[j, i]:
                col = STICKER_PAL[rows[j - 2][i - 2]]
            elif line[j, i]:
                col = INK
            elif edge[j, i]:
                col = PAPER
            else:
                continue
            a[y0 + j * cell:y0 + (j + 1) * cell, x0 + i * cell:x0 + (i + 1) * cell] = col


def title(a, word="devgotchi", cell=7, box=(452, 256, 812, 337), top=263):
    """wipe the mockup's lettering off the cream plate and set the name in chunky pixels"""
    x0, y0, x1, y1 = box
    c = a[y0:y1, x0:x1]
    ink = grow(c.sum(2) < 400, 2)
    for j in range(c.shape[0]):
        cream = np.median(c[j][~ink[j]], 0) if (~ink[j]).any() else c[j - 1].mean(0)
        c[j, ink[j]] = cream
    w = sum(len(LOWER[ch][0]) for ch in word) + len(word) - 1
    x = (x0 + x1) // 2 - w * cell // 2
    for ch in word:
        g = LOWER[ch]
        for j, row in enumerate(g):
            for i, v in enumerate(row):
                if v == "#":
                    a[top + j * cell:top + (j + 1) * cell, x + i * cell:x + (i + 1) * cell] = INK
        x += (len(g[0]) + 1) * cell


def decorate(a):
    """swap the mockup's two cat-face stickers for a heart and a debugging duck, and retitle the plate"""
    dark_or_white = lambda c: (c.sum(2) < 330) | (c.min(2) >= 225)
    a[230:258, 575:690] = a[230:258, 568:569]  # the top sticker overlapped the plate's straight top edge
    heal(a, (545, 110, 712, 232), dark_or_white)
    heal(a, (945, 522, 1092, 664), dark_or_white)
    title(a)
    sticker(a, HEART, 627, 172, 8)
    sticker(a, DUCK, 1016, 593, 7)
    return a


def mockup():
    return decorate(np.array(Image.open(KIT / "reference/approved-pixel-mockup.png").convert("RGB")).astype(int))


def save(im, name, colors=96):
    im.quantize(colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(OUT / name, optimize=True)


def shell():
    a = mockup()
    h, w, _ = a.shape
    bg = a[5, 5]
    near = np.abs(a - bg).sum(2) < 40
    seen = np.zeros((h, w), bool)
    stack = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    while stack:  # flood the pink backdrop and the drop shadow away from the borders
        x, y = stack.pop()
        if 0 <= x < w and 0 <= y < h and not seen[y, x] and (near[y, x] or y > 1219):
            seen[y, x] = True
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    alpha = np.where(seen, 0, 255).astype("uint8")
    alpha[1220:] = 0
    full = Image.fromarray(np.dstack([a.astype("uint8"), alpha]), "RGBA")
    x0, y0, x1, y1 = CROP

    def part(box, name, colors=160):
        im = full.crop(box)
        save(im, name, colors)

    part(CROP, "shell.png")
    part((x0, y0, x1, ROW1), "top.png")
    part((x0, ROW1, COL1, ROW2), "row-coffee.png", 96)
    part((COL1, ROW1, COL2, ROW2), "row-nap.png", 96)
    part((COL2, ROW1, x1, ROW2), "row-debug.png", 96)
    part((x0, ROW2, x1, y1), "bottom.png", 64)
    for n, box in {"coffee": (306, 876, 496, 1044), "nap": (528, 876, 726, 1044), "debug": (757, 876, 946, 1044)}.items():
        save(full.crop(box), f"btn-{n}.png", 64)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    shell()
    print(sorted(p.name for p in OUT.iterdir()), sum(p.stat().st_size for p in OUT.rglob("*.png")) // 1024, "KB")
