from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from constants import SCD_COLUMNS
from models import AnnotationRecord


EXTRACTED_DIR = Path("data/interim/judgments_extracted")
ANNOTATION_DIR = Path("data/interim/judgment_annotations")
PROCESSED_PATH = Path("data/processed/scd_annotations.parquet")
REGISTRY_PATH = Path("data/raw/registry.jsonl")


def load_registry_by_raw_path(path: Path = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL record at {path}:{line_number}") from exc
            raw_html_path = record.get("raw_html_path")
            if isinstance(raw_html_path, str) and raw_html_path:
                records[raw_html_path] = record
    return records


def annotation_path_for(
    extracted_path: Path,
    extracted_dir: Path = EXTRACTED_DIR,
    annotation_dir: Path = ANNOTATION_DIR,
) -> Path:
    relative_path = extracted_path.relative_to(extracted_dir)
    return annotation_dir / relative_path


def read_extracted_record(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_annotation(path: Path, record: AnnotationRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(
        record.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def write_aggregate(
    records: list[AnnotationRecord],
    output_path: Path = PROCESSED_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        row = record.scd_row()
        row.update(
            {
                "html_id": record.html_id,
                "raw_html_path": record.raw_html_path,
                "annotation_version": record.annotation_version,
                "model_name": record.model_name,
                "warnings": ";".join(record.warnings),
            }
        )
        rows.append(row)

    columns = [
        *SCD_COLUMNS,
        "html_id",
        "raw_html_path",
        "annotation_version",
        "model_name",
        "warnings",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    frame.to_parquet(temp_path, index=False)
    temp_path.replace(output_path)
