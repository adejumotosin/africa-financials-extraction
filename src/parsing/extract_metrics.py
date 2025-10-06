# AI-Enhanced Financial Data Extractor - V4 COMPLETE & CORRECTED
# Part 1 of 3: Core Setup, Configuration, Validation, and Number Processing


import os
import re
import json
import io
import math
import fitz # PyMuPDF
import pytesseract
import camelot
import pdfplumber
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Union
from PIL import Image
import warnings
import time
from decimal import Decimal, InvalidOperation
warnings.filterwarnings('ignore')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# -------------------------
# CONFIGURATION & CONSTANTS
# -------------------------

DEBUG_MODE = True # Set to True for verbose logging of all found candidates

# Directory Setup
RAW_DIR = "raw_data"
OUTPUT_DIR = "output"

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Financial Value Validation Ranges (increased for scaled values)
FINANCIAL_RANGES = {
    "Total Revenue": {
        "min": 1000,
        "max": 1e15,
        "typical_min": 100000,
        "typical_max": 1e14
    },
    "Net Income": {
        "min": -1e14,
        "max": 1e14,
        "typical_min": -1e12,
        "typical_max": 1e13
    },
    "Total Assets": {
        "min": 1000,
        "max": 1e16,
        "typical_min": 100000,
        "typical_max": 1e15
    },
    "Total Liabilities": {
        "min": 0,
        "max": 1e16,
        "typical_min": 1000,
        "typical_max": 1e15
    },
    "Shareholders' Equity": {
        "min": -1e14,
        "max": 1e15,
        "typical_min": 1000,
        "typical_max": 1e14
    }
}

# Scale Detection Keywords (for text context)
SCALE_INDICATORS = {
    'thousands': {
        'multiplier': 1000,
        'priority': 1,
        'patterns': [r'in thousands', r'\(000\)', r"'000", r'000s', r'thousands of']
    },
    'millions': {
        'multiplier': 1000000,
        'priority': 2,
        'patterns': [r'in millions', r'\(000,000\)', r"'000,000", r'millions of', r'in million']
    },
    'billions': {
        'multiplier': 1000000000,
        'priority': 3,
        'patterns': [r'in billions', r'billions of', r'in billion']
    }
}

# Financial Concepts
FINANCIAL_CONCEPTS = {
    "Total Revenue": {
        "primary_terms": [
            "total operating income",
            "total revenue",
            "gross revenue", 
            "revenue"
        ],
        "negative_terms": [
            "cost of revenue",
            "other operating expenses"
        ]
    },
    "Net Income": {
        "primary_terms": [
            "profit for the year",
            "profit for the period",
            "net income",
            "net profit",
            "profit after tax"
        ],
        "negative_terms": [
            "gross income",
            "net fee and commission income",
            "profit before"
        ]
    },
    "Total Assets": {
        "primary_terms": [
            "total assets"
        ],
        "negative_terms": [
            "non-current assets",
            "current assets",
            "pledged as collateral",
            "net assets",
            "total liabilities and equity"  # Critical: this also contains "total assets" words
        ]
    },
    "Total Liabilities": {
        "primary_terms": [
            "total liabilities"
        ],
        "negative_terms": [
            "non-current liabilities",
            "current liabilities",
            "total liabilities and equity",  # Exclude the sum line
            "deferred tax liabilities",
            "financial liabilities",
            "derivative financial liabilities",
            "other liabilities"
        ]
    },
    "Shareholders' Equity": {
        "primary_terms": [
            "equity"  # Keep it simple - just "equity" as shown in your PDF
        ],
        "negative_terms": [
            "total liabilities and equity",  # CRITICAL: exclude this line
            "liabilities and equity",
            "deposits",                       # Exclude ALL deposit lines
            "borrowed",                       # Exclude borrowings
            "return on equity",              # Exclude ratios
            "derivative",                    # Exclude derivative lines
            "financial liabilities"          # Exclude liability lines
        ]
    }
}

# -------------------------
# VALIDATION FRAMEWORK
# -------------------------

class FinancialValidator:
    """Comprehensive financial data validation framework."""
    
    def __init__(self):
        self.validation_results = []
    
    def validate_value(self, metric: str, value: float, confidence: float, 
                      context: str = "") -> Dict:
        """Validate a single financial metric value."""
        if metric not in FINANCIAL_RANGES:
            return {
                "is_valid": False,
                "confidence_adjusted": 0.0,
                "issues": [f"Unknown metric: {metric}"],
                "severity": "error"
            }
        
        issues = []
        severity = "good"
        confidence_multiplier = 1.0
        
        ranges = FINANCIAL_RANGES[metric]
        
        # Check absolute bounds
        if value < ranges["min"] or value > ranges["max"]:
            issues.append(f"Value {value:,.0f} outside valid range")
            severity = "error"
            confidence_multiplier = 0.1
        
        # Check typical bounds
        elif value < ranges["typical_min"] or value > ranges["typical_max"]:
            issues.append(f"Value {value:,.0f} outside typical range")
            severity = "warning"
            confidence_multiplier = 0.7
        
        # Context-based validation - check for artifacts
        if self._detect_potential_artifacts(value, context):
            issues.append("Value may be page number or formatting artifact")
            severity = "error"
            confidence_multiplier = 0.2
        
        # Adjust confidence
        adjusted_confidence = min(1.0, max(0.0, confidence * confidence_multiplier))
        
        return {
            "is_valid": severity != "error",
            "confidence_adjusted": adjusted_confidence,
            "issues": issues,
            "severity": severity,
            "original_confidence": confidence,
            "confidence_multiplier": confidence_multiplier
        }
    
    def _detect_potential_artifacts(self, value: float, context: str) -> bool:
        """Detect if value is likely a page number, date, or other artifact."""
        context_lower = context.lower()
        
        # Page numbers (1-999) - only if integer and context suggests it
        if 1 <= value <= 999 and value == int(value):
            if "page" in context_lower or "report" in context_lower:
                return True
        
        # Years (1900-2100)
        if 1900 <= value <= 2100 and value == int(value):
            return True
        
        return False
    
    def validate_balance_sheet(self, assets: float, liabilities: float, 
                              equity: float) -> Dict:
        """Enhanced balance sheet validation with proper error bounds."""
        result = {
            "is_balanced": False,
            "confidence": 0.0,
            "status": "Unknown",
            "severity": "error",
            "details": {},
            "issues": []
        }
        
        try:
            # Check for missing or invalid values
            if not all(isinstance(v, (int, float)) and v is not None 
                      for v in [assets, liabilities, equity]):
                result["issues"].append("Non-numeric or missing values")
                result["status"] = "Invalid - non-numeric values"
                return result
            
            if assets <= 0:
                result["issues"].append("Assets must be positive")
                result["status"] = "Invalid - negative/zero assets"
                return result
            
            if liabilities < 0:
                result["issues"].append("Liabilities cannot be negative")
                result["status"] = "Invalid - negative liabilities"
                return result
            
            # Calculate balance
            expected_total = liabilities + equity
            difference = abs(assets - expected_total)
            relative_error = difference / assets if assets > 0 else float('inf')
            
            # Determine status based on relative error
            if relative_error < 0.001: # 0.1%
                result.update({
                    "is_balanced": True,
                    "confidence": 0.98,
                    "status": "Perfectly Balanced",
                    "severity": "excellent"
                })
            elif relative_error < 0.01: # 1%
                result.update({
                    "is_balanced": True,
                    "confidence": 0.90,
                    "status": "Well Balanced",
                    "severity": "good"
                })
            elif relative_error < 0.05: # 5%
                result.update({
                    "is_balanced": True,
                    "confidence": 0.70,
                    "status": "Acceptably Balanced",
                    "severity": "acceptable"
                })
            elif relative_error < 0.15: # 15%
                result.update({
                    "is_balanced": False,
                    "confidence": 0.40,
                    "status": "Poorly Balanced",
                    "severity": "warning"
                })
            else:
                result.update({
                    "is_balanced": False,
                    "confidence": 0.10,
                    "status": "Severely Unbalanced",
                    "severity": "error"
                })
            
            # Add detailed information
            result["details"] = {
                "assets": assets,
                "liabilities": liabilities,
                "equity": equity,
                "expected_total": expected_total,
                "difference": difference,
                "relative_error": relative_error,
                "error_percentage": relative_error * 100
            }
            
        except Exception as e:
            result.update({
                "status": f"Validation Error: {str(e)}",
                "issues": [f"Exception during validation: {e}"]
            })
        
        return result
    
    def validate_extraction_set(self, results: Dict) -> Dict:
        """Validate the complete set of extracted financial metrics."""
        validation_summary = {
            "overall_quality": "unknown",
            "total_metrics": len(results),
            "valid_metrics": 0,
            "invalid_metrics": 0,
            "average_confidence": 0.0,
            "issues": [],
            "metric_validations": {}
        }
        
        valid_confidences = []
        
        for metric, data in results.items():
            value = data.get("value")
            confidence = data.get("confidence", 0.0)
            
            if value is not None:
                validation = self.validate_value(
                    metric, value, confidence, data.get("source", "")
                )
                validation_summary["metric_validations"][metric] = validation
                
                if validation["is_valid"]:
                    validation_summary["valid_metrics"] += 1
                    valid_confidences.append(validation["confidence_adjusted"])
                else:
                    validation_summary["invalid_metrics"] += 1
                    validation_summary["issues"].extend(validation["issues"])
            else:
                validation_summary["invalid_metrics"] += 1
                validation_summary["issues"].append(f"{metric}: No value extracted")
        
        # Calculate overall quality
        if valid_confidences:
            validation_summary["average_confidence"] = np.mean(valid_confidences)
            
            if validation_summary["average_confidence"] > 0.8:
                validation_summary["overall_quality"] = "excellent"
            elif validation_summary["average_confidence"] > 0.6:
                validation_summary["overall_quality"] = "good"
            elif validation_summary["average_confidence"] > 0.4:
                validation_summary["overall_quality"] = "fair"
            else:
                validation_summary["overall_quality"] = "poor"
        else:
            validation_summary["overall_quality"] = "failed"
        
        return validation_summary


# -------------------------
# NUMBER PROCESSING FRAMEWORK
# -------------------------

class NumberProcessor:
    """Enhanced number processing with context awareness."""
    
    def __init__(self):
        self.scale_cache = {}
    
    def _parse_number(self, number_str: str) -> Optional[float]:
        """Parse number string handling various formats."""
        try:
            number_str = str(number_str).strip()
            
            # Handle numbers in parentheses for negatives: (1,234.56) -> -1234.56
            is_negative = number_str.startswith('(') and number_str.endswith(')')
            if is_negative:
                number_str = number_str[1:-1]
            
            # Remove commas and spaces
            cleaned_str = number_str.replace(',', '').replace(' ', '')
            
            # Check for empty or placeholder values
            if not cleaned_str or cleaned_str in ['-', '—', 'nan', 'None', '']:
                return None
            
            # Convert to float
            number = float(cleaned_str)
            
            # Apply negative if needed
            if is_negative:
                number *= -1
            
            # Sanity check
            if math.isnan(number) or math.isinf(number):
                return None
            
            return number
            
        except (ValueError, TypeError):
            return None
    
    def _detect_scale(self, context: str) -> Dict:
        """Detect scale multipliers from context."""
        context_lower = context.lower()
        
        best_scale = {
            'name': 'units',
            'multiplier': 1,
            'priority': 0,
            'confidence': 0.5
        }
        
        for scale_name, scale_data in SCALE_INDICATORS.items():
            for pattern in scale_data['patterns']:
                if re.search(pattern, context_lower):
                    if scale_data['priority'] > best_scale['priority']:
                        best_scale = {
                            'name': scale_name,
                            'multiplier': scale_data['multiplier'],
                            'priority': scale_data['priority'],
                            'confidence': 0.8
                        }
        
        return best_scale
    
    def extract_numbers_with_context(self, text: str, 
                                    window_size: int = 100) -> List[Dict]:
        """Extract numbers with surrounding context for better validation."""
        numbers = []
        
        # Enhanced pattern to capture various number formats
        pattern = r'\(?([\d,]+(?:\.\d+)?)\)?'
        
        for match in re.finditer(pattern, text):
            try:
                num_str = match.group(0)
                number = self._parse_number(num_str)
                
                if number is not None and number != 0:
                    # Extract context window
                    start, end = match.span()
                    context_start = max(0, start - window_size)
                    context_end = min(len(text), end + window_size)
                    context = text[context_start:context_end]
                    
                    # Detect scale from context
                    scale_info = self._detect_scale(context)
                    
                    # Don't apply scale to very small numbers (likely ratios/percentages)
                    if 0 < number < 100:
                        scaled_number = number
                        scale_info['multiplier'] = 1
                        scale_info['name'] = 'units (ratio detected)'
                    else:
                        scaled_number = number * scale_info['multiplier']
                    
                    numbers.append({
                        'value': scaled_number,
                        'original_value': number,
                        'context': context,
                        'scale_info': scale_info,
                        'confidence': 0.7
                    })
                    
            except (ValueError, TypeError):
                continue
        
        # Remove duplicates and sort by confidence
        unique_numbers = self._deduplicate_numbers(numbers)
        return sorted(unique_numbers, key=lambda x: x['confidence'], reverse=True)
    
    def _deduplicate_numbers(self, numbers: List[Dict]) -> List[Dict]:
        """Remove duplicate numbers that are likely the same value."""
        if not numbers:
            return []
        
        unique_numbers = []
        seen_values = set()
        
        for num_data in numbers:
            value = num_data['value']
            
            # Check if we've seen a very similar value
            is_duplicate = False
            for seen_value in seen_values:
                if abs(value - seen_value) / max(abs(value), abs(seen_value), 1) < 0.01:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_numbers.append(num_data)
                seen_values.add(value)
        
        return unique_numbers


# Initialize global instances
validator = FinancialValidator()
number_processor = NumberProcessor()

print("Part 1 loaded: Core setup, validation, validation, and number processing")


# Part 2 of 3: Table Processing, Text Extraction, and OCR

# -------------------------
# SMART TABLE PROCESSING
# -------------------------

class SmartTableProcessor:
    """Intelligent table processing with financial relevance filtering."""
    
    def __init__(self):
        self.financial_keywords = {
            'high_priority': [
                'revenue', 'income', 'profit', 'loss', 'assets', 'liabilities',
                'equity', 'cash', 'debt', 'earnings', 'sales', 'total'
            ],
            'medium_priority': [
                'operations', 'operating', 'financial', 'consolidated',
                'balance', 'statement', 'year', 'period', 'ended'
            ]
        }
    
    def _clean_table_enhanced(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enhanced table cleaning with better data preservation."""
        if df.empty:
            return df
        
        try:
            # Convert to string for consistent processing
            df = df.astype(str)
            
            # Replace whitespace-only cells with NaN
            df = df.replace(r'^\s*$', np.nan, regex=True)
            
            # Drop completely empty rows and columns
            df = df.dropna(how='all').dropna(axis=1, how='all')
            
            # Clean cell values
            for col in df.columns:
                df[col] = df[col].replace({
                    'nan': '',
                    'None': '',
                    'null': '',
                    '—': '',
                    '–': ''
                })
            
            # Reset index
            df = df.reset_index(drop=True)
            
            return df
            
        except Exception as e:
            print(f" Table cleaning error: {e}")
            return pd.DataFrame()
    
    def extract_tables_smart(self, pdf_path: str) -> Tuple[List[pd.DataFrame], List[Dict]]:
        """Extract and filter tables with multiple fallback methods."""
        tables = []
        metadata = []
        
        # Method 1: Camelot Lattice (best for structured tables)
        try:
            camelot_tables = camelot.read_pdf(
                pdf_path,
                pages='all',
                flavor='lattice',
                suppress_stdout=True
            )
            
            for i, table in enumerate(camelot_tables):
                if not table.df.empty and table.df.shape[0] > 2:
                    cleaned_df = self._clean_table_enhanced(table.df)
                    if not cleaned_df.empty:
                        tables.append(cleaned_df)
                        metadata.append({
                            "source": "camelot_lattice",
                            "page": table.page,
                            "table_id": f"camelot_lattice_{i}"
                        })
        except Exception as e:
            print(f" Camelot lattice failed: {e}")
        
        # Method 2: Camelot Stream (fallback)
        if len(tables) < 3:
            try:
                camelot_tables = camelot.read_pdf(
                    pdf_path,
                    pages='all',
                    flavor='stream',
                    suppress_stdout=True
                )
                
                for i, table in enumerate(camelot_tables):
                    if not table.df.empty and table.df.shape[0] > 2:
                        cleaned_df = self._clean_table_enhanced(table.df)
                        if not cleaned_df.empty:
                            tables.append(cleaned_df)
                            metadata.append({
                                "source": "camelot_stream",
                                "page": table.page,
                                "table_id": f"camelot_stream_{i}"
                            })
            except Exception as e:
                print(f" Camelot stream failed: {e}")
        
        # Method 3: PDFplumber (ultimate fallback)
        if len(tables) < 2:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages[:10], start=1):
                        page_tables = page.extract_tables()
                        
                        for j, table_data in enumerate(page_tables):
                            if table_data and len(table_data) > 2:
                                try:
                                    # Create DataFrame
                                    headers = table_data[0] if table_data[0] else [
                                        f"Col_{i}" for i in range(len(table_data[1]))
                                    ]
                                    df = pd.DataFrame(table_data[1:], columns=headers)
                                    cleaned_df = self._clean_table_enhanced(df)
                                    
                                    if not cleaned_df.empty:
                                        tables.append(cleaned_df)
                                        metadata.append({
                                            "source": "pdfplumber",
                                            "page": page_num,
                                            "table_id": f"pdfplumber_{page_num}_{j}"
                                        })
                                except Exception:
                                    continue
            except Exception as e:
                print(f" PDFplumber failed: {e}")
        
        print(f" Found {len(tables)} tables via combined methods.")
        if tables and DEBUG_MODE:
         print("\n" + "="*70)
         print("DEBUG - First Table Structure (first 6 rows):")
         print("="*70)
         print(tables[0].head(6))
         print("="*70 + "\n")
        return tables, metadata
    
    def _extract_document_scale(self, tables: List[pd.DataFrame]) -> Dict:
        """Extract scale from document headers found within tables."""
        for table in tables[:5]: # Check first 5 tables
            try:
                # Combine first 2 rows into a single string to check for headers
                header_text = " ".join(
                    str(val) for row_idx in range(min(2, len(table)))
                    for val in table.iloc[row_idx].values
                ).lower()
                
                # Check for scale indicators
                if any(indicator in header_text for indicator in 
                      ['in thousands', "'000", "(000)", "in '000"]):
                    print(" ✓ Document scale detected: Thousands (×1,000)")
                    return {
                        'multiplier': 1000,
                        'name': 'thousands',
                        'confidence': 0.95
                    }
                
                if 'in millions' in header_text:
                    print(" ✓ Document scale detected: Millions (×1,000,000)")
                    return {
                        'multiplier': 1000000,
                        'name': 'millions',
                        'confidence': 0.95
                    }
                
                if 'in billions' in header_text:
                    print(" ✓ Document scale detected: Billions (×1,000,000,000)")
                    return {
                        'multiplier': 1000000000,
                        'name': 'billions',
                        'confidence': 0.95
                    }
                    
            except Exception:
                continue
        
        print(" ! No document-wide scale detected, assuming units.")
        return {
            'multiplier': 1,
            'name': 'units',
            'confidence': 0.5
        }


# -------------------------
# ENHANCED TEXT EXTRACTION
# -------------------------

class SmartTextExtractor:
    """Enhanced text extraction with context awareness."""
    
    def __init__(self):
        self.cache = {}
    
    def extract_text(self, pdf_path: str) -> str:
        """Extract text from PDF with error handling."""
        if pdf_path in self.cache:
            return self.cache[pdf_path]
        
        text = ""
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:20]: # Limit to first 20 pages
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    except Exception as e:
                        if DEBUG_MODE:
                            print(f" Page text extraction error: {e}")
                        continue
        except Exception as e:
            print(f" Text extraction error: {e}")
        
        # Fallback to PyMuPDF if PDFplumber fails
        if not text or len(text) < 100:
            try:
                doc = fitz.open(pdf_path)
                for page_num in range(min(20, len(doc))):
                    try:
                        page = doc[page_num]
                        page_text = page.get_text()
                        if page_text:
                            text += page_text + "\n"
                    except Exception:
                        continue
                doc.close()
            except Exception as e:
                print(f" PyMuPDF text extraction error: {e}")
        
        self.cache[pdf_path] = text
        print(f" Extracted {len(text)} characters of text")
        return text if text else ""
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        return text.strip()


# -------------------------
# OPTIMIZED OCR PROCESSING
# -------------------------

class SmartOCRProcessor:
    """Optimized OCR processing with selective application."""
    
    def __init__(self):
        self.ocr_cache = {}
    
    def ocr_pdf(self, pdf_path: str, max_pages: int = 3) -> str:
        """Smart OCR that only processes pages that need it."""
        if pdf_path in self.ocr_cache:
            return self.ocr_cache[pdf_path]
        
        ocr_text = ""
        
        try:
            doc = fitz.open(pdf_path)
            
            # Only OCR first few pages if text extraction failed
            for page_num in range(min(max_pages, len(doc))):
                try:
                    page = doc[page_num]
                    
                    # Check if page has text
                    text = page.get_text()
                    if text and len(text.strip()) > 50:
                        continue # Skip OCR if text exists
                    
                    # Perform OCR
                    page_text = self._ocr_page(page, page_num + 1)
                    if page_text:
                        ocr_text += f"\n--- PAGE {page_num + 1} OCR ---\n{page_text}\n"
                        
                except Exception as e:
                    if DEBUG_MODE:
                        print(f" OCR failed for page {page_num + 1}: {e}")
                    continue
            
            doc.close()
            
        except Exception as e:
            print(f" OCR processing error: {e}")
        
        self.ocr_cache[pdf_path] = ocr_text
        
        if ocr_text:
            print(f" OCR extracted {len(ocr_text)} characters")
        
        return ocr_text
    
    def _ocr_page(self, page, page_num: int) -> str:
        """OCR a single page with optimized settings."""
        try:
            # Create high-quality image
            mat = fitz.Matrix(2.0, 2.0) # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            # Enhance image for better OCR
            img = img.convert('L') # Convert to grayscale
            
            # OCR with optimized config
            config = r'--oem 3 --psm 6'
            
            text = pytesseract.image_to_string(
                img,
                config=config,
                timeout=30
            )
            
            # Clean OCR text
            if text:
                text = re.sub(r'\n\s*\n', '\n', text)
                text = re.sub(r' +', ' ', text)
                return text.strip()
            
            return ""
            
        except Exception as e:
            if DEBUG_MODE:
                print(f" Page {page_num} OCR error: {e}")
            return ""


# Initialize processors
table_processor = SmartTableProcessor()
text_extractor = SmartTextExtractor()
ocr_processor = SmartOCRProcessor()

print("Part 2 loaded: Table processing, text extraction, and OCR")


# Part 3 of 3: Financial Extraction Logic, Main Pipeline, and Execution

# -------------------------
# FINANCIAL EXTRACTION ORCHESTRATOR
# -------------------------

class FinancialExtractor:
    """Orchestrates multiple extraction methods with intelligent result aggregation."""
    
    def __init__(self):
        self.validator = validator
        self.number_processor = number_processor
    
    def _extract_latest_value_from_row(self, row_data: pd.Series) -> Optional[float]:
        
        
        # Iterate in reverse order, skipping the first column (which is the label)
        for val in reversed(row_data.values[1:]):
            val_str = str(val).strip()
            
            # Skip empty, null, or invalid values
            if not val_str or val_str.lower() in ['nan', 'none', '', '-']:
                continue
            
            # Handle cells with multiple values separated by \n (common in extracted tables)
            if '\n' in val_str:
                parts = [p.strip() for p in val_str.split('\n')]
                
                for part in parts:
                    # Skip percentage values (e.g., "2.4%", "15.6%")
                    if '%' in part:
                        continue
                    
                    # Skip empty parts
                    if not part or part == '-':
                        continue
                    
                    # Try to parse as number
                    number = self.number_processor._parse_number(part)
                    if number is not None and number != 0:
                        return number
            else:
                # Single value in cell - just parse it
                number = self.number_processor._parse_number(val_str)
                if number is not None and number != 0:
                    return number
        
        return None
    
    def _extract_from_tables_rules(self, metric: str, concept_data: Dict,
                                  tables: List[pd.DataFrame], 
                                  metadata: List[Dict]) -> List[Dict]:
        """Rule-based table extraction with strict term matching and comprehensive filtering."""
        candidates = []
        primary_terms = concept_data['primary_terms']
        negative_terms = concept_data.get('negative_terms', [])
        
        for i, (table, meta) in enumerate(zip(tables, metadata)):
            try:
                for row_idx, row in table.iterrows():
                    # Get the label (first column)
                    first_cell_raw = str(row.iloc[0]).strip()
                    first_cell = first_cell_raw.lower()
                    
                    # Skip empty, null, or header-like rows
                    if not first_cell or first_cell in ['nan', 'none', '', 'assets', 'liabilities', 'equity']:
                        continue
                    
                    # STEP 1: Check negative terms FIRST (critical for avoiding false matches)
                    should_skip = False
                    for neg_term in negative_terms:
                        # Use word-boundary matching for negative terms too
                        if re.search(r'\b' + re.escape(neg_term) + r'\b', first_cell):
                            if DEBUG_MODE:
                                print(f" → Skipping (negative term '{neg_term}'): {first_cell[:50]}")
                            should_skip = True
                            break
                    
                    if should_skip:
                        continue
                    
                    # STEP 2: Check primary terms with strict matching
                    for term in primary_terms:
                        # Use word boundary regex to avoid partial matches
                        # Example: "equity" won't match "equity investments"
                        term_pattern = r'\b' + re.escape(term) + r'\b'
                        
                        if re.search(term_pattern, first_cell):
                            # Extract the latest value from this row
                            latest_value = self._extract_latest_value_from_row(row)
                            
                            if latest_value is not None:
                                # STEP 3: Additional validation filters
                                
                                # Filter 1: Size validation for major balance sheet items
                                if metric in ['Total Assets', 'Total Liabilities', 'Shareholders\' Equity']:
                                    # Reject suspiciously small values (likely artifacts or sub-items)
                                    if latest_value < 1_000_000:  # Less than 1 million
                                        if DEBUG_MODE:
                                            print(f" → Rejecting {latest_value:,.0f} from '{first_cell[:40]}' (too small for {metric})")
                                        continue
                                
                                # Filter 2: Context check for Equity specifically
                                if metric == "Shareholders' Equity":
                                    # Additional liability indicators to reject
                                    liability_indicators = [
                                        'deposit', 'borrowed', 'payable', 
                                        'liability', 'debt', 'loan'
                                    ]
                                    if any(indicator in first_cell for indicator in liability_indicators):
                                        if DEBUG_MODE:
                                            print(f" → Rejecting '{first_cell[:50]}' (liability indicator found)")
                                        continue
                                    
                                    # Make sure it's actually the "Equity" line or "Total Equity" line
                                    if first_cell not in ['equity', 'total equity', 'shareholders\' equity', 'shareholders equity']:
                                        # Be lenient but log it
                                        if DEBUG_MODE:
                                            print(f" → Weak match for equity: '{first_cell}'")
                                
                                # STEP 4: Validate using the validator
                                validation = self.validator.validate_value(
                                    metric, 
                                    latest_value, 
                                    confidence=0.85, 
                                    context=first_cell
                                )
                                
                                if validation['is_valid']:
                                    candidates.append({
                                        'value': latest_value,  # Store RAW value (will be scaled later)
                                        'confidence': validation['confidence_adjusted'],
                                        'method': 'rule_table_latest',
                                        'source': f"Pg {meta.get('page', '?')}, Row '{first_cell_raw}'",
                                        'validation': validation,
                                        'row_label': first_cell  # Store for debugging
                                    })
                                    
                                    if DEBUG_MODE:
                                        print(f" ✓ Valid candidate: '{first_cell[:50]}' → {latest_value:,.0f}")
                                    
                                    # Found a match for this term, move to next row
                                    break
                                else:
                                    if DEBUG_MODE:
                                        print(f" ✗ Validation failed for {latest_value:,.0f} from '{first_cell[:40]}'")
                            
            except Exception as e:
                if DEBUG_MODE:
                    print(f" Error processing table {i+1} for '{metric}': {e}")
                continue
        
        return candidates
    
    def _extract_from_text_rules(self, metric: str, concept_data: Dict, 
                                text: str) -> List[Dict]:
        """Rule-based text extraction."""
        candidates = []
        primary_terms = concept_data['primary_terms']
        negative_terms = concept_data.get('negative_terms', [])
        
        for term in primary_terms:
            # Find term followed by numbers within 100 characters
            pattern = rf"{re.escape(term)}[\s\S]{{0,100}}?((?:\(?\d[\d,.]*\)?)+)"
            
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    context = match.group(0)
                    
                    # Check for negative terms in context
                    if any(neg_term in context.lower() for neg_term in negative_terms):
                        continue
                    
                    # Extract numbers from context
                    numbers = self.number_processor.extract_numbers_with_context(context)
                    
                    for num_data in numbers[:1]: # Take best match only
                        value = num_data['value']
                        
                        validation = self.validator.validate_value(
                            metric, 
                            value, 
                            num_data['confidence'], 
                            context
                        )
                        
                        if validation['is_valid']:
                            candidates.append({
                                'value': value,
                                'confidence': validation['confidence_adjusted'] * 0.7, # Text discount
                                'method': 'rule_text',
                                'source': f"Text match on '{term}'",
                                'validation': validation
                            })
                            
                except Exception:
                    continue
        
        return candidates
    
    def _select_best_candidate(self, metric: str, candidates: List[Dict]) -> Dict:
        """Select the best candidate from multiple extraction attempts."""
        
        if DEBUG_MODE:
            print(f"\n DEBUG - All candidates for {metric}:")
            sorted_candidates = sorted(
                candidates, 
                key=lambda x: x.get('confidence', 0), 
                reverse=True
            )
            for i, c in enumerate(sorted_candidates[:10]):
                val_str = f"{c.get('value'):,.0f}" if c.get('value') is not None else "N/A"
                conf = c.get('confidence', 0)
                method = c.get('method', 'unknown')
                source = c.get('source', 'unknown')[:50]
                print(f" {i+1}. {val_str:<20} | conf={conf:.2f} | {method:<20} | {source}")
        
        if not candidates:
            return {
                'value': None,
                'confidence': 0.0,
                'method': 'not_found',
                'source': 'No candidates found'
            }
        
        # Filter out invalid candidates
        valid_candidates = [
            c for c in candidates 
            if c.get('validation', {}).get('is_valid', False)
        ]
        
        if not valid_candidates:
            return {
                'value': None,
                'confidence': 0.0,
                'method': 'validation_failed',
                'source': f"{len(candidates)} candidates rejected by validation"
            }
        
        # Sort by confidence
        valid_candidates.sort(key=lambda x: x['confidence'], reverse=True)
        
        # Check for consensus among top candidates
        top_candidates = valid_candidates[:3]
        
        if len(top_candidates) >= 2:
            top_value = top_candidates[0]['value']
            
            # Relaxed consensus tolerance: 5% difference
            agreeing = [
                c for c in top_candidates 
                if abs(c['value'] - top_value) / max(abs(top_value), 1) < 0.05
            ]
            
            if len(agreeing) >= 2:
                best = top_candidates[0].copy()
                best['confidence'] = min(0.99, best['confidence'] * 1.15)
                best['method'] += "_consensus"
                
                if DEBUG_MODE:
                    print(f" → Consensus found: {len(agreeing)} candidates agree")
                
                return best
        
        return valid_candidates[0]
    
    def extract_all_metrics(self, tables: List[pd.DataFrame], 
                          table_metadata: List[Dict], 
                          full_text: str, 
                          document_scale: Dict) -> Dict:
        """Main extraction orchestrator with proper scaling logic."""
        results = {}
        scale_multiplier = document_scale['multiplier']
        
        print(f"\n{'='*70}")
        print(f"Extracting metrics with document scale: {document_scale['name']} (×{scale_multiplier:,})")
        print(f"{'='*70}")
        
        for metric, concept_data in FINANCIAL_CONCEPTS.items():
            print(f"\n Processing: {metric}...")
            
            candidates = []
            
            # Collect candidates from all methods
            candidates.extend(
                self._extract_from_tables_rules(metric, concept_data, tables, table_metadata)
            )
            candidates.extend(
                self._extract_from_text_rules(metric, concept_data, full_text)
            )
            
            # Select best candidate (still unscaled)
            best_result = self._select_best_candidate(metric, candidates)
            
            # Apply document scale to table-based extractions
            if best_result.get('value') is not None and 'table' in best_result.get('method', ''):
                original_value = best_result['value']
                
                # Don't scale if value looks like a ratio/percentage
                if 0 < original_value < 100:
                    scaled_value = original_value
                    if DEBUG_MODE:
                        print(f" → Skipping scale (likely ratio): {original_value}")
                else:
                    scaled_value = original_value * scale_multiplier
                    
                    if DEBUG_MODE:
                        print(f" → Applying scale: {original_value:,.0f} × {scale_multiplier:,} = {scaled_value:,.0f}")
                
                # Re-validate the scaled value
                final_validation = self.validator.validate_value(
                    metric, 
                    scaled_value, 
                    best_result['confidence']
                )
                
                if final_validation['is_valid']:
                    best_result['value'] = scaled_value
                    best_result['original_value'] = original_value
                    best_result['confidence'] = final_validation['confidence_adjusted']
                    best_result['source'] += f" [scaled ×{scale_multiplier:,}]"
                else:
                    # Scaling made it invalid - likely wrong scale detection
                    if DEBUG_MODE:
                        print(f" ✗ Scaled value failed validation: {final_validation['issues']}")
                        print(f" → This suggests incorrect scale detection or artifact")
                    
                    # Mark as not found rather than using wrong value
                    best_result = {
                        'value': None,
                        'confidence': 0.0,
                        'method': 'scaling_validation_failed',
                        'source': best_result['source']
                    }
            
            results[metric] = best_result
            
            # Print result
            if best_result.get('value') is not None:
                print(f" ✓ Found: {best_result['value']:,.0f} (confidence: {best_result['confidence']:.2%})")
            else:
                print(f" ✗ Not found ({best_result.get('method', 'unknown')})")
        
        return results


# Initialize extractor
financial_extractor = FinancialExtractor()


# -------------------------
# MAIN PROCESSING PIPELINE
# -------------------------

def process_pdf_complete(pdf_path: str) -> Tuple[Dict, Dict]:
    """Complete processing pipeline with all fixes applied."""
    pdf_name = os.path.basename(pdf_path)
    
    print(f"\n{'='*70}")
    print(f"Processing: {pdf_name}")
    print(f"{'='*70}")
    
    # Step 1: Extract tables
    print("\n[1/5] Extracting tables...")
    tables, table_metadata = table_processor.extract_tables_smart(pdf_path)
    
    if not tables:
        print(" ✗ FATAL: No tables extracted. Cannot continue.")
        return {}, {}
    
    # Step 2: Extract full text
    print("\n[2/5] Extracting full text...")
    full_text = text_extractor.extract_text(pdf_path)
    
    # Step 3: OCR fallback if needed
    if not full_text or len(full_text) < 500:
        print("\n[3/5] Running OCR (low text content detected)...")
        ocr_text = ocr_processor.ocr_pdf(pdf_path)
        full_text += ocr_text
    else:
        print("\n[3/5] Skipping OCR (sufficient text extracted)")
    
    # Step 4: Detect document-wide scale
    print("\n[4/5] Detecting document-wide scale...")
    doc_scale = table_processor._extract_document_scale(tables)
    
    # Step 5: Extract financial metrics
    print("\n[5/5] Extracting financial metrics...")
    results = financial_extractor.extract_all_metrics(
        tables, 
        table_metadata, 
        full_text, 
        doc_scale
    )
    
    # Validate balance sheet
    print(f"\n{'='*70}")
    print("Balance Sheet Validation")
    print(f"{'='*70}")
    
    assets = results.get("Total Assets", {}).get("value")
    liabilities = results.get("Total Liabilities", {}).get("value")
    equity = results.get("Shareholders' Equity", {}).get("value")
    
    balance_validation = validator.validate_balance_sheet(
        assets or 0, 
        liabilities or 0, 
        equity or 0
    )
    
    print(f" Status: {balance_validation['status']}")
    print(f" Confidence: {balance_validation['confidence']:.1%}")
    
    if balance_validation.get('details'):
        details = balance_validation['details']
        print(f" Assets: {details.get('assets', 0):>20,.0f}")
        print(f" L + E: {details.get('expected_total', 0):>20,.0f}")
        print(f" Difference: {details.get('difference', 0):>20,.0f} ({details.get('error_percentage', 0):.2f}%)")
    
    validation_summary = {
        'balance_sheet': balance_validation,
        'document_scale': doc_scale
    }
    
    print(f"\n{'='*70}")
    print(f"Processing complete for {pdf_name}")
    print(f"{'='*70}\n")
    
    return results, validation_summary


# -------------------------
# OUTPUT AND REPORTING
# -------------------------

def print_final_results(pdf_name: str, results: Dict, validation: Dict):
    """Print comprehensive final results."""
    print(f"\n{'='*70}")
    print(f"FINAL RESULTS: {pdf_name}")
    print(f"{'='*70}\n")
    
    print("Extracted Financial Metrics:")
    print("-" * 70)
    
    for metric, data in results.items():
        val = data.get('value')
        conf = data.get('confidence', 0)
        method = data.get('method', 'unknown')
        
        if val is not None:
            status = "✓" if conf > 0.7 else "⚠" if conf > 0.4 else "✗"
            print(f"{status} {metric:<28} {val:>18,.0f} ({conf:>5.1%}) [{method}]")
        else:
            print(f"✗ {metric:<28} {'Not Found':>18} ( 0.0%) [{method}]")
    
    print("\n" + "-" * 70)
    
    balance = validation.get('balance_sheet', {})
    doc_scale = validation.get('document_scale', {})
    
    print(f"\nBalance Sheet: {balance.get('status', 'Unknown')}")
    print(f"Document Scale: {doc_scale.get('name', 'unknown')} (×{doc_scale.get('multiplier', 1):,})")
    
    print(f"\n{'='*70}\n")


# -------------------------
# MAIN EXECUTION
# -------------------------

if __name__ == "__main__":
    print("="*70)
    print("AI-ENHANCED FINANCIAL DATA EXTRACTOR - V4 COMPLETE")
    print("="*70)
    print(f"\nDEBUG_MODE: {'ENABLED' if DEBUG_MODE else 'DISABLED'}")
    print(f"RAW_DIR: {RAW_DIR}")
    print(f"OUTPUT_DIR: {OUTPUT_DIR}\n")
    
    # Find PDF files
    pdf_files = [f for f in os.listdir(RAW_DIR) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print(f"✗ No PDF files found in '{RAW_DIR}' directory.")
        print(f" Please add PDF financial reports to process.\n")
        exit(0)
    
    print(f"Found {len(pdf_files)} PDF file(s) to process:")
    for pdf in pdf_files:
        print(f" • {pdf}")
    print()
    
    # Process each PDF
    for pdf_file in pdf_files:
        pdf_path = os.path.join(RAW_DIR, pdf_file)
        
        try:
            # Process the PDF
            results, validation = process_pdf_complete(pdf_path)
            
            # Print final results
            if results:
                print_final_results(pdf_file, results, validation)
            else:
                print(f"\n✗ Failed to extract any metrics from {pdf_file}\n")
            
        except Exception as e:
            print(f"\n{'='*70}")
            print(f"✗✗✗ FATAL ERROR processing {pdf_file} ✗✗✗")
            print(f"{'='*70}")
            print(f"Error: {e}\n")
            
            import traceback
            traceback.print_exc()
            print()
    
    print("="*70)
    print("EXTRACTION COMPLETE")
    print("="*70)

print("Part 3 loaded: Extraction logic, main pipeline, and execution")
print("\n" + "="*70)
print("ALL PARTS LOADED - SYSTEM READY")
print("="*70)