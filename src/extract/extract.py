from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Tag


EXTRACTION_VERSION = "v1"
JUDGMENT_SELECTOR = "#highlight_content > .content"
PARAGRAPH_SELECTOR = "div.para"


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def select_judgment_content(soup: BeautifulSoup) -> Tag:
    content = soup.select_one(JUDGMENT_SELECTOR)
    if content is None:
        raise ValueError(f"Could not find judgment content: {JUDGMENT_SELECTOR}")
    return content


def extract_judgment_paragraphs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    content = select_judgment_content(soup)

    paragraphs = [
        normalize_text(paragraph.get_text(" ", strip=True))
        for paragraph in content.select(PARAGRAPH_SELECTOR)
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]

    if paragraphs:
        return paragraphs

    fallback = normalize_text(content.get_text(" ", strip=True))
    return [fallback] if fallback else []


def extract_judgment_text(html: str) -> str:
    return "\n".join(extract_judgment_paragraphs(html)).strip()


def build_extraction_record(raw_html_path: Path, html: str) -> dict[str, object]:
    paragraphs = extract_judgment_paragraphs(html)
    text = "\n".join(paragraphs).strip()

    return {
        "raw_html_path": str(raw_html_path),
        "html_id": raw_html_path.stem,
        "extraction_version": EXTRACTION_VERSION,
        "selector": JUDGMENT_SELECTOR,
        "paragraph_selector": PARAGRAPH_SELECTOR,
        "paragraphs": paragraphs,
        "text": text,
        "paragraph_count": len(paragraphs),
        "char_count": len(text),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
