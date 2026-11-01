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
  The Beta prior on the outlet rates, Beta(2,1) (outlets usually right) or Beta(1,1)
  (flat), is chosen by 5-fold cross-validation inside the training claims (`prior="auto"`).

`dawid_skene` learns the share of true claims together with the outlet rates, as in the
original method, so it is not handicapped when true and false claims are unbalanced.

Every report also gives a reference that sees no vote at all: the claim's source (OHCHR
claims are mostly true, fact-checked claims are all false in this window). A method can
only be credited with what it adds beyond that.

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
        a0: tuple[float, float] = (2.0, 1.0), learn_prior: bool = False,
        eb: float | None = None) -> dict[str, float]:  # fmt: skip
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
        if eb:  # empirical Bayes: shrink each source towards the pooled rates
            ms = min(max(sum(s_num.values()) / max(sum(s_den.values()), 1e-9), 0.05), 0.95)
            mc = min(max(sum(c_num.values()) / max(sum(c_den.values()), 1e-9), 0.05), 0.95)
            sens = {o: (s_num[o] + eb * ms) / (s_den[o] + eb) for o in outlets}
            spec = {o: (c_num[o] + eb * mc) / (c_den[o] + eb) for o in outlets}
        else:
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
        free = [g for g in claims if g not in clamp]
        if learn_prior and free:
            prior = min(max(sum(new[g] for g in free) / len(free), 0.02), 0.98)
        if max(abs(new[g] - p[g]) for g in claims) < 1e-6:
            p = new
            break
        p = new
    return p


def dawid_skene(votes, claims, **_) -> dict[str, float]:
    return _em(votes, claims, clamp={}, prior=0.5, learn_prior=True)


PRIORS = {"beta21": (2.0, 1.0), "flat": (1.0, 1.0)}


def carcux(votes, claims, train: dict[str, int], a0: tuple[float, float] = PRIORS["beta21"],
           **_) -> dict[str, float]:  # fmt: skip
    base = min(max(sum(train.values()) / len(train), 0.05), 0.95) if train else 0.5
    return _em(votes, claims, clamp=train, prior=base, a0=a0)


def choose_prior(votes, train: dict[str, int], k: int = 5) -> tuple[str, dict[str, float]]:
    """The outlet-rate prior with the best out-of-fold AUC inside the training claims."""
    groups = sorted(g for g in train if votes.get(g))
    rng = random.Random(SEED)  # noqa: S311 - a reproducible split, not security
    rng.shuffle(groups)
    parts = [groups[i::k] for i in range(k)]
    results = {}
    for name, a0 in PRIORS.items():
        scores = {}
        for part in parts:
            held = set(part)
            fit_on = {g: t for g, t in train.items() if g not in held}
            s = carcux(votes, sorted(train), train=fit_on, a0=a0)
            scores.update({g: s[g] for g in part})
        results[name] = auc([train[g] for g in groups], [scores[g] for g in groups]) or 0.0
    best = max(PRIORS, key=lambda n: (results[n], n == "beta21"))  # ties keep Beta(2,1)
    return best, results


EB_STRENGTHS = (2.0, 5.0, 10.0, 20.0, 50.0)


def carcux_eb(votes, claims, train: dict[str, int], strength: float | None = None,
              **_) -> dict[str, float]:  # fmt: skip
    """CARCUX with an empirical-Bayes prior on the source rates; its strength is chosen by
    3-fold cross-validation inside the training items unless given."""
    base = min(max(sum(train.values()) / len(train), 0.05), 0.95) if train else 0.5
    if strength is None:
        strength = choose_strength(votes, claims, train)
    return _em(votes, claims, clamp=train, prior=base, eb=strength)


def choose_strength(votes, claims, train: dict[str, int], k: int = 3) -> float:
    groups = sorted(g for g in train if votes.get(g))
    if len(groups) < 2 * k or len({train[g] for g in groups}) < 2:
        return 10.0
    rng = random.Random(SEED)  # noqa: S311 - a reproducible split, not security
    rng.shuffle(groups)
    parts = [groups[i::k] for i in range(k)]
    best, best_score = 10.0, -1.0
    for st in EB_STRENGTHS:
        scores = {}
        for part in parts:
            held = set(part)
            s = carcux_eb(votes, claims, {g: t for g, t in train.items() if g not in held},
                          strength=st)  # fmt: skip
            scores.update({g: s[g] for g in part})
        y, p = [train[g] for g in groups], [scores[g] for g in groups]
        # log loss rewards ranking and calibration together
        score = -sum(-math.log(max(q if t else 1 - q, 1e-6)) for t, q in zip(y, p, strict=True))
        if score > best_score:
            best, best_score = st, score
    return best


def _logit(q: float) -> float:
    q = min(max(q, 1e-6), 1 - 1e-6)
    return math.log(q / (1 - q))


def fit_platt(y: list[int], p: list[float], ridge: float = 1.0) -> tuple[float, float]:
    """a, b minimising log loss of sigmoid(a·logit(p) + b) plus a ridge pulling towards the
    identity (a = 1, b = 0), by damped Newton steps with backtracking. a is kept in
    [0.05, 3] and b in [-5, 5]: when the training scores separate the classes perfectly the
    unpenalised fit runs off to infinity."""
    x = [_logit(q) for q in p]

    def loss(a, b):
        tot = ridge * ((a - 1) ** 2 + b**2) / 2
        for xi, yi in zip(x, y, strict=True):
            z = a * xi + b
            tot += math.log1p(math.exp(-abs(z))) + max(z, 0) - yi * z
        return tot

    a, b = 1.0, 0.0
    cur = loss(a, b)
    for _ in range(100):
        ga, gb = ridge * (a - 1), ridge * b
        haa, hab, hbb = ridge, 0.0, ridge
        for xi, yi in zip(x, y, strict=True):
            q = _sigmoid(a * xi + b)
            r, w = q - yi, q * (1 - q)
            ga, gb = ga + r * xi, gb + r
            haa, hab, hbb = haa + w * xi * xi, hab + w * xi, hbb + w
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        step = 1.0
        while step > 1e-4:
            na = min(max(a - step * da, 0.05), 3.0)
            nb = min(max(b - step * db, -5.0), 5.0)
            new = loss(na, nb)
            if new <= cur:
                break
            step /= 2
        else:
            break
        moved = abs(na - a) + abs(nb - b)
        a, b, cur = na, nb, new
        if moved < 1e-7:
            break
    return a, b


def carcux_cal(votes, claims, train: dict[str, int], k: int = 3, **_) -> dict[str, float]:
    """CARCUX, then Platt scaling fitted on out-of-fold scores inside the training items."""
    full = carcux(votes, claims, train=train)
    groups = sorted(g for g in train if votes.get(g))
    if len(groups) < 4 * k or len({train[g] for g in groups}) < 2:
        return full
    rng = random.Random(SEED)  # noqa: S311 - a reproducible split, not security
    rng.shuffle(groups)
    oof = {}
    for i in range(k):
        held = set(groups[i::k])
        s = carcux(votes, claims, train={g: t for g, t in train.items() if g not in held})
        oof.update({g: s[g] for g in held})
    a, b = fit_platt([train[g] for g in groups], [oof[g] for g in groups])
    return {g: (q if g in train else _sigmoid(a * _logit(q) + b)) for g, q in full.items()}


def claim_sources(claims_path: Path) -> dict[str, str]:
    """claim_group -> 'ohchr' if any of its claims comes from the OHCHR report, else
    'fact_check'."""
    out: dict[str, str] = {}
    for line in claims_path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("in_scope") != "yes":
            continue
        g = r.get("claim_group") or r["claim_id"]
        if r["source"] == "ohchr" or g not in out:
            out[g] = r["source"]
    return out


METHODS = {"majority": majority, "reliability": reliability, "dawid_skene": dawid_skene,
           "carcux": carcux}  # fmt: skip


# ------------------------------------------------------------------ evaluation


def auc(y: list[int], p: list[float]) -> float | None:
    pos = [s for s, t in zip(p, y, strict=True) if t == 1]
    neg = [s for s, t in zip(p, y, strict=True) if t == 0]
    if not pos or not neg:
        return None
    # Mann-Whitney U from mid-ranks: the same value as counting every pair, in n log n
    order = sorted(p)
    first: dict[float, int] = {}
    last: dict[float, int] = {}
    for i, s in enumerate(order, start=1):
        first.setdefault(s, i)
        last[s] = i
    rank_sum = sum((first[s] + last[s]) / 2 for s in pos)
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


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
    # calibration: 10 bins of equal size, mean |predicted - observed| weighted by bin size
    order = sorted(range(len(y)), key=lambda i: p[i])
    bins = [order[i * len(y) // 10 : (i + 1) * len(y) // 10] for i in range(10)]
    ece = sum(abs(sum(p[i] for i in b) - sum(y[i] for i in b)) for b in bins if b) / len(y)
    # selective accuracy: the 80% of items the method is most sure about
    sure = sorted(range(len(y)), key=lambda i: -abs(p[i] - 0.5))[: max(1, int(0.8 * len(y)))]
    acc80 = sum(pred[i] == y[i] for i in sure) / len(sure)
    return {
        "n": len(y),
        "auc": auc(y, p),
        "accuracy": acc,
        "macro_f1": sum(f1s) / 2,
        "brier": brier,
        "ece": ece,
        "acc_at_80pct": acc80,
    }


def intervals(truth: dict[str, int], ids: list[str], scores: dict[str, dict]) -> dict:
    """Bootstrap intervals over test claims: AUC and Brier per method, and the AUC gain of
    CARCUX over each other method on the same resampled claims (paired)."""
    from carcux_data.j24.ci import interval

    def stat(method, key):
        return lambda gs: metrics([truth[g] for g in gs], [scores[method][g] for g in gs])[key]

    res = {m: {"auc": interval(ids, stat(m, "auc")), "brier": interval(ids, stat(m, "brier"))}
           for m in scores}  # fmt: skip
    if "carcux" in scores:
        for m in scores:
            if m == "carcux":
                continue

            def gain(gs, m=m):
                a, b = stat("carcux", "auc")(gs), stat(m, "auc")(gs)
                return None if a is None or b is None else a - b

            res["carcux"][f"auc_gain_over_{m}"] = interval(ids, gain)
    return res


def run(out: Path, claims_path: Path, *, stances: str = "auto", sheets=None, key=None,
        prior: str = "auto", log: Callable[[str], None] = print) -> dict:  # fmt: skip
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
    if prior == "auto":
        prior, inner = choose_prior(votes, train)
        report["prior_cv_auc"] = inner
    report["prior"] = prior
    src = claim_sources(claims_path)
    report["reference_claim_source_only"] = metrics(
        [truth[g] for g in covered], [1.0 if src.get(g) == "ohchr" else 0.0 for g in covered]
    )
    scores = {}
    for name, fn in METHODS.items():
        s = fn(votes, claims, train=train, a0=PRIORS[prior])
        scores[name] = s
        report["methods"][name] = {
            "all_test": metrics([truth[g] for g in test_ids], [s[g] for g in test_ids]),
            "test_with_votes": metrics([truth[g] for g in covered], [s[g] for g in covered]),
        }  # fmt: skip
        log(f"  {name}: {report['methods'][name]['test_with_votes']}")
    report["intervals_95"] = intervals(truth, covered, scores)
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
