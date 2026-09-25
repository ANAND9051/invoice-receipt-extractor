"""
Local Offline Llama.cpp Extractor with Optimized Direct Prompting & Robust json-repair.
Eliminates GBNF grammar evaluation overhead for 10x faster local inference on CPU.
"""

import os
import json
import logging
import re
import time
from typing import Optional, Tuple, Dict, Any, Callable
from huggingface_hub import hf_hub_download
import llama_cpp
from llama_cpp import Llama
import json_repair

from extractor.schemas import ExtractedInvoiceReceipt
from extractor.validator import validate_extraction, ValidationResult
from extractor.local_ocr import extract_document_text
from extractor.categorizer import apply_auto_categorization

logger = logging.getLogger(__name__)

# Pre-defined lightweight models optimized for 8 GB RAM / CPU systems
SUPPORTED_LOCAL_MODELS = {
    "Qwen2.5-0.5B-Instruct (⚡ Ultra-Fast, ~0.4 GB - Recommended for CPU)": {
        "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "size_mb": 398,
    },
    "Qwen2.5-1.5B-Instruct (🎯 High Accuracy, ~1.0 GB)": {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_mb": 986,
    },
    "Llama-3.2-1B-Instruct (Lightweight, ~0.8 GB)": {
        "repo_id": "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "filename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "size_mb": 810,
    },
    "Qwen2.5-3B-Instruct (Deep Extraction, ~2.0 GB)": {
        "repo_id": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_mb": 1930,
    },
}

LOCAL_SYSTEM_PROMPT = """You are a financial document parser. Extract receipt/invoice data from OCR text into a compact JSON object.
Omit null or empty fields. Use these exact keys:
- document_type: "Receipt" or "Invoice"
- invoice_number: string or null
- issue_date: "YYYY-MM-DD"
- vendor: {"name": "...", "address": "...", "phone": "...", "tax_id": "..."}
- customer: {"name": "...", "address": "..."}
- line_items: [{"description": "...", "quantity": 1.0, "unit_price": 0.0, "total_price": 0.0}]
- subtotal: float
- taxes: [{"name": "...", "rate_percentage": 0.0, "amount": 0.0}]
- tax_total: float
- tip_or_gratuity: float
- discount_total: float
- total_amount: float
- currency: "INR" or "USD"
- payment: {"payment_method": "...", "payment_status": "Paid", "card_last_four": "..."}

Rules:
1. Do not invent items or amounts not present in text.
2. Return strictly valid JSON. Avoid unescaped double quotes inside description text."""

# Singleton cache for the loaded Llama model to prevent reloading weights on each query
_cached_llama_model: Optional[Llama] = None
_cached_cache_key: Optional[str] = None


def download_local_model(model_key: str, models_dir: str = "models", progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
    """Downloads a GGUF model from Hugging Face Hub if not already present."""
    if model_key not in SUPPORTED_LOCAL_MODELS:
        raise ValueError(f"Unknown model key: {model_key}")

    os.makedirs(models_dir, exist_ok=True)
    meta = SUPPORTED_LOCAL_MODELS[model_key]
    dest_path = os.path.join(models_dir, meta["filename"])

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 50 * 1024 * 1024:
        logger.info(f"Model already downloaded at {dest_path}")
        return dest_path

    logger.info(f"Downloading {meta['filename']} from {meta['repo_id']}...")
    downloaded_path = hf_hub_download(
        repo_id=meta["repo_id"],
        filename=meta["filename"],
        local_dir=models_dir,
    )
    return downloaded_path


def _clean_and_repair_json(raw_text: str) -> Dict[str, Any]:
    """
    Cleans markdown formatting and repairs malformed/truncated JSON using json_repair.
    Guarantees returning a dictionary without crashing.
    """
    text = raw_text.strip()
    # Strip markdown block wrappers if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    # Locate outermost curly braces
    start_idx = text.find("{")
    end_idx = text.rfind("}")

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = text[start_idx:end_idx + 1]
    elif start_idx != -1:
        json_str = text[start_idx:]
    else:
        json_str = text

    # Primary parse attempt using json_repair (handles unescaped quotes, missing commas, truncations)
    try:
        parsed = json_repair.loads(json_str)
        if isinstance(parsed, dict):
            return parsed
        elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
            return parsed[0]
    except Exception as e:
        logger.warning(f"json_repair.loads failed: {e}. Trying repair_json fallback...")

    # Secondary attempt using repair_json string fixing
    try:
        fixed_str = json_repair.repair_json(json_str)
        parsed = json.loads(fixed_str)
        if isinstance(parsed, dict):
            return parsed
        elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
            return parsed[0]
    except Exception as e:
        logger.warning(f"json_repair.repair_json failed: {e}. Trying regex cleanup...")

    # Tertiary attempt: standard regex repair
    try:
        cleaned = re.sub(r",\s*([\]}])", r"\1", json_str)
        return json.loads(cleaned)
    except Exception as e:
        logger.error(f"All JSON repair attempts exhausted: {e}")
        return {"notes_or_terms": f"OCR text partially parsed: {text[:200]}"}


def _normalize_extracted_dict(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Defensively normalizes field aliases and types into the ExtractedInvoiceReceipt schema."""
    if not isinstance(parsed, dict):
        return {}

    # Date alias
    if "invoice_date" in parsed and "issue_date" not in parsed:
        parsed["issue_date"] = parsed.pop("invoice_date")

    # Taxes alias
    if "tax_items" in parsed and "taxes" not in parsed:
        parsed["taxes"] = parsed.pop("tax_items")
    if "total_tax" in parsed and "tax_total" not in parsed:
        parsed["tax_total"] = parsed.pop("total_tax")

    # If taxes is a single number instead of a list:
    if "taxes" in parsed and isinstance(parsed["taxes"], (int, float)):
        if "tax_total" not in parsed or not parsed["tax_total"]:
            parsed["tax_total"] = float(parsed["taxes"])
        parsed["taxes"] = [{"name": "Tax", "amount": float(parsed["taxes"])}]
    elif "taxes" in parsed and isinstance(parsed["taxes"], list):
        clean_taxes = []
        for t in parsed["taxes"]:
            if isinstance(t, dict):
                clean_taxes.append(t)
        parsed["taxes"] = clean_taxes

    # Tip & discount aliases
    if "tip" in parsed and "tip_or_gratuity" not in parsed:
        parsed["tip_or_gratuity"] = parsed.pop("tip")
    if "discount" in parsed and "discount_total" not in parsed:
        parsed["discount_total"] = parsed.pop("discount")
    if "shipping" in parsed and "shipping_fee" not in parsed:
        parsed["shipping_fee"] = parsed.pop("shipping")

    # Vendor & Customer string normalization
    if "vendor" in parsed and isinstance(parsed["vendor"], str):
        parsed["vendor"] = {"name": parsed["vendor"]}
    elif "vendor" not in parsed or not isinstance(parsed["vendor"], dict):
        parsed["vendor"] = {}

    if "customer" in parsed and isinstance(parsed["customer"], str):
        parsed["customer"] = {"name": parsed["customer"]}
    elif "customer" not in parsed or not isinstance(parsed["customer"], dict):
        parsed["customer"] = {}

    # Payment aliases & string normalization
    if "payment" in parsed:
        if isinstance(parsed["payment"], str):
            parsed["payment"] = {"payment_method": parsed["payment"], "payment_status": "Paid"}
        elif isinstance(parsed["payment"], dict):
            p = parsed["payment"]
            if "method" in p and "payment_method" not in p:
                p["payment_method"] = p.pop("method")
            if "status" in p and "payment_status" not in p:
                p["payment_status"] = p.pop("status")
            if "card_last4" in p and "card_last_four" not in p:
                p["card_last_four"] = p.pop("card_last4")
    else:
        parsed["payment"] = {}

    # Monetary fields sanitization (stripping ₹, $, commas, etc.)
    for money_field in [
        "total_amount", "subtotal", "tax_total", "tip_or_gratuity",
        "discount_total", "shipping_fee", "amount_paid", "balance_due"
    ]:
        if money_field in parsed and parsed[money_field] is not None:
            if isinstance(parsed[money_field], str):
                clean_num = re.sub(r"[^\d.-]", "", parsed[money_field])
                try:
                    parsed[money_field] = float(clean_num) if clean_num else None
                except ValueError:
                    parsed[money_field] = None

    # Line items sanitization
    if "line_items" in parsed and isinstance(parsed["line_items"], list):
        cleaned_items = []
        for it in parsed["line_items"]:
            if isinstance(it, str):
                cleaned_items.append({"description": it, "quantity": 1.0})
            elif isinstance(it, dict):
                # Ensure description is present
                desc = it.get("description") or it.get("item") or it.get("name") or "Item"
                it["description"] = str(desc)

                for num_field in ["quantity", "unit_price", "total_price"]:
                    if num_field in it and it[num_field] is not None:
                        if isinstance(it[num_field], str):
                            clean_n = re.sub(r"[^\d.-]", "", str(it[num_field]))
                            try:
                                it[num_field] = float(clean_n) if clean_n else None
                            except ValueError:
                                it[num_field] = None
                cleaned_items.append(it)
        parsed["line_items"] = cleaned_items
    else:
        parsed["line_items"] = []

    return parsed


class LlamaCppExtractor:
    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int = 4):
        global _cached_llama_model, _cached_cache_key
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        cache_key = f"{model_path}_{n_threads}_{n_ctx}"

        # Reuse cached model in memory to avoid slow disk reloads
        if _cached_llama_model is not None and _cached_cache_key == cache_key:
            self.llm = _cached_llama_model
        else:
            logger.info(f"Loading Llama model from {model_path} with {n_threads} threads, context {n_ctx}...")
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_batch=512,
                n_threads=self.n_threads,
                verbose=False,
            )
            _cached_llama_model = self.llm
            _cached_cache_key = cache_key

    def extract_from_text(
        self,
        ocr_text: str,
        custom_instructions: Optional[str] = None
    ) -> Tuple[ExtractedInvoiceReceipt, ValidationResult]:
        """Extracts structured invoice data from OCR text using fast unconstrained ChatML generation & json-repair."""
        sys_prompt = LOCAL_SYSTEM_PROMPT
        if custom_instructions and custom_instructions.strip():
            sys_prompt += f"\nAdditional Instructions: {custom_instructions.strip()}"

        user_content = f"OCR Document Text:\n---\n{ocr_text.strip()}\n---\nExtract JSON:"

        # Format prompt with assistant prefill to eliminate preamble latency
        is_qwen = "qwen" in self.model_path.lower()
        if is_qwen:
            formatted_prompt = f"<|im_start|>system\n{sys_prompt}<|im_end|>\n<|im_start|>user\n{user_content}<|im_end|>\n<|im_start|>assistant\n{{"
            stop_tokens = ["<|im_end|>", "```"]
        else:
            formatted_prompt = f"<|start_header_id|>system<|end_header_id|>\n\n{sys_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{user_content}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n{{"
            stop_tokens = ["<|eot_id|>", "```"]

        t0 = time.time()
        # Allocate up to 1024 tokens for long receipts with many items
        res = self.llm(
            formatted_prompt,
            max_tokens=1024,
            stop=stop_tokens,
            temperature=0.1,
        )
        t_gen = time.time() - t0

        raw_content = "{" + res["choices"][0]["text"].strip()
        tokens_used = res["usage"]["completion_tokens"]
        logger.info(f"Local LLM generated {tokens_used} tokens in {t_gen:.2f}s ({tokens_used / max(0.01, t_gen):.1f} tok/s)")

        # Parse & repair JSON with json-repair
        parsed_data = _clean_and_repair_json(raw_content)
        normalized_data = _normalize_extracted_dict(parsed_data)

        # Defensively instantiate ExtractedInvoiceReceipt
        try:
            extracted_obj = ExtractedInvoiceReceipt(**normalized_data)
        except Exception as e:
            logger.warning(f"ExtractedInvoiceReceipt strict validation failed: {e}. Building with fallback...")
            # Fallback: construct empty schema and set known valid keys
            extracted_obj = ExtractedInvoiceReceipt()
            for k, v in normalized_data.items():
                if hasattr(extracted_obj, k):
                    try:
                        setattr(extracted_obj, k, v)
                    except Exception:
                        pass

        # Auto-classify product categories (Vegetables, Fruits, Dairy, etc.)
        apply_auto_categorization(extracted_obj)

        # Validate extraction quality & math consistency
        validation_result = validate_extraction(extracted_obj)
        if extracted_obj.confidence_score is None:
            extracted_obj.confidence_score = round(validation_result.quality_score / 100.0, 2)

        return extracted_obj, validation_result

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        mime_type: str,
        custom_instructions: Optional[str] = None
    ) -> Tuple[ExtractedInvoiceReceipt, ValidationResult, str]:
        """Runs OCR first, then parses OCR text with Llama."""
        ocr_text = extract_document_text(file_bytes, mime_type)
        if not ocr_text.strip():
            raise ValueError("OCR failed to detect any text in the document.")

        extracted_obj, validation_result = self.extract_from_text(
            ocr_text=ocr_text,
            custom_instructions=custom_instructions
        )
        return extracted_obj, validation_result, ocr_text
