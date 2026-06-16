from __future__ import annotations

import json
from pathlib import Path

from extract import build_extraction_record


RAW_DIR = Path("data/raw/judgments")
INTERIM_DIR = Path("data/interim/judgments_extracted")


def output_path_for(
    raw_html_path: Path,
    raw_dir: Path = RAW_DIR,
    output_dir: Path = INTERIM_DIR,
) -> Path:
    relative_path = raw_html_path.relative_to(raw_dir)
    return output_dir / relative_path.with_suffix(".json")


def write_extraction_record(output_path: Path, record: dict[str, object]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    temp_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(output_path)


def extract_file(raw_html_path: Path, raw_dir: Path, output_dir: Path) -> Path:
    html = raw_html_path.read_text(encoding="utf-8")
    record = build_extraction_record(raw_html_path=raw_html_path, html=html)
    output_path = output_path_for(
        raw_html_path=raw_html_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
    )
    write_extraction_record(output_path=output_path, record=record)
    return output_path
