import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from carcux_fusion import llm, simulate
from carcux_fusion.data import load


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    simulate.generate(out, events=30, contamination=0.3, seed=2)
    return out


@pytest.fixture(scope="module")
def data(sim):
    return load(sim)


def _busiest(data):
    return max(data.events.values(), key=lambda e: len(e.evidence))


# --- Prompt ------------------------------------------------------------------------------


def test_prompt_shows_reports_by_the_cutoff_without_identities(data, sim):
    event = _busiest(data)
    first = data.first_seen(event)
    early = llm.prompt(data, event, first)
    late = llm.prompt(data, event, first + timedelta(days=7))
    assert early.count("\n[") <= late.count("\n[")
    assert late.startswith(f"{min(len(event.evidence), llm.MAX_REPORTS)} report(s)")
    sources = (sim / "sources.jsonl").read_text()
    for row in map(json.loads, sources.splitlines()):
        assert row["source_id"] not in late  # pseudonyms only
    assert "reliability" not in late.split("Labels:")[0]  # the simulator's notes stay out
    for line in late.splitlines():
        if line.startswith("["):
            assert len(line.split(": ", 1)[1]) <= llm.EXCERPT


def test_prompt_stance_can_be_left_out(data):
    event = _busiest(data)
    cut = data.first_seen(event) + timedelta(days=7)
    assert llm.STANCE[1] in llm.prompt(data, event, cut) or llm.STANCE[-1] in llm.prompt(
        data, event, cut
    )
    bare = llm.prompt(data, event, cut, stance=False)
    assert llm.STANCE[1] not in bare and llm.STANCE[-1] not in bare


def test_same_source_gets_the_same_pseudonym(data):
    event = _busiest(data)
    text = llm.prompt(data, event, data.first_seen(event) + timedelta(days=7))
    seen = {}
    lines = [x for x in text.splitlines() if x.startswith("[")]
    for ev, line in zip(event.evidence[: llm.MAX_REPORTS], lines, strict=True):
        alias = line.split(" source ")[1].split(",")[0].split(":")[0]
        src = data.observations[ev.obs_id].source_id
        assert seen.setdefault(src, alias) == alias


# --- Parsing -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "p", "label", "parsed"),
    [
        ('{"probability": 0.8, "label": "verified", "reason": "x"}', 0.8, "verified", True),
        (
            'Sure! {"probability": 1.7, "label": "Partially Verified"}',
            1.0,
            "partially_verified",
            True,
        ),
        ('{"probability": "0.2", "label": "refuted"}', 0.2, "refuted", True),
        ('{"probability": 0.3, "label": "maybe"}', 0.3, "unverified", False),
        ("I cannot answer.", 0.5, "unverified", False),
        ('{"probability": 0.4, "label": "verified"', 0.5, "verified", False),
    ],
)
def test_parse(reply, p, label, parsed):
    out = llm.parse(reply)
    assert out["probability"] == pytest.approx(p)
    assert out["parsed"] is parsed
    if parsed:
        assert out["label"] == label
    else:
        assert out["label"] in llm.LABELS


# --- Asking and caching ----------------------------------------------------------------------


class Counting:
    model = "counting"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def __call__(self, text):
        self.calls += 1
        return self.replies.pop(0) if self.replies else '{"probability": 0.9, "label": "verified"}'


def test_cache_answers_once_and_survives_restarts(tmp_path):
    client = Counting([])
    ask = llm.Asker(client, "m", tmp_path, log=lambda *_: None)
    assert ask("q")["probability"] == 0.9
    ask("q")
    assert client.calls == 1
    again = llm.Asker(Counting([]), "m", tmp_path, log=lambda *_: None)
    again("q")
    assert again.client.calls == 0
    other_model = llm.Asker(Counting([]), "other", tmp_path, log=lambda *_: None)
    other_model("q")
    assert other_model.client.calls == 1


def test_unusable_answer_is_retried_once_then_counted():
    ask = llm.Asker(Counting(["nonsense", "still nonsense"]), "m", None, log=lambda *_: None)
    assert ask("q")["probability"] == 0.5
    assert ask.failures == 1 and ask.client.calls == 2
    ask2 = llm.Asker(Counting(["nonsense"]), "m", None, log=lambda *_: None)
    assert ask2("q")["parsed"] and ask2.failures == 0


def test_unreachable_model_is_a_clear_error(sim, capsys):
    code = llm.main(
        [str(sim), "--base-url", "http://127.0.0.1:9", "--cache", "", "--checkpoints", "final"]
    )
    assert code == 1
    assert "ollama pull" in capsys.readouterr().err


# --- Backends against a stand-in server ----------------------------------------------------------


@pytest.fixture
def server():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, dict(self.headers), body))
            answer = '{"probability": 0.7, "label": "unverified", "reason": "r"}'
            if self.path == "/api/chat":
                out = {"message": {"role": "assistant", "content": answer}}
            else:
                out = {"choices": [{"message": {"content": answer}}]}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    httpd.shutdown()


def test_ollama_request(server):
    url, seen = server
    reply = llm.backend("ollama", "qwen2.5:7b", url)("hello")
    assert llm.parse(reply)["probability"] == 0.7
    path, _, body = seen[0]
    assert path == "/api/chat" and body["format"] == "json" and body["stream"] is False
    assert body["options"]["temperature"] == 0 and body["model"] == "qwen2.5:7b"
    assert body["messages"][-1] == {"role": "user", "content": "hello"}


def test_openai_compatible_request(server, monkeypatch):
    url, seen = server
    monkeypatch.setenv("CARCUX_LLM_API_KEY", "test-key")
    reply = llm.backend("openai", "some-model", url + "/v1")("hello")
    assert llm.parse(reply)["label"] == "unverified"
    path, headers, body = seen[0]
    assert path == "/v1/chat/completions" and body["temperature"] == 0
    assert headers["Authorization"] == "Bearer test-key"


def test_openai_needs_a_url_and_unknown_backends_fail():
    with pytest.raises(ValueError):
        llm.backend("openai", "m")
    with pytest.raises(ValueError):
        llm.backend("magic", "m")


# --- Study -----------------------------------------------------------------------------------


def test_end_to_end_with_the_fake_model(sim, tmp_path):
    out = tmp_path / "r.json"
    args = [str(sim), "--backend", "fake", "--cache", str(tmp_path), "--folds", "3"]
    assert llm.main([*args, "--checkpoints", "T+6h", "final", "--json", str(out)]) == 0
    r = json.loads(out.read_text())
    assert set(r["checkpoints"]) == {"T+6h", "final"}
    final = r["checkpoints"]["final"]
    assert {"llm", "llm, as stated", "majority", "reliability-dep"} <= set(final["methods"])
    assert "llm, as stated" in final["brier_vs_proposed"]
    assert r["llm"]["model"] == "fake" and r["llm"]["unparsed_answers"] == 0
    assert 0 <= r["llm"]["labels"]["final"]["macro_f1"] <= 1
    # Stance counting through Platt is exactly majority vote.
    assert final["methods"]["llm"]["brier"] == pytest.approx(final["methods"]["majority"]["brier"])


def test_simulate_flag(tmp_path, capsys):
    args = ["--simulate", "--events", "20", "--backend", "fake", "--cache", ""]
    assert llm.main([*args, "--checkpoints", "final", "--folds", "3"]) == 0
    assert "LLM fake" in capsys.readouterr().out


def test_needs_a_dataset_or_simulate():
    with pytest.raises(SystemExit):
        llm.main([])
