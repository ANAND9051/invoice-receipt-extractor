import sys, os
sys.path.insert(0, os.path.abspath("."))
import time
import json
import re
from llama_cpp import Llama
from extractor.schemas import ExtractedInvoiceReceipt
from extractor.validator import validate_extraction

ocr_text = """BISTRO DELIGHT
142 Market Street Suite 4
San Francisco, CA94105
Tel: (415) 555-0199
Tax ID: US-8829104-SF
Receipt #: REC-2026-9041
Date: 2026-09-24 19:42
Server: Sarah M. (Table 12)
Order Type: Dine-In
QTY ITEM
AMOUNT
2 Artisan Truffle Burger
$37.00
2 x $18.50
1  Crispy Rosemary Fries
$7.50
1 x $7.50
2 Sparkling San Pellegrino
$8.00
2 x $4.00
1  Warm Molten Lava Cake
$9.50
1 x $9.50
Subtotal:
$62.00
Sales Tax (8.5%):
$5.27
Tip/Gratuity (18%):
$11.16
TOTAL:
$78.43
Payment VISAending in 4921
Auth Code: 839201| Status APPROVED
Thank You for Dining With Us!
Please Visit Again Soon"""

system_prompt = """You are a financial document parser. Extract receipt/invoice data from OCR text into a compact JSON object.
Omit null or empty fields. Use these exact keys:
- document_type: "Receipt" or "Invoice"
- invoice_number: string
- issue_date: "YYYY-MM-DD"
- vendor: {"name": "...", "address": "...", "phone": "...", "tax_id": "..."}
- line_items: [{"description": "...", "quantity": 1.0, "unit_price": 0.0, "total_price": 0.0}]
- subtotal: float
- taxes: [{"name": "...", "rate_percentage": 0.0, "amount": 0.0}]
- tax_total: float
- tip_or_gratuity: float
- total_amount: float
- currency: "USD"
- payment: {"payment_method": "...", "payment_status": "Paid", "card_last_four": "..."}

Return ONLY the JSON object. Do not include markdown or explanations."""

user_prompt = f"OCR Text:\n{ocr_text}\n\nJSON:"
chat_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n{{"

# Test Qwen2.5-0.5B
print("=== TESTING QWEN2.5-0.5B ===")
t0 = time.time()
llm05 = Llama(model_path="models/qwen2.5-0.5b-instruct-q4_k_m.gguf", n_ctx=2048, n_batch=512, n_threads=4, verbose=False)
t_load = time.time() - t0
print(f"0.5B Model load: {t_load:.2f}s")

t_gen_0 = time.time()
res = llm05(chat_prompt, max_tokens=600, stop=["<|im_end|>", "```"], temperature=0.1)
t_gen_1 = time.time()
duration = t_gen_1 - t_gen_0
toks = res["usage"]["completion_tokens"]
print(f"0.5B Generation: {duration:.2f}s ({toks} tokens, {toks/duration:.2f} tok/s)")

raw = "{" + res["choices"][0]["text"].strip()
start_idx = raw.find("{")
end_idx = raw.rfind("}")
clean_json = raw[start_idx:end_idx+1] if (start_idx != -1 and end_idx != -1) else raw

try:
    parsed = json.loads(clean_json)
    doc = ExtractedInvoiceReceipt(**parsed)
    val = validate_extraction(doc)
    print(f"0.5B PARSE SUCCESS! Vendor: {doc.vendor.name}, Total: {doc.total_amount}")
    print(f"0.5B Line Items: {len(doc.line_items)}, Quality Score: {val.quality_score}/100")
except Exception as e:
    print(f"0.5B Parse error: {e}")
    print("Raw output was:\n", clean_json)
