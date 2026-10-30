"""Check runtime dependencies and OCR; exit nonzero on missing requirements."""
import importlib
import shutil
import subprocess


def main():
    failed = False
    for module in ('fitz', 'pandas', 'openpyxl', 'PIL', 'camelot', 'pytesseract'):
        try:
            importlib.import_module(module)
            print(f'OK: {module}')
        except ImportError as exc:
            print(f'FAIL: {module}: {exc}')
            failed = True
    tesseract = shutil.which('tesseract')
    if tesseract:
        result = subprocess.run([tesseract, '--version'], capture_output=True, text=True)
        print(result.stdout.splitlines()[0] if result.stdout else result.stderr)
        failed |= result.returncode != 0
    else:
        print('FAIL: install the Tesseract OCR executable and add it to PATH')
        failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
