#!/usr/bin/env python3
import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import FrameType
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from sentinel.evaluation import EvalConfig, EvaluationRunner, write_report  # noqa: E402
from sentinel.evaluation.baselines import BaselineConfig, run_baseline  # noqa: E402
from sentinel.evaluation.dataset import load_dataset, make_manifest  # noqa: E402
from sentinel.evaluation.replay import ReplayEngine  # noqa: E402
from sentinel.evaluation.runner import attach_baseline  # noqa: E402
from sentinel.semantic.base import SemanticEngine  # noqa: E402
from sentinel.semantic.engines.jev_direct import JevDirectEngine  # noqa: E402
from sentinel.settings.models import MODEL_ID  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit synthetic or adjudicated evaluation")
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "core/tests/fixtures/eval/dataset.jsonl"
    )
    parser.add_argument("--mode", choices=["real", "fixture"], default="real")
    parser.add_argument("--split", choices=["test", "tuning", "all"], default="test")
    parser.add_argument("--lang", choices=["zh", "en", "all"], default="all")
    parser.add_argument("--allow-tuned-test", action="store_true")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--engine", choices=["jev_direct"], default="jev_direct")
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--endpoint")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--no-cache", action="store_true", default=True)
    parser.add_argument("--out", type=Path, default=ROOT / "eval/reports/evaluation")
    parser.add_argument("--baselines", "--baseline", action="store_true")
    parser.add_argument("--make-manifest", type=Path, metavar="NEW_PATH")
    args = parser.parse_args(argv)
    try:
        if args.make_manifest:
            make_manifest(args.dataset, args.make_manifest, mode=args.mode)
            print("manifest written; provenance review required")
            return 0
        dataset = load_dataset(args.dataset, mode=args.mode)
        version = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
        config = EvalConfig(
            dataset,
            split=args.split,
            lang=args.lang,
            model_id=args.model_id,
            timeout_sec=args.timeout,
            allow_tuned_test=args.allow_tuned_test,
            gate=args.gate,
            code_version=version + ("+dirty" if dirty else ""),
        )
        engine = (
            ReplayEngine(args.replay, dataset, args.model_id)
            if args.replay
            else JevDirectEngine(
                model_id=args.model_id,
                api_key=os.environ.get("TYPESAFE_API_KEY"),
                **({"endpoint": args.endpoint} if args.endpoint else {}),
            )
        )
        baseline = BaselineConfig.from_env() if args.baselines else None
        if baseline is not None and args.split != "test":
            raise ValueError("baseline requires test split")
    except (ValueError, OSError, subprocess.SubprocessError):
        print("invalid dataset, provenance, manifest or configuration", file=sys.stderr)
        return 2
    runner = EvaluationRunner(config, cast(SemanticEngine, engine))

    def cancel(signum: int, frame: FrameType | None) -> None:
        runner.cancel.cancel()

    previous = {sig: signal.signal(sig, cancel) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        report = runner.run()
        if args.baselines:
            samples = [
                s
                for s in dataset.samples
                if s.split == "test" and (args.lang == "all" or s.lang == args.lang)
            ]
            attach_baseline(report, run_baseline(baseline, samples, cancel=runner.cancel))
        paths = write_report(report, args.out)
        print(
            f"samples={report.samples} completed={report.completed} failed={report.failed} "
            f"gold={report.gold_quality.status} gate={report.gate.status}"
        )
        print(f"report={paths.json}")
        return report.exit_code
    except OSError:
        print("report output unavailable", file=sys.stderr)
        return 4
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
