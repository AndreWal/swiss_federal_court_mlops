from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path

from constants import ANNOTATION_VERSION
from models import AnnotationRecord
from ollama_client import OllamaClient, apply_llm_classification
from parsers import build_base_annotation
from annotation_storage import (
    ANNOTATION_DIR,
    EXTRACTED_DIR,
    PROCESSED_PATH,
    annotation_path_for,
    load_registry_by_raw_path,
    read_extracted_record,
    write_aggregate,
    write_annotation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Annotate extracted Swiss Federal Court judgments with SCD codebook variables."
    )
    parser.add_argument(
        "--extracted-dir",
        type=Path,
        default=EXTRACTED_DIR,
        help="Directory containing extracted judgment JSON files.",
    )
    parser.add_argument(
        "--annotation-dir",
        type=Path,
        default=ANNOTATION_DIR,
        help="Directory for per-judgment annotation JSON files.",
    )
    parser.add_argument(
        "--processed-path",
        type=Path,
        default=PROCESSED_PATH,
        help="Path for aggregate parquet output.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of judgments to annotate (0 = all).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing annotation JSON files.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Call Ollama for ambiguous semantic fields.",
    )
    parser.add_argument(
        "--ollama-host",
        default=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama HTTP endpoint.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OLLAMA_MODEL", "qwen3:0.6b"),
        help="Ollama model name.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")
    if not args.extracted_dir.exists():
        raise FileNotFoundError(f"Extracted directory does not exist: {args.extracted_dir}")


def needs_llm(annotation: dict[str, object]) -> bool:
    return any(
        annotation.get(field) is None
        for field in ("area_detailed", "app_class", "resp_class", "outcome")
    )


def build_annotation_record(
    extracted_path: Path,
    registry_by_raw_path: dict[str, dict[str, object]],
    llm_client: OllamaClient | None,
    model_name: str | None,
) -> AnnotationRecord:
    extracted_record = read_extracted_record(extracted_path)
    raw_html_path = extracted_record.get("raw_html_path")
    registry_record = (
        registry_by_raw_path.get(raw_html_path) if isinstance(raw_html_path, str) else None
    )

    annotation = build_base_annotation(
        extracted_record=extracted_record,
        registry_record=registry_record,
    )
    llm_context = annotation.pop("_llm_context")
    annotation["annotation_version"] = ANNOTATION_VERSION
    annotation["model_name"] = model_name if llm_client is not None else None
    annotation.setdefault("confidence", {})

    if llm_client is not None and needs_llm(annotation):
        try:
            classification = llm_client.classify(llm_context)
        except Exception as exc:  # noqa: BLE001
            annotation.setdefault("warnings", []).append(f"llm_failed:{str(exc)[:160]}")
        else:
            apply_llm_classification(annotation, classification)

    annotation.setdefault("evidence", {})["annotated_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    return AnnotationRecord(**annotation)


def main() -> None:
    args = parse_args()
    validate_args(args)

    registry_by_raw_path = load_registry_by_raw_path()
    llm_client = (
        OllamaClient(host=args.ollama_host, model=args.model) if args.use_llm else None
    )

    processed = 0
    skipped = 0
    failed = 0
    records: list[AnnotationRecord] = []

    for extracted_path in sorted(args.extracted_dir.rglob("*.json")):
        if args.limit and processed >= args.limit:
            break

        output_path = annotation_path_for(
            extracted_path=extracted_path,
            extracted_dir=args.extracted_dir,
            annotation_dir=args.annotation_dir,
        )
        if output_path.exists() and not args.force:
            try:
                records.append(AnnotationRecord.model_validate_json(output_path.read_text()))
            except Exception:  # noqa: BLE001
                pass
            skipped += 1
            continue

        try:
            record = build_annotation_record(
                extracted_path=extracted_path,
                registry_by_raw_path=registry_by_raw_path,
                llm_client=llm_client,
                model_name=args.model,
            )
            write_annotation(output_path, record)
            records.append(record)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"error {extracted_path}: {exc}")
            continue

        processed += 1
        print(f"annotated {extracted_path} -> {output_path}")

    if records:
        write_aggregate(records, args.processed_path)

    print(f"Finished: processed={processed}, skipped={skipped}, failed={failed}")
    if records:
        print(f"Wrote aggregate: {args.processed_path}")


if __name__ == "__main__":
    main()
