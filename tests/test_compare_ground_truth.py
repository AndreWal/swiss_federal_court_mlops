from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pandas as pd  # type: ignore[import-untyped]


COMPARE_DIR = Path(__file__).resolve().parents[1] / "src" / "compare_ground_truth"
sys.path.insert(0, str(COMPARE_DIR))

from compare import compare_frames, values_equal  # noqa: E402


def test_normalization_treats_equivalent_values_as_equal() -> None:
    assert values_equal(None, float("nan"))
    assert values_equal("", "NA")
    assert values_equal(1, 1.0)
    assert values_equal("1", 1)
    assert values_equal(True, "TRUE")
    assert values_equal("  Public  ", "Public")
    assert not values_equal("Public", "public")


def test_compare_frames_flags_mismatches_and_unmatched_rows() -> None:
    predictions = pd.DataFrame(
        [
            {
                "docref": "1C_1/2020",
                "date": "2020-01-01",
                "year": 2020,
                "outcome": "rejected",
                "n_judges": 3,
                "html_id": "a",
                "raw_html_path": "raw/a.html",
            },
            {
                "docref": "1C_2/2020",
                "date": "2020-01-02",
                "year": 2020,
                "outcome": "granted",
                "n_judges": 1,
                "html_id": "b",
                "raw_html_path": "raw/b.html",
            },
        ]
    )
    ground_truth = pd.DataFrame(
        [
            {
                "Unnamed: 0": 1,
                "docref": "1C_1/2020",
                "date": "2020-01-01",
                "year": 2020.0,
                "outcome": "granted",
                "n_judges": 3.0,
            }
        ]
    )

    result = compare_frames(predictions=predictions, ground_truth=ground_truth)

    first = result.comparison.loc[0]
    second = result.comparison.loc[1]
    assert first["ground_truth_match_status"] == "matched"
    assert bool(first["outcome_mismatch"]) is True
    assert bool(first["year_mismatch"]) is False
    assert bool(first["n_judges_mismatch"]) is False
    assert first["n_mismatched_fields"] == 1

    assert second["ground_truth_match_status"] == "missing_ground_truth"
    assert pd.isna(second["outcome_mismatch"])
    assert second["n_mismatched_fields"] == 0

    assert len(result.mismatches) == 1
    mismatch = result.mismatches.iloc[0]
    assert mismatch["field"] == "outcome"
    assert mismatch["predicted_value"] == "rejected"
    assert mismatch["ground_truth_value"] == "granted"
    assert mismatch["html_id"] == "a"

    missing_summary = result.summary[
        result.summary["field"] == "__missing_ground_truth__"
    ].iloc[0]
    assert missing_summary["mismatches"] == 1

    outcome_summary = result.summary[result.summary["field"] == "outcome"].iloc[0]
    assert outcome_summary["matched_rows"] == 1
    assert outcome_summary["matches"] == 0
    assert outcome_summary["match_rate"] == 0.0
    assert "mismatch_rate" not in result.summary.columns


def test_compare_rejects_duplicate_keys() -> None:
    predictions = pd.DataFrame(
        [
            {"docref": "1C_1/2020", "date": "2020-01-01", "year": 2020},
            {"docref": "1C_1/2020", "date": "2020-01-01", "year": 2020},
        ]
    )
    ground_truth = pd.DataFrame(
        [{"docref": "1C_1/2020", "date": "2020-01-01", "year": 2020}]
    )

    try:
        compare_frames(predictions=predictions, ground_truth=ground_truth)
    except ValueError as exc:
        assert "duplicate rows" in str(exc)
    else:
        raise AssertionError("Expected duplicate keys to raise ValueError")


def test_run_compare_cli_writes_outputs(tmp_path: Path) -> None:
    predictions_path = tmp_path / "predictions.parquet"
    ground_truth_path = tmp_path / "ground_truth.csv"
    comparison_path = tmp_path / "comparison.parquet"
    mismatches_path = tmp_path / "mismatches.csv"
    summary_path = tmp_path / "summary.csv"

    pd.DataFrame(
        [
            {
                "docref": "1C_1/2020",
                "date": "2020-01-01",
                "year": 2020,
                "outcome": "rejected",
            }
        ]
    ).to_parquet(predictions_path, index=False)
    pd.DataFrame(
        [
            {
                "Unnamed: 0": 1,
                "docref": "1C_1/2020",
                "date": "2020-01-01",
                "year": 2020,
                "outcome": "granted",
            }
        ]
    ).to_csv(ground_truth_path, index=False)

    completed = subprocess.run(
        [
            sys.executable,
            "src/compare_ground_truth/run_compare.py",
            "--predictions-path",
            str(predictions_path),
            "--ground-truth-path",
            str(ground_truth_path),
            "--comparison-path",
            str(comparison_path),
            "--mismatches-path",
            str(mismatches_path),
            "--summary-path",
            str(summary_path),
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    assert "Compared predictions: 1" in completed.stdout
    assert comparison_path.exists()
    assert mismatches_path.exists()
    assert summary_path.exists()
    assert len(pd.read_parquet(comparison_path)) == 1
    assert len(pd.read_csv(mismatches_path)) == 1
    assert not pd.read_csv(summary_path).empty
