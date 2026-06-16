from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


RegistryRecord = dict[str, Any]
RegistryIndex = dict[str, RegistryRecord]


def record_key(record: Mapping[str, Any]) -> str | None:
    docid = record.get("docid")
    if isinstance(docid, str) and docid:
        return docid

    url = record.get("url")
    if isinstance(url, str) and url:
        return url

    return None


def load_registry_index(path: Path) -> RegistryIndex:
    index: RegistryIndex = {}
    if not path.exists():
        return index

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL record at {path}:{line_number}") from exc

            key = record_key(record)
            if key is not None:
                index[key] = record

    return index


def append_registry_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")


def is_downloaded(record: Mapping[str, Any] | None) -> bool:
    if record is None:
        return False

    status = record.get("status")
    if status in {"downloaded", "already_exists"}:
        raw_html_path = record.get("raw_html_path")
        return isinstance(raw_html_path, str) and bool(raw_html_path)

    return False


def is_error(record: Mapping[str, Any] | None) -> bool:
    return record is not None and record.get("status") == "error"
