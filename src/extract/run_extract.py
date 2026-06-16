from __future__ import annotations

import argparse
from pathlib import Path

from storage import INTERIM_DIR, RAW_DIR, extract_file, output_path_for


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract judgment text from downloaded Swiss Federal Court HTML."
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=RAW_DIR,
        help="Directory containing raw judgment HTML files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=INTERIM_DIR,
        help="Directory for extracted judgment JSON files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of HTML files to extract (0 = all).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing extracted JSON files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")

    processed = 0
    skipped = 0
    failed = 0

    for raw_html_path in sorted(args.raw_dir.rglob("*.html")):
        output_path = output_path_for(
            raw_html_path=raw_html_path,
            raw_dir=args.raw_dir,
            output_dir=args.output_dir,
        )
        if output_path.exists() and not args.force:
            skipped += 1
            continue

        if args.limit and processed >= args.limit:
            break

        try:
            extract_file(
                raw_html_path=raw_html_path,
                raw_dir=args.raw_dir,
                output_dir=args.output_dir,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"error {raw_html_path}: {exc}")
            continue

        processed += 1
        print(f"extracted {raw_html_path} -> {output_path}")

    print(f"Finished: processed={processed}, skipped={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
