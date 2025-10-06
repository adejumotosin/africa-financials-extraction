import pytesseract
import camelot
import subprocess
import shutil
from PIL import Image

def check_tesseract():
    print("🔎 Checking Tesseract...")
    try:
        version = pytesseract.get_tesseract_version()
        print(f"✅ Tesseract found: {version}")

        # OCR Test: Create a sample image with text
        img = Image.new("RGB", (200, 60), color="white")
        import PIL.ImageDraw as ImageDraw
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Hello OCR!", fill=(0, 0, 0))
        img.save("test_image.png")

        text = pytesseract.image_to_string(Image.open("test_image.png"))
        print(f"✅ OCR Test Output: {text.strip()}")
    except Exception as e:
        print(f"❌ Tesseract test failed: {e}")

def check_ghostscript():
    print("\n🔎 Checking Ghostscript...")
    gs_cmd = shutil.which("gswin64c") or shutil.which("gs")
    if gs_cmd:
        try:
            result = subprocess.run([gs_cmd, "--version"], capture_output=True, text=True)
            print(f"✅ Ghostscript found: {result.stdout.strip()}")
        except Exception as e:
            print(f"❌ Ghostscript error: {e}")
    else:
        print("❌ Ghostscript not found in PATH")

def check_camelot():
    print("\n🔎 Checking Camelot...")
    try:
        tables = camelot.read_pdf("sample.pdf", pages="1")
        print(f"✅ Camelot can read PDFs (found {tables.n} tables in sample.pdf)")
        if tables.n > 0:
            print("📊 First table preview:")
            print(tables[0].df.head()) # show first 5 rows
    except Exception as e:
        print(f"⚠️ Camelot test skipped or failed: {e}")

def check_ocr_on_pdf():
    print("\n🔎 Testing OCR on scanned.pdf...")
    try:
        import pdfplumber

        with pdfplumber.open("scanned.pdf") as pdf:
            first_page = pdf.pages[0]
            image = first_page.to_image(resolution=300).original
            text = pytesseract.image_to_string(image)
            print("✅ OCR extracted text from scanned.pdf:")
            print("----------------------------------------")
            print(text[:500]) # print first 500 characters
            print("----------------------------------------")
    except FileNotFoundError:
        print("⚠️ No scanned.pdf found. Please add one to your project folder.")
    except Exception as e:
        print(f"❌ OCR test failed: {e}")

if __name__ == "__main__":
    print("=== Environment Sanity Test ===\n")
    check_tesseract()
    check_ghostscript()
    check_camelot()
    check_ocr_on_pdf()