import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from sentinel.semantic.segment import split_sentences

from .models import Counts, EvalSample, Manifest, Mode, SplitCounts

LABEL_COUNTS = {"overturn": 4, "weaken": 7, "support": 5, "none": 14}
SUBSET_COUNTS = {"numeric": 5, "title_only": 3, "adversarial": 3, "long": 3, "multi_thesis": 3}


@dataclass(frozen=True)
class Dataset:
    samples: tuple[EvalSample, ...]
    manifest: Manifest
    mode: Mode


def read_samples(path: Path) -> tuple[EvalSample, ...]:
    try:
        return tuple(
            EvalSample.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    except (ValueError, OSError) as exc:
        raise ValueError("invalid dataset schema or file") from exc


def composition(samples: tuple[EvalSample, ...]) -> Counts:
    splits = {}
    for split in ("tuning", "test"):
        group = [s for s in samples if s.split == split]
        splits[split] = SplitCounts(
            total=len(group),
            labels=dict(Counter(s.label.relation for s in group)),
            languages=dict(Counter(s.lang for s in group)),
            subsets=dict(Counter(tag for s in group for tag in s.subsets)),
        )
    positives = sum(s.label.relation in ("weaken", "overturn") for s in samples)
    return Counts(
        total=len(samples), positive=positives, negative=len(samples) - positives, splits=splits
    )


def input_hash(sample: EvalSample) -> str:
    payload = sample.model_dump(include={"id", "instrument", "thesis", "passage"}, by_alias=True)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def validate_dataset(dataset: Dataset) -> None:
    samples, manifest = dataset.samples, dataset.manifest
    if {s.id for s in samples} != {f"p-{i:04d}" for i in range(1, 61)} or len(samples) != 60:
        raise ValueError("id must be unique p-0001..p-0060, including across splits")
    counts = composition(samples)
    if counts != manifest.counts or (counts.total, counts.positive, counts.negative) != (
        60,
        22,
        38,
    ):
        raise ValueError("manifest counts or positive ratio mismatch")
    for group in counts.splits.values():
        if (
            group.total != 30
            or group.labels != LABEL_COUNTS
            or group.languages != {"zh": 15, "en": 15}
            or group.subsets != SUBSET_COUNTS
        ):
            raise ValueError("split composition mismatch")
    if manifest.split_seed != 20261102 or not manifest.generation.strip():
        raise ValueError("manifest generation or split seed invalid")
    if dataset.mode == "fixture":
        if (
            manifest.source != "synthetic"
            or manifest.annotation_status != "unadjudicated"
            or manifest.annotator_ids
            or manifest.independent_annotation
        ):
            raise ValueError("fixture requires synthetic/unadjudicated source, no human claims")
    elif dataset.mode == "real":
        if (
            manifest.source != "human"
            or manifest.annotation_status != "adjudicated"
            or len(set(manifest.annotator_ids)) != 2
            or not manifest.independent_annotation
        ):
            raise ValueError("real mode requires human/adjudicated independent source")
    else:
        raise ValueError("unknown dataset mode")
    shared: dict[tuple[str, str, str], list[EvalSample]] = defaultdict(list)
    for sample in samples:
        if sample.label.relation == "overturn" and sample.event_state != "completed":
            raise ValueError("kill_met positive requires eventState=completed")
        if len(set(sample.subsets)) != len(sample.subsets):
            raise ValueError("duplicate subset")
        sentences = split_sentences(sample.passage.text)
        for label in [sample.label, *sample.annotators]:
            if label.evidence_sentence is not None and label.evidence_sentence > len(sentences):
                raise ValueError("evidenceSentence outside passage")
        if dataset.mode == "fixture":
            if sample.annotators or sample.adjudicated:
                raise ValueError("synthetic labels must remain unadjudicated without annotators")
        elif (
            not sample.adjudicated
            or len(sample.annotators) != 2
            or {a.id for a in sample.annotators} != set(manifest.annotator_ids)
        ):
            raise ValueError("unadjudicated or missing independent annotations")
        if ("title_only" in sample.subsets) != (sample.passage.content_status == "title_only"):
            raise ValueError("title_only subset mismatch")
        if ("long" in sample.subsets) != (len(sample.passage.text) > 800):
            raise ValueError("long subset mismatch")
        if "multi_thesis" in sample.subsets:
            shared[(sample.split, sample.instrument, sample.passage.event_id)].append(sample)
    for shared_group in shared.values():
        if (
            len(shared_group) < 2
            or len({s.passage.text for s in shared_group}) != 1
            or len({s.thesis.statement for s in shared_group}) != len(shared_group)
        ):
            raise ValueError("multi_thesis must share passage and use distinct theses")


def load_dataset(path: Path, *, mode: Mode = "real") -> Dataset:
    try:
        manifest = Manifest.model_validate_json(path.with_name("manifest.json").read_text())
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except (ValueError, OSError) as exc:
        raise ValueError("invalid manifest schema or file") from exc
    if actual_hash != manifest.sha256:
        raise ValueError("dataset hash mismatch")
    dataset = Dataset(read_samples(path), manifest, mode)
    validate_dataset(dataset)
    return dataset


def make_manifest(path: Path, out: Path, *, mode: Mode) -> Manifest:
    if mode != "fixture":
        raise ValueError("real provenance must be independently reviewed, never generated")
    samples = read_samples(path)
    ids = sorted({a.id for s in samples for a in s.annotators})
    manifest = Manifest(
        source="synthetic",
        annotation_status="unadjudicated",
        annotator_ids=ids,
        independent_annotation=False,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        split_seed=20261102,
        generation="manual controlled fixture; provenance requires human review",
        counts=composition(samples),
    )
    validate_dataset(Dataset(samples, manifest, mode))
    with out.open("x", encoding="utf-8") as stream:
        stream.write(manifest.model_dump_json(indent=2) + "\n")
    return manifest
