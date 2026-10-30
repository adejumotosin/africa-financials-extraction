import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fitz
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

import financial_core as core
import semantic_financial_extractor as pipeline


class ParsingTests(unittest.TestCase):
    def test_sign_zero_and_invalid_formats(self):
        for text, expected in [('(1,250)', -1250), ('-1,250', -1250), ('−1,250', -1250), ('0', 0), ('0.25', .25), ('1,234.50', 1234.5), ('—', None), ('NaN', None), ('1.234,50', None), ('1,25', None)]:
            with self.subTest(text=text):
                self.assertEqual(core.parse_number(text), expected)

    def test_note_reference_not_revenue(self):
        self.assertEqual(core.text_candidates('Revenue 12 1,250,000 900,000'), [])
        rows = [['Metric', 'Notes', '2025', '2024'], ['Revenue', '12', '1,250,000', '900,000']]
        result = core.select_metrics(core.table_candidates(rows))['Total Revenue']
        self.assertEqual(result['Value'], 1250000)

    def test_cost_and_capital_not_totals(self):
        self.assertEqual(core.text_candidates('Cost of revenue 1234567\nShare capital 100'), [])
        self.assertEqual(core.text_candidates('Total equity 900')[0].value, 900)

    def test_losses_preserved_in_text(self):
        for text in ['Net income (1,250)', 'Net income -1,250']:
            self.assertEqual(core.text_candidates(text)[0].value, -1250)

    def test_latest_year_in_either_order(self):
        for rows in [[['Metric', '2025', '2024'], ['Revenue', '2000000', '1500000']], [['Metric', '2024', '2025'], ['Revenue', '1500000', '2000000']]]:
            candidates = core.table_candidates(rows)
            self.assertEqual(core.select_metrics(candidates)['Total Revenue']['Value'], 2000000)
            self.assertEqual(core.select_metrics(candidates, period=2024)['Total Revenue']['Value'], 1500000)

    def test_actual_fiscal_year_excludes_forecasts(self):
        rows = [['FY Dec (USDmn)', 'FY2024(A)', 'FY2025(A)', 'FY2026(F)'], ['Sales', '245,122', '281,724', '323,505']]
        result = core.select_metrics(core.table_candidates(rows))['Total Revenue']
        self.assertEqual(result['Value'], 281724000000)
        self.assertEqual(result['Period'], 2025)
        self.assertEqual(result['Currency'], 'USD')

    def test_short_month_year_headers(self):
        rows = [['In thousands of Nigerian Naira', 'June-25', 'Dec-24'], ['Total assets', '500', '400']]
        result = core.select_metrics(core.table_candidates(rows))['Total Assets']
        self.assertEqual(result['Value'], 500000)
        self.assertEqual(result['Period'], 2025)
        self.assertEqual(result['Currency'], 'NGN')

    def test_malformed_current_does_not_select_prior(self):
        for headers in [[], [['Metric', 'June-25', 'Dec-24']]]:
            rows = headers + [['Equity', '2,994,613,90614', '2,712,017,614']]
            result = core.select_metrics(core.table_candidates(rows))["Shareholders' Equity"]
            self.assertIsNone(result['Value'])

    def test_zero_current_year_is_not_prior_year(self):
        rows = [['Metric', '2024', '2025'], ['Net income', '1500', '0']]
        self.assertEqual(core.select_metrics(core.table_candidates(rows))['Net Income']['Value'], 0)

    def test_missing_current_year_never_uses_prior_year(self):
        rows = [['Metric', '2024', '2025'], ['Revenue', '1500', '-']]
        result = core.select_metrics(core.table_candidates(rows))['Total Revenue']
        self.assertIsNone(result['Value'])
        self.assertEqual(result['Period'], 2025)
        self.assertEqual(result['Status'], 'not_found')

    def test_scaling_precedes_validation_including_small_numbers(self):
        rows = [['NGN in millions Group', '2025'], ['Total assets', '50'], ['Total liabilities', '60'], ['Equity', '(10)']]
        results = core.select_metrics(core.table_candidates(rows))
        self.assertEqual(results['Total Assets']['Value'], 50000000)
        self.assertEqual(results["Shareholders' Equity"]['Value'], -10000000)
        self.assertEqual(core.validate_results(results)['status'], 'Balanced')

    def test_millions_not_misread_as_thousands(self):
        self.assertEqual(core.detect_scale("NGN '000,000"), 1000000)
        self.assertIsNone(core.detect_scale('NGN in thousands USD in millions'))

    def test_missing_is_not_zero(self):
        self.assertEqual(core.validate_balance_sheet(100, 100, None)['status'], 'Incomplete')
        self.assertEqual(core.validate_balance_sheet(100, 100, 0)['status'], 'Balanced')

    def test_nonfinite_is_invalid(self):
        self.assertEqual(core.validate_balance_sheet(float('nan'), 100, 0)['status'], 'Incomplete')

    def test_conflicting_values_are_ambiguous(self):
        candidates = core.text_candidates('Revenue 100\nRevenue 200')
        result = core.select_metrics(candidates)['Total Revenue']
        self.assertEqual(result['Status'], 'ambiguous')
        self.assertIsNone(result['Value'])

    def test_unlabelled_multiple_columns_are_not_guessed(self):
        self.assertEqual(core.table_candidates([['Revenue', '100', '200']]), [])

    def test_group_company_not_mixed(self):
        rows = [['', 'Group', '', 'Company', ''], ['', '2025', '2024', '2025', '2024'], ['Revenue', '100', '90', '80', '70']]
        candidates = core.table_candidates(rows)
        self.assertEqual(core.select_metrics(candidates)['Total Revenue']['Status'], 'ambiguous')
        self.assertEqual(core.select_metrics(candidates, scope='group')['Total Revenue']['Value'], 100)
        self.assertEqual(core.select_metrics(candidates, scope='company')['Total Revenue']['Value'], 80)

    def test_distinct_periods_in_same_year_are_ambiguous_even_if_values_equal(self):
        rows = [['Metric', 'June 2025', 'December 2025'], ['Revenue', '100', '100']]
        result = core.select_metrics(core.table_candidates(rows))['Total Revenue']
        self.assertEqual(result['Status'], 'ambiguous')

    def test_missing_context_cannot_certify_balance(self):
        results = core.select_metrics(core.text_candidates('Total assets 100\nTotal liabilities 100\nEquity 0'))
        self.assertFalse(core.validate_results(results)['is_balanced'])

    def test_mismatched_years_cannot_certify_balance(self):
        candidates = core.table_candidates([['NGN in units Group', '2025'], ['Total assets', '100']])
        candidates += core.table_candidates([['NGN in units Group', '2024'], ['Total liabilities', '80'], ['Equity', '20']])
        self.assertFalse(core.validate_results(core.select_metrics(candidates))['is_balanced'])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pdf(self, texts):
        path = self.root / 'fixture.pdf'
        with fitz.open() as doc:
            for text in texts:
                page = doc.new_page()
                if text:
                    page.insert_text((50, 50), text)
            doc.save(path)
        return path

    def test_ocr_uses_every_distinct_page(self):
        path = self.pdf(['', '', ''])
        with patch.object(pipeline, 'ocr_page', side_effect=lambda page: f'page {page.number}'):
            self.assertEqual(pipeline.ocr_pdf(path), 'page 0\npage 1\npage 2')

    def test_ocr_after_page_twenty_on_mixed_document(self):
        path = self.pdf(['cover'] * 24 + [''])
        with patch.object(pipeline, 'ocr_page', return_value='Revenue 123') as ocr:
            pages, errors = pipeline.extract_page_texts(path)
            self.assertIn('Revenue 123', pages[25])
            self.assertEqual(ocr.call_count, 1)
            self.assertFalse(errors)

    def test_no_tables_still_exports_text_metrics(self):
        path = self.pdf(['NGN in units Group 2025\nRevenue 150\nNet income -10\nTotal assets 100\nTotal liabilities 80\nEquity 20'])
        with patch.object(pipeline, 'extract_tables', return_value=([], [])), contextlib.redirect_stdout(io.StringIO()):
            results, summary = pipeline.process_pdf(path, self.root / 'out')
        self.assertEqual(results['Net Income']['Value'], -10)
        self.assertEqual(summary['Balance Status'], 'Balanced')
        for suffix in ['_metrics.csv', '_metrics.json', '.xlsx']:
            self.assertTrue((self.root / 'out' / ('fixture' + suffix)).exists())
        data = json.loads((self.root / 'out' / 'fixture_metrics.json').read_text())
        self.assertEqual(data['metrics'][0]['Candidates'][0]['page'], 1)
        self.assertEqual(pd.read_excel(self.root / 'out' / 'fixture.xlsx', sheet_name='metrics').shape[0], 5)

    def test_ocr_failure_recorded_and_nonzero_exit(self):
        path = self.pdf([''])
        with patch.object(pipeline, 'ocr_page', side_effect=RuntimeError('missing engine')), patch.object(pipeline, 'extract_tables', return_value=([], [])), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            status = pipeline.main(['--pdf', str(path), '--output-dir', str(self.root / 'out')])
        self.assertEqual(status, 1)
        summary = json.loads((self.root / 'out' / 'fixture_metrics.json').read_text())['summary']
        self.assertTrue(summary['Errors'])

    def test_missing_pdf_nonzero_exit(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pipeline.main(['--pdf', str(self.root / 'missing.pdf')]), 1)

    def test_legacy_cli_export(self):
        path = self.pdf(['Revenue 150'])
        script = Path(pipeline.__file__).parent / 'src/parsing/extract_metrics.py'
        result = subprocess.run([sys.executable, str(script), '--pdf', str(path), '--output-dir', str(self.root / 'out')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'out' / 'fixture_metrics.csv').exists())

    def test_real_camelot_table_uses_headers_and_scale(self):
        path = self.root / 'table.pdf'
        rows = [['Metric', '2025', '2024'], ['Revenue', '90', '60'],
                ['Net income', '(5)', '10'], ['Total assets', '50', '40'],
                ['Total liabilities', '60', '30'], ['Equity', '(10)', '10']]
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 80), 'Group NGN in millions')
            xs = [40, 300, 430, 550]
            for x in xs:
                page.draw_line((x, 100), (x, 100 + 30 * len(rows)))
            for i in range(len(rows) + 1):
                page.draw_line((40, 100 + 30 * i), (550, 100 + 30 * i))
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    page.insert_text((xs[j] + 8, 120 + 30 * i), cell)
            doc.save(path)
        with contextlib.redirect_stdout(io.StringIO()):
            results, summary = pipeline.process_pdf(path, self.root / 'out')
        self.assertEqual(results['Total Revenue']['Value'], 90000000)
        self.assertEqual(results['Net Income']['Value'], -5000000)
        self.assertEqual(results["Shareholders' Equity"]['Value'], -10000000)
        self.assertEqual(summary['Balance Status'], 'Balanced')

    def test_formula_strings_escaped(self):
        self.assertEqual(pipeline._export_frame([{'text': '=1+1', 'value': -10}]).iloc[0].to_dict(), {'text': "'=1+1", 'value': -10})

    @unittest.skipUnless(shutil.which('tesseract'), 'Tesseract executable required')
    def test_real_scanned_pdf_ocr(self):
        font = ImageFont.truetype('DejaVuSans.ttf', 36)
        image = Image.new('RGB', (1200, 450), 'white')
        ImageDraw.Draw(image).multiline_text((40, 40), 'Revenue 125000\nNet income (1250)\nTotal assets 500000', font=font, fill='black', spacing=20)
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        path = self.root / 'scan.pdf'
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=225)
            page.insert_image(page.rect, stream=buffer.getvalue())
            doc.save(path)
        with contextlib.redirect_stdout(io.StringIO()):
            results, summary = pipeline.process_pdf(path, self.root / 'out')
        self.assertEqual(results['Total Revenue']['Value'], 125000)
        self.assertEqual(results['Net Income']['Value'], -1250)
        self.assertFalse(summary['Errors'])


if __name__ == '__main__':
    unittest.main()
