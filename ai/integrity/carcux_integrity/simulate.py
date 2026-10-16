"""Simulated field workers, ordinary and compromised, to measure the checks and the
account score. **Not evidence about real people:** every account and report here is
made up.

Each ordinary worker has a home area (a real Bangladeshi locality or district centre),
working hours and a usual number of reports a day, and writes short Banglish, Bangla or
English reports that sometimes name their area. Two weeks of ordinary work come first.
On the last day some accounts are taken over or misused, one scenario each:

| Scenario | What happens |
|---|---|
| `stolen_far` | someone else uses the account from another district |
| `burst` | a dozen reports in a few minutes |
| `copier` | rumours copied from public posts, sent as field reports |
| `spoofed_place` | GPS at home, text about a far-away place it was not at |
| `old_photos` | photos reused from other workers' reports |
| `night_shift` | reports in the small hours, which the worker never sends |

Ordinary workers on the last day include honest noise: a trip to a neighbouring district,
a report naming a nearby area, a weak GPS fix, a post-like phrase.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from carcux_extraction.places import gazetteer
from carcux_integrity.checks import Report, Text

DHAKA = timezone(timedelta(hours=6))
SCENARIOS = ["stolen_far", "burst", "copier", "spoofed_place", "old_photos", "night_shift"]

TEMPLATES = [
    "{place} e pani jomeche, rasta diye hata jacche na",
    "{place} te hatu pani, dokan bondho",
    "{place}-e current nai shokal theke",
    "{place} এ রাস্তায় পানি জমেছে",
    "{place} এলাকায় বিদ্যুৎ নেই",
    "Waterlogging near {place} market, traffic slow",
    "Tree fell on the road in {place}, one lane open",
    "Drain overflowing at {place} bus stand",
]
PLAIN = [
    "pani ektu komse, kintu ekhono ache",
    "rasta khola, gari cholche",
    "aj bristi nai, sob thik ache",
    "Water level same as morning",
    "বৃষ্টি থেমেছে, পানি নামছে",
]
RUMOURS = [
    "Breaking: dam gates opened upstream, everyone in the district must leave immediately tonight",
    "সতর্কতা: আগামী এক ঘণ্টার মধ্যে বড় ভূমিকম্প হবে, সবাই বাসা থেকে বের হয়ে যান এখনই",
    "Flyover collapsed near the airport, hundreds trapped, share this video with everyone now",
    "Bridge over the river has broken completely, no one can cross, army has been called in",
]


@dataclass
class World:
    reports: list[Report] = field(default_factory=list)
    public: list[Text] = field(default_factory=list)
    scenario: dict[str, str] = field(default_factory=dict)  # account -> scenario
    injected: set[str] = field(default_factory=set)  # report ids that are abnormal
    report_scenario: dict[str, str] = field(default_factory=dict)  # report id -> scenario
    now: datetime | None = None


def _places() -> list[dict]:
    g = gazetteer()
    return [
        {"name": x["name"], "lat": x["lat"], "lon": x["lon"]}
        for x in g["localities"] + g["districts"]
    ]


def _dist2(a: dict, b: dict) -> float:
    return (a["lat"] - b["lat"]) ** 2 + (a["lon"] - b["lon"]) ** 2


def _jitter(rng: random.Random, lat: float, lon: float, km: float) -> tuple[float, float]:
    return lat + rng.gauss(0, km / 111), lon + rng.gauss(0, km / 102)


def simulate(workers: int = 60, days: int = 14, compromised: int = 18, seed: int = 0) -> World:
    rng = random.Random(seed)
    places = _places()
    start = datetime(2026, 7, 1, tzinfo=DHAKA)
    w = World(now=start + timedelta(days=days + 1))
    n = 0

    def report(acc, at, text, lat, lon, acc_m=None, photos=(), scenario=None):
        nonlocal n
        n += 1
        rid = f"R{n:05d}"
        r = Report(
            rid,
            acc,
            text,
            lat,
            lon,
            at - timedelta(minutes=rng.randint(0, 20)),
            at,
            acc_m if acc_m is not None else rng.choice([15, 30, 60]),
            tuple(photos),
        )
        w.reports.append(r)
        if scenario:
            w.injected.add(rid)
            w.report_scenario[rid] = scenario
        return r

    def photo():
        return f"{rng.getrandbits(64):016x}"

    profiles = []
    for k in range(workers):
        home = rng.choice(places)
        profiles.append(
            {
                "acc": f"W{k:03d}",
                "home": home,
                "range": rng.uniform(1.0, 4.0),
                "hours": (rng.randint(7, 10), rng.randint(17, 21)),
                "rate": rng.uniform(1.5, 6.0),
            }
        )

    def ordinary(p, day_start, count):
        out = []
        for _ in range(count):
            h = rng.uniform(*p["hours"])
            at = day_start + timedelta(hours=h)
            lat, lon = _jitter(rng, p["home"]["lat"], p["home"]["lon"], p["range"])
            text = (
                rng.choice(TEMPLATES).format(place=p["home"]["name"])
                if rng.random() < 0.6
                else rng.choice(PLAIN)
            )
            out.append(
                report(p["acc"], at, text, lat, lon, photos=[photo()] if rng.random() < 0.3 else [])
            )
        return out

    for day in range(days):
        for p in profiles:
            ordinary(p, start + timedelta(days=day), _poisson(rng, p["rate"]))

    # Public posts in the same weeks, some of them rumours.
    for i in range(80):
        text = (
            rng.choice(RUMOURS)
            if i % 4 == 0
            else f"{rng.choice(TEMPLATES).format(place=rng.choice(places)['name'])} #{i}"
        )
        w.public.append(Text(f"P{i:03d}", text, "public post"))

    last = start + timedelta(days=days)
    bad = rng.sample(profiles, compromised)
    for i, p in enumerate(bad):
        w.scenario[p["acc"]] = SCENARIOS[i % len(SCENARIOS)]
    earlier_photos = [h for r in w.reports for h in r.photo_hashes]
    for p in profiles:
        s = w.scenario.get(p["acc"])
        normal = max(_poisson(rng, p["rate"]), 1)
        if s is None:
            day = ordinary(p, last, normal)
            # Honest noise: a trip, a nearby place, weak GPS, a shared phrase.
            roll = rng.random()
            if roll < 0.15 and day:
                near = min(
                    (x for x in places if x["name"] != p["home"]["name"]),
                    key=lambda x: _dist2(x, p["home"]),
                )
                lat, lon = _jitter(rng, near["lat"], near["lon"], 1.0)
                report(
                    p["acc"],
                    last + timedelta(hours=p["hours"][1] - 1),
                    f"{near['name']} e giyechilam, okhaneo pani",
                    lat,
                    lon,
                )
            elif roll < 0.25:
                lat, lon = _jitter(rng, p["home"]["lat"], p["home"]["lon"], 0.5)
                report(
                    p["acc"],
                    last + timedelta(hours=p["hours"][0] + 1),
                    rng.choice(PLAIN),
                    lat,
                    lon,
                    acc_m=1500,
                )
            continue
        ordinary(p, last, max(normal // 2, 1))
        hours = rng.uniform(*p["hours"])
        at = last + timedelta(hours=hours)
        if s == "stolen_far":
            far = max(
                places,
                key=lambda x: (
                    (x["lat"] - p["home"]["lat"]) ** 2 + (x["lon"] - p["home"]["lon"]) ** 2
                ),
            )
            for j in range(3):
                lat, lon = _jitter(rng, far["lat"], far["lon"], 2.0)
                text = rng.choice(TEMPLATES).format(place=far["name"])
                report(p["acc"], at + timedelta(hours=j * 2), text, lat, lon, scenario=s)
        elif s == "burst":
            for j in range(12):
                lat, lon = _jitter(rng, p["home"]["lat"], p["home"]["lon"], p["range"])
                report(
                    p["acc"],
                    at + timedelta(seconds=40 * j),
                    rng.choice(PLAIN),
                    lat,
                    lon,
                    scenario=s,
                )
        elif s == "copier":
            for j, post in enumerate(rng.sample([x for x in w.public if x.text in RUMOURS], 2)):
                lat, lon = _jitter(rng, p["home"]["lat"], p["home"]["lon"], p["range"])
                report(p["acc"], at + timedelta(hours=j), post.text, lat, lon, scenario=s)
        elif s == "spoofed_place":
            elsewhere = max(
                places,
                key=lambda x: abs(x["lat"] - p["home"]["lat"]) + abs(x["lon"] - p["home"]["lon"]),
            )
            for j in range(2):
                lat, lon = _jitter(rng, p["home"]["lat"], p["home"]["lon"], p["range"])
                text = rng.choice(TEMPLATES).format(place=elsewhere["name"])
                report(p["acc"], at + timedelta(hours=j), text, lat, lon, scenario=s)
        elif s == "old_photos":
            for j in range(2):
                lat, lon = _jitter(rng, p["home"]["lat"], p["home"]["lon"], p["range"])
                report(
                    p["acc"],
                    at + timedelta(hours=j),
                    rng.choice(PLAIN),
                    lat,
                    lon,
                    photos=[rng.choice(earlier_photos)],
                    scenario=s,
                )
        elif s == "night_shift":
            for j in range(4):
                lat, lon = _jitter(rng, p["home"]["lat"], p["home"]["lon"], p["range"])
                report(
                    p["acc"],
                    last + timedelta(hours=2, minutes=25 * j),
                    rng.choice(PLAIN),
                    lat,
                    lon,
                    scenario=s,
                )
    return w


def _poisson(rng: random.Random, mean: float) -> int:
    # Knuth's method; fine for small means.
    limit, k, p = pow(2.718281828459045, -mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
