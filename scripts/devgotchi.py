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
She grows up from a baby to a teen with headphones to a wise elder dev, and after {RETIRE_DAY} days a new egg hatches. Neglect her and she starts rewriting everything in Rust.

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
    return (f'<a href="{PROFILE}"><img src="https://raw.githubusercontent.com/{REPO}/__SHA__/egg/top.svg" width="240" alt="{describe(st)}"></a>\n\n'
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
    return f"{emo} **{NAME} {did}!** {change}.{extra}\n\n{hi}\n\n" + footer(st)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "render":
        render(load())
    elif cmd == "tick":
        tick()
    else:
        print(act(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""))
