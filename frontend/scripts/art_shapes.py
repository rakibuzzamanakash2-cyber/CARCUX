"""Silhouettes for the console's Bangladeshi scenes, as SVG path data.

Each is drawn from key points and smoothed (Catmull-Rom to cubic Bezier), feet at
the bottom of its box, so scenes can place them with a translate/scale.
"""


def smooth(points, closed=True, t=0.5):
    """Catmull-Rom spline through points as an SVG path."""
    n = len(points)
    if n < 3:
        return ""
    d = f"M{points[0][0]:.1f} {points[0][1]:.1f}"
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = points[(i - 1) % n] if closed or i > 0 else points[i]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        p3 = points[(i + 2) % n] if closed or i + 2 < n else p2
        c1 = (p1[0] + (p2[0] - p0[0]) * t / 3, p1[1] + (p2[1] - p0[1]) * t / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * t / 3, p2[1] - (p3[1] - p1[1]) * t / 3)
        d += f" C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d + (" Z" if closed else "")


# Royal Bengal tiger walking left: big head carried at shoulder height, heavy
# shoulders, long legs, long tail curving up at the tip. Feet at y=150.
TIGER_PTS = [
    (2, 92), (8, 84), (20, 72), (26, 64), (32, 57), (40, 61), (48, 63), (62, 65),
    (80, 54), (96, 50), (130, 56), (165, 58), (195, 52), (215, 58), (222, 64),
    (236, 76), (246, 96), (248, 118), (253, 130), (262, 128), (266, 121), (269, 126),
    (262, 136), (250, 139), (240, 129), (238, 106), (232, 87), (224, 80),
    (226, 94), (229, 110), (233, 126), (227, 141), (231, 148), (222, 150), (208, 150),
    (211, 140), (214, 126), (208, 112), (202, 112), (200, 128), (198, 146), (201, 150),
    (186, 150), (184, 140), (186, 122), (182, 106), (164, 104), (130, 106), (104, 102),
    (100, 120), (102, 146), (105, 150), (90, 150), (88, 138), (88, 116), (84, 108),
    (78, 118), (76, 140), (80, 150), (64, 150), (62, 138), (64, 112), (60, 100),
    (50, 100), (36, 104), (22, 104), (10, 100), (4, 96),
]
TIGER = smooth(TIGER_PTS, t=0.5)
# Stripes, drawn as strokes in a slightly lighter tone over the body.
TIGER_STRIPES = " ".join(
    smooth(pts, closed=False)
    for pts in [
        [(104, 54), (110, 70), (104, 88)],
        [(120, 56), (126, 74), (120, 94)],
        [(136, 57), (142, 76), (136, 98)],
        [(152, 58), (158, 76), (152, 98)],
        [(168, 58), (174, 74), (168, 96)],
        [(184, 55), (190, 72), (184, 92)],
        [(200, 54), (206, 68), (202, 84)],
        [(66, 70), (72, 82), (68, 94)],
        [(36, 70), (42, 78)],
    ]
)

# Water buffalo (moish) walking right, head forward, crescent horns swept back.
BUFFALO_PTS = [
    (30, 62), (80, 58), (130, 56), (150, 52), (172, 64), (184, 70), (198, 86),
    (206, 100), (210, 110), (206, 117), (196, 117), (186, 108), (172, 100),
    (160, 106), (152, 112), (154, 126), (152, 146), (156, 150), (142, 150),
    (140, 140), (140, 122), (134, 116), (130, 128), (130, 146), (132, 150),
    (120, 150), (118, 140), (118, 120), (100, 118), (70, 118), (62, 124), (64, 146),
    (66, 150), (52, 150), (50, 138), (46, 124), (40, 118), (36, 130), (38, 146),
    (40, 150), (28, 150), (26, 138), (22, 120), (16, 100), (16, 80), (22, 68),
]
BUFFALO = smooth(BUFFALO_PTS, t=0.5)
BUFFALO_HORN = smooth(
    [(182, 74), (168, 67), (156, 58), (148, 47), (150, 39), (156, 43), (164, 53),
     (176, 61), (188, 67)],
    t=0.5,
)
BUFFALO_TAIL = smooth(
    [(18, 74), (11, 98), (8, 118), (9, 130), (15, 128), (15, 112), (18, 90)], t=0.5
)

# Farmer with a conical bamboo hat (mathal), walking right with a stick on the shoulder.
FARMER = (
    "M2 20 C14 8 40 8 52 20 C44 22 12 22 2 20 Z "  # hat
    + smooth([(22, 22), (32, 22), (33, 30), (30, 34), (36, 40), (40, 56), (38, 66),
              (40, 84), (46, 110), (40, 112), (32, 88), (28, 112), (20, 112), (24, 84),
              (22, 60), (22, 42), (26, 34), (22, 30)], t=0.4)
    + " M30 40 L66 26 L67 29 L32 45 Z"
)

# Country boat (nouka) with its curved bamboo canopy (chhoi), bow raised.
BOAT = (
    smooth([(0, 8), (20, 22), (60, 28), (110, 28), (150, 24), (178, 12), (186, 4),
            (188, 10), (176, 26), (150, 36), (100, 40), (50, 38), (16, 30), (2, 18)], t=0.5)
    + " M50 28 C54 12 70 8 88 8 C106 8 118 12 122 28 Z"
)
BOATMAN = (
    "M142 26 L144 2 C146 -4 152 -4 154 2 L156 26 Z "
    "M144 -6 C143 -14 153 -14 152 -6 C151 -2 145 -2 144 -6 Z "
    "M120 -30 L170 40 L167 42 L117 -28 Z"
)

# Hilltop stupa (kyang), Chittagong Hill Tracts.
STUPA = (
    "M0 70 L64 70 L60 62 L4 62 Z M8 62 C8 36 56 36 56 62 Z "
    "M26 40 L38 40 L34 26 L30 26 Z M31 26 L32 4 L33 26 Z M28 30 L36 30 L35 32 L29 32 Z"
)
