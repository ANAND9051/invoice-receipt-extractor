import sys, os
sys.path.insert(0, os.path.abspath("."))
import time
import json
import re
from llama_cpp import Llama
from extractor.schemas import ExtractedInvoiceReceipt
from extractor.validator import validate_extraction

t0 = time.time()
llm = Llama(
    model_path="models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    n_ctx=2048,
    n_batch=512,
    n_threads=4,
    verbose=False
)
print(f"Model load: {time.time() - t0:.2f}s", flush=True)

sample_text = """
BISTRO DELIGHT
123 Main St, New York, NY
Tel: (555) 123-4567
Date: 2024-04-15  Invoice #: INV-2024-001

Description          Qty    Price    Total
Truffle Burger        2     18.50    37.00
Craft IPA             2      7.00    14.00
Tiramisu              1      8.50     8.50

Subtotal:                            59.50
Tax (8.875%):                         5.28
Tip:                                 10.00
Total:                              $74.78
Payment: Visa ending in 4321
"""

system_prompt = """You are a financial document parser. Extract receipt/invoice data from the OCR text into clean JSON.
Only include fields present in the text (omit null fields):
- document_type: "receipt" or "invoice"
- invoice_number
- invoice_date: "YYYY-MM-DD"
- vendor: {"name": "...", "address": "...", "phone": "..."}
- line_items: [{"description": "...", "quantity": 1.0, "unit_price": 0.0, "total_price": 0.0}]
- subtotal: float
- total_tax: float
- tip: float
- total_amount: float
- currency: "USD"
- payment: {"method": "...", "status": "paid"}

Output strictly a JSON object starting with { and ending with }."""

user_prompt = f"OCR Text:\n{sample_text.strip()}\n\nReturn JSON:"

chat_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n{{"

t1 = time.time()
res = llm(
    chat_prompt,
    max_tokens=400,
    stop=["<|im_end|>", "```"],
    temperature=0.1
)
t2 = time.time()
raw = "{" + res["choices"][0]["text"].strip()
# Clean markdown if any
raw = re.sub(r"^```json\s*", "", raw)
raw = re.sub(r"\s*```$", "", raw)
# Find the JSON object boundaries
start_idx = raw.find("{")
end_idx = raw.rfind("}")
if start_idx != -1 and end_idx != -1:
    clean_json = raw[start_idx:end_idx+1]
else:
    clean_json = raw

tokens = res["usage"]["completion_tokens"]
duration = t2 - t1
print(f"Extraction took {duration:.2f}s ({tokens} tokens, {tokens/duration:.2f} tok/s)", flush=True)

data = json.loads(clean_json)
doc = ExtractedInvoiceReceipt(**data)
val = validate_extraction(doc)

print(f"Vendor: {doc.vendor.name if doc.vendor else None}", flush=True)
print(f"Total: {doc.total_amount}", flush=True)
print(f"Line items ({len(doc.line_items)}):", [(item.description, item.total_price) for item in doc.line_items], flush=True)
print(f"Validation Score: {val.quality_score}/100, Math consistent: {val.math_consistent}", flush=True)
