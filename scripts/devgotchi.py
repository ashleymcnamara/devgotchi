"""devgotchi: a tiny pixel developer the community raises through GitHub issues.

usage:
  python3 scripts/devgotchi.py render
  python3 scripts/devgotchi.py tick                     # hourly-ish decay, run by cron
  python3 scripts/devgotchi.py act "<title>" "<login>" "<account created_at>"   # prints the bot comment
"""
import json, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
EGG_DIR = ROOT / "egg"
REPO = "ashleymcnamara/devgotchi"
PROFILE = "https://github.com/ashleymcnamara"
OWNER = "ashleymcnamara"
COOLDOWN_HOURS, MIN_ACCOUNT_DAYS = 1, 7
NAME = "Byte"

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
INK, YELLOW, PINK, SHADOW = "#1a0f2e", "#ffd479", "#f7a8c4", "#b8336a"
CREAM, LCD, LCDK = "#fffaf0", "#efeaff", "#3b2a63"
W, H, TOP, MID = 300, 384, 262, 330
EGG = "M150 16 C 224 16, 288 132, 288 236 C 288 324, 228 368, 150 368 C 72 368, 12 324, 12 236 C 12 132, 76 16, 150 16 Z"
LX, LY, LW, LH, P = 78, 124, 144, 104, 4

BUG = ["k...k", ".kkk.", "kkkkk", ".kkk.", "k...k"]
CUP = [".k.k..", "..k.k.", "kkkkk.", "kkkkkk", "kkkk.k", "kkkkk.", ".kkk.."]
SPLAT = ["k.k.k", ".k.k.", "kk.kk", ".k.k.", "k.k.k"]
ICONS = {"coffee": [".k.k.", "kkkk.", "kkk.k", "kkkk.", ".kk.."],
         "nap": [".kkk.", "kk...", "k....", "kk...", ".kkk."],
         "debug": BUG,
         "love": [".k.k.", "kkkkk", "kkkkk", ".kkk.", "..k.."]}
BUTTONS = [("coffee", 86), ("nap", 150), ("debug", 214)]
BY = 288
ACTIONS = {
    "coffee": ("☕", "Pour Byte a coffee", "drank your coffee"),
    "nap": ("💤", "Send Byte to bed", "took a power nap"),
    "debug": ("🐛", "Help Byte squash a bug", "squashed a bug with you"),
}


def px(rows, x0, y0, s, fill, cls=""):
    r = "".join(f'<rect x="{x0 + x * s}" y="{y0 + y * s}" width="{s}" height="{s}" fill="{fill}"/>'
                for y, row in enumerate(rows) for x, c in enumerate(row) if c == "k")
    return f'<g{cls}>{r}</g>'


def txt(x, y, s, size=8, anchor="start", cls=""):
    return (f'<text{cls} x="{x}" y="{y}" text-anchor="{anchor}" font-family="{MONO}" font-weight="800" '
            f'font-size="{size}" fill="{LCDK}" letter-spacing=".5">{s}</text>')


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
        ".khhkssssssssssk hk.".replace(" ", "h"),
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
SP = 3


def cpx(rows, x0, y0, s, cls="", tint=None):
    r = "".join(f'<rect x="{x0 + x * s}" y="{y0 + y * s}" width="{s}" height="{s}" fill="{tint or PAL[c]}"/>'
                for y, row in enumerate(rows) for x, c in enumerate(row) if c in PAL)
    return f'<g{cls}>{r}</g>'


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


def sprite(st, closed=False):
    """returns (rows, x_offset_in_pixels) for Byte at her current stage."""
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


def screen(st):
    last = st.get("last") or {}
    act = last.get("action") if hours_since(last.get("at")) < REACT_HOURS else None
    cond, abbr = condition(st), stage(st)[2]
    awake, shut = sprite(st), sprite(st, closed=True)
    sp = 4 if abbr == "BABY" else SP
    w, h = len(awake[0]) * sp, len(awake) * sp
    sx, sy = LX + (LW - w) // 2 - 6, LY + 82 - h
    if act == "nap":
        pet = cpx(shut, sx, sy, sp)
    else:
        pet = cpx(awake, sx, sy, sp, ' class="fa"') + cpx(shut, sx, sy, sp, ' class="fb"')
    prop, pop, stat = "", "", f"{abbr} · DAY {day(st)}"
    right = sx + w + 4
    if abbr == "TODDLER" and not act:
        prop += cpx(CAT, right, LY + 68, 3)
    if abbr in ("KID", "ADULT") and not act:
        prop += cpx(LAPTOP, right, LY + 64, 3)
    if act == "coffee":
        prop, pop, stat = cpx(MUG, right, LY + 58, 3), "+2", f"ENERGY {st['energy']}/10"
    elif act == "nap":
        prop = "".join(f'<text x="{right + dx}" y="{LY + dy}" font-family="{MONO}" font-weight="800" font-size="{fs}" fill="{PAL["p"]}">{z}</text>'
                       for dx, dy, fs, z in ((0, 82, 10, "z"), (9, 70, 13, "Z"), (18, 56, 16, "Z")))
        pop, stat = "+3", f"REST {st['rest']}/10"
    elif act == "debug":
        prop, pop, stat = cpx(SPLATC, right + 2, LY + 66, 4), "OK!", f"BUGS {st['bugs']}"
    elif cond == "rust":
        prop = cpx(CRABC, right, LY + 68, 3, ' class="bug"')
        pop, stat = ".rs", "REWRITING IN RUST"
    elif cond == "grumpy":
        pop, stat = "ugh", "GRUMPY"
    if st["bugs"]:
        prop += cpx(BUGC, LX + 8, LY + 70, 3, ' class="bug"')
    if st["bugs"] >= 3:
        prop += cpx(BUGC, LX + 12, LY + 40, 3)
    poptxt = txt(right + 14, LY + (30 if act == "nap" else 40), pop, 10, "middle", ' class="pop"') if pop else ""
    hearts = "".join(cpx(HEART, LX + LW - 40 + i * 12, LY + 6, 2, tint=None if i < mood(st) else "#d8cff5")
                     for i in range(3))
    status = (f'<rect x="{LX + 4}" y="{LY + LH - 17}" width="{LW - 8}" height="1" fill="{LCDK}" opacity=".25"/>'
              + txt(LX + 8, LY + LH - 6, NAME.upper()) + txt(LX + LW - 8, LY + LH - 6, stat, anchor="end"))
    return hearts + pet + prop + poptxt + status


def body(st):
    ghost = "".join(f'<rect x="{LX + x * P}" y="{LY + y * P}" width="{P - 1}" height="{P - 1}" fill="{LCDK}" opacity=".06"/>'
                    for x in range(LW // P) for y in range(LH // P))
    icons = "".join(px(ic, 92 + i * 34, 108, 2, INK) for i, ic in enumerate(ICONS.values()))
    btns = "".join(
        f'<ellipse cx="{x}" cy="{BY + 2}" rx="21" ry="20" fill="{SHADOW}" opacity=".28"/>'
        f'<circle cx="{x}" cy="{BY + 4}" r="15" fill="{SHADOW}"/>'
        f'<circle cx="{x}" cy="{BY}" r="15" fill="{YELLOW}" stroke="{INK}" stroke-width="2.5"/>'
        f'<path d="M{x - 9} {BY - 3} a 10 10 0 0 1 9 -8" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".75"/>'
        f'<text x="{x}" y="{BY + 34}" text-anchor="middle" font-family="{MONO}" font-weight="800" font-size="9" '
        f'fill="{SHADOW}" letter-spacing="1.5">{n.upper()}</text>'
        for n, x in BUTTONS)
    grille = "".join(f'<circle cx="{150 + dx}" cy="350" r="2.2" fill="{SHADOW}" opacity=".55"/>' for dx in (-20, -10, 0, 10, 20))
    bevel = 'transform="translate(150 200) scale(.93 .94) translate(-150 -200)"'
    return (f'<rect x="139" y="5" width="22" height="16" rx="6" fill="{SHADOW}" stroke="{INK}" stroke-width="2.5"/>'
            f'<rect x="146" y="9" width="8" height="4" rx="2" fill="{INK}" opacity=".55"/>'
            f'<path d="{EGG}" transform="translate(0 7)" fill="{SHADOW}"/>'
            f'<path d="{EGG}" fill="{PINK}" stroke="{INK}" stroke-width="4"/>'
            f'<path d="{EGG}" {bevel} fill="none" stroke="#fff" stroke-width="2" opacity=".45"/>'
            f'<path d="M58 150 C 62 98, 92 52, 128 38" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity=".5"/>'
            f'<circle cx="138" cy="34" r="3.5" fill="#fff" opacity=".6"/>'
            f'<text x="150" y="84" text-anchor="middle" font-family="{MONO}" font-weight="800" font-size="17" fill="{INK}" letter-spacing="1">devgotchi</text>'
            f'<rect x="62" y="96" width="176" height="148" rx="26" fill="{CREAM}" stroke="{INK}" stroke-width="3"/>'
            + icons + f'<path d="M97 101 l4 4 l4 -4 z" fill="{SHADOW}"/>'
            + f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" rx="6" fill="{LCD}" stroke="{INK}" stroke-width="2"/>'
            + ghost + screen(st) + btns + grille)


CSS = ("@keyframes a{0%,49%{opacity:1}50%,100%{opacity:0}}@keyframes b{0%,49%{opacity:0}50%,100%{opacity:1}}"
       ".fa{animation:a 1.2s steps(1) infinite}.fb{animation:b 1.2s steps(1) infinite}"
       "@keyframes w{0%,49%{transform:translateX(0)}50%,100%{transform:translateX(4px)}}.bug{animation:w .8s steps(1) infinite}"
       "@keyframes up{0%{transform:translateY(6px);opacity:0}20%,70%{opacity:1}100%{transform:translateY(-10px);opacity:0}}"
       ".pop{animation:up 1.8s ease-out infinite}")


def slice_svg(st, x, y, w, h, title, css=""):
    reduce = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{title}"><title>{title}</title><style>{css}{reduce}</style>{body(st)}</svg>\n')


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


def render(st):
    EGG_DIR.mkdir(exist_ok=True)
    (EGG_DIR / "top.svg").write_text(slice_svg(st, 0, 0, W, TOP, f"devgotchi: {NAME}, a tiny pixel developer raised by the community. {stage(st)[1].capitalize()}, day {day(st)}.", CSS))
    for i, (n, _) in enumerate(BUTTONS):
        (EGG_DIR / f"btn-{n}.svg").write_text(slice_svg(st, i * 100, TOP, 100, MID - TOP, f"{n} button"))
    (EGG_DIR / "bottom.svg").write_text(slice_svg(st, 0, MID, W, H - MID, "devgotchi speaker grille"))
    v = int(time.time())
    btns = "".join(
        f'<a href="{issue_url(n)}">'
        f'<img src="egg/btn-{n}.svg?v={v}" width="100" align="top" alt="{n}"></a>' for n, _ in BUTTONS)
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

{NAME} is a tiny pixel developer the community raises together. Press a button, hit **Submit**, and she reacts here in about 30 seconds.<br>
She grows up from a baby to a teen with headphones to a wise elder dev. Neglect her and she starts rewriting everything in Rust.

<img src="egg/top.svg?v={v}" width="300" align="top" alt="{NAME}"><br>{btns}<br><img src="egg/bottom.svg?v={v}" width="300" align="top" alt="">

<sub>{" · ".join(line)}</sub>

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
    if st["ticks"] % 2 == 0:
        st["bugs"] = min(5, st["bugs"] + 1)
    save(st)


def footer(st):
    return (f'<a href="{PROFILE}"><img src="https://raw.githubusercontent.com/{REPO}/__SHA__/egg/top.svg" width="240" alt="{NAME}"></a>\n\n'
            f"**[← back to the egg]({PROFILE})** · "
            f"<sub>{NAME} is a {stage(st)[1]}, day {day(st)} · {plural(len(st['users']), 'caretaker')} so far</sub>")


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

    was = condition(st)
    before = dict(st)
    if a == "coffee":
        st["energy"] = min(10, st["energy"] + 2)
        st["rest"] = max(0, st["rest"] - 1)
    elif a == "nap":
        st["rest"] = min(10, st["rest"] + 3)
        st["energy"] = max(0, st["energy"] - 1)
    else:
        st["bugs"] = max(0, st["bugs"] - 1)
        st["energy"] = max(0, st["energy"] - 1)
    st["total"] += 1
    if st["total"] % 4 == 0 and a != "debug":
        st["bugs"] = min(5, st["bugs"] + 1)
    today = date.today().isoformat()
    first = u is None
    if first:
        u = {"count": 0, "first": today, "last_day": None, "streak": 0}
    if u["last_day"] != today:
        yday = date.fromordinal(date.today().toordinal() - 1).isoformat()
        u["streak"] = u["streak"] + 1 if u["last_day"] == yday else 1
    stamp = now().isoformat(timespec="seconds")
    u.update(count=u["count"] + 1, last_day=today, at=stamp)
    st["users"][user] = u
    st["last"] = {"action": a, "user": user, "at": stamp}
    st["last_care"] = stamp
    save(st)

    emo, _, did = ACTIONS[a]
    change = {"coffee": f"Energy {before['energy']} → {st['energy']}",
              "nap": f"Rest {before['rest']} → {st['rest']}",
              "debug": f"Bugs {before['bugs']} → {st['bugs']}"}[a]
    if first:
        hi = f"Hi @{user}, you're caretaker **no. {len(st['users'])}**! 💖"
    else:
        streak = f" · 🔥 **{u['streak']}-day streak**" if u["streak"] > 1 else ""
        n = u["count"]
        suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        hi = f"Welcome back @{user}, that's your **{n}{suf} visit**{streak}."
    extra = ""
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
