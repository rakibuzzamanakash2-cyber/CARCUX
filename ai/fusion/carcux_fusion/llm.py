"""B6: an LLM given all of an event's reports.

    python -m carcux_fusion.llm DATASET_DIR [--backend ollama] [--model qwen2.5:7b]
        [--checkpoints T+6h final] [--no-stance] [--cache DIR] [--json out.json]
    python -m carcux_fusion.llm --simulate [--events 60] [--contamination 0.3] [--sim-seed 1] ...

For one event at a checkpoint, the model reads every report published by then (time
since the first report, source type, a pseudonymous source label so repeated accounts
are visible, the report text cut to 300 characters, and by default the report's
annotated stance, the same input every other method gets) and answers in JSON: the
probability that the event really happened, one of the six assessment labels, and a
short reason.

The answer enters the evaluation like any other method: its probability, as log-odds,
goes through the same Platt calibration fitted on training folds (`llm`), and is also
scored exactly as stated (`llm, as stated`). Its labels are scored against the gold
checkpoint labels like the assessment in `assess`.

Backends (no extra packages; plain HTTP):

- `ollama` (default): a local model through Ollama (http://localhost:11434). Free,
  reproducible, and reports never leave the machine;
- `openai`: any OpenAI-compatible server (`--base-url`, key in `CARCUX_LLM_API_KEY`):
  a hosted API, or a model served from Colab;
- `fake`: a rule that counts stances, for tests and dry runs.

Answers are cached on disk by model and prompt, so reruns, folds and checkpoints with
the same evidence cost nothing. Never send real CARCUX-BD reports to a hosted service
without checking the data's terms first.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from carcux_fusion import assess, evaluate, metrics, simulate
from carcux_fusion import methods as M
from carcux_fusion.data import Dataset, Event, load

LABELS = assess.LABELS
MAX_REPORTS = 40
EXCERPT = 300
STANCE = {1: "says it happened", -1: "says it did not happen / calls it false"}

SYSTEM = (
    "You assess disaster reports from Bangladesh for a situation room. Reports may be "
    "in English, Bangla or Banglish. Some sources are unreliable, some reports copy "
    "others, and some events are rumours that never happened. Judge only from the "
    "reports given. Answer with JSON only."
)
INSTRUCTIONS = """Labels:
- verified: it happened and the reports agree on the details
- partially_verified: it happened but credible reports disagree on details (severity, counts, cause)
- conflicting: credible reports disagree on whether it happened
- unverified: not enough reliable evidence either way
- refuted: it did not happen
- insufficient_evidence: no usable reports

Answer as JSON:
{"probability": <0 to 1, that the event really happened>,
 "label": "<one label>", "reason": "<one short sentence>"}"""


# --- Prompt ----------------------------------------------------------------------------


def prompt(data: Dataset, event: Event, cutoff: datetime, *, stance: bool = True) -> str:
    items = [ev for ev in event.evidence if data.observations[ev.obs_id].published <= cutoff][
        :MAX_REPORTS
    ]
    if not items:
        return f"No reports yet.\n\n{INSTRUCTIONS}"
    first = data.observations[items[0].obs_id].published
    alias: dict[str, str] = {}
    lines = [f"{len(items)} report(s) about one possible event, oldest first:"]
    for n, ev in enumerate(items, 1):
        ob = data.observations[ev.obs_id]
        who = alias.setdefault(ob.source_id, f"S{len(alias) + 1}")
        minutes = int((ob.published - first).total_seconds() // 60)
        kind = data.source_type.get(ob.source_id, "other")
        text = " ".join(ob.text.split())[:EXCERPT]
        head = f"[{n}] +{minutes // 60}h{minutes % 60:02d}m, {kind} source {who}"
        if stance:
            head += f", {STANCE[ev.vote]}"
        lines.append(f"{head}: {text}")
    return "\n".join(lines) + "\n\n" + INSTRUCTIONS


def parse(reply: str) -> dict:
    """The model's JSON, made safe: probability in [0, 1], a known label."""
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    try:
        out = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        out = {}
    try:
        p = float(out.get("probability"))
    except (TypeError, ValueError):
        p = float("nan")
    ok = not math.isnan(p)
    label = str(out.get("label", "")).strip().lower().replace(" ", "_")
    return {
        "probability": min(max(p, 0.0), 1.0) if ok else 0.5,
        "label": label if label in LABELS else "unverified",
        "reason": str(out.get("reason", ""))[:300],
        "parsed": ok and label in LABELS,
    }


# --- Backends ----------------------------------------------------------------------------


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(  # noqa: S310 (a configured local or API URL)
        url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read())


class Ollama:
    def __init__(self, model: str, host: str = "http://localhost:11434", timeout=600):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout

    def __call__(self, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0, "seed": 0, "num_ctx": 8192},
        }
        return _post(f"{self.host}/api/chat", body, {}, self.timeout)["message"]["content"]


class OpenAICompatible:
    def __init__(self, model: str, base_url: str, timeout=600):
        self.model, self.url, self.timeout = model, base_url.rstrip("/"), timeout
        self.key = os.environ.get("CARCUX_LLM_API_KEY", "")

    def __call__(self, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        reply = _post(f"{self.url}/chat/completions", body, headers, self.timeout)
        return reply["choices"][0]["message"]["content"]


class Fake:
    """Counts stances: for tests and dry runs, not a baseline."""

    model = "fake"

    def __call__(self, user: str) -> str:
        yes, no = user.count(STANCE[1]), user.count(STANCE[-1])
        p = (yes + 1) / (yes + no + 2)
        label = "verified" if p >= 0.8 else "refuted" if p <= 0.2 else "unverified"
        if yes + no == 0:
            label = "insufficient_evidence"
        return json.dumps({"probability": p, "label": label, "reason": "stance count"})


def backend(name: str, model: str, base_url: str | None = None):
    if name == "ollama":
        return Ollama(model, base_url or "http://localhost:11434")
    if name == "openai":
        if not base_url:
            raise ValueError("--base-url is needed for an OpenAI-compatible server")
        return OpenAICompatible(model, base_url)
    if name == "fake":
        return Fake()
    raise ValueError(f"unknown backend {name}")


# --- Asking, with a cache ----------------------------------------------------------------


class Asker:
    def __init__(self, client, model: str, cache_dir: str | Path | None = None, log=print):
        self.client, self.model, self.log = client, model, log
        self.memory: dict[str, dict] = {}
        self.path = Path(cache_dir) / "llm-cache.jsonl" if cache_dir else None
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line:
                    row = json.loads(line)
                    self.memory[row["key"]] = row["answer"]
        self.calls = self.failures = 0
        self.seconds = 0.0

    def key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}\n{SYSTEM}\n{text}".encode()).hexdigest()

    def __call__(self, text: str) -> dict:
        k = self.key(text)
        if k in self.memory:
            return self.memory[k]
        answer = None
        for attempt in range(2):
            start = time.perf_counter()
            try:
                answer = parse(self.client(text))
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
                if attempt:
                    raise RuntimeError(f"the model did not answer: {exc}") from exc
                continue
            finally:
                self.seconds += time.perf_counter() - start
                self.calls += 1
            if answer["parsed"]:
                break
        if not answer["parsed"]:
            self.failures += 1
        self.memory[k] = answer
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": k, "answer": answer}, ensure_ascii=False) + "\n")
        if self.calls % 25 == 0:
            self.log(f"  {self.calls} model calls, {self.seconds / self.calls:.1f} s each")
        return answer


class LLM(M.Method):
    """B6 as a fusion method: the model's stated probability, as log-odds."""

    name = "llm"

    def __init__(self, ask: Asker, stance: bool = True):
        self.ask, self.stance = ask, stance
        self.answers: dict[tuple[str, datetime], dict] = {}

    def answer(self, data: Dataset, eid: str, cutoff: datetime) -> dict:
        key = (eid, cutoff)
        if key not in self.answers:
            self.answers[key] = self.ask(prompt(data, data.events[eid], cutoff, stance=self.stance))
        return self.answers[key]

    def raw(self, data, events, cutoffs, deps):
        out = {}
        for eid in events:
            p = min(max(self.answer(data, eid, cutoffs[eid])["probability"], 1e-3), 1 - 1e-3)
            out[eid] = math.log(p / (1 - p))
        return out


# --- Study -------------------------------------------------------------------------------


def run(
    data: Dataset,
    ask: Asker,
    *,
    k: int = 5,
    seed: int = 0,
    checkpoints: list[str] | None = None,
    stance: bool = True,
) -> dict:
    llm = LLM(ask, stance=stance)
    chosen = [c for c in evaluate.CHECKPOINTS if not checkpoints or c[0] in checkpoints]
    keep: dict = {}
    result = evaluate.run(
        data,
        k=k,
        seed=seed,
        method_list=[M.Majority(), M.Reliability("detected"), llm],
        keep=keep,
        checkpoints=chosen,
    )
    events = keep["events"]
    first = {e: data.first_seen(data.events[e]) for e in events}
    truth = [int(data.events[e].occurred) for e in events]
    labels_by_cp = {}
    for cp, hours in chosen:
        cut = {e: first[e] + timedelta(hours=hours) for e in events}
        answers = {e: llm.answer(data, e, cut[e]) for e in events}
        stated = [answers[e]["probability"] for e in events]
        block = result["checkpoints"][cp]
        block["methods"]["llm, as stated"] = metrics.score(stated, truth).as_dict()
        proposed = keep["predictions"][cp][evaluate.PROPOSED]
        block["brier_vs_proposed"]["llm, as stated"] = evaluate.paired_bootstrap(
            [(p - y) ** 2 for p, y in zip(stated, truth, strict=True)],
            [(proposed[e] - y) ** 2 for e, y in zip(events, truth, strict=True)],
            seed=seed,
        )
        scored = [e for e in events if data.events[e].gold_labels.get(cp)]
        labels_by_cp[cp] = assess._label_scores(
            [answers[e]["label"] for e in scored], [data.events[e].gold_labels[cp] for e in scored]
        )
    result["llm"] = {
        "model": ask.model,
        "stance_given": stance,
        "calls": ask.calls,
        "seconds_per_call": ask.seconds / ask.calls if ask.calls else None,
        "unparsed_answers": ask.failures,
        "labels": labels_by_cp,
    }
    return result


def table(result: dict) -> str:
    info = result["llm"]
    lines = [
        evaluate.table(result),
        "",
        f"LLM {info['model']} (stance {'given' if info['stance_given'] else 'not given'}): "
        f"{info['calls']} new calls"
        + (f", {info['seconds_per_call']:.1f} s each" if info["seconds_per_call"] else "")
        + f", {info['unparsed_answers']} unusable answers",
        f"{'its own labels':<20}{'accuracy':>10}{'macro-F1':>10}{'wrongly verified':>18}",
    ]
    for cp, s in info["labels"].items():
        if s["accuracy"] is None:
            continue
        lines.append(
            f"{cp:<20}{s['accuracy']:>10.3f}{s['macro_f1']:>10.3f}{s['wrongly_verified']:>18.3f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.llm")
    parser.add_argument("dataset", nargs="?")
    parser.add_argument("--backend", default="ollama", choices=["ollama", "openai", "fake"])
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--base-url")
    parser.add_argument("--checkpoints", nargs="+", choices=[c for c, _ in evaluate.CHECKPOINTS])
    parser.add_argument("--no-stance", action="store_true", help="give the text only")
    parser.add_argument("--cache", default=".llm-cache", help="answer cache folder")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--simulate", action="store_true", help="generate a simulated set")
    parser.add_argument("--events", type=int, default=60)
    parser.add_argument("--contamination", type=float, default=0.3)
    parser.add_argument("--sim-seed", type=int, default=1)
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    if not args.simulate and not args.dataset:
        parser.error("give a dataset folder, or --simulate")
    try:
        client = backend(args.backend, args.model, args.base_url)
        ask = Asker(client, getattr(client, "model", args.model), args.cache)
        with tempfile.TemporaryDirectory() as tmp:
            path = args.dataset
            if args.simulate:
                path = Path(tmp) / f"sim-c{args.contamination}-s{args.sim_seed}"
                simulate.generate(
                    path, events=args.events, contamination=args.contamination, seed=args.sim_seed
                )
            result = run(
                load(path),
                ask,
                k=args.folds,
                seed=args.seed,
                checkpoints=args.checkpoints,
                stance=not args.no_stance,
            )
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        if args.backend == "ollama":
            print(
                "Is Ollama running, and is the model pulled? (ollama pull MODEL)", file=sys.stderr
            )
        return 1
    print(table(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
