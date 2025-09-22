# africa-financials-extraction
Automated pipeline for extracting and structuring financial statements of African listed companies.
Africa Financials Extraction
An automated pipeline for extracting and structuring financial statements from annual reports of publicly listed companies across African stock exchanges.

The goal is to make company financial data searchable, comparable, and exportable for analysts, investors, and researchers.
Project Overview
African listed companies publish annual and quarterly reports in PDF/Excel formats. These reports are often unstructured, making analysis difficult.

This project aims to:
1. Crawl stock exchange websites and fetch financial reports.
2. Parse & Extract financial data (Revenue, Net Income, Assets, Liabilities, Equity).
3. Normalize & Validate financial statements across different reporting formats.
4. Output structured datasets (CSV/Excel/JSON).
5. Provide a Streamlit dashboard for comparison and export.
Repository Structure
africa-financials-extraction/
│
├── raw_data/ # Collected reports (PDF/Excel)
├── processed/ # Clean extracted text
├── outputs/ # Structured CSVs
├── src/ # Source code
│ ├── parsing/ # PDF/OCR parsing scripts
│ ├── crawling/ # Crawlers for exchanges
│ └── dashboard/ # Streamlit app
│
├── requirements.txt
└── README.md
Project Roadmap
Week 1 – Setup & Data Collection: Create repo, install dependencies, collect sample reports
Week 2 – PDF Text Extraction: Extract text, apply OCR, standardize text
Week 3 – Financial Metric Extraction (MVP): Regex extraction for core metrics, export CSV
Week 4 – Crawling & Ingestion: Build NSE Nigeria crawler, automate downloads
Week 5 – Normalization & Validation: Schema mapping, validation rules
Week 6 – Dashboard & Export: Streamlit dashboard, deploy to Streamlit Cloud
Installation
1. Clone the repo:
git clone https://github.com/your-username/africa-financials-extraction.git
cd africa-financials-extraction

2. Create & activate virtual environment:
python -m venv venv
source venv/bin/activate # Mac/Linux
venv\Scripts\activate # Windows

3. Install dependencies:
pip install -r requirements.txt
Data Sources
- Nigerian Exchange (NGX): https://ngxgroup.com/
- Nairobi Securities Exchange (NSE): https://www.nse.co.ke/
- Johannesburg Stock Exchange (JSE): https://www.jse.co.za/
Current Status
- Repo created ✅
- Dependencies installed ✅
- First batch of sample reports collected (Nigeria, Kenya, South Africa) ✅

Next step → Week 2: Extract text from PDFs.
License
MIT License. Free to use and modify.
