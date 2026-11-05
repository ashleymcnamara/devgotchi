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
FONT = "dgpx," + "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

PAL = {"k": "#2a1b3d", "h": "#7a4526", "H": "#a8673a", "s": "#f9d2b0", "c": "#f49ab0", "w": "#ffffff",
       "p": "#8f6cf2", "P": "#6449c9", "l": "#c6b6ff", "m": "#c04cf0", "g": "#d9d4e6", "G": "#a69fba",
       "r": "#e5484d", "o": "#f26b2a", "b": "#7b4a2a"}
GIRL = ["........kkkk........",
        ".......khhhhk.......",
        ".......khhHhk.......",
        "......kkhhhhkk......",
        "....kkhhhhhhhhkk....",
        "...khhhHHhhhhhhhk...",
        "..khhHhhhhhhhhhhhk..",
        ".khhhhhhhhhhhhhhhhk.",
        ".khhhhhhhhhhhhhhhhk.",
        ".khhshhsshhsshhshhk.",
        ".khhsssssssssssshhk.",
        ".khhsswksssswksshhk.",
        ".khhsskksssskksshhk.",
        ".khhscssskkssscshhk.",
        ".khhksssssssssskhhk.",
        ".khhhhkkkkkkkkhhhhk.",
        "..khhkppwsswppkhhk..",
        "...kkpppwppwpppkk...",
        "...kppppwppwppppk...",
        "..ksppppppppppppsk..",
        "...kpppppPPpppppk...",
        "....kkkkkkkkkkkk....",
        "....kPPk....kPPk....",
        "....kkkk....kkkk...."]
BABY = ["................",
        ".....kkkkkk.....",
        "....khhHhhhk....",
        "...khhhhhhhhk...",
        "..khhhhhhhhhhk..",
        "..khsssssssshk..",
        "..kssssssssssk..",
        "..kswksssswksk..",
        "..kskksssskksk..",
        "..kcssskksssck..",
        "..kppkkkkkkppk..",
        ".kppppllppppppk.",
        ".kppplllpppppPk.",
        ".kpppppppppPPPk.",
        "..kPPpppppPPPk..",
        "...kkkkkkkkkk..."]
CAT = ["k.....k", "kk...kk", "kwwwwwk", "kwkwkwk", "kwwcwwk", ".kkkkk."]
LAPTOP = ["kkkkkkkk.", "kllllllk.", "kllwwllk.", "kllllllk.", "kkkkkkkkk", "kPPPPPPPk", "kkkkkkkkk"]
MUG = [".w.w...", "..w.w..", "kkkkk..", "kbbbkk.", "kwwwk.k", "kwwwkk.", ".kkk..."]
BUGC = [".k.k.", "krrrk", "rrkrr", "krrrk", ".r.r."]
SPLATC = ["r.r.r", ".rwr.", "rwwwr", ".rwr.", "r.r.r"]
CRABC = ["o.......o", "oo.....oo", ".ooooooo.", "ookoookoo", "ooooooooo", "o.o...o.o"]
HEART = [".c.c.", "ccccc", "ccccc", ".ccc.", "..c.."]
STAGES = [(0, "baby", "BABY"), (1, "toddler", "TODDLER"), (3, "kid", "KID"), (7, "teen", "TEEN"),
          (14, "grown-up dev", "ADULT"), (30, "wise elder dev", "ELDER")]
REACT_HOURS, GRUMPY_HOURS, RUST_HOURS = 6, 24, 48


def cpx(rows, x0, y0, s, cls="", tint=None):
    r = "".join(f'<rect x="{x0 + x * s}" y="{y0 + y * s}" width="{s}" height="{s}" fill="{tint or PAL[c]}"/>'
                for y, row in enumerate(rows) for x, c in enumerate(row) if c in PAL)
    return f'<g{cls}>{r}</g>'


_uri = {}


def uri(name):
    if name not in _uri:
        mime = "font/ttf" if name.endswith(".ttf") else "image/png"
        _uri[name] = f"data:{mime};base64," + base64.b64encode((ART / name).read_bytes()).decode()
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


def txt(x, y, s, size=7, anchor="start", fill=LCDK, extra=""):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{FONT}" font-weight="700" '
            f'font-size="{size}" fill="{fill}"{extra}>{s}</text>')


def xp(st):
    return st.get("xp", st["total"] * 5)


def level(st):
    return 1 + xp(st) // 100


def recent(st):
    last = st.get("last") or {}
    return last.get("action") if hours_since(last.get("at")) < REACT_HOURS else None


def sprite(st, closed=False):
    """Byte at her current stage, as rows of palette letters."""
    abbr, cond = stage(st)[2], condition(st)
    if abbr == "BABY":
        rows = [list(r) for r in BABY]
        if closed:
            rows[7] = list("..kssssssssssk..")
        return ["".join(r) for r in rows]
    g = [list(r) for r in GIRL]
    if closed:
        g[11] = list(".khhsssssssssssshhk.")
        g[12] = list(".khhskksssssskkshhk.")
    if cond != "ok":
        g[13] = list(".khhscsskkkksscshhk.")
        g[10] = list(".khhskksssssskkshhk.")
    if abbr in ("ADULT", "ELDER"):
        for x in (5, 6, 7, 8, 11, 12, 13, 14):
            g[10][x] = "k"
        for y in (11, 12):
            g[y][5] = g[y][8] = g[y][11] = g[y][14] = "k"
        g[11][9] = g[11][10] = "k"
    if abbr == "TEEN":
        for x in range(6, 14):
            g[4][x] = "m"
        g[5][3] = g[6][2] = g[5][16] = g[6][17] = "m"
        for y in range(7, 10):
            g[y][1] = g[y][18] = "m"
        for y in range(10, 14):
            g[y][0], g[y][1], g[y][2] = "k", "m", "m"
            g[y][17], g[y][18], g[y][19] = "m", "m", "k"
    if abbr == "ELDER":
        g = [[{"h": "g", "H": "G"}.get(c, c) for c in r] for r in g]
    if abbr == "TODDLER":
        g = g[:16] + [list("..khhkppwsswppkhhk.."), list("...kkpppwppwpppkk..."),
                      list("..ksppppppppppppsk.."), list("....kkkkkkkkkkkk...."), list("....kPPk....kPPk...."),
                      list("....kkkk....kkkk....")]
    return ["".join(r) for r in g]


def lcd(st):
    """the live screen. independent groups: #status #props #character #pop #stats."""
    act, cond, abbr = recent(st), condition(st), stage(st)[2]
    jit = st.get("jitter", 0) >= JITTERY
    lx, ly, lw, lh = LCDBOX
    oy = (lh / K - LH) / 2
    up = f'transform="translate({lx - LX * K} {ly + oy * K - LY * K}) scale({K})"'  # screen grid -> shell pixels

    def g(i, inner, cls=""):
        return f'<g id="{i}"{cls}><g {up}>{inner}</g></g>'

    awake, shut = sprite(st), sprite(st, closed=True)
    sp = 4 if abbr == "BABY" else 3
    w, h = len(awake[0]) * sp, len(awake) * sp
    sx, sy = LX + (LW - w) // 2 - 6, LY + 82 - h
    pet = (cpx(shut, sx, sy, sp) if act == "nap"
           else cpx(awake, sx, sy, sp, ' class="fa"') + cpx(shut, sx, sy, sp, ' class="fb"'))
    prop, pop, stat = "", "", f"{abbr} DAY {day(st)}"
    right = sx + w + 4
    if abbr == "TODDLER" and not act:
        prop += cpx(CAT, right, LY + 68, 3)
    if abbr in ("KID", "TEEN", "ADULT", "ELDER") and not act:
        prop += cpx(LAPTOP, right, LY + 64, 3)
    if act == "coffee":
        prop, pop, stat = cpx(MUG, right, LY + 58, 3), "ZING" if jit else "+2", f"ENERGY {st['energy']}/10"
    elif act == "nap":
        prop = "".join(txt(right + dx, LY + dy, z, fs, fill=PAL["p"], extra=' class="zz"')
                       for dx, dy, fs, z in ((0, 82, 9, "z"), (9, 70, 12, "Z"), (18, 56, 15, "Z")))
        pop, stat = "+3", f"REST {st['rest']}/10"
    elif act == "debug":
        prop, pop, stat = cpx(SPLATC, right + 2, LY + 66, 4), "OK!", f"BUGS {st['bugs']}"
    elif cond == "rust":
        prop = cpx(CRABC, right, LY + 68, 3, ' class="bug"')
        pop, stat = ".rs", "IN RUST"
    elif cond == "grumpy":
        pop, stat = "ugh", "GRUMPY"
    elif jit:
        pop, stat = "!!", "JITTERY"
    if st["bugs"]:
        prop += cpx(BUGC, LX + 8, LY + 70, 3, ' class="bug"')
    if st["bugs"] >= 3:
        prop += cpx(BUGC, LX + 12, LY + 40, 3)
    poptxt = txt(right + 14, LY + (30 if act == "nap" else 40), pop, 9, "middle", extra=' class="pop"') if pop else ""
    hearts = "".join(cpx(HEART, LX + LW - 40 + i * 12, LY + 6, 2, tint=None if i < mood(st) else OFF) for i in range(3))
    level_tag = txt(LX + 8, LY + 14, f"LV {level(st)}", 7)
    stats = (f'<rect x="{LX + 4}" y="{LY + LH - 17}" width="{LW - 8}" height="1" fill="{LCDK}" opacity=".25"/>'
             + txt(LX + 8, LY + LH - 6, NAME.upper()) + txt(LX + LW - 8, LY + LH - 6, stat, anchor="end"))
    return (f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" fill="{LCD}"/>'
            f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" fill="url(#grid)"/>'
            + g("status", hearts + level_tag) + g("props", prop)
            + g("character", f'<g class="{"jit" if jit and act != "nap" else ""}">{pet}</g>')
            + g("pop", poptxt) + g("stats", stats))


GRIDDEF = (f'<pattern id="grid" x="{LCDBOX[0]}" y="{LCDBOX[1]}" width="{K * 4}" height="{K * 4}" patternUnits="userSpaceOnUse">'
           f'<rect width="{K * 3}" height="{K * 3}" fill="{LCDK}" opacity=".06"/></pattern>')
CSS = ("@keyframes a{0%,49%{opacity:1}50%,100%{opacity:0}}@keyframes b{0%,49%{opacity:0}50%,100%{opacity:1}}"
       ".fa{animation:a 1.2s steps(1) infinite}.fb{animation:b 1.2s steps(1) infinite}"
       "@keyframes w{0%,49%{transform:translateX(0)}50%,100%{transform:translateX(2px)}}.bug{animation:w .8s steps(1) infinite}"
       "@keyframes jit{0%,32%{transform:translateX(-1px)}33%,65%{transform:translateX(1px)}66%,100%{transform:translateX(0)}}"
       ".jit{animation:jit .3s steps(1) infinite}"
       "@keyframes up{0%{transform:translateY(6px);opacity:0}20%,70%{opacity:1}100%{transform:translateY(-10px);opacity:0}}"
       ".pop{animation:up 1.8s steps(6) infinite}"
       "@keyframes zz{0%{transform:translateY(3px);opacity:0}30%,70%{opacity:1}100%{transform:translateY(-5px);opacity:0}}"
       ".zz{animation:zz 2.4s steps(6) infinite}.zz:nth-of-type(2){animation-delay:.6s}.zz:nth-of-type(3){animation-delay:1.2s}"
       "image{image-rendering:pixelated}"
       "@media (prefers-reduced-motion:reduce){*{animation:none!important}.fb{opacity:0}}")


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
