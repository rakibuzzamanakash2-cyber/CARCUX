"""A simulated CARCUX-BD dataset for developing and stress-testing correlation.

It is not evidence about real events, and every record says so (`is_simulated`, titles
marked [SIMULATED], example.org references). Its job is to exercise the hard cases the
real data will contain, at a size where differences between methods are measurable,
before enough real annotation exists:

- English, Bangla and Banglish reports of the same event, which share few characters;
- reports with GPS, with only a district, or with no location at all;
- "twins": the same kind of event at the same place days apart (time separates them),
  or at the same time in a nearby district (place separates them);
- different events at the same place and hour (fire and accident: type separates them);
- child events (a road blockage caused by waterlogging) with reports about both;
- false events, with reports that deny them.

    python -m carcux_correlation.simulate OUT_DIR [--events 80] [--seed 1]

The output passes the CARCUX-BD validator: `python -m carcux_data.validate OUT_DIR`.
"""

import argparse
import json
import math
import random
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

GENERATOR_VERSION = "0.1"
TYPE_WRONG = 0.10  # share of reports whose claimed type is wrong
TYPE_MISSING = 0.20  # share with no type claim at all
DHAKA = timezone(timedelta(hours=6))

# District centres (from the CARCUX gazetteer, nuhil/bangladesh-geocode, MIT).
PLACES = [
    ("Dhaka", "ঢাকা", "Dhaka", 23.7115, 90.4111),
    ("Gazipur", "গাজীপুর", "Dhaka", 24.0023, 90.4264),
    ("Narayanganj", "নারায়ণগঞ্জ", "Dhaka", 23.6337, 90.4965),
    ("Narsingdi", "নরসিংদী", "Dhaka", 23.9322, 90.7154),
    ("Chattogram", "চট্টগ্রাম", "Chattogram", 22.3351, 91.8341),
    ("Cox's Bazar", "কক্সবাজার", "Chattogram", 21.4432, 91.9738),
    ("Rangamati", "রাঙ্গামাটি", "Chattogram", 22.6556, 92.1754),
    ("Bandarban", "বান্দরবান", "Chattogram", 22.1953, 92.2184),
    ("Cumilla", "কুমিল্লা", "Chattogram", 23.4683, 91.1788),
    ("Feni", "ফেনী", "Chattogram", 23.0232, 91.3841),
    ("Noakhali", "নোয়াখালী", "Chattogram", 22.8696, 91.0994),
    ("Sylhet", "সিলেট", "Sylhet", 24.8898, 91.8698),
    ("Sunamganj", "সুনামগঞ্জ", "Sylhet", 25.0658, 91.395),
    ("Moulvibazar", "মৌলভীবাজার", "Sylhet", 24.4829, 91.7774),
    ("Habiganj", "হবিগঞ্জ", "Sylhet", 24.3749, 91.4155),
    ("Rajshahi", "রাজশাহী", "Rajshahi", 24.3723, 88.5631),
    ("Bogura", "বগুড়া", "Rajshahi", 24.8465, 89.3778),
    ("Rangpur", "রংপুর", "Rangpur", 25.7558, 89.2445),
    ("Kurigram", "কুড়িগ্রাম", "Rangpur", 25.8054, 89.6362),
    ("Gaibandha", "গাইবান্ধা", "Rangpur", 25.3288, 89.5281),
    ("Khulna", "খুলনা", "Khulna", 22.8158, 89.5687),
    ("Satkhira", "সাতক্ষীরা", "Khulna", 22.7181, 89.0687),
    ("Bagerhat", "বাগেরহাট", "Khulna", 22.6516, 89.7859),
    ("Barishal", "বরিশাল", "Barishal", 22.7004, 90.3732),
    ("Patuakhali", "পটুয়াখালী", "Barishal", 22.3596, 90.3299),
    ("Bhola", "ভোলা", "Barishal", 22.6859, 90.6482),
    ("Mymensingh", "ময়মনসিংহ", "Mymensingh", 24.7466, 90.4072),
    ("Netrokona", "নেত্রকোণা", "Mymensingh", 24.871, 90.7279),
    ("Jamalpur", "জামালপুর", "Mymensingh", 24.9375, 89.9378),
    ("Sirajganj", "সিরাজগঞ্জ", "Rajshahi", 24.4534, 89.7007),
]

FAMILY = {
    "waterlogging": "natural_calamity",
    "flood": "natural_calamity",
    "landslide": "natural_calamity",
    "fire": "urban_emergency",
    "building_collapse": "urban_emergency",
    "road_accident": "road_infrastructure",
    "road_blockage": "road_infrastructure",
    "power_outage": "road_infrastructure",
}

# {p} is the place as the reporter writes it. Several wordings per language.
TEMPLATES: dict[str, dict[str, list[str]]] = {
    "waterlogging": {
        "en": [
            "Roads in {p} under knee-deep water after heavy rain",
            "Waterlogging in {p}, vehicles stuck since morning",
            "Streets of {p} flooded after the downpour, people wading through",
        ],
        "bn-Latn": [
            "{p} e hatu pani, rasta te gari cholche na",
            "{p} er rasta pani te dube ache",
            "brishtir pore {p} e onek pani jomse",
        ],
        "bn": ["{p}-এ হাঁটুপানি, যান চলাচল ব্যাহত", "ভারী বৃষ্টিতে {p}-এর রাস্তায় জলাবদ্ধতা", "{p}-এ রাস্তা পানির নিচে"],
    },
    "flood": {
        "en": [
            "Flood situation worsens in {p}, thousands stranded",
            "River crosses danger level near {p}, villages inundated",
            "Floodwater enters new areas of {p}",
        ],
        "bn-Latn": [
            "{p} e bonna, onek manush pani bondi",
            "nodir pani bipodshimar upore, {p} er gram dube geche",
            "{p} e bonnar obostha kharap",
        ],
        "bn": [
            "{p}-এ বন্যা পরিস্থিতির অবনতি",
            "{p}-এ নদীর পানি বিপৎসীমার ওপরে",
            "{p}-এ বন্যায় পানিবন্দী হাজারো মানুষ",
        ],
    },
    "landslide": {
        "en": [
            "Landslide in {p} after overnight rain, houses buried",
            "Hill collapse in {p}, rescue under way",
        ],
        "bn-Latn": [
            "{p} e pahar dhos, kichu ghor chapa porse",
            "rater brishtite {p} e mati dhose porse",
        ],
        "bn": ["{p}-এ পাহাড়ধস, কয়েকটি ঘর চাপা", "{p}-এ ভূমিধসে হতাহত"],
    },
    "fire": {
        "en": [
            "Fire breaks out at a market in {p}",
            "Blaze in {p}, firefighters at the scene",
            "Factory fire in {p}, thick smoke over the area",
        ],
        "bn-Latn": [
            "{p} er bajare agun lagse",
            "{p} e agun, fire service er gari aisa",
            "{p} e factory te agun, onek dhoya",
        ],
        "bn": ["{p}-এর বাজারে আগুন", "{p}-এ অগ্নিকাণ্ড, ফায়ার সার্ভিস ঘটনাস্থলে", "{p}-এ কারখানায় আগুন"],
    },
    "building_collapse": {
        "en": ["Building collapses in {p}, several trapped"],
        "bn-Latn": ["{p} e building bhenge porse, manush atka"],
        "bn": ["{p}-এ ভবন ধসে আটকা কয়েকজন"],
    },
    "road_accident": {
        "en": [
            "Bus and truck collide on the highway near {p}",
            "Road crash near {p} leaves several injured",
        ],
        "bn-Latn": ["{p} er kase highway te bus truck er dhakka", "{p} e accident, koyekjon ahoto"],
        "bn": ["{p}-এর কাছে মহাসড়কে বাস-ট্রাক সংঘর্ষ", "{p}-এ সড়ক দুর্ঘটনায় আহত কয়েকজন"],
    },
    "road_blockage": {
        "en": ["Traffic halted in {p}, road blocked", "Long tailback in {p} as road closes"],
        "bn-Latn": ["{p} e rasta bondho, jam onek", "{p} e gari choltese na, rasta block"],
        "bn": ["{p}-এ সড়ক অবরোধ, যান চলাচল বন্ধ", "{p}-এ রাস্তা বন্ধ, দীর্ঘ যানজট"],
    },
    "power_outage": {
        "en": ["Power outage across {p} for hours", "Blackout in {p} since last night"],
        "bn-Latn": ["{p} e current nai shokal theke", "{p} e load shedding cholche"],
        "bn": ["{p}-এ বিদ্যুৎ বিভ্রাট", "{p}-এ ঘণ্টার পর ঘণ্টা বিদ্যুৎ নেই"],
    },
}
DENIALS = {
    "en": "No {t} in {p}; the report going round is a rumour",
    "bn-Latn": "{p} e kono {t} hoy nai, eta gujob",
    "bn": "{p}-এ কোনো {t} হয়নি, এটি গুজব",
}
TYPE_WORDS = {
    "en": {
        "fire": "fire",
        "flood": "flood",
        "waterlogging": "waterlogging",
        "landslide": "landslide",
        "building_collapse": "collapse",
        "road_accident": "accident",
        "road_blockage": "blockade",
        "power_outage": "outage",
    },
    "bn-Latn": {
        "fire": "agun",
        "flood": "bonna",
        "waterlogging": "jolaboddhota",
        "landslide": "pahar dhos",
        "building_collapse": "building dhos",
        "road_accident": "accident",
        "road_blockage": "oborodh",
        "power_outage": "biddut bibhrat",
    },
    "bn": {
        "fire": "আগুন",
        "flood": "বন্যা",
        "waterlogging": "জলাবদ্ধতা",
        "landslide": "পাহাড়ধস",
        "building_collapse": "ভবন ধস",
        "road_accident": "দুর্ঘটনা",
        "road_blockage": "অবরোধ",
        "power_outage": "বিদ্যুৎ বিভ্রাট",
    },
}
FILLERS = {
    "en": ["", "", " Please send help.", " Still the same now.", " Seen this morning."],
    "bn-Latn": ["", "", " keu help koren", " ekhono same obostha", " shokal theke"],
    "bn": ["", "", " দ্রুত সাহায্য দরকার।", " এখনও একই অবস্থা।", " সকাল থেকে।"],
}


def _iso(dt: datetime) -> str:
    return dt.astimezone(DHAKA).isoformat(timespec="seconds")


def _offset(lat: float, lon: float, km: float, rng: random.Random) -> tuple[float, float]:
    """A point about `km` from (lat, lon) in a random direction."""
    angle = rng.uniform(0, 2 * math.pi)
    dlat = km * math.cos(angle) / 110.574
    dlon = km * math.sin(angle) / (111.320 * math.cos(math.radians(lat)))
    return round(lat + dlat, 5), round(lon + dlon, 5)


def _place_text(place: tuple, language: str, rng: random.Random) -> str:
    name, bn = place[0], place[1]
    if language == "bn":
        return bn
    if language == "bn-Latn" and rng.random() < 0.3:
        return name.lower()
    return name


class _Sim:
    def __init__(self, n_events: int, seed: int, start: datetime):
        self.rng = random.Random(seed)
        self.seed = seed
        self.n_events = n_events
        self.start = start
        self.events: list[dict] = []
        self.observations: list[dict] = []
        self.relations: list[dict] = []
        self.workers = [f"SRC-{i:06d}" for i in range(1, 13)]

    # --- events ---------------------------------------------------------------------

    def _event(
        self,
        etype: str,
        place: tuple,
        lat: float,
        lon: float,
        when: datetime,
        occurred: bool = True,
        parent: str | None = None,
    ) -> dict:
        eid = f"EVT-{len(self.events) + 1:06d}"
        name = place[0]
        ev = {
            "event_id": eid,
            "family": FAMILY[etype],
            "type": etype,
            "title": f"[SIMULATED] {etype.replace('_', ' ').capitalize()} in {name}",
            "location": {
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "precision_m": 500,
                "admin": {"division": place[2], "district": name},
            },
            "start": _iso(when),
            "end": _iso(when + timedelta(hours=self.rng.uniform(6, 72))),
            "time_precision": "hour",
            "ground_truth": {
                "occurred": occurred,
                "facts": [{"attribute": "occurrence", "value": occurred}],
                "sources": [
                    {
                        "reference": f"https://example.org/simulated/{eid}",
                        "published_at": _iso(when + timedelta(days=2)),
                        "kind": "other",
                    }
                ],
            },
            "assessments": [
                {
                    "as_of": _iso(when + timedelta(days=2)),
                    "checkpoint": "final",
                    "label": "verified" if occurred else "refuted",
                    "rationale": "Simulated event: the label follows the simulated ground truth.",
                    "annotations": [
                        self._ann(
                            when + timedelta(days=2), label="verified" if occurred else "refuted"
                        )
                    ],
                }
            ],
        }
        if parent:
            ev["parent_event_id"] = parent
        self.events.append(ev)
        ev["_place"], ev["_lat"], ev["_lon"], ev["_when"] = place, lat, lon, when
        return ev

    def _ann(self, at: datetime, annotator: str = "ANN-001", **extra) -> dict:
        return {
            "annotator": annotator,
            "confidence": 3,
            "annotated_at": _iso(at),
            "guideline_version": "0.2",
            **extra,
        }

    # --- observations ---------------------------------------------------------------

    def _observe(self, events: list[dict], deny: bool = False) -> None:
        """One report about one event (or about a parent and its child together)."""
        ev = events[0]
        rng = self.rng
        language = rng.choices(["en", "bn", "bn-Latn"], weights=[35, 30, 35])[0]
        place = ev["_place"]
        p_text = _place_text(place, language, rng)
        if deny:
            word = TYPE_WORDS[language][ev["type"]]
            text = DENIALS[language].format(t=word, p=p_text)
        else:
            parts = [rng.choice(TEMPLATES[e["type"]][language]).format(p=p_text) for e in events]
            text = "; ".join(parts) if language != "bn" else "। ".join(parts)
            # Some reporters do not name the place at all.
            if rng.random() < 0.15:
                text = text.replace(p_text, "here" if language == "en" else "ekhane")
            text += rng.choice(FILLERS[language])
        seen = ev["_when"] + timedelta(hours=rng.expovariate(1 / 4))
        published = seen + timedelta(minutes=rng.uniform(2, 90))

        mode = rng.choices(["gps", "district", "none"], weights=[45, 25, 30])[0]
        mentions = []
        if mode == "gps":
            error_km = abs(rng.gauss(0, 0.25))
            lat, lon = _offset(ev["_lat"], ev["_lon"], error_km, rng)
            mentions.append(
                {
                    "surface": p_text,
                    "from_gps": True,
                    "resolved": {
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "precision_m": round(rng.uniform(10, 120)),
                        "admin": {"division": place[2], "district": place[0]},
                    },
                }
            )
        elif mode == "district":
            mentions.append(
                {
                    "surface": p_text,
                    "resolved": {
                        "geometry": {"type": "Point", "coordinates": [place[4], place[3]]},
                        "precision_m": 30000,
                        "admin": {"division": place[2], "district": place[0]},
                    },
                }
            )

        oid = f"OBS-{len(self.observations) + 1:07d}"
        claims = [{"attribute": "occurrence", "value": not deny}]
        if not deny:
            # Types come from a keyword classifier in practice: often right, sometimes
            # missing, sometimes wrong.
            roll = rng.random()
            if roll < TYPE_WRONG:
                claimed = rng.choice([t for t in TEMPLATES if t != ev["type"]])
                claims.append({"attribute": "event_type", "value": claimed})
            elif roll >= TYPE_WRONG + TYPE_MISSING:
                claims.append({"attribute": "event_type", "value": ev["type"]})
        self.observations.append(
            {
                "obs_id": oid,
                "source_id": rng.choice(self.workers),
                "modality": "text",
                "language": language,
                "published_at": _iso(published),
                "observed_at": _iso(seen),
                "collected_at": _iso(published + timedelta(minutes=1)),
                "content_policy": "full",
                "text": text,
                "claims": claims,
                **({"location_mentions": mentions} if mentions else {}),
                "is_simulated": True,
                "simulation": {
                    "kind": "contradiction" if deny else "field_report",
                    "generator_version": GENERATOR_VERSION,
                    "seed": self.seed,
                    "derived_from": ev["event_id"],
                    "parameters": {"location": mode},
                },
            }
        )
        label = "contradicts" if deny else "supports"
        for e in events:
            at = published + timedelta(days=3)
            self.relations.append(
                {
                    "obs_id": oid,
                    "event_id": e["event_id"],
                    "annotations": [
                        self._ann(at, "ANN-001", label=label),
                        self._ann(at, "ANN-002", label=label),
                    ],
                    "gold": {"label": label},
                }
            )

    # --- the scenario -----------------------------------------------------------------

    def run(self) -> None:
        rng = self.rng
        span = timedelta(days=30)
        types = list(TEMPLATES)
        while len(self.events) < self.n_events:
            etype = rng.choice(types)
            place = rng.choice(PLACES)
            lat, lon = _offset(place[3], place[4], rng.uniform(0, 6), rng)
            when = self.start + span * rng.random()
            occurred = rng.random() > 0.08
            ev = self._event(etype, place, lat, lon, when, occurred)
            n = 1 + min(int(rng.expovariate(1 / 3)), 9)
            for _ in range(n):
                self._observe([ev], deny=not occurred and rng.random() < 0.5)

            roll = rng.random()
            if roll < 0.15:  # twin: same kind, same place, days later
                lat2, lon2 = _offset(lat, lon, rng.uniform(0.2, 2.0), rng)
                twin = self._event(
                    etype, place, lat2, lon2, when + timedelta(days=rng.uniform(3, 7))
                )
                for _ in range(1 + int(rng.expovariate(1 / 2))):
                    self._observe([twin])
            elif roll < 0.30:  # twin: same kind, same hours, a nearby district
                other = min(
                    (p for p in PLACES if p != place),
                    key=lambda p: (p[3] - place[3]) ** 2 + (p[4] - place[4]) ** 2,
                )
                lat2, lon2 = _offset(other[3], other[4], rng.uniform(0, 4), rng)
                twin = self._event(
                    etype, other, lat2, lon2, when + timedelta(hours=rng.uniform(-3, 3))
                )
                for _ in range(1 + int(rng.expovariate(1 / 2))):
                    self._observe([twin])
            elif roll < 0.40:  # a different event at the same place and hour
                other_type = rng.choice([t for t in types if t != etype])
                lat2, lon2 = _offset(lat, lon, rng.uniform(0.05, 0.6), rng)
                near = self._event(
                    other_type, place, lat2, lon2, when + timedelta(hours=rng.uniform(-1, 1))
                )
                for _ in range(1 + int(rng.expovariate(1 / 2))):
                    self._observe([near])
            if etype in ("waterlogging", "flood") and occurred and rng.random() < 0.35:
                child = self._event(
                    "road_blockage",
                    place,
                    lat,
                    lon,
                    when + timedelta(hours=rng.uniform(0.5, 3)),
                    parent=ev["event_id"],
                )
                for _ in range(1 + int(rng.expovariate(1 / 2))):
                    self._observe([child])
                self._observe([ev, child])  # one report about both

    def write(self, out: Path) -> dict[str, int]:
        out.mkdir(parents=True, exist_ok=True)
        sources = [
            {
                "source_id": s,
                "source_type": "field",
                "name": "Field worker (simulated)",
                "is_simulated": True,
            }
            for s in self.workers
        ]
        events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in self.events]
        files = {
            "events.jsonl": events,
            "sources.jsonl": sources,
            "observations.jsonl": self.observations,
            "relations.jsonl": self.relations,
            "dependences.jsonl": [],
        }
        for name, rows in files.items():
            (out / name).write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
            )
        return {name: len(rows) for name, rows in files.items()}


def generate(out: str | Path, *, events: int = 80, seed: int = 1) -> dict[str, int]:
    sim = _Sim(events, seed, start=datetime(2026, 6, 1, tzinfo=UTC))
    sim.run()
    return sim.write(Path(out))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_correlation.simulate")
    parser.add_argument("out")
    parser.add_argument("--events", type=int, default=80, help="seed events (twins come extra)")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    counts = generate(args.out, events=args.events, seed=args.seed)
    for name, n in counts.items():
        print(f"{name}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
