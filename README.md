# Africa Financials Extraction

A financial data engineering project for turning African listed-company reports into structured, analysis-ready financial metrics.

The current prototype combines digital PDF parsing, table extraction, OCR fallback, metric matching, balance-sheet validation, and CSV/Excel export.

## Problem

Financial statements across African markets are frequently published as PDFs with inconsistent layouts, scanned pages, and exchange-specific reporting formats. This makes cross-company screening and analysis difficult to automate.

This project explores a reusable extraction pipeline that converts those reports into structured data for analysts, researchers, and downstream financial applications.

## Current pipeline

```text
Annual / quarterly report PDF
          |
          v
PyMuPDF text blocks
          |
          +------> Camelot table extraction
          |
          +------> Tesseract OCR fallback
          |
          v
Metric matching and normalization
          |
          v
Balance-sheet consistency check
          |
          v
CSV + multi-sheet Excel output
```

## Metrics currently targeted

- Total revenue
- Net income / profit after tax
- Total assets
- Total liabilities
- Shareholders' equity

The extractor searches common reporting-language variants such as revenue, turnover, sales, net income, profit after tax, and equity.

## Implemented components

- Digital PDF block extraction with PyMuPDF
- Table extraction with Camelot
- OCR fallback with Tesseract and PyMuPDF
- Regex-based financial metric matching
- CSV output for extracted metrics
- Multi-sheet Excel export containing metrics, text blocks, tables, and summary data
- Basic accounting-equation validation for assets versus liabilities plus equity
- Sample financial reports and structured output files for experimentation

## Run locally

```bash
git clone https://github.com/adejumotosin/africa-financials-extraction.git
cd africa-financials-extraction

python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Place financial reports in `raw_data/`, then run:

```bash
python semantic_financial_extractor.py
```

Generated outputs are written to `processed/`.

## Data sources and market scope

The broader project is designed around publicly available listed-company reports from African exchanges, including markets such as:

- Nigerian Exchange Group
- Nairobi Securities Exchange
- Johannesburg Stock Exchange

Exchange websites and individual issuer filings should be checked for their applicable terms and redistribution rules before automated collection at scale.

## Current limitations

This repository is a prototype rather than a production financial-data service.

- Regex-based nearby-number extraction can associate the wrong value with a metric in complex statements.
- Table structures differ substantially between issuers and reporting periods.
- OCR accuracy depends on scan quality.
- Currency, units, period alignment, restatements, and consolidated-versus-separate statements require stronger normalization.
- Extracted values should be verified against the source report before analytical or investment use.

## Roadmap

1. Add page-level and table-level provenance for every extracted value.
2. Introduce statement-aware parsing for income statement, balance sheet, and cash-flow tables.
3. Normalize currency, units, reporting periods, and accounting labels.
4. Add confidence scoring and human-review workflows.
5. Add exchange and issuer ingestion adapters.
6. Build company-period datasets for screening and comparison.
7. Add automated validation tests against manually labelled financial statements.
8. Expose structured outputs through an API and analytical dashboard.

## Security note

Environment files and local credentials are excluded from version control. Production credentials should always be stored in a secrets manager or deployment environment rather than committed to the repository.

## License

MIT License.


## Reliable parsing and review workflow

Requires Python 3.11+ and the **Tesseract executable** (install separately from the
Python packages, e.g. `sudo apt-get install tesseract-ocr` on Ubuntu). Camelot 1.x
uses its PDFium backend; Ghostscript is not required by this configuration.

Both entry points now use `financial_core.py`. The legacy
`src/parsing/extract_metrics.py` command writes to `output/`; the root command
writes to `processed/`. Paths are relative to the working directory unless supplied
explicitly. Imports do not create directories or start extraction.

```bash
python test_env.py
python semantic_financial_extractor.py --pdf raw_data/sample.pdf --output-dir processed
python semantic_financial_extractor.py --pdf raw_data/sample.pdf --period 2025 --scope group
python -m unittest discover -s tests -v
```

Each run exports CSV, Excel and JSON. JSON preserves every candidate's raw value,
scale multiplier, currency, year, entity scope, page and row/line source. Excel
includes metrics, page text, extracted tables and a summary. Formula-like source
strings are escaped in spreadsheet outputs. All pages are inspected; scanned and
image-bearing pages receive OCR even in otherwise digital documents. OCR failures
are recorded in the summary and produce a nonzero CLI exit code. Missing files,
empty input directories and documents with no extracted values also fail the CLI.

- Exact metric labels prevent expenses and share capital from becoming totals.
- Numbers preserve signs, parentheses and explicit zero. Dashes are missing values.
- Comparative table columns require reporting-year headers. `--period` selects a
  particular year; otherwise the latest labelled year is used. Multiple columns
  with the same year and different values/scopes are ambiguous, not guessed.
- `--scope group` or `--scope company` requires an explicitly identified scope.
- Scale is applied before validation, including small and negative amounts.
- Missing currency, scale, year or scope yields `needs_review`; conflicting
  candidates yield `ambiguous` with no selected value. Missing scale preserves the
  raw reported number in `Value`, with `Multiplier` null; it is **not** a normalized
  base-currency amount. Consumers must check status and metadata before aggregation.
- Balance checks require all three values and consistent reporting context.
  Explicit zero equity is valid; missing equity is not replaced with zero.
- Statuses are deterministic checks, not statistical confidence scores. A
  balanced equation does not establish that a source report was parsed correctly.

The parser intentionally abstains on unsupported layouts, including multiline
numeric cells and unlabelled comparative text. It currently identifies **years**,
not full quarter/half-year duration semantics; multiple periods within one year
require human review. Conflicting unit/currency contexts also require review.
There is no claim of universal issuer-layout coverage. The committed historical
CSV/XLSX files predate this implementation and must not be treated as verified
results from the current parser. Regenerate and verify against the source PDFs.

The regression suite covers parsing, entity/period conflicts, missing-data
validation, late-page OCR, failures, both CLI paths and all export formats. It
includes a generated scanned PDF exercised with real Tesseract when installed;
CI installs Tesseract and runs the suite on Python 3.11 and 3.12.
