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

# Everything is drawn in the approved mockup's pixel space (1254x1254). art/ holds the shell and
# Byte's frames cut from the kit by scripts/build_art.py; the bot only base64s them, no Pillow needed.
ART = ROOT / "art"
CROP = (118, 0, 1020, 1242)
ROW1, ROW2, COL1, COL2 = 870, 1098, 511, 745
LCDBOX = (338, 398, 577, 442)
HEAD_Y, FIELD_Y, FLOOR, FOOT_Y = 398, 490, 716, 740
CX = 627
BTNS = {"coffee": (306, 876, 190, 168), "nap": (528, 876, 198, 168), "debug": (757, 876, 189, 168)}
SCALE = 1 / 3
INK, HEAD, FIELD, GRID, FLOORC = "#1c1c3a", "#262743", "#c7e4f8", "#bcdcf3", "#8aa9dc"
XPON, XPOFF, BAR = "#d18efa", "#4f447a", "#312e56"
GREENS = ["#3a3d5c", "#0e4429", "#006d32", "#26a641", "#69dc7e"]
FONT = "dgpx," + "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SHEET = {"BABY": "baby", "TODDLER": "toddler", "KID": "child", "TEEN": "teen", "ADULT": "adult", "ELDER": "elder"}
# seconds per loop; frames step through it evenly
SPEED = {"idle": 2.4, "code": .9, "nap": 2.6, "eat": 1.4, "happy": 1.2, "sad": 2.4}

PAL = {"k": "#1c1c3a", "r": "#e5484d", "o": "#f26b2a", "w": "#ffffff", "c": "#fc74ac", "g": "#7ee0d4"}
BUGC = [".k.k.", "krrrk", "rrkrr", "krrrk", ".r.r."]
CRABC = ["o.......o", "oo.....oo", ".ooooooo.", "ookoookoo", "ooooooooo", "o.o...o.o"]
HEART = [".cc.cc.", "ccccccc", "ccccccc", ".ccccc.", "..ccc..", "...c..."]
BRANCH = ["g...g", "g...g", "g..g.", "g.g..", "gg...", "g....", "g...."]
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
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{FONT}" font-weight="700" '
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
    """Byte's animation frames, stacked; CSS shows one at a time. Feet sit on the floor line."""
    sheet, a = SHEET[stage(st)[2]], anim(st)
    fr = frames(sheet, a)
    tall = max(f[1] + f[3] for f in fr) - min(f[1] for f in fr)
    s = min(3.0, 222 / tall)
    bottom = max(f[1] + f[3] for f in fr)
    n, dur = len(fr), SPEED[a]
    out = []
    for i, (bx, by, w, h) in enumerate(fr):
        x, y = CX - w * s / 2, FLOOR - (bottom - by) * s
        style = f' class="fr fr{i}" style="animation:k{n} {dur}s steps(1) {-dur * ((n - i) % n) / n:.2f}s infinite"' if n > 1 else ""
        out.append(img(f"girl/{sheet}-{a}-{i}.png", round(x, 1), round(y, 1), round(w * s, 1), round(h * s, 1), style))
    return "".join(out)


def squares(st):
    """the last 30 days of care as a tiny contribution graph."""
    days = st.get("days", {})
    out = []
    for i in range(30):
        d = date.fromordinal(date.today().toordinal() - 29 + i).isoformat()
        n = days.get(d, 0)
        lvl = 0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3 if n <= 6 else 4
        out.append(f'<rect x="{438 + (i // 3) * 13}" y="{424 + (i % 3) * 13}" width="11" height="11" fill="{GREENS[lvl]}"/>')
    return "".join(out)


def lcd(st):
    """the live screen. independent groups: #status #props #character #pop #stats."""
    act, cond, abbr = recent(st), condition(st), stage(st)[2]
    jit = st.get("jitter", 0) >= JITTERY
    lx, ly, lw, lh = LCDBOX
    hearts = "".join(cpx(HEART, 802 + i * 34, 432, 4, tint=None if i < mood(st) else XPOFF) for i in range(3))
    status = (f'<rect x="{lx}" y="{HEAD_Y}" width="{lw}" height="{FIELD_Y - HEAD_Y}" fill="{HEAD}"/>'
              + img("octo.png", 356, 412, 66, 64) + squares(st)
              + cpx(BRANCH, 586, 430, 4) + t(612, 456, f"{abbr} D{day(st)}", 19, "#e9e6ff") + hearts)
    props = img("cat.png", 352, FLOOR - 78, 142, 78)
    if act != "nap":
        props += img("mug.png", 790, FLOOR - 156, 95, 156, ' class="steam"' if act == "coffee" else "")
    pop = ""
    if act == "coffee":
        pop = "ZING!" if jit else "+2 NRG"
    elif act == "nap":
        props += "".join(t(800 + dx, dy, z, fs, "#8f6cf2", extra=' class="zz"') for dx, dy, fs, z in
                         ((0, 700, 28, "z"), (26, 660, 36, "Z"), (56, 612, 46, "Z")))
        pop = "+3 REST"
    elif act == "debug":
        pop = "FIXED!" if st["bugs"] == 0 else "-1 BUG"
    elif cond == "rust":
        props += cpx(CRABC, 760, FLOOR - 42, 7, ' class="bug"')
        pop = "IN RUST"
    elif cond == "grumpy":
        pop = "UGH"
    elif jit:
        pop = "!!"
    for i, (bx, by) in enumerate([(366, 512), (862, 512), (470, 560)][:st["bugs"]]):
        props += cpx(BUGC, bx, by, 8, ' class="bug"')
    poptxt = ""
    if pop:
        w = len(pop) * 17 + 24
        poptxt = (f'<g class="pop"><rect x="{CX + 70}" y="506" width="{w}" height="40" fill="#fff" stroke="{INK}" stroke-width="5"/>'
                  + t(CX + 70 + w / 2, 535, pop, 22, INK, "middle") + "</g>")
    x, lv = xp(st), level(st)
    filled = (x % 100) * 16 // 100
    segs = "".join(f'<rect x="{438 + i * 24.5}" y="782" width="21" height="16" fill="{XPON if i < filled else XPOFF}"/>' for i in range(16))
    word = ("JITTERY" if jit else {"rust": "RUSTY", "grumpy": "GRUMPY"}.get(cond) or ["", "MEH", "OK", "HAPPY"][mood(st)])
    stats = (t(366, 766, f"LVL {lv}", 24) + t(470, 766, f"XP {x:,}", 24) + t(890, 766, f"ENERGY {st['energy']}/10", 24, INK, "end")
             + f'<rect x="430" y="775" width="400" height="30" fill="{BAR}"/>' + segs
             + t(366, 830, f"REST {st['rest']}/10  BUGS {st['bugs']}", 17, "#4a4a7a")
             + t(890, 830, word, 17, "#b8336a", "end"))
    night = f'<rect x="{lx}" y="{FIELD_Y}" width="{lw}" height="{FLOOR - FIELD_Y}" fill="#3a2a6a" opacity=".22"/>' if act == "nap" else ""
    return (f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" fill="{FIELD}"/>'
            f'<rect x="{lx}" y="{FIELD_Y}" width="{lw}" height="{FLOOR - FIELD_Y}" fill="url(#grid)"/>'
            f'<rect x="{lx}" y="{FLOOR}" width="{lw}" height="5" fill="{FLOORC}"/>'
            f'{night}<g id="status">{status}</g><g id="props">{props}</g>'
            f'<g id="character"><g class="{"jit" if jit and act != "nap" else "bob"}">{girl(st)}</g></g>'
            f'<g id="pop">{poptxt}</g><g id="stats">{stats}</g>')


GRIDDEF = ('<pattern id="grid" width="9" height="9" patternUnits="userSpaceOnUse">'
           f'<rect width="9" height="9" fill="{FIELD}"/><rect width="7" height="7" fill="{GRID}"/></pattern>')
CSS = ("@keyframes k2{0%,49.9%{opacity:1}50%,100%{opacity:0}}@keyframes k3{0%,33.2%{opacity:1}33.3%,100%{opacity:0}}"
       "@keyframes w{0%,49%{transform:translateX(0)}50%,100%{transform:translateX(6px)}}.bug{animation:w .8s steps(1) infinite}"
       "@keyframes bob{0%,49%{transform:translateY(0)}50%,100%{transform:translateY(-4px)}}.bob{animation:bob 1.6s steps(1) infinite}"
       "@keyframes jit{0%,32%{transform:translateX(-4px)}33%,65%{transform:translateX(4px)}66%,100%{transform:translateX(0)}}"
       ".jit{animation:jit .3s steps(1) infinite}"
       "@keyframes up{0%{transform:translateY(10px);opacity:0}15%,75%{transform:translateY(0);opacity:1}100%{transform:translateY(-6px);opacity:0}}"
       ".pop{animation:up 3s steps(6) infinite}"
       "@keyframes zz{0%{transform:translateY(8px);opacity:0}30%,70%{opacity:1}100%{transform:translateY(-16px);opacity:0}}"
       ".zz{animation:zz 2.4s steps(6) infinite}.zz:nth-of-type(2){animation-delay:.6s}.zz:nth-of-type(3){animation-delay:1.2s}"
       "@keyframes st{0%,49%{transform:translateY(0)}50%,100%{transform:translateY(-4px)}}.steam{animation:st 1s steps(1) infinite}"
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
