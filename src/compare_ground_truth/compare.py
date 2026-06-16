from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]


KEY_COLUMNS = ["docref", "date"]
IGNORED_COLUMNS = {"Unnamed: 0", *KEY_COLUMNS}
AUDIT_COLUMNS = [
    "html_id",
    "raw_html_path",
    "annotation_version",
    "model_name",
    "warnings",
]
DEFAULT_PREDICTIONS_PATH = Path("data/processed/scd_annotations.parquet")
DEFAULT_GROUND_TRUTH_PATH = Path("data/ground_truth/bger-2024-1.csv")
DEFAULT_COMPARISON_PATH = Path("data/processed/scd_ground_truth_comparison.parquet")
DEFAULT_MISMATCHES_PATH = Path("data/processed/scd_ground_truth_mismatches.csv")
DEFAULT_SUMMARY_PATH = Path("data/processed/scd_ground_truth_summary.csv")


@dataclass(frozen=True)
class ComparisonResult:
    comparison: pd.DataFrame
    mismatches: pd.DataFrame
    summary: pd.DataFrame


def is_missing(value: Any) -> bool:
    if pd.isna(value):
        return True
    if isinstance(value, str):
        return value.strip() in {"", "NA", "NaN", "nan", "<NA>"}
    return False


def normalize_value(value: Any) -> tuple[str, Any]:
    if is_missing(value):
        return ("missing", None)

    if isinstance(value, bool):
        return ("bool", value)

    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.casefold()
        if lowered == "true":
            return ("bool", True)
        if lowered == "false":
            return ("bool", False)
        numeric = pd.to_numeric(stripped, errors="coerce")
        if not pd.isna(numeric):
            numeric_float = float(numeric)
            if numeric_float.is_integer():
                return ("number", int(numeric_float))
            return ("number", numeric_float)
        return ("string", stripped)

    numeric = pd.to_numeric(value, errors="coerce")
    if not pd.isna(numeric):
        numeric_float = float(numeric)
        if numeric_float.is_integer():
            return ("number", int(numeric_float))
        return ("number", numeric_float)

    return ("string", str(value).strip())


def values_equal(predicted: Any, ground_truth: Any) -> bool:
    return normalize_value(predicted) == normalize_value(ground_truth)


def display_value(value: Any) -> str:
    kind, normalized = normalize_value(value)
    if kind == "missing":
        return ""
    return str(normalized)


def comparable_columns(predictions: pd.DataFrame, ground_truth: pd.DataFrame) -> list[str]:
    shared = set(predictions.columns).intersection(ground_truth.columns)
    return sorted(shared - IGNORED_COLUMNS)


def validate_keys(frame: pd.DataFrame, path_label: str) -> None:
    missing = [column for column in KEY_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"{path_label} is missing key columns: {missing}")
    duplicates = frame.duplicated(KEY_COLUMNS)
    if duplicates.any():
        duplicate_count = int(duplicates.sum())
        raise ValueError(
            f"{path_label} has {duplicate_count} duplicate rows for key {KEY_COLUMNS}"
        )


def compare_frames(
    predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
) -> ComparisonResult:
    validate_keys(predictions, "predictions")
    validate_keys(ground_truth, "ground truth")

    fields = comparable_columns(predictions, ground_truth)
    merged = predictions.merge(
        ground_truth.drop(columns=["Unnamed: 0"], errors="ignore"),
        on=KEY_COLUMNS,
        how="left",
        suffixes=("_pred", "_truth"),
        indicator=True,
    )
    matched = merged["_merge"] == "both"
    missing_ground_truth = int((merged["_merge"] == "left_only").sum())

    comparison = merged[KEY_COLUMNS].copy()
    for column in AUDIT_COLUMNS:
        if column in merged.columns:
            comparison[column] = merged[column]

    comparison["ground_truth_match_status"] = "matched"
    comparison.loc[~matched, "ground_truth_match_status"] = "missing_ground_truth"

    mismatch_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    mismatch_columns: list[str] = []

    for field in fields:
        pred_col = f"{field}_pred"
        truth_col = f"{field}_truth"
        mismatch_col = f"{field}_mismatch"
        mismatch_columns.append(mismatch_col)

        field_mismatches = []
        mismatch_count = 0
        matched_count = int(matched.sum())
        for index, row in merged.iterrows():
            if not matched.loc[index]:
                field_mismatches.append(pd.NA)
                continue
            is_mismatch = not values_equal(row[pred_col], row[truth_col])
            field_mismatches.append(is_mismatch)
            if is_mismatch:
                mismatch_count += 1
                mismatch_rows.append(
                    {
                        "docref": row["docref"],
                        "date": row["date"],
                        "field": field,
                        "predicted_value": display_value(row[pred_col]),
                        "ground_truth_value": display_value(row[truth_col]),
                        "html_id": row.get("html_id"),
                        "raw_html_path": row.get("raw_html_path"),
                    }
                )

        comparison[mismatch_col] = pd.Series(field_mismatches, dtype="boolean")
        match_count = matched_count - mismatch_count
        summary_rows.append(
            {
                "field": field,
                "matched_rows": matched_count,
                "matches": match_count,
                "match_rate": match_count / matched_count if matched_count else pd.NA,
                "mismatches": mismatch_count,
                "missing_ground_truth": missing_ground_truth,
            }
        )

    comparison["n_mismatched_fields"] = comparison[mismatch_columns].sum(
        axis=1,
        skipna=True,
    )
    mismatches = pd.DataFrame(
        mismatch_rows,
        columns=[
            "docref",
            "date",
            "field",
            "predicted_value",
            "ground_truth_value",
            "html_id",
            "raw_html_path",
        ],
    )
    summary = pd.DataFrame(summary_rows)
    summary = pd.concat(
        [
            summary,
            pd.DataFrame(
                [
                    {
                        "field": "__missing_ground_truth__",
                        "matched_rows": int(matched.sum()),
                        "matches": pd.NA,
                        "match_rate": pd.NA,
                        "mismatches": missing_ground_truth,
                        "missing_ground_truth": missing_ground_truth,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    return ComparisonResult(
        comparison=comparison,
        mismatches=mismatches,
        summary=summary,
    )


def load_predictions(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def load_ground_truth(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def write_result(
    result: ComparisonResult,
    comparison_path: Path,
    mismatches_path: Path,
    summary_path: Path,
) -> None:
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    mismatches_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    result.comparison.to_parquet(comparison_path, index=False)
    result.mismatches.to_csv(mismatches_path, index=False)
    result.summary.to_csv(summary_path, index=False)
