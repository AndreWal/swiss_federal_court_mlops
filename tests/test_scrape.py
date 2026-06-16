from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys


SCRAPE_DIR = Path(__file__).resolve().parents[1] / "src" / "scrape"
sys.path.insert(0, str(SCRAPE_DIR))

from discover import extract_judgment_links, iter_discovered_decisions, search_page_path  # noqa: E402
from download import judgment_html_path, make_html_digest, normalize_html_bytes  # noqa: E402
from registry import append_registry_record, load_registry_index  # noqa: E402
from run_scrape import has_existing_download, parse_date_arg, should_download  # noqa: E402


def test_parse_date_arg_accepts_iso_and_bger_formats() -> None:
    assert parse_date_arg("2015-09-01") == date(2015, 9, 1)
    assert parse_date_arg("01.09.2015") == date(2015, 9, 1)


def test_extract_judgment_links_from_saved_search_page() -> None:
    html_path = Path("data/raw/bger/search_pages/search_01.09.2015_01.09.2015_page_1.html")
    if not html_path.exists():
        html_path = next(Path("data/raw/search_pages").glob("search_*_page_*.html"))

    decisions = extract_judgment_links(
        html=html_path.read_text(encoding="utf-8"),
        base_url="https://search.bger.ch/ext/eurospider/live/de/php/aza/http/index.php",
        decision_date=date(2015, 9, 1),
        search_page_path_value=str(html_path),
    )

    assert decisions
    assert decisions[0].docid.startswith("aza://")
    assert decisions[0].url.startswith("https://search.bger.ch/")
    assert decisions[0].decision_date == date(2015, 9, 1)
    assert all("publiziert" not in decision.title.lower() for decision in decisions)


def test_iter_discovered_decisions_reuses_cached_search_page(tmp_path: Path) -> None:
    decision_date = date(2020, 1, 1)
    cached_page = search_page_path(tmp_path, decision_date, page=1)
    cached_page.parent.mkdir(parents=True, exist_ok=True)
    cached_page.write_text(
        '<a href="?type=show_document&highlight_docid=aza%3A%2F%2Fcached">'
        "01.01.2020 1C_1/2020</a>",
        encoding="utf-8",
    )

    class FailingClient:
        def get(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("cached discovery should not perform HTTP requests")

    decisions = list(
        iter_discovered_decisions(
            client=FailingClient(),  # type: ignore[arg-type]
            start_date=decision_date,
            end_date=decision_date,
            search_dir=tmp_path,
            max_pages_per_day=1,
        )
    )

    assert len(decisions) == 1
    assert decisions[0].docid == "aza://cached"


def test_judgment_html_path_is_deterministic_and_sharded() -> None:
    judgment_dir = Path("data/raw/bger/judgments")
    docid = "aza://01-09-2015-2C_988-2014"
    url = "https://example.test/judgment"
    digest = make_html_digest(docid=docid, url=url)

    path = judgment_html_path(judgment_dir=judgment_dir, docid=docid, url=url)

    assert path == judgment_dir / digest[:2] / f"{digest}.html"
    assert judgment_html_path(judgment_dir, docid, url) == path


def test_normalize_html_bytes_writes_valid_utf8() -> None:
    content = (
        b'<html><head><meta charset="UTF-8"></head>'
        b"<body>Bitte erkl\xe4ren Sie sich</body></html>"
    )

    normalized = normalize_html_bytes(content)

    assert normalized.decode("utf-8")
    assert "erklären" in normalized.decode("utf-8")


def test_load_registry_index_uses_latest_record_per_docid(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    append_registry_record(
        registry_path,
        {"docid": "aza://x", "status": "error", "url": "https://example.test/1"},
    )
    append_registry_record(
        registry_path,
        {"docid": "aza://x", "status": "downloaded", "url": "https://example.test/2"},
    )

    index = load_registry_index(registry_path)

    assert index["aza://x"]["status"] == "downloaded"
    assert index["aza://x"]["url"] == "https://example.test/2"


def test_load_registry_index_rejects_invalid_jsonl(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(json.dumps({"docid": "aza://x"}) + "\nnot-json\n", encoding="utf-8")

    try:
        load_registry_index(registry_path)
    except ValueError as exc:
        assert "Invalid JSONL record" in str(exc)
    else:
        raise AssertionError("Expected invalid JSONL to raise ValueError")


def test_has_existing_download_requires_file(tmp_path: Path) -> None:
    html_path = tmp_path / "judgment.html"
    record = {"status": "downloaded", "raw_html_path": str(html_path)}

    assert not has_existing_download(record)

    html_path.write_text("<html></html>", encoding="utf-8")
    assert has_existing_download(record)


def test_should_download_skips_downloaded_and_handles_errors(tmp_path: Path) -> None:
    html_path = tmp_path / "judgment.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    decision = extract_judgment_links(
        html='<a href="?type=show_document&highlight_docid=aza%3A%2F%2Fx">01.01.2020 1A 1/2020</a>',
        base_url="https://search.bger.ch/ext/eurospider/live/de/php/aza/http/index.php",
        decision_date=date(2020, 1, 1),
        search_page_path_value="search.html",
    )[0]

    downloaded_index = {
        decision.docid: {"status": "downloaded", "raw_html_path": str(html_path)}
    }
    error_index = {decision.docid: {"status": "error", "raw_html_path": None}}

    assert not should_download(decision, downloaded_index, force=False, retry_errors=False)
    assert should_download(decision, downloaded_index, force=True, retry_errors=False)
    assert not should_download(decision, error_index, force=False, retry_errors=False)
    assert should_download(decision, error_index, force=False, retry_errors=True)
