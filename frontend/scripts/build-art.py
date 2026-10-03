"""Draw the console's Bangladeshi scenes as SVG (public/art/*.svg).

Hand-built from layered silhouettes, so the art is ours, small, and works offline:

- sundarbans.svg  Mangrove forest at dusk, a Royal Bengal tiger on the bank, a nouka on the river
- paddy.svg       Paddy fields, palms and huts, a farmer with a water buffalo, egrets
- hills.svg       Chittagong Hill Tracts: misty ridges, the river below, a hilltop kyang
- padma.svg       The Padma at sunset: sail boats, a char, a river dolphin
- sidebar.svg     Mangrove silhouettes for the bottom of the navigation

Palm, egret, hut, deer and dolphin outlines come from game-icons.net (CC BY 3.0,
by Lorc and Delapouite), read from the @iconify-json/game-icons package if present:

    npm pack @iconify-json/game-icons && tar xzf iconify-json-game-icons-*.tgz
    python scripts/build-art.py package/icons.json
"""

import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from art_shapes import (  # noqa: E402
    BOAT,
    BOATMAN,
    BUFFALO,
    BUFFALO_HORN,
    BUFFALO_TAIL,
    FARMER,
    STUPA,
    TIGER,
    TIGER_STRIPES,
)

OUT = Path(__file__).resolve().parents[1] / "public" / "art"
W, H = 1600, 400
ICONS = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else None


def icon(name: str) -> tuple[str, int]:
    ic = ICONS["icons"][name]
    return ic["body"].replace('fill="currentColor"', ""), ic.get("width", ICONS.get("width", 512))


def place(body: str, x: float, y: float, size: float, box: int = 512, fill="#000", flip=False, opacity=1.0):
    """Put a 512-box icon with its bottom-centre at (x, y), `size` px tall."""
    k = size / box
    fx = -k if flip else k
    tx = x + (size / 2 if flip else -size / 2)
    return (
        f'<g transform="translate({tx:.1f} {y - size:.1f}) scale({fx:.4f} {k:.4f})" '
        f'fill="{fill}" opacity="{opacity}">{body}</g>'
    )


def shape(d: str, x: float, y: float, scale: float, fill: str, flip=False, extra=""):
    sx = -scale if flip else scale
    return f'<path d="{d}" transform="translate({x:.1f} {y:.1f}) scale({sx:.3f} {scale:.3f})" fill="{fill}" {extra}/>'


def ridge(seed: int, base: float, amp: float, waves=(1.0, 2.3, 5.1, 11.0), weights=(1, 0.5, 0.25, 0.1)):
    """A smooth skyline across the width, closed down to the bottom."""
    rnd = random.Random(seed)
    phases = [rnd.uniform(0, math.tau) for _ in waves]
    pts = []
    for i in range(0, W + 1, 8):
        t = i / W * math.tau
        y = base - amp * sum(w * math.sin(f * t + p) for f, w, p in zip(waves, weights, phases)) / sum(weights)
        pts.append((i, y))
    d = "M0 %d " % H + " ".join(f"L{x} {y:.1f}" for x, y in pts) + f" L{W} {H} Z"
    return d, pts


def canopy(seed: int, base: float, height: float, x0=0, x1=W, density=0.09, crowns=(10, 26), fill="#000", opacity=1.0, tall=0.15):
    """Mangrove canopy: a skyline traced over many round crowns, with a few tall sundari trees."""
    rnd = random.Random(seed)
    circles = []
    extra = []
    x = x0 - 30
    while x < x1 + 30:
        r = rnd.uniform(*crowns)
        top = base - height * rnd.uniform(0.25, 1.0)
        circles.append((x, top + r, r))
        if rnd.random() < tall:  # an emergent sundari: thin trunk, flat layered crown
            t = top - height * rnd.uniform(0.6, 1.3)
            extra.append(f'<rect x="{x - 1.5:.1f}" y="{t:.1f}" width="3" height="{base - t:.1f}"/>')
            for _ in range(3):
                extra.append(
                    f'<ellipse cx="{x + rnd.uniform(-r, r) * 0.6:.1f}" cy="{t + rnd.uniform(-3, 8):.1f}" '
                    f'rx="{r * rnd.uniform(0.7, 1.2):.1f}" ry="{r * rnd.uniform(0.35, 0.55):.1f}"/>'
                )
        x += r * rnd.uniform(0.7, 1.3) / (density * 10)
    pts = []
    for xs in range(int(x0) - 4, int(x1) + 5, 3):
        top = base
        for cx, cy, r in circles:
            dx = xs - cx
            if abs(dx) < r:
                top = min(top, cy - math.sqrt(r * r - dx * dx))
        pts.append((xs, top))
    d = f"M{x0 - 4} {H} " + " ".join(f"L{px} {py:.1f}" for px, py in pts) + f" L{x1 + 4} {H} Z"
    return f'<g fill="{fill}" opacity="{opacity}"><path d="{d}"/>' + "".join(extra) + "</g>"


def roots(seed: int, x0: float, x1: float, y: float, fill: str, n=60):
    """Pneumatophores: the breathing roots that spike out of Sundarbans mud."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        x = rnd.uniform(x0, x1)
        h = rnd.uniform(4, 13)
        out.append(f'<path d="M{x - 1.2:.1f} {y} L{x:.1f} {y - h:.1f} L{x + 1.2:.1f} {y} Z"/>')
    return f'<g fill="{fill}">' + "".join(out) + "</g>"


def mangrove_tree(x: float, y: float, s: float, fill: str):
    """A foreground mangrove: arched prop roots, leaning trunk, layered crown."""
    roots_ = "".join(
        f'<path d="M{x + dx * s:.1f} {y} Q{x + dx * s * 0.6:.1f} {y - 40 * s:.1f} {x:.1f} {y - 50 * s:.1f}" '
        f'stroke="{fill}" stroke-width="{3 * s:.1f}" fill="none"/>'
        for dx in (-40, -26, -12, 10, 24, 38)
    )
    trunk = (
        f'<path d="M{x - 5 * s:.1f} {y - 48 * s:.1f} C{x - 4 * s:.1f} {y - 110 * s:.1f} {x + 6 * s:.1f} {y - 150 * s:.1f} '
        f'{x + 4 * s:.1f} {y - 190 * s:.1f} L{x + 10 * s:.1f} {y - 190 * s:.1f} C{x + 12 * s:.1f} {y - 150 * s:.1f} '
        f'{x + 4 * s:.1f} {y - 110 * s:.1f} {x + 5 * s:.1f} {y - 48 * s:.1f} Z" fill="{fill}"/>'
    )
    crown = "".join(
        f'<ellipse cx="{x + cx * s:.1f}" cy="{y + cy * s:.1f}" rx="{rx * s:.1f}" ry="{ry * s:.1f}" fill="{fill}"/>'
        for cx, cy, rx, ry in [(6, -200, 60, 26), (-30, -176, 46, 20), (44, -170, 50, 20), (10, -226, 40, 18), (-54, -150, 30, 12), (70, -146, 34, 12)]
    )
    return roots_ + trunk + crown


def birds(seed: int, x0, y0, n, fill, size=1.0):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        x = x0 + rnd.uniform(0, 160) * size
        y = y0 + rnd.uniform(0, 50) * size
        w = rnd.uniform(6, 11) * size
        out.append(
            f'<path d="M{x - w:.1f} {y - w * 0.35:.1f} Q{x - w / 2:.1f} {y - w * 0.6:.1f} {x:.1f} {y:.1f} '
            f'Q{x + w / 2:.1f} {y - w * 0.6:.1f} {x + w:.1f} {y - w * 0.35:.1f}" stroke="{fill}" '
            f'stroke-width="{1.6 * size:.1f}" fill="none" stroke-linecap="round"/>'
        )
    return "".join(out)


def svg(defs: str, body: str, w=W, h=H) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'preserveAspectRatio="xMidYMid slice"><defs>{defs}</defs>{body}</svg>'
    )


def sky(id_: str, stops: list[tuple[float, str]]) -> str:
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{id_}" x1="0" y1="0" x2="0" y2="1">{s}</linearGradient>'


def sun(id_: str, color: str) -> str:
    return (
        f'<radialGradient id="{id_}"><stop offset="0" stop-color="{color}" stop-opacity="1"/>'
        f'<stop offset="0.35" stop-color="{color}" stop-opacity="0.55"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>'
    )


def sundarbans() -> str:
    defs = (
        sky("sk", [(0, "#0c3a29"), (0.45, "#3b6a48"), (0.72, "#c89a4c"), (0.8, "#f0c46e")])
        + sun("sn", "#ffe2a0")
        + sky("rv", [(0, "#c6a258"), (0.08, "#56806a"), (0.5, "#1d4a3c"), (1, "#0b2a20")])
    )
    body = f'<rect width="{W}" height="{H}" fill="url(#sk)"/>'
    body += '<circle cx="1180" cy="262" r="150" fill="url(#sn)"/><circle cx="1180" cy="262" r="34" fill="#ffe7b0"/>'
    body += birds(3, 980, 120, 7, "#18382a")
    body += canopy(11, 285, 26, density=0.12, crowns=(8, 16), fill="#4f7a5c", opacity=0.75, tall=0.1)
    body += canopy(12, 300, 40, density=0.1, crowns=(12, 24), fill="#24503a", tall=0.2)
    body += f'<rect y="300" width="{W}" height="{H - 300}" fill="url(#rv)"/>'
    for i in range(18):  # sun glitter on the water
        y = 306 + i * 5.5
        w = 90 - i * 4
        body += f'<rect x="{1180 - w / 2 + (i % 3 - 1) * 6:.0f}" y="{y:.0f}" width="{w}" height="1.6" fill="#ffd98c" opacity="{0.8 - i * 0.04:.2f}"/>'
    body += "".join(
        f'<path d="M{x} {y} q12 -3 24 0" stroke="#7fa48c" stroke-width="1" fill="none" opacity="0.5"/>'
        for x, y in [(300, 340), (380, 356), (640, 372), (820, 346), (900, 384), (1420, 352), (1500, 372)]
    )
    # Mud bank on the right, the tiger walking along it, breathing roots.
    body += '<path d="M1230 318 C1300 300 1450 296 1600 300 L1600 330 C1450 334 1300 334 1230 318 Z" fill="#163a2a"/>'
    body += roots(5, 1250, 1600, 312, "#163a2a", n=70)
    body += shape(TIGER, 1330, 230, 0.55, "#0e2a1e")
    body += f'<path d="{TIGER_STRIPES}" transform="translate(1330 230) scale(0.55)" stroke="#c28a3a" stroke-width="4" fill="none" stroke-linecap="round" opacity="0.8"/>'
    # Nouka with its boatman, and its reflection.
    body += f'<g opacity="0.95">{shape(BOAT, 560, 316, 0.9, "#0f2c20")}{shape(BOATMAN, 560, 316, 0.9, "#0f2c20")}</g>'
    body += f'<g opacity="0.18" transform="translate(0 680) scale(1 -1)">{shape(BOAT, 560, 316, 0.9, "#0f2c20")}</g>'
    # Foreground mangroves framing the left, where the page title sits.
    body += mangrove_tree(70, 400, 1.15, "#0a2219") + mangrove_tree(230, 410, 0.85, "#0c271c")
    body += roots(9, 0, 420, 398, "#0a2219", n=50)
    return svg(defs, body)


def paddy() -> str:
    defs = sky("sk", [(0, "#1f5a3a"), (0.5, "#7fa874"), (0.78, "#e8d79a"), (0.82, "#f4e2a6")]) + sun("sn", "#fff1c4")
    body = f'<rect width="{W}" height="{H}" fill="url(#sk)"/>'
    body += '<circle cx="360" cy="250" r="160" fill="url(#sn)"/><circle cx="360" cy="250" r="30" fill="#fff4cf"/>'
    body += birds(7, 520, 110, 6, "#2a4a34")
    # Village tree line: palms and huts on the horizon.
    body += canopy(21, 268, 18, density=0.11, crowns=(10, 18), fill="#5d8a5a", opacity=0.8, tall=0.0)
    if ICONS:
        palm, box = icon("palm-tree")
        hut, hbox = icon("hut")
        for x, s, f in [(700, 90, False), (760, 70, True), (1000, 100, True), (1060, 80, False), (1290, 95, False), (1450, 75, True), (180, 80, True)]:
            body += place(palm, x, 274, s, box, "#2d5a3a", flip=f)
        for x, s in [(880, 36), (920, 30), (1190, 34)]:
            body += place(hut, x, 274, s, hbox, "#2d5a3a")
    # Paddy terraces: bands that get wider towards the viewer, with a strip of water.
    bands = [(270, "#6d9b4e"), (286, "#5c8f45"), (300, "#a9c7b0"), (306, "#4f8740"), (326, "#5f9a49"), (350, "#3f7a36"), (380, "#33692f")]
    for (y, c), (y2, _) in zip(bands, bands[1:] + [(H, "")]):
        body += f'<rect y="{y}" width="{W}" height="{y2 - y}" fill="{c}"/>'
    rnd = random.Random(4)
    for y in range(330, H, 7):  # rows of seedlings
        body += f'<path d="M0 {y} H{W}" stroke="#2c5e2a" stroke-width="1" stroke-dasharray="{rnd.randint(3,6)} {rnd.randint(4,8)}" opacity="0.6"/>'
    # Farmer driving a water buffalo at the plough, egrets nearby.
    body += shape(BUFFALO, 1120, 228, 0.62, "#1b3a24") + shape(BUFFALO_HORN, 1120, 228, 0.62, "#1b3a24") + shape(BUFFALO_TAIL, 1120, 228, 0.62, "#1b3a24")
    # Yoke rope from the buffalo back to the plough the farmer holds.
    body += '<path d="M1124 262 Q1090 286 1052 292" stroke="#1b3a24" stroke-width="2" fill="none"/>'
    body += '<path d="M1040 284 L1060 300 L1048 302 Z" fill="#1b3a24"/>'
    body += shape(FARMER, 1020, 255, 0.62, "#1b3a24")
    if ICONS:
        heron, hb = icon("heron")
        for x, s, f in [(1330, 44, False), (1380, 36, True), (1460, 40, False)]:
            body += place(heron, x, 336, s, hb, "#f4f1e6", flip=f)
    return svg(defs, body)


def hills() -> str:
    defs = (
        sky("sk", [(0, "#16452f"), (0.45, "#6c967a"), (0.75, "#d9c88f"), (1, "#e7d49b")])
        + sun("sn", "#fff0c0")
        + '<linearGradient id="mist" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#eef3e6" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#eef3e6" stop-opacity="0.32"/><stop offset="1" stop-color="#eef3e6" stop-opacity="0"/></linearGradient>'
    )
    body = f'<rect width="{W}" height="{H}" fill="url(#sk)"/>'
    body += '<circle cx="1220" cy="150" r="170" fill="url(#sn)"/><circle cx="1220" cy="150" r="32" fill="#fff4d2"/>'
    layers = [(31, 210, 40, "#9db59a", 0.9), (32, 245, 50, "#7a9d80", 1), (33, 285, 55, "#557d5f", 1), (34, 325, 50, "#2f5a40", 1), (35, 365, 40, "#173d2a", 1)]
    for i, (seed, base, amp, color, op) in enumerate(layers):
        d, pts = ridge(seed, base, amp)
        body += f'<path d="{d}" fill="{color}" opacity="{op}"/>'
        if i < 4:  # mist in each valley
            body += f'<rect y="{base - 30}" width="{W}" height="70" fill="url(#mist)"/>'
        if i == 2:  # the kyang on the highest point of this ridge
            x, y = min(pts[40:160], key=lambda p: p[1])
            body += shape(STUPA, x - 22, y - 46, 0.7, color)
    # The river winding through the valley floor.
    body += (
        '<path d="M0 372 C200 352 360 392 560 372 C760 352 900 392 1100 376 C1300 360 1450 386 1600 370 '
        'L1600 382 C1450 398 1300 372 1100 388 C900 404 760 364 560 384 C360 404 200 364 0 384 Z" fill="#9fc0b4" opacity="0.7"/>'
    )
    body += birds(13, 760, 80, 5, "#2b4a36")
    return svg(defs, body)


def padma() -> str:
    defs = (
        sky("sk", [(0, "#163f33"), (0.4, "#5c7f62"), (0.66, "#e0a85a"), (0.72, "#f2c070")])
        + sun("sn", "#ffd88f")
        + sky("rv", [(0, "#e3b46a"), (0.1, "#7a8f6c"), (0.6, "#2c5a4e"), (1, "#123329")])
    )
    body = f'<rect width="{W}" height="{H}" fill="url(#sk)"/>'
    body += '<circle cx="820" cy="282" r="190" fill="url(#sn)"/><circle cx="820" cy="282" r="40" fill="#ffe4a8"/>'
    body += canopy(41, 288, 10, density=0.13, crowns=(6, 12), fill="#4d6f53", opacity=0.7, tall=0.0)
    body += f'<rect y="288" width="{W}" height="{H - 288}" fill="url(#rv)"/>'
    for i in range(20):
        y = 294 + i * 5.5
        w = 120 - i * 5
        body += f'<rect x="{820 - w / 2 + (i % 3 - 1) * 8:.0f}" y="{y:.0f}" width="{w}" height="1.6" fill="#ffd98c" opacity="{0.85 - i * 0.04:.2f}"/>'
    # A char (sandbank) with kash grass.
    body += '<path d="M1080 330 C1180 318 1380 316 1520 326 C1440 338 1200 340 1080 330 Z" fill="#c9b27a" opacity="0.8"/>'
    rnd = random.Random(8)
    body += "".join(
        f'<path d="M{x:.0f} 326 q{rnd.uniform(-4, 4):.1f} -{rnd.uniform(8, 16):.0f} {rnd.uniform(-2, 2):.1f} -{rnd.uniform(14, 22):.0f}" stroke="#eae2c8" stroke-width="1.4" fill="none"/>'
        for x in [rnd.uniform(1100, 1500) for _ in range(40)]
    )
    # Sail boats with tall square sails (pal tola nouka).
    for x, y, s in [(330, 330, 1.0), (560, 308, 0.6), (1220, 356, 0.8)]:
        body += shape(BOAT, x, y, 0.55 * s, "#122c22")
        body += f'<path d="M{x + 50 * s:.0f} {y + 8 * s:.0f} L{x + 52 * s:.0f} {y - 90 * s:.0f} L{x + 56 * s:.0f} {y - 90 * s:.0f} L{x + 56 * s:.0f} {y + 8 * s:.0f} Z" fill="#122c22"/>'
        body += f'<path d="M{x + 57 * s:.0f} {y - 86 * s:.0f} L{x + 110 * s:.0f} {y - 74 * s:.0f} L{x + 104 * s:.0f} {y - 6 * s:.0f} L{x + 57 * s:.0f} {y - 4 * s:.0f} Z" fill="#7a4a2a" opacity="0.92"/>'
    if ICONS:
        dolphin, db = icon("dolphin")
        body += place(dolphin, 980, 330, 46, db, "#1b3a30", flip=True)
    body += birds(17, 1240, 120, 6, "#20402f")
    return svg(defs, body)


def sidebar() -> str:
    w, h = 240, 260
    defs = (
        '<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.6" stop-color="#fff" stop-opacity="1"/></linearGradient>'
        f'<mask id="m"><rect width="{w}" height="{h}" fill="url(#fade)"/></mask>'
    )
    body = '<g mask="url(#m)">'
    body += mangrove_tree(60, 260, 0.7, "#145236") + mangrove_tree(180, 270, 0.9, "#114a30")
    body += roots(2, 0, 240, 258, "#145236", n=40)
    body += shape(TIGER, 70, 176, 0.36, "#17603e")
    body += "</g>"
    return svg(defs, body, w, h).replace('preserveAspectRatio="xMidYMid slice"', 'preserveAspectRatio="xMidYMax meet"')


OUT.mkdir(parents=True, exist_ok=True)
for name, fn in [("sundarbans", sundarbans), ("paddy", paddy), ("hills", hills), ("padma", padma), ("sidebar", sidebar)]:
    path = OUT / f"{name}.svg"
    path.write_text(fn(), encoding="utf-8")
    print(f"{path.name}: {path.stat().st_size // 1024} KB")
