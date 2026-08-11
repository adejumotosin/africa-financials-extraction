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
- OCR fallback with Tesseract and pdfplumber
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
