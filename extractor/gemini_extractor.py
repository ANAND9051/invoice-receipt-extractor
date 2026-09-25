"""
Gemini Multimodal Extractor for Receipts and Invoices using google-genai SDK.
Full first-class support for Gemini 2.5 Flash, Gemini 2.0 Flash, with automatic 503 retry and resilient fallback.
"""

import json
import logging
import re
import io
import time
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image
import httpx
from google import genai
from google.genai import types, errors
import json_repair

from extractor.schemas import ExtractedInvoiceReceipt
from extractor.validator import validate_extraction, ValidationResult
from extractor.categorizer import apply_auto_categorization

logger = logging.getLogger(__name__)

# Valid official Gemini models in Google AI Studio
VALID_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro",
]

SYSTEM_PROMPT = """You are an expert Document AI and financial data extraction assistant.
Your task is to analyze the provided document (receipt, invoice, bill, or financial statement) and extract comprehensive, structured information with extreme accuracy.

Key Extraction Instructions:
1. Document Type: Classify whether this is an Invoice, Receipt, Tax Invoice, Utility Bill, Credit Note, or Expense Voucher.
2. Vendor / Merchant:
   - Identify the primary business or store issuing the bill.
   - Look for address, phone, email, website, and tax registration (VAT/GST/EIN/RFC/CIF) numbers.
3. Customer / Buyer:
   - Identify billed customer, company name, address, and customer tax ID if present.
4. Line Items:
   - Extract every single purchased item or service row.
   - Parse quantity, unit of measure, unit price, discounts, tax rates, and total line price.
   - If quantity or unit price is missing, infer logically (e.g. qty=1.0) only if unambiguous.
5. Financial Totals:
   - Extract Subtotal (pre-tax amount).
   - Itemize all taxes (e.g. VAT 20%, Sales Tax 8.25%, GST 18%, etc.) with rates and amounts.
   - Extract discount totals, shipping fees, tips/gratuity, and the final Total Amount.
   - All monetary amounts should be pure numbers (floats) without currency symbols.
6. Dates:
   - Standardize dates into ISO format (YYYY-MM-DD) whenever possible.
7. Currency:
   - Identify the 3-letter currency code (USD, EUR, GBP, INR, CAD, AUD, JPY, etc.) and currency symbol.
8. Payment:
   - Identify payment method (Cash, UPI, Visa, Mastercard, Wire, etc.), status (Paid, Due), and last 4 card digits if visible.
9. Accuracy:
   - Never invent or hallucinate line items or numbers. If a field is not visible in the document, leave it as null.
"""


def create_genai_client(api_key: str) -> genai.Client:
    """
    Creates a robust genai.Client configured with write=None timeout
    to prevent SSL socket write timeouts on image uploads.
    """
    robust_httpx = httpx.Client(
        timeout=httpx.Timeout(120.0, connect=30.0, read=120.0, write=None),
        follow_redirects=True,
    )
    return genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(httpx_client=robust_httpx)
    )


def normalize_model_name(model_name: str) -> str:
    """Returns the requested model name, defaulting to gemini-2.5-flash."""
    cleaned = model_name.strip()
    return cleaned if cleaned else "gemini-2.5-flash"


def test_api_key_validity(api_key: str) -> Tuple[bool, str, List[str]]:
    """Tests if a Gemini API key is valid using available flash models."""
    if not api_key or len(api_key.strip()) < 10:
        return False, "API key is empty or too short.", []
    try:
        client = create_genai_client(api_key)
        # Probe with gemini-2.5-flash first, falling back to gemini-2.0-flash if temporary 503 occurs
        for test_model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
            try:
                response = client.models.generate_content(
                    model=test_model,
                    contents="hello",
                )
                if response and response.text:
                    return True, f"API Key verified active (via {test_model})!", VALID_GEMINI_MODELS
            except errors.APIError as e:
                if e.code in [503, 429] or "high demand" in str(e).lower():
                    logger.warning(f"Key test probe on {test_model} got {e.code}, trying fallback test model...")
                    continue
                raise e

        return True, "API Key format verified active.", VALID_GEMINI_MODELS

    except errors.APIError as e:
        err_str = str(e).lower()
        if e.code == 400 or "not valid" in err_str:
            return False, "API key is not valid. Please double-check your key in Google AI Studio.", []
        elif e.code == 404 or "not found" in err_str:
            return False, f"Model error (404): {e.message}", []
        elif e.code == 429:
            return False, "Rate limit reached or quota exhausted for this API key.", []
        return False, f"Google API Error ({e.code}): {e.message}", []
    except Exception as e:
        return False, f"Connection error: {str(e)}", []


class ReceiptExtractor:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key.strip()
        self.requested_model = normalize_model_name(model_name)
        self.model_name = self.requested_model
        self.client = create_genai_client(self.api_key)

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        mime_type: str,
        custom_instructions: Optional[str] = None
    ) -> Tuple[ExtractedInvoiceReceipt, ValidationResult]:
        """
        Extracts structured data from image or PDF bytes with automatic 503 retry and resilient fallback.
        """
        # Optimize image size and format to ensure fast transmission without SSL write stalls
        processed_bytes = file_bytes
        processed_mime = mime_type

        if mime_type.startswith("image/"):
            try:
                img = Image.open(io.BytesIO(file_bytes))
                if img.mode != "RGB":
                    img = img.convert("RGB")

                # Scale to max 1600px on the longest side (optimal resolution for Gemini Vision)
                max_dim = 1600
                if max(img.width, img.height) > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85, optimize=True)
                processed_bytes = buf.getvalue()
                processed_mime = "image/jpeg"
            except Exception as img_err:
                logger.warning(f"Image preprocessing note: {img_err}")

        # Build prompt
        prompt = SYSTEM_PROMPT
        if custom_instructions and custom_instructions.strip():
            prompt += f"\n\nAdditional User Guidance:\n{custom_instructions.strip()}"

        prompt += "\nExtract the receipt/invoice data accurately into the structured schema."

        # Prepare multimodal document part
        file_part = types.Part.from_bytes(data=processed_bytes, mime_type=processed_mime)

        # Fallback chain prioritizing requested model then fast alternatives
        models_to_try = [self.requested_model]
        for fallback in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash", "gemini-2.5-pro"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        raw_data = None
        last_api_error = None

        for current_model in models_to_try:
            try:
                logger.info(f"Attempting extraction with model: {current_model}")
                response = self.client.models.generate_content(
                    model=current_model,
                    contents=[file_part, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExtractedInvoiceReceipt,
                        temperature=0.1,
                    ),
                )
                response_text = response.text or "{}"
                try:
                    raw_data = json.loads(response_text)
                except Exception:
                    raw_data = json_repair.loads(response_text)

                self.model_name = current_model  # Record successful model
                break

            except errors.APIError as api_err:
                err_msg = api_err.message or str(api_err)
                err_lower = err_msg.lower()
                last_api_error = api_err

                # Non-recoverable: invalid key
                if api_err.code == 400 or "not valid" in err_lower or "api_key" in err_lower:
                    raise ValueError("Google Gemini API key is invalid. Please check your key in Google AI Studio.") from api_err

                # 503 (High Demand / Server Spike) or 429 (Rate limit) or 500/504
                if api_err.code in [503, 429, 500, 504] or "high demand" in err_lower or "overloaded" in err_lower:
                    logger.warning(f"Model '{current_model}' busy ({api_err.code}: {err_msg}). Retrying once after 1.5s...")
                    time.sleep(1.5)
                    try:
                        response = self.client.models.generate_content(
                            model=current_model,
                            contents=[file_part, prompt],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=ExtractedInvoiceReceipt,
                                temperature=0.1,
                            ),
                        )
                        response_text = response.text or "{}"
                        raw_data = json_repair.loads(response_text)
                        self.model_name = current_model
                        break
                    except Exception as retry_err:
                        logger.warning(f"Retry on '{current_model}' also unavailable: {retry_err}. Automatically switching to fallback model...")
                        last_api_error = retry_err
                        continue  # Move immediately to next model in fallback list!

                elif api_err.code == 404 or "not found" in err_lower:
                    logger.warning(f"Model '{current_model}' returned 404. Trying next fallback...")
                    continue
                else:
                    logger.warning(f"Model '{current_model}' error ({api_err.code}): {err_msg}. Trying fallback...")
                    continue

            except (json.JSONDecodeError, Exception) as parse_err:
                logger.warning(f"Structured schema call note on {current_model} ({parse_err}). Trying fallback prompt extraction...")
                try:
                    fallback_prompt = prompt + "\nRespond with strictly valid JSON matching the invoice schema."
                    response = self.client.models.generate_content(
                        model=current_model,
                        contents=[file_part, fallback_prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1,
                        ),
                    )
                    raw_text = response.text or "{}"
                    clean_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
                    clean_text = re.sub(r"\s*```$", "", clean_text)
                    raw_data = json_repair.loads(clean_text)
                    self.model_name = current_model
                    break
                except Exception as final_err:
                    logger.warning(f"Fallback JSON parsing also failed on {current_model}: {final_err}")
                    last_api_error = final_err
                    continue

        if raw_data is None:
            if last_api_error:
                raise ValueError(f"Google Gemini API error: {last_api_error}")
            raise ValueError("Extraction failed: could not parse document into structured data.")

        if not isinstance(raw_data, dict):
            if isinstance(raw_data, list) and len(raw_data) > 0 and isinstance(raw_data[0], dict):
                raw_data = raw_data[0]
            else:
                raw_data = {}

        try:
            extracted_obj = ExtractedInvoiceReceipt(**raw_data)
        except Exception as e:
            logger.warning(f"Schema instantiation note: {e}. Building with fallback...")
            extracted_obj = ExtractedInvoiceReceipt()
            for k, v in raw_data.items():
                if hasattr(extracted_obj, k):
                    try:
                        setattr(extracted_obj, k, v)
                    except Exception:
                        pass

        # Automatically classify line item product groups (Vegetables, Fruits, Dairy, etc.)
        apply_auto_categorization(extracted_obj)

        # Run verification & math checks
        validation_result = validate_extraction(extracted_obj)
        
        # Attach confidence if not populated by model
        if extracted_obj.confidence_score is None:
            extracted_obj.confidence_score = round(validation_result.quality_score / 100.0, 2)

        return extracted_obj, validation_result
