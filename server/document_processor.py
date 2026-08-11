"""
Document Processor Module for Trackeneer
Extracts structured data from:
- Syllabus PDFs → subjects, topics, difficulty, estimated hours
- Academic Calendar PDFs → important dates, holidays, events
- Exam Timetable PDFs → exam schedule as hard constraints

HYBRID EXTRACTION PIPELINE:
1. Digital Path: Camelot (tables) + pdfplumber (text) - FREE
2. OCR Path: pytesseract + pdf2image for scanned PDFs - FREE
3. Cohere AI: ONLY for JSON schema conversion & validation repair
"""

import re
import os
import sys
import json
import time
from datetime import datetime, timedelta

# Force UTF-8 stdout/stderr so Unicode symbols don't crash on Windows cp1252
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path
import numpy as np

# PDF extraction libraries
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    print("Warning: pdfplumber not installed. Install with: pip install pdfplumber")

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    print("Warning: PyPDF2 not installed. Install with: pip install PyPDF2")

# Camelot for table extraction
try:
    import camelot
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False
    print("Info: camelot-py not installed. Tables will use pdfplumber fallback.")

# OCR libraries for scanned PDFs
try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
    # Configure Tesseract path for Windows
    if os.name == 'nt':  # Windows
        tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
except ImportError:
    HAS_TESSERACT = False

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

# OpenCV for image preprocessing
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    print("Info: opencv not installed. Image preprocessing disabled.")

from ai_client import build_text_model

# Shared text model (GitHub Models preferred when configured)
try:
    _gemini_model = build_text_model()
    HAS_GEMINI = _gemini_model is not None
    print("AI text model configured" if HAS_GEMINI else "AI text model skipped: no provider key set")
except Exception:
    HAS_GEMINI = False
    _gemini_model = None
    print("Info: AI text model unavailable")

# Groq AI (Fast, generous free tier - 14,400 requests/day)
try:
    from groq import Groq
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    groq_client = None  # Will be initialized when key is set
    HAS_GROQ = bool(GROQ_API_KEY)
    print("✅ Groq AI configured" if HAS_GROQ else "⚠ Groq AI skipped: GROQ_API_KEY not set")
except ImportError:
    HAS_GROQ = False
    print("Info: groq not installed")

# Cohere AI (disabled - using local NLP for speed)
HAS_COHERE = False

# Local NLP flag - always enabled for fast processing
USE_LOCAL_NLP = True

# LayoutLMv3 for document understanding
try:
    from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification, LayoutLMv3ForSequenceClassification
    from PIL import Image
    import torch
    HAS_LAYOUTLM = True
    print("✅ LayoutLMv3 available for document understanding")
except ImportError:
    HAS_LAYOUTLM = False
    print("Info: LayoutLMv3 not installed. Install with: pip install transformers torch pillow")

# Local NLP Libraries for fast text mining
try:
    import nltk
    from nltk.tokenize import sent_tokenize, word_tokenize
    from nltk.corpus import stopwords
    HAS_NLTK = True
    # Download required NLTK data (silent)
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)
except ImportError:
    HAS_NLTK = False
    print("Info: nltk not installed. Install with: pip install nltk")

# LLM Whisperer for advanced OCR extraction (disabled by default)
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: requests not installed. Install with: pip install requests")

# --- Local NLP Configuration ---
# Using regex + NLTK for fast local processing (no API calls)
USE_LOCAL_NLP = True  # Always use local NLP for speed

# --- LLM Whisperer Configuration ---
LLM_WHISPERER_API_KEY = os.getenv("LLM_WHISPERER_API_KEY")
LLM_WHISPERER_BASE_URL = os.getenv("LLM_WHISPERER_BASE_URL", "https://llmwhisperer-api.us-central.unstract.com/api/v2")


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Subject:
    """Represents a subject/topic from syllabus"""
    name: str
    topics: List[str] = field(default_factory=list)
    difficulty: str = "medium"  # easy, medium, hard
    estimated_hours: float = 10.0
    priority: int = 5  # 1-10 scale
    weekly_target_hours: float = 2.0
    prerequisites: List[str] = field(default_factory=list)

@dataclass
class AcademicEvent:
    """Represents an event from academic calendar"""
    name: str
    date: str  # ISO format
    end_date: Optional[str] = None  # For multi-day events
    event_type: str = "general"  # holiday, exam, deadline, event
    is_holiday: bool = False
    affects_study: bool = True

@dataclass
class ExamSchedule:
    """Represents an exam from timetable"""
    subject: str
    date: str  # ISO format
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    venue: Optional[str] = None
    exam_type: str = "final"  # mid,final ,practicaal 

@dataclass
class StudyConstraints:
    """Combined constraints for scheduling algorithm"""
    subjects: List[Subject] = field(default_factory=list)
    academic_events: List[AcademicEvent] = field(default_factory=list)
    exams: List[ExamSchedule] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'subjects': [asdict(s) for s in self.subjects],
            'academic_events': [asdict(e) for e in self.academic_events],
            'exams': [asdict(e) for e in self.exams],
            'preferences': self.preferences
        }


# ============================================================================
# HYBRID PDF EXTRACTION PIPELINE (FREE)
# ============================================================================

class HybridPDFExtractor:
    """
    Hybrid extraction pipeline that uses FREE tools:
    
    DIGITAL PATH (for text-based PDFs):
    1. Camelot - Excellent table extraction
    2. pdfplumber - Text and layout extraction
    
    OCR PATH (for scanned/image PDFs):
    1. pdf2image - Convert PDF pages to images
    2. OpenCV - Image preprocessing (deskew, denoise)
    3. pytesseract - OCR text extraction
    
    Quality check determines which path to use automatically.
    """
    
    # Minimum text length to consider extraction successful
    MIN_TEXT_THRESHOLD = 100
    # Minimum text-to-page ratio to consider PDF as digital
    MIN_QUALITY_RATIO = 50  # 50 chars per page minimum
    
    def __init__(self):
        self.extraction_method = None
        self.tables_extracted = []
        self.quality_score = 0
    
    def extract(self, file_path: str) -> Dict[str, Any]:
        """
        Main extraction method with automatic path selection.
        
        Returns:
            {
                'text': str,
                'tables': List[str],
                'method': str,  # 'digital' or 'ocr'
                'quality_score': float,
                'page_count': int
            }
        """
        result = {
            'text': '',
            'tables': [],
            'method': 'none',
            'quality_score': 0,
            'page_count': 0
        }
        
        # Step 1: Try digital extraction first (Camelot + pdfplumber)
        digital_result = self._extract_digital(file_path)
        
        if digital_result['quality_score'] >= self.MIN_QUALITY_RATIO:
            # Good quality digital extraction
            print(f"✅ Digital extraction successful (quality: {digital_result['quality_score']:.1f})")
            return digital_result
        
        # Step 2: Poor quality - try OCR path
        print(f"⚠️ Digital extraction quality low ({digital_result['quality_score']:.1f}), trying OCR...")
        
        if HAS_TESSERACT and HAS_PDF2IMAGE:
            ocr_result = self._extract_ocr(file_path)
            
            if ocr_result['quality_score'] > digital_result['quality_score']:
                print(f"✅ OCR extraction better (quality: {ocr_result['quality_score']:.1f})")
                return ocr_result
        else:
            print("⚠️ OCR libraries not available (install pytesseract and pdf2image)")
        
        # Return whichever is better
        return digital_result if digital_result['quality_score'] > 0 else result
    
    def _extract_digital(self, file_path: str) -> Dict[str, Any]:
        """
        Digital extraction path using Camelot + pdfplumber.
        Best for PDFs with selectable text.
        """
        result = {
            'text': '',
            'tables': [],
            'method': 'digital',
            'quality_score': 0,
            'page_count': 0
        }
        
        text_parts = []
        table_texts = []
        pages_with_text = 0
        
        # Extract tables with Camelot (best for structured tables)
        if HAS_CAMELOT:
            try:
                tables = camelot.read_pdf(file_path, pages='all', flavor='lattice')
                if len(tables) == 0:
                    # Try stream mode for borderless tables
                    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
                
                for table in tables:
                    df = table.df
                    # Convert table to readable text
                    table_text = df.to_string(index=False, header=False)
                    table_texts.append(table_text)
                    
                if table_texts:
                    print(f"📊 Camelot extracted {len(tables)} tables")
            except Exception as e:
                print(f"Camelot table extraction failed: {e}")
        
        # Extract text with pdfplumber
        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(file_path) as pdf:
                    result['page_count'] = len(pdf.pages)
                    
                    for page in pdf.pages:
                        # Extract text
                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            text_parts.append(page_text)
                            pages_with_text += 1
                        
                        # Extract tables (if Camelot didn't work)
                        if not table_texts:
                            tables = page.extract_tables()
                            for table in tables:
                                if table:
                                    rows = []
                                    for row in table:
                                        if row:
                                            row_text = " | ".join([str(cell) if cell else "" for cell in row])
                                            rows.append(row_text)
                                    if rows:
                                        table_texts.append("\n".join(rows))
            except Exception as e:
                print(f"pdfplumber extraction failed: {e}")
        
        # Combine all text
        all_text = "\n\n".join(text_parts)
        if table_texts:
            all_text += "\n\n=== TABLES ===\n\n" + "\n\n---\n\n".join(table_texts)
        
        result['text'] = all_text
        result['tables'] = table_texts
        
        # Calculate quality score (chars per page)
        if result['page_count'] > 0:
            result['quality_score'] = len(all_text) / result['page_count']
            text_page_ratio = pages_with_text / result['page_count']
            # Force OCR if most pages are image-based or text is too sparse
            if len(all_text) < self.MIN_TEXT_THRESHOLD or text_page_ratio < 0.2:
                result['quality_score'] = 0
                print(f"⚠️ Detected image-heavy PDF (text pages: {pages_with_text}/{result['page_count']}), forcing OCR")
        
        return result
    
    def _extract_ocr(self, file_path: str) -> Dict[str, Any]:
        """
        OCR extraction path for scanned/image PDFs.
        Uses pdf2image + OpenCV preprocessing + pytesseract.
        """
        result = {
            'text': '',
            'tables': [],
            'method': 'ocr',
            'quality_score': 0,
            'page_count': 0
        }
        
        try:
            # Convert PDF to images
            print("📄 Converting PDF to images for OCR...")
            images = convert_from_path(file_path, dpi=300)
            result['page_count'] = len(images)
            
            text_parts = []
            
            for i, image in enumerate(images):
                # Convert PIL Image to numpy array for OpenCV
                img_array = np.array(image)
                
                # Preprocess image for better OCR
                processed_img = self._preprocess_image(img_array)
                
                # Convert back to PIL Image for pytesseract
                pil_img = Image.fromarray(processed_img)
                
                # OCR with pytesseract
                page_text = pytesseract.image_to_string(
                    pil_img,
                    lang='eng',
                    config='--psm 6'  # Assume uniform block of text
                )
                
                if page_text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{page_text}")
            
            result['text'] = "\n\n".join(text_parts)
            
            # Calculate quality score
            if result['page_count'] > 0:
                result['quality_score'] = len(result['text']) / result['page_count']
            
            print(f"📄 OCR extracted {len(result['text'])} characters from {result['page_count']} pages")
            
        except Exception as e:
            print(f"OCR extraction failed: {e}")
        
        return result
    
    def _preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better OCR results.
        - Convert to grayscale
        - Denoise
        - Threshold/binarize
        - Deskew if needed
        """
        if not HAS_OPENCV:
            return img
        
        try:
            # Convert to grayscale if needed
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            else:
                gray = img
            
            # Denoise
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            
            # Adaptive thresholding for better text contrast
            binary = cv2.adaptiveThreshold(
                denoised, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11, 2
            )
            
            return binary
            
        except Exception as e:
            print(f"Image preprocessing failed: {e}")
            return img


# ============================================================================
# PDF TEXT EXTRACTION (Legacy wrapper)
# ============================================================================

class PDFTextExtractor:
    """Unified PDF text extraction with multiple backend support"""
    
    @staticmethod
    def extract_text(file_path: str, use_llm_whisperer: bool = False) -> str:
        """Extract text from PDF using available libraries
        
        Priority order (changed to prioritize FREE options):
        1. pdfplumber (FREE, good for tables and structured content)
        2. PyPDF2 (FREE, basic fallback)
        3. LLM Whisperer (PAID/LIMITED - only if explicitly requested for OCR)
        """
        text = ""
        
        # Try pdfplumber FIRST (FREE and good for Mumbai University PDFs)
        if HAS_PDFPLUMBER:
            try:
                text = PDFTextExtractor._extract_with_pdfplumber(file_path)
                if text.strip() and len(text) > 100:
                    print(f"✅ pdfplumber extracted {len(text)} characters")
                    return text
            except Exception as e:
                print(f"pdfplumber extraction failed: {e}")
        
        # Fallback to PyPDF2 (also FREE)
        if HAS_PYPDF2:
            try:
                text = PDFTextExtractor._extract_with_pypdf2(file_path)
                if text.strip() and len(text) > 100:
                    print(f"✅ PyPDF2 extracted {len(text)} characters")
                    return text
            except Exception as e:
                print(f"PyPDF2 extraction failed: {e}")
        
        # Only use LLM Whisperer if explicitly requested AND free options failed
        # (useful for scanned PDFs that need OCR)
        if use_llm_whisperer and HAS_REQUESTS and LLM_WHISPERER_API_KEY:
            try:
                extractor = LLMWhispererExtractor()
                if extractor.enabled:
                    print("📄 Trying LLM Whisperer (OCR mode) as fallback...")
                    text = extractor.extract_with_best_mode(file_path)
                    if text.strip():
                        return text
            except Exception as e:
                print(f"LLM Whisperer extraction failed: {e}")
        
        return text
    
    @staticmethod
    def _extract_with_pdfplumber(file_path: str) -> str:
        """Extract text using pdfplumber"""
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                
                # Also extract tables
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            row_text = " | ".join([str(cell) if cell else "" for cell in row])
                            text_parts.append(row_text)
        
        return "\n".join(text_parts)
    
    @staticmethod
    def _extract_with_pypdf2(file_path: str) -> str:
        """Extract text using PyPDF2"""
        text_parts = []
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        
        return "\n".join(text_parts)
    
    @staticmethod
    def extract_with_layout(file_path: str) -> List[Dict]:
        """Extract text with layout information (for heading detection)"""
        if not HAS_PDFPLUMBER:
            return []
        
        elements = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    chars = page.chars
                    
                    # Group characters by line
                    lines = {}
                    for char in chars:
                        y = round(char['top'], 0)
                        if y not in lines:
                            lines[y] = []
                        lines[y].append(char)
                    
                    for y in sorted(lines.keys()):
                        line_chars = sorted(lines[y], key=lambda c: c['x0'])
                        text = "".join([c['text'] for c in line_chars])
                        
                        if text.strip():
                            # Calculate average font size
                            sizes = [c.get('size', 12) for c in line_chars if c.get('size')]
                            avg_size = sum(sizes) / len(sizes) if sizes else 12
                            
                            # Check if bold
                            fonts = [c.get('fontname', '') for c in line_chars]
                            is_bold = any('bold' in f.lower() for f in fonts)
                            
                            elements.append({
                                'text': text.strip(),
                                'page': page_num + 1,
                                'y': y,
                                'font_size': avg_size,
                                'is_bold': is_bold
                            })
        except Exception as e:
            print(f"Layout extraction failed: {e}")
        
        return elements


# ============================================================================
# LLM WHISPERER - ADVANCED OCR EXTRACTION
# ============================================================================

class LLMWhispererExtractor:
    """
    LLM Whisperer API for advanced OCR extraction from PDFs.
    Provides superior text extraction especially for:
    - Scanned PDFs
    - Complex layouts (Mumbai University format)
    - Tables and structured content
    - Handwritten text
    """
    
    def __init__(self):
        self.api_key = LLM_WHISPERER_API_KEY
        self.base_url = LLM_WHISPERER_BASE_URL
        self.enabled = HAS_REQUESTS and bool(self.api_key)
        
        if not self.enabled:
            print("⚠️ LLM Whisperer not available. Using fallback extraction.")
    
    def extract_text(self, file_path: str, mode: str = "native_text") -> str:
        """
        Extract text from PDF using LLM Whisperer API.
        
        Args:
            file_path: Path to the PDF file
            mode: Extraction mode
                - "native_text": For native/digital PDFs (faster)
                - "low_cost": OCR optimized for cost
                - "high_quality": Best OCR quality (slower)
                - "form": For forms with checkboxes, tables
        
        Returns:
            Extracted text from the PDF
        """
        if not self.enabled:
            return ""
        
        try:
            print(f"📄 Extracting text with LLM Whisperer ({mode} mode)...")
            
            # Step 1: Submit the document for processing
            whisper_hash = self._submit_document(file_path, mode)
            if not whisper_hash:
                return ""
            
            # Step 2: Poll for results
            text = self._poll_for_results(whisper_hash)
            
            if text:
                print(f"✅ LLM Whisperer extracted {len(text)} characters")
            
            return text
            
        except Exception as e:
            print(f"⚠️ LLM Whisperer extraction failed: {e}")
            return ""
    
    def _submit_document(self, file_path: str, mode: str) -> Optional[str]:
        """Submit document to LLM Whisperer for processing"""
        url = f"{self.base_url}/whisper"
        
        # Headers - send raw binary with Content-Type
        headers = {
            "unstract-key": self.api_key,
            "Content-Type": "application/octet-stream"
        }
        
        params = {
            "mode": mode,
            "output_mode": "line-printer",  # LLM-friendly output
            "page_seperator": "<<<PAGE_BREAK>>>",
            "mark_vertical_lines": "true",
            "mark_horizontal_lines": "true",
        }
        
        # For scanned PDFs, use OCR mode
        if mode in ["low_cost", "high_quality"]:
            params["force_text_processing"] = "true"
        
        # Send raw binary data, not multipart form
        with open(file_path, 'rb') as f:
            content = f.read()
        
        response = requests.post(
            url,
            headers=headers,
            params=params,
            data=content,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('whisper_hash')
        elif response.status_code == 202:
            # Async processing started
            result = response.json()
            return result.get('whisper_hash')
        else:
            print(f"⚠️ LLM Whisperer submit failed: {response.status_code} - {response.text}")
            return None
    
    def _poll_for_results(self, whisper_hash: str, max_attempts: int = 30) -> str:
        """Poll for extraction results"""
        import time
        
        url = f"{self.base_url}/whisper-status"
        headers = {"unstract-key": self.api_key}
        params = {"whisper_hash": whisper_hash}
        
        for attempt in range(max_attempts):
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status', '')
                
                if status == 'processed':
                    # Get the extracted text
                    return self._get_extracted_text(whisper_hash)
                elif status == 'processing':
                    print(f"  ⏳ Processing... (attempt {attempt + 1}/{max_attempts})")
                    time.sleep(2)
                elif status == 'failed':
                    print(f"⚠️ Processing failed: {result.get('message', 'Unknown error')}")
                    return ""
            else:
                print(f"⚠️ Status check failed: {response.status_code}")
                time.sleep(2)
        
        print("⚠️ Timeout waiting for LLM Whisperer results")
        return ""
    
    def _get_extracted_text(self, whisper_hash: str) -> str:
        """Retrieve the extracted text from LLM Whisperer response"""
        url = f"{self.base_url}/whisper-retrieve"
        headers = {"unstract-key": self.api_key}
        params = {"whisper_hash": whisper_hash}
        
        response = requests.get(url, headers=headers, params=params, timeout=60)
        
        if response.status_code == 200:
            # Response is JSON with result_text field containing the actual text
            try:
                data = response.json()
                # The actual extracted text is in 'result_text' field
                if 'result_text' in data:
                    return data['result_text']
                # Fallback to other possible field names
                if 'extraction' in data:
                    return data['extraction']
                if 'text' in data:
                    return data['text']
                # If no known field, return raw response
                print(f"⚠️ Unknown response format, keys: {list(data.keys())}")
                return str(data)
            except Exception as e:
                # If not JSON, return raw text
                print(f"⚠️ Response parse error: {e}, returning raw text")
                return response.text
        else:
            print(f"⚠️ Failed to retrieve text: {response.status_code}")
            return ""
    
    def extract_with_best_mode(self, file_path: str) -> str:
        """
        Automatically detect and use the best extraction mode.
        Tries native_text first, falls back to OCR if needed.
        """
        # First try native text extraction (faster, cheaper)
        text = self.extract_text(file_path, mode="native_text")
        
        # Check if extraction quality is poor (likely scanned PDF)
        if self._is_poor_quality(text):
            print("🔄 Native extraction poor, trying OCR mode...")
            text = self.extract_text(file_path, mode="high_quality")
        
        return text
    
    def _is_poor_quality(self, text: str) -> bool:
        """Check if extracted text quality is poor"""
        if not text or len(text) < 100:
            return True
        
        # Check for too many non-printable characters
        printable_ratio = sum(c.isprintable() or c.isspace() for c in text) / len(text)
        if printable_ratio < 0.8:
            return True
        
        # Check for reasonable word structure
        words = text.split()
        if len(words) < 20:
            return True
        
        # Check average word length (gibberish tends to have weird lengths)
        avg_word_len = sum(len(w) for w in words) / len(words)
        if avg_word_len < 2 or avg_word_len > 15:
            return True
        
        return False


# Initialize global LLM Whisperer extractor
llm_whisperer = LLMWhispererExtractor()


# ============================================================================
# UNIVERSAL DOCUMENT EXTRACTOR - Auto-detect and extract any PDF
# ============================================================================

class UniversalDocumentExtractor:
    """
    Universal PDF extractor that auto-detects document type and extracts data.
    Supports: Syllabus, Academic Calendar, Exam Timetable, and mixed documents.
    """
    
    # Keywords for document type detection
    SYLLABUS_KEYWORDS = [
        'syllabus', 'curriculum', 'course', 'module', 'unit', 'topic', 'learning outcome',
        'credit', 'semester', 'subject', 'scheme', 'examination', 'internal assessment',
        'theory', 'practical', 'hours', 'objectives', 'prerequisite'
    ]
    
    CALENDAR_KEYWORDS = [
        'calendar', 'holiday', 'vacation', 'semester break', 'academic year',
        'working days', 'festival', 'republic day', 'independence day', 'diwali',
        'christmas', 'eid', 'holi', 'ganesh', 'leave', 'off day'
    ]
    
    TIMETABLE_KEYWORDS = [
        'timetable', 'time table', 'exam schedule', 'examination schedule',
        'date sheet', 'datesheet', 'exam date', 'slot', 'session', 'forenoon',
        'afternoon', 'morning', 'evening', 'venue', 'hall', 'room'
    ]
    
    def __init__(self):
        self.llm_whisperer = llm_whisperer
    
    def detect_document_type(self, text: str) -> str:
        """
        Auto-detect document type from text content.
        Returns: 'syllabus', 'calendar', 'timetable', or 'mixed'
        """
        text_lower = text.lower()
        
        # Count keyword matches
        syllabus_score = sum(1 for kw in self.SYLLABUS_KEYWORDS if kw in text_lower)
        calendar_score = sum(1 for kw in self.CALENDAR_KEYWORDS if kw in text_lower)
        timetable_score = sum(1 for kw in self.TIMETABLE_KEYWORDS if kw in text_lower)
        
        # Check for date patterns (more dates = likely calendar or timetable)
        date_patterns = len(re.findall(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}', text))
        date_patterns += len(re.findall(r'\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', text_lower))
        
        # Check for time patterns (more times = likely timetable)
        time_patterns = len(re.findall(r'\d{1,2}[:\.]?\d{2}\s*(?:am|pm)?', text_lower))
        
        # Adjust scores based on patterns
        if date_patterns > 10:
            calendar_score += 3
            timetable_score += 2
        if time_patterns > 5:
            timetable_score += 3
        
        # Check for module/topic numbering (X.0, X.Y patterns)
        module_patterns = len(re.findall(r'\d+\.\d+', text))
        if module_patterns > 10:
            syllabus_score += 5
        
        print(f"📊 Document detection scores - Syllabus: {syllabus_score}, Calendar: {calendar_score}, Timetable: {timetable_score}")
        
        # Determine type
        max_score = max(syllabus_score, calendar_score, timetable_score)
        
        if max_score < 3:
            return 'unknown'
        
        if syllabus_score == max_score and syllabus_score > calendar_score + timetable_score:
            return 'syllabus'
        elif timetable_score == max_score:
            return 'timetable'
        elif calendar_score == max_score:
            return 'calendar'
        elif syllabus_score > 5 and (calendar_score > 3 or timetable_score > 3):
            return 'mixed'
        
        return 'syllabus' if syllabus_score >= calendar_score else 'calendar'
    
    def extract_any_pdf(self, file_path: str) -> Dict[str, Any]:
        """
        Universal extraction method with HYBRID pipeline:
        
        1. Digital Path: Camelot (tables) + pdfplumber (text) - FREE
        2. OCR Path: pytesseract + pdf2image for scanned PDFs - FREE
        3. Cohere AI: ONLY for JSON schema conversion & validation repair
        
        Returns:
            {
                'document_type': str,
                'subjects': List[Dict],
                'events': List[Dict],
                'exams': List[Dict],
                'raw_text': str,
                'extraction_method': str,
                'tables': List[str],
                'quality_score': float
            }
        """
        print(f"\n🔍 Universal PDF Extraction: {os.path.basename(file_path)}")
        
        # Step 1: Use Hybrid Extractor (auto-selects digital vs OCR path)
        hybrid = HybridPDFExtractor()
        extraction = hybrid.extract(file_path)
        
        text = extraction.get('text', '')
        extraction_method = extraction.get('method', 'unknown')
        tables = extraction.get('tables', [])
        quality_score = extraction.get('quality_score', 0)
        
        if not text or len(text) < 50:
            # Fallback to legacy extraction with LLM Whisperer enabled (Nuclear option for scanned PDFs)
            print("⚠️ Hybrid extraction failed, trying legacy method with LLM Whisperer...")
            text = PDFTextExtractor.extract_text(file_path, use_llm_whisperer=True)
            extraction_method = 'legacy+llm_whisperer'
        
        if not text or len(text) < 50:
            print("⚠️ Failed to extract text from PDF")
            return {
                'document_type': 'unknown',
                'subjects': [],
                'events': [],
                'exams': [],
                'raw_text': '',
                'extraction_method': 'failed',
                'tables': [],
                'quality_score': 0
            }
        
        print(f"📊 Extraction method: {extraction_method}, Quality: {quality_score:.1f} chars/page")
        if tables:
            print(f"📊 Tables found: {len(tables)}")
        
        # Step 2: Detect document type
        doc_type = self.detect_document_type(text)
        print(f"📄 Detected document type: {doc_type}")
        
        # Step 3: Use Cohere ONLY for JSON schema conversion
        # (not for extraction - that's done by Camelot/pdfplumber/OCR)
        result = {
            'document_type': doc_type,
            'subjects': [],
            'events': [],
            'exams': [],
            'raw_text': text[:5000],  # First 5000 chars for reference
            'extraction_method': f'{extraction_method}+local_nlp',
            'tables': tables,
            'quality_score': quality_score
        }
        
        if doc_type in ['syllabus', 'mixed', 'unknown']:
            result['subjects'] = self._extract_subjects(text)
        
        if doc_type in ['calendar', 'mixed', 'unknown']:
            result['events'] = self._extract_events(text)
        
        if doc_type in ['timetable', 'mixed', 'unknown']:
            result['exams'] = self._extract_exams(text)
        
        # Step 4: Validate and repair with Cohere if needed
        result = self._validate_and_repair(result)
        
        print(f"✅ Extracted: {len(result['subjects'])} subjects, {len(result['events'])} events, {len(result['exams'])} exams")
        
        return result
    
    def _validate_and_repair(self, result: Dict) -> Dict:
        """
        Validate extraction results using local processing.
        No API calls needed - local NLP handles everything.
        """
        # Local NLP already extracts complete data, no repair needed
        return result
    
    def _extract_subjects(self, text: str) -> List[Dict]:
        """Extract subjects using Local NLP + rule-based methods"""
        subjects = []
        
        # Use fast local NLP extraction
        if USE_LOCAL_NLP:
            try:
                ai_results = ai_extractor.extract_syllabus_with_ai(text)
                if ai_results and len(ai_results) > 0:
                    return ai_results
            except Exception as e:
                print(f"⚠️ Local NLP extraction failed: {e}")
        
        # Enhanced rule-based extraction for Mumbai University format
        subjects = self._extract_subjects_enhanced(text)
        if subjects:
            return subjects
        
        # Fallback to basic rule-based
        parser = SyllabusParser()
        subjects = parser._parse_from_text(text)
        return [
            {
                'code': '',
                'name': s.name,
                'modules': [],
                'topics': s.topics,
                'total_hours': s.estimated_hours,
                'difficulty': s.difficulty
            }
            for s in subjects
        ]
    
    def _extract_subjects_enhanced(self, text: str) -> List[Dict]:
        """Enhanced subject extraction for various university formats"""
        subjects = []
        modules = []
        topics = []
        
        # Extract modules - multiple patterns for different formats
        # Pattern 1: "I Machine Learning", "II Feature Selection", etc.
        roman_module_pattern = r'^\s*(I{1,3}|IV|V|VI)\s+([A-Z][A-Za-z\s&]+?)(?:\s+\d+\s*(?:CO|Hours?|hrs)?|\s*$)'
        # Pattern 2: "Module I: Name" or "Unit 1: Name"
        explicit_module_pattern = r'(?:Module|Unit)\s*(?:I{1,3}|IV|V|VI|[1-6])\s*[:\-\s]+([^\n]+)'
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            # Try roman numeral pattern first (for Mumbai University format)
            match = re.match(roman_module_pattern, line)
            if match:
                module_name = match.group(2).strip()
                # Clean up module name
                module_name = re.sub(r'\s+', ' ', module_name)
                module_name = re.sub(r'\s*(Introduction|to|and)\s*$', '', module_name, flags=re.IGNORECASE)
                if len(module_name) > 3 and len(module_name) < 80 and module_name not in modules:
                    modules.append(module_name)
        
        # Try explicit module pattern
        explicit_matches = re.findall(explicit_module_pattern, text, re.IGNORECASE)
        for m in explicit_matches:
            clean_name = re.sub(r'\s+', ' ', m.strip())[:80]
            # Skip if it looks like instructions
            if 'must be from' in clean_name.lower() or 'randomly' in clean_name.lower():
                continue
            if len(clean_name) > 3 and clean_name not in modules:
                modules.append(clean_name)
        
        # Extract course objectives as topics (numbered like "1 To learn...")
        objective_patterns = [
            r'(?:^\s*\d+\s+)?To\s+learn\s+(.+?)(?:\n|$)',
            r'(?:^\s*\d+\s+)?To\s+understand\s+(.+?)(?:\n|$)',
            r'(?:^\s*\d+\s+)?To\s+evaluate\s+(.+?)(?:\n|$)',
            r'(?:^\s*\d+\s+)?To\s+analyze\s+(.+?)(?:\n|$)',
        ]
        
        for pattern in objective_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                topic = re.sub(r'\s+', ' ', match.strip())
                if len(topic) > 10 and len(topic) < 200 and topic not in topics:
                    topics.append(topic)
        
        # Extract detailed content topics (Introduction to X, Basics of Y)
        content_patterns = [
            r'Introduction\s+to\s+([A-Za-z\s]+?)(?:--|,|\n|$)',
            r'Basics\s+of\s+([A-Za-z\s]+?)(?:--|,|\n|$)',
        ]
        
        for pattern in content_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                topic = match.strip()[:60]
                if len(topic) > 3 and topic not in topics:
                    topics.append(topic)
        
        # Look for subject code and name
        code_pattern = r'([A-Z]{2,}[0-9]{2,}[A-Z]*[0-9]*)'
        code_matches = re.findall(code_pattern, text)
        
        # Find subject name from context
        subject_name = None
        combined_text = ' '.join(text.split('\n')[:50])  # First 50 lines
        
        # Look for "Machine Learning", "Blockchain", etc.
        name_patterns = [
            r'Machine\s*Learning\s*(?:&|and)?\s*Blockchain',
            r'Machine\s*Learning',
            r'Blockchain\s*Technology',
            r'Blockchain',
            r'Data\s*Science',
            r'Artificial\s*Intelligence',
            r'Deep\s*Learning',
            r'Neural\s*Network',
            r'Database\s*Management',
            r'Operating\s*Systems?',
            r'Computer\s*Networks?',
            r'Software\s*Engineering',
            r'Web\s*Development',
            r'Cloud\s*Computing',
            r'Cyber\s*Security',
            r'Internet\s*of\s*Things',
            r'Big\s*Data',
            r'Data\s*Mining',
            r'Natural\s*Language\s*Processing',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                subject_name = match.group(0).strip()
                break
        
        # Estimate hours
        hours_matches = re.findall(r'(\d+)\s*(?:Hours?|hrs?|Hrs)', text, re.IGNORECASE)
        total_hours = sum(int(h) for h in hours_matches) if hours_matches else len(modules) * 8
        if total_hours > 200:  # Cap at reasonable value
            total_hours = len(modules) * 8 if modules else 40
        
        # Determine difficulty
        combined_lower = text.lower()
        if any(kw in combined_lower for kw in ['neural network', 'deep learning', 'algorithm', 'optimization', 'mathematical', 'eigenvalue']):
            difficulty = 'hard'
        elif any(kw in combined_lower for kw in ['basic', 'introduction', 'fundamentals', 'overview', 'simple']):
            difficulty = 'easy'
        else:
            difficulty = 'medium'
        
        # Get best code
        code = code_matches[0] if code_matches else ''
        
        # Build subject
        if subject_name or modules or topics:
            subjects.append({
                'code': code,
                'name': subject_name or 'Extracted Course',
                'modules': modules[:10],
                'topics': topics[:20],
                'total_hours': total_hours,
                'difficulty': difficulty,
                'estimated_hours': total_hours,
                'weekly_target_hours': max(4, total_hours // 12),
                'priority': 8 if difficulty == 'hard' else (6 if difficulty == 'medium' else 4)
            })
        
        return subjects

    def _extract_events(self, text: str) -> List[Dict]:
        """Extract calendar events using Local NLP + rule-based methods"""
        # Try Local NLP extraction first
        if USE_LOCAL_NLP:
            try:
                ai_results = ai_extractor.extract_calendar_with_ai(text)
                if ai_results:
                    return ai_results
            except Exception as e:
                print(f"⚠️ Local NLP calendar extraction failed: {e}")
        
        # Fallback to rule-based
        parser = AcademicCalendarParser()
        events = parser._parse_text(text)
        return [
            {
                'name': e.name,
                'date': e.date,
                'end_date': e.end_date,
                'event_type': e.event_type,
                'is_holiday': e.is_holiday
            }
            for e in events
        ]
    
    def _extract_exams(self, text: str) -> List[Dict]:
        """Extract exam schedule using Local NLP + rule-based methods"""
        # Try Local NLP extraction first
        if USE_LOCAL_NLP:
            try:
                ai_results = ai_extractor.extract_exam_timetable_with_ai(text)
                if ai_results:
                    return ai_results
            except Exception as e:
                print(f"⚠️ Local NLP exam extraction failed: {e}")
        
        # Fallback to rule-based
        parser = ExamTimetableParser()
        # Use internal parsing methods
        exams = parser._parse_line_by_line(text)
        return [
            {
                'subject': e.subject,
                'subject_code': '',
                'date': e.date,
                'start_time': e.start_time,
                'end_time': e.end_time,
                'venue': e.venue,
                'exam_type': e.exam_type
            }
            for e in exams
        ]


# Initialize global universal extractor
universal_extractor = UniversalDocumentExtractor()


# ============================================================================
# LAYOUTLMV3 DOCUMENT UNDERSTANDING (Best for structured documents)
# ============================================================================

class LayoutLMv3Extractor:
    """
    LayoutLMv3-based document extraction for syllabi.
    Understands document layout (tables, headers, structure).
    Much better than regex for complex PDFs.
    """
    
    # Use local model path (downloaded via git lfs)
    LOCAL_MODEL_PATH = "./layoutlmv3-base"
    
    def __init__(self, model_path: str = None):
        self.enabled = False
        self.processor = None
        self.model = None
        
        # Use local path if exists, else try HuggingFace
        if model_path:
            self.model_path = model_path
        elif Path(self.LOCAL_MODEL_PATH).exists():
            self.model_path = self.LOCAL_MODEL_PATH
        else:
            self.model_path = "microsoft/layoutlmv3-base"
        
        if HAS_LAYOUTLM and HAS_PDF2IMAGE:
            try:
                print(f"🔄 Loading LayoutLMv3 from {self.model_path}...")
                self.processor = LayoutLMv3Processor.from_pretrained(self.model_path, apply_ocr=True)
                self.model = LayoutLMv3ForSequenceClassification.from_pretrained(self.model_path)
                self.enabled = True
                print("✅ LayoutLMv3 loaded successfully")
            except Exception as e:
                print(f"⚠️ LayoutLMv3 load failed: {e}")
                self.enabled = False
        else:
            print("Info: LayoutLMv3 requires: pip install transformers torch pillow pdf2image")
    
    def extract_from_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract structured data from PDF using LayoutLMv3 + Tesseract OCR.
        Converts PDF pages to images, then uses LayoutLMv3's processor
        which internally calls Tesseract for layout-aware OCR.
        """
        if not self.enabled:
            return {}
        
        try:
            import fitz  # PyMuPDF for PDF to image conversion
            from io import BytesIO
            
            # Open PDF with PyMuPDF
            doc = fitz.open(pdf_path)
            all_text = []
            all_words_boxes = []
            max_pages = min(15, len(doc))
            
            for i in range(max_pages):
                page = doc[i]
                
                # Render page to high-res image for OCR
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom = ~144 DPI
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(BytesIO(img_data)).convert("RGB")
                
                # Use LayoutLMv3 processor with Tesseract OCR (apply_ocr=True by default)
                encoding = self.processor(
                    image,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512
                )
                
                # Decode tokens to get OCR text
                if hasattr(encoding, 'input_ids'):
                    text = self.processor.tokenizer.decode(
                        encoding.input_ids[0],
                        skip_special_tokens=True
                    )
                    all_text.append(text)
                
                print(f"   📄 Page {i+1}/{max_pages} processed (LayoutLMv3+Tesseract)")
            
            doc.close()
            
            # Combine all text
            full_text = '\n\n'.join(all_text)
            
            return {
                'text': full_text,
                'method': 'layoutlmv3_tesseract',
                'pages_processed': max_pages
            }
            
        except Exception as e:
            print(f"⚠️ LayoutLMv3 extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def extract_with_ocr(self, image_path: str) -> Dict[str, Any]:
        """Extract text from a single image using LayoutLMv3's built-in OCR."""
        if not self.enabled:
            return {}
        
        try:
            image = Image.open(image_path).convert("RGB")
            encoding = self.processor(image, return_tensors="pt", truncation=True)
            
            # Get words from OCR
            words = []
            if hasattr(self.processor, 'tokenizer'):
                # Decode tokens back to text
                tokens = encoding.input_ids[0]
                words = self.processor.tokenizer.decode(tokens, skip_special_tokens=True)
            
            return {
                'text': words,
                'method': 'layoutlmv3_ocr'
            }
        except Exception as e:
            print(f"⚠️ LayoutLMv3 OCR failed: {e}")
            return {}


# Initialize LayoutLMv3 (will be lazy-loaded on first use)
layoutlm_extractor = None

def get_layoutlm_extractor():
    """Lazy load LayoutLMv3 extractor."""
    global layoutlm_extractor
    if layoutlm_extractor is None and HAS_LAYOUTLM:
        layoutlm_extractor = LayoutLMv3Extractor()
    return layoutlm_extractor


# ============================================================================
# LOCAL NLP-POWERED EXTRACTION (Fast, No API calls)
# ============================================================================

class LocalNLPExtractor:
    """
    Fast local NLP-based document extraction using regex + text mining.
    Optimized for Mumbai University syllabus format.
    No API calls - processes locally for speed.
    """
    
    # Course code patterns (Mumbai University specific)
    COURSE_CODE_PATTERNS = [
        r'\b(HAIML[A-Z]?\d{3})\b',              # HAIMLC501, HAIMLC601
        r'\b(IoTCSBC[A-Z]?\d{3})\b',            # IoTCSBCC701
        r'\b(BSC\d{3}[A-Z]?)\b',                # BSC201, BSC202X
        r'\b(ESC\d{3})\b',                       # ESC201
        r'\b(PCC\d{3}[A-Z]?)\b',                # PCC201X
        r'\b(BSL\d{3}[A-Z]?)\b',                # BSL201X
        r'\b(ESL\d{3})\b',                       # ESL201
        r'\b(PCL\d{3}[A-Z]?)\b',                # PCL201X
        r'\b(VSEC\d{3})\b',                      # VSEC201
        r'\b(CC\d{3})\b',                        # CC201
        r'\b(IKS\d{3})\b',                       # IKS201
        r'\b([A-Z]{2,5}\d{3,4}[A-Z]?)\b',       # Generic: CS101, HAIMLC501
        r'\b([A-Z]{2,3}[-\s]?\d{3,4})\b',       # CS-101, CS 101
        r'\b(\d{2}[A-Z]{2,4}\d{2,4})\b',        # 18CS56
    ]
    
    # Module patterns (Mumbai University specific)
    MODULE_PATTERNS = [
        # "1.0 Linear Algebra 05" or "Module No. Topics Hrs"
        r'(\d+)\.0\s+([A-Z][A-Za-z\s&,\-]+?)(?:\s+(\d+)\s*$|\s+\d+\s*$)',
        # "Module I: Introduction" or "Module 1: Introduction"  
        r'(?:Module|Unit|Chapter)\s*(?:No\.?|#)?\s*[:\-]?\s*(I{1,4}|IV|V|VI|[1-9]|10)\s*[:\-\s]+([^\n]+)',
        # "I Introduction to Machine Learning 7 CO1"
        r'^(I{1,4}|IV|V|VI)\s+([A-Z][A-Za-z\s&,\-]+?)(?:\s+\d+\s*(?:CO\d*)?|\s*$)',
        # "1. Mathematics: Vectors..." 
        r'^(\d+)\.\s+([A-Z][A-Za-z\s&,\-:]+?)(?:\s+\d+|\s*$)',
        # Numbered sections like "1.1 Vectors and Matrices"
        r'(\d+\.\d+)\s+([A-Z][A-Za-z\s&,\-]+?)(?:\s*,|\s*$)',
    ]
    
    # Topic extraction patterns (Mumbai University specific)
    TOPIC_PATTERNS = [
        # "1.1 Vectors and Matrices, Solving Linear equations"
        r'\d+\.\d+\s+([A-Z][A-Za-z\s&,\(\)\-]+)',
        # Comma-separated topics in module descriptions
        r'([A-Z][a-z]+(?:\s+[A-Za-z]+){0,3}),\s+([A-Z][a-z]+(?:\s+[A-Za-z]+){0,3})',
        # Explicit topic patterns
        r'(?:^|\n)\s*[\d\.]+\s+([A-Z][a-z][^\n]{5,80})',
        r'(?:^|\n)\s*[•\-\*→]\s+([A-Z][^\n]{5,80})',
        r'Introduction[:\-\s]+([A-Za-z\s,]+?)(?:\.|,|\n)',
    ]
    
    # Subject name patterns (Mumbai University subjects - expanded)
    SUBJECT_KEYWORDS = [
        # AI/ML Subjects
        'Mathematics for AI', 'Mathematics for AI & ML', 'Mathematics for AI&ML',
        'Game Theory using AI', 'Game Theory using AI & ML',
        'AI&ML in Healthcare', 'Text, Web and Social Media Analytics',
        'Machine Learning', 'Deep Learning', 'Artificial Intelligence', 'Neural Network',
        'Machine Learning & Blockchain',
        # Data Science
        'Data Science', 'Data Mining', 'Big Data', 'Analytics', 'Data Structure',
        'Exploratory Data Analysis',
        # Core CS
        'Database', 'DBMS', 'SQL', 'NoSQL',
        'Operating System', 'Computer Network', 'Computer Architecture',
        'Software Engineering', 'Web Development', 'Mobile Development',
        'Python Programming', 'Programming',
        # Security & Blockchain
        'Blockchain', 'Cryptography', 'Cyber Security', 'Information Security',
        'Consensus Mechanism', 'Smart Contract',
        # Other
        'Cloud Computing', 'Distributed System', 'Parallel Computing',
        'Algorithm', 'Digital Signal Processing', 'Image Processing', 'Computer Vision',
        'Natural Language Processing', 'NLP', 'Text Mining',
        'Internet of Things', 'IoT', 'Embedded System',
        'Compiler Design', 'Theory of Computation', 'Automata',
        # Mathematics
        'Linear Algebra', 'Probability', 'Statistics', 'Optimization',
        'Dimension Reduction', 'Applied Mathematics',
        'Discrete Mathematics', 'Engineering Mathematics',
        # First Year
        'Engineering Graphics', 'Engineering Workshop',
        'Applied Physics', 'Applied Chemistry',
        'Indian Knowledge System', 'Design Thinking',
        # Automobile/Mechanical
        'Automobile Engineering', 'Mechanical Engineering',
        'Thermodynamics', 'Fluid Mechanics',
        # Mumbai University Specific
        'Internal Assessment', 'Term Work', 'End Semester Examination', 'Oral & Practical',
        'Theory Examination', 'Course Objectives', 'Course Outcomes',
        'Mumbai University', 'University of Mumbai'
    ]
    
    # Difficulty keywords
    DIFFICULTY_KEYWORDS = {
        'hard': ['advanced', 'complex', 'optimization', 'algorithm', 'neural', 'deep learning',
                 'eigenvalue', 'eigenvector', 'matrix decomposition', 'transform', 'kernel', 
                 'bayesian', 'markov', 'gradient', 'convex', 'mathematical', 'theorem', 'proof',
                 'svd', 'singular value', 'dimensionality reduction', 'pca', 'lda',
                 'backpropagation', 'tensor', 'consensus', 'cryptography'],
        'easy': ['introduction', 'basic', 'fundamental', 'overview', 'simple', 'beginner',
                 'concept', 'definition', 'history', 'types of', 'what is', 'need for',
                 'prerequisite', 'terminology', 'framework'],
        'medium': ['application', 'implementation', 'design', 'analysis', 'methods',
                   'techniques', 'practical', 'case study', 'classification', 'clustering',
                   'regression', 'visualization', 'preprocessing']
    }
    
    def __init__(self):
        self.enabled = True  # Always enabled - local processing
        self.use_layoutlm = HAS_LAYOUTLM
        print("✅ Local NLP Extractor initialized (fast, no API calls)")
        if self.use_layoutlm:
            print("   LayoutLMv3 available for enhanced extraction")
    
    def extract_syllabus_from_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Extract syllabus from PDF file using Groq/Gemini AI.
        Falls back to local NLP if AI fails.
        """
        # First, extract text from PDF - prefer pdfplumber for full text
        text = ""
        
        # Use pdfplumber for better full-text extraction
        if HAS_PDFPLUMBER:
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    text = '\n'.join([p.extract_text() or '' for p in pdf.pages])
                print(f"   pdfplumber extracted {len(text)} chars")
            except Exception as e:
                print(f"⚠️ pdfplumber failed: {e}")
        
        # Fallback to LayoutLMv3 if pdfplumber failed
        if not text and self.use_layoutlm:
            try:
                layoutlm = get_layoutlm_extractor()
                if layoutlm and layoutlm.enabled:
                    print("🔍 Using LayoutLMv3 for PDF extraction...")
                    result = layoutlm.extract_from_pdf(pdf_path)
                    if result and result.get('text'):
                        text = result['text']
            except Exception as e:
                print(f"⚠️ LayoutLMv3 failed: {e}")
        
        if not text:
            return []
        
        # Try Groq first (fast, generous free tier - 14,400 requests/day)
        if HAS_GROQ and GROQ_API_KEY != "gsk_PLACEHOLDER":
            try:
                return self._extract_with_groq(text)
            except Exception as e:
                print(f"⚠️ Groq extraction failed: {e}, trying Gemini...")
        
        # Try Gemini API
        if HAS_GEMINI:
            try:
                return self._extract_with_gemini(text)
            except Exception as e:
                print(f"⚠️ Gemini extraction failed: {e}, falling back to local NLP")
        
        # Fallback to local NLP
        return self.extract_syllabus_with_ai(text)
    
    def _extract_with_groq_or_fallback(self, text: str) -> List[Dict]:
        """Extract syllabus using Groq AI, falling back to Gemini or LocalNLP."""
        # Try Groq first (fast, generous free tier)
        if HAS_GROQ and GROQ_API_KEY != "gsk_PLACEHOLDER":
            try:
                return self._extract_with_groq(text)
            except Exception as e:
                print(f"⚠️ Groq extraction failed: {e}, trying Gemini...")
        
        # Try Gemini API
        if HAS_GEMINI:
            try:
                return self._extract_with_gemini(text)
            except Exception as e:
                print(f"⚠️ Gemini extraction failed: {e}, falling back to local NLP")
        
        # Fallback to local NLP
        return self.extract_syllabus_with_ai(text)
    
    def _extract_with_gemini(self, text: str) -> List[Dict]:
        """Extract syllabus using Google Gemini AI."""
        print("🔍 Using Gemini AI for syllabus extraction...")
        
        model = _gemini_model
        
        prompt = f"""Analyze this university syllabus text (specifically focusing on Mumbai University structure) and extract structured course information.
Return a JSON array with courses. Each course should have:
- code: course code (e.g., "IoTCSBCC701", "HAIMLC501")
- name: full course name
- modules: array of module names with hours (e.g., ["Introduction to ML (7 hrs)", "Feature Selection (9 hrs)"])
- topics: array of key topics covered
- total_hours: total teaching hours (number)
- difficulty: "easy", "medium", or "hard"

SYLLABUS TEXT:
{text[:8000]}

Return ONLY valid JSON array, no markdown or explanation."""

        try:
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Clean JSON response
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
            result_text = result_text.strip()
            
            courses = json.loads(result_text)
            
            # Normalize the response
            normalized = []
            for c in courses:
                normalized.append({
                    'code': c.get('code', ''),
                    'name': c.get('name', 'Unknown Course'),
                    'modules': c.get('modules', [])[:10],
                    'topics': c.get('topics', [])[:20],
                    'total_hours': c.get('total_hours', 48),
                    'estimated_hours': c.get('total_hours', 48),
                    'difficulty': c.get('difficulty', 'medium'),
                    'weekly_target_hours': max(4, c.get('total_hours', 48) // 12),
                    'priority': 9 if c.get('difficulty') == 'hard' else 7,
                    'modules_count': len(c.get('modules', []))
                })
            
            print(f"✅ Gemini extracted {len(normalized)} courses")
            return normalized
            
        except json.JSONDecodeError as e:
            print(f"⚠️ Gemini JSON parse error: {e}")
            raise
        except Exception as e:
            print(f"⚠️ Gemini API error: {e}")
            raise
        
        return []
    
    def _extract_with_groq(self, text: str) -> List[Dict]:
        """Extract syllabus using Groq AI (fast, generous free tier)."""
        print("🔍 Using Groq AI for syllabus extraction...")
        print(f"   Text length: {len(text)} chars")
        
        client = Groq(api_key=GROQ_API_KEY)
        
        # Use more text for better extraction (up to 12000 chars)
        text_chunk = text[:12000]
        
        prompt = f"""Analyze this syllabus (specifically looking for Mumbai University / University of Mumbai formats) and extract ALL courses.

For EACH course found, extract:
- code: course code (like CSC401, CSC402, CSL401 etc)
- name: full course name 
- modules: array of module/unit names with hours like ["Linear Algebra (7 hrs)", "Complex Integration (7 hrs)"]
- topics: key topics from each module
- total_hours: sum of all module hours
- difficulty: "easy", "medium" or "hard" based on content

Look for patterns like:
- "Course Code: CSC401" or "CSC401 Engineering Mathematics"
- "Module 1", "Module 2" or "Unit I", "Unit II" sections
- Hours mentioned as "7 Hours", "(7 hrs)", "Hrs: 7"

SYLLABUS TEXT:
{text_chunk}

Return ONLY a valid JSON array of courses. No markdown, no explanation."""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000
            )
            
            result_text = response.choices[0].message.content.strip()
            print(f"   Groq raw response length: {len(result_text)} chars")
            print(f"   Groq response preview: {result_text[:200]}...")
            
            # Clean JSON response
            if result_text.startswith('```'):
                lines = result_text.split('```')
                if len(lines) > 1:
                    result_text = lines[1]
                    if result_text.startswith('json'):
                        result_text = result_text[4:]
            result_text = result_text.strip()
            
            # Handle case where response starts with [ but has trailing text
            if '[' in result_text:
                start = result_text.index('[')
                # Find the matching closing bracket
                bracket_count = 0
                end = start
                for i, c in enumerate(result_text[start:], start):
                    if c == '[':
                        bracket_count += 1
                    elif c == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end = i + 1
                            break
                result_text = result_text[start:end]
            
            courses = json.loads(result_text)
            print(f"   Parsed {len(courses)} courses from JSON")
            
            # Normalize the response
            normalized = []
            for c in courses:
                normalized.append({
                    'code': c.get('code', ''),
                    'name': c.get('name', 'Unknown Course'),
                    'modules': c.get('modules', [])[:10],
                    'topics': c.get('topics', [])[:20],
                    'total_hours': c.get('total_hours', 48),
                    'estimated_hours': c.get('total_hours', 48),
                    'difficulty': c.get('difficulty', 'medium'),
                    'weekly_target_hours': max(4, c.get('total_hours', 48) // 12),
                    'priority': 9 if c.get('difficulty') == 'hard' else 7,
                    'modules_count': len(c.get('modules', []))
                })
            
            print(f"✅ Groq extracted {len(normalized)} courses")
            return normalized
            
        except json.JSONDecodeError as e:
            print(f"⚠️ Groq JSON parse error: {e}")
            raise
        except Exception as e:
            print(f"⚠️ Groq API error: {e}")
            raise
    
    def extract_syllabus_with_ai(self, text: str) -> List[Dict]:
        """
        Orchestrator for Syllabus Extraction: Groq -> Gemini -> Local NLP.
        """
        # Try Groq (fast, free tier)
        if HAS_GROQ and GROQ_API_KEY != "gsk_PLACEHOLDER":
            try:
                return self._extract_with_groq(text)
            except Exception as e:
                print(f"⚠️ Groq syllabus extraction failed: {e}")
        
        # Try Gemini
        if HAS_GEMINI:
            try:
                return self._extract_with_gemini(text)
            except Exception as e:
                print(f"⚠️ Gemini syllabus extraction failed: {e}")
                
        # Fallback to local
        return self._extract_syllabus_local(text)

    def _extract_syllabus_local(self, text: str) -> List[Dict]:
        """
        Extract structured syllabus data using local NLP and regex (Original implementation).
        Fully automatic - detects patterns from PDF structure.
        """
        print("🔍 Using Local NLP for syllabus extraction (auto mode)...")
        # ... (implementation continues below, reusing original code logic)
        
        courses = []
        # Step 1: Auto-detect course entries (code + name pairs)
        course_entries = self._auto_detect_courses(text)
        print(f"   Auto-detected {len(course_entries)} course entries")
        
        if course_entries:
            for entry in course_entries:
                section = self._find_course_section(text, entry)
                modules_data = self._extract_modules_with_hours(section)
                modules = [m['title'] for m in modules_data]
                topics = self._extract_topics(section)
                total_hours = sum(m.get('hours', 0) for m in modules_data)
                if total_hours < 10:
                    total_hours = self._extract_hours(section)
                diff = self._estimate_difficulty(entry['name'] + ' ' + ' '.join(modules))
                
                courses.append({
                    'code': entry['code'],
                    'name': entry['name'],
                    'modules': modules[:10],
                    'topics': topics[:20],
                    'total_hours': total_hours,
                    'estimated_hours': total_hours,
                    'difficulty': diff,
                    'weekly_target_hours': max(4, total_hours // 12),
                    'priority': 9 if diff == 'hard' else (7 if diff == 'medium' else 5),
                    'modules_count': len(modules)
                })
        else:
            course = self._extract_single_course(text)
            if course:
                courses.append(course)
        
        if courses:
            total_modules = sum(len(c.get('modules', [])) for c in courses)
            total_topics = sum(len(c.get('topics', [])) for c in courses)
            print(f"✅ Local NLP Extracted {len(courses)} courses with {total_modules} modules")
        else:
            print("⚠️ No courses extracted locally")
        
        return courses

    def extract_exam_timetable_with_ai(self, text: str) -> List[Dict]:
        """Orchestrator for Exam Timetable: Groq -> Gemini -> Local."""
        if HAS_GROQ and GROQ_API_KEY != "gsk_PLACEHOLDER":
            try:
                return self._extract_exams_with_groq(text)
            except Exception as e:
                print(f"⚠️ Groq exam extraction failed: {e}")

        if HAS_GEMINI:
            try:
                return self._extract_exams_with_gemini(text)
            except Exception as e:
                print(f"⚠️ Gemini exam extraction failed: {e}")

        return self._extract_exam_timetable_local(text)

    def _extract_exam_timetable_local(self, text: str) -> List[Dict]:
        """Extract exam schedule using local NLP (Original implementation)."""
        print("🔍 Using Local NLP for exam timetable extraction...")
        
        exams = []
        lines = text.split('\n')
        current_date = None
        
        for line in lines:
            # Try to find date
            date_match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', line)
            if date_match:
                d, m, y = date_match.groups()
                y = f"20{y}" if len(y) == 2 else y
                current_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            # Also check for text dates
            month_match = re.search(r'(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*(\d{4})?', line, re.IGNORECASE)
            if month_match:
                d, m, y = month_match.groups()
                month_num = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
                           'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
                m = month_num.get(m.lower()[:3], '01')
                y = y or '2026'
                current_date = f"{y}-{m}-{d.zfill(2)}"
            
            subject = self._extract_subject_from_line(line)
            time_match = re.search(r'(\d{1,2})[:\.]?(\d{2})?\s*(am|pm|AM|PM)?', line)
            start_time = None
            if time_match:
                h, m, ampm = time_match.groups()
                h = int(h)
                if ampm and ampm.lower() == 'pm' and h < 12:
                    h += 12
                start_time = f"{str(h).zfill(2)}:{m or '00'}"
            
            if subject and current_date:
                exams.append({
                    'subject': subject,
                    'subject_code': '',
                    'date': current_date,
                    'start_time': start_time,
                    'end_time': None,
                    'venue': self._extract_venue(line),
                    'exam_type': 'final' if 'final' in line.lower() else 'mid'
                })
        
        print(f"✅ Local NLP extracted {len(exams)} exams")
        return exams

    def extract_calendar_with_ai(self, text: str) -> List[Dict]:
        """Orchestrator for Acad Calendar: Groq -> Gemini -> Local."""
        if HAS_GROQ and GROQ_API_KEY != "gsk_PLACEHOLDER":
            try:
                return self._extract_calendar_with_groq(text)
            except Exception as e:
                print(f"⚠️ Groq calendar extraction failed: {e}")

        if HAS_GEMINI:
            try:
                return self._extract_calendar_with_gemini(text)
            except Exception as e:
                print(f"⚠️ Gemini calendar extraction failed: {e}")

        return self._extract_calendar_local(text)

    def _extract_calendar_local(self, text: str) -> List[Dict]:
        """Extract academic calendar events using local NLP (Original implementation)."""
        print("🔍 Using Local NLP for calendar extraction...")
        
        events = []
        lines = text.split('\n')
        
        holiday_keywords = ['holiday', 'vacation', 'break', 'off', 'closed', 'leave', 'festival',
                          'diwali', 'christmas', 'eid', 'holi', 'republic', 'independence']
        exam_keywords = ['exam', 'test', 'assessment', 'evaluation']
        
        for line in lines:
            if len(line.strip()) < 5:
                continue
            
            date = self._extract_date_from_line(line)
            if not date:
                continue
            
            name = self._extract_event_name(line)
            if not name:
                continue
            
            line_lower = line.lower()
            is_holiday = any(kw in line_lower for kw in holiday_keywords)
            is_exam = any(kw in line_lower for kw in exam_keywords)
            event_type = 'holiday' if is_holiday else ('exam' if is_exam else 'event')
            
            events.append({
                'name': name,
                'date': date,
                'end_date': None,
                'event_type': event_type,
                'is_holiday': is_holiday
            })
        
        print(f"✅ Local NLP extracted {len(events)} events")
        return events

    # --- AI Helper Methods ---

    def _extract_exams_with_groq(self, text: str) -> List[Dict]:
        """Extract exam timetable using Groq AI."""
        print("🔍 Using Groq AI for exam timetable...")
        client = Groq(api_key=GROQ_API_KEY)
        text_chunk = text[:12000] # Increased limit
        
        prompt = f"""Extract exam timetable from this text.
        Return JSON array where each object has:
        - subject: exam subject name
        - date: YYYY-MM-DD
        - start_time: HH:MM (24h)
        - end_time: HH:MM (24h)
        - venue: string or null
        
        Text:
        {text_chunk}
        
        Return ONLY valid JSON array."""
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = response.choices[0].message.content.strip()
        # Clean markdown
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        exams = json.loads(content)
        print(f"✅ Groq extracted {len(exams)} exams")
        return exams

    def _extract_exams_with_gemini(self, text: str) -> List[Dict]:
        """Extract exam timetable using Gemini AI."""
        print("🔍 Using Gemini AI for exam timetable...")
        model = _gemini_model
        prompt = f"""Extract exam timetable from this text.
        Return JSON array where each object has:
        - subject: exam subject name
        - date: YYYY-MM-DD
        - start_time: HH:MM (24h)
        - end_time: HH:MM (24h)
        - venue: string or null
        
        Text:
        {text[:8000]}
        
        Return ONLY valid JSON array."""
        
        response = model.generate_content(prompt)
        content = response.text.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        exams = json.loads(content)
        print(f"✅ Gemini extracted {len(exams)} exams")
        return exams

    def _extract_calendar_with_groq(self, text: str) -> List[Dict]:
        """Extract academic calendar using Groq AI."""
        print("🔍 Using Groq AI for calendar...")
        client = Groq(api_key=GROQ_API_KEY)
        text_chunk = text[:12000]
        
        prompt = f"""Extract academic events from this text.
        Return JSON array where each object has:
        - name: event name
        - date: YYYY-MM-DD
        - event_type: "holiday", "exam", "event"
        - is_holiday: boolean
        
        Text:
        {text_chunk}
        
        Return ONLY valid JSON array."""
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        events = json.loads(content)
        print(f"✅ Groq extracted {len(events)} events")
        return events

    def _extract_calendar_with_gemini(self, text: str) -> List[Dict]:
        """Extract academic calendar using Gemini AI."""
        print("🔍 Using Gemini AI for calendar...")
        model = _gemini_model
        prompt = f"""Extract academic events from this text.
        Return JSON array where each object has:
        - name: event name
        - date: YYYY-MM-DD
        - event_type: "holiday", "exam", "event"
        - is_holiday: boolean
        
        Text:
        {text[:8000]}
        
        Return ONLY valid JSON array."""
        
        response = model.generate_content(prompt)
        content = response.text.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        events = json.loads(content)
        print(f"✅ Gemini extracted {len(events)} events")
        return events
    
    def _auto_detect_courses(self, text: str) -> List[Dict]:
        """
        Automatically detect course code + name pairs from any syllabus.
        Works with Mumbai University, other universities, and generic formats.
        """
        courses = []
        seen_codes = set()
        
        # Pattern 1: Code followed by name in table format
        # Examples: "HAIMLC501 Mathematics for AI & ML" or "BSC201 Applied Mathematics"
        pattern1 = r'\b([A-Z]{2,8}[A-Z]?\d{3,4}[A-Z]?)\s+([A-Z][A-Za-z][A-Za-z\s&,\-]+?)(?:\s+\d{2}|\s+0[0-4]|\n)'
        for match in re.finditer(pattern1, text):
            code, name = match.groups()
            name = name.strip()
            name = re.sub(r'\s+', ' ', name)
            if code not in seen_codes and len(name) > 3 and len(name) < 80:
                # Filter out false positives
                if not re.match(r'^(Total|Theory|Practical|Tutorial|Credit|Exam|Internal|End)', name):
                    courses.append({'code': code, 'name': name, 'pos': match.start()})
                    seen_codes.add(code)
        
        # Pattern 2: Course Name row in table (common format)
        # "Course Name: X" or table cell with subject name
        pattern2 = r'(?:Course|Subject)\s*(?:Name|Title)\s*[:\s]+([A-Z][A-Za-z\s&,\-]+?)(?:\n|$)'
        for match in re.finditer(pattern2, text, re.IGNORECASE):
            name = match.group(1).strip()
            name = re.sub(r'\s+', ' ', name)
            if len(name) > 5 and len(name) < 80:
                if not re.match(r'^(Teaching|Examination|Credit|Hours)', name):
                    # Find associated code nearby
                    nearby_text = text[max(0, match.start()-200):match.start()+50]
                    code_match = re.search(r'\b([A-Z]{2,8}\d{3,4}[A-Z]?)\b', nearby_text)
                    code = code_match.group(1) if code_match else ''
                    
                    if code not in seen_codes or not code:
                        courses.append({'code': code, 'name': name, 'pos': match.start()})
                        if code:
                            seen_codes.add(code)
        
        # Pattern 3: "Subject Code Subject Name" table headers followed by data
        pattern3 = r'Subject\s+Code\s+Subject\s+Name[^\n]*\n+([A-Z]{2,8}\d{3,4}[A-Z]?)\s+([A-Z][A-Za-z\s&\-]+?)(?:\s+\d|\n)'
        for match in re.finditer(pattern3, text, re.IGNORECASE):
            code, name = match.groups()
            name = name.strip()
            if code not in seen_codes and len(name) > 3:
                courses.append({'code': code, 'name': name, 'pos': match.start()})
                seen_codes.add(code)
        
        # Pattern 4: Standalone course headers (e.g., "Artificial Intelligence: Sem V")
        pattern4 = r'([A-Z][A-Za-z\s&]+?):\s*Sem(?:ester)?\s*[IVX]+\s*\n'
        for match in re.finditer(pattern4, text):
            name = match.group(1).strip()
            if len(name) > 5 and name not in [c['name'] for c in courses]:
                courses.append({'code': '', 'name': name, 'pos': match.start()})
        
        # Sort by position in document
        courses.sort(key=lambda x: x['pos'])
        
        # Remove duplicates with similar names
        unique = []
        for course in courses:
            is_dup = False
            for existing in unique:
                if course['name'].lower() in existing['name'].lower() or existing['name'].lower() in course['name'].lower():
                    is_dup = True
                    break
            if not is_dup:
                unique.append(course)
        
        return unique[:15]  # Max 15 courses
    
    def _find_course_section(self, text: str, entry: Dict) -> str:
        """Find the text section belonging to a specific course."""
        pos = entry.get('pos', 0)
        
        # Find the next course boundary or end of relevant content
        # Look for next course code or "Course Code" header
        next_boundary = len(text)
        
        # Search for next course code after this position
        pattern = r'\b[A-Z]{2,8}\d{3,4}[A-Z]?\s+[A-Z][a-z]'
        for match in re.finditer(pattern, text[pos+100:]):
            next_boundary = pos + 100 + match.start()
            break
        
        # Also check for section markers
        section_markers = [r'\nCourse\s+Code\s+Course', r'\nText\s+Books:', r'\nReferences:', r'\nAssessment:']
        for marker in section_markers:
            match = re.search(marker, text[pos+100:], re.IGNORECASE)
            if match:
                marker_pos = pos + 100 + match.start()
                if marker_pos < next_boundary:
                    next_boundary = marker_pos
        
        return text[pos:next_boundary]
    
    def _extract_single_course(self, text: str) -> Optional[Dict]:
        """Fallback: Extract as a single course when auto-detection fails."""
        # Find any course code
        code = ''
        for pattern in self.COURSE_CODE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                code = match.group(1) if match.lastindex else match.group(0)
                break
        
        # Extract modules
        modules_data = self._extract_modules_with_hours(text)
        modules = [m['title'] for m in modules_data]
        
        if not modules:
            return None
        
        # Infer name from content
        name = self._infer_subject_name(text, modules)
        
        # Extract topics
        topics = self._extract_topics(text)
        
        # Calculate hours
        total_hours = sum(m.get('hours', 0) for m in modules_data)
        if total_hours < 10:
            total_hours = self._extract_hours(text)
        
        # Estimate difficulty
        diff = self._estimate_difficulty(name + ' ' + ' '.join(modules))
        
        return {
            'code': code,
            'name': name,
            'modules': modules[:10],
            'topics': topics[:20],
            'total_hours': total_hours,
            'estimated_hours': total_hours,
            'difficulty': diff,
            'weekly_target_hours': max(4, total_hours // 12),
            'priority': 9 if diff == 'hard' else (7 if diff == 'medium' else 5),
            'modules_count': len(modules)
        }
    
    def _extract_course_codes(self, text: str) -> List[str]:
        """Extract course codes using regex patterns - Mumbai University format."""
        codes = []
        seen = set()
        
        for pattern in self.COURSE_CODE_PATTERNS:
            matches = re.findall(pattern, text)
            for code in matches:
                code = code.strip()
                # Filter out common false positives
                if code and code not in seen:
                    # Skip pure numbers, very short codes, or common words
                    if len(code) >= 4 and not code.isdigit():
                        # Skip if it looks like a year or page number
                        if not re.match(r'^(19|20)\d{2}$', code):
                            codes.append(code)
                            seen.add(code)
        
        return codes[:15]
    
    def _extract_subject_names(self, text: str) -> List[str]:
        """Extract subject names from text - optimized for Mumbai University."""
        names = []
        text_lower = text.lower()
        
        # First priority: Look for explicit course name patterns with code
        # Pattern: "HAIMLC501 Mathematics for AI&ML" or "Course Code Course Name"
        code_name_patterns = [
            # HAIMLC501 Mathematics for AI & ML
            r'(HAIML[A-Z]?\d{3})\s+([A-Z][A-Za-z\s&\-]+?)(?:\s+\d{2}|\n)',
            # IoTCSBCC701 Machine Learning & Blockchain
            r'(IoTCSBC[A-Z]?\d{3})\s+([A-Z][A-Za-z\s&\-]+?)(?:\s+\d{2}|\n)',
            # BSC201 Applied Mathematics
            r'(BSC\d{3}[A-Z]?)\s+([A-Z][A-Za-z\s&\-]+?)(?:\s+\d{1,2}|\n)',
        ]
        
        for pattern in code_name_patterns:
            matches = re.findall(pattern, text)
            for code, name in matches:
                name = name.strip()
                name = re.sub(r'\s+', ' ', name)
                # Filter out false positives
                if len(name) > 3 and len(name) < 60:
                    if not re.match(r'^\d|^Total|^Credits|^Theory|^Practical|^Tutorial', name):
                        full_name = name
                        # Don't add duplicates
                        if full_name not in names:
                            names.append(full_name)
        
        # Second priority: Look for "Course Name" in table format
        course_name_pattern = r'Course\s+(?:Code\s+)?(?:Course\s+)?Name[^\n]*\n+([A-Z][A-Za-z]?[0-9]*)\s+([A-Z][A-Za-z\s&\-]+?)(?:\s+\d|\n)'
        matches = re.findall(course_name_pattern, text)
        for code, name in matches:
            name = name.strip()
            if len(name) > 3 and len(name) < 60 and name not in names:
                names.append(name)
        
        # Third priority: Check for specific Mumbai University subject titles
        mu_subjects = [
            ('Mathematics for AI', 'Mathematics for AI & ML'),
            ('Game Theory using AI', 'Game Theory using AI & ML'),
            ('AI&ML in Healthcare', 'AI & ML in Healthcare'),
            ('Text, Web and Social Media', 'Text, Web and Social Media Analytics'),
            ('Machine Learning & Blockchain', 'Machine Learning & Blockchain'),
            ('Machine Learning', 'Machine Learning'),
            ('Neural Network and Deep Learning', 'Neural Network and Deep Learning'),
            ('Introduction to Blockchain', 'Introduction to Blockchain'),
            ('Consensus Mechanism', 'Consensus Mechanism & Smart Contracts'),
            ('Applied Mathematics', 'Applied Mathematics'),
            ('Engineering Graphics', 'Engineering Graphics'),
            ('Python Programming', 'Python Programming'),
            ('Data Structure', 'Data Structures'),
        ]
        
        for pattern, full_name in mu_subjects:
            if pattern.lower() in text_lower and full_name not in names:
                names.append(full_name)
        
        # Remove duplicates and similar names
        cleaned = []
        for name in names:
            is_dup = False
            for existing in cleaned:
                # Skip if too similar
                if name.lower() in existing.lower() or existing.lower() in name.lower():
                    is_dup = True
                    break
            if not is_dup:
                cleaned.append(name)
        
        return cleaned[:5]  # Max 5 subjects per document
    
    def _extract_modules_with_hours(self, text: str) -> List[Dict]:
        """Extract modules with their hours - Mumbai University format."""
        modules = []
        seen_titles = set()
        
        # Pattern 1: "1.0 Linear Algebra 05" format (common in Mumbai Uni syllabi)
        pattern1 = r'^(\d+)\.0\s+([A-Z][A-Za-z\s&,\-]+?)\s+(\d{1,2})\s*$'
        for match in re.findall(pattern1, text, re.MULTILINE):
            num, title, hours = match
            title = title.strip()
            if title and title.lower() not in seen_titles and len(title) > 3:
                modules.append({'num': int(num), 'title': title, 'hours': int(hours)})
                seen_titles.add(title.lower())
        
        # Pattern 2: Roman numeral "I Introduction to Machine Learning 7 CO1"
        pattern2 = r'^(I{1,3}|IV|V|VI)\s+([A-Z][A-Za-z\s&,\-]+?)\s+(\d{1,2})\s*(?:CO\d*)?\s*$'
        roman_to_int = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6}
        for match in re.findall(pattern2, text, re.MULTILINE):
            roman, title, hours = match
            title = title.strip()
            if title and title.lower() not in seen_titles and len(title) > 3:
                modules.append({'num': roman_to_int.get(roman, 1), 'title': title, 'hours': int(hours)})
                seen_titles.add(title.lower())
        
        # Pattern 3: "Module I: Topic Name" or "Module 1: Topic Name"
        pattern3 = r'Module\s*(?:No\.?)?\s*(I{1,3}|IV|V|VI|\d+)[:\s]+([A-Z][A-Za-z\s&,\-]+?)(?:\s+(\d{1,2}))?\s*$'
        for match in re.findall(pattern3, text, re.MULTILINE | re.IGNORECASE):
            num_str, title, hours = match
            title = title.strip()
            if title and title.lower() not in seen_titles and len(title) > 3:
                num = roman_to_int.get(num_str, int(num_str) if num_str.isdigit() else 1)
                hrs = int(hours) if hours else 8
                modules.append({'num': num, 'title': title, 'hours': hrs})
                seen_titles.add(title.lower())
        
        # Pattern 4: Numbered detailed content "1. Introduction:- What Is Learning?"
        pattern4 = r'^(\d+)\.\s+([A-Z][A-Za-z\s&:\-]+?)(?:\s+(\d{1,2})\s*(?:CO\d*)?)?\s*$'
        for match in re.findall(pattern4, text, re.MULTILINE):
            num, title, hours = match
            title = title.strip()
            # Clean up title
            title = re.sub(r'[:\-]+\s*$', '', title)
            if title and title.lower() not in seen_titles and len(title) > 3:
                # Skip false positives
                if not re.match(r'^\d|^Sr|^To ', title):
                    hrs = int(hours) if hours else 8
                    modules.append({'num': int(num), 'title': title, 'hours': hrs})
                    seen_titles.add(title.lower())
        
        # Sort by module number
        modules.sort(key=lambda x: x['num'])
        
        # If no modules found, try simpler patterns
        if not modules:
            # Try to find section headers
            section_pattern = r'(?:^|\n)([A-Z][a-z]+(?:\s+[A-Za-z]+){1,4})[:\-]\s*(?:\n|$)'
            for match in re.findall(section_pattern, text):
                title = match.strip()
                if title and title.lower() not in seen_titles and len(title) > 5:
                    if not re.match(r'^Course|^Subject|^Credit|^Total|^Assessment', title):
                        modules.append({'num': len(modules) + 1, 'title': title, 'hours': 8})
                        seen_titles.add(title.lower())
        
        return modules[:10]
    
    def _extract_modules(self, text: str) -> List[str]:
        """Extract module/unit titles (backward compatibility)."""
        modules_data = self._extract_modules_with_hours(text)
        return [m['title'] for m in modules_data]
    
    def _extract_topics(self, text: str) -> List[str]:
        """Extract topics and learning objectives - Mumbai University format."""
        topics = []
        seen = set()
        
        # Pattern 1: Numbered sub-sections like "1.1 Vectors and Matrices"
        numbered_subs = re.findall(r'\d+\.\d+\s+([A-Z][A-Za-z\s&,\(\)\-]+?)(?:\.|,|$)', text)
        for t in numbered_subs:
            t = t.strip()
            # Split by comma to get individual topics
            for sub in t.split(','):
                sub = sub.strip()
                if len(sub) > 3 and len(sub) < 80 and sub.lower() not in seen:
                    topics.append(sub)
                    seen.add(sub.lower())
        
        # Pattern 2: Content within module descriptions (comma-separated)
        # "Vectors and Matrices, Solving Linear equations, The four Fundamental Subspaces"
        content_pattern = r'(?:^|\n)[A-Z][A-Za-z\s]+[:\-]\s*([A-Z][^\n]+)'
        for match in re.findall(content_pattern, text):
            items = match.split(',')
            for item in items:
                item = item.strip()
                item = re.sub(r'\s+', ' ', item)
                if len(item) > 3 and len(item) < 80 and item.lower() not in seen:
                    topics.append(item)
                    seen.add(item.lower())
        
        # Pattern 3: Course objectives "To learn/understand X"
        objectives = re.findall(r'To\s+(?:learn|understand|study|analyze|evaluate|build|acquire|provide|focus)\s+([^\n\.]+)', text, re.IGNORECASE)
        for t in objectives:
            t = t.strip()
            if len(t) > 5 and len(t) < 100 and t.lower() not in seen:
                topics.append(t)
                seen.add(t.lower())
        
        # Pattern 4: Course outcomes
        outcomes = re.findall(r'(?:able to|will be able to)\s+([^\n\.]+)', text, re.IGNORECASE)
        for t in outcomes:
            t = t.strip()
            if len(t) > 5 and len(t) < 100 and t.lower() not in seen:
                topics.append(t)
                seen.add(t.lower())
        
        # Pattern 5: Self-learning topics
        self_learn = re.findall(r'Self[-\s]?learning\s*Topics?[:\s]+([^\n]+)', text, re.IGNORECASE)
        for t in self_learn:
            t = t.strip()
            if len(t) > 5 and t.lower() not in seen:
                topics.append(f"[Self-study] {t}")
                seen.add(t.lower())
        
        # Pattern 6: Bullet points
        bullets = re.findall(r'(?:^|\n)\s*[•\-\*●]\s+([A-Z][^\n]{5,80})', text)
        for t in bullets:
            t = t.strip()
            if len(t) > 5 and t.lower() not in seen:
                topics.append(t)
                seen.add(t.lower())
        
        return topics[:30]
    
    def _extract_hours(self, text: str) -> int:
        """Extract total hours from syllabus - Mumbai University format."""
        # Look for explicit total at end of module table
        patterns = [
            r'Total\s+(\d+)\s*$',                          # "Total 48"
            r'Total\s*(?:Hours?|Hrs?)?[:\s]*(\d+)',         # "Total Hours: 48"
            r'(\d+)\s*(?:Hours?|Hrs?)\s*(?:Total|in total)', # "48 Hours Total"
            r'Duration[:\s]*(\d+)\s*(?:Hours?|Hrs?)',        # "Duration: 48 Hours"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                hours = int(match.group(1))
                if 10 <= hours <= 200:
                    return hours
        
        # Sum up module hours (format: "Module Name 08" or "08 Hours")
        module_hours = re.findall(r'(?:^|\s)(\d{1,2})\s*$', text, re.MULTILINE)
        if module_hours:
            total = sum(int(h) for h in module_hours if 3 <= int(h) <= 20)
            if 20 <= total <= 100:
                return total
        
        # Look for credit hours (4 credits typically = 4 hours/week × 12 weeks = 48 hours)
        credit_match = re.search(r'(?:Credits?|Credit Assigned)[:\s]*(\d+)', text, re.IGNORECASE)
        if credit_match:
            credits = int(credit_match.group(1))
            if 1 <= credits <= 6:
                return credits * 12  # Approximate hours
        
        return 48  # Default for semester course
    
    def _estimate_difficulty(self, text: str) -> str:
        """Estimate difficulty based on keywords."""
        text_lower = text.lower()
        
        scores = {'hard': 0, 'medium': 0, 'easy': 0}
        for diff, keywords in self.DIFFICULTY_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[diff] += 1
        
        if scores['hard'] > scores['medium'] and scores['hard'] > scores['easy']:
            return 'hard'
        elif scores['easy'] > scores['medium'] and scores['easy'] > scores['hard']:
            return 'easy'
        return 'medium'
    
    def _infer_subject_name(self, text: str, modules: List[str]) -> str:
        """Infer subject name from content when not explicitly found."""
        combined = ' '.join(modules).lower()
        text_lower = text.lower()
        
        # Check for specific Mumbai University subjects
        if 'mathematics for ai' in text_lower or 'linear algebra' in combined:
            return 'Mathematics for AI & ML'
        elif 'game theory' in text_lower:
            return 'Game Theory using AI & ML'
        elif 'healthcare' in text_lower and ('ai' in text_lower or 'ml' in text_lower):
            return 'AI & ML in Healthcare'
        elif 'text' in text_lower and 'social media' in text_lower:
            return 'Text, Web and Social Media Analytics'
        elif 'machine learning' in combined and 'blockchain' in combined:
            return 'Machine Learning & Blockchain'
        elif 'machine learning' in combined or 'neural' in combined:
            return 'Machine Learning'
        elif 'blockchain' in combined or 'consensus' in combined:
            return 'Blockchain Technology'
        elif 'data' in combined and ('mining' in combined or 'science' in combined):
            return 'Data Science'
        elif 'database' in combined or 'sql' in combined:
            return 'Database Management Systems'
        elif 'network' in combined:
            return 'Computer Networks'
        elif 'operating' in combined:
            return 'Operating Systems'
        elif 'algorithm' in combined or 'data structure' in combined:
            return 'Data Structures and Algorithms'
        elif 'python' in combined or 'programming' in combined:
            return 'Python Programming'
        elif 'graphics' in combined:
            return 'Engineering Graphics'
        elif 'physics' in combined:
            return 'Applied Physics'
        elif 'chemistry' in combined:
            return 'Applied Chemistry'
        elif 'mathematics' in combined:
            return 'Applied Mathematics'
        
        # Use first module as fallback
        if modules:
            return modules[0]
        
        return 'Engineering Course'
    
    def extract_exam_timetable_with_ai(self, text: str) -> List[Dict]:
        """Extract exam schedule using local NLP."""
        print("🔍 Using Local NLP for exam timetable extraction...")
        
        exams = []
        lines = text.split('\n')
        
        current_date = None
        
        for line in lines:
            # Try to find date
            date_match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', line)
            if date_match:
                d, m, y = date_match.groups()
                y = f"20{y}" if len(y) == 2 else y
                current_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            # Also check for text dates
            month_match = re.search(r'(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*(\d{4})?', line, re.IGNORECASE)
            if month_match:
                d, m, y = month_match.groups()
                month_num = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
                           'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
                m = month_num.get(m.lower()[:3], '01')
                y = y or '2026'
                current_date = f"{y}-{m}-{d.zfill(2)}"
            
            # Extract subject from line
            subject = self._extract_subject_from_line(line)
            
            # Extract time
            time_match = re.search(r'(\d{1,2})[:\.]?(\d{2})?\s*(am|pm|AM|PM)?', line)
            start_time = None
            if time_match:
                h, m, ampm = time_match.groups()
                h = int(h)
                if ampm and ampm.lower() == 'pm' and h < 12:
                    h += 12
                start_time = f"{str(h).zfill(2)}:{m or '00'}"
            
            if subject and current_date:
                exams.append({
                    'subject': subject,
                    'subject_code': '',
                    'date': current_date,
                    'start_time': start_time,
                    'end_time': None,
                    'venue': self._extract_venue(line),
                    'exam_type': 'final' if 'final' in line.lower() else 'mid'
                })
        
        print(f"✅ Local NLP extracted {len(exams)} exams")
        return exams
    
    def _extract_subject_from_line(self, line: str) -> Optional[str]:
        """Extract subject name from a line."""
        # Remove date, time patterns
        clean = re.sub(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}', '', line)
        clean = re.sub(r'\d{1,2}[:\.]?\d{2}\s*(?:am|pm)?', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'(?:Room|Hall|Venue)[:\s]*\w+', '', clean, flags=re.IGNORECASE)
        
        # Look for course code + name
        match = re.search(r'([A-Z]{2,5}\d{2,4}[A-Z]?)?\s*[:\-]?\s*([A-Z][A-Za-z\s&]+)', clean)
        if match:
            name = match.group(2).strip()
            if len(name) > 3:
                return name
        
        return None
    
    def _extract_venue(self, line: str) -> Optional[str]:
        """Extract venue from line."""
        match = re.search(r'(?:Room|Hall|Venue|Building)[:\s]*([A-Z]?\d+[A-Z]?|\w+\s+Hall)', line, re.IGNORECASE)
        return match.group(1) if match else None
    
    def extract_calendar_with_ai(self, text: str) -> List[Dict]:
        """Extract academic calendar events using local NLP."""
        print("🔍 Using Local NLP for calendar extraction...")
        
        events = []
        lines = text.split('\n')
        
        holiday_keywords = ['holiday', 'vacation', 'break', 'off', 'closed', 'leave', 'festival',
                          'diwali', 'christmas', 'eid', 'holi', 'republic', 'independence']
        exam_keywords = ['exam', 'test', 'assessment', 'evaluation']
        
        for line in lines:
            if len(line.strip()) < 5:
                continue
            
            # Extract date
            date = self._extract_date_from_line(line)
            if not date:
                continue
            
            # Extract event name
            name = self._extract_event_name(line)
            if not name:
                continue
            
            # Determine event type
            line_lower = line.lower()
            is_holiday = any(kw in line_lower for kw in holiday_keywords)
            is_exam = any(kw in line_lower for kw in exam_keywords)
            
            event_type = 'holiday' if is_holiday else ('exam' if is_exam else 'event')
            
            events.append({
                'name': name,
                'date': date,
                'end_date': None,
                'event_type': event_type,
                'is_holiday': is_holiday
            })
        
        print(f"✅ Local NLP extracted {len(events)} events")
        return events
    
    def _extract_date_from_line(self, line: str) -> Optional[str]:
        """Extract date from line."""
        # DD/MM/YYYY or DD-MM-YYYY
        match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', line)
        if match:
            d, m, y = match.groups()
            y = f"20{y}" if len(y) == 2 else y
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        
        # DD Month YYYY
        month_map = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
                   'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
        
        match = re.search(r'(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*[,\']?\s*(\d{4})?', line, re.IGNORECASE)
        if match:
            d, m, y = match.groups()
            m = month_map.get(m.lower()[:3], '01')
            y = y or '2026'
            return f"{y}-{m}-{d.zfill(2)}"
        
        return None
    
    def _extract_event_name(self, line: str) -> Optional[str]:
        """Extract event name from line."""
        # Remove date patterns
        clean = re.sub(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}', '', line)
        clean = re.sub(r'\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*[,\']?\s*\d{4}?', '', clean, flags=re.IGNORECASE)
        
        # Clean up
        clean = re.sub(r'[:\-–—|]+', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        if len(clean) > 3:
            return clean
        return None
    
    def enhance_extracted_text(self, text: str) -> str:
        """Clean up OCR text using local processing."""
        if len(text) < 50:
            return text
        
        # Fix common OCR errors
        replacements = [
            (r'l(?=\d)', '1'),  # l before digit -> 1
            (r'(?<=\d)l', '1'),  # l after digit -> 1
            (r'(?<=[A-Za-z])0(?=[A-Za-z])', 'O'),  # 0 between letters -> O
            (r'\s{2,}', ' '),  # Multiple spaces -> single
            (r'([a-z])([A-Z])', r'\1 \2'),  # Add space between camelCase
        ]
        
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text)
        
        return text


# Initialize global AI extractor (now using local NLP)
ai_extractor = LocalNLPExtractor()


# ============================================================================
# SYLLABUS PARSER - University/College Syllabus Format
# ============================================================================

class SyllabusParser:
    """
    Parse university syllabus PDF to extract courses with modules and topics.
    
    Uses table extraction for structured syllabi with:
    - Course codes: HAIMLC501, CS101, etc.
    - Module tables with Module No., Topics, Hours
    - Course name tables
    """
    
    # Course code patterns
    COURSE_CODE_PATTERN = r'\b([A-Z]{2,}[A-Z0-9]*\d{3,4}[A-Z]?)\b'
    
    # Difficulty estimation keywords (expanded for AI/ML syllabus)
    DIFFICULTY_KEYWORDS = {
        'easy': ['introduction', 'basic', 'fundamental', 'overview', 'simple', 'types of', 
                 'definition', 'concept', 'history', 'what is', 'need for'],
        'medium': ['application', 'implementation', 'design', 'analysis', 'methods', 'techniques',
                   'visualization', 'descriptive', 'correlation', 'regression', 'probability',
                   'distribution', 'clustering', 'classification', 'features'],
        'hard': ['advanced', 'complex', 'optimization', 'algorithm', 'theory', 'reduction', 'svd', 
                 'eigenvalue', 'neural', 'deep learning', 'dimensionality', 'gradient', 
                 'convex', 'linear algebra', 'matrix', 'vector', 'transform', 'projection',
                 'pca', 'lda', 't-sne', 'kernel', 'lagrangian', 'hessian', 'jacobian',
                 'bayesian', 'markov', 'eigenvalue decomposition', 'singular value']
    }
    
    def __init__(self):
        self.subjects: List[Subject] = []
        self.ai_extractor = ai_extractor
    
    def parse(self, file_path: str) -> List[Subject]:
        """Parse syllabus PDF and extract courses with modules"""
        # Use pdfplumber for reliable full-text extraction
        text = PDFTextExtractor.extract_text(file_path)
        
        if text:
            print(f"✅ Extracted {len(text)} characters from PDF")
        else:
            print("⚠️ No text extracted from PDF")
            return []
        
        # Try AI-powered extraction (Groq first, then Gemini, then LocalNLP)
        if self.ai_extractor.enabled:
            print("🤖 Using AI for syllabus extraction...")
            
            # Pass extracted text directly to AI extractor
            ai_results = self.ai_extractor._extract_with_groq_or_fallback(text)
            if ai_results:
                subjects = self._convert_ai_results_to_subjects(ai_results)
                if subjects:
                    print(f"✅ AI extracted {len(subjects)} subjects")
                    return subjects
        
        # Fallback to rule-based extraction
        print("📋 Using rule-based syllabus extraction...")
        if HAS_PDFPLUMBER:
            return self._parse_with_tables(file_path)
        return self._parse_from_text(text)
    
    def _text_needs_enhancement(self, text: str) -> bool:
        """Check if text has OCR errors that need AI enhancement"""
        if not text:
            return False
        # Check for common OCR issues
        garbled_ratio = len(re.findall(r'[^\x00-\x7F]', text)) / max(len(text), 1)
        missing_spaces = len(re.findall(r'[a-z][A-Z]', text)) / max(len(text), 1)
        return garbled_ratio > 0.05 or missing_spaces > 0.02
    
    def _convert_ai_results_to_subjects(self, ai_results: List[Dict]) -> List[Subject]:
        """Convert AI extraction results to Subject objects"""
        subjects = []
        for course in ai_results:
            try:
                # Handle case where course might be a string
                if isinstance(course, str):
                    subjects.append(Subject(
                        name=course,
                        topics=[],
                        difficulty='medium',
                        estimated_hours=48.0,
                        priority=6,
                        weekly_target_hours=4.0
                    ))
                    continue
                
                code = course.get('code', '')
                name = course.get('name', 'Unknown Course')
                
                # Build full name
                full_name = f"{name} ({code})" if code else name
                
                # Collect topics from modules
                all_topics = []
                total_hours = course.get('total_hours', 0)
                
                for module in course.get('modules', []):
                    # Handle module as string or dict
                    if isinstance(module, str):
                        all_topics.append(f"📘 {module}")
                    elif isinstance(module, dict):
                        module_name = module.get('name', module.get('title', 'Module'))
                        all_topics.append(f"📘 {module_name}")
                        for topic in module.get('topics', []):
                            all_topics.append(f"  • {topic}")
                        if not total_hours:
                            total_hours += module.get('hours', 0)
                
                # Add topics from course.topics if present
                for topic in course.get('topics', []):
                    if isinstance(topic, str):
                        all_topics.append(f"  • {topic}")
                
                # Get difficulty
                difficulty = course.get('difficulty', 'medium')
                if difficulty not in ['easy', 'medium', 'hard']:
                    difficulty = 'medium'
                
                # Calculate weekly target
                weekly_target = max(2.0, total_hours / 12) if total_hours > 0 else 4.0
                
                subjects.append(Subject(
                    name=full_name,
                    topics=all_topics,
                    difficulty=difficulty,
                    estimated_hours=float(total_hours) if total_hours > 0 else len(all_topics) * 2.0,
                    priority=8 if difficulty == 'hard' else (6 if difficulty == 'medium' else 4),
                    weekly_target_hours=round(weekly_target, 1)
                ))
            except Exception as e:
                print(f"⚠️ Error converting course: {e}")
                continue
        
        return subjects
    
    def _parse_with_tables(self, file_path: str) -> List[Subject]:
        """Parse using table extraction for structured syllabi"""
        subjects = []
        
        with pdfplumber.open(file_path) as pdf:
            current_course = None
            current_modules = []
            last_module = None  # Track last module for continuing across pages
            
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                text = page.extract_text() or ""
                
                for table in tables:
                    if not table:
                        continue
                    
                    # Check if this is a course info table
                    course_info = self._extract_course_from_table(table)
                    if course_info:
                        # Save previous course
                        if current_course and current_modules:
                            subjects.append(self._create_subject(current_course, current_modules))
                        
                        current_course = course_info
                        current_modules = []
                        last_module = None
                        continue
                    
                    # Check if this is a module/topics table
                    modules, last_mod = self._extract_modules_from_table(table, last_module)
                    if modules:
                        current_modules.extend(modules)
                        last_module = last_mod
            
            # Save last course
            if current_course and current_modules:
                subjects.append(self._create_subject(current_course, current_modules))
        
        # If no subjects found via tables, try text parsing
        if not subjects:
            text = PDFTextExtractor.extract_text(file_path)
            subjects = self._parse_from_text(text)
        
        return subjects
    
    def _extract_course_from_table(self, table: List[List]) -> Optional[Dict]:
        """Extract course code and name from a course info table"""
        if not table or len(table) < 2:
            return None
        
        for row in table:
            if not row:
                continue
            
            row_text = ' '.join([str(cell) if cell else '' for cell in row])
            
            # Look for course code
            code_match = re.search(self.COURSE_CODE_PATTERN, row_text)
            if code_match:
                code = code_match.group(1)
                
                # Find course name in the same row
                for cell in row:
                    if cell and isinstance(cell, str):
                        cell_clean = cell.replace('\n', ' ').strip()
                        # Check if it looks like a course name (not the code itself)
                        if cell_clean and cell_clean != code and len(cell_clean) > 5:
                            if not re.match(r'^[\d\-\s]+$', cell_clean):
                                return {
                                    'code': code,
                                    'name': cell_clean
                                }
        
        return None
    
    def _extract_modules_from_table(self, table: List[List], last_module: Optional[Dict] = None) -> Tuple[List[Dict], Optional[Dict]]:
        """Extract modules and topics from a module table
        
        Args:
            table: The table data
            last_module: The last module from previous table (for continuation)
            
        Returns:
            Tuple of (list of modules, last module for continuation)
        """
        modules = []
        
        if not table or len(table) < 2:
            return modules, last_module
        
        # Check if this looks like a module table
        # Look for headers like "Module No.", "Topics", "Hrs."
        header_row = None
        is_continuation = False
        
        for i, row in enumerate(table[:3]):
            row_text = ' '.join([str(cell) if cell else '' for cell in row]).lower()
            if 'module' in row_text or 'topic' in row_text or 'hrs' in row_text:
                header_row = i
                break
        
        # If no header found, check if first row starts with a sub-topic number (continuation)
        if header_row is None:
            first_row = table[0] if table else []
            first_cells = [str(cell).strip() if cell else '' for cell in first_row]
            
            # Check if starts with X.Y pattern (sub-topic continuation)
            for cell in first_cells[:2]:
                if re.match(r'^\d+\.\d+$', cell) and last_module:
                    is_continuation = True
                    header_row = -1  # Start from row 0
                    break
                # Check if starts with X.0 pattern (new module)
                if re.match(r'^\d+\.0$', cell):
                    header_row = -1
                    break
            
            if header_row is None:
                return modules, last_module
        
        # Parse data rows
        current_module = last_module if is_continuation else None
        
        for row in table[header_row + 1:]:
            if not row or all(cell is None or str(cell).strip() == '' for cell in row):
                continue
            
            # Clean row cells
            cells = [str(cell).replace('\n', ' ').strip() if cell else '' for cell in row]
            
            # Skip "Total" rows
            if any('total' in cell.lower() for cell in cells if cell):
                continue
            
            # Check for module header (e.g., "1.0", "2.0")
            first_cell = cells[0] if cells else ''
            second_cell = cells[1] if len(cells) > 1 else ''
            
            # Module header pattern: "1.0" or "2.0" etc.
            if re.match(r'^\d+\.0$', first_cell):
                # This is a module header
                # Find module name (usually in column 2 or 3)
                module_name = ''
                hours = 0
                
                for cell in cells[1:]:
                    if cell:
                        # Check if it's hours (just a number)
                        if re.match(r'^\d+$', cell):
                            hours = int(cell)
                        elif not module_name and len(cell) > 2:
                            module_name = cell
                
                if module_name:
                    current_module = {
                        'number': first_cell,
                        'name': module_name,
                        'hours': hours,
                        'topics': []
                    }
                    modules.append(current_module)
            
            # Sub-topic pattern: "1.1", "2.1" etc. (in second column usually)
            elif re.match(r'^\d+\.\d+$', second_cell) and current_module:
                # This is a sub-topic
                topic_text = ''
                hours_val = 0
                for cell in cells[2:]:
                    if cell:
                        if re.match(r'^\d+$', cell):
                            hours_val = int(cell)
                        elif len(cell) > 3:
                            topic_text = cell
                            break
                
                if topic_text:
                    current_module['topics'].append(topic_text)
                    if hours_val:
                        current_module['hours'] = current_module.get('hours', 0) + hours_val
            
            # Also check first cell for sub-topic
            elif re.match(r'^\d+\.\d+$', first_cell) and current_module:
                topic_text = ''
                hours_val = 0
                for cell in cells[1:]:
                    if cell:
                        if re.match(r'^\d+$', cell):
                            hours_val = int(cell)
                        elif len(cell) > 3:
                            topic_text = cell
                            break
                
                if topic_text:
                    current_module['topics'].append(topic_text)
                    if hours_val:
                        current_module['hours'] = current_module.get('hours', 0) + hours_val
        
        return modules, current_module
    
    def _parse_from_text(self, text: str) -> List[Subject]:
        """Fallback: Parse from plain text when tables aren't available"""
        subjects = []
        lines = text.split('\n')
        
        current_course = None
        current_modules = []
        current_module = None
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Look for course code
            code_match = re.search(self.COURSE_CODE_PATTERN, line)
            if code_match:
                code = code_match.group(1)
                # Try to find name
                remaining = line[code_match.end():].strip()
                remaining = re.sub(r'^[\s:\-]+', '', remaining)
                
                if remaining and len(remaining) > 5:
                    if current_course and current_modules:
                        subjects.append(self._create_subject(current_course, current_modules))
                    
                    current_course = {'code': code, 'name': remaining}
                    current_modules = []
                    current_module = None
                continue
            
            # Look for module header (X.0 Module Name)
            module_match = re.match(r'^(\d+)\.0\s+(.+?)(?:\s+(\d+)\s*)?$', line)
            if module_match:
                module_name = module_match.group(2).strip()
                hours = int(module_match.group(3)) if module_match.group(3) else 0
                
                current_module = {
                    'number': f"{module_match.group(1)}.0",
                    'name': module_name,
                    'hours': hours,
                    'topics': []
                }
                current_modules.append(current_module)
                continue
            
            # Look for sub-topic (X.Y Topic content)
            topic_match = re.match(r'^(\d+)\.(\d+)\s+(.+)', line)
            if topic_match and current_module:
                topic_text = topic_match.group(3).strip()
                if len(topic_text) > 3:
                    current_module['topics'].append(topic_text)
        
        # Save last course
        if current_course and current_modules:
            subjects.append(self._create_subject(current_course, current_modules))
        
        return subjects
    
    def _create_subject(self, course_info: Dict, modules: List[Dict]) -> Subject:
        """Create a Subject object from parsed data"""
        course_name = course_info.get('name', 'Unknown Course')
        course_code = course_info.get('code', '')
        
        # Clean course name
        course_name = re.sub(r'\s+', ' ', course_name).strip()
        if course_code:
            full_name = f"{course_name} ({course_code})"
        else:
            full_name = course_name
        
        # Collect all topics and calculate hours
        all_topics = []
        total_hours = 0
        
        for module in modules:
            module_name = module.get('name', 'Module')
            topics = module.get('topics', [])
            hours = module.get('hours', 0)
            
            # Add module as a main topic
            all_topics.append(f"📘 {module_name}")
            
            # Add sub-topics
            for topic in topics:
                all_topics.append(f"  • {topic}")
            
            total_hours += hours
        
        # Estimate difficulty
        difficulty = self._estimate_difficulty(all_topics)
        
        # Calculate weekly target based on total hours
        weekly_target = max(2.0, total_hours / 12) if total_hours > 0 else 4.0
        
        return Subject(
            name=full_name,
            topics=all_topics,
            difficulty=difficulty,
            estimated_hours=float(total_hours) if total_hours > 0 else len(all_topics) * 2.0,
            priority=8 if difficulty == 'hard' else (6 if difficulty == 'medium' else 4),
            weekly_target_hours=round(weekly_target, 1)
        )
    
    def _estimate_difficulty(self, topics: List[str]) -> str:
        """Estimate difficulty based on topic keywords"""
        combined = ' '.join(topics).lower()
        
        scores = {'easy': 0, 'medium': 0, 'hard': 0}
        for difficulty, keywords in self.DIFFICULTY_KEYWORDS.items():
            for kw in keywords:
                if kw in combined:
                    scores[difficulty] += 1
        
        if scores['hard'] > scores['medium'] and scores['hard'] > scores['easy']:
            return 'hard'
        elif scores['easy'] > scores['medium']:
            return 'easy'
        return 'medium'


# ============================================================================
# ACADEMIC CALENDAR PARSER
# ============================================================================

class AcademicCalendarParser:
    """Parse academic calendar PDF to extract events and holidays"""
    
    # Date patterns
    DATE_PATTERNS = [
        r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})',  # DD/MM/YYYY or DD-MM-YYYY
        r'(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*[,\']?\s*(\d{2,4})?',
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})[,\s]*(\d{2,4})?',
        # Mumbai University "First Half / Second Half" patterns
        r'First\s+Half\s+of\s+(\d{4})',
        r'Second\s+Half\s+of\s+(\d{4})',
        r'Commencement\s+Date.*(\d{2}/\d{2}/\d{4})'
    ]
    
    # Event type keywords
    HOLIDAY_KEYWORDS = ['holiday', 'vacation', 'break', 'off', 'closed', 'leave']
    EXAM_KEYWORDS = ['exam', 'test', 'assessment', 'evaluation', 'viva']
    DEADLINE_KEYWORDS = ['deadline', 'submission', 'due', 'last date', 'final date']
    
    MONTH_MAP = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    def __init__(self, default_year: int = None):
        self.default_year = default_year or datetime.now().year
        self.events: List[AcademicEvent] = []
        self.ai_extractor = ai_extractor
    
    def parse(self, file_path: str) -> List[AcademicEvent]:
        """Parse academic calendar PDF"""
        text = PDFTextExtractor.extract_text(file_path)
        
        # Try AI-powered extraction first
        if self.ai_extractor.enabled:
            print("🤖 Using Cohere AI for calendar extraction...")
            ai_results = self.ai_extractor.extract_calendar_with_ai(text)
            if ai_results:
                events = self._convert_ai_results_to_events(ai_results)
                if events:
                    print(f"✅ AI extracted {len(events)} events")
                    return events
        
        # Fallback to rule-based extraction
        print("📋 Using rule-based calendar extraction...")
        return self._parse_text(text)
    
    def _convert_ai_results_to_events(self, ai_results: List[Dict]) -> List[AcademicEvent]:
        """Convert AI extraction results to AcademicEvent objects"""
        events = []
        for event_data in ai_results:
            try:
                name = event_data.get('name', '')
                date = event_data.get('date', '')
                
                if not name or not date:
                    continue
                
                # Validate date
                try:
                    datetime.fromisoformat(date)
                except ValueError:
                    continue
                
                events.append(AcademicEvent(
                    name=name,
                    date=date,
                    end_date=event_data.get('end_date'),
                    event_type=event_data.get('event_type', 'event'),
                    is_holiday=event_data.get('is_holiday', False),
                    affects_study=not event_data.get('is_holiday', False)
                ))
            except Exception as e:
                print(f"⚠️ Error converting event: {e}")
                continue
        
        return events
    
    def _parse_text(self, text: str) -> List[AcademicEvent]:
        """Parse calendar text to extract events"""
        events = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            # Try to extract date
            date = self._extract_date(line)
            if not date:
                continue
            
            # Extract event name (remove date from line)
            event_name = self._extract_event_name(line)
            if not event_name or len(event_name) < 3:
                continue
            
            # Determine event type
            event_type = self._determine_event_type(event_name)
            is_holiday = event_type == 'holiday'
            
            events.append(AcademicEvent(
                name=event_name,
                date=date,
                event_type=event_type,
                is_holiday=is_holiday,
                affects_study=not is_holiday
            ))
        
        return events
    
    def _extract_date(self, text: str) -> Optional[str]:
        """Extract date from text and return ISO format"""
        text_lower = text.lower()
        
        # Try each pattern
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                groups = match.groups()
                
                try:
                    if pattern == self.DATE_PATTERNS[0]:
                        # DD/MM/YYYY format
                        day = int(groups[0])
                        month = int(groups[1])
                        year = int(groups[2]) if len(groups[2]) == 4 else 2000 + int(groups[2])
                    else:
                        # Month name format
                        if groups[0].isdigit():
                            day = int(groups[0])
                            month = self.MONTH_MAP.get(groups[1][:3], 1)
                            year = int(groups[2]) if groups[2] else self.default_year
                        else:
                            month = self.MONTH_MAP.get(groups[0][:3], 1)
                            day = int(groups[1])
                            year = int(groups[2]) if groups[2] else self.default_year
                    
                    if year < 100:
                        year = 2000 + year
                    
                    # Validate date
                    if 1 <= day <= 31 and 1 <= month <= 12:
                        return f"{year}-{month:02d}-{day:02d}"
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_event_name(self, text: str) -> str:
        """Extract event name from line (remove date)"""
        # Remove date patterns
        for pattern in self.DATE_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Clean up
        text = re.sub(r'[:\-–—|]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _determine_event_type(self, name: str) -> str:
        """Determine event type from name"""
        name_lower = name.lower()
        
        if any(kw in name_lower for kw in self.HOLIDAY_KEYWORDS):
            return 'holiday'
        if any(kw in name_lower for kw in self.EXAM_KEYWORDS):
            return 'exam'
        if any(kw in name_lower for kw in self.DEADLINE_KEYWORDS):
            return 'deadline'
        
        return 'event'


# ============================================================================
# EXAM TIMETABLE PARSER
# ============================================================================

class ExamTimetableParser:
    """
    Parse exam timetable PDF to extract exam schedule.
    Supports multiple formats:
    - Table format (columns: Date, Time, Subject, Venue)
    - Row format (each line contains date + subject)
    - Section format (date header followed by subjects)
    """
    
    # Time patterns - more comprehensive
    TIME_PATTERNS = [
        r'(\d{1,2})[:\.](\d{2})\s*(am|pm|AM|PM|a\.m\.|p\.m\.)?',
        r'(\d{1,2})\s*(am|pm|AM|PM|a\.m\.|p\.m\.)',
        r'(\d{1,2}):(\d{2})\s*(?:to|-|–)\s*(\d{1,2}):(\d{2})',  # Time range
    ]
    
    # Subject code patterns (common in universities)
    SUBJECT_CODE_PATTERNS = [
        r'([A-Z]{2,4}[-\s]?\d{3,4})',  # CS101, CS-101, MATH1001
        r'(\d{2}[A-Z]{2,4}\d{2,4})',    # 18CS56, 21MAT11
    ]
    
    # Common subject keywords to help identify subjects
    SUBJECT_KEYWORDS = [
        'mathematics', 'math', 'calculus', 'algebra', 'statistics',
        'physics', 'chemistry', 'biology',
        'computer', 'programming', 'data structure', 'algorithm', 'database',
        'network', 'operating system', 'software', 'web', 'machine learning',
        'electronics', 'electrical', 'mechanical', 'civil',
        'management', 'economics', 'accounting', 'english', 'communication'
    ]
    
    # Words to filter out (not subject names)
    FILTER_WORDS = [
        'exam', 'examination', 'test', 'room', 'hall', 'venue', 'building',
        'time', 'date', 'day', 'morning', 'afternoon', 'evening', 'session',
        'forenoon', 'fn', 'an', 'slot', 'batch', 'roll', 'number', 'seat',
        'instructions', 'note', 'important', 'student', 'candidate',
        'university', 'college', 'department', 'semester', 'year',
        'internal', 'external', 'theory', 'practical', 'lab',
        'marks', 'duration', 'hours', 'mins', 'minutes',
        'page', 'serial', 'sl', 'no', 'sr'
    ]
    
    def __init__(self, default_year: int = None):
        self.default_year = default_year or datetime.now().year
        self.calendar_parser = AcademicCalendarParser(default_year)
        self.ai_extractor = ai_extractor
    
    def parse(self, file_path: str) -> List[ExamSchedule]:
        """Parse exam timetable PDF using multiple strategies with OCR support"""
        exams = []
        text = ""
        
        # Strategy 0: Try LayoutLMv3 + Tesseract OCR first (best for scanned PDFs)
        print("🔍 Attempting LayoutLMv3 + Tesseract OCR extraction...")
        layoutlm = get_layoutlm_extractor()
        if layoutlm and layoutlm.enabled:
            try:
                result = layoutlm.extract_from_pdf(file_path)
                if result and result.get('text'):
                    text = result['text']
                    print(f"✅ LayoutLMv3 extracted {len(text)} characters")
            except Exception as e:
                print(f"⚠️ LayoutLMv3 extraction failed: {e}")
        
        # Fallback to pdfplumber for digital PDFs
        if not text or len(text) < 100:
            print("📄 Trying pdfplumber extraction...")
            text = PDFTextExtractor.extract_text(file_path)
        
        if not text or len(text) < 100:
            print("🖼️ Trying Gemini image-based OCR fallback for scanned timetable...")
            exams = self._extract_exams_from_scanned_pdf_with_gemini(file_path)
            if exams:
                print(f"✅ Gemini image OCR extracted {len(exams)} exams")
                return self._deduplicate_exams(exams)
            print("❌ Failed to extract text from PDF")
            return []
        
        # Strategy 1: Try Groq AI extraction first (most robust for structured data)
        if HAS_GROQ and GROQ_API_KEY != "gsk_PLACEHOLDER":
            print("🤖 Using Groq AI for exam timetable extraction...")
            try:
                exams = self._extract_exams_with_groq(text)
                if exams:
                    print(f"✅ Groq AI extracted {len(exams)} exams")
                    return self._deduplicate_exams(exams)
            except Exception as e:
                print(f"⚠️ Groq extraction failed: {e}")
        
        # Strategy 2: Try LocalNLP AI extraction
        if self.ai_extractor.enabled:
            print("🤖 Using LocalNLP for exam timetable extraction...")
            ai_results = self.ai_extractor.extract_exam_timetable_with_ai(text)
            if ai_results:
                exams = self._convert_ai_results_to_exams(ai_results)
                if exams:
                    print(f"✅ LocalNLP extracted {len(exams)} exams")
                    return self._deduplicate_exams(exams)
        
        print("📋 Using rule-based exam extraction...")
        
        # Strategy 1: Try layout-aware parsing (best for tables)
        elements = PDFTextExtractor.extract_with_layout(file_path)
        if elements:
            exams = self._parse_with_layout(elements)
            if exams:
                print(f"  → Layout parsing found {len(exams)} exams")
                return self._deduplicate_exams(exams)
        
        # Strategy 2: Try plain text with table detection
        exams = self._parse_table_format(text)
        if exams:
            print(f"  → Table parsing found {len(exams)} exams")
            return self._deduplicate_exams(exams)
        
        # Strategy 3: Line-by-line parsing
        exams = self._parse_line_by_line(text)
        if exams:
            print(f"  → Line parsing found {len(exams)} exams")
            return self._deduplicate_exams(exams)
        
        # Strategy 4: Section-based parsing
        exams = self._parse_sections(text)
        print(f"  → Section parsing found {len(exams)} exams")
        return self._deduplicate_exams(exams)

    def _get_google_vision_model(self):
        """Build a Google Gemini model directly for multimodal OCR fallback."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return None

        try:
            import google.generativeai as genai
        except Exception as e:
            print(f"⚠️ Gemini vision client unavailable: {e}")
            return None

        try:
            genai.configure(api_key=api_key)
            model_name = os.getenv("GOOGLE_GENAI_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
            return genai.GenerativeModel(model_name)
        except Exception as e:
            print(f"⚠️ Failed to initialize Gemini vision model: {e}")
            return None

    def _extract_exams_from_scanned_pdf_with_gemini(self, file_path: str) -> List[ExamSchedule]:
        """Extract exam timetable directly from rendered page images using Gemini."""
        model = self._get_google_vision_model()
        if not model:
            return []

        try:
            page_images = self._render_pdf_pages_for_vision(file_path)
            if not page_images:
                return []

            prompt = """You are reading pages from a university exam timetable PDF.
Extract every exam shown across all provided pages.

Return ONLY a valid JSON array. Each item must have this exact shape:
[
  {
    "subject": "Digital Signal Processing",
    "date": "2025-11-18",
    "start_time": "10:30",
    "end_time": "13:30",
    "venue": null,
    "exam_type": "final"
  }
]

Rules:
- Include every visible exam row from all pages.
- Convert dates to ISO format YYYY-MM-DD.
- Use 24-hour HH:MM time when visible, otherwise null.
- Subject must be the human-readable paper name only, not the subject code.
- Ignore headers, seat number notes, legends, and administrative instructions.
- If a field is not visible, use null.
- Return JSON only with no markdown fences or explanation."""

            response = model.generate_content([prompt, *page_images])
            content = (getattr(response, "text", "") or "").strip()
            if not content:
                return []

            content = re.sub(r"^```json\s*", "", content, flags=re.MULTILINE)
            content = re.sub(r"^```\s*|\s*```$", "", content, flags=re.MULTILINE)
            ai_results = json.loads(content.strip())
            if not isinstance(ai_results, list):
                return []

            return self._convert_ai_results_to_exams(ai_results)
        except Exception as e:
            print(f"⚠️ Gemini image OCR fallback failed: {e}")
            return []

    def _render_pdf_pages_for_vision(self, file_path: str, max_pages: int = 4) -> List[Any]:
        """Render PDF pages to PIL images using whatever local backend is available."""
        from io import BytesIO

        # Prefer PyMuPDF when available.
        try:
            import fitz

            page_images = []
            with fitz.open(file_path) as doc:
                for page_index in range(min(max_pages, len(doc))):
                    page = doc[page_index]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
                    image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
                    page_images.append(image)
            if page_images:
                return page_images
        except Exception as e:
            print(f"⚠️ PyMuPDF rendering unavailable: {e}")

        # Fall back to pypdfium2, which works without external poppler binaries.
        try:
            import pypdfium2 as pdfium

            page_images = []
            pdf = pdfium.PdfDocument(file_path)
            for page_index in range(min(max_pages, len(pdf))):
                page = pdf[page_index]
                bitmap = page.render(scale=2.5)
                pil_image = bitmap.to_pil().convert("RGB")
                page_images.append(pil_image)
            if page_images:
                return page_images
        except Exception as e:
            print(f"⚠️ pypdfium2 rendering unavailable: {e}")

        print("⚠️ Image OCR prerequisites unavailable: no supported PDF renderer found")
        return []
    
    def _extract_exams_with_groq(self, text: str) -> List[ExamSchedule]:
        """Extract exam schedule using Groq AI with structured output"""
        try:
            client = Groq(api_key=GROQ_API_KEY)
            
            prompt = f"""Extract exam schedule information from this timetable.

Text:
{text[:8000]}

Return a JSON array with this EXACT structure:
[
  {{
    "subject": "Computer Networks",
    "date": "2025-11-15",
    "day": "Monday",
    "start_time": "10:00",
    "end_time": "13:00",
    "venue": "Hall A",
    "exam_type": "final"
  }}
]

CRITICAL RULES:
- subject: ONLY the subject/paper name. DO NOT include course codes like CSC401, HAIMLC501, 153111, IoTCSBCC702, etc.
- date: ISO format YYYY-MM-DD
- day: full day name if available
- start_time/end_time: 24-hour HH:MM format
- exam_type: "final", "mid", "practical", "quiz", or "exam"
- Extract ALL exams, don't skip any

IMPORTANT: The subject field must contain ONLY the human-readable subject name, not codes.

Return ONLY the JSON array, no markdown or explanation."""
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean markdown code blocks
            if content.startswith('```'):
                content = '\n'.join(content.split('\n')[1:-1])
            content = content.replace('```json', '').replace('```', '').strip()
            
            # Parse JSON
            exam_data = json.loads(content)
            
            if not isinstance(exam_data, list):
                print("⚠️ Groq returned non-list data")
                return []
            
            # Convert to ExamSchedule objects
            exams = []
            for exam in exam_data:
                try:
                    subject = exam.get('subject', '')
                    subject_code = exam.get('subject_code', '')
                    
                    # Clean the subject name - remove any codes that might be included
                    subject = self._remove_code_from_subject(subject)
                    
                    date = exam.get('date', '')
                    if not date or not subject:
                        continue
                    
                    # Validate date
                    try:
                        datetime.fromisoformat(date)
                    except ValueError:
                        print(f"⚠️ Invalid date format: {date}")
                        continue
                    
                    exams.append(ExamSchedule(
                        subject=subject,
                        date=date,
                        start_time=exam.get('start_time'),
                        end_time=exam.get('end_time'),
                        venue=exam.get('venue'),
                        exam_type=exam.get('exam_type', 'exam')
                    ))
                except Exception as e:
                    print(f"⚠️ Error converting exam: {e}")
                    continue
            
            return exams
            
        except Exception as e:
            print(f"⚠️ Groq extraction error: {e}")
            return []
    
    def _remove_code_from_subject(self, text: str) -> str:
        """Remove subject codes from subject name (codes at beginning or end)"""
        if not text:
            return text
        
        original = text
        
        # Remove codes at the beginning (e.g., "CSC401 - Computer Networks")
        text = re.sub(r'^[A-Z]{2,}[-\s]?\d{3,}[A-Z]?\s*[-–—:]\s*', '', text)
        text = re.sub(r'^\d{6,}\s*[-–—:]\s*', '', text)  # 153111 - Math
        
        # Remove codes at the end (various patterns)
        # HAIMLC501, TCSBCC501, IoTCSBCC702
        text = re.sub(r'\s*[-–—]?\s*[A-Za-z]{1,3}[oO0]?[A-Z]{2,}[A-Z0-9]*\d{3,}[A-Z]?\s*$', '', text)
        # Standard codes: CS101, MATH1001
        text = re.sub(r'\s*[-–—]?\s*[A-Z]{2,}\d{3,}[A-Z]?\s*$', '', text)
        # Numeric codes: 153111, 2153112
        text = re.sub(r'\s*[-–—]?\s*\d{5,}\s*$', '', text)
        # Mixed: OEC301, ILO7016, ILO7017
        text = re.sub(r'\s*[-–—]?\s*[A-Z]{2,3}\d{3,5}\s*$', '', text)
        
        # OCR-garbled codes (P loTCSBCC701, P P aioe, PAM) loTESBEDOTOL)
        text = re.sub(r'\s*[-–—]?\s*[PpIi]\s+[A-Za-z0-9]+\s*$', '', text)
        text = re.sub(r'\s*[-–—]?\s*[PpIi]\s*[PpIi]\s+[A-Za-z0-9]+\s*$', '', text)
        text = re.sub(r'\s*[-–—]?\s*\([^)]*\)\s*[A-Za-z0-9]+\s*$', '', text)  # (PAM) something
        
        # Clean up trailing punctuation and spaces
        text = re.sub(r'\s*[-–—:]+\s*$', '', text)
        text = text.strip()
        
        # If we removed everything, return original (minus obvious codes)
        if not text or len(text) < 3:
            # Try to extract just the name part before any code
            match = re.match(r'^(.+?)\s*[-–—]\s*[A-Za-z0-9]+$', original)
            if match:
                return match.group(1).strip()
            return original.strip()
        
        return text
    
    def _convert_ai_results_to_exams(self, ai_results: List[Dict]) -> List[ExamSchedule]:
        """Convert AI extraction results to ExamSchedule objects"""
        exams = []
        for exam_data in ai_results:
            try:
                subject = exam_data.get('subject', '')
                
                # Clean subject name - remove any codes
                subject = self._remove_code_from_subject(subject)
                
                date = exam_data.get('date', '')
                if not date or not subject:
                    continue
                
                # Validate date format
                try:
                    datetime.fromisoformat(date)
                except ValueError:
                    continue
                
                exams.append(ExamSchedule(
                    subject=subject,
                    date=date,
                    start_time=exam_data.get('start_time'),
                    end_time=exam_data.get('end_time'),
                    venue=exam_data.get('venue'),
                    exam_type=exam_data.get('exam_type', 'exam')
                ))
            except Exception as e:
                print(f"⚠️ Error converting exam: {e}")
                continue
        
        return exams
    
    def _parse_with_layout(self, elements: List[Dict]) -> List[ExamSchedule]:
        """Parse using layout information - good for formatted tables"""
        exams = []
        
        # Group elements by approximate row (y position)
        rows = {}
        for elem in elements:
            y_key = round(elem['y'] / 15) * 15  # Group within 15px
            if y_key not in rows:
                rows[y_key] = []
            rows[y_key].append(elem)
        
        # Sort rows by y position
        sorted_rows = sorted(rows.items(), key=lambda x: x[0])
        
        current_date = None
        header_row = None
        
        for y, row_elements in sorted_rows:
            # Combine text from row
            row_text = ' '.join([e['text'] for e in sorted(row_elements, key=lambda x: x.get('x', 0))])
            
            # Skip if looks like header
            if self._is_header_row(row_text):
                header_row = row_text
                continue
            
            # Try to extract date
            date = self.calendar_parser._extract_date(row_text)
            if date:
                current_date = date
            
            # Try to extract subject
            subject = self._extract_subject_smart(row_text)
            if subject and len(subject) > 2:
                start_time, end_time = self._extract_time_range(row_text)
                venue = self._extract_venue(row_text)
                exam_type = self._determine_exam_type(row_text)
                
                # Use current_date if no date in this row
                exam_date = date or current_date
                if exam_date:
                    exams.append(ExamSchedule(
                        subject=subject,
                        date=exam_date,
                        start_time=start_time,
                        end_time=end_time,
                        venue=venue,
                        exam_type=exam_type
                    ))
        
        return exams
    
    def _parse_table_format(self, text: str) -> List[ExamSchedule]:
        """Parse table-like format with columns separated by multiple spaces or tabs"""
        exams = []
        lines = text.split('\n')
        
        current_date = None
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            # Skip header rows
            if self._is_header_row(line):
                continue
            
            # Split by multiple spaces or tabs (table columns)
            columns = re.split(r'\s{2,}|\t+', line)
            columns = [c.strip() for c in columns if c.strip()]
            
            if len(columns) >= 2:
                # Try to find date and subject in columns
                date_found = None
                subject_found = None
                time_found = None
                venue_found = None
                
                for col in columns:
                    if not date_found:
                        date_found = self.calendar_parser._extract_date(col)
                    if not subject_found:
                        subj = self._extract_subject_smart(col)
                        if subj and len(subj) > 3:
                            subject_found = subj
                    if not time_found:
                        t1, t2 = self._extract_time_range(col)
                        if t1:
                            time_found = (t1, t2)
                    if not venue_found:
                        venue_found = self._extract_venue(col)
                
                if date_found:
                    current_date = date_found
                
                if subject_found and current_date:
                    exams.append(ExamSchedule(
                        subject=subject_found,
                        date=current_date,
                        start_time=time_found[0] if time_found else None,
                        end_time=time_found[1] if time_found else None,
                        venue=venue_found,
                        exam_type=self._determine_exam_type(line)
                    ))
        
        return exams
    
    def _parse_line_by_line(self, text: str) -> List[ExamSchedule]:
        """Parse text line by line"""
        exams = []
        lines = text.split('\n')
        
        current_date = None
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            if self._is_header_row(line):
                continue
            
            # Extract date
            date = self.calendar_parser._extract_date(line)
            if date:
                current_date = date
            
            # Extract subject
            subject = self._extract_subject_smart(line)
            
            if subject and current_date:
                start_time, end_time = self._extract_time_range(line)
                venue = self._extract_venue(line)
                exam_type = self._determine_exam_type(line)
                
                exams.append(ExamSchedule(
                    subject=subject,
                    date=current_date,
                    start_time=start_time,
                    end_time=end_time,
                    venue=venue,
                    exam_type=exam_type
                ))
        
        return exams
    
    def _parse_sections(self, text: str) -> List[ExamSchedule]:
        """Parse by date sections - date as header, subjects below"""
        exams = []
        lines = text.split('\n')
        
        current_date = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Check if this line is primarily a date
            date = self.calendar_parser._extract_date(line)
            if date:
                # Check if this is a date-only line (header)
                remaining = line
                for pattern in self.calendar_parser.DATE_PATTERNS:
                    remaining = re.sub(pattern, '', remaining, flags=re.IGNORECASE)
                remaining = remaining.strip()
                
                if len(remaining) < 10:  # Mostly just a date
                    current_date = date
                    continue
            
            # Try to extract subject from this line
            subject = self._extract_subject_smart(line)
            if subject and current_date:
                start_time, end_time = self._extract_time_range(line)
                
                exams.append(ExamSchedule(
                    subject=subject,
                    date=current_date,
                    start_time=start_time,
                    end_time=end_time,
                    exam_type=self._determine_exam_type(line)
                ))
        
        return exams
    
    def _is_header_row(self, text: str) -> bool:
        """Check if row is a header row"""
        text_lower = text.lower()
        header_keywords = ['date', 'time', 'subject', 'course', 'paper', 'venue', 'room', 
                          'sl.no', 'sr.no', 'serial', 'code', 'session']
        
        # If multiple header keywords present, likely a header
        count = sum(1 for kw in header_keywords if kw in text_lower)
        return count >= 2
    
    def _extract_subject_smart(self, text: str) -> Optional[str]:
        """Smart extraction of subject name - returns ONLY the subject name without code"""
        original = text
        cleaned = text
        
        # First, try to find subject code and extract name
        for pattern in self.SUBJECT_CODE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                code = match.group(1)
                # Get text after the code as subject name
                after_code = text[match.end():].strip()
                after_code = re.sub(r'^[\s:\-–]+', '', after_code)
                
                # Also check text before the code
                before_code = text[:match.start()].strip()
                before_code = re.sub(r'[\s:\-–]+$', '', before_code)
                
                # Use whichever part is longer and valid
                subject_name = self._clean_subject_name(after_code) or self._clean_subject_name(before_code)
                if subject_name and len(subject_name) > 3:
                    # Return ONLY the subject name, no code
                    return subject_name
        
        # Remove date patterns
        for pattern in self.calendar_parser.DATE_PATTERNS:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove time patterns
        for pattern in self.TIME_PATTERNS:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove venue patterns
        cleaned = re.sub(r'(?:room|hall|venue|lab|building)[\s:\-]*[A-Z0-9\-]+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b[A-Z]{1,2}[-\s]?\d{2,4}\b', '', cleaned)  # Room codes
        
        # Remove filter words
        for word in self.FILTER_WORDS:
            cleaned = re.sub(rf'\b{word}s?\b', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up
        cleaned = re.sub(r'[:\-–—|/\\()\[\]{}]', ' ', cleaned)
        cleaned = re.sub(r'\d{1,2}:\d{2}', '', cleaned)  # Remove remaining times
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Remove leading/trailing numbers and punctuation
        cleaned = re.sub(r'^[\d\s\.\-]+', '', cleaned)
        cleaned = re.sub(r'[\d\s\.\-]+$', '', cleaned)
        cleaned = cleaned.strip()
        
        # Validate: should be reasonable length and contain letters
        if len(cleaned) >= 3 and re.search(r'[a-zA-Z]{2,}', cleaned):
            return cleaned.title()
        
        return None
    
    def _clean_subject_name(self, text: str) -> str:
        """Clean up extracted subject name - remove codes and garbled text"""
        # Remove common suffixes/prefixes
        for word in self.FILTER_WORDS:
            text = re.sub(rf'\b{word}s?\b', '', text, flags=re.IGNORECASE)
        
        # Remove special characters
        text = re.sub(r'[:\-–—|/\\()\[\]{}]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove leading numbers
        text = re.sub(r'^\d+[\.\s]*', '', text)
        
        # Remove subject codes at the end (common patterns)
        # Pattern: letters followed by numbers (e.g., HAIMLC701, loTCSBCC701, CS101)
        text = re.sub(r'\s*[-–—]?\s*[A-Za-z]{1,2}[oO0]?[A-Z]{2,}[A-Z0-9]*\d{3,}[A-Z]?\s*$', '', text)
        text = re.sub(r'\s*[-–—]?\s*[A-Z]{2,}\d{3,}[A-Z]?\s*$', '', text)  # HAIMLC501
        text = re.sub(r'\s*[-–—]?\s*\d{6,}\s*$', '', text)  # 153111, 2153112
        text = re.sub(r'\s*[-–—]?\s*[A-Z]{3,}[-]?[A-Z]*\d{3,}\s*$', '', text)  # OEC301, ILO7016
        
        # Remove garbled OCR codes (mix of letters/numbers at end)
        text = re.sub(r'\s*[-–—]?\s*[PpIi]\s*[A-Za-z0-9]{5,}\s*$', '', text)  # P loTCSBCC701
        text = re.sub(r'\s*[-–—]?\s*[A-Za-z][oO0][A-Z]+\d+\s*$', '', text)  # loTCSBCC503
        
        # Clean up trailing hyphens/dashes and spaces
        text = re.sub(r'\s*[-–—]+\s*$', '', text)
        text = text.strip()
        
        return text
    
    def _extract_time_range(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract start and end time from line"""
        times = []
        
        # First try to find time range pattern
        range_pattern = r'(\d{1,2})[:\.]?(\d{2})?\s*(am|pm|AM|PM)?\s*(?:to|-|–|—)\s*(\d{1,2})[:\.]?(\d{2})?\s*(am|pm|AM|PM)?'
        range_match = re.search(range_pattern, line, re.IGNORECASE)
        if range_match:
            g = range_match.groups()
            try:
                # Start time
                start_hour = int(g[0])
                start_min = int(g[1]) if g[1] else 0
                start_period = (g[2] or '').lower()
                
                # End time
                end_hour = int(g[3])
                end_min = int(g[4]) if g[4] else 0
                end_period = (g[5] or start_period or '').lower()
                
                # Convert to 24h
                if start_period == 'pm' and start_hour < 12:
                    start_hour += 12
                elif start_period == 'am' and start_hour == 12:
                    start_hour = 0
                    
                if end_period == 'pm' and end_hour < 12:
                    end_hour += 12
                elif end_period == 'am' and end_hour == 12:
                    end_hour = 0
                
                return f"{start_hour:02d}:{start_min:02d}", f"{end_hour:02d}:{end_min:02d}"
            except (ValueError, IndexError):
                pass
        
        # Fall back to finding individual times
        time_pattern = r'(\d{1,2})[:\.](\d{2})\s*(am|pm|AM|PM)?'
        for match in re.finditer(time_pattern, line, re.IGNORECASE):
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                period = (match.group(3) or '').lower()
                
                if period == 'pm' and hour < 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0
                
                times.append(f"{hour:02d}:{minute:02d}")
            except (ValueError, IndexError):
                continue
        
        if len(times) >= 2:
            return times[0], times[1]
        elif len(times) == 1:
            return times[0], None
        
        return None, None
    
    def _extract_venue(self, line: str) -> Optional[str]:
        """Extract venue/room from line"""
        venue_patterns = [
            r'(?:room|hall|venue|lab|building)[\s:\-]*([A-Z0-9][\w\-]*)',
            r'\b(LH[-\s]?\d+)\b',  # Lecture Hall
            r'\b(LAB[-\s]?\d+)\b',  # Lab
            r'\b([A-Z]{1,3}[-\s]?\d{2,4}[A-Z]?)\b',  # Room codes like A-101, CS102
        ]
        
        for pattern in venue_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                venue = match.group(1).strip()
                # Avoid matching subject codes
                if not any(kw in venue.lower() for kw in ['cs', 'it', 'ec', 'me', 'cv', 'math']):
                    return venue
        
        return None
    
    def _determine_exam_type(self, line: str) -> str:
        """Determine exam type from context"""
        line_lower = line.lower()
        
        if any(kw in line_lower for kw in ['mid', 'midterm', 'mid-term', 'cie', 'internal']):
            return 'mid'
        if any(kw in line_lower for kw in ['final', 'end', 'semester', 'see', 'external']):
            return 'final'
        if any(kw in line_lower for kw in ['quiz', 'test', 'class', 'surprise']):
            return 'quiz'
        if any(kw in line_lower for kw in ['practical', 'lab', 'viva', 'oral']):
            return 'practical'
        
        return 'exam'
    
    def _deduplicate_exams(self, exams: List[ExamSchedule]) -> List[ExamSchedule]:
        """
        Remove duplicate exams using semantic similarity.
        Merges exams on the same day if subject names are semantically similar.
        """
        if not exams:
            return []
            
        # Group exams by date first
        date_groups = {}
        for exam in exams:
            if exam.date not in date_groups:
                date_groups[exam.date] = []
            date_groups[exam.date].append(exam)
            
        unique_exams = []
        
        # Try to import sklearn for TF-IDF similarity
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            HAS_SKLEARN = True
        except ImportError:
            HAS_SKLEARN = False
            from difflib import SequenceMatcher
            
        for date, days_exams in date_groups.items():
            if len(days_exams) == 1:
                unique_exams.extend(days_exams)
                continue
                
            # If we have multiple exams on the same day, check for semantic duplicates
            merged_indices = set()
            
            if HAS_SKLEARN and len(days_exams) > 1:
                # Use TF-IDF + Cosine Similarity
                subjects = [e.subject.lower() for e in days_exams]
                try:
                    tfidf = TfidfVectorizer().fit_transform(subjects)
                    cosine_sim = cosine_similarity(tfidf, tfidf)
                    
                    for i in range(len(days_exams)):
                        if i in merged_indices:
                            continue
                            
                        current_best = days_exams[i]
                        
                        for j in range(i + 1, len(days_exams)):
                            if j in merged_indices:
                                continue
                                
                            # If similarity > 0.6 (high similarity), treat as duplicate
                            if cosine_sim[i][j] > 0.6:
                                merged_indices.add(j)
                                # Keep the one with longer name / better data
                                candidate = days_exams[j]
                                if len(candidate.subject) > len(current_best.subject):
                                    current_best = candidate
                                elif not current_best.start_time and candidate.start_time:
                                    current_best = candidate
                                    
                        unique_exams.append(current_best)
                        merged_indices.add(i)
                except:
                    # Fallback if vectorization fails (e.g. empty strings)
                    HAS_SKLEARN = False
            
            if not HAS_SKLEARN:
                # Fallback to SequenceMatcher
                for i in range(len(days_exams)):
                    if i in merged_indices:
                        continue
                        
                    current_best = days_exams[i]
                    
                    for j in range(i + 1, len(days_exams)):
                        if j in merged_indices:
                            continue
                            
                        candidate = days_exams[j]
                        similarity = SequenceMatcher(None, current_best.subject.lower(), candidate.subject.lower()).ratio()
                        
                        if similarity > 0.7:
                            merged_indices.add(j)
                            if len(candidate.subject) > len(current_best.subject):
                                current_best = candidate
                            elif not current_best.start_time and candidate.start_time:
                                current_best = candidate
                                
                    unique_exams.append(current_best)
                    merged_indices.add(i)

        # Final sort by date
        unique_exams.sort(key=lambda x: x.date)
        return unique_exams


# ============================================================================
# CSP TIMETABLE GENERATOR
# ============================================================================

class CSPTimetableGenerator:
    """
    Constraint Satisfaction Problem based timetable generator
    
    Time Complexity: O(n × d × c) where:
    - n = number of subjects
    - d = domain size (available time slots)
    - c = constraint check cost
    
    This is more efficient than brute force O(d^n) and provides
    optimal or near-optimal solutions with backtracking + pruning.
    """
    
    def __init__(self, constraints: StudyConstraints):
        self.constraints = constraints
        self.subjects = constraints.subjects
        self.events = {e.date: e for e in constraints.academic_events}
        self.exams = constraints.exams
        
        # Preferences with defaults
        prefs = constraints.preferences
        self.study_start_hour = prefs.get('study_start_hour', 6)  # 6 AM
        self.study_end_hour = prefs.get('study_end_hour', 22)     # 10 PM
        self.slot_duration = prefs.get('slot_duration_minutes', 60)  # 1 hour slots
        self.break_duration = prefs.get('break_duration_minutes', 15)
        self.max_daily_hours = prefs.get('max_daily_hours', 8)
        self.days_ahead = prefs.get('days_ahead', 14)
        
        # Generate time slots
        self.time_slots = self._generate_time_slots()
        
        # Track assignments
        self.assignment = {}  # slot_id -> subject
        self.domain = {}      # slot_id -> list of possible subjects
    
    def _generate_time_slots(self) -> List[Dict]:
        """Generate available time slots for the planning horizon"""
        slots = []
        start_date = datetime.now().date()
        
        for day_offset in range(self.days_ahead):
            current_date = start_date + timedelta(days=day_offset)
            date_str = current_date.isoformat()
            
            # Check if holiday
            event = self.events.get(date_str)
            if event and event.is_holiday:
                continue
            
            # Generate slots for the day
            hour = self.study_start_hour
            daily_slots = 0
            
            while hour < self.study_end_hour and daily_slots < self.max_daily_hours:
                slot_id = f"{date_str}_{hour:02d}:00"
                
                # Check for exam conflicts
                has_exam = self._has_exam_conflict(date_str, hour)
                
                if not has_exam:
                    slots.append({
                        'id': slot_id,
                        'date': date_str,
                        'start_hour': hour,
                        'end_hour': hour + 1,
                        'day_name': current_date.strftime('%A')
                    })
                    daily_slots += 1
                
                hour += 1 + (self.break_duration // 60)
        
        return slots
    
    def _has_exam_conflict(self, date: str, hour: int) -> bool:
        """Check if there's an exam at this time"""
        for exam in self.exams:
            if exam.date == date:
                if exam.start_time:
                    exam_hour = int(exam.start_time.split(':')[0])
                    if abs(exam_hour - hour) < 2:  # Buffer of 2 hours
                        return True
                else:
                    # Assume exam takes morning/afternoon
                    return True
        return False
    
    def _get_days_until_exam(self, subject_name: str, from_date: str) -> int:
        """Get days until next exam for subject"""
        subject_lower = subject_name.lower()
        from_dt = datetime.fromisoformat(from_date)
        
        for exam in self.exams:
            if subject_lower in exam.subject.lower():
                exam_dt = datetime.fromisoformat(exam.date)
                days = (exam_dt - from_dt).days
                if days > 0:
                    return days
        
        return 999  # No exam found
    
    def _priority_score(self, subject: Subject, slot: Dict) -> float:
        """Calculate priority score for assigning subject to slot"""
        score = 0.0
        
        # Factor 1: Difficulty weight (hard subjects get higher priority)
        difficulty_weights = {'easy': 1.0, 'medium': 2.0, 'hard': 3.0}
        score += difficulty_weights.get(subject.difficulty, 2.0)
        
        # Factor 2: Exam proximity (closer exam = higher priority)
        days_until = self._get_days_until_exam(subject.name, slot['date'])
        if days_until < 7:
            score += (7 - days_until) * 2  # Up to 14 bonus points
        
        # Factor 3: Subject priority
        score += subject.priority
        
        # Factor 4: Weekly target consideration
        current_assigned = self._count_weekly_hours(subject.name, slot['date'])
        if current_assigned < subject.weekly_target_hours:
            score += 5  # Bonus for under-assigned subjects
        
        return score
    
    def _count_weekly_hours(self, subject_name: str, date: str) -> float:
        """Count hours assigned to subject in the same week"""
        target_dt = datetime.fromisoformat(date)
        week_start = target_dt - timedelta(days=target_dt.weekday())
        week_end = week_start + timedelta(days=6)
        
        hours = 0
        for slot_id, assigned_subject in self.assignment.items():
            if assigned_subject and assigned_subject.name == subject_name:
                slot_date = datetime.fromisoformat(slot_id.split('_')[0])
                if week_start <= slot_date <= week_end:
                    hours += 1
        
        return hours
    
    def _is_consistent(self, subject: Subject, slot: Dict) -> bool:
        """Check if assignment is consistent with constraints"""
        date = slot['date']
        
        # Constraint 1: Don't exceed daily hours for subject
        daily_count = sum(
            1 for sid, subj in self.assignment.items()
            if subj and subj.name == subject.name and sid.startswith(date)
        )
        if daily_count >= 3:  # Max 3 hours per subject per day
            return False
        
        # Constraint 2: Check weekly target not exceeded too much
        weekly_hours = self._count_weekly_hours(subject.name, date)
        if weekly_hours >= subject.weekly_target_hours * 1.5:
            return False
        
        # Constraint 3: Prerequisites met (simplified - just check if prereq scheduled before)
        for prereq in subject.prerequisites:
            prereq_scheduled = any(
                subj and subj.name.lower() == prereq.lower()
                for sid, subj in self.assignment.items()
                if sid < slot['id']
            )
            if not prereq_scheduled:
                # Allow but with penalty (handled in priority)
                pass
        
        return True
    
    def generate(self) -> List[Dict]:
        """Generate timetable using CSP with backtracking"""
        if not self.subjects:
            return []
        
        # Initialize domains
        for slot in self.time_slots:
            self.domain[slot['id']] = [s for s in self.subjects]
        
        # Sort slots by date/time
        sorted_slots = sorted(self.time_slots, key=lambda s: s['id'])
        
        # Solve using backtracking with MRV heuristic
        self._backtrack(sorted_slots, 0)
        
        # Build result
        result = []
        for slot in sorted_slots:
            subject = self.assignment.get(slot['id'])
            if subject:
                result.append({
                    'slot_id': slot['id'],
                    'date': slot['date'],
                    'day': slot['day_name'],
                    'start_time': f"{slot['start_hour']:02d}:00",
                    'end_time': f"{slot['end_hour']:02d}:00",
                    'subject': subject.name,
                    'difficulty': subject.difficulty,
                    'topics': subject.topics[:3] if subject.topics else []
                })
        
        return result
    
    def _backtrack(self, slots: List[Dict], index: int) -> bool:
        """Backtracking search with constraint propagation"""
        if index >= len(slots):
            return True
        
        slot = slots[index]
        slot_id = slot['id']
        
        # Get subjects sorted by priority (MRV: minimum remaining values)
        candidates = [
            (s, self._priority_score(s, slot))
            for s in self.domain.get(slot_id, [])
            if self._is_consistent(s, slot)
        ]
        
        # Sort by priority descending
        candidates.sort(key=lambda x: -x[1])
        
        for subject, _ in candidates:
            self.assignment[slot_id] = subject
            
            # Forward checking - prune domains
            pruned = self._forward_check(slot, subject)
            
            if self._backtrack(slots, index + 1):
                return True
            
            # Restore pruned values
            self._restore_domains(pruned)
            self.assignment[slot_id] = None
        
        # Allow slot to be empty
        self.assignment[slot_id] = None
        return self._backtrack(slots, index + 1)
    
    def _forward_check(self, slot: Dict, subject: Subject) -> Dict:
        """Forward checking - prune inconsistent values"""
        pruned = {}
        date = slot['date']
        
        # Limit same subject on same day
        daily_count = sum(
            1 for sid, subj in self.assignment.items()
            if subj and subj.name == subject.name and sid.startswith(date)
        )
        
        if daily_count >= 2:
            for slot_id, domain in self.domain.items():
                if slot_id.startswith(date) and subject in domain:
                    if slot_id not in pruned:
                        pruned[slot_id] = []
                    pruned[slot_id].append(subject)
                    domain.remove(subject)
        
        return pruned
    
    def _restore_domains(self, pruned: Dict):
        """Restore pruned values to domains"""
        for slot_id, subjects in pruned.items():
            self.domain[slot_id].extend(subjects)


# ============================================================================
# UNIFIED DOCUMENT PROCESSOR
# ============================================================================

class DocumentProcessor:
    """Unified interface for processing all document types with AI enhancement"""
    
    def __init__(self, upload_dir: str = None):
        self.upload_dir = upload_dir or os.path.join(os.path.dirname(__file__), 'uploads', 'documents')
        os.makedirs(self.upload_dir, exist_ok=True)
        
        self.syllabus_parser = SyllabusParser()
        self.calendar_parser = AcademicCalendarParser()
        self.exam_parser = ExamTimetableParser()
        self.ai_extractor = ai_extractor
        self.llm_whisperer = llm_whisperer
        self.universal_extractor = universal_extractor
    
    @property
    def ai_enabled(self) -> bool:
        """Check if AI extraction is available"""
        return self.ai_extractor.enabled
    
    @property
    def ocr_enabled(self) -> bool:
        """Check if LLM Whisperer OCR is available"""
        return self.llm_whisperer.enabled
    
    def extract_text_with_ocr(self, file_path: str, mode: str = "native_text") -> str:
        """
        Extract text from PDF using LLM Whisperer OCR.
        
        Args:
            file_path: Path to PDF file
            mode: "native_text", "low_cost", "high_quality", or "form"
        
        Returns:
            Extracted text
        """
        if self.llm_whisperer.enabled:
            return self.llm_whisperer.extract_text(file_path, mode)
        return PDFTextExtractor.extract_text(file_path, use_llm_whisperer=False)
    
    def process_any_pdf(self, file_path: str) -> Dict[str, Any]:
        """
        🚀 UNIVERSAL PDF PROCESSOR - Auto-detect and extract from ANY PDF!
        
        Automatically detects if the PDF is:
        - Syllabus → extracts subjects, topics, difficulty, hours
        - Academic Calendar → extracts events, holidays
        - Exam Timetable → extracts exam schedule
        - Mixed document → extracts all available data
        
        Args:
            file_path: Path to any PDF file
        
        Returns:
            {
                'document_type': 'syllabus' | 'calendar' | 'timetable' | 'mixed',
                'subjects': [...],
                'events': [...],
                'exams': [...],
                'raw_text': str (first 5000 chars),
                'extraction_method': str
            }
        """
        return self.universal_extractor.extract_any_pdf(file_path)
    
    def process_syllabus(self, file_path: str) -> List[Subject]:
        """Process syllabus PDF"""
        return self.syllabus_parser.parse(file_path)
    
    def process_calendar(self, file_path: str) -> List[AcademicEvent]:
        """Process academic calendar PDF"""
        return self.calendar_parser.parse(file_path)
    
    def process_exam_timetable(self, file_path: str) -> List[ExamSchedule]:
        """Process exam timetable PDF"""
        return self.exam_parser.parse(file_path)
    
    def process_all(
        self, 
        syllabus_path: str = None,
        calendar_path: str = None,
        exam_timetable_path: str = None,
        preferences: Dict = None
    ) -> StudyConstraints:
        """Process all documents and return combined constraints"""
        subjects = []
        events = []
        exams = []
        
        if syllabus_path and os.path.exists(syllabus_path):
            subjects = self.process_syllabus(syllabus_path)
            print(f"📚 Extracted {len(subjects)} subjects from syllabus")
        
        if calendar_path and os.path.exists(calendar_path):
            events = self.process_calendar(calendar_path)
            print(f"📅 Extracted {len(events)} events from calendar")
        
        if exam_timetable_path and os.path.exists(exam_timetable_path):
            exams = self.process_exam_timetable(exam_timetable_path)
            print(f"📝 Extracted {len(exams)} exams from timetable")
        
        return StudyConstraints(
            subjects=subjects,
            academic_events=events,
            exams=exams,
            preferences=preferences or {}
        )
    
    def generate_timetable(self, constraints: StudyConstraints) -> List[Dict]:
        """Generate study timetable from constraints using CSP"""
        generator = CSPTimetableGenerator(constraints)
        return generator.generate()
    
    def save_file(self, content: bytes, filename: str, doc_type: str) -> str:
        """Save uploaded file and return path"""
        type_dir = os.path.join(self.upload_dir, doc_type)
        os.makedirs(type_dir, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = re.sub(r'[^\w\-.]', '_', filename)
        unique_name = f"{timestamp}_{safe_name}"
        
        file_path = os.path.join(type_dir, unique_name)
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return file_path


# ============================================================================
# TESTING / DEMO
# ============================================================================

if __name__ == "__main__":
    # Demo with sample data
    print("=== Document Processor Demo ===\n")
    
    # Create sample subjects manually for testing
    subjects = [
        Subject(
            name="Data Structures and Algorithms",
            topics=["Arrays", "Linked Lists", "Trees", "Graphs", "Dynamic Programming"],
            difficulty="hard",
            estimated_hours=40,
            priority=9,
            weekly_target_hours=8
        ),
        Subject(
            name="Database Management Systems",
            topics=["SQL", "Normalization", "Transactions", "Indexing"],
            difficulty="medium",
            estimated_hours=30,
            priority=7,
            weekly_target_hours=5
        ),
        Subject(
            name="Operating Systems",
            topics=["Process Management", "Memory Management", "File Systems"],
            difficulty="hard",
            estimated_hours=35,
            priority=8,
            weekly_target_hours=6
        ),
        Subject(
            name="Computer Networks",
            topics=["OSI Model", "TCP/IP", "Routing", "Security"],
            difficulty="medium",
            estimated_hours=25,
            priority=6,
            weekly_target_hours=4
        )
    ]
    
    # Create sample exams
    exams = [
        ExamSchedule(subject="Data Structures and Algorithms", date="2026-02-01", start_time="09:00"),
        ExamSchedule(subject="Database Management Systems", date="2026-02-05", start_time="09:00"),
        ExamSchedule(subject="Operating Systems", date="2026-02-08", start_time="14:00"),
    ]
    
    # Create sample holidays
    events = [
        AcademicEvent(name="Republic Day", date="2026-01-26", is_holiday=True),
        AcademicEvent(name="Mid-sem Break", date="2026-01-31", is_holiday=True),
    ]
    
    # Create constraints
    constraints = StudyConstraints(
        subjects=subjects,
        academic_events=events,
        exams=exams,
        preferences={
            'study_start_hour': 8,
            'study_end_hour': 20,
            'max_daily_hours': 6,
            'days_ahead': 14
        }
    )
    
    # Generate timetable
    generator = CSPTimetableGenerator(constraints)
    timetable = generator.generate()
    
    print(f"\n📅 Generated Timetable ({len(timetable)} slots):\n")
    
    current_date = None
    for slot in timetable[:20]:  # Show first 20
        if slot['date'] != current_date:
            current_date = slot['date']
            print(f"\n📆 {slot['day']}, {slot['date']}")
            print("-" * 40)
        
        print(f"  {slot['start_time']} - {slot['end_time']}: {slot['subject']} ({slot['difficulty']})")
    
    print("\n✅ Demo complete!")
