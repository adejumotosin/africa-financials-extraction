"""PDF extraction CLI with conservative shared parsing and source provenance."""
import argparse
import json
from pathlib import Path
import sys
import warnings

import fitz
import pandas as pd

from financial_core import (LABELS, table_candidates, text_candidates,
                            select_metrics, validate_results)

RAW_DIR = 'raw_data'
OUTPUT_DIR = 'processed'


def extract_blocks(pdf_path):
    blocks = []
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            for block in page.get_text('blocks'):
                blocks.append({'page': page_number, 'bbox': block[:4], 'text': block[4]})
    return blocks


def ocr_page(page):
    import pytesseract
    from PIL import Image
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), colorspace=fitz.csRGB)
    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(image, config='--psm 6', timeout=60)


def extract_page_texts(pdf_path):
    """Inspect every page, including image pages in otherwise digital reports."""
    pages, errors = {}, []
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            text = page.get_text()
            # Image-bearing pages may mix a digital header with scanned statements.
            needs_ocr = not text.strip() or bool(page.get_images())
            if needs_ocr:
                try:
                    recognized = ocr_page(page)
                    if recognized.strip():
                        text += '\n' + recognized
                    elif not text.strip():
                        errors.append(f'Page {page_number}: OCR returned no text')
                except Exception as exc:
                    errors.append(f'Page {page_number}: OCR failed: {exc}')
            pages[page_number] = text
    return pages, errors


def ocr_pdf(pdf_path):
    """Compatibility helper: OCR each page exactly once."""
    with fitz.open(pdf_path) as document:
        return '\n'.join(ocr_page(page) for page in document)


def extract_tables(pdf_path):
    """Return tables and page metadata; text/OCR remains usable on failure."""
    tables, metadata = [], []
    try:
        import camelot
    except ImportError:
        warnings.warn('Camelot is unavailable; using text/OCR extraction only.')
        return tables, metadata
    seen = set()
    for flavor in ('lattice', 'stream'):
        try:
            for table in camelot.read_pdf(str(pdf_path), pages='all', flavor=flavor):
                rows = table.df.fillna('').values.tolist()
                key = (int(table.page), json.dumps(rows))
                if key not in seen:
                    seen.add(key)
                    tables.append(table.df)
                    metadata.append({'page': int(table.page), 'source': f'{flavor} table {len(tables)}'})
        except Exception as exc:
            warnings.warn(f'Camelot {flavor} failed: {exc}')
    return tables, metadata


def extract_metrics(blocks, ocr_text=None, period=None, scope=None):
    """Compatibility API; only unambiguous complete text rows are accepted."""
    pages = {}
    for block in blocks:
        page = block.get('page', 1)
        pages[page] = pages.get(page, '') + '\n' + block['text']
    if ocr_text:
        pages[0] = ocr_text
    candidates = [c for page, text in pages.items() for c in text_candidates(text, page)]
    return list(select_metrics(candidates, period, scope).values())


def _export_frame(records):
    # Prevent source PDF strings from becoming executable spreadsheet formulas.
    def safe(value):
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, ensure_ascii=False)
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
    return pd.DataFrame(records).map(safe)


def save_outputs(base_name, metrics, blocks, tables, summary, output_dir=OUTPUT_DIR):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics_df = _export_frame(metrics)
    metrics_df.to_csv(output / f'{base_name}_metrics.csv', index=False)
    with pd.ExcelWriter(output / f'{base_name}.xlsx', engine='openpyxl') as writer:
        metrics_df.to_excel(writer, sheet_name='metrics', index=False)
        _export_frame(blocks).to_excel(writer, sheet_name='blocks', index=False)
        for index, table in enumerate(tables, 1):
            _export_frame(table.to_dict('records')).to_excel(writer, sheet_name=f'table_{index}', index=False)
        _export_frame([summary]).to_excel(writer, sheet_name='summary', index=False)
    (output / f'{base_name}_metrics.json').write_text(
        json.dumps({'metrics': metrics, 'summary': summary}, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def process_pdf(pdf_path, output_dir=OUTPUT_DIR, period=None, scope=None):
    pages, errors = extract_page_texts(pdf_path)
    tables, metadata = extract_tables(pdf_path)
    candidates = []
    for table, meta in zip(tables, metadata):
        candidates.extend(table_candidates(table.fillna('').values.tolist(), **meta,
                                           context=pages.get(meta['page'], '')))
    for page, text in pages.items():
        candidates.extend(text_candidates(text, page))
    results = select_metrics(candidates, period, scope)
    balance = validate_results(results)
    summary = {'PDF': str(pdf_path), 'Balance Status': balance['status'],
               'Balance Diff': balance['difference'], 'Errors': errors,
               'Review Required': bool(errors) or any(r['Status'] != 'extracted' for r in results.values())}
    blocks = [{'page': page, 'text': text} for page, text in pages.items()]
    save_outputs(Path(pdf_path).stem, list(results.values()), blocks, tables, summary, output_dir)
    print(f'\n{Path(pdf_path).name}: {balance["status"]}')
    for record in results.values():
        print(f'{record["Metric"]}: {record["Value"]} [{record["Status"]}]')
    for error in errors:
        print(error, file=sys.stderr)
    return results, summary


def main(argv=None, default_output=OUTPUT_DIR):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, help='Process one PDF instead of a directory')
    parser.add_argument('--raw-dir', type=Path, default=Path(RAW_DIR))
    parser.add_argument('--output-dir', type=Path, default=Path(default_output))
    parser.add_argument('--period', type=int, help='Reporting year; otherwise select latest labelled year')
    parser.add_argument('--scope', choices=('group', 'company'), help='Require an explicitly labelled entity scope')
    args = parser.parse_args(argv)
    files = [args.pdf] if args.pdf else sorted(p for p in args.raw_dir.glob('*') if p.suffix.lower() == '.pdf')
    if not files:
        print(f'No PDF files found in {args.raw_dir}', file=sys.stderr)
        return 1
    failed = False
    for path in files:
        try:
            results, summary = process_pdf(path, args.output_dir, args.period, args.scope)
            if summary['Errors'] or all(r['Value'] is None for r in results.values()):
                failed = True
        except Exception as exc:
            print(f'Failed to process {path}: {exc}', file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
