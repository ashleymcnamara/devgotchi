"""one-off: cut the kit art into the small PNGs the renderer embeds.

needs Pillow + numpy (dev only, the bot never runs this):
    python scripts/build_art.py ~/Desktop/devogachi-readme-pixel-kit
art/pixel.ttf is Silkscreen Bold (SIL Open Font License, see art/OFL.txt).
"""
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

KIT = Path(sys.argv[1]).expanduser()
OUT = Path(__file__).resolve().parent.parent / "art"
CROP = (118, 0, 1138, 1242)  # egg bounds in mockup pixels; devgotchi.py uses the same box
ROW1, ROW2, COL1, COL2 = 870, 1098, 511, 745  # README slices; all divisible into whole pixels at 1/3 scale
COLS = {"baby": (206, 410), "toddler": (419, 627), "child": (637, 846), "teen": (856, 1072),
        "adult": (1082, 1307), "elder": (1316, 1522)}
ROWS = {"idle": (288, 361), "happy": (446, 511), "sad": (519, 583), "code": (591, 663),
        "eat": (670, 735), "nap": (742, 821)}


# Octicons mark-github (16px, MIT, github.com/primer/octicons) snapped to its own 16x16 grid
MARK = [
    ".....######.....",
    "...##########...",
    "..############..",
    ".###.######.###.",
    ".###........###.",
    "####........####",
    "###..........###",
    "###..........###",
    "###..........###",
    "####........####",
    "#####......#####",
    ".##.##....#####.",
    ".##.......#####.",
    "..##......####..",
    "...###....###...",
    "................",
]
INK, PAPER = (38, 37, 63), (255, 250, 253)


def mark():
    return np.array([[c == "#" for c in r] for r in MARK])


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


def stamp(a, cx, cy, cell, ink, border=None):
    m = mark()
    if border is not None:
        m = np.pad(m, 1)
        plate = grow(m)
    h = m.shape[0] * cell
    x0, y0 = cx - h // 2, cy - h // 2
    for j in range(m.shape[0]):
        for i in range(m.shape[1]):
            if m[j, i]:
                col = ink
            elif border is not None and plate[j, i]:
                col = border
            else:
                continue
            a[y0 + j * cell:y0 + (j + 1) * cell, x0 + i * cell:x0 + (i + 1) * cell] = col


def octicons(a):
    """swap the mockup's AI-drawn cat faces for the real GitHub mark"""
    sticker = lambda c: (c.sum(2) < 330) | (c.min(2) >= 225)
    heal(a, (545, 115, 712, 237), sticker)
    stamp(a, 627, 176, 7, INK, PAPER)
    heal(a, (945, 522, 1092, 664), sticker)
    stamp(a, 1016, 593, 7, INK, PAPER)
    heal(a, (798, 664, 838, 702), lambda c: c.sum(2) < 400)
    stamp(a, 818, 683, 2, INK)
    a[422:486, 358:424] = a[440, 365]
    stamp(a, 391, 454, 3, (255, 255, 255))
    return a


def mockup():
    return octicons(np.array(Image.open(KIT / "reference/approved-pixel-mockup.png").convert("RGB")).astype(int))


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
        save(im.resize((im.width * 2 // 3, im.height * 2 // 3), Image.LANCZOS), name, colors)

    part(CROP, "shell.png")
    part((x0, y0, x1, ROW1), "top.png")
    part((x0, ROW1, COL1, ROW2), "row-coffee.png", 96)
    part((COL1, ROW1, COL2, ROW2), "row-nap.png", 96)
    part((COL2, ROW1, x1, ROW2), "row-debug.png", 96)
    part((x0, ROW2, x1, y1), "bottom.png", 64)
    for n, box in {"coffee": (306, 876, 496, 1044), "nap": (528, 876, 726, 1044), "debug": (757, 876, 946, 1044)}.items():
        save(full.crop(box), f"btn-{n}.png", 64)


def keyed(a, box, name):
    x0, y0, x1, y1 = box
    c = a[y0:y1, x0:x1]
    bg = (c[..., 2] - c[..., 0] > 18) & (c[..., 0] > 120)
    save(Image.fromarray(np.dstack([c, np.where(bg, 0, 255)]).astype("uint8"), "RGBA"), name, 48)


def props():
    a = mockup()
    keyed(a, (358, 638, 500, 716), "cat.png")
    keyed(a, (785, 560, 880, 716), "mug.png")
    c = a[422:486, 358:424]
    save(Image.fromarray(c.astype("uint8")).convert("RGBA"), "octo.png", 16)


def comps(mask, gap=4):
    """connected blobs after a small dilation, so sparkles and Zs stay with their frame."""
    h, w = mask.shape
    d = mask.copy()
    for _ in range(gap):
        d = d | np.roll(d, 1, 0) | np.roll(d, -1, 0) | np.roll(d, 1, 1) | np.roll(d, -1, 1)
    lab = np.zeros((h, w), int)
    n, out = 0, []
    for y in range(h):
        for x in range(w):
            if d[y, x] and not lab[y, x]:
                n += 1
                q, pts = deque([(y, x)]), []
                lab[y, x] = n
                while q:
                    cy, cx = q.popleft()
                    pts.append((cy, cx))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < h and 0 <= nx < w and d[ny, nx] and not lab[ny, nx]:
                                lab[ny, nx] = n
                                q.append((ny, nx))
                ys, xs = [p[0] for p in pts], [p[1] for p in pts]
                out.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, (lab == n) & mask))
    return out


def fg(crop):
    """flood the cell background in from the edges; everything else is sprite."""
    edge = np.concatenate([crop[0], crop[-1], crop[:, 0], crop[:, -1]])
    dist = np.abs(crop - np.median(edge, 0)).sum(-1)
    h, w = dist.shape
    bg = np.zeros((h, w), bool)
    q = deque([(0, x) for x in range(w)] + [(h - 1, x) for x in range(w)] + [(y, 0) for y in range(h)] + [(y, w - 1) for y in range(h)])
    while q:
        y, x = q.popleft()
        if bg[y, x] or dist[y, x] > 38:
            continue
        bg[y, x] = True
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not bg[ny, nx]:
                q.append((ny, nx))
    return ~bg


def frames():
    s = np.array(Image.open(KIT / "reference/original-girl-sprite-sheet.png").convert("RGB")).astype(int)
    meta = {}
    (OUT / "girl").mkdir(exist_ok=True)
    for st, (x0, x1) in COLS.items():
        for an, (y0, y1) in ROWS.items():
            crop = s[y0:y1, x0:x1]
            fr = []
            for bx0, by0, bx1, by1, m in sorted(comps(fg(crop)), key=lambda c: c[0]):
                if m.sum() < 500:
                    continue
                rgba = np.dstack([crop.astype("uint8"), (m * 255).astype("uint8")])[by0:by1, bx0:bx1]
                save(Image.fromarray(rgba), f"girl/{st}-{an}-{len(fr)}.png", 64)
                fr.append([int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)])
            meta[f"{st}-{an}"] = fr
    (OUT / "girl/meta.json").write_text(json.dumps(meta) + "\n")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    shell()
    props()
    frames()
    print(sorted(p.name for p in OUT.iterdir()), sum(p.stat().st_size for p in OUT.rglob("*.png")) // 1024, "KB")
