"""Legacy entry point using the same tested parser as the root CLI.

Run from the repository root: python src/parsing/extract_metrics.py --pdf report.pdf
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_financial_extractor import main, process_pdf


def process_pdf_complete(pdf_path):
    return process_pdf(pdf_path, output_dir='output')


if __name__ == '__main__':
    raise SystemExit(main(default_output='output'))
