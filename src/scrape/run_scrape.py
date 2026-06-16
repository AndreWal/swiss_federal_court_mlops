from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path
import time

import httpx

from discover import DiscoveredDecision, iter_discovered_decisions
from download import download_judgment
from registry import (
    RegistryIndex,
    append_registry_record,
    is_downloaded,
    is_error,
    load_registry_index,
    record_key,
)


HEADERS = {
    "User-Agent": "Mozilla/5.0 research-script/0.1",
}


def parse_date_arg(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid date '{value}'. Use YYYY-MM-DD or DD.MM.YYYY."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover Swiss Federal Court judgments and download raw HTML."
    )
    parser.add_argument(
        "--start-date",
        type=parse_date_arg,
        required=True,
        help="Start date (inclusive): YYYY-MM-DD or DD.MM.YYYY.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date_arg,
        required=True,
        help="End date (inclusive): YYYY-MM-DD or DD.MM.YYYY.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Raw data directory.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=2.0,
        help="Pause duration between network requests.",
    )
    parser.add_argument(
        "--max-pages-per-day",
        type=int,
        default=1000,
        help="Maximum search result pages to request for each date.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of judgment downloads for this run (0 = all).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload judgments even when the registry/file says they exist.",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retry judgments whose latest registry status is error.",
    )
    parser.add_argument(
        "--refresh-search-pages",
        action="store_true",
        help="Re-fetch search pages even when saved pages already exist.",
    )
    return parser.parse_args()


def registry_record(
    decision: DiscoveredDecision,
    result: dict[str, str | int | None],
) -> dict[str, str | int | None]:
    return {
        "docid": decision.docid,
        "title": decision.title,
        "url": decision.url,
        "status": result["status"],
        "http_status": result["http_status"],
        "raw_html_path": result["raw_html_path"],
        "content_hash": result["content_hash"],
        "decision_date": decision.decision_date.isoformat(),
        "search_page_path": decision.search_page_path,
        "scraped_at": result["scraped_at"],
        "error_message": result["error_message"],
        "source": decision.source,
        "language": decision.language,
        "court": decision.court,
    }


def error_record(
    decision: DiscoveredDecision,
    exc: Exception,
) -> dict[str, str | int | None]:
    return {
        "docid": decision.docid,
        "title": decision.title,
        "url": decision.url,
        "status": "error",
        "http_status": None,
        "raw_html_path": None,
        "content_hash": None,
        "decision_date": decision.decision_date.isoformat(),
        "search_page_path": decision.search_page_path,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "error_message": str(exc)[:2000],
        "source": decision.source,
        "language": decision.language,
        "court": decision.court,
    }


def has_existing_download(record: dict | None) -> bool:
    if not is_downloaded(record):
        return False

    raw_html_path = record.get("raw_html_path") if record is not None else None
    return isinstance(raw_html_path, str) and Path(raw_html_path).exists()


def should_download(
    decision: DiscoveredDecision,
    registry_index: RegistryIndex,
    force: bool,
    retry_errors: bool,
) -> bool:
    if force:
        return True

    latest = registry_index.get(decision.docid) or registry_index.get(decision.url)
    if has_existing_download(latest):
        return False

    if is_error(latest) and not retry_errors:
        return False

    return True


def validate_args(args: argparse.Namespace) -> None:
    if args.end_date < args.start_date:
        raise ValueError("--end-date must be on or after --start-date")
    if args.sleep_seconds < 0:
        raise ValueError("--sleep-seconds must be non-negative")
    if args.max_pages_per_day < 1:
        raise ValueError("--max-pages-per-day must be at least 1")
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")


def main() -> None:
    args = parse_args()
    validate_args(args)

    raw_dir = args.raw_dir
    search_dir = raw_dir / "search_pages"
    judgment_dir = raw_dir / "judgments"
    registry_path = raw_dir / "registry.jsonl"

    registry_index = load_registry_index(registry_path)
    print(f"Loaded {len(registry_index)} registry entries from {registry_path}")

    discovered_count = 0
    attempted_count = 0
    downloaded_count = 0
    skipped_count = 0
    error_count = 0

    with httpx.Client(
        http2=True,
        follow_redirects=True,
        headers=HEADERS,
        timeout=45.0,
    ) as client:
        for decision in iter_discovered_decisions(
            client=client,
            start_date=args.start_date,
            end_date=args.end_date,
            search_dir=search_dir,
            sleep_seconds=args.sleep_seconds,
            max_pages_per_day=args.max_pages_per_day,
            refresh_search_pages=args.refresh_search_pages,
        ):
            discovered_count += 1

            if not should_download(
                decision=decision,
                registry_index=registry_index,
                force=args.force,
                retry_errors=args.retry_errors,
            ):
                skipped_count += 1
                continue

            if args.limit and attempted_count >= args.limit:
                break

            attempted_count += 1
            try:
                result = download_judgment(
                    client=client,
                    decision=decision,
                    judgment_dir=judgment_dir,
                    force=args.force,
                )
                record = registry_record(decision=decision, result=result)
            except Exception as exc:  # noqa: BLE001
                error_count += 1
                record = error_record(decision=decision, exc=exc)

            append_registry_record(registry_path, record)
            key = record_key(record)
            if key is not None:
                registry_index[key] = record

            if record["status"] in {"downloaded", "already_exists"}:
                downloaded_count += 1

            print(
                f"{record['status']} {record['docid']} {record['raw_html_path']}"
            )

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    print(
        "Finished: "
        f"discovered={discovered_count}, "
        f"attempted={attempted_count}, "
        f"downloaded={downloaded_count}, "
        f"skipped={skipped_count}, "
        f"errors={error_count}"
    )


if __name__ == "__main__":
    main()
