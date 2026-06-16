from __future__ import annotations

import argparse
from pathlib import Path

from compare import (
    DEFAULT_COMPARISON_PATH,
    DEFAULT_GROUND_TRUTH_PATH,
    DEFAULT_MISMATCHES_PATH,
    DEFAULT_PREDICTIONS_PATH,
    DEFAULT_SUMMARY_PATH,
    compare_frames,
    load_ground_truth,
    load_predictions,
    write_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare generated SCD annotations against the ground-truth dataset."
    )
    parser.add_argument(
        "--predictions-path",
        type=Path,
        default=DEFAULT_PREDICTIONS_PATH,
        help="Generated annotation parquet path.",
    )
    parser.add_argument(
        "--ground-truth-path",
        type=Path,
        default=DEFAULT_GROUND_TRUTH_PATH,
        help="Ground-truth SCD CSV path.",
    )
    parser.add_argument(
        "--comparison-path",
        type=Path,
        default=DEFAULT_COMPARISON_PATH,
        help="Output row-level comparison parquet path.",
    )
    parser.add_argument(
        "--mismatches-path",
        type=Path,
        default=DEFAULT_MISMATCHES_PATH,
        help="Output long-form mismatch CSV path.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help="Output per-field summary CSV path.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not args.predictions_path.exists():
        raise FileNotFoundError(f"Predictions file does not exist: {args.predictions_path}")
    if not args.ground_truth_path.exists():
        raise FileNotFoundError(
            f"Ground-truth file does not exist: {args.ground_truth_path}"
        )


def main() -> None:
    args = parse_args()
    validate_args(args)

    predictions = load_predictions(args.predictions_path)
    ground_truth = load_ground_truth(args.ground_truth_path)
    result = compare_frames(predictions=predictions, ground_truth=ground_truth)
    write_result(
        result=result,
        comparison_path=args.comparison_path,
        mismatches_path=args.mismatches_path,
        summary_path=args.summary_path,
    )

    missing = int(
        (result.comparison["ground_truth_match_status"] == "missing_ground_truth").sum()
    )
    print(f"Compared predictions: {len(result.comparison)}")
    print(f"Missing ground truth: {missing}")
    print(f"Mismatches: {len(result.mismatches)}")
    print(f"Wrote comparison: {args.comparison_path}")
    print(f"Wrote mismatches: {args.mismatches_path}")
    print(f"Wrote summary: {args.summary_path}")


if __name__ == "__main__":
    main()
