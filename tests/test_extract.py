from __future__ import annotations

import json
from pathlib import Path
import sys


EXTRACT_DIR = Path(__file__).resolve().parents[1] / "src" / "extract"
sys.path.insert(0, str(EXTRACT_DIR))

from extract import (  # noqa: E402
    build_extraction_record,
    extract_judgment_text,
)
from storage import (  # noqa: E402
    extract_file,
    output_path_for,
)


HTML = """
<html>
  <body>
    <div id="highlight_content" class="box">
      <div class="content">
        <div class="para">Tribunale federale&nbsp;</div>
        <div class="para">&nbsp;</div>
        <div class="para">Urteil vom 19. Januar 2007</div>
      </div>
    </div>
  </body>
</html>
"""


def test_extract_judgment_text_uses_highlight_content_paragraphs() -> None:
    assert extract_judgment_text(HTML) == (
        "Tribunale federale\nUrteil vom 19. Januar 2007"
    )


def test_build_extraction_record_contains_llm_ready_text() -> None:
    record = build_extraction_record(Path("data/raw/judgments/2b/example.html"), HTML)

    assert record["html_id"] == "example"
    assert record["paragraphs"] == [
        "Tribunale federale",
        "Urteil vom 19. Januar 2007",
    ]
    assert record["text"] == "Tribunale federale\nUrteil vom 19. Januar 2007"
    assert record["paragraph_count"] == 2
    assert record["char_count"] == len(record["text"])


def test_output_path_preserves_raw_shard_layout() -> None:
    path = output_path_for(
        raw_html_path=Path("data/raw/judgments/2b/2bebc96c115adc97.html"),
        raw_dir=Path("data/raw/judgments"),
        output_dir=Path("data/interim/judgments_extracted"),
    )

    assert path == Path("data/interim/judgments_extracted/2b/2bebc96c115adc97.json")


def test_extract_file_writes_json(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "judgments"
    output_dir = tmp_path / "interim" / "judgments_extracted"
    raw_html_path = raw_dir / "2b" / "example.html"
    raw_html_path.parent.mkdir(parents=True)
    raw_html_path.write_text(HTML, encoding="utf-8")

    output_path = extract_file(
        raw_html_path=raw_html_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
    )

    record = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_path == output_dir / "2b" / "example.json"
    assert record["raw_html_path"] == str(raw_html_path)
    assert record["text"] == "Tribunale federale\nUrteil vom 19. Januar 2007"
