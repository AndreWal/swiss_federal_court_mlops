# Swiss Federal Court MLOps Pipeline

This repository is still work in progress. The current pipeline downloads raw
Swiss Federal Court HTML files, extracts the relevant judgment content, parses
some SCD codebook features, and compares those generated codings against an
existing ground-truth dataset that should be stored locally in
`data/ground_truth/`.

The feature pipeline is currently being built with deterministic parsing rules
first. The comparison against ground truth is used as the main diagnostic loop:
large disagreement clusters are inspected, parser rules are improved, and the
comparison is regenerated. Where deterministic rules are not sufficient, a small
local language model can be used to extract or classify additional semantic
features. Ollama is already configured as a Docker Compose service for this
purpose.

Once the feature pipeline is stable, the next step is a supervised machine
learning pipeline that predicts judgment outcomes as a classification task. That
model pipeline is planned to use MLflow for experiment tracking and model
management. In the final setup, new judgment data will be downloaded
continuously and model performance will be monitored over time.

## Pipeline

Minimal local deterministic pipeline:

```bash
make scrape
make extract
uv run src/annotate/run_annotate.py --limit 25
uv run src/compare_ground_truth/run_compare.py
```

Dockerized LLM pipeline:

```bash
make docker-up
make llm-setup
make annotate
make compare-ground-truth
```

`make annotate` runs inside Docker with Ollama enabled. For quick parser-only
checks, use `uv run src/annotate/run_annotate.py --limit 25`.

## Configuration

Python dependencies are managed with `uv`. Docker Compose reads local database
and pgAdmin settings from `.env`, which is intentionally ignored by Git. These
settings are included because the final processed dataset is intended to be
stored in a PostgreSQL database. pgAdmin is included as a local browser-based
tool for inspecting that database during development.

Use `.env.example` as the template for local configuration.

The current Compose file expects these keys:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`
- `DATABASE_URL`
- `PGADMIN_DEFAULT_EMAIL`
- `PGADMIN_DEFAULT_PASSWORD`
- `PGADMIN_PORT`

## Scraping

The scraping step discovers Federal Supreme Court judgments by querying the BGer
search endpoint date by date. It saves both the search result pages and the raw
judgment HTML.

```bash
make scrape
```

The Make target defaults to:

```bash
uv run src/scrape/run_scrape.py --start-date 01.07.2007 --end-date 23.06.2026 --sleep-seconds 2
```

Important scraper behavior:

- Dates can be passed as `YYYY-MM-DD` or `DD.MM.YYYY`.
- Search pages are written to `data/raw/search_pages/`.
- Existing search pages are reused by default, so reruns do not re-query BGer
  for dates/pages already saved locally. Pass `--refresh-search-pages` to
  re-fetch them.
- Judgment HTML files are written to `data/raw/judgments/<shard>/<digest>.html`.
- `data/raw/registry.jsonl` records `docid`, title, URL, decision date, raw path,
  content hash, status, and error information.
- Existing downloads are skipped unless `--force` is used.
- Failed downloads are skipped on later runs unless `--retry-errors` is used.
- If the registry says a judgment was downloaded but the HTML file is missing,
  the scraper treats it as missing and downloads it again.
- The default request delay is 2 seconds.

Useful local variants:

```bash
uv run src/scrape/run_scrape.py --start-date 2008-01-01 --end-date 2008-01-07
uv run src/scrape/run_scrape.py --start-date 2008-01-01 --end-date 2008-01-07 --limit 10
uv run src/scrape/run_scrape.py --start-date 2008-01-01 --end-date 2008-01-07 --retry-errors
uv run src/scrape/run_scrape.py --start-date 2026-06-10 --end-date 2026-06-16 --refresh-search-pages
```

The `make scrape` target accepts overrides:

```bash
make scrape SCRAPE_START=2026-06-10 SCRAPE_END=2026-06-16
make scrape SCRAPE_ARGS=--refresh-search-pages
make scrape SCRAPE_SLEEP=0.5
```

## Text Extraction

The extraction step converts downloaded HTML into normalized judgment text JSON.
It does not perform legal coding. It only prepares clean text and paragraphs for
the annotation stage.

```bash
make extract
```

The extractor reads from `data/raw/judgments/` and writes to
`data/interim/judgments_extracted/`, preserving the raw shard layout. For example:

```text
data/raw/judgments/00/example.html
data/interim/judgments_extracted/00/example.json
```

Each extracted JSON contains:

- `raw_html_path`
- `html_id`
- extraction version and CSS selectors used
- `paragraphs`
- newline-joined `text`
- paragraph and character counts
- extraction timestamp

Useful local variants:

```bash
uv run src/extract/run_extract.py --limit 25
uv run src/extract/run_extract.py --force
uv run src/extract/run_extract.py --raw-dir data/raw/judgments --output-dir data/interim/judgments_extracted
```

## Docker And Ollama

Ollama runs inside Docker Compose, not on the host. The `app` service talks to
Ollama at `http://ollama:11434`, and model files are stored in the persistent
`ollama_models` Docker volume.

```bash
make docker-up
make llm-setup
```

`make llm-setup` pulls `qwen3:0.6b` once into the Docker volume. The default app
environment uses:

- `OLLAMA_HOST=http://ollama:11434`
- `OLLAMA_MODEL=qwen3:0.6b`

## Main Commands

- `make scrape`: discover judgments, reuse cached search pages, and download missing raw HTML into `data/raw/`.
- `make extract`: convert raw HTML into LLM-ready text JSON in `data/interim/judgments_extracted/`.
- `make annotate`: annotate all extracted judgments inside Docker using Ollama.
- `make compare-ground-truth`: compare generated annotations with `data/ground_truth/bger-2024-1.csv`.
- `make llm-setup`: pull the default Ollama model into the persistent Docker volume.
- `make docker-down`: stop Docker services without deleting volumes.

For deterministic-only local development without a live Ollama service:

```bash
uv run src/annotate/run_annotate.py --limit 25
```

## Outputs

The raw, interim, processed, and ground-truth data folders are ignored by Git.
Keep the SCD ground-truth CSV locally at `data/ground_truth/bger-2024-1.csv`
and the codebook locally at `data/ground_truth/codebook-2024-1.pdf`.

- Raw HTML: `data/raw/judgments/`
- Cached search pages: `data/raw/search_pages/`
- Download registry: `data/raw/registry.jsonl`
- Extracted judgment text: `data/interim/judgments_extracted/`
- Per-judgment annotations: `data/interim/judgment_annotations/`
- Aggregate annotations: `data/processed/scd_annotations.parquet`
- Ground-truth row comparison: `data/processed/scd_ground_truth_comparison.parquet`
- Long-form mismatches: `data/processed/scd_ground_truth_mismatches.csv`
- Per-field match summary: `data/processed/scd_ground_truth_summary.csv`

## Ground-Truth Comparison

The comparison step joins generated annotations with the SCD ground truth using
`docref` and `date`. It flags every shared codebook field where the generated
coding differs from the ground truth. Predictions without a matching ground-truth
row are kept and marked as `missing_ground_truth`.

The ground-truth data and codebook used for this comparison come from:

> Geering, Florian, and Jakob Merane. 2024. *Swiss Federal Supreme Court Dataset
> (SCD).* Zenodo. https://doi.org/10.5281/zenodo.11092977

Run locally:

```bash
uv run src/compare_ground_truth/run_compare.py
```

Run through Docker:

```bash
make compare-ground-truth
```

### Current Comparison Summary

The current local comparison outputs are based on the current
`data/processed/scd_annotations.parquet`. The current local data directory
contains 142,556 raw HTML files, extracted text JSON files, per-case annotation
JSON files, and aggregate annotation rows. Of those annotated predictions in the
aggregate parquet:

- 142,556 predictions were compared.
- 121,975 rows matched a ground-truth row on `docref` and `date`.
- 20,581 rows had no matching ground-truth row and are marked as `missing_ground_truth`.
- The matched rows have 792,587 field-level mismatches across all compared columns.
- Exact-match fields in the matched subset: `division`, `division_type`,
  `doi_version`, `proc_type`, `year`.
- The earlier large `merged_cases` disagreement was caused by scanning the full
  judgment body for docket citations. The parser now only uses the judgment head,
  and `merged_cases` has 20 mismatches in the matched subset.
- Most unmatched rows are outside the released SCD ground-truth coverage. The
  matched ground-truth rows currently run through 2024-03-28, while 16,052
  unmatched rows are dated 2024 or later. Another 4,529 unmatched rows are
  earlier cases, concentrated in legacy-style docket numbers from 2006-2008 such
  as `2007.I_*`, `2007.U_*`, `1A_*`, `2P_*`, `4C_*`, `5P_*`, `6P_*`, and `6S_*`.
- The largest remaining substantive disagreements are in area labels, party
  representation/class labels, outcome nuance, topic/issue text, and BGE/BGer
  citation counts. `url` and `length` are intentionally omitted below because
  they are not useful substantive coding-quality indicators.

Selected match rates for substantively relevant variables:

| Field | Matches / Matched Rows | Match Rate |
| --- | ---: | ---: |
| `division` | 121,975 / 121,975 | 100.0% |
| `division_type` | 121,975 / 121,975 | 100.0% |
| `doi_version` | 121,975 / 121,975 | 100.0% |
| `proc_type` | 121,975 / 121,975 | 100.0% |
| `year` | 121,975 / 121,975 | 100.0% |
| `merged_cases` | 121,955 / 121,975 | 100.0% |
| `language` | 121,531 / 121,975 | 99.6% |
| `source_date` | 121,376 / 121,975 | 99.5% |
| `proc_duration` | 121,341 / 121,975 | 99.5% |
| `leading_case` | 117,984 / 121,975 | 96.7% |
| `source_canton` | 116,499 / 121,975 | 95.5% |
| `outcome_binary` | 115,454 / 121,975 | 94.7% |
| `n_judges` | 111,188 / 121,975 | 91.2% |
| `app_class` | 110,016 / 121,975 | 90.2% |
| `outcome` | 109,772 / 121,975 | 90.0% |
| `issue` | 108,889 / 121,975 | 89.3% |
| `app_represented` | 104,943 / 121,975 | 86.0% |
| `resp_represented` | 96,636 / 121,975 | 79.2% |
| `resp_class` | 93,928 / 121,975 | 77.0% |
| `topic` | 95,567 / 121,975 | 78.3% |
| `area_general` | 85,499 / 121,975 | 70.1% |
| `area_intermediate` | 70,699 / 121,975 | 58.0% |
| `cited_bger` | 86,481 / 121,975 | 70.9% |
| `area_detailed` | 65,784 / 121,975 | 53.9% |
| `n_cited_bger` | 60,992 / 121,975 | 50.0% |
| `n_cited_bge` | 49,924 / 121,975 | 40.9% |
| `cited_bge` | 48,152 / 121,975 | 39.5% |

These numbers are a diagnostic snapshot, not a full-dataset quality statement.
Regenerate them after a full annotation run with:

```bash
make annotate
make compare-ground-truth
```

## Tests

```bash
uv run pytest
uv run ruff check .
uv run mypy .
```
