import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .metrics import GOLD_CLASSES, PREDICTED_CLASSES
from .models import EvalReport


@dataclass(frozen=True)
class ReportPaths:
    markdown: Path
    json: Path
    predictions: Path


def redact_text(text: str) -> str:
    # 通用脱敏会屏蔽 SHA；评测必须保留可复核哈希，只清除环境密钥和认证文本。
    secrets = [
        os.environ.get(key, "")
        for key in ("TYPESAFE_API_KEY", "JEV_API_KEY", "EVAL_BASELINE_API_KEY")
    ]
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        text = text.replace(secret, "REDACTED")
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "REDACTED", text)
    return re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer REDACTED", text)


def write_report(report: EvalReport, out_dir: Path) -> ReportPaths:
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        out_dir = out_dir / (report.date.replace(":", "-") + "-" + uuid4().hex)
        out_dir.mkdir(parents=True, exist_ok=False)
    paths = ReportPaths(
        out_dir / "report.md", out_dir / "report.json", out_dir / "predictions.jsonl"
    )
    lines = [
        "# Evaluation report",
        "",
        f"Source: {report.source}/{report.annotation_status}; "
        f"predictions: {report.prediction_source}.",
        f"Gold quality: {report.gold_quality.status}; kappa: {report.gold_quality.kappa}.",
        f"Real model verification: {report.real_model_status}. Baseline: {report.baseline.status}.",
        f"Gate: {report.gate.status}; passed: {report.gate.passed}; "
        f"experiment: {report.gate.experimental_passed}.",
        f"Date: {report.date}; code: {report.code_version}; "
        f"dataset SHA-256: {report.dataset_hash}.",
        f"Engine: {report.engine}; model: {report.model_id}; "
        f"questions: {report.question_set_version}; "
        f"thresholds: {report.thresholds}; split: {report.split}; language: {report.lang}.",
        f"Samples: {report.samples}; completed: {report.completed}; failed: {report.failed}.",
        f"Calls: {report.usage.calls}; input tokens: {report.usage.input_tokens}; "
        f"output tokens: {report.usage.output_tokens}; cost USD: {report.usage.cost_usd:.6f}.",
        f"Usage complete: {report.usage.complete}; estimated: {report.usage.estimated}.",
        f"Usage basis: {report.usage_basis}; pricing: {report.pricing_verification}.",
        f"Price snapshot: {report.pricing}.",
        "",
        *report.warnings,
        "",
        "| Group / policy | n | positives | Precision (Wilson) | "
        "Recall (Wilson) | F1 (bootstrap) |",
        "|---|---:|---:|---|---|---|",
    ]
    pairs = {
        "all": (report.strict, report.lenient),
        **{k: (v.strict, v.lenient) for k, v in report.by_lang.items()},
        **{k: (v.strict, v.lenient) for k, v in report.by_subset.items()},
    }
    for group, policies in pairs.items():
        for policy, metrics in zip(("strict", "lenient"), policies, strict=True):
            lines.append(
                f"| {group}/{policy} | {metrics.n} | {metrics.positive_count} | "
                f"{metrics.precision} {metrics.precision_ci} | "
                f"{metrics.recall} {metrics.recall_ci} | "
                f"{metrics.f1} {metrics.f1_ci} |"
            )
    lines += [
        "",
        "Gold x predicted confusion matrix:",
        "",
        "| Gold | " + " | ".join(PREDICTED_CLASSES) + " |",
        "|---|" + "---:|" * len(PREDICTED_CLASSES),
    ]
    for label, values in zip(GOLD_CLASSES, report.strict.matrix, strict=True):
        lines.append("| " + label + " | " + " | ".join(map(str, values)) + " |")
    lines += [
        "",
        f"Uncertain: {report.uncertain_count}/{report.completed} ({report.uncertain_rate}).",
        f"Evidence: {json.dumps(report.evidence)}.",
        f"Baseline: {report.baseline.model_dump_json(exclude={'rows'})}.",
        f"Gate reason: {report.gate.reason}.",
        "",
        "Failures and unrun samples:",
        "",
    ]
    lines.extend(f"- {r.id}: {r.status}/{r.error}" for r in report.rows if r.status != "ok")
    with paths.json.open("x", encoding="utf-8") as stream:
        stream.write(redact_text(report.model_dump_json(indent=2)) + "\n")
    with paths.markdown.open("x", encoding="utf-8") as stream:
        stream.write(redact_text("\n".join(lines)) + "\n")
    with paths.predictions.open("x", encoding="utf-8") as stream:
        stream.write("".join(redact_text(r.model_dump_json()) + "\n" for r in report.rows))
    return paths
