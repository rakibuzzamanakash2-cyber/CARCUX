"""Fusion: how true is each claim, given what many outlets said about it? (Paper 1.)

Every candidate article carries a stance on its claim (automatic now, human once the
sheets are back). A stance becomes a vote: repeats supports the claim, corrects opposes
it, questions opposes it weakly, mentions and unrelated give no vote. Votes from the same
story in several outlets (copies, syndication) are not independent, so articles of a
claim whose titles nearly match share one vote between them.

Methods compared (all give P(claim is true)):

- `majority`: supporting minus opposing votes, smoothed.
- `reliability`: each outlet weighted by how often its stances agreed with the truth on
  the training claims (supervised).
- `dawid_skene`: outlet reliability and claim truth estimated together by EM without any
  truth labels (unsupervised truth discovery).
- `carcux`: the proposed method. Dawid-Skene EM in which (a) the training claims are
  clamped to their known truth, (b) each outlet has separate rates for supporting true
  claims and opposing false ones, with Beta priors, (c) votes are weighted by stance
  confidence and by the copy discount above, and (d) the prior is the training base rate.

Truth comes only from OHCHR (found = true, contradicted = false) and fact-checkers (false,
altered, misleading = false; true = true); relayed, unproven and partly-true claims have no
truth label. Claim groups are split 70/30 with the protocol's seed; nothing is fitted on the
test claims.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from carcux_data.j24.stance import DEFAULTS, predict, read_sheets

SEED, TEST_SHARE = 2024, 0.3
VOTE = {"repeats": 1.0, "corrects": -1.0, "questions": -0.5}
COPY_JACCARD = 0.6  # title-word overlap above which two articles count as one story
FALSE_VERDICTS = {"false", "altered", "misleading"}


# ------------------------------------------------------------------ inputs


def truth_labels(claims_path: Path) -> dict[str, int]:
    """claim_group -> 1 (true) / 0 (false), from OHCHR and fact-checkers only."""
    votes: dict[str, list[int]] = defaultdict(list)
    for line in claims_path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("in_scope") != "yes":
            continue
        g = r.get("claim_group") or r["claim_id"]
        if r["source"] == "ohchr":
            if r.get("ohchr_finding") == "found":
                votes[g].append(1)
            elif r.get("ohchr_finding") == "contradicted":
                votes[g].append(0)
        elif r.get("verdict") in FALSE_VERDICTS:
            votes[g].append(0)
        elif r.get("verdict") == "true":
            votes[g].append(1)
    # a group with conflicting verdicts (one fact-checker true, another false) has no label
    return {g: v[0] for g, v in votes.items() if len(set(v)) == 1}


def _title_words(t: str) -> set[str]:
    return set(re.findall(r"[a-z0-9ঀ-৿]+", (t or "").lower()))


def copy_clusters(articles: list[dict]) -> list[int]:
    """A cluster id per article: articles whose titles share most words are one story."""
    ids = list(range(len(articles)))

    def find(i: int) -> int:
        while ids[i] != i:
            ids[i] = ids[ids[i]]
            i = ids[i]
        return i

    words = [_title_words(a.get("title", "")) for a in articles]
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            a, b = words[i], words[j]
            if a and b and len(a & b) / len(a | b) >= COPY_JACCARD:
                ids[find(i)] = find(j)
    return [find(i) for i in range(len(articles))]


def load_votes(
    out: Path,
    *,
    stances: str = "auto",
    sheets: list[Path] | None = None,
    key: Path | None = None,
    params: dict | None = None,
) -> dict[str, list[dict]]:
    """claim_group -> votes [{outlet, vote, weight}] from the candidates and their stances."""
    cands = [json.loads(x) for x in (out / "matches" / "candidates.jsonl")
             .read_text("utf-8").splitlines() if x.strip()]  # fmt: skip
    for n, c in enumerate(cands, 1):
        c["pair_id"] = f"p{n:05d}"
    feats = {}
    fpath = out / "matches" / "stance_features.jsonl"
    if fpath.exists():
        for line in fpath.read_text("utf-8").splitlines():
            if line.strip():
                f = json.loads(line)
                feats[f["pair_id"]] = f
    human: dict[str, str] = {}
    if stances == "human":
        from collections import Counter

        examples = set(json.loads(key.read_text("utf-8")).get("examples", {})) if key else set()
        examples = examples or set()
        for pid, given in read_sheets(sheets or []).items():
            counts = Counter(lab for _, lab in given).most_common()
            if pid not in examples and not (len(counts) > 1 and counts[0][1] == counts[1][1]):
                human[pid] = counts[0][0]
    by_claim: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        if stances == "human":
            label, conf = human.get(c["pair_id"]), 1.0
        else:
            f = feats.get(c["pair_id"])
            if not f:
                continue
            label = predict(f, params or DEFAULTS)
            conf = (
                f["entail"] if label == "repeats" else f["contra"] if label == "corrects" else 0.5
            )
            conf = max(conf, 0.5)
        if label in VOTE:
            vote = {"outlet": c["outlet"], "title": c.get("title", ""), "vote": VOTE[label],
                    "conf": conf}  # fmt: skip
            by_claim[c["claim_group"]].append(vote)
    for votes in by_claim.values():
        clusters = copy_clusters(votes)
        sizes = defaultdict(int)
        for k in clusters:
            sizes[k] += 1
        for v, k in zip(votes, clusters, strict=True):
            v["weight"] = v["conf"] / sizes[k]
    return by_claim


def split(groups: list[str]) -> set[str]:
    """The test claim groups: a fixed 30%, drawn once with the protocol's seed."""
    g = sorted(set(groups))
    random.Random(SEED).shuffle(g)  # noqa: S311 - a reproducible split, not security
    return set(g[: round(len(g) * TEST_SHARE)])


# ------------------------------------------------------------------ methods


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(min(x, 30), -30)))


def majority(votes: dict[str, list[dict]], claims: list[str], **_) -> dict[str, float]:
    out = {}
    for g in claims:
        sup = sum(v["weight"] for v in votes.get(g, []) if v["vote"] > 0)
        opp = sum(-v["vote"] * v["weight"] for v in votes.get(g, []) if v["vote"] < 0)
        out[g] = (sup + 1) / (sup + opp + 2)
    return out


def _agree(v: dict, truth: int) -> bool:
    return (v["vote"] > 0) == (truth == 1)


def reliability(votes, claims, train: dict[str, int], **_) -> dict[str, float]:
    good, total = defaultdict(float), defaultdict(float)
    for g, t in train.items():
        for v in votes.get(g, []):
            total[v["outlet"]] += v["weight"]
            good[v["outlet"]] += v["weight"] * _agree(v, t)
    base = sum(train.values()) / len(train) if train else 0.5
    out = {}
    for g in claims:
        logit = math.log(base / (1 - base)) if 0 < base < 1 else 0.0
        for v in votes.get(g, []):
            r = (good[v["outlet"]] + 1) / (total[v["outlet"]] + 2)
            logit += (
                v["weight"] * abs(v["vote"]) * math.copysign(1, v["vote"]) * math.log(r / (1 - r))
            )
        out[g] = _sigmoid(logit)
    return out


def _em(votes, claims, clamp: dict[str, int], prior: float, iters: int = 50,
        a0: tuple[float, float] = (2.0, 1.0)) -> dict[str, float]:  # fmt: skip
    """Binary Dawid-Skene. sens = P(support | true), spec = P(oppose | false), per outlet."""
    p = majority(votes, claims)
    p.update({g: float(t) for g, t in clamp.items() if g in p})
    outlets = {v["outlet"] for g in claims for v in votes.get(g, [])}
    for _ in range(iters):
        s_num, s_den, c_num, c_den = (defaultdict(float) for _ in range(4))
        for g in claims:
            for v in votes.get(g, []):
                w = v["weight"] * abs(v["vote"])
                o, sup = v["outlet"], v["vote"] > 0
                s_num[o] += w * p[g] * sup
                s_den[o] += w * p[g]
                c_num[o] += w * (1 - p[g]) * (not sup)
                c_den[o] += w * (1 - p[g])
        sens = {o: (s_num[o] + a0[0]) / (s_den[o] + sum(a0)) for o in outlets}
        spec = {o: (c_num[o] + a0[0]) / (c_den[o] + sum(a0)) for o in outlets}
        new = {}
        for g in claims:
            if g in clamp:
                new[g] = float(clamp[g])
                continue
            logit = math.log(prior / (1 - prior))
            for v in votes.get(g, []):
                w, o = v["weight"] * abs(v["vote"]), v["outlet"]
                if v["vote"] > 0:
                    logit += w * math.log(sens[o] / (1 - spec[o]))
                else:
                    logit += w * math.log((1 - sens[o]) / spec[o])
            new[g] = _sigmoid(logit)
        if max(abs(new[g] - p[g]) for g in claims) < 1e-6:
            p = new
            break
        p = new
    return p


def dawid_skene(votes, claims, **_) -> dict[str, float]:
    return _em(votes, claims, clamp={}, prior=0.5)


def carcux(votes, claims, train: dict[str, int], **_) -> dict[str, float]:
    base = min(max(sum(train.values()) / len(train), 0.05), 0.95) if train else 0.5
    return _em(votes, claims, clamp=train, prior=base)


METHODS = {"majority": majority, "reliability": reliability, "dawid_skene": dawid_skene,
           "carcux": carcux}  # fmt: skip


# ------------------------------------------------------------------ evaluation


def auc(y: list[int], p: list[float]) -> float | None:
    pos = [s for s, t in zip(p, y, strict=True) if t == 1]
    neg = [s for s, t in zip(p, y, strict=True) if t == 0]
    if not pos or not neg:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def metrics(y: list[int], p: list[float]) -> dict:
    if not y:
        return {"n": 0}
    pred = [int(s >= 0.5) for s in p]
    f1s = []
    for lab in (0, 1):
        tp = sum(a == lab and b == lab for a, b in zip(y, pred, strict=True))
        fp = sum(a != lab and b == lab for a, b in zip(y, pred, strict=True))
        fn = sum(a == lab and b != lab for a, b in zip(y, pred, strict=True))
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0)
    acc = sum(a == b for a, b in zip(y, pred, strict=True)) / len(y)
    brier = sum((s - t) ** 2 for s, t in zip(p, y, strict=True)) / len(y)
    return {
        "n": len(y),
        "auc": auc(y, p),
        "accuracy": acc,
        "macro_f1": sum(f1s) / 2,
        "brier": brier,
    }


def run(out: Path, claims_path: Path, *, stances: str = "auto", sheets=None, key=None,
        log: Callable[[str], None] = print) -> dict:  # fmt: skip
    truth = truth_labels(claims_path)
    votes = load_votes(out, stances=stances, sheets=sheets, key=key)
    claims = sorted(set(truth) | set(votes))
    test = split(list(truth))
    train = {g: t for g, t in truth.items() if g not in test}
    test_ids = sorted(g for g in truth if g in test)
    covered = [g for g in test_ids if votes.get(g)]
    report = {"stances": stances, "claims_with_truth": len(truth), "train": len(train),
              "test": len(test_ids), "test_with_votes": len(covered),
              "test_true_share": sum(truth[g] for g in test_ids) / max(len(test_ids), 1),
              "methods": {}}  # fmt: skip
    scores = {}
    for name, fn in METHODS.items():
        s = fn(votes, claims, train=train)
        scores[name] = s
        report["methods"][name] = {
            "all_test": metrics([truth[g] for g in test_ids], [s[g] for g in test_ids]),
            "test_with_votes": metrics([truth[g] for g in covered], [s[g] for g in covered]),
        }  # fmt: skip
        log(f"  {name}: {report['methods'][name]['test_with_votes']}")
    folder = out / "fusion"
    folder.mkdir(exist_ok=True)
    (folder / f"report_{stances}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    with (folder / f"claims_{stances}.jsonl").open("w", encoding="utf-8") as f:
        for g in claims:
            part = "test" if g in test else "train" if g in truth else "unlabelled"
            row = {"claim_group": g, "truth": truth.get(g), "split": part,
                   "votes": len(votes.get(g, [])),
                   **{m: round(scores[m][g], 4) for m in METHODS}}  # fmt: skip
            f.write(json.dumps(row) + "\n")
    return report
