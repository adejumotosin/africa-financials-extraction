"""Conservative financial parsing; no PDF or OCR dependencies.

Ambiguous layouts are review items, never a reason to guess a year or value.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
import math
import re
import unicodedata

LABELS = {
    'Total Revenue': ('total operating income', 'total revenue', 'gross revenue', 'revenue', 'turnover', 'sales'),
    'Net Income': ('profit for the year', 'loss for the year', 'profit for the period', 'loss for the period', 'net income', 'net profit', 'net loss', 'profit after tax', 'loss after tax'),
    'Total Assets': ('total assets',),
    'Total Liabilities': ('total liabilities',),
    "Shareholders' Equity": ('total equity', "shareholders' equity", 'shareholders equity', 'equity'),
}
NUMBER = r'(?:\([−+-]?\d[\d,]*(?:\.\d+)?\)|[−+-]?\d[\d,]*(?:\.\d+)?)'
YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')


def header_year(text):
    text = str(text).strip()
    matches = YEAR.findall(text)
    if len(matches) == 1:
        return int(matches[0])
    short = re.fullmatch(r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[- /](\d{2})', text, re.I)
    return 2000 + int(short[1]) if short else None


def forecast_header(text):
    return bool(re.search(r'(?:19|20)\d{2}\s*(?:\([FE]\)|[FE]\b)|forecast|estimate', str(text), re.I))


def parse_number(value):
    """Accept explicit numeric cells; dashes/missing cells are not reported zero."""
    text = str(value).strip().replace('−', '-').replace('\u00a0', ' ')
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1].strip()
    # Reject decimal-comma and malformed grouping instead of changing magnitudes.
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', text):
        return None
    try:
        number = Decimal(text.replace(',', ''))
        if negative:
            number = -abs(number)
        return float(number) if number.is_finite() else None
    except InvalidOperation:
        return None


def normalize_label(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value)).lower().replace('’', "'")).strip(' :\n\t')


def metric_for_label(value):
    label = normalize_label(value)
    return next((metric for metric, terms in LABELS.items() if label in terms), None)


def detect_scale(text):
    text = str(text).lower().replace('’', "'")
    found = set()
    # Strip larger suffix first, so '000,000 does not also mean thousands.
    for pattern, multiplier in [
        (r"in billions?|billions of", 1_000_000_000),
        (r"in millions?|millions of|'000,000|\(000,000\)|(?:usd|ngn|zar|kes|ghs|egp|gbp|eur)mn\b", 1_000_000),
        (r"in thousands?|thousands of|'000\b|\(000\)|000s\b", 1000),
        (r'\bin units\b|\bactual units\b', 1),
    ]:
        if re.search(pattern, text):
            found.add(multiplier)
            text = re.sub(pattern, '', text)
    return next(iter(found)) if len(found) == 1 else None


def detect_currency(text):
    codes = set(re.findall(r'\b(NGN|USD|ZAR|KES|GHS|EGP|GBP|EUR)(?=\b|MN\b)', str(text).upper()))
    if 'nigerian naira' in str(text).lower():
        codes.add('NGN')
    if '₦' in str(text):
        codes.add('NGN')
    return next(iter(codes)) if len(codes) == 1 else None


def detect_scope(text):
    text = normalize_label(text)
    scopes = set()
    if re.search(r'\bgroup\b|\bconsolidated\b', text):
        scopes.add('group')
    if re.search(r'\bcompany\b|\bseparate\b', text):
        scopes.add('company')
    return next(iter(scopes)) if len(scopes) == 1 else None


@dataclass(frozen=True)
class Candidate:
    metric: str
    raw_value: float | None
    value: float | None
    page: int
    source: str
    label: str
    period: int | None
    scope: str | None
    currency: str | None
    multiplier: int | None
    method: str
    period_label: str | None = None


def table_candidates(rows, page=1, source='table', context=''):
    """Read exact metric rows with an unambiguous year/scope column mapping."""
    rows = [[str(cell or '').strip() if cell != 0 else '0' for cell in row] for row in rows]
    if not rows:
        return []
    candidates = []
    years, scopes, note_columns, period_labels = {}, {}, set(), {}
    headers = []
    for row_index, row in enumerate(rows):
        metric = metric_for_label(row[0]) if row else None
        if metric is None:
            # Only header-like rows may alter column metadata.
            if any(header_year(cell) is not None for cell in row) or any(detect_scope(cell) for cell in row) or any(normalize_label(cell) in ('note', 'notes') for cell in row):
                headers.append(' '.join(row))
                current_scope = None
                for col, cell in enumerate(row):
                    scope = detect_scope(cell)
                    if scope:
                        current_scope = scope
                    if current_scope:
                        scopes[col] = current_scope
                    year = header_year(cell)
                    if forecast_header(cell):
                        note_columns.add(col)  # Forecasts are not reported financials.
                    elif year is not None:
                        years[col] = year
                        period_labels[col] = normalize_label(cell)
                    elif len(YEAR.findall(cell)) > 1:
                        years.pop(col, None)
                    if normalize_label(cell) in ('note', 'notes'):
                        note_columns.add(col)
            # Keep unit/currency headers even if they contain no dates.
            if detect_scale(' '.join(row)) or detect_currency(' '.join(row)):
                headers.append(' '.join(row))
            continue
        local_context = ' '.join(headers) + ' ' + context
        multiplier = detect_scale(local_context)
        currency = detect_currency(local_context)
        scope_default = detect_scope(local_context)
        numeric = [(col, parse_number(cell)) for col, cell in enumerate(row[1:], 1) if col not in note_columns]
        if years:
            # Preserve empty current-period cells so selection cannot fall back
            # silently to a populated comparative period.
            numeric = [(col, parse_number(row[col]) if col < len(row) else None)
                       for col in years if col > 0 and col not in note_columns]
        else:
            numeric = [(col, val) for col, val in numeric if val is not None]
        if not years and (len(numeric) != 1 or sum(bool(cell.strip()) for col, cell in enumerate(row[1:], 1) if col not in note_columns) != 1):
            continue  # Note numbers / comparative columns cannot be guessed.
        for col, value in numeric:
            candidates.append(Candidate(metric, value, value * (multiplier or 1) if value is not None else None, page,
                f'{source}, row {row_index + 1}, column {col + 1}', row[0],
                years.get(col), scopes.get(col, scope_default), currency, multiplier, 'table', period_labels.get(col)))
    return candidates


def text_candidates(text, page=1):
    """Fallback accepts only a complete labelled line with one numeric value."""
    candidates = []
    scale, currency, scope = detect_scale(text), detect_currency(text), detect_scope(text)
    years = set(YEAR.findall(text))
    period = int(next(iter(years))) if len(years) == 1 else None
    for line_index, line in enumerate(text.splitlines(), 1):
        for metric, labels in LABELS.items():
            for label in sorted(labels, key=len, reverse=True):
                match = re.fullmatch(re.escape(label) + r'\s*:?\s+(' + NUMBER + r')\s*', normalize_label(line))
                if not match:
                    continue
                value = parse_number(match.group(1))
                if value is not None:
                    candidates.append(Candidate(metric, value, value * (scale or 1), page,
                        f'page {page}, line {line_index}', label, period, scope, currency, scale, 'text', str(period) if period else None))
                break
    return candidates


def select_metrics(candidates, period=None, scope=None):
    results = {}
    for metric in LABELS:
        pool = [c for c in candidates if c.metric == metric]
        if scope:
            pool = [c for c in pool if c.scope == scope]
        known_periods = [c.period for c in pool if c.period is not None]
        target_period = period if period is not None else max(known_periods, default=None)
        if target_period is not None:
            pool = [c for c in pool if c.period == target_period]
        # Tables retain column relationships; fallback prose cannot override them.
        if any(c.method == 'table' for c in pool):
            pool = [c for c in pool if c.method == 'table']
        if any(c.value is not None for c in pool):
            pool = [c for c in pool if c.value is not None]
        record = {'Metric': metric, 'Value': None, 'Status': 'not_found', 'Period': target_period,
                  'Scope': scope, 'Period Label': None, 'Currency': None, 'Multiplier': None, 'Sources': [], 'Candidates': [asdict(c) for c in pool]}
        if pool and any(c.value is not None for c in pool):
            signatures = {(c.value, c.period, c.period_label, c.scope, c.currency, c.multiplier) for c in pool}
            if len(signatures) != 1:
                record['Status'] = 'ambiguous'
            else:
                c = pool[0]
                valid = math.isfinite(c.value) and (metric not in ('Total Assets', 'Total Liabilities', 'Total Revenue') or c.value >= 0)
                record.update({'Period Label': c.period_label})
                record.update(Value=c.value if valid else None, Scope=c.scope, Currency=c.currency,
                              Multiplier=c.multiplier, Sources=sorted({c.source for c in pool}),
                              Status=('extracted' if all(x is not None for x in (c.period, c.scope, c.currency, c.multiplier)) else 'needs_review') if valid else 'invalid')
        results[metric] = record
    return results


def validate_balance_sheet(assets, liabilities, equity, tolerance=0.001):
    if any(v is None or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (assets, liabilities, equity)):
        return {'status': 'Incomplete', 'is_balanced': False, 'difference': None}
    if assets <= 0 or liabilities < 0:
        return {'status': 'Invalid', 'is_balanced': False, 'difference': None}
    difference = abs(assets - liabilities - equity)
    balanced = difference / assets <= tolerance
    return {'status': 'Balanced' if balanced else 'Unbalanced', 'is_balanced': balanced, 'difference': difference}


def validate_results(results):
    records = [results[name] for name in ('Total Assets', 'Total Liabilities', "Shareholders' Equity")]
    result = validate_balance_sheet(*(r['Value'] for r in records))
    if result['status'] in ('Incomplete', 'Invalid'):
        return result
    contexts = {(r['Period'], r['Period Label'], r['Scope'], r['Currency'], r['Multiplier']) for r in records}
    if len(contexts) != 1 or any(r['Status'] != 'extracted' for r in records):
        return {'status': 'Needs review: incomplete or inconsistent reporting context', 'is_balanced': False, 'difference': result['difference']}
    return result
