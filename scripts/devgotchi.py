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

# Everything sits on one pixel grid: a cell is 6 units of the approved mockup (2 css px in the README).
# art/ holds the shell and Byte's frames, already snapped by scripts/build_art.py; the bot only base64s them.
ART = ROOT / "art"
U, GX, GY = 6, 118, 0
CROP = (GX, GY, 1020, 1242)  # 170 x 207 cells
ROW1, ROW2, COL1, COL2 = 870, 1098, 514, 748
BTNS = {n: (GX + c * U, GY + r * U, w * U, h * U) for n, (c, r, w, h) in
        {"coffee": (31, 146, 32, 28), "nap": (68, 146, 33, 28), "debug": (107, 146, 31, 28)}.items()}
# the screen: cells 38..132 x 70..136 of the shell, plus a 1-cell ink border. rows below are relative to it.
SX, SY, SW, SH = 38, 70, 95, 67
LCDBOX = (GX + (SX - 1) * U, GY + (SY - 1) * U, (SW + 2) * U, (SH + 2) * U)
HEADH, FLOORR, STATR = 11, 53, 55
CXC = 54
SCALE = 1 / 3
INK, HEAD, FIELD, GRID, FLOORC = "#1c1c3a", "#262743", "#c7e4f8", "#bcdcf3", "#8aa9dc"
DIM, OFF = "#3d3f66", "#a9c6e8"
GREENS = [DIM, "#0e4429", "#006d32", "#26a641", "#69dc7e"]
FONT = "dgpx," + "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
ADV = {**{c: 7 for c in "ABCDGHJKOPQRSU0234567890"}, **{c: 6 for c in "EFLTZ1-/"},
       **{c: 8 for c in "MNVWXY+"}, " ": 4, "I": 4, "!": 4, ".": 4}
SHEET = {"BABY": "baby", "TODDLER": "toddler", "KID": "child", "TEEN": "teen", "ADULT": "adult", "ELDER": "elder"}
# seconds per loop; frames step through it evenly
SPEED = {"idle": 2.4, "code": .9, "nap": 2.6, "eat": 1.4, "happy": 1.2, "sad": 2.4}

PAL = {"k": "#1c1c3a", "r": "#e5484d", "o": "#f26b2a", "w": "#ffffff", "c": "#fc74ac", "y": "#f5b83d",
       "m": "#8f6cf2", "d": DIM}
BUGC = [".k.....k.", "..k...k..", "..kkkkk..", ".krrkrrk.", "krwrkrrrk", ".krrkrrk.", "krrrkrrrk", ".kkkkkkk."]
CRABC = ["o.......o", "oo.....oo", ".ooooooo.", "ookoookoo", "ooooooooo", "o.o...o.o"]
HEART = [".cc.cc.", "ccccccc", "ccccccc", ".ccccc.", "..ccc..", "...c..."]
MINI = ["..www..", ".wwwww.", "ww.w.ww", "w.....w", "ww...ww", ".ww.ww.", "..w.w.."]  # Octicons mark-github, 7x7
BOLT = ["..y", ".yy", "yy.", "y.."]
MOON = [".mm", "mm.", "mm.", ".mm"]
STAR = [".c.", "ccc", ".c.", "c.c"]
STAGES = [(0, "baby", "BABY"), (1, "toddler", "TODDLER"), (3, "kid", "KID"), (7, "teen", "TEEN"),
          (14, "grown-up dev", "ADULT"), (30, "wise elder dev", "ELDER")]
REACT_HOURS, GRUMPY_HOURS, RUST_HOURS = 6, 24, 48


def gx(c):
    return GX + (SX + c) * U


def gy(r):
    return GY + (SY + r) * U


def box(c, r, w, h, fill, extra=""):
    return f'<rect x="{gx(c)}" y="{gy(r)}" width="{w * U}" height="{h * U}" fill="{fill}"{extra}/>'


def cpx(rows, c0, r0, cls="", tint=None):
    r = "".join(box(c0 + x, r0 + y, 1, 1, tint or PAL[ch]) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch in PAL)
    return f'<g{cls}>{r}</g>'


def width(s):
    return sum(ADV.get(c, 7) for c in s.upper())


def txt(c, r, s, fill=INK, anchor="start", size=1, extra=""):
    """pixel text whose capitals fill rows r..r+5*size-1, starting at cell c."""
    return (f'<text x="{gx(c)}" y="{gy(r + 5 * size)}" text-anchor="{anchor}" font-family="{FONT}" '
            f'font-size="{48 * size}" fill="{fill}"{extra}>{s}</text>')


_uri = {}


def uri(name):
    if name not in _uri:
        mime = "font/ttf" if name.endswith(".ttf") else "image/png"
        _uri[name] = f"data:{mime};base64," + base64.b64encode((ART / name).read_bytes()).decode()
    return _uri[name]


def dims(name):
    """size in grid cells (art is stored at 4x)"""
    w, h = struct.unpack(">II", (ART / name).read_bytes()[16:24])
    return w // 4, h // 4


def img(name, x, y, w, h, extra=""):
    return f'<image href="{uri(name)}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="none"{extra}/>'


def cimg(name, c, r, extra=""):
    w, h = dims(name)
    return img(name, gx(c), gy(r), w * U, h * U, extra)


_meta = None


def frames(sheet, anim):
    global _meta
    if _meta is None:
        _meta = json.loads((ART / "girl/meta.json").read_text())
    return _meta[f"{sheet}-{anim}"]


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


def t(x, y, s, size, fill=INK, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{FONT}" '
            f'font-size="{size}" fill="{fill}"{extra}>{s}</text>')


def xp(st):
    return st.get("xp", st["total"] * 5)


def level(st):
    return 1 + xp(st) // 100


def recent(st):
    last = st.get("last") or {}
    return last.get("action") if hours_since(last.get("at")) < REACT_HOURS else None


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
    return "code" if mood(st) >= 2 else "idle"


def girl(st):
    """Byte's animation frames, stacked; CSS shows one at a time. Feet sit on the floor."""
    sheet, a = SHEET[stage(st)[2]], anim(st)
    fr = frames(sheet, a)
    bottom = max(by + h for by, w, h in fr)
    n, dur = len(fr), SPEED[a]
    out = []
    for i, (by, w, h) in enumerate(fr):
        style = f' class="fr fr{i}" style="animation:k{n} {dur}s steps(1) {-dur * ((n - i) % n) / n:.2f}s infinite"' if n > 1 else ""
        out.append(img(f"girl/{sheet}-{a}-{i}.png", gx(CXC - w // 2), gy(FLOORR - (bottom - by)), w * U, h * U, style))
    return "".join(out)


def squares(st):
    """the last 30 days of care as a tiny contribution graph."""
    days = st.get("days", {})
    out = []
    for i in range(30):
        d = date.fromordinal(date.today().toordinal() - 29 + i).isoformat()
        n = days.get(d, 0)
        lvl = 0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3 if n <= 6 else 4
        out.append(box(11 + (i // 3) * 3, 1 + (i % 3) * 3, 2, 2, GREENS[lvl]))
    return "".join(out)


def meter(icon, c, n, of, on):
    return cpx(icon, c, 62) + "".join(box(c + 4 + i * 3, 62, 2, 4, on if i < n else OFF) for i in range(of))


def lcd(st):
    """the live screen. independent groups: #status #props #character #pop #stats."""
    act, cond, abbr = recent(st), condition(st), stage(st)[2]
    jit = st.get("jitter", 0) >= JITTERY
    hearts = "".join(cpx(HEART, 71 + i * 8, 3, tint=None if i < mood(st) else DIM) for i in range(3))
    status = box(0, 0, SW, HEADH, HEAD) + cpx(MINI, 2, 2) + squares(st) + txt(43, 3, f"D{day(st)}", "#e9e6ff") + hearts
    cat, mug = dims("cat.png"), dims("mug.png")
    props = cimg("cat.png", 1, FLOORR - cat[1])
    if act != "nap":
        props += cimg("mug.png", SW - 2 - mug[0], FLOORR - mug[1], ' class="steam"' if act == "coffee" else "")
    pop = ""
    if act == "coffee":
        pop = "ZING!" if jit else "+NRG"
    elif act == "nap":
        props += "".join(txt(c, r, z, "#8f6cf2", size=sz, extra=' class="zz"') for c, r, sz, z in
                         ((76, 44, 1, "z"), (81, 35, 1, "Z"), (85, 22, 2, "Z")))
        pop = "+REST"
    elif act == "debug":
        pop = "FIXED!" if st["bugs"] == 0 else "-1 BUG"
    elif cond == "rust":
        props += cpx(CRABC, 70, FLOORR - 6, ' class="bug"')
        pop = "RUST!"
    elif cond == "grumpy":
        pop = "UGH"
    elif jit:
        pop = "!!"
    for bc, br in [(8, 24), (82, 14), (25, 31)][:st["bugs"]]:
        props += cpx(BUGC, bc, br, ' class="bug"')
    poptxt = ""
    if pop:
        w = width(pop) + 2
        poptxt = (f'<g class="pop">{box(2, 13, w, 9, INK)}{box(3, 14, w - 2, 7, "#fff")}'
                  + txt(3, 15, pop) + "</g>")
    x, lv = xp(st), level(st)
    stats = (txt(1, 56, abbr) + txt(SW - 1, 56, f"LV {lv}", anchor="end")
             + meter(BOLT, 2, st["energy"], 10, PAL["y"]) + meter(MOON, 39, st["rest"], 10, PAL["m"])
             + meter(STAR, 76, (x % 100) // 20, 5, PAL["c"]))
    night = box(0, HEADH, SW, FLOORR - HEADH, "#3a2a6a", ' opacity=".22"') if act == "nap" else ""
    lx, ly, lw, lh = LCDBOX
    return (f'<rect x="{lx}" y="{ly + U}" width="{lw}" height="{lh - 2 * U}" fill="{INK}"/>'
            f'<rect x="{lx + U}" y="{ly}" width="{lw - 2 * U}" height="{lh}" fill="{INK}"/>'
            + box(0, 0, SW, SH, FIELD) + box(0, HEADH, SW, FLOORR - HEADH, "url(#grid)")
            + box(0, FLOORR, SW, 2, FLOORC)
            + f'{night}<g id="status">{status}</g><g id="props">{props}</g>'
            f'<g id="character"><g class="{"jit" if jit and act != "nap" else "bob"}">{girl(st)}</g></g>'
            f'<g id="pop">{poptxt}</g><g id="stats">{stats}</g>')


GRIDDEF = (f'<pattern id="grid" x="{GX}" y="{GY}" width="{4 * U}" height="{4 * U}" patternUnits="userSpaceOnUse">'
           f'<rect width="{4 * U}" height="{4 * U}" fill="{FIELD}"/><rect width="{U}" height="{U}" fill="{GRID}"/></pattern>')
CSS = ("@keyframes k2{0%,49.9%{opacity:1}50%,100%{opacity:0}}@keyframes k3{0%,33.2%{opacity:1}33.3%,100%{opacity:0}}"
       "@keyframes w{0%,49%{transform:translateX(0)}50%,100%{transform:translateX(6px)}}.bug{animation:w .8s steps(1) infinite}"
       "@keyframes bob{0%,49%{transform:translateY(0)}50%,100%{transform:translateY(-6px)}}.bob{animation:bob 1.6s steps(1) infinite}"
       "@keyframes jit{0%,32%{transform:translateX(-6px)}33%,65%{transform:translateX(6px)}66%,100%{transform:translateX(0)}}"
       ".jit{animation:jit .3s steps(1) infinite}"
       "@keyframes up{0%{transform:translateY(12px);opacity:0}15%,75%{transform:translateY(0);opacity:1}100%{transform:translateY(-6px);opacity:0}}"
       ".pop{animation:up 3s steps(6) infinite}"
       "@keyframes zz{0%{transform:translateY(8px);opacity:0}30%,70%{opacity:1}100%{transform:translateY(-16px);opacity:0}}"
       ".zz{animation:zz 2.4s steps(6) infinite}.zz:nth-of-type(2){animation-delay:.6s}.zz:nth-of-type(3){animation-delay:1.2s}"
       "@keyframes st{0%,49%{transform:translateY(0)}50%,100%{transform:translateY(-6px)}}.steam{animation:st 1s steps(1) infinite}"
       "image{image-rendering:pixelated}"
       "@media (prefers-reduced-motion:reduce){*{animation:none!important}.fr{opacity:0}.fr0{opacity:1}}")


def svg(view, w, h, inner, title, css=CSS, font=True):
    x, y, vw, vh = view
    lab = f'role="img" aria-label="{title}"><title>{title}</title>' if title else 'aria-hidden="true">'
    face = f'@font-face{{font-family:dgpx;src:url({uri("pixel.ttf")}) format("truetype")}}' if font else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {vw} {vh}" width="{w}" height="{h}" '
            f'shape-rendering="crispEdges" {lab}<defs>{GRIDDEF}</defs><style>{face}{css}</style>{inner}</svg>\n')


def plural(n, w):
    return f"{n} {w}{'' if n == 1 else 's'}"


def day(st):
    return (date.today() - date.fromisoformat(st["born"])).days + 1


PROMPTS = {"coffee": "☕ **Pour Byte a coffee**", "nap": "💤 **Send Byte to bed**", "debug": "🐛 **Help Byte squash a bug**"}


def issue_url(n):
    # GitHub's new issue page can ignore ?template=, so prefill title and body directly too.
    body = f"{PROMPTS[n]}\n\nJust hit **Create** and a bot does the rest. {NAME} reacts on the egg in about 30 seconds.\n\n_(please don't edit the title)_"
    return (f"https://github.com/{REPO}/issues/new?template={n}.md"
            f"&title={quote('pet|' + n, safe='')}&body={quote(body, safe='')}")


def preview(st, a):
    """a copy of the state as it would look right after pressing a."""
    sim = json.loads(json.dumps(st))
    apply(sim, a, "")
    return sim


def render(st):
    EGG_DIR.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    x0, y0, cw, ch = CROP
    alt = f"devgotchi: {NAME}, a tiny pixel developer raised by the community. {stage(st)[1].capitalize()}, day {day(st)}, level {level(st)}."
    (EGG_DIR / "top.svg").write_text(svg((x0, y0, cw, ROW1), round(cw * SCALE), round(ROW1 * SCALE),
                                         img("top.png", x0, y0, cw, ROW1) + lcd(st), alt))
    (EGG_DIR / "lcd.svg").write_text(svg(LCDBOX, LCDBOX[2], LCDBOX[3], lcd(st), alt))
    for n in BTNS:
        (EGG_DIR / f"lcd-{n}.svg").write_text(svg(LCDBOX, LCDBOX[2], LCDBOX[3], lcd(preview(st, n)), f"{NAME} after {n}"))
    for f in ["shell.png", "btn-coffee.png", "btn-nap.png", "btn-debug.png", "pixel.ttf"]:
        if not (DOCS / f).exists() or (DOCS / f).read_bytes() != (ART / f).read_bytes():
            (DOCS / f).write_bytes((ART / f).read_bytes())
    (DOCS / "actions.json").write_text(json.dumps(
        {"repo": REPO, "name": NAME, "crop": list(CROP), "lcd": list(LCDBOX),
         "buttons": [{"id": n, "box": list(bx), "label": ACTIONS[n][1], "url": issue_url(n)} for n, bx in BTNS.items()]},
        indent=2) + "\n")
    v = int(time.time())
    widths = {"coffee": COL1 - x0, "nap": COL2 - COL1, "debug": x0 + cw - COL2}
    btns = "".join(f'<a href="{PAGES}?do={n}"><img src="art/row-{n}.png" width="{round(w * SCALE)}" align="top" alt="{ACTIONS[n][1]}"></a>'
                   for n, w in widths.items())
    last = st.get("last")
    top = sorted(st["users"].items(), key=lambda kv: -kv[1]["count"])[:3]
    line = []
    if last:
        line.append(f'last {last["action"]} from @{last["user"]}')
    if top:
        line.append("top caretakers: " + " ".join(f"@{u}" for u, _ in top))
    line.append(f'{plural(len(st["users"]), "caretaker")} · {plural(st["total"], "action")}')
    (ROOT / "README.md").write_text(f"""<div align="center">

# 🥚 devgotchi

{NAME} is a tiny pixel developer the community raises together. Press a button, hit **Create**, and she reacts here in about 30 seconds.<br>
She grows up from a baby to a teen with headphones to a wise elder dev. Neglect her and she starts rewriting everything in Rust.

<a href="{PAGES}"><img src="egg/top.svg?v={v}" width="{round(cw * SCALE)}" align="top" alt="{alt}"></a><br>{btns}<br><img src="art/bottom.png" width="{round(cw * SCALE)}" align="top" alt="">

<sub>{" · ".join(line)}</sub>

<sub>☕ +energy (too much and she gets jittery) · 💤 +rest, +energy, calms her down · 🐛 −1 bug, costs energy, +XP</sub>

<sub>one press per person per hour · lives on [@{OWNER}'s profile]({PROFILE})</sub>

</div>
""")


def issue_body(n):
    emo, verb, _ = ACTIONS[n]
    return (f"{emo} **{verb}**\n\nJust hit **Submit new issue** and a bot does the rest. "
            f"{NAME} will react on the egg in about 30 seconds.\n\n_(please don't edit the title)_")


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
    return (f'<a href="{PROFILE}"><img src="https://raw.githubusercontent.com/{REPO}/__SHA__/egg/top.svg" width="240" alt="{NAME}"></a>\n\n'
            f"**[← back to the egg]({PROFILE})** · "
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
    extra = f"\n\n⭐ **Level up!** {NAME} is level {level(st)} now." if level(st) > lv else ""
    if was == "rust":
        extra = f"\n\n🦀 **You rescued {NAME}!** She was halfway through rewriting everything in Rust."
    elif was == "grumpy":
        extra = f"\n\n🌤️ {NAME} was feeling neglected. You cheered her up."
    if st.get("seen_stage") != stage(st)[2]:
        if st.get("seen_stage"):
            extra += f"\n\n🎉 **{NAME} grew up!** She's a **{stage(st)[1]}** now, and you're the first to see it."
        st["seen_stage"] = stage(st)[2]
        save(st)
    return f"{emo} **{NAME} {did}!** {change}.{extra}\n\n{hi}\n\n" + footer(st)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "render":
        render(load())
    elif cmd == "tick":
        tick()
    else:
        print(act(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""))
