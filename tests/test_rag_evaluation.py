import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).parents[1] / "bench/rag_pilot"


def load(name):
    spec = importlib.util.spec_from_file_location("rag_pilot_" + name, BASE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt_does_not_include_reference_answer():
    runner = load("run_model")
    chat = runner.messages(
        dict(
            repo="example",
            commit="abc",
            question="Question?",
            reference_answer="SECRET_EXPECTED_ANSWER",
        ),
        dict(context="source excerpt"),
    )
    assert "SECRET_EXPECTED_ANSWER" not in json.dumps(chat)
    assert "source excerpt" in chat[-1]["content"]


def test_endpoint_routes():
    runner = load("run_model")
    assert (
        runner.endpoint("http://localhost:1234", "openai")
        == "http://localhost:1234/v1/chat/completions"
    )
    assert (
        runner.endpoint("http://localhost:1234/v1/", "openai")
        == "http://localhost:1234/v1/chat/completions"
    )
    assert runner.endpoint("http://localhost:11434", "ollama") == "http://localhost:11434/api/chat"
    assert (
        runner.endpoint("http://localhost:11434/api", "ollama") == "http://localhost:11434/api/chat"
    )


def test_json_answer_schema():
    runner = load("run_model")
    text = (
        "```json\n"
        + json.dumps(
            dict(answer="ok", abstain=False, citations=[dict(file="a.py", start=2, end=4)])
        )
        + "\n```"
    )
    answer, valid = runner.parse_answer(text)
    assert valid and answer["answer"] == "ok"
    for invalid in [
        "not json",
        '{"answer":"ok"}',
        '{"answer":"ok","abstain":"false","citations":[]}',
    ]:
        assert not runner.parse_answer(invalid)[1]
    assert not runner.parse_answer(
        json.dumps(
            dict(answer="x", abstain=False, citations=[dict(file="a.py", start=True, end=2)])
        )
    )[1]


def test_openai_compatible_transport():
    runner = load("run_model")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                dict(
                    model="local-test",
                    choices=[
                        dict(
                            message=dict(content='{"answer":"ok","abstain":false,"citations":[]}'),
                            finish_reason="stop",
                        )
                    ],
                    usage=dict(prompt_tokens=11, completion_tokens=7),
                )
            ).encode()

    with patch.object(runner.urllib.request, "build_opener") as build:
        build.return_value.open.return_value = Response()
        result = runner.call(
            "http://localhost:1234/v1", "openai", "local-test", [dict(role="user", content="test")]
        )
        request = build.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        assert payload["messages"] == [dict(role="user", content="test")]
        assert payload["temperature"] == 0 and payload["stream"] is False
        assert result["usage"]["completion_tokens"] == 7
        assert result["format_valid"]


def test_ollama_transport_normalizes_usage():
    runner = load("run_model")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                dict(
                    model="local-test",
                    message=dict(content='{"answer":"unknown","abstain":true,"citations":[]}'),
                    done_reason="stop",
                    prompt_eval_count=10,
                    eval_count=5,
                    eval_duration=2_000_000_000,
                    load_duration=500_000_000,
                )
            ).encode()

    with patch.object(runner.urllib.request, "build_opener") as build:
        build.return_value.open.return_value = Response()
        result = runner.call("http://localhost:11434", "ollama", "local-test", [])
        payload = json.loads(build.return_value.open.call_args.args[0].data)
        assert payload["options"]["num_predict"] == 512
        assert result["usage"]["decode_seconds"] == 2
        assert result["usage"]["load_seconds"] == 0.5
        assert result["answer"]["abstain"] is True


def test_evidence_coverage_requires_full_interval():
    scoring = load("score_contexts")
    required = dict(file="a.py", start=10, end=15)
    assert scoring.covered(
        required, [dict(file="a.py", start=9, end=12), dict(file="a.py", start=13, end=20)]
    )
    assert not scoring.covered(
        required, [dict(file="a.py", start=10, end=12), dict(file="a.py", start=14, end=20)]
    )
    assert not scoring.covered(required, [dict(file="b.py", start=1, end=100)])


def test_evidence_alternatives_and_unanswerable():
    scoring = load("score_contexts")
    case = dict(
        id="a",
        repo="r",
        kind="behavior",
        answerable=True,
        essential_claims=[
            dict(
                id="a.1",
                evidence_mode="any",
                evidence=[dict(file="a.py", start=1, end=2), dict(file="a.py", start=8, end=9)],
            )
        ],
    )
    context = dict(
        mode="codectx",
        provided_spans=[dict(file="a.py", start=8, end=10)],
        context_characters=10,
        context_sha256="hash",
    )
    assert scoring.score(case, context)["all_required_evidence"]
    case.update(answerable=False, kind="unanswerable", essential_claims=[])
    assert scoring.score(case, context)["all_required_evidence"] is None


def test_citation_validity_is_not_semantic_support(tmp_path):
    scoring = load("score_contexts")
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n")
    context = dict(provided_spans=[dict(file="a.py", start=2, end=3)])
    valid = scoring.citation_geometry(dict(file="a.py", start=2, end=2), context, tmp_path)
    assert valid["valid_source_range"] and valid["within_supplied_evidence"]
    assert valid["semantic_support"] == "requires_review"
    assert not scoring.citation_geometry(
        dict(file="../outside", start=1, end=1), context, tmp_path
    )["valid_source_range"]
    assert not scoring.citation_geometry(dict(file="a.py", start=1, end=99), context, tmp_path)[
        "valid_source_range"
    ]


def test_model_judge_requires_unique_complete_claims():
    import sys

    import pytest

    with patch.dict(sys.modules, run_model=load("run_model")):
        judge = load("judge_model")
    case = dict(essential_claims=[dict(id="a.1"), dict(id="a.2")])
    value = dict(
        claims=[dict(id="a.1", verdict="correct"), dict(id="a.2", verdict="missing")],
        faithfulness="partial",
        citation_support="not_applicable",
        abstention_correct=False,
        brief_reason="One claim is missing.",
    )
    assert judge.parse_judgment(json.dumps(value), case)["faithfulness"] == "partial"
    value["claims"][1]["id"] = "a.1"
    with pytest.raises(ValueError, match="every required claim once"):
        judge.parse_judgment(json.dumps(value), case)


def test_context_report_preserves_human_review(tmp_path):
    scoring = load("score_contexts")
    results = tmp_path / "results"
    (results / "contexts").mkdir(parents=True)
    (tmp_path / "cases.reviewed.json").write_text(
        json.dumps(
            [dict(id="x", repo="r", kind="unanswerable", answerable=False, essential_claims=[])]
        )
    )
    contexts = [
        dict(
            case_id="x", mode=mode, provided_spans=[], context_characters=0, context_sha256="empty"
        )
        for mode in ["none", "bm25", "codectx", "gold"]
    ]
    (results / "contexts/r.jsonl").write_text("".join(json.dumps(c) + "\n" for c in contexts))
    existing = "case_id,reviewer,notes\nx,human,keep this annotation\n"
    (results / "answer-review.csv").write_text(existing)
    with patch.object(scoring, "BASE", tmp_path):
        scoring.main()
    assert (results / "answer-review.csv").read_text() == existing
    assert (results / "answer-review-template.csv").exists()
