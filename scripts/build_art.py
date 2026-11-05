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
ROW1, ROW2, COL1, COL2 = 870, 1098, 514, 748  # README slices, on the 6px grid
# Coffee/Nap/Debug in grid pixels from CROP's corner: x, y, w, h (devgotchi.py has the same)
BTNS = {"coffee": (31, 146, 32, 28), "nap": (68, 146, 33, 28), "debug": (107, 146, 31, 28)}
COLS = {"baby": (206, 410), "toddler": (419, 627), "child": (637, 846), "teen": (856, 1072),
        "adult": (1082, 1307), "elder": (1316, 1522)}
ROWS = {"idle": (288, 361), "happy": (446, 511), "sad": (519, 583), "code": (591, 663),
        "eat": (670, 735), "nap": (742, 821)}


# Everything lands on one grid: a "pixel" is 6 mockup px (2 css px in the README), stored 4x for retina.
U, X4 = 6, 4
# Octicons mark-github (MIT, github.com/primer/octicons), hand-snapped to 13x13 and a 7x7 for tiny spots
MARK = [
    "....#####....",
    "..#########..",
    ".###########.",
    ".##.#####.##.",
    "###.......###",
    "##.........##",
    "##.........##",
    "###.......###",
    "####.....####",
    ".#.##...####.",
    ".##.....####.",
    "..###...###..",
    "....#...#....",
]
MINI = [
    "..###..",
    ".#####.",
    "##.#.##",
    "#.....#",
    "##...##",
    ".##.##.",
    "..#.#..",
]
INK, PAPER = (38, 37, 63, 255), (255, 250, 253, 255)


def bits(rows):
    return np.array([[c == "#" for c in r] for r in rows])


def grow(m, n=1):
    for _ in range(n):
        g = m.copy()
        g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
        m = g
    return m


def heal(a, box, icon):
    """paint over an old icon by interpolating each row between the untouched pixels either side"""
    x0, y0, x1, y1 = box
    c = a[y0:y1, x0:x1]
    m = grow(icon(c), 3)
    xs = np.arange(c.shape[1])
    for j in range(c.shape[0]):
        k = ~m[j]
        if m[j].any() and k.sum() >= 2:
            for ch in range(3):
                c[j, m[j], ch] = np.interp(xs[m[j]], xs[k], c[j, k, ch])


def mockup():
    """the approved mockup with its AI-drawn cat-face logos painted out (real marks go back on after snapping)"""
    a = np.array(Image.open(KIT / "reference/approved-pixel-mockup.png").convert("RGB")).astype(int)
    sticker = lambda c: (c.sum(2) < 330) | (c.min(2) >= 225)
    heal(a, (545, 115, 712, 237), sticker)
    heal(a, (945, 522, 1092, 664), sticker)
    heal(a, (798, 664, 838, 702), lambda c: c.sum(2) < 400)
    return a


def snap(rgba, f, colors=64):
    """resample AI 'pixel art' onto a true grid: each f x f block becomes one pixel, by vote, outlines favoured"""
    rgba = rgba.astype("uint8")
    q = Image.fromarray(rgba[..., :3]).quantize(colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    idx = np.array(q)
    pal = np.array(q.getpalette()[:colors * 3]).reshape(-1, 3)
    weight = 1 + (pal.sum(1) < 260) * .7
    solid = rgba[..., 3] > 127
    H, W = idx.shape
    nh, nw = max(1, round(H / f)), max(1, round(W / f))
    out = np.zeros((nh, nw, 4), "uint8")
    for j in range(nh):
        y0, y1 = round(j * f), max(round(j * f) + 1, round((j + 1) * f))
        for i in range(nw):
            x0, x1 = round(i * f), max(round(i * f) + 1, round((i + 1) * f))
            m = solid[y0:y1, x0:x1]
            if m.size == 0 or m.mean() < .5:
                continue
            k = np.argmax(np.bincount(idx[y0:y1, x0:x1][m], minlength=len(pal)) * weight)
            out[j, i] = (*pal[k], 255)
    return out


def put(dst, src, x, y):
    m = src[..., 3] > 0
    dst[y:y + src.shape[0], x:x + src.shape[1]][m] = src[m]


def sticker(tilt=0):
    """the mark as a dark sticker with a white edge, same family as the </> and >_ stickers"""
    n = 17
    plate = np.ones((n, n), bool)
    for y, x in ((0, 0), (0, n - 1), (n - 1, 0), (n - 1, n - 1)):
        plate[y, x] = False
    plate = np.pad(plate, 2)
    white = grow(plate)
    out = np.zeros(plate.shape + (4,), "uint8")
    out[grow(white)] = INK
    out[white] = PAPER
    out[plate] = INK
    out[3:3 + 13, 3:3 + 13][bits(MARK)] = PAPER
    if tilt:  # rotate big then sample back down, so the pixels stay square
        big = Image.fromarray(out).resize((out.shape[1] * 8, out.shape[0] * 8), Image.NEAREST)
        big = np.array(big.rotate(tilt, Image.NEAREST, expand=True))
        out = big[4::8, 4::8]
    return out


GLYPH = {  # 3x5 letters for the button plates (the mockup's letters smear at this size)
    "C": ["###", "#..", "#..", "#..", "###"], "O": ["###", "#.#", "#.#", "#.#", "###"],
    "F": ["###", "#..", "##.", "#..", "#.."], "E": ["###", "#..", "##.", "#..", "###"],
    "N": ["#..#", "##.#", "#.##", "#..#", "#..#"], "A": [".#.", "#.#", "###", "#.#", "#.#"],
    "P": ["##.", "#.#", "##.", "#..", "#.."], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "B": ["##.", "#.#", "##.", "#.#", "##."], "U": ["#.#", "#.#", "#.#", "#.#", "###"],
    "G": ["###", "#..", "#.#", "#.#", "###"],
}
# the big label: chunky lowercase, rows 0-2 ascender, 3-7 x-height, 8-9 descender
TITLE = "devgotchi"
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
PLATES = {"COFFEE": (34, 60, 175), "NAP": (73, 96, 176), "DEBUG": (109, 134, 175)}  # x0, x1, top row of text area


def letter(n):
    x0, x1, y0 = 57, 112, 44  # inside of the label plate
    cream = np.median(n[48:52, 60:110][n[48:52, 60:110, :3].min(2) > 215], 0).astype("uint8")
    n[43:55, 53:117] = cream
    w = sum(len(LOWER[c][0]) + 1 for c in TITLE) - 1
    x = x0 + (x1 - x0 + 1 - w) // 2
    for c in TITLE:
        g = bits(LOWER[c])
        n[y0:y0 + g.shape[0], x:x + g.shape[1]][g] = INK
        x += g.shape[1] + 1
    for word, (x0, x1, y) in PLATES.items():
        plate = n[y + 2, x0 + 1].copy()
        n[y:y + 6, x0:x1 + 1] = plate
        w = sum(len(GLYPH[c][0]) + 1 for c in word) - 1
        x = x0 + (x1 - x0 + 1 - w) // 2
        for c in word:
            g = bits(GLYPH[c])
            n[y + 1:y + 6, x:x + g.shape[1]][g] = INK
            x += g.shape[1] + 1


def save(a, name, colors=128):
    im = Image.fromarray(a.astype("uint8"), "RGBA")
    im = im.resize((im.width * X4, im.height * X4), Image.NEAREST)
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
    alpha = np.where(seen, 0, 255)
    alpha[1220:] = 0
    x0, y0, x1, y1 = CROP
    n = snap(np.dstack([a, alpha])[y0:y1, x0:x1], U, 72)
    letter(n)
    put(n, sticker(), 75, 19)
    st = sticker(-10)
    put(n, st, 150 - st.shape[1] // 2, 99 - st.shape[0] // 2)
    r1, r2, c1, c2 = ROW1 // U, ROW2 // U, (COL1 - x0) // U, (COL2 - x0) // U
    save(n, "shell.png")
    save(n[:r1], "top.png")
    save(n[r1:r2, :c1], "row-coffee.png")
    save(n[r1:r2, c1:c2], "row-nap.png")
    save(n[r1:r2, c2:], "row-debug.png")
    save(n[r2:], "bottom.png")
    for name, (bx, by, bw, bh) in BTNS.items():
        save(n[by:by + bh, bx:bx + bw], f"btn-{name}.png")
    Image.fromarray(n).resize((n.shape[1] * 4, n.shape[0] * 4), Image.NEAREST).save("/tmp/snap-shell.png")


def keyed(a, box):
    x0, y0, x1, y1 = box
    c = a[y0:y1, x0:x1]
    bg = (c[..., 2] - c[..., 0] > 18) & (c[..., 0] > 120)
    return snap(np.dstack([c, np.where(bg, 0, 255)]), U, 32)


def props():
    a = mockup()
    save(keyed(a, (358, 638, 500, 716)), "cat.png")
    mug = keyed(a, (785, 560, 880, 716))
    mug[17:24, 2:9][bits(MINI)] = INK
    save(mug, "mug.png")


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


# how tall (in grid pixels) Byte stands at each stage: she still grows, but even the baby fills the screen
TALL = {"baby": 30, "toddler": 32, "child": 34, "teen": 35, "adult": 36, "elder": 36}


def split(blobs):
    """two frames drawn touching come out as one blob; cut it at its thinnest column near the middle"""
    if len(blobs) != 1 or blobs[0][2] - blobs[0][0] < 1.8 * (blobs[0][3] - blobs[0][1]):
        return blobs
    x0, y0, x1, y1, m = blobs[0]
    cols = m[y0:y1, x0:x1].sum(0)
    w = x1 - x0
    k = x0 + w // 3 + int(np.argmin(cols[w // 3:2 * w // 3]))
    out = []
    for a, b in ((x0, k), (k, x1)):
        mm = np.zeros_like(m)
        mm[:, a:b] = m[:, a:b]
        ys, xs = np.nonzero(mm)
        out.append((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, mm))
    return out


def frames():
    s = np.array(Image.open(KIT / "reference/original-girl-sprite-sheet.png").convert("RGB")).astype(int)
    meta = {}
    (OUT / "girl").mkdir(exist_ok=True)
    for p in (OUT / "girl").glob("*.png"):
        p.unlink()
    for st, (x0, x1) in COLS.items():
        cut = {}
        for an, (y0, y1) in ROWS.items():
            crop = s[y0:y1, x0:x1]
            cut[an] = (crop, split([c for c in sorted(comps(fg(crop)), key=lambda c: c[0]) if c[4].sum() >= 500]))
        f = max(by1 - by0 for _, by0, _, by1, _ in cut["idle"][1]) / TALL[st]
        for an, (crop, blobs) in cut.items():
            fr = []
            for bx0, by0, bx1, by1, m in blobs:
                px = snap(np.dstack([crop, m * 255])[by0:by1, bx0:bx1], f, 40)
                save(px, f"girl/{st}-{an}-{len(fr)}.png", 40)
                fr.append([round(by0 / f), px.shape[1], px.shape[0]])
            meta[f"{st}-{an}"] = fr
    (OUT / "girl/meta.json").write_text(json.dumps(meta) + "\n")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    shell()
    props()
    frames()
    print(sorted(p.name for p in OUT.iterdir()), sum(p.stat().st_size for p in OUT.rglob("*.png")) // 1024, "KB")
