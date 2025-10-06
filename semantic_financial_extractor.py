"""
Semantic Financial Extractor
----------------------------
This script processes African listed company PDFs and extracts financial metrics
using a semantic + OCR + table hybrid approach.

Key Features:
- Block extraction with PyMuPDF
- Table extraction with Camelot
- OCR fallback with Tesseract
- Semantic matching using regex and embeddings
- Outputs to CSV + Excel (with summary sheet)
- Terminal summary + Balance Sheet validation

Usage:
    python semantic_financial_extractor.py --pdf raw_data/report.pdf
"""

import os
import re
import fitz # PyMuPDF
import pytesseract
import camelot
import pdfplumber
import pandas as pd
from typing import List, Dict, Optional
from PIL import Image

# -------------------------
# Configurations
# -------------------------

QUERIES = {
    "Total Revenue": r"(revenue|turnover|sales)",
    "Net Income": r"(net income|profit after tax|profit for the year)",
    "Total Assets": r"(total assets)",
    "Total Liabilities": r"(total liabilities)",
    "Shareholders' Equity": r"(equity|share capital|total equity)"
}

OUTPUT_DIR = "processed"
RAW_DIR = "raw_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)


# -------------------------
# PDF Processing Functions
# -------------------------

def extract_blocks(pdf_path: str) -> List[Dict]:
    """Extract text blocks using PyMuPDF (good for digital PDFs)."""
    blocks = []
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc, start=1):
        for block in page.get_text("blocks"):
            blocks.append({
                "page": page_num,
                "bbox": block[:4],
                "text": block[4]
            })
    return blocks


def extract_tables(pdf_path: str) -> List[pd.DataFrame]:
    """Extract tables using Camelot."""
    try:
        tables = camelot.read_pdf(pdf_path, pages="all")
        return [t.df for t in tables]
    except Exception:
        return []


def ocr_pdf(pdf_path: str) -> str:
    """Fallback OCR for scanned PDFs using pdfplumber + Tesseract."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                image = pdf.pages[0].to_image(resolution=300).original
                text += pytesseract.image_to_string(image) + "\n"
    except Exception as e:
        print(f"⚠️ OCR failed: {e}")
    return text


# -------------------------
# Semantic Extraction Logic
# -------------------------

def extract_metrics(blocks: List[Dict], ocr_text: Optional[str] = None) -> List[Dict]:
    """Extract key metrics using regex-based semantic matching."""
    results = []

    # Search in digital blocks
    text_data = " ".join([b["text"] for b in blocks]).lower()

    # Include OCR text if available
    if ocr_text:
        text_data += " " + ocr_text.lower()

    for metric, pattern in QUERIES.items():
        match = re.search(pattern, text_data, re.IGNORECASE)
        value = None
        if match:
            # Try to capture nearby numbers
            snippet = text_data[match.start(): match.start() + 100]
            number_match = re.search(r"([\d,.]+)", snippet)
            if number_match:
                try:
                    value = float(number_match.group(1).replace(",", ""))
                except ValueError:
                    value = None
        results.append({
            "Metric": metric,
            "Value": value
        })
    return results


# -------------------------
# Save Outputs
# -------------------------

def save_outputs(base_name: str, metrics: List[Dict], blocks: List[Dict], tables: List[pd.DataFrame], summary: Dict):
    """Saves outputs to CSV and Excel (with summary sheet)."""
    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(os.path.join(OUTPUT_DIR, f"{base_name}_metrics.csv"), index=False)

    # Save Excel with multiple sheets
    excel_path = os.path.join(OUTPUT_DIR, f"{base_name}.xlsx")
    with pd.ExcelWriter(excel_path) as writer:
        metrics_df.to_excel(writer, sheet_name="metrics", index=False)
        pd.DataFrame(blocks).to_excel(writer, sheet_name="blocks", index=False)
        for i, table in enumerate(tables):
            table.to_excel(writer, sheet_name=f"table_{i+1}", index=False)
        pd.DataFrame([summary]).to_excel(writer, sheet_name="summary", index=False)


# -------------------------
# Processing Pipeline
# -------------------------

def process_pdf(pdf_path: str):
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]

    # 1. Extract text blocks
    blocks = extract_blocks(pdf_path)

    # 2. Extract tables
    tables = extract_tables(pdf_path)

    # 3. Fallback OCR
    ocr_text = ocr_pdf(pdf_path)

    # 4. Extract semantic metrics
    metrics = extract_metrics(blocks, ocr_text)

    # 5. Build summary
    results_dict = {m["Metric"]: m["Value"] for m in metrics}
    assets = results_dict.get("Total Assets")
    liabilities = results_dict.get("Total Liabilities")
    equity = results_dict.get("Shareholders' Equity")

    balance_status = "N/A"
    balance_diff = None
    if assets and liabilities and equity:
        diff = abs(assets - (liabilities + equity))
        rel_error = diff / assets
        balance_status = "✅ BALANCED" if rel_error < 0.05 else f"❌ UNBALANCED (err {rel_error:.2%})"
        balance_diff = diff

    summary = {
        "PDF": base_name,
        **results_dict,
        "Balance Status": balance_status,
        "Balance Diff": balance_diff
    }

    # 6. Save outputs
    save_outputs(base_name, metrics, blocks, tables, summary)

    # 7. Print quick summary to terminal
    print(f"\n📊 Results for {base_name}.pdf")
    print("-" * 40)
    for m in metrics:
        metric = m["Metric"]
        value = m["Value"]
        if value is None:
            value_str = "❌ Not found"
        else:
            value_str = f"{value:,.0f}"
        print(f"{metric:<22} {value_str}")

    if assets and liabilities and equity:
        print("\n⚖️ Balance Sheet Check")
        print(f" Assets: {assets:,.0f}")
        print(f" Liabilities: {liabilities:,.0f}")
        print(f" Equity: {equity:,.0f}")
        print(f" Diff: {balance_diff:,.0f}")
        print(f" Status: {balance_status}")
    print()


# -------------------------
# Main Runner
# -------------------------

if __name__ == "__main__":
    pdfs = [f for f in os.listdir(RAW_DIR) if f.endswith(".pdf")]
    if not pdfs:
        print("⚠️ No PDFs found in raw_data/. Please add some reports to process.")
    for pdf in pdfs:
        process_pdf(os.path.join(RAW_DIR, pdf))