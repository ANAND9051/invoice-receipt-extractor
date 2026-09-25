import time
import json
import re
from llama_cpp import Llama

llm = Llama(
    model_path="models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    n_ctx=2048,
    n_batch=512,
    n_threads=4,
    verbose=False
)

prompt = """<|im_start|>system
You are a helpful financial assistant. Extract receipt info into a JSON object with keys: store, date, total, items. Return strictly JSON.<|im_end|>
<|im_start|>user
Store: Walmart
Date: 2023-10-01
Apples: $5.00
Milk: $3.50
Total: $8.50<|im_end|>
<|im_start|>assistant
"""

# Test raw without grammar
t0 = time.time()
out = llm(prompt, max_tokens=150, stop=["<|im_end|>"], temperature=0.1)
t1 = time.time()
text = out["choices"][0]["text"]
toks = out["usage"]["completion_tokens"]
print(f"RAW (No grammar): {toks} tokens in {t1 - t0:.2f}s ({toks/(t1-t0):.2f} tok/s)")
print("Text:", text.strip()[:100])
