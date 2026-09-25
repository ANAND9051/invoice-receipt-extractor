import time
import json
from llama_cpp import Llama
from extractor.schemas import ExtractedInvoiceReceipt
from extractor.validator import validate_extraction

print("Loading model...")
t_load = time.time()
llm = Llama(
    model_path="models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    n_ctx=2048,
    n_batch=512,
    n_threads=4,
    verbose=False
)
print(f"Model loaded in {time.time() - t_load:.2f}s")

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

system_prompt = """You are a financial document parser. Extract receipt/invoice data into valid JSON matching this structure:
{
  "document_type": "receipt",
  "invoice_number": "INV-2024-001",
  "invoice_date": "2024-04-15",
  "due_date": null,
  "vendor": {"name": "BISTRO DELIGHT", "address": "123 Main St, New York, NY", "phone": "(555) 123-4567", "email": null, "tax_id": null, "website": null},
  "customer": {"name": null, "address": null, "tax_id": null},
  "line_items": [
    {"description": "Truffle Burger", "quantity": 2.0, "unit_price": 18.50, "total_price": 37.00}
  ],
  "subtotal": 59.50,
  "tax_items": [{"tax_name": "Sales Tax", "rate_percentage": 8.875, "amount": 5.28}],
  "total_tax": 5.28,
  "discount": 0.0,
  "tip": 10.0,
  "shipping": 0.0,
  "total_amount": 74.78,
  "currency": "USD",
  "payment": {"method": "Visa", "status": "paid", "transaction_id": null},
  "notes": null
}
Return strictly the JSON object. Do not include markdown codeblocks or extra text.
"""

print("Starting generation...")
t0 = time.time()
res = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Extract JSON for this text:\n{sample_text.strip()}"}
    ],
    response_format={"type": "json_object"},
    temperature=0.1,
    max_tokens=600
)
t1 = time.time()
duration = t1 - t0
content = res["choices"][0]["message"]["content"]
tokens_generated = res["usage"]["completion_tokens"]
print(f"Generated {tokens_generated} tokens in {duration:.2f}s ({tokens_generated / duration:.2f} tok/s)")
print("Output preview:", content[:200])

data = json.loads(content)
doc = ExtractedInvoiceReceipt(**data)
val = validate_extraction(doc)
print(f"Parsed Successfully! Vendor: {doc.vendor.name if doc.vendor else None}")
print(f"Grand Total: {doc.total_amount}")
print(f"Line items count: {len(doc.line_items)}")
print(f"Quality score: {val.quality_score}/100, Math consistent: {val.math_consistent}")
