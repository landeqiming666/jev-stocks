from dataclasses import replace

import pytest


def thesis(ref="t1", kill="Sale exceeds 2%"):
    from sentinel.semantic.base import ThesisInput

    return ThesisInput(ref, ref, 1, "Controlling shareholder retains shares", kill, "hash")


def pairs():
    from sentinel.semantic.base import PairInput, PassageInput

    return [
        PairInput(thesis(ref), PassageInput(pid, "A disclosed fact.", pid))
        for ref in ("t1", "t2")
        for pid in ("p1", "p2", "p3")
    ]


def test_classify_truth_table_matches_document():
    from sentinel.domain.classify import Probabilities, classify, headline

    rows = [
        (0.97, 0.89, 0.84, 0.93, 0.03, "overturn", 0.93),
        (0.98, 0.92, 0.81, 0.88, 0.02, "overturn", 0.92),
        (0.95, 0.74, 0.41, None, 0.06, "weaken", 0.74),
        (0.93, 0.55, 0.22, 0.31, 0.18, "uncertain", 0.55),
        (0.58, 0.42, 0.20, 0.35, 0.10, "uncertain", 0.42),
        (0.29, 0.95, 0.90, 0.99, 0.01, "none", 0.99),
        (0.80, 0.10, 0.05, None, 0.85, "support", 0.10),
        (0.80, 0.10, 0.05, None, 0.50, "none", 0.10),
        (0.80, 0.30, 0.05, None, 0.85, "uncertain", 0.30),
        (0.80, 0.70, 0.05, None, 0.10, "weaken", 0.70),
        (0.30, 0.10, 0.05, None, 0.10, "none", 0.10),
        (0.80, 0.05, 0.75, None, 0.10, "overturn", 0.75),
        (0.80, 0.90, 0.05, None, 0.90, "weaken", 0.90),
    ]
    for relevant, against, contradicts, kill, supports, relation, value in rows:
        p = Probabilities(relevant, against, contradicts, kill, supports)
        assert (classify(p), headline(p)) == (relation, value)


def test_question_set_has_exact_five_noul_keys():
    from sentinel.semantic.questions import QUESTION_SET_VERSION, build_score_questions

    questions = build_score_questions([thesis()], flavor="direct")
    assert set(questions) == {
        "t1__relevant",
        "t1__against",
        "t1__contradicts",
        "t1__kill_met",
        "t1__supports",
    }
    assert all(q.type == "noul" for q in questions.values())
    assert QUESTION_SET_VERSION == "qs-2026-11-02.2"


def test_question_set_omits_kill_met_without_condition():
    from sentinel.semantic.questions import build_score_questions

    questions = build_score_questions([thesis(kill=None)], flavor="direct")
    assert len(questions) == 4 and "t1__kill_met" not in questions


def test_question_text_contains_no_numeric_thresholds():
    from sentinel.semantic.questions import build_evidence_questions, build_score_questions

    for flavor in ("direct", "jevdb"):
        questions = build_score_questions([thesis()], flavor=flavor)
        for relation in ("overturn", "weaken", "uncertain"):
            questions.update(build_evidence_questions(relation, 40, has_kill=True, flavor=flavor))
        for q in questions.values():
            text = q.instructions + q.true_text + q.false_text
            assert not any(t in text for t in ("%", "0.7", "0.3", "2%"))


def test_jevdb_templates_are_independent_not_direct_rewrites(monkeypatch):
    from sentinel.semantic import questions as q

    direct = q.build_score_questions([thesis()], flavor="direct")
    expected = q.build_score_questions([thesis()], flavor="jevdb")
    assert "theses.t1.thesis" in direct["t1__relevant"].instructions
    assert "`thesis`" in expected["t1__relevant"].instructions
    monkeypatch.setattr(q, "DIRECT_SCORE_TEMPLATES", {})
    monkeypatch.setattr(q, "PREFIX", "BROKEN DIRECT")
    assert q.build_score_questions([thesis()], flavor="jevdb") == expected


def test_auto_falls_back_once_when_jevdb_load_fails(monkeypatch):
    from sentinel.errors import EngineError
    from sentinel.messages import MESSAGES
    from sentinel.semantic.engines import EngineFactories, select_engine
    from tests.fakes.engine import FakeEngine

    reason = "未找到 JEVDB 扩展，已改用 Jev 直连（同一模型）"
    monkeypatch.setitem(MESSAGES, "engine.changed", reason)
    calls = []

    def db():
        calls.append("jevdb")
        raise EngineError("ENGINE_UNAVAILABLE")

    def direct():
        calls.append("jev_direct")
        return FakeEngine()

    selected = select_engine("auto", EngineFactories(db, direct))
    assert selected.engine.name == "jev_direct"
    assert selected.changed.reason == reason
    assert (selected.changed.from_engine, selected.changed.to_engine) == ("jevdb", "jev_direct")
    assert calls == ["jevdb", "jev_direct"]


def test_explicit_jevdb_never_falls_back():
    from sentinel.errors import EngineError
    from sentinel.semantic.engines import EngineFactories, select_engine

    error = EngineError("ENGINE_UNAVAILABLE")

    def db():
        raise error

    def direct():
        pytest.fail("unexpected fallback")

    with pytest.raises(EngineError) as exc:
        select_engine("jevdb", EngineFactories(db, direct))
    assert exc.value is error


def test_score_pairs_returns_exact_requested_count():
    from tests.fakes.engine import FakeCancelToken, FakeEngine

    requested = pairs()[:2] + pairs()[4:5]
    engine = FakeEngine()
    scores = engine.score_pairs("Zenith Arc Robotics Inc. (ZZAR)", requested, FakeCancelToken())
    assert [(s.thesis_id, s.passage_id) for s in scores] == [
        (p.thesis.thesis_id, p.passage.passage_id) for p in requested
    ]
    assert engine.requested_pairs == 3


def test_jevdb_templates_have_no_placeholders_or_foreign_paths():
    from sentinel.semantic.questions import build_evidence_questions, build_score_questions

    questions = build_score_questions([thesis()], flavor="jevdb")
    questions.update(build_evidence_questions("overturn", 3, has_kill=True, flavor="jevdb"))
    for q in questions.values():
        text = q.instructions + q.true_text + q.false_text
        assert not any(t in text for t in ("{", "}", "theses."))


def test_fake_engine_returns_one_pairscore_per_pair():
    from sentinel.semantic.base import CancelToken, SemanticEngine
    from tests.fakes.engine import FakeCancelToken, FakeEngine

    engine, token = FakeEngine(), FakeCancelToken()
    assert isinstance(engine, SemanticEngine) and isinstance(token, CancelToken)
    requested = pairs()
    scores = engine.score_event(
        "ZZAR", [thesis(), thesis("t2")], [p.passage for p in requested[:3]], token
    )
    assert len(scores) == 6 and engine.score_calls == 1 and engine.requested_pairs == 6
    assert scores[0].probabilities.kill_met is not None
    assert replace(scores[0], passage_id="other") != scores[0]


def test_direct_templates_match_reviewed_g0_snapshot():
    import ast
    from pathlib import Path

    from sentinel.semantic import questions as q

    source = Path(__file__).resolve().parents[4] / "scripts/probe_jev.py"
    snapshot = {}
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "PREFIX",
                    "PREFIX_E",
                    "QUESTIONS",
                    "QUESTION_SET_VERSION",
                ):
                    snapshot[target.id] = ast.literal_eval(node.value)
    assert snapshot["QUESTION_SET_VERSION"] == q.QUESTION_SET_VERSION
    assert snapshot["PREFIX"] == q.PREFIX and snapshot["PREFIX_E"] == q.PREFIX_E
    assert snapshot["QUESTIONS"] == q.DIRECT_SCORE_TEMPLATES
    for ref, kill in (("t1", None), ("t2", "Sale exceeds 2%")):
        for name, spec in q.build_score_questions([thesis(ref, kill)], flavor="direct").items():
            text, true, false = snapshot["QUESTIONS"][name.split("__")[1]]
            assert spec.instructions == (snapshot["PREFIX"] + " " + text).format(id=ref)
            assert (spec.true_text, spec.false_text) == (true, false)


def test_evidence_templates_match_g0_rendered_snapshot():
    import runpy
    from pathlib import Path

    from sentinel.semantic.questions import build_evidence_questions

    g0 = runpy.run_path(str(Path(__file__).resolve().parents[4] / "scripts/probe_jev.py"))
    for relation in ("overturn", "weaken", "uncertain"):
        for has_kill in (True, False):
            state = {"thesis": "Shareholder retains shares"}
            if has_kill:
                state["kill_condition"] = "Sale exceeds 2%"
            sample = g0["Sample"](
                "synthetic", "ZZAR", "One fact. Another fact.", {"t1": state}, relation
            )
            payload, spans = g0["evidence_request"](sample, "jev-1.14.0")
            specs = build_evidence_questions(
                relation, len(spans), has_kill=has_kill, flavor="direct"
            )
            assert {
                name: {
                    "type": s.type,
                    "instructions": s.instructions,
                    "criteria": {"true": s.true_text, "false": s.false_text},
                }
                for name, s in specs.items()
            } == payload["questions"]
            assert all("`" not in s.instructions for s in specs.values())


@pytest.mark.parametrize("field", ["relevant", "against", "contradicts", "kill_met", "supports"])
@pytest.mark.parametrize(
    "bad", [True, False, float("nan"), float("inf"), -float("inf"), -0.01, 1.01, "0.5", 10**400]
)
def test_probabilities_reject_invalid_numbers(field, bad):
    from sentinel.domain.classify import Probabilities

    values = dict(relevant=0.8, against=0.1, contradicts=0.1, kill_met=None, supports=0.9)
    values[field] = bad
    with pytest.raises(ValueError):
        Probabilities(**values)


@pytest.mark.parametrize(
    "yes,no",
    [
        (True, 0.3),
        (0.7, False),
        (float("nan"), 0.3),
        (0.7, float("inf")),
        (1.1, 0.3),
        (0.7, -0.1),
        (0.3, 0.3),
        (0.2, 0.3),
    ],
)
def test_threshold_validation(yes, no):
    from sentinel.domain.classify import Probabilities, classify

    with pytest.raises(ValueError):
        classify(Probabilities(0.8, 0.1, 0.1, None, 0.9), yes, no)


def test_none_kill_is_absent_even_at_zero_no_boundary():
    from sentinel.domain.classify import Probabilities, classify, headline

    p = Probabilities(1, 1, 1, None, 1)
    assert (classify(p, 1, 0), headline(p)) == ("overturn", 1)
    assert classify(Probabilities(1, 0.29, 0.29, None, 0.7)) == "support"
    assert classify(Probabilities(0.3, 0.1, 0.3, None, 0.9)) == "uncertain"
    assert classify(Probabilities(0.3, 0.1, 0.1, 0.7, 0.9)) == "overturn"


def test_input_limits_count_unicode_codepoints():
    from sentinel.semantic.base import PassageInput
    from sentinel.semantic.questions import build_evidence_questions, build_score_questions

    t = replace(thesis(), statement="😀" * 500, kill_condition="😀" * 300)
    assert (
        len(build_score_questions([replace(t, ref=f"t{i}") for i in range(1, 6)], flavor="direct"))
        == 25
    )
    assert len(PassageInput("p", "😀" * 1200, "hash").text) == 1200
    assert len(build_evidence_questions("overturn", 40, has_kill=True, flavor="direct")) == 40
    for kwargs in (
        {"statement": "a" * 501},
        {"statement": " "},
        {"kill_condition": "a" * 301},
        {"kill_condition": ""},
        {"ref": "t1\n"},
        {"ref": "t0"},
        {"version": True},
        {"version": 0},
    ):
        with pytest.raises(ValueError):
            replace(t, **kwargs)
    with pytest.raises(ValueError):
        PassageInput("p", "😀" * 1201, "hash")
    for ts in ([], [t, t], [replace(t, ref=f"t{i}") for i in range(1, 7)]):
        with pytest.raises(ValueError):
            build_score_questions(ts, flavor="direct")
    for count in (0, 41, True, 1.5):
        with pytest.raises(ValueError):
            build_evidence_questions("overturn", count, has_kill=True, flavor="direct")


def test_question_argument_and_name_validation():
    from sentinel.semantic.questions import (
        build_evidence_questions,
        build_score_questions,
        validate_question_name,
    )

    for name in ("t1__relevant", "s40"):
        validate_question_name(name)
    for name in ("t1__other", "t1__relevant\n", "s0", "s1\n", "t01__against"):
        with pytest.raises(ValueError):
            validate_question_name(name)
    with pytest.raises(ValueError):
        build_score_questions([thesis()], flavor="other")
    for relation, kill in (("support", True), ("none", True), ("overturn", 1)):
        with pytest.raises(ValueError):
            build_evidence_questions(relation, 1, has_kill=kill, flavor="direct")
    with pytest.raises(ValueError):
        build_evidence_questions("weaken", 1, has_kill=False, flavor="other")


def test_all_public_data_are_frozen_and_evidence_is_defensive():
    from copy import deepcopy
    from dataclasses import FrozenInstanceError, fields

    from sentinel.semantic import base, engine
    from sentinel.semantic.questions import QuestionSpec
    from tests.fakes.engine import FakeCancelToken, FakeEngine

    pair = pairs()[0]
    values = [0.1, 0.9]
    evidence = base.EvidenceScore(values, "jev-1.14.0", 10, False)
    values[0] = 0.8
    assert evidence.sentence_probabilities == [0.1, 0.9]
    assert deepcopy(evidence) == evidence
    for mutate in (
        lambda: evidence.sentence_probabilities.append(0.5),
        lambda: evidence.sentence_probabilities.__setitem__(0, 0.5),
        lambda: evidence.sentence_probabilities.__iadd__([0.5]),
    ):
        with pytest.raises(TypeError):
            mutate()
    score = FakeEngine().score_pairs("ZZAR", [pair], FakeCancelToken())[0]
    for obj in (
        pair.thesis,
        pair.passage,
        pair,
        score,
        evidence,
        score.probabilities,
        base.EngineHealth("ok", ""),
        QuestionSpec("i", "t", "f"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, fields(obj)[0].name, None)
    for name in engine.__all__:
        assert getattr(engine, name) is getattr(base, name)
    assert [f.name for f in fields(base.PairScore)] == [
        "thesis_id",
        "version",
        "passage_id",
        "probabilities",
        "model_id",
        "input_tokens",
        "tokens_estimated",
        "latency_ms",
    ]
    with pytest.raises(ValueError):
        base.EvidenceScore([float("nan")], "jev-1.14.0", 1, False)
    with pytest.raises(ValueError):
        replace(score, input_tokens=True)


@pytest.mark.parametrize(
    "code", ["UNAUTHENTICATED", "MODEL_ERROR", "RATE_LIMITED", "TIMEOUT", "BUDGET_EXCEEDED"]
)
def test_auto_preserves_other_errors(code):
    from sentinel.errors import EngineError
    from sentinel.semantic.engines import EngineFactories, select_engine

    error = EngineError(code)

    def db():
        raise error

    with pytest.raises(EngineError) as exc:
        select_engine("auto", EngineFactories(db, lambda: pytest.fail("unexpected direct")))
    assert exc.value is error


def test_selection_success_and_direct_failure_do_not_retry():
    from sentinel.errors import UserError
    from sentinel.semantic.engines import EngineFactories, select_engine
    from tests.fakes.engine import FakeEngine

    db_engine, direct_engine = FakeEngine(name="jevdb"), FakeEngine()
    factories = EngineFactories(lambda: db_engine, lambda: direct_engine)
    assert select_engine("auto", factories).engine is db_engine
    assert select_engine("auto", factories).changed is None
    assert select_engine("jev_direct", factories).engine is direct_engine
    with pytest.raises(ValueError):
        select_engine("other", factories)
    error = UserError("CONFIG_REQUIRED")

    def direct():
        raise error

    with pytest.raises(UserError) as exc:
        select_engine("jev_direct", EngineFactories(lambda: pytest.fail("unexpected db"), direct))
    assert exc.value is error


def test_missing_engine_change_message_is_explicit_cr_blocker():
    from sentinel.errors import EngineError
    from sentinel.messages import MESSAGES, MessageKeyError
    from sentinel.semantic.engines import EngineFactories, select_engine
    from tests.fakes.engine import FakeEngine

    def db():
        raise EngineError("ENGINE_UNAVAILABLE")

    if "engine.changed" not in MESSAGES:
        with pytest.raises(MessageKeyError, match="engine.changed"):
            select_engine("auto", EngineFactories(db, FakeEngine))
    else:
        assert (
            select_engine("auto", EngineFactories(db, FakeEngine)).changed.reason
            == MESSAGES["engine.changed"]
        )


def test_fake_failure_cancellation_and_evidence_counters():
    from sentinel.errors import CancelledError, EngineError
    from tests.fakes.engine import FakeCancelToken, FakeEngine

    token = FakeCancelToken(True)
    engine = FakeEngine()
    with pytest.raises(CancelledError):
        engine.score_pairs("ZZAR", pairs(), token)
    assert engine.score_calls == engine.requested_pairs == 0
    token.cancelled = False
    engine = FakeEngine(before_pair=lambda i: token.cancel() if i == 1 else None)
    with pytest.raises(CancelledError):
        engine.score_pairs("ZZAR", pairs(), token)
    assert engine.requested_pairs == 6 and engine.completed_pairs == 1
    partial = FakeEngine(fail_after=2)
    with pytest.raises(EngineError, match="MODEL_ERROR"):
        partial.score_pairs("ZZAR", pairs(), FakeCancelToken())
    assert (partial.score_calls, partial.requested_pairs, partial.completed_pairs) == (1, 6, 2)
    error = EngineError("TIMEOUT")
    engine = FakeEngine(error=error, evidence_error=error)
    with pytest.raises(EngineError) as exc:
        engine.score_pairs("ZZAR", pairs()[:1], FakeCancelToken())
    assert exc.value is error
    with pytest.raises(EngineError) as exc:
        engine.locate_evidence(thesis(), "weaken", ["A fact."], FakeCancelToken())
    assert exc.value is error and engine.evidence_calls == 1
    ok = FakeEngine(name="jevdb")
    result = ok.locate_evidence(
        thesis(), "overturn", ["A fact.", "Another fact."], FakeCancelToken()
    )
    assert result.sentence_probabilities == [0.9, 0.9] and result.tokens_estimated
    assert ok.evidence_calls == 1
