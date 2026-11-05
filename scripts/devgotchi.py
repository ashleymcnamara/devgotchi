"""devgotchi: a tiny pixel developer the community raises through GitHub issues.

usage:
  python3 scripts/devgotchi.py render
  python3 scripts/devgotchi.py tick                     # hourly-ish decay, run by cron
  python3 scripts/devgotchi.py act "<title>" "<login>" "<account created_at>"   # prints the bot comment
"""
import base64, json, struct, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
EGG_DIR = ROOT / "egg"
DOCS = ROOT / "docs"
REPO = "ashleymcnamara/devgotchi"
PROFILE = "https://github.com/ashleymcnamara"
OWNER = "ashleymcnamara"
COOLDOWN_HOURS, MIN_ACCOUNT_DAYS = 1, 7
NAME = "Byte"

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
PAGES = "https://ashleymcnamara.github.io/devgotchi/"
ACTIONS = {
    "coffee": ("☕", "Pour Byte a coffee", "drank your coffee"),
    "nap": ("💤", "Send Byte to bed", "took a power nap"),
    "debug": ("🐛", "Help Byte squash a bug", "squashed a bug with you"),
}
JITTERY = 3

# The shell is the approved mockup (1254x1254 px space) cut by scripts/build_art.py. Byte's screen is
# hand-drawn pixel art on a 144x104 grid, scaled 4x into the shell's LCD; the bot needs no Pillow.
ART = ROOT / "art"
CROP = (118, 0, 1020, 1242)
ROW1, ROW2, COL1, COL2 = 870, 1098, 511, 745
LCDBOX = (338, 398, 577, 442)
BTNS = {"coffee": (306, 876, 190, 168), "nap": (528, 876, 198, 168), "debug": (757, 876, 189, 168)}
SCALE = 1 / 3
LX, LY, LW, LH, K = 78, 124, 144, 104, 4  # the screen's own grid, and how much it is blown up
LCD, LCDK, OFF = "#efeaff", "#3b2a63", "#d8cff5"

PAL = {"k": "#2a1b3d", "h": "#7a4526", "H": "#a8673a", "s": "#f9d2b0", "c": "#f49ab0", "w": "#ffffff",
       "p": "#8f6cf2", "P": "#6449c9", "l": "#c6b6ff", "m": "#c04cf0", "g": "#d9d4e6", "G": "#a69fba",
       "r": "#e5484d", "o": "#f26b2a", "b": "#7b4a2a"}
CAT = ["k.....k", "kk...kk", "kwwwwwk", "kwkwkwk", "kwwcwwk", ".kkkkk."]
LAPTOP = ["kkkkkkkk.", "kllllllk.", "kllwwllk.", "kllllllk.", "kkkkkkkkk", "kPPPPPPPk", "kkkkkkkkk"]
MUG = [".w.w...", "..w.w..", "kkkkk..", "kbbbkk.", "kwwwk.k", "kwwwkk.", ".kkk..."]
BUGC = [".k.k.", "krrrk", "rrkrr", "krrrk", ".r.r."]
SPLATC = ["r.r.r", ".rwr.", "rwwwr", ".rwr.", "r.r.r"]
CRABC = ["o.......o", "oo.....oo", ".ooooooo.", "ookoookoo", "ooooooooo", "o.o...o.o"]
HEART = [".c.c.", "ccccc", "ccccc", ".ccc.", "..c.."]
SHEET = {"BABY": "baby", "TODDLER": "toddler", "KID": "child", "TEEN": "teen", "ADULT": "adult", "ELDER": "elder"}
SPEED = {"idle": 2.4, "code": .9, "nap": 2.6, "eat": 1.4, "happy": 1.2, "sad": 2.4, "walk": 1.0}

STAGES = [(0, "baby", "BABY"), (1, "toddler", "TODDLER"), (3, "kid", "KID"), (7, "teen", "TEEN"),
          (14, "grown-up dev", "ADULT"), (30, "wise elder dev", "ELDER")]
REACT_HOURS, GRUMPY_HOURS, RUST_HOURS = 6, 24, 48
RETIRE_DAY = 60  # after this the next press hatches a new egg and Byte starts over as a baby
STAGE_SAY = {"BABY": "*happy baby noises*", "TODDLER": "She showed you her cat.",
             "KID": "She asked you 400 questions about Git.", "TEEN": "She nodded without taking her headphones off.",
             "ADULT": "She added you to the CONTRIBUTORS file.", "ELDER": "She told you about the time she fixed prod with a floppy disk."}
DOING = {"nap": "napping", "eat": "having a snack", "happy": "cheering", "code": "coding", "walk": "going for a walk",
         "idle": "hanging out", "sad": "feeling down"}


def cpx(rows, x0, y0, s, cls="", tint=None):
    r = "".join(f'<rect x="{x0 + x * s}" y="{y0 + y * s}" width="{s}" height="{s}" fill="{tint or PAL[c]}"/>'
                for y, row in enumerate(rows) for x, c in enumerate(row) if c in PAL)
    return f'<g{cls}>{r}</g>'


_uri = {}


def uri(name):
    if name not in _uri:
        _uri[name] = "data:image/png;base64," + base64.b64encode((ART / name).read_bytes()).decode()
    return _uri[name]


def dims(name):
    return struct.unpack(">II", (ART / name).read_bytes()[16:24])


def img(name, x, y, w, h, extra=""):
    return f'<image href="{uri(name)}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="none"{extra}/>'


def now():
    return datetime.now(timezone.utc)


def hours_since(iso):
    return (now() - datetime.fromisoformat(iso)).total_seconds() / 3600 if iso else 1e9


def stage(st):
    return [x for x in STAGES if day(st) - 1 >= x[0]][-1]


def condition(st):
    h = hours_since(st.get("last_care") or st["born"] + "T00:00:00+00:00")
    if h >= RUST_HOURS:
        return "rust"
    if h >= GRUMPY_HOURS or mood(st) == 1:
        return "grumpy"
    return "ok"


def mood(st):
    avg = (st["energy"] + st["rest"] + max(0, 10 - 3 * st["bugs"])) / 3
    return 3 if avg >= 7 else 2 if avg >= 4 else 1


_glyphs = None


def num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def txt(x, y, s, size=7, anchor="start", fill=LCDK, extra=""):
    """pixel text from art/glyphs.json (baked from pixel.ttf), so no font has to ride along in every svg."""
    global _glyphs
    if _glyphs is None:
        _glyphs = json.loads((ART / "glyphs.json").read_text())
    k, gl = size / _glyphs["size"], _glyphs["glyphs"]
    chars = [gl.get(c, gl["?"]) for c in s]
    w = sum(c["adv"] for c in chars) * k
    x0 = x - {"middle": w / 2, "end": w}.get(anchor, 0)
    d, cx = [], 0
    for c in chars:
        for rx, ry, rw in c["runs"]:
            d.append(f"M{num(x0 + (cx + rx) * k)} {num(y + ry * k)}h{num(rw * k)}v{num(k)}h{num(-rw * k)}z")
        cx += c["adv"]
    return f'<path d="{"".join(d)}" fill="{fill}"{extra}/>'


def xp(st):
    return st.get("xp", st["total"] * 5)


def level(st):
    return 1 + xp(st) // 100


def recent(st):
    last = st.get("last") or {}
    return last.get("action") if hours_since(last.get("at")) < REACT_HOURS else None


_meta = None


def frames(sheet, a):
    global _meta
    if _meta is None:
        _meta = json.loads((ART / "girl/meta.json").read_text())
    return _meta[f"{sheet}-{a}"]


def anim(st):
    """which row of the sprite sheet Byte is acting out right now."""
    act, cond = recent(st), condition(st)
    if act == "nap":
        return "nap"
    if act == "coffee":
        return "eat"
    if act == "debug":
        return "happy" if st["bugs"] == 0 else "code"
    if cond != "ok":
        return "sad"
    if mood(st) >= 2:
        return "walk" if st.get("ticks", 0) % 2 else "code"
    return "idle"


def gen(st):
    return st.get("gen", 1)


def describe(st):
    """alt text that says what the screen actually shows."""
    cond = condition(st)
    doing = {"rust": "rewriting everything in Rust", "grumpy": "grumpy from being ignored"}.get(cond, DOING[anim(st)])
    bugs = f", with {plural(st['bugs'], 'bug')} crawling around" if st["bugs"] else ""
    g = f" (generation {gen(st)})" if gen(st) > 1 else ""
    return (f"{NAME}{g} is a {stage(st)[1]} on day {day(st)}, level {level(st)}. "
            f"She's {doing}{bugs}. Her sleeping cat is next to her.")


def girl(st, cx, floor, tallest):
    """Byte's sprite-sheet frames, stacked; CSS shows one at a time. Returns markup and her right edge."""
    sheet, a = SHEET[stage(st)[2]], anim(st)
    fr = frames(sheet, a)
    top, bottom = min(f[1] for f in fr), max(f[1] + f[3] for f in fr)
    s = min(1.0, tallest / (bottom - top))
    n, dur = len(fr), SPEED[a]
    out, right = [], cx
    for i, (bx, by, w, h) in enumerate(fr):
        x, y = cx - w * s / 2, floor - (bottom - by) * s
        right = max(right, x + w * s)
        style = f' class="fr fr{i}" style="animation:k{n} {dur}s steps(1) {-dur * ((n - i) % n) / n:.2f}s infinite"' if n > 1 else ""
        out.append(img(f"girl/{sheet}-{a}-{i}.png", round(x, 2), round(y, 2), round(w * s, 2), round(h * s, 2), style))
    return "".join(out), right


def lcd(st):
    """the live screen. independent groups: #status #props #character #pop #stats."""
    act, cond, abbr = recent(st), condition(st), stage(st)[2]
    jit = st.get("jitter", 0) >= JITTERY
    lx, ly, lw, lh = LCDBOX
    oy = (lh / K - LH) / 2
    up = f'transform="translate({lx - LX * K} {ly + oy * K - LY * K}) scale({K})"'  # screen grid -> shell pixels

    def g(i, inner, cls=""):
        return f'<g id="{i}"{cls}><g {up}>{inner}</g></g>'

    pet, right = girl(st, LX + LW // 2 - 8, LY + 84, 64)
    right = round(right) + 2
    prop, pop, stat = "", "", f"{abbr} DAY {day(st)}"
    prop += img("cat.png", LX + 3, LY + 84 - 18, round(142 * 18 / 78, 2), 18)
    if act == "coffee":
        prop, pop, stat = prop + cpx(MUG, right, LY + 58, 3), "ZING" if jit else "+2", f"ENERGY {st['energy']}/10"
    elif act == "nap":
        pop, stat = "+3", f"REST {st['rest']}/10"
    elif act == "debug":
        prop, pop, stat = prop + cpx(SPLATC, right + 2, LY + 66, 4), "OK!", f"BUGS {st['bugs']}"
    elif cond == "rust":
        prop += cpx(CRABC, right, LY + 68, 3, ' class="bug"')
        pop, stat = ".rs", "IN RUST"
    elif cond == "grumpy":
        pop, stat = "ugh", "GRUMPY"
    elif jit:
        pop, stat = "!!", "JITTERY"
    elif day(st) > RETIRE_DAY:
        stat = "NEW EGG SOON"
    if st["bugs"]:
        prop += cpx(BUGC, LX + 10, LY + 44, 3, ' class="bug"')
    if st["bugs"] >= 3:
        prop += cpx(BUGC, LX + 12, LY + 40, 3)
    poptxt = txt(right + 14, LY + (30 if act == "nap" else 40), pop, 9, "middle", extra=' class="pop"') if pop else ""
    hearts = "".join(cpx(HEART, LX + LW - 40 + i * 12, LY + 6, 2, tint=None if i < mood(st) else OFF) for i in range(3))
    level_tag = txt(LX + 8, LY + 14, (f"G{gen(st)} " if gen(st) > 1 else "") + f"LV {level(st)}", 7)
    stats = (f'<rect x="{LX + 4}" y="{LY + LH - 17}" width="{LW - 8}" height="1" fill="{LCDK}" opacity=".25"/>'
             + txt(LX + 8, LY + LH - 6, NAME.upper()) + txt(LX + LW - 8, LY + LH - 6, stat, anchor="end"))
    return (f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" fill="{LCD}"/>'
            f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" fill="url(#grid)"/>'
            + g("status", hearts + level_tag) + g("props", prop)
            + g("character", f'<g class="{"jit" if jit and act != "nap" else ""}">{pet}</g>')
            + g("pop", poptxt) + g("stats", stats))


GRIDDEF = (f'<pattern id="grid" x="{LCDBOX[0]}" y="{LCDBOX[1]}" width="{K * 4}" height="{K * 4}" patternUnits="userSpaceOnUse">'
           f'<rect width="{K * 3}" height="{K * 3}" fill="{LCDK}" opacity=".06"/></pattern>')
CSS = ("@keyframes k2{0%,49.9%{opacity:1}50%,100%{opacity:0}}@keyframes k3{0%,33.2%{opacity:1}33.3%,100%{opacity:0}}"
       ".fr{opacity:0}"
       "@keyframes w{0%,49%{transform:translateX(0)}50%,100%{transform:translateX(2px)}}.bug{animation:w .8s steps(1) infinite}"
       "@keyframes jit{0%,32%{transform:translateX(-1px)}33%,65%{transform:translateX(1px)}66%,100%{transform:translateX(0)}}"
       ".jit{animation:jit .3s steps(1) infinite}"
       "@keyframes up{0%{transform:translateY(6px);opacity:0}20%,70%{opacity:1}100%{transform:translateY(-10px);opacity:0}}"
       ".pop{animation:up 1.8s steps(6) infinite}"
       "@keyframes zz{0%{transform:translateY(3px);opacity:0}30%,70%{opacity:1}100%{transform:translateY(-5px);opacity:0}}"
       ".zz{animation:zz 2.4s steps(6) infinite}.zz:nth-of-type(2){animation-delay:.6s}.zz:nth-of-type(3){animation-delay:1.2s}"
       "image{image-rendering:pixelated}"
       "@media (prefers-reduced-motion:reduce){*{animation:none!important}.fr{opacity:0}.fr0{opacity:1}}")


def svg(view, w, h, inner, title, css=CSS):
    x, y, vw, vh = view
    lab = f'role="img" aria-label="{title}"><title>{title}</title>' if title else 'aria-hidden="true">'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {vw} {vh}" width="{w}" height="{h}" '
            f'shape-rendering="crispEdges" {lab}<defs>{GRIDDEF}</defs><style>{css}</style>{inner}</svg>\n')


def plural(n, w):
    return f"{n} {w}{'' if n == 1 else 's'}"


def day(st):
    return (date.today() - date.fromisoformat(st["born"])).days + 1


PROMPTS = {"coffee": "☕ **Pour Byte a coffee**", "nap": "💤 **Send Byte to bed**", "debug": "🐛 **Help Byte squash a bug**"}


def need(st):
    """the button that helps most right now, and why, in Byte's words."""
    if st.get("jitter", 0) >= JITTERY:
        return "nap", "She's had way too much coffee. A nap would calm her down."
    if st["bugs"] >= 3:
        return "debug", f"There are {st['bugs']} bugs on her screen. Help her squash one!"
    low = min(("rest", "nap"), ("energy", "coffee"), key=lambda kv: st[kv[0]])
    if st[low[0]] <= 4:
        return low[1], ("She can barely keep her eyes open. Send her to bed!" if low[1] == "nap"
                        else "She's running on empty. She could really use a coffee!")
    if st["bugs"]:
        return "debug", f"There's {plural(st['bugs'], 'bug')} on her screen. Help her squash it!"
    return None, "She's doing great. Any button keeps her happy."


def upcoming(st):
    d = day(st) - 1
    nxt = [x for x in STAGES if x[0] > d]
    if nxt:
        n = nxt[0][0] - d
        return f"becomes a {nxt[0][1]} {'tomorrow' if n == 1 else f'in {n} days'}"
    n = RETIRE_DAY + 1 - d
    return "a new egg hatches with the next press" if n <= 0 else f"a new egg hatches {'tomorrow' if n == 1 else f'in {n} days'}"


def recent_users(st, n=5):
    return [u for u, _ in sorted(st["users"].items(), key=lambda kv: kv[1].get("at") or "", reverse=True)[:n]]


def issue_url(n):
    # GitHub's new issue page can ignore ?template=, so prefill title and body directly too.
    body = f"{PROMPTS[n]}\n\nJust hit **Create** and a bot does the rest. {NAME} replies right here in about 30 seconds.\n\n_(please don't edit the title)_"
    return (f"https://github.com/{REPO}/issues/new?template={n}.md"
            f"&title={quote('pet|' + n, safe='')}&body={quote(body, safe='')}")


def preview(st, a):
    """a copy of the state as it would look right after pressing a."""
    sim = json.loads(json.dumps(st))
    apply(sim, a, "")
    return sim


# ---- README cards: pixel stickers around the egg, drawn with the same font and sprites as the screen ----
INK, CARD, PINK, PINK2, BLUSH, PLUM, LAV, SUN, RUST = ("#2a1b3d", "#fff6fb", "#ff5fa2", "#f7a8c4", "#fadced",
                                                     "#b8336a", "#efeaff", "#ffd36b", "#f26b2a")
CW = 680
EGGPX = ["....XXXXX....", "..XXPPPPPXX..", ".XPHHPPPPPDX.", ".XPHPPPPPPDX.", "XPPPPPPPPPPDX",
         "XPPLLLLLLLPDX", "XPPLSSSSSLPDX", "XPPLSSSSSLPDX", "XPPLSSSSSLPDX", "XPPLLLLLLLPDX",
         "XPPPPPPPPPPDX", "XPPOPPOPPOPDX", ".XPPPPPPPPDX.", "..XXDDDDDXX..", "....XXXXX...."]
EGGPAL = {"X": INK, "P": PINK2, "H": "#ffffff", "D": "#e07aa4", "L": BLUSH, "S": LAV, "O": SUN}
SPARK = ["..k..", "..k..", "kk.kk", "..k..", "..k.."]
ZZZ = [".....kkk", "......k.", ".....kkk", "kkkk....", "...k....", "..k.....", ".k......", "kkkk...."]
CARD_CSS = ("image{image-rendering:pixelated}.soft{image-rendering:auto}"
            "@keyframes k2{0%,49.9%{opacity:1}50%,100%{opacity:0}}@keyframes k3{0%,33.2%{opacity:1}33.3%,100%{opacity:0}}"
            ".fr{opacity:0}@keyframes tw{0%,59%{opacity:1}60%,100%{opacity:.15}}.tw{animation:tw 1.6s steps(1) infinite}"
            ".tw2{animation-delay:.8s}@keyframes bob{0%,49%{transform:translateY(0)}50%,100%{transform:translateY(-4px)}}"
            ".bob{animation:bob 1s steps(1) infinite}@keyframes w{0%,49%{transform:translateX(0)}50%,100%{transform:translateX(3px)}}"
            ".walk{animation:w .7s steps(1) infinite}"
            "@media (prefers-reduced-motion:reduce){*{animation:none!important}.fr{opacity:0}.fr0{opacity:1}}")


def T(x, top, s, size=16, anchor="start", fill=INK, extra=""):
    """pixel text placed by its top edge (the font's caps are 5/8 of the size tall)."""
    return txt(x, top + size * 5 / 8, s, size, anchor, fill, extra)


def px(rows, x0, y0, s, pal, cls=""):
    r = "".join(f'<rect x="{x0 + x * s}" y="{y0 + y * s}" width="{s}" height="{s}" fill="{pal[c] if isinstance(pal, dict) else pal}"/>'
                for y, row in enumerate(rows) for x, c in enumerate(row) if c != "." and (not isinstance(pal, dict) or c in pal))
    return f'<g{cls}>{r}</g>'


def tw(s, size=16):
    global _glyphs
    if _glyphs is None:
        txt(0, 0, "a")
    gl = _glyphs["glyphs"]
    return sum(gl.get(c, gl["?"])["adv"] for c in s) * size / _glyphs["size"]


def wrap(s, width, size=16):
    lines, cur = [], ""
    for w in s.split():
        if cur and tw(cur + " " + w, size) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur]


def plate(x, y, w, h, fill=CARD, b=4, shadow=PINK2):
    """a chunky pixel card: notched corners, ink outline, offset pink shadow."""
    def notch(x, y, w, h, c):
        return (f'<rect x="{x + b}" y="{y}" width="{w - 2 * b}" height="{h}" fill="{c}"/>'
                f'<rect x="{x}" y="{y + b}" width="{w}" height="{h - 2 * b}" fill="{c}"/>')
    sh = notch(x + b, y + b, w, h, shadow) if shadow else ""
    return sh + notch(x, y, w, h, INK) + notch(x + b, y + b, w - 2 * b, h - 2 * b, fill)


def tab(x, y, label, fill=PINK, ink=INK, icon=""):
    w = round(tw(label)) + 28 + (22 if icon else 0)
    return plate(x, y, w, 32, fill, shadow=None) + icon + T(x + 14 + (22 if icon else 0), y + 8, label, 16, fill=ink), w


def card(h, title, body, icon="", title_fill=PINK):
    t, _ = tab(24, 0, title, title_fill, icon=icon)
    return plate(0, 16, CW - 4, h - 20) + t + body


def sticker(view_h, inner, alt, w=CW):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {view_h}" width="{w}" height="{view_h}" '
            f'shape-rendering="crispEdges" role="img" aria-label="{alt}"><title>{alt}</title><style>{CARD_CSS}</style>{inner}</svg>\n')


def pose(sheet, a, cx, floor, cls="", animate=True, sil=None):
    fr = frames(sheet, a)
    bottom = max(f[1] + f[3] for f in fr)
    fr = fr if animate else fr[:1]
    out, n = [], len(fr)
    for i, (bx, by, w, h) in enumerate(fr):
        st_ = f' class="fr fr{i}" style="animation:k{n} {SPEED[a]}s steps(1) {-SPEED[a] * ((n - i) % n) / n:.2f}s infinite"' if n > 1 else ""
        f = f' filter="url(#{sil})"' if sil else ""
        out.append(img(f"girl/{sheet}-{a}-{i}.png", round(cx - w / 2), floor - (bottom - by), w, h, st_ + f))
    return f'<g{cls}>{"".join(out)}</g>'


def title_card():
    word, size = "devgotchi", 48
    w = tw(word, size)
    x, y = (CW - w) / 2, 14
    k = size / 8
    out = "".join(T(x + dx, y + dy, word, size, fill=INK) for dx, dy in
                  [(-k, 0), (k, 0), (0, -k), (0, k), (-k, -k), (k, k), (-k, k), (k, -k), (k * 2, k * 2), (k, k * 2), (k * 2, k)])
    out += T(x, y, word, size, fill=PINK) + T(x, y, word, size, fill="#ffffff", extra=f' clip-path="url(#hi)"')
    clip = f'<defs><clipPath id="hi"><rect x="0" y="{y}" width="{CW}" height="{k}"/></clipPath></defs>'
    stars = (px(SPARK, x - 52, 18, 4, SUN, ' class="tw"') + px(SPARK, x + w + 26, 8, 3, PINK2, ' class="tw tw2"')
             + px(SPARK, x + w + 40, 50, 4, SUN, ' class="tw tw2"') + px(SPARK, x - 34, 58, 3, PINK2, ' class="tw"')
             + px(HEART, x + w + 8, 70, 3, {"c": PINK}))
    tag = "RAISE A TINY DEV, TOGETHER"
    tw_ = tw(tag)
    pill = plate((CW - tw_) / 2 - 18, 84, tw_ + 36, 34, CARD, shadow=PINK2) + T(CW / 2, 94, tag, 16, "middle", fill=PLUM)
    return sticker(126, clip + stars + out + pill, f"devgotchi: raise a tiny dev, together")


def bubble_card(st):
    want, why = need(st)
    icon = {"coffee": px(MUG, 0, 0, 4, PAL), "debug": px(BUGC, 2, 2, 5, PAL), "nap": px(ZZZ, 0, 0, 4, {"k": "#6449c9"})}.get(
        want, px(HEART, 4, 6, 5, {"c": PINK}))
    lines = wrap(why, 420)
    sub = f"{NAME} {upcoming(st)}."
    bw, lh = 600, 24
    subl = wrap(sub, 420)
    h = 30 + (len(lines) + len(subl)) * lh + 2
    x0 = (CW - bw) / 2
    tail = (f'<rect x="{CW / 2 - 12}" y="4" width="24" height="16" fill="{INK}"/>'
            f'<rect x="{CW / 2 - 8}" y="0" width="16" height="8" fill="{INK}"/>'
            f'<rect x="{CW / 2 - 4}" y="8" width="8" height="16" fill="{CARD}"/>'
            f'<rect x="{CW / 2 - 8}" y="14" width="16" height="10" fill="{CARD}"/>')
    hearts = "".join(px(HEART, x0 + bw - 76 + i * 20, 38, 3, {"c": PINK if i < mood(st) else BLUSH}) for i in range(3))
    body = "".join(T(x0 + 92, 40 + i * lh, l, 16, fill=INK) for i, l in enumerate(lines))
    body += "".join(T(x0 + 92, 46 + (len(lines) + i) * lh, l, 16, fill=PLUM) for i, l in enumerate(subl))
    ic = f'<g transform="translate({x0 + 30} {16 + (h - 28) / 2})"><g class="bob">{icon}</g></g>'
    inner = plate(x0, 16, bw, h + 16) + tail + ic + body + hearts
    return sticker(h + 40, inner, f"{why} {sub}")


def coin(cx, cy, icon, r=11, s=4):
    """a chunky yellow pixel button, like the ones on the egg."""
    out = []
    for j in range(-r, r):
        half = int(((r - .5) ** 2 - (j + .5) ** 2) ** .5 + .5)
        y = cy + j * s
        out.append(f'<rect x="{cx - half * s}" y="{y}" width="{half * 2 * s}" height="{s}" fill="{INK}"/>')
        inner = int(((r - 1.5) ** 2 - (j + .5) ** 2) ** .5 + .5) if abs(j + .5) < r - 1.5 else 0
        if inner:
            fill = "#fff2b8" if j < -r // 2 else SUN if j < r // 2 else "#f2b83d"
            out.append(f'<rect x="{cx - inner * s}" y="{y}" width="{inner * 2 * s}" height="{s}" fill="{fill}"/>')
    return "".join(out) + icon


def care_card():
    cols = [("COFFEE", ["+ ENERGY", "TOO MUCH =", "JITTERY"], px(MUG, -21, -21, 6, PAL)),
            ("NAP", ["+ REST", "+ ENERGY", "CALMS HER"], px(ZZZ, -20, -20, 5, {"k": "#6449c9"})),
            ("DEBUG", ["- 1 BUG", "+ XP", "COSTS ENERGY"], px(BUGC, -15, -15, 6, PAL))]
    cw = (CW - 4 - 48) / 3
    body = ""
    for i, (lab, desc, icon) in enumerate(cols):
        cx = round(24 + cw * i + cw / 2)
        body += coin(cx, 92, f'<g transform="translate({cx} 92)"><g class="bob" style="animation-delay:{i * .33:.2f}s">{icon}</g></g>')
        body += T(cx, 148, lab, 24, "middle", fill=INK)
        body += "".join(T(cx, 184 + j * 24, d, 16, "middle", fill=PLUM) for j, d in enumerate(desc))
    body += f'<rect x="28" y="266" width="{CW - 60}" height="4" fill="{BLUSH}"/>'
    body += T(CW / 2, 284, "ONE PRESS PER PERSON, PER HOUR", 16, "middle", fill=INK)
    return sticker(318, card(318, "HOW TO CARE FOR HER", body),
                   "How to care for her. Coffee gives energy, but too much makes her jittery. A nap gives rest and energy and calms her down. "
                   "Debugging squashes a bug for XP and costs energy. One press per person, per hour.")


def life_card(st):
    now_i = [x[2] for x in STAGES].index(stage(st)[2])
    slots = [(SHEET[a], lab, d + 1) for d, _, a in STAGES for lab in [{"ADULT": "DEV", "TODDLER": "TOT"}.get(a, a)]] + [(None, "EGG", RETIRE_DAY + 1)]
    sw = (CW - 4 - 32) / len(slots)
    floor = 140
    sil = ('<defs><filter id="sil"><feFlood flood-color="#c9bce8"/><feComposite in2="SourceAlpha" operator="in"/></filter></defs>')
    body = sil
    for i, (sheet, lab, d) in enumerate(slots):
        cx = round(16 + sw * i + sw / 2)
        if i == now_i:
            body += plate(round(cx - sw / 2) + 2, 50, round(sw) - 4, 148, BLUSH, b=4, shadow=None)
            body += f'<g class="bob">{px(HEART, cx - 8, 34, 3, {"c": PINK})}</g>'
        if sheet:
            body += pose(sheet, "idle", cx, floor, animate=i == now_i, sil=None if i <= now_i else "sil")
        else:
            body += px(EGGPX, cx - 26, floor - 60, 4, EGGPAL if now_i == len(slots) - 1 else {k: "#c9bce8" for k in EGGPAL})
        on = i <= now_i
        body += T(cx, 152, lab, 16, "middle", fill=INK if on else "#9a8bb8")
        body += T(cx, 174, f"DAY {d}", 16, "middle", fill=PLUM if on else "#b3a6cf")
    body += T(CW / 2, 214, f"SHE'S A {stage(st)[1].upper()} RIGHT NOW", 16, "middle", fill=PLUM)
    names = ", ".join(f"{l.lower()} on day {d}" for _, l, d in slots)
    return sticker(252, card(252, "HOW SHE GROWS", body),
                   f"How she grows: {names}. She's a {stage(st)[1]} right now.")


def neglect_card(st):
    sheet = SHEET[stage(st)[2]]
    pw = (CW - 4 - 48 - 2 * 28) / 3
    xs = [24 + i * (pw + 28) for i in range(3)]
    floor = 132
    body = ""
    for i, x in enumerate(xs):
        fill = "#fff0e6" if i == 2 else LAV
        body += plate(round(x), 52, round(pw), 150, fill, b=4, shadow=None)
        if i < 2:
            ax = round(x + pw + 6)
            body += px(["k..", "kk.", "kkk", "kk.", "k.."], ax, 116, 4, INK)
    # 6h: hearts drain, bugs move in
    c0 = xs[0] + pw / 2
    body += T(c0, 64, "EVERY 6 HRS", 16, "middle", fill=PLUM)
    body += "".join(px(HEART, c0 - 38 + j * 26, 94, 4, {"c": PINK if j == 0 else "#d8cff5"}) for j in range(3))
    body += px(BUGC, c0 - 34, 120, 4, PAL, ' class="walk"') + px(BUGC, c0 + 14, 128, 4, PAL)
    body += T(c0, 164, "SHE GETS TIRED", 16, "middle", fill=INK) + T(c0, 184, "BUGS PILE UP", 16, "middle", fill=INK)
    # 24h: grumpy
    c1 = xs[1] + pw / 2
    body += T(c1, 64, "AFTER 1 DAY", 16, "middle", fill=PLUM)
    body += pose(sheet, "sad", round(c1), floor + 24, animate=True)
    body += T(c1 + 44, 92, "ugh", 16, "middle", fill=PLUM)
    body += T(c1, 182, "GRUMPY", 16, "middle", fill=INK)
    # 48h: rust
    c2 = xs[2] + pw / 2
    body += T(c2, 64, "AFTER 2 DAYS", 16, "middle", fill=RUST)
    body += pose(sheet, "sad", round(c2 - 22), floor + 8, animate=True)
    body += px(CRABC, round(c2 + 14), floor - 26, 4, {"o": RUST, "k": INK}, ' class="walk"')
    body += T(c2 + 32, 84, ".RS", 16, "middle", fill=RUST)
    body += "".join(T(c2, 144 + j * 20, w, 16, "middle", fill=INK) for j, w in enumerate(["REWRITING", "EVERYTHING", "IN RUST"]))
    foot = "SHE NEVER DIES. ONE PRESS CHEERS HER UP"
    body += px(HEART, CW / 2 - tw(foot) / 2 - 24, 222, 3, {"c": PINK}) + T(CW / 2 + 4, 220, foot, 16, "middle", fill=INK)
    return sticker(258, card(258, "IF YOU FORGET HER", body, title_fill=SUN),
                   "If you forget her: every 6 hours she gets tired and bugs pile up. After 1 day she's grumpy. "
                   "After 2 days she starts rewriting everything in Rust. She never dies. One press cheers her right up.")


def render(st):
    EGG_DIR.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    x0, y0, cw, ch = CROP
    alt = f"devgotchi: {describe(st)}"
    (EGG_DIR / "top.svg").write_text(svg((x0, y0, cw, ROW1), round(cw * SCALE), round(ROW1 * SCALE),
                                         img("top.png", x0, y0, cw, ROW1) + lcd(st), alt))
    (EGG_DIR / "lcd.svg").write_text(svg(LCDBOX, LCDBOX[2], LCDBOX[3], lcd(st), alt))
    for n in BTNS:
        (EGG_DIR / f"lcd-{n}.svg").write_text(svg(LCDBOX, LCDBOX[2], LCDBOX[3], lcd(preview(st, n)), f"{ACTIONS[n][1]}: {describe(preview(st, n))}"))
    for f in ["shell.png", "btn-coffee.png", "btn-nap.png", "btn-debug.png", "pixel.ttf"]:
        if not (DOCS / f).exists() or (DOCS / f).read_bytes() != (ART / f).read_bytes():
            (DOCS / f).write_bytes((ART / f).read_bytes())
    (DOCS / "actions.json").write_text(json.dumps(
        {"repo": REPO, "name": NAME, "crop": list(CROP), "lcd": list(LCDBOX),
         "buttons": [{"id": n, "box": list(bx), "label": ACTIONS[n][1], "url": issue_url(n)} for n, bx in BTNS.items()]},
        indent=2) + "\n")
    want, why = need(st)
    (EGG_DIR / "status.json").write_text(json.dumps(
        {"need": want, "why": why, "next": upcoming(st), "recent": recent_users(st), "stage": stage(st)[1], "day": day(st)},
        indent=2) + "\n")
    v = int(time.time())
    widths = {"coffee": COL1 - x0, "nap": COL2 - COL1, "debug": x0 + cw - COL2}
    btns = "".join(f'<a href="{PAGES}?do={n}"><img src="art/row-{n}.png" width="{round(w * SCALE)}" align="top" alt="{ACTIONS[n][1]}"></a>'
                   for n, w in widths.items())
    line = []
    if st["users"]:
        line.append("recently: " + " ".join(f"@{u}" for u in recent_users(st)))
    line.append(f'{plural(len(st["users"]), "caretaker")} · {plural(st["total"], "action")}')
    hint = (f"{ACTIONS[want][0]} " if want else "💖 ") + why
    for name, body in {"title": title_card(), "bubble": bubble_card(st), "care": care_card(),
                       "life": life_card(st), "neglect": neglect_card(st)}.items():
        (EGG_DIR / f"{name}.svg").write_text(body)
    w = round(cw * SCALE)
    who = (" ".join(f"@{u}" for u in recent_users(st)) + " · ") if st["users"] else ""
    (ROOT / "README.md").write_text(f"""<div align="center">

<img src="egg/title.svg?v={v}" width="{CW}" alt="devgotchi: raise a tiny dev, together">

Byte is a tiny pixel dev the internet raises together.<br>
Press a button on the egg, hit **Create**, and she replies to you in about 30 seconds.

<a href="{PAGES}"><img src="egg/top.svg?v={v}" width="{w}" align="top" alt="{alt}"></a><br>{btns}<br><img src="art/bottom.png" width="{w}" align="top" alt="">

<img src="egg/bubble.svg?v={v}" width="{CW}" alt="{why} {NAME} {upcoming(st)}.">

<sub>💕 raised by {who}{plural(len(st["users"]), "caretaker")} · {st["total"]} {"press" if st["total"] == 1 else "presses"}</sub>

<br>

<img src="egg/care.svg?v={v}" width="{CW}" alt="How to care for her. Coffee gives energy, but too much makes her jittery. A nap gives rest and energy and calms her down. Debugging squashes a bug for XP and costs a little energy. One press per person, per hour.">

<img src="egg/life.svg?v={v}" width="{CW}" alt="How she grows: baby, toddler, kid, teen, dev, then a wise elder. After day {RETIRE_DAY} a new egg hatches. She's a {stage(st)[1]} right now.">

<img src="egg/neglect.svg?v={v}" width="{CW}" alt="If you forget her: every 6 hours she gets tired and bugs pile up. After 1 day she's grumpy. After 2 days she starts rewriting everything in Rust. She never dies, and one press cheers her right up.">

<sub>🥚 also hiding on [@{OWNER}'s profile]({PROFILE}) · [play in your browser]({PAGES})</sub>

</div>
""")


def issue_body(n):
    emo, verb, _ = ACTIONS[n]
    return (f"{emo} **{verb}**\n\nJust hit **Submit new issue** and a bot does the rest. "
            f"{NAME} replies right here in about 30 seconds.\n\n_(please don't edit the title)_")


def load():
    return json.loads(STATE.read_text())


def save(st):
    STATE.write_text(json.dumps(st, indent=2) + "\n")
    render(st)


def tick():
    st = load()
    st["ticks"] = st.get("ticks", 0) + 1
    st["energy"] = max(0, st["energy"] - 1)
    st["rest"] = max(0, st["rest"] - 1)
    st["jitter"] = max(0, st.get("jitter", 0) - 1)
    if st["ticks"] % 2 == 0:
        st["bugs"] = min(5, st["bugs"] + 1)
    save(st)


def footer(st):
    return (f'<a href="{PAGES}"><img src="https://raw.githubusercontent.com/{REPO}/__SHA__/egg/top.svg" width="240" alt="{describe(st)}"></a>\n\n'
            f"**[← back to the egg]({PAGES})** · "
            f"<sub>{NAME} is a {stage(st)[1]}, day {day(st)} · {plural(len(st['users']), 'caretaker')} so far</sub>")


def apply(st, a, user, stamp=None):
    """the game rules for one button press. mutates st."""
    st.setdefault("xp", st["total"] * 5)
    jit = st.get("jitter", 0)
    if a == "coffee":
        st["energy"] = min(10, st["energy"] + (1 if jit >= JITTERY else 2))
        st["rest"] = max(0, st["rest"] - 1)
        st["jitter"] = min(5, jit + 1)
    elif a == "nap":
        st["rest"] = min(10, st["rest"] + 3)
        st["energy"] = min(10, st["energy"] + 1)
        st["jitter"] = 0
    else:
        st["xp"] += 10 if st["bugs"] else 0
        st["bugs"] = max(0, st["bugs"] - 1)
        st["energy"] = max(0, st["energy"] - 1)
    st["xp"] += 5
    st["total"] += 1
    if st["total"] % 4 == 0 and a != "debug":
        st["bugs"] = min(5, st["bugs"] + 1)
    today = date.today().isoformat()
    days = st.setdefault("days", {})
    days[today] = days.get(today, 0) + 1
    for d in sorted(days)[:-30]:
        del days[d]
    stamp = stamp or now().isoformat(timespec="seconds")
    st["last"] = {"action": a, "user": user, "at": stamp}
    st["last_care"] = stamp


def hatch(st):
    """the elder retires and Byte starts over as a baby. caretakers and their streaks carry over."""
    today = date.today().isoformat()
    st.setdefault("elders", []).append({"gen": gen(st), "born": st["born"], "retired": today, "level": level(st)})
    st.update(gen=gen(st) + 1, born=today, energy=10, rest=10, bugs=0, jitter=0, xp=0, seen_stage="BABY", last_care=None)


def act(title, user, created=""):
    st = load()
    a = title.strip().lower().removeprefix("pet|").strip()
    if a not in ACTIONS:
        return f"🥚 {NAME} only understands the buttons on the egg.\n\n" + footer(st)
    try:
        age = (now() - datetime.fromisoformat(created.replace("Z", "+00:00"))).days
    except ValueError:
        age = 0
    if age < MIN_ACCOUNT_DAYS:
        return (f"🥚 Thanks for stopping by! {NAME} only accepts care from GitHub accounts older than "
                f"{MIN_ACCOUNT_DAYS} days, to keep the egg safe from spam bots. Come back soon 💖\n\n" + footer(st))
    u = st["users"].get(user)
    if u and user != OWNER and hours_since(u.get("at")) < COOLDOWN_HOURS:
        mins = max(1, int((COOLDOWN_HOURS - hours_since(u["at"])) * 60))
        return (f"⏳ {NAME} is still processing your last visit, @{user}. "
                f"Come back in about {plural(mins, 'minute')}!\n\n" + footer(st))

    was_st = dict(st, last=None)
    (EGG_DIR / "before.svg").write_text(svg(LCDBOX, LCDBOX[2], LCDBOX[3], lcd(was_st), f"Before: {describe(was_st)}"))
    hatched = None
    if day(st) > RETIRE_DAY:
        hatched = level(st)
        hatch(st)
    was, lv = condition(st), level(st)
    before = dict(st)
    stamp = now().isoformat(timespec="seconds")
    apply(st, a, user, stamp)
    today = date.today().isoformat()
    first = u is None
    if first:
        u = {"count": 0, "first": today, "last_day": None, "streak": 0}
    if u["last_day"] != today:
        yday = date.fromordinal(date.today().toordinal() - 1).isoformat()
        u["streak"] = u["streak"] + 1 if u["last_day"] == yday else 1
    u.update(count=u["count"] + 1, last_day=today, at=stamp)
    st["users"][user] = u
    save(st)

    emo, _, did = ACTIONS[a]
    change = {"coffee": f"Energy {before['energy']} → {st['energy']}",
              "nap": f"Rest {before['rest']} → {st['rest']}, Energy {before['energy']} → {st['energy']}",
              "debug": f"Bugs {before['bugs']} → {st['bugs']}, +{xp(st) - xp(before)} XP"}[a]
    if a == "coffee" and st["jitter"] >= JITTERY:
        change += f". ⚡ She's getting jittery, a nap would help"
    if first:
        hi = f"Hi @{user}, you're caretaker **no. {len(st['users'])}**! 💖"
    else:
        streak = f" · 🔥 **{u['streak']}-day streak**" if u["streak"] > 1 else ""
        n = u["count"]
        suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        hi = f"Welcome back @{user}, that's your **{n}{suf} visit**{streak}."
    extra = ""
    if hatched:
        extra = (f"\n\n🥚 **A new egg hatched!** {NAME} (generation {gen(st) - 1}) retired at level {hatched} after "
                 f"{RETIRE_DAY} days of shipping. Meet generation {gen(st)}, and you're the very first to hold her.")
    elif was == "rust":
        extra = f"\n\n🦀 **You rescued {NAME}!** She was halfway through rewriting everything in Rust."
    elif was == "grumpy":
        extra = f"\n\n🌤️ {NAME} was feeling neglected. You cheered her up."
    if level(st) > lv and not hatched:
        extra += f"\n\n⭐ **Level up!** {NAME} is level {level(st)} now."
    if st.get("seen_stage") != stage(st)[2]:
        if st.get("seen_stage"):
            extra += f"\n\n🎉 **{NAME} grew up!** She's a **{stage(st)[1]}** now, and you're the first to see it."
        st["seen_stage"] = stage(st)[2]
        save(st)
    extra += f"\n\n_{STAGE_SAY[stage(st)[2]]}_"
    raw = f"https://raw.githubusercontent.com/{REPO}/__SHA__/egg"
    pics = (f'<img src="{raw}/before.svg" width="220" alt="Before: {describe(was_st)}"> ➜ '
            f'<img src="{raw}/lcd.svg" width="220" alt="After: {describe(st)}">')
    return (f"{emo} **{NAME} {did}!** {change}.{extra}\n\n{pics}\n\n{hi}\n\n"
            f"**[← back to the egg]({PAGES})** · <sub>{NAME} {upcoming(st)} · "
            f"{plural(len(st['users']), 'caretaker')} so far</sub>")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "render":
        render(load())
    elif cmd == "tick":
        tick()
    else:
        print(act(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""))
