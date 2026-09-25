import sys, os
sys.path.insert(0, os.path.abspath("."))
import time
import json
import re
from llama_cpp import Llama
from extractor.schemas import ExtractedInvoiceReceipt
from extractor.validator import validate_extraction
from extractor.local_ocr import extract_document_text

sample_image_path = "samples/sample_restaurant_receipt.png"
with open(sample_image_path, "rb") as f:
    img_bytes = f.read()

t_ocr_0 = time.time()
ocr_text = extract_document_text(img_bytes, "image/png")
t_ocr_1 = time.time()
print(f"OCR completed in {t_ocr_1 - t_ocr_0:.2f}s")
print(f"OCR text snippet:\n{ocr_text[:200]}...\n")

# Test fast ChatML inference
llm = Llama(
    model_path="models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    n_ctx=2048,
    n_batch=512,
    n_threads=4,
    verbose=False
)

system_prompt = """You are a financial document parser. Extract receipt or invoice data from OCR text into valid JSON.
Omit null or absent fields. Use these exact field names:
- document_type: "Receipt" or "Invoice"
- invoice_number: string or null
- issue_date: "YYYY-MM-DD"
- vendor: {"name": "...", "address": "...", "phone": "..."}
- customer: {"name": "..."}
- line_items: [{"description": "...", "quantity": 1.0, "unit_price": 0.0, "total_price": 0.0}]
- subtotal: float
- taxes: [{"name": "...", "rate_percentage": 0.0, "amount": 0.0}]
- tax_total: float
- tip_or_gratuity: float
- discount_total: float
- total_amount: float
- currency: "USD"
- payment: {"payment_method": "...", "payment_status": "Paid", "card_last_four": "..."}

Return strictly a JSON object."""

user_prompt = f"OCR Document Text:\n---\n{ocr_text.strip()}\n---\nExtract JSON:"

chat_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n{{"

t0 = time.time()
res = llm(
    chat_prompt,
    max_tokens=450,
    stop=["<|im_end|>", "```"],
    temperature=0.1
)
t1 = time.time()
toks = res["usage"]["completion_tokens"]
print(f"LLM Generation completed in {t1 - t0:.2f}s ({toks} tokens, {toks/(t1-t0):.2f} tok/s)")

raw = "{" + res["choices"][0]["text"].strip()
start_idx = raw.find("{")
end_idx = raw.rfind("}")
if start_idx != -1 and end_idx != -1:
    clean_json = raw[start_idx:end_idx+1]
else:
    clean_json = raw

parsed = json.loads(clean_json)

# Normalize field names if model used alternate conventions
if "invoice_date" in parsed and "issue_date" not in parsed:
    parsed["issue_date"] = parsed.pop("invoice_date")
if "tax_items" in parsed and "taxes" not in parsed:
    parsed["taxes"] = parsed.pop("tax_items")
if "total_tax" in parsed and "tax_total" not in parsed:
    parsed["tax_total"] = parsed.pop("total_tax")
if "tip" in parsed and "tip_or_gratuity" not in parsed:
    parsed["tip_or_gratuity"] = parsed.pop("tip")
if "discount" in parsed and "discount_total" not in parsed:
    parsed["discount_total"] = parsed.pop("discount")

# Normalize payment
if "payment" in parsed and isinstance(parsed["payment"], dict):
    p = parsed["payment"]
    if "method" in p and "payment_method" not in p:
        p["payment_method"] = p.pop("method")
    if "status" in p and "payment_status" not in p:
        p["payment_status"] = p.pop("status")

doc = ExtractedInvoiceReceipt(**parsed)
val = validate_extraction(doc)

print("\n--- EXTRACTION SUCCESS ---")
print(f"Document Type: {doc.document_type}")
print(f"Vendor: {doc.vendor.name if doc.vendor else 'N/A'}")
print(f"Date: {doc.issue_date}")
print(f"Total Amount: {doc.currency or '$'} {doc.total_amount}")
print(f"Line items ({len(doc.line_items)}):")
for it in doc.line_items:
    print(f"  - {it.description}: qty {it.quantity} @ {it.unit_price} = {it.total_price}")
print(f"Quality Score: {val.quality_score}/100, Valid: {val.is_valid}")
