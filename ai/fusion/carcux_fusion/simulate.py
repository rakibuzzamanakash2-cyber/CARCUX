"""A simulated CARCUX-BD dataset with a contamination dial, for fusion (RQ2-RQ5).

Not evidence about real events: every record says it is simulated (`is_simulated`,
titles marked [SIMULATED], example.org references, source notes).

What it models:

- **Sources with a reliability.** Field workers, news outlets, social accounts and an
  official disaster office, each with a hidden reliability drawn around its type's mean
  (written in the source's `notes` so analyses can check it, never used by the methods).
  An item's stance is right with probability equal to its source's reliability.
- **Real and false events.** A false event exists because someone claimed it; more
  careful sources then tend to deny it.
- **Copies.** Items get copied: verbatim, reworded, reposted, cited ("according to
  ..."), or the photo reused. Copies repeat their origin's stance, so they look like
  extra votes but are not new evidence. Gold dependences record every copy.
- **Time.** First reports within hours; the official office confirms or denies later
  (6 to 30 hours), so checkpoints T+1h, T+6h, T+24h and final see different evidence.
- **Contamination** (0 to 0.6): the share of all items that are injected: rumours
  amplified by copy cascades, false denials of real events, and extra amplification of
  existing false claims. Injected items mostly come from accounts never seen before
  (60 %), some from hijacked credible accounts (20 %: field workers, news outlets),
  the rest from known rumour accounts, so a method cannot simply learn the culprits'
  names. Events the injection creates are marked (`parameters.injected_event`), so the
  same clean events can be compared across contamination levels.

    python -m carcux_fusion.simulate OUT_DIR [--events 120] [--contamination 0.3] [--seed 1]
"""

import argparse
import hashlib
import json
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from carcux_correlation.simulate import (
    DENIALS,
    FAMILY,
    FILLERS,
    PLACES,
    TEMPLATES,
    TYPE_WORDS,
    _iso,
    _place_text,
)

GENERATOR_VERSION = "0.1"
CHECKPOINTS = [("T+1h", 1), ("T+6h", 6), ("T+24h", 24), ("final", 24 * 7)]
CREDIBLE = {"field", "news", "public_record"}

# Source pools: (type, count, mean reliability).
POOLS = [
    ("field", 12, 0.90),
    ("news", 6, 0.85),
    ("public_record", 1, 0.97),
    ("social", 30, 0.65),
    ("rumour", 12, 0.20),  # social accounts that start and spread rumours
]
COPY_TYPES = {  # who copies how
    "social": ["repost", "verbatim_copy", "same_media"],
    "news": ["rewrite", "cites"],
    "rumour": ["repost", "verbatim_copy"],
    "fresh": ["repost", "verbatim_copy"],
}
# Who starts injected items (the rest: known rumour accounts).
FRESH_SHARE = 0.6  # accounts never seen before
HIJACKED_SHARE = 0.2  # credible accounts (field, news) posting false content
CITES = {
    "en": "According to {s}, {t}",
    "bn-Latn": "{s} er moto, {t}",
    "bn": "{s}-এর মতে, {t}",
}
REPOST = {"en": "Sharing: {t}", "bn-Latn": "share korlam: {t}", "bn": "শেয়ার করছি: {t}"}
# What makes two eyewitnesses' words differ: where exactly, and when.
DETAILS = {
    "en": [
        "near the bus stand",
        "by the school",
        "next to the bazar",
        "behind the mosque",
        "on the main road",
        "near the bridge",
        "in front of the hospital",
        "around the market",
        "at the ghat",
        "near the station",
        "by the college gate",
        "at the crossing",
    ],
    "bn-Latn": [
        "bus stand er kase",
        "school er pashe",
        "bazar er pashe",
        "mosjid er pichone",
        "main road e",
        "bridge er kase",
        "hospital er samne",
        "market er ashe pashe",
        "ghat e",
        "station er kase",
        "college gate e",
        "mor e",
    ],
    "bn": [
        "বাসস্ট্যান্ডের কাছে",
        "স্কুলের পাশে",
        "বাজারের পাশে",
        "মসজিদের পেছনে",
        "মেইন রোডে",
        "ব্রিজের কাছে",
        "হাসপাতালের সামনে",
        "মার্কেটের আশেপাশে",
        "ঘাটে",
        "স্টেশনের কাছে",
        "কলেজ গেটে",
        "মোড়ে",
    ],
}


def _beta(rng: random.Random, mean: float, strength: float = 20.0) -> float:
    return min(0.995, max(0.005, rng.betavariate(mean * strength, (1 - mean) * strength)))


def _phash(rng: random.Random) -> str:
    return f"{rng.getrandbits(64):016x}"


def _flip(h: str, bits: int, rng: random.Random) -> str:
    v = int(h, 16)
    for b in rng.sample(range(64), bits):
        v ^= 1 << b
    return f"{v:016x}"


class _Sim:
    def __init__(self, n_events: int, contamination: float, seed: int):
        if not 0 <= contamination <= 0.6:
            raise ValueError("contamination must be between 0 and 0.6")
        self.rng = random.Random(seed)
        self.seed = seed
        self.c = contamination
        self.n_events = n_events
        self.start = datetime(2026, 7, 1, tzinfo=UTC)
        self.sources: list[dict] = []
        self.pool: dict[str, list[dict]] = {}
        self.events: list[dict] = []
        self.items: list[dict] = []  # observations, with private fields starting "_"
        self.deps: list[dict] = []

    # --- sources ----------------------------------------------------------------------

    def make_sources(self) -> None:
        rng = self.rng
        n = 0
        for kind, count, mean in POOLS:
            for k in range(count):
                n += 1
                sid = f"SRC-{n:06d}"
                stype = "social" if kind == "rumour" else kind
                rel = _beta(rng, mean)
                rec = {
                    "source_id": sid,
                    "source_type": stype,
                    "name": {
                        "field": "Field worker (simulated)",
                        "news": f"News outlet {k + 1} (simulated)",
                        "public_record": "Disaster office (simulated)",
                        "social": "Social account (simulated)",
                    }[stype],
                    "is_simulated": True,
                    "notes": f"simulated reliability {rel:.3f}; pool {kind}",
                }
                if stype == "social":
                    rec["platform"] = "facebook"
                    rec["account_ref"] = hashlib.sha256(f"{self.seed}:{sid}".encode()).hexdigest()
                if stype == "news":
                    rec["domain"] = f"news{k + 1}.example.org"
                self.sources.append(rec)
                self.pool.setdefault(kind, []).append({**rec, "_rel": rel, "_kind": kind})

    def pick(self, kind: str) -> dict:
        if kind == "fresh":
            return self.fresh_account()
        return self.rng.choice(self.pool[kind])

    def fresh_account(self) -> dict:
        """A social account never seen before (a new or throwaway rumour account)."""
        sid = f"SRC-{len(self.sources) + 1:06d}"
        rel = _beta(self.rng, 0.2)
        rec = {
            "source_id": sid,
            "source_type": "social",
            "name": "Social account (simulated)",
            "platform": "facebook",
            "account_ref": hashlib.sha256(f"{self.seed}:{sid}".encode()).hexdigest(),
            "is_simulated": True,
            "notes": f"simulated reliability {rel:.3f}; pool fresh (injected)",
        }
        self.sources.append(rec)
        return {**rec, "_rel": rel, "_kind": "fresh"}

    def contamination_source(self) -> tuple[dict, bool]:
        """Who starts an injected item: mostly accounts never seen before, some hijacked
        credible accounts (field workers, news outlets), some known rumour accounts."""
        roll = self.rng.random()
        if roll < FRESH_SHARE:
            return self.fresh_account(), False
        if roll < FRESH_SHARE + HIJACKED_SHARE:
            return self.pick(self.rng.choice(["field", "news"])), True
        return self.pick("rumour"), False

    # --- events -----------------------------------------------------------------------

    def new_event(self, occurred: bool, *, injected: bool = False) -> dict:
        rng = self.rng
        etype = rng.choice(list(TEMPLATES))
        place = rng.choice(PLACES)
        when = self.start + timedelta(days=60 * rng.random())
        eid = f"EVT-{len(self.events) + 1:06d}"
        ev = {
            "event_id": eid,
            "family": FAMILY[etype],
            "type": etype,
            "title": f"[SIMULATED] {etype.replace('_', ' ').capitalize()} in {place[0]}",
            "location": {
                "geometry": {"type": "Point", "coordinates": [place[4], place[3]]},
                "precision_m": 3000,
                "admin": {"division": place[2], "district": place[0]},
            },
            "start": _iso(when),
            "time_precision": "hour",
            "_occurred": occurred,
            "_when": when,
            "_place": place,
            "_injected": injected,
        }
        self.events.append(ev)
        return ev

    # --- items ------------------------------------------------------------------------

    def text_for(self, ev: dict, vote: int, language: str) -> str:
        rng = self.rng
        p = _place_text(ev["_place"], language, rng)
        detail = (
            f", {rng.choice(DETAILS[language])} ({rng.randint(5, 23)}:{rng.randint(0, 59):02d})"
        )
        if vote < 0:
            return DENIALS[language].format(t=TYPE_WORDS[language][ev["type"]], p=p) + detail
        base = rng.choice(TEMPLATES[ev["type"]][language]).format(p=p)
        return base + detail + rng.choice(FILLERS[language])

    def add_item(
        self, ev, source, vote, when, *, kind, text=None, language=None, phash=None, role="original"
    ) -> dict:
        language = language or self.rng.choice(["en", "bn", "bn-Latn"])
        item = {
            "obs_id": f"OBS-{len(self.items) + 1:07d}",
            "_event": ev,
            "_source": source,
            "_vote": vote,
            "_when": when,
            "_kind": kind,
            "_lang": language,
            "_text": text if text is not None else self.text_for(ev, vote, language),
            "_phash": phash,
            "_role": role,
        }
        self.items.append(item)
        return item

    def original(
        self,
        ev,
        kind_pool: str,
        *,
        delay_h: float,
        vote: int | None = None,
        sim_kind: str | None = None,
        source: dict | None = None,
        hijacked: bool = False,
    ) -> dict:
        rng = self.rng
        source = source or self.pick(kind_pool)
        if vote is None:
            truth = 1 if ev["_occurred"] else -1
            vote = truth if rng.random() < source["_rel"] else -truth
        when = ev["_when"] + timedelta(hours=delay_h)
        if sim_kind is None:
            if source["source_type"] == "field":
                sim_kind = "field_report"
            elif vote < 0:
                sim_kind = "contradiction"
            elif not ev["_occurred"]:
                sim_kind = "false_event"
            else:
                sim_kind = "source_report"
        photo = _phash(rng) if source["source_type"] == "field" and rng.random() < 0.5 else None
        item = self.add_item(ev, source, vote, when, kind=sim_kind, phash=photo)
        item["_hijacked"] = hijacked
        return item

    def copy(self, origin: dict, copier_pool: str) -> dict:
        rng = self.rng
        source = self.pick(copier_pool)
        how = rng.choice(COPY_TYPES[copier_pool])
        if how == "same_media" and not origin["_phash"]:
            how = "repost"
        lang = origin["_lang"]
        text = origin["_text"]
        phash = None
        evidence = ["timestamp_order"]
        if how == "repost":
            text = REPOST[lang].format(t=text)
            evidence.append("platform_share")
        elif how == "rewrite":
            words = text.split()
            keep = [w for w in words if rng.random() > 0.2] or words
            text = " ".join(keep) + rng.choice(FILLERS[lang])
            evidence.append("text_overlap")
        elif how == "cites":
            text = CITES[lang].format(
                s=origin["_source"]["name"].replace(" (simulated)", ""), t=text
            )
            evidence.append("attribution")
        elif how == "same_media":
            text = self.text_for(origin["_event"], origin["_vote"], lang)
            phash = _flip(origin["_phash"], rng.randint(0, 3), rng)
            evidence.append("media_hash")
        else:  # verbatim_copy
            evidence.append("text_overlap")
        when = origin["_when"] + timedelta(minutes=rng.expovariate(1 / 90) + 1)
        item = self.add_item(
            origin["_event"],
            source,
            origin["_vote"],
            when,
            kind="duplicate",
            text=text,
            language=lang,
            phash=phash,
            role="copy",
        )
        self.deps.append({"obs": item, "origin": origin, "type": how, "evidence": evidence})
        return item

    def cascade(self, origin: dict, mean_copies: float, pools: list[str]) -> list[dict]:
        """Copies of an item, and copies of copies (each copy can be copied again)."""
        out, frontier = [], [origin]
        while frontier:
            node = frontier.pop()
            n = self._poisson(mean_copies if node is origin else mean_copies * 0.4)
            for _ in range(n):
                c = self.copy(node, self.rng.choice(pools))
                out.append(c)
                frontier.append(c)
        return out

    def _poisson(self, lam: float) -> int:
        # Knuth; small lambdas only.
        threshold, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= threshold:
                return k
            k += 1

    # --- the scenario ---------------------------------------------------------------------

    def clean_event(self, occurred: bool) -> None:
        rng = self.rng
        ev = self.new_event(occurred)
        if occurred:
            n = 1 + self._poisson(2.0)
            for _ in range(n):
                pool = rng.choices(["field", "news", "social"], weights=[5, 2, 3])[0]
                o = self.original(ev, pool, delay_h=rng.expovariate(1 / 3))
                self.cascade(o, 0.8, ["social", "news"])
        else:  # a mistaken claim, then others weigh in
            first = self.original(ev, rng.choice(["social", "news"]), delay_h=0.2, vote=1)
            self.cascade(first, 0.8, ["social", "news"])
            for _ in range(self._poisson(1.2)):
                pool = rng.choices(["field", "news", "social"], weights=[4, 2, 3])[0]
                o = self.original(ev, pool, delay_h=rng.uniform(0.5, 8))
                self.cascade(o, 0.5, ["social", "news"])
        if rng.random() < 0.55:  # the official office confirms or denies, later
            self.original(ev, "public_record", delay_h=rng.uniform(6, 30))

    def contaminate(self, target: int) -> None:
        """Inject items until `target` of them exist."""
        rng = self.rng
        start = len(self.items)
        real = [e for e in self.events if e["_occurred"]]
        while len(self.items) - start < target:
            roll = rng.random()
            if roll < 0.6:  # a rumour, amplified
                ev = self.new_event(False, injected=True)
                src, hijacked = self.contamination_source()
                o = self.original(
                    ev,
                    "",
                    delay_h=0.1,
                    vote=1,
                    sim_kind="false_event",
                    source=src,
                    hijacked=hijacked,
                )
                self.cascade(o, 1.5, ["fresh", "rumour", "social"])
                if rng.random() < 0.3:
                    self.original(ev, "public_record", delay_h=rng.uniform(6, 30))
            elif roll < 0.9 and real:  # a false denial of a real event, amplified
                ev = rng.choice(real)
                src, hijacked = self.contamination_source()
                o = self.original(
                    ev,
                    "",
                    delay_h=rng.uniform(0.5, 12),
                    vote=-1,
                    sim_kind="contradiction",
                    source=src,
                    hijacked=hijacked,
                )
                self.cascade(o, 1.0, ["fresh", "rumour", "social"])
            else:  # more copies of an existing false claim
                wrong = [
                    i for i in self.items if i["_vote"] != (1 if i["_event"]["_occurred"] else -1)
                ]
                if not wrong:
                    continue
                self.cascade(rng.choice(wrong), 1.0, ["fresh", "rumour", "social"])

    def run(self) -> None:
        self.make_sources()
        for _ in range(self.n_events):
            self.clean_event(self.rng.random() < 0.8)
        clean = len(self.items)
        self.contaminate(round(clean * self.c / (1 - self.c)))

    # --- gold assessment over time ----------------------------------------------------------

    def label_at(self, ev: dict, as_of: datetime) -> str:
        """What a careful analyst would conclude from the evidence published so far:
        copies are ignored, only credible source types count, the official word wins."""
        seen = [i for i in self.items if i["_event"] is ev and i["_when"] <= as_of]
        roots = [i for i in seen if i["_role"] == "original"]
        official = [i for i in roots if i["_source"]["source_type"] == "public_record"]
        if official:
            label = "verified" if official[-1]["_vote"] > 0 else "refuted"
        else:
            sup = sum(1 for i in roots if i["_vote"] > 0 and i["_source"]["_kind"] in CREDIBLE)
            den = sum(1 for i in roots if i["_vote"] < 0 and i["_source"]["_kind"] in CREDIBLE)
            if sup >= 2 and den == 0:
                label = "verified"
            elif sup and den:
                label = "conflicting"
            elif den and not sup:
                label = "refuted"
            elif seen:
                label = "unverified"
            else:
                label = "insufficient_evidence"
        if not ev["_occurred"] and label == "verified":
            label = "unverified"
        return label

    # --- output ---------------------------------------------------------------------------

    def _ann(self, at: datetime, annotator: str = "ANN-001", **extra) -> dict:
        return {
            "annotator": annotator,
            "confidence": 3,
            "annotated_at": _iso(at),
            "guideline_version": "0.2",
            **extra,
        }

    def records(self) -> dict[str, list[dict]]:
        items = sorted(self.items, key=lambda i: (i["_when"], i["obs_id"]))
        events = []
        for ev in self.events:
            mine = [i for i in items if i["_event"] is ev]
            if not mine:
                continue
            t0 = mine[0]["_when"]
            done = t0 + timedelta(days=7)
            assessments = []
            for name, hours in CHECKPOINTS:
                as_of = t0 + timedelta(hours=hours)
                label = self.label_at(ev, as_of)
                assessments.append(
                    {
                        "as_of": _iso(as_of),
                        "checkpoint": name,
                        "label": label,
                        "rationale": "Simulated: the rule a careful analyst would apply to the "
                        "evidence published by then (copies ignored).",
                        "annotations": [self._ann(as_of, label=label)],
                    }
                )
            out = {k: v for k, v in ev.items() if not k.startswith("_")}
            out["ground_truth"] = {
                "occurred": ev["_occurred"],
                "facts": [{"attribute": "occurrence", "value": ev["_occurred"]}],
                "sources": [
                    {
                        "reference": f"https://example.org/simulated/{ev['event_id']}",
                        "published_at": _iso(done),
                        "kind": "other",
                    }
                ],
            }
            out["assessments"] = assessments
            events.append(out)

        observations, relations = [], []
        for i in items:
            ev = i["_event"]
            label = "supports" if i["_vote"] > 0 else "contradicts"
            claims = [{"attribute": "occurrence", "value": i["_vote"] > 0}]
            if i["_vote"] > 0:
                claims.append({"attribute": "event_type", "value": ev["type"]})
            rec = {
                "obs_id": i["obs_id"],
                "source_id": i["_source"]["source_id"],
                "modality": "mixed" if i["_phash"] else "text",
                "language": i["_lang"],
                "published_at": _iso(i["_when"]),
                "collected_at": _iso(i["_when"] + timedelta(minutes=1)),
                "content_policy": "full",
                "text": i["_text"],
                "claims": claims,
                "is_simulated": True,
                "simulation": {
                    "kind": i["_kind"],
                    "generator_version": GENERATOR_VERSION,
                    "seed": self.seed,
                    "derived_from": ev["event_id"],
                    "parameters": {
                        "contamination": self.c,
                        "role": i["_role"],
                        "injected_event": ev["_injected"],
                        "hijacked_account": i.get("_hijacked", False),
                    },
                },
            }
            if i["_phash"]:
                rec["media"] = [{"kind": "image", "phash": i["_phash"]}]
            observations.append(rec)
            at = i["_when"] + timedelta(days=8)
            relations.append(
                {
                    "obs_id": i["obs_id"],
                    "event_id": ev["event_id"],
                    "annotations": [
                        self._ann(at, label=label),
                        self._ann(at, "ANN-002", label=label),
                    ],
                    "gold": {"label": label},
                }
            )

        dependences = [
            {
                "obs_id": d["obs"]["obs_id"],
                "origin_obs_id": d["origin"]["obs_id"],
                "type": d["type"],
                "evidence": d["evidence"],
                "annotations": [self._ann(d["obs"]["_when"] + timedelta(days=8))],
            }
            for d in sorted(self.deps, key=lambda d: d["obs"]["obs_id"])
        ]
        return {
            "events.jsonl": events,
            "sources.jsonl": self.sources,
            "observations.jsonl": observations,
            "relations.jsonl": relations,
            "dependences.jsonl": dependences,
        }


def generate(
    out: str | Path, *, events: int = 120, contamination: float = 0.0, seed: int = 1
) -> dict[str, int]:
    sim = _Sim(events, contamination, seed)
    sim.run()
    files = sim.records()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in files.items():
        (out / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    return {name: len(rows) for name, rows in files.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.simulate")
    parser.add_argument("out")
    parser.add_argument("--events", type=int, default=120)
    parser.add_argument("--contamination", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        counts = generate(
            args.out, events=args.events, contamination=args.contamination, seed=args.seed
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for name, n in counts.items():
        print(f"{name}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
