import os
import pdfplumber
import pytesseract
from PIL import Image
import fitz # PyMuPDF

#Point to Tesseract executable (Windows only)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

RAW_DATA = "raw_data/"
PROCESSED = "processed/"

def extract_text_pdf(file_path):
    """
    Extract text from PDF using pdfplumber.
    If that fails (scanned PDF), use OCR (pytesseract).
    """
    text = ""

    # Try pdfplumber (for text-based PDFs)
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"pdfplumber failed on {file_path}: {e}")

    # If nothing extracted, fall back to OCR
    if not text.strip():
        print(f" Falling back to OCR for {file_path} ...")
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300) # high resolution improves OCR
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            page_text = pytesseract.image_to_string(img)
            text += f"\n--- Page {page_num+1} ---\n{page_text}"

    return text

def save_text(file_name, text):
    """
    Save extracted text to processed/ folder as .txt
    """
    os.makedirs(PROCESSED, exist_ok=True)
    out_file = os.path.join(PROCESSED, file_name.replace(".pdf", ".txt"))
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Saved extracted text → {out_file}")


if __name__ == "__main__":
    # Loop over all PDFs in raw_data/
    for file_name in os.listdir(RAW_DATA):
        if file_name.endswith(".pdf"):
            file_path = os.path.join(RAW_DATA, file_name)
            print(f"Processing {file_name} ...")
            extracted_text = extract_text_pdf(file_path)
            save_text(file_name, extracted_text)

    print("All done! Check the processed/ folder for outputs.")