"""
Local OCR Engine using RapidOCR and pypdf for local, offline text extraction.
"""

import io
import logging
from typing import List, Tuple, Optional
from PIL import Image
import pypdf
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR

logger = logging.getLogger(__name__)

# Global singleton OCR engine to avoid reloading ONNX models on every call
_ocr_engine: Optional[RapidOCR] = None


def get_ocr_engine() -> RapidOCR:
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = RapidOCR()
    return _ocr_engine


def extract_text_from_image(image: Image.Image) -> str:
    """Extracts text from a PIL Image using RapidOCR."""
    engine = get_ocr_engine()
    # Convert image to RGB if needed
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    result, _ = engine(image)
    if not result:
        return ""
    
    lines = [box[1] for box in result if box and len(box) > 1]
    return "\n".join(lines)


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extracts text from PDF bytes:
    1. First checks for native embedded digital text (via pypdf).
    2. If no text or scanned document, renders pages via pypdfium2 and uses RapidOCR.
    """
    extracted_text = []
    
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                extracted_text.append(text.strip())
    except Exception as e:
        logger.warning(f"Native PDF text extraction failed: {e}")

    # If native text extraction yielded substantial text, return it
    total_native_text = "\n\n".join(extracted_text)
    if len(total_native_text.strip()) > 100:
        return total_native_text

    # Otherwise fallback to rendering pages and running OCR
    logger.info("Falling back to OCR for scanned PDF...")
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        ocr_pages_text = []
        for i, page in enumerate(pdf):
            img = page.render(scale=2.0).to_pil()
            page_text = extract_text_from_image(img)
            if page_text:
                ocr_pages_text.append(f"--- PAGE {i+1} ---\n{page_text}")
        return "\n\n".join(ocr_pages_text)
    except Exception as e:
        logger.error(f"OCR on PDF failed: {e}")
        return ""


def extract_document_text(file_bytes: bytes, mime_type: str) -> str:
    """General dispatcher to extract text from image or PDF bytes."""
    if mime_type == "application/pdf":
        return extract_text_from_pdf_bytes(file_bytes)
    else:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            return extract_text_from_image(img)
        except Exception as e:
            logger.error(f"Image text extraction failed: {e}")
            return ""
