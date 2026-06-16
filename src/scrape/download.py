from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import UnicodeDammit

from discover import DiscoveredDecision


OUTPUT_ENCODING = "utf-8"


def make_html_digest(docid: str, url: str) -> str:
    source = docid or url
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def judgment_html_path(judgment_dir: Path, docid: str, url: str) -> Path:
    digest = make_html_digest(docid=docid, url=url)
    return judgment_dir / digest[:2] / f"{digest}.html"


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_html_bytes(content: bytes) -> bytes:
    decoded = UnicodeDammit(content, is_html=True).unicode_markup
    if decoded is None:
        decoded = content.decode(OUTPUT_ENCODING, errors="replace")
    return decoded.encode(OUTPUT_ENCODING)


def download_judgment(
    client: httpx.Client,
    decision: DiscoveredDecision,
    judgment_dir: Path,
    force: bool = False,
) -> dict[str, str | int | None]:
    output_path = judgment_html_path(
        judgment_dir=judgment_dir,
        docid=decision.docid,
        url=decision.url,
    )

    if output_path.exists() and not force:
        return {
            "status": "already_exists",
            "http_status": None,
            "raw_html_path": str(output_path),
            "content_hash": content_hash(output_path.read_bytes()),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "error_message": None,
        }

    response = client.get(decision.url)
    response.raise_for_status()
    normalized_content = normalize_html_bytes(response.content)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    temp_path.write_bytes(normalized_content)
    temp_path.replace(output_path)

    return {
        "status": "downloaded",
        "http_status": response.status_code,
        "raw_html_path": str(output_path),
        "content_hash": content_hash(normalized_content),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "error_message": None,
    }
