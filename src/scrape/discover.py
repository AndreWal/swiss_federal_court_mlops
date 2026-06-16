from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import time
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://search.bger.ch/ext/eurospider/live/de/php/aza/http/index.php"
OUTPUT_ENCODING = "utf-8"


@dataclass(frozen=True)
class DiscoveredDecision:
    docid: str
    title: str
    url: str
    decision_date: date
    search_page_path: str
    source: str = "bger"
    language: str = "de"
    court: str = "BGer"


def iter_dates(start_date: date, end_date: date) -> Iterator[date]:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def format_bger_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def search_page_path(search_dir: Path, decision_date: date, page: int) -> Path:
    date_str = format_bger_date(decision_date)
    return search_dir / f"search_{date_str}_{date_str}_page_{page}.html"


def fetch_search_page(
    client: httpx.Client,
    decision_date: date,
    page: int,
    query_words: str = "",
) -> httpx.Response:
    date_str = format_bger_date(decision_date)
    params = {
        "lang": "de",
        "type": "simple_query",
        "query_words": query_words,
        "top_subcollection_aza": "all",
        "from_date": date_str,
        "to_date": date_str,
        "page": str(page),
    }

    response = client.get(BASE_URL, params=params)
    response.raise_for_status()
    return response


def extract_judgment_links(
    html: str,
    base_url: str,
    decision_date: date,
    search_page_path_value: str,
) -> list[DiscoveredDecision]:
    soup = BeautifulSoup(html, "lxml")
    results: list[DiscoveredDecision] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if "type=show_document" not in href and "highlight_docid" not in href:
            continue

        title = " ".join(link.get_text(" ", strip=True).split())
        if "publiziert" in title.lower():
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        query = parse_qs(parsed.query)
        docid = query.get("highlight_docid", [""])[0]
        if not docid:
            docid = full_url

        if docid in seen:
            continue

        seen.add(docid)
        results.append(
            DiscoveredDecision(
                docid=docid,
                title=title,
                url=full_url,
                decision_date=decision_date,
                search_page_path=search_page_path_value,
            )
        )

    return results


def iter_discovered_decisions(
    client: httpx.Client,
    start_date: date,
    end_date: date,
    search_dir: Path,
    sleep_seconds: float = 0.0,
    max_pages_per_day: int = 100,
    refresh_search_pages: bool = False,
) -> Iterator[DiscoveredDecision]:
    if max_pages_per_day < 1:
        raise ValueError("max_pages_per_day must be at least 1")

    search_dir.mkdir(parents=True, exist_ok=True)

    for decision_date in iter_dates(start_date, end_date):
        for page in range(1, max_pages_per_day + 1):
            output_path = search_page_path(search_dir, decision_date, page)
            if output_path.exists() and not refresh_search_pages:
                html = output_path.read_text(encoding=OUTPUT_ENCODING)
                base_url = BASE_URL
            else:
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

                response = fetch_search_page(
                    client=client,
                    decision_date=decision_date,
                    page=page,
                )
                html = response.text
                base_url = str(response.url)
                output_path.write_text(html, encoding=OUTPUT_ENCODING)

            decisions = extract_judgment_links(
                html=html,
                base_url=base_url,
                decision_date=decision_date,
                search_page_path_value=str(output_path),
            )
            if not decisions:
                break

            yield from decisions


def discover_decisions(
    client: httpx.Client,
    start_date: date,
    end_date: date,
    search_dir: Path,
    sleep_seconds: float = 0.0,
    max_pages_per_day: int = 100,
    refresh_search_pages: bool = False,
) -> list[DiscoveredDecision]:
    return list(
        iter_discovered_decisions(
            client=client,
            start_date=start_date,
            end_date=end_date,
            search_dir=search_dir,
            sleep_seconds=sleep_seconds,
            max_pages_per_day=max_pages_per_day,
            refresh_search_pages=refresh_search_pages,
        )
    )
