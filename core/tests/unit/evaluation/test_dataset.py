import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from sentinel.evaluation.dataset import load_dataset

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "eval"


def rewrite(tmp_path, mutate=None, manifest_mutate=None):
    data = [json.loads(line) for line in (FIXTURES / "dataset.jsonl").read_text().splitlines()]
    if mutate:
        mutate(data)
    path = tmp_path / "dataset.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data))
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest_mutate:
        manifest_mutate(manifest)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return path


def test_dataset_has_exact_composition():
    dataset = load_dataset(FIXTURES / "dataset.jsonl", mode="fixture")
    assert len(dataset.samples) == 60
    assert dataset.manifest.source == "synthetic"
    assert dataset.manifest.annotation_status == "unadjudicated"
    assert Counter(s.label.relation for s in dataset.samples) == {
        "overturn": 8,
        "weaken": 14,
        "support": 10,
        "none": 28,
    }
    for split in ("tuning", "test"):
        samples = [s for s in dataset.samples if s.split == split]
        assert len(samples) == 30
        assert Counter(s.lang for s in samples) == {"zh": 15, "en": 15}
        assert Counter(t for s in samples for t in s.subsets) == {
            "numeric": 5,
            "title_only": 3,
            "adversarial": 3,
            "long": 3,
            "multi_thesis": 3,
        }
        assert all(not s.annotators and not s.adjudicated for s in samples)
        assert all(
            (s.thesis.kill_condition is not None) == ("numeric" in s.subsets) for s in samples
        )
        assert {s.event_state for s in samples} >= {"planned", "cancelled", "completed"}


def test_real_dataset_rejects_unadjudicated_fixture():
    with pytest.raises(ValueError, match="source|adjudicat"):
        load_dataset(FIXTURES / "dataset.jsonl")


def test_dataset_rejects_tuning_test_overlap(tmp_path):
    path = rewrite(tmp_path, lambda rows: rows[30].update(id=rows[0]["id"]))
    with pytest.raises(ValueError, match="id"):
        load_dataset(path, mode="fixture")


@pytest.mark.parametrize("state", ["planned", "cancelled"])
def test_planned_sale_is_not_kill_met_positive(tmp_path, state):
    path = rewrite(tmp_path, lambda rows: rows[0].update(eventState=state))
    with pytest.raises(ValueError, match="completed"):
        load_dataset(path, mode="fixture")


def test_manifest_hash_change_is_rejected(tmp_path):
    path = rewrite(tmp_path)
    path.write_text(path.read_text().replace("Zenith", "ZENITH", 1))
    with pytest.raises(ValueError, match="hash"):
        load_dataset(path, mode="fixture")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: rows[0].update(lang="en"),
        lambda rows: rows[0].update(split="test"),
        lambda rows: rows[0]["thesis"].update(statement=" "),
        lambda rows: rows[0].update(unexpected=True),
        lambda rows: rows[0]["label"].update(evidenceSentence=999),
        lambda rows: rows[0].update(
            annotators=[{"id": "invented", "relation": "overturn", "evidenceSentence": 1}]
        ),
        lambda rows: rows[0].update(adjudicated=True),
        lambda rows: rows[0].update(subsets=[]),
    ],
)
def test_dataset_rejects_invalid_structure_or_composition(tmp_path, mutation):
    with pytest.raises(ValueError):
        load_dataset(rewrite(tmp_path, mutation), mode="fixture")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m: m.update(source="recorded"),
        lambda m: m.update(annotationStatus="adjudicated"),
        lambda m: m["counts"].update(total=59),
        lambda m: m["counts"].update(positive=21),
        lambda m: m.update(annotatorIds=["fake-a", "fake-b"]),
    ],
)
def test_manifest_source_and_counts_are_checked(tmp_path, mutation):
    with pytest.raises(ValueError):
        load_dataset(rewrite(tmp_path, manifest_mutate=mutation), mode="fixture")


def test_make_manifest_is_exclusive_and_never_generates_real_provenance(tmp_path):
    from sentinel.evaluation.dataset import make_manifest

    out = tmp_path / "review.json"
    manifest = make_manifest(FIXTURES / "dataset.jsonl", out, mode="fixture")
    assert manifest.source == "synthetic" and not manifest.independent_annotation
    with pytest.raises(FileExistsError):
        make_manifest(FIXTURES / "dataset.jsonl", out, mode="fixture")
    with pytest.raises(ValueError, match="reviewed"):
        make_manifest(FIXTURES / "dataset.jsonl", tmp_path / "real.json", mode="real")


def test_real_mode_still_rejects_unadjudicated_rows_with_changed_manifest(tmp_path):
    path = rewrite(
        tmp_path,
        manifest_mutate=lambda m: m.update(
            source="human",
            annotationStatus="adjudicated",
            independentAnnotation=True,
            annotatorIds=["declared-but-absent-1", "declared-but-absent-2"],
        ),
    )
    with pytest.raises(ValueError, match="unadjudicated"):
        load_dataset(path)
