"""devgotchi: a tiny pixel developer the community raises through GitHub issues.

usage:
  python3 scripts/devgotchi.py render
  python3 scripts/devgotchi.py act "<issue title>" "<login>"   # prints the bot comment
"""
import json, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
EGG_DIR = ROOT / "egg"
REPO = "ashleymcnamara/devgotchi-lab"
NAME = "Byte"

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
INK, YELLOW, PINK, SHADOW = "#1a0f2e", "#ffd479", "#f7a8c4", "#b8336a"
CREAM, LCD, LCDK = "#fffaf0", "#c3cf9f", "#26301c"
W, H, TOP, MID = 300, 384, 262, 330
EGG = "M150 16 C 224 16, 288 132, 288 236 C 288 324, 228 368, 150 368 C 72 368, 12 324, 12 236 C 12 132, 76 16, 150 16 Z"
LX, LY, LW, LH, P = 78, 124, 144, 104, 4

PET = ["....kkkkk..kk",
       "..kkkkkkkkkkk",
       ".kkkkkkkkkkk.",
       ".kkk.....kkk.",
       ".kk.......kk.",
       ".kk.k...k.kk.",
       ".kk.k...k.kk.",
       ".kk.......kk.",
       ".kk..kkk..kk.",
       ".kkk.....kkk.",
       ".kk.kkkkk.kk.",
       ".kk...k...kk.",
       "..kkkkkkkkk..",
       ".kkkk...kkkk.",
       "k.kkkkkkkkk.k",
       "..kkkkkkkkk..",
       "...kk...kk..."]
BLINK = PET[:5] + [".kk.......kk.", ".kk.kk.kk.kk."] + PET[7:]
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


def mood(st):
    avg = (st["energy"] + st["rest"] + max(0, 10 - 3 * st["bugs"])) / 3
    return 3 if avg >= 7 else 2 if avg >= 4 else 1


def screen(st):
    last = (st.get("last") or {}).get("action")
    sx, sy = LX + 11 * P, LY + 3 * P
    if last == "nap":
        sleepy = [r if i not in (5, 6) else BLINK[i] for i, r in enumerate(PET)]
        pet = px(sleepy, sx, sy, P, LCDK)
    else:
        pet = px(PET, sx, sy, P, LCDK, ' class="fa"') + px(BLINK, sx + P, sy, P, LCDK, ' class="fb"')
    prop, pop, stat = "", "", f"JR · DAY {day(st)}"
    if last == "coffee":
        prop, pop, stat = px(CUP, 184, 176, 4, LCDK), "+2", f"ENERGY {st['energy']}/10"
    elif last == "nap":
        prop = txt(184, 206, "z", 10) + txt(194, 194, "Z", 13) + txt(204, 180, "Z", 16)
        pop, stat = "+3", f"REST {st['rest']}/10"
    elif last == "debug":
        prop, pop, stat = px(SPLAT, 190, 184, 4, LCDK), "OK!", f"BUGS {st['bugs']}"
    if st["bugs"]:
        prop += px(BUG, LX + 3 * P, LY + 15 * P, P, LCDK, ' class="bug"')
    popy = 150 if last == "nap" else 166
    poptxt = txt(198, popy, pop, 10, "middle", ' class="pop"') if pop else ""
    hearts = "".join(px(ICONS["love"], LX + LW - 44 + i * 13, LY + 5, 2, LCDK if i < mood(st) else "#9aa67a")
                     for i in range(3))
    status = (f'<rect x="{LX + 4}" y="{LY + LH - 17}" width="{LW - 8}" height="1" fill="{LCDK}" opacity=".35"/>'
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


def render(st):
    EGG_DIR.mkdir(exist_ok=True)
    (EGG_DIR / "top.svg").write_text(slice_svg(st, 0, 0, W, TOP, f"devgotchi: {NAME}, a tiny pixel developer raised by the community. Junior dev, day {day(st)}.", CSS))
    for i, (n, _) in enumerate(BUTTONS):
        (EGG_DIR / f"btn-{n}.svg").write_text(slice_svg(st, i * 100, TOP, 100, MID - TOP, f"{n} button"))
    (EGG_DIR / "bottom.svg").write_text(slice_svg(st, 0, MID, W, H - MID, "devgotchi speaker grille"))
    v = int(time.time())
    btns = "".join(
        f'<a href="https://github.com/{REPO}/issues/new?title={quote("pet|" + n)}&body={quote(issue_body(n))}">'
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

# 🥚 devgotchi lab

A tiny pixel developer the community raises together. Press a button, hit **Submit**, and {NAME} reacts here in about 30 seconds.

<img src="egg/top.svg?v={v}" width="300" align="top" alt="{NAME}"><br>{btns}<br><img src="egg/bottom.svg?v={v}" width="300" align="top" alt="">

<sub>{" · ".join(line)}</sub>

</div>
""")


def issue_body(n):
    emo, verb, _ = ACTIONS[n]
    return (f"{emo} **{verb}**\n\nJust hit **Submit new issue** and a bot does the rest. "
            f"{NAME} will react on the egg in about 30 seconds.\n\n_(please don't edit the title)_")


def act(title, user):
    st = json.loads(STATE.read_text())
    a = title.strip().lower().removeprefix("pet|").strip()
    if a not in ACTIONS:
        return f"🥚 {NAME} didn't understand `{title[:40]}`. Try one of the buttons on the egg!"
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
    u = st["users"].get(user)
    first = u is None
    if first:
        u = {"count": 0, "first": today, "last_day": None, "streak": 0}
    if u["last_day"] != today:
        yday = date.fromordinal(date.today().toordinal() - 1).isoformat()
        u["streak"] = u["streak"] + 1 if u["last_day"] == yday else 1
    u["count"] += 1
    u["last_day"] = today
    st["users"][user] = u
    st["last"] = {"action": a, "user": user, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    STATE.write_text(json.dumps(st, indent=2) + "\n")
    render(st)

    emo, _, did = ACTIONS[a]
    change = {"coffee": f"Energy {before['energy']} → {st['energy']}",
              "nap": f"Rest {before['rest']} → {st['rest']}",
              "debug": f"Bugs {before['bugs']} → {st['bugs']}"}[a]
    if first:
        hi = f"Hi @{user}, you're caretaker **#{len(st['users'])}**! 💖"
    else:
        streak = f" · 🔥 **{u['streak']}-day streak**" if u["streak"] > 1 else ""
        hi = f"Welcome back @{user}, that's visit **#{u['count']}**{streak}."
    return (f"{emo} **{NAME} {did}!** {change}.\n\n{hi}\n\n"
            f"<sub>{NAME} is a junior dev, day {day(st)} · {plural(len(st['users']), 'caretaker')} so far · "
            f"[go see her →](https://github.com/{REPO})</sub>")


if __name__ == "__main__":
    if sys.argv[1] == "render":
        render(json.loads(STATE.read_text()))
    else:
        print(act(sys.argv[2], sys.argv[3]))
