"""
DocuExtract AI: Structured Data & Receipt/Invoice Extractor
Supports both:
1. ☁️ Cloud Multimodal AI (Google Gemini API)
2. 💻 Local Offline AI (Llama.cpp GGUF + RapidOCR)
"""

import os
import io
import json
import glob
import time
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from PIL import Image
import pandas as pd
import pypdfium2 as pdfium
import streamlit as st

from extractor.schemas import ExtractedInvoiceReceipt, LineItem
from extractor.gemini_extractor import ReceiptExtractor, test_api_key_validity, VALID_GEMINI_MODELS
from extractor.validator import validate_extraction
from extractor.local_ocr import extract_document_text
from extractor.exporter import (
    to_json_str,
    to_csv_bytes,
    to_line_items_csv_bytes,
    to_excel_bytes,
    get_invoice_summary_dict,
    get_line_items_df,
)
from extractor.db import (
    save_extraction,
    get_all_extractions,
    delete_extraction,
    clear_all_extractions,
)
from extractor.llama_extractor import (
    LlamaCppExtractor,
    SUPPORTED_LOCAL_MODELS,
    download_local_model,
)
from extractor.categorizer import (
    group_line_items_by_category,
    get_category_emoji,
    CATEGORY_RULES,
)

# Load environment variables
load_dotenv()

st.set_page_config(
    page_title="DocuExtract AI - Structured Receipt & Invoice Extractor",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-success { background-color: #DCFCE7; color: #15803D; }
    .badge-warning { background-color: #FEF9C3; color: #A16207; }
    .badge-info { background-color: #E0F2FE; color: #0369A1; }
    .badge-purple { background-color: #F3E8FF; color: #7E22CE; }

    /* Column flexbox min-width fix so columns don't overflow */
    div[data-testid="column"] {
        min-width: 0 !important;
    }

    /* Metric card container - strictly bounded */
    div[data-testid="stMetric"] {
        background-color: #F8FAFC !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 10px !important;
        padding: 10px 12px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
        min-height: 92px !important;
        height: 100% !important;
        overflow: hidden !important;
        box-sizing: border-box !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
    }

    /* Force all text inside stMetricValue to wrap within its card */
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] *,
    div[data-testid="stMetricValue"] span,
    div[data-testid="stMetricValue"] div {
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: #0F172A !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
        word-break: break-word !important;
        text-overflow: unset !important;
        overflow: hidden !important;
        line-height: 1.22 !important;
    }

    /* Metric labels */
    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricLabel"] *,
    div[data-testid="stMetricLabel"] p {
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        color: #64748B !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        margin-bottom: 2px !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
        word-break: break-word !important;
    }

    /* Metric delta badges */
    div[data-testid="stMetricDelta"],
    div[data-testid="stMetricDelta"] * {
        font-size: 0.75rem !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
    }
</style>
""", unsafe_allow_html=True)


# --- Helper Functions ---
def get_pdf_page_images(pdf_bytes: bytes) -> List[Image.Image]:
    """Renders PDF pages into PIL Images using pypdfium2."""
    images = []
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        for page in pdf:
            images.append(page.render(scale=2.0).to_pil())
    except Exception as e:
        st.error(f"Error rendering PDF pages: {e}")
    return images


def determine_mime_type(filename: str) -> str:
    ext = filename.lower().split(".")[-1]
    if ext == "pdf":
        return "application/pdf"
    elif ext in ["jpg", "jpeg"]:
        return "image/jpeg"
    elif ext == "png":
        return "image/png"
    elif ext == "webp":
        return "image/webp"
    return "application/octet-stream"


# --- Session State Setup ---
if "api_key" not in st.session_state:
    _key = os.getenv("GEMINI_API_KEY", "")
    if not _key:
        try:
            if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                _key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
    st.session_state.api_key = _key

if "single_doc_data" not in st.session_state:
    st.session_state.single_doc_data = None

if "single_doc_val" not in st.session_state:
    st.session_state.single_doc_val = None

if "single_doc_ocr_text" not in st.session_state:
    st.session_state.single_doc_ocr_text = None

if "single_doc_file_info" not in st.session_state:
    st.session_state.single_doc_file_info = None

if "batch_results" not in st.session_state:
    st.session_state.batch_results = []


# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⚙️ Extractor Engine")
    
    # Engine Provider Toggle
    engine_provider = st.radio(
        "Select Processing Backend",
        options=["☁️ Cloud (Google Gemini)", "💻 Local Offline (Llama.cpp)"],
        index=0,
        help="Choose between cloud multimodal AI (high accuracy, zero RAM) or 100% offline local AI (private, no API keys)."
    )

    is_cloud = "Gemini" in engine_provider
    local_model_path = None

    if is_cloud:
        st.markdown('<span class="status-badge badge-info">☁️ Cloud Multimodal</span>', unsafe_allow_html=True)
        # API Key Input
        api_key_input = st.text_input(
            "Gemini API Key",
            value=st.session_state.api_key,
            type="password",
            help="Get a free key from Google AI Studio: https://aistudio.google.com/app/apikey"
        )
        if api_key_input:
            st.session_state.api_key = api_key_input.strip()

        col_k1, col_k2 = st.columns([2, 1])
        with col_k1:
            if st.session_state.api_key:
                st.markdown('<span class="status-badge badge-success">✓ Key Set</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-badge badge-warning">⚠️ Key Required</span>', unsafe_allow_html=True)
        with col_k2:
            if st.button("⚡ Test", help="Test if your Gemini API key is valid and has active quota"):
                if not st.session_state.api_key:
                    st.error("Please enter an API key first.")
                else:
                    with st.spinner("Probing API & fetching available models..."):
                        is_ok, msg, models_found = test_api_key_validity(st.session_state.api_key)
                        if is_ok:
                            st.success(f"✓ Key active! Models accessible: {', '.join(models_found[:3])}")
                            st.session_state.discovered_models = models_found
                        else:
                            st.error(f"❌ {msg}")

        # Use discovered models if available, otherwise default list
        available_models = st.session_state.get("discovered_models", VALID_GEMINI_MODELS)
        if not available_models:
            available_models = VALID_GEMINI_MODELS

        model_choice = st.selectbox(
            "Gemini Model",
            options=available_models,
            index=0,
            help="gemini-2.5-flash is the default recommended multimodal model for receipts and invoices."
        )

        st.caption("💡 *Note: If your key lacks Generative Language API permissions, switch to **Local Offline** above to extract 100% offline without any API key.*")

    else:
        st.markdown('<span class="status-badge badge-purple">🔒 100% Offline & Private</span>', unsafe_allow_html=True)
        
        models_dir = os.path.join(os.path.dirname(__file__), "models")
        os.makedirs(models_dir, exist_ok=True)

        selected_local_model_name = st.selectbox(
            "Local Model",
            options=list(SUPPORTED_LOCAL_MODELS.keys()) + ["Custom GGUF File..."],
            index=0,
            help="Models are quantized to GGUF Q4_K_M for minimal RAM usage on 8 GB machines."
        )

        if selected_local_model_name != "Custom GGUF File...":
            meta = SUPPORTED_LOCAL_MODELS[selected_local_model_name]
            expected_file = os.path.join(models_dir, meta["filename"])
            is_downloaded = os.path.exists(expected_file) and os.path.getsize(expected_file) > 100 * 1024 * 1024

            if is_downloaded:
                st.markdown(f'<span class="status-badge badge-success">✓ Model Downloaded ({meta["size_mb"]} MB)</span>', unsafe_allow_html=True)
                local_model_path = expected_file
            else:
                st.markdown(f'<span class="status-badge badge-warning">⬇️ Download Needed ({meta["size_mb"]} MB)</span>', unsafe_allow_html=True)
                if st.button(f"📥 Download Model ({meta['size_mb']} MB)", use_container_width=True):
                    with st.spinner(f"Downloading {meta['filename']} from Hugging Face..."):
                        local_model_path = download_local_model(selected_local_model_name, models_dir=models_dir)
                    st.success("Download complete!")
                    st.rerun()
        else:
            custom_path = st.text_input("Local .gguf File Path", placeholder="C:/path/to/model.gguf")
            if custom_path and os.path.exists(custom_path):
                local_model_path = custom_path
                st.success("Valid GGUF file located!")
            elif custom_path:
                st.error("File not found.")

        cpu_threads = st.slider("CPU Threads", min_value=1, max_value=8, value=4, help="Number of CPU cores dedicated to inference.")

    st.markdown("---")
    
    # Optional extraction guidance
    custom_guidance = st.text_area(
        "Custom Guidance (Optional)",
        placeholder="e.g. Ensure client VAT number is captured; check line item discounts.",
        help="Add specific prompt instructions or edge-case handling rules."
    )

    st.markdown("---")
    st.markdown("### 🧪 Quick Test Samples")
    samples_dir = os.path.join(os.path.dirname(__file__), "samples")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("🍕 Restaurant Receipt", use_container_width=True):
            sample_path = os.path.join(samples_dir, "sample_restaurant_receipt.png")
            if os.path.exists(sample_path):
                with open(sample_path, "rb") as f:
                    file_bytes = f.read()
                st.session_state.test_sample_bytes = file_bytes
                st.session_state.test_sample_name = "sample_restaurant_receipt.png"
                st.session_state.test_sample_mime = "image/png"
                st.session_state.single_doc_data = None
                st.session_state.single_doc_ocr_text = None
                st.success("Loaded sample receipt!")
                st.rerun()

    with col_s2:
        if st.button("💼 Tech Invoice (PDF)", use_container_width=True):
            sample_path = os.path.join(samples_dir, "sample_invoice.pdf")
            if os.path.exists(sample_path):
                with open(sample_path, "rb") as f:
                    file_bytes = f.read()
                st.session_state.test_sample_bytes = file_bytes
                st.session_state.test_sample_name = "sample_invoice.pdf"
                st.session_state.test_sample_mime = "application/pdf"
                st.session_state.single_doc_data = None
                st.session_state.single_doc_ocr_text = None
                st.success("Loaded sample invoice PDF!")
                st.rerun()


# --- Main Area ---
st.markdown('<div class="main-header">📄 DocuExtract AI: Structured Receipt & Invoice Extractor</div>', unsafe_allow_html=True)
mode_desc = "Gemini Multimodal Cloud Vision" if is_cloud else "Llama.cpp Local GGUF + RapidOCR"
st.markdown(f'<div class="sub-header">Financial document parser powered by <b>{mode_desc}</b> with Pydantic schema validation</div>', unsafe_allow_html=True)

# Main Navigation Tabs
tab_single, tab_batch, tab_history = st.tabs([
    "🔍 Document Inspector & Review",
    "📚 Batch Extraction Mode",
    "🗄️ Database History & Search"
])


# =========================================================
# TAB 1: SINGLE DOCUMENT INSPECTION & REVIEW
# =========================================================
with tab_single:
    st.markdown("##### Upload Document (Image or PDF)")
    
    col_up, col_btn = st.columns([3, 1])
    with col_up:
        uploaded_file = st.file_uploader(
            "Choose a receipt or invoice",
            type=["png", "jpg", "jpeg", "webp", "pdf"],
            key="single_file_uploader",
            label_visibility="collapsed"
        )

    active_bytes = None
    active_filename = None
    active_mime = None

    if uploaded_file is not None:
        active_bytes = uploaded_file.getvalue()
        active_filename = uploaded_file.name
        active_mime = determine_mime_type(uploaded_file.name)
    elif "test_sample_bytes" in st.session_state and st.session_state.test_sample_bytes is not None:
        active_bytes = st.session_state.test_sample_bytes
        active_filename = st.session_state.test_sample_name
        active_mime = st.session_state.test_sample_mime

    with col_btn:
        extract_button = st.button("🚀 Extract Data", type="primary", use_container_width=True, disabled=(active_bytes is None))

    # Extraction Trigger
    if extract_button and active_bytes:
        if is_cloud and not st.session_state.api_key:
            st.error("⚠️ Please enter your Gemini API Key in the left sidebar to proceed.")
        elif not is_cloud and not local_model_path:
            st.error("⚠️ Please download or specify a local GGUF model in the left sidebar first.")
        else:
            if is_cloud:
                with st.spinner("☁️ Extracting structured data with Gemini Multimodal Vision..."):
                    try:
                        t_start = time.time()
                        extractor = ReceiptExtractor(api_key=st.session_state.api_key, model_name=model_choice)
                        extracted_doc, val_res = extractor.extract_from_bytes(
                            file_bytes=active_bytes,
                            mime_type=active_mime,
                            custom_instructions=custom_guidance
                        )
                        t_total = time.time() - t_start
                        st.session_state.single_doc_ocr_text = None
                        st.session_state.single_doc_data = extracted_doc
                        st.session_state.single_doc_val = val_res
                        st.session_state.single_doc_file_info = {
                            "name": active_filename,
                            "bytes": active_bytes,
                            "mime": active_mime
                        }
                        used_model = extractor.model_name
                        if used_model != model_choice:
                            st.info(f"ℹ️ Google Server Note: `{model_choice}` was experiencing high traffic (503); automatically completed using high-availability `{used_model}`!")
                        st.session_state.extraction_metrics = f"☁️ Cloud Gemini ({used_model}) completed in **{t_total:.1f}s**"
                        st.success(f"Extraction completed in {t_total:.1f}s!")
                    except Exception as err:
                        err_str = str(err)
                        if "503" in err_str or "high demand" in err_str.lower():
                            st.warning("⚠️ **Google Gemini Server Spike (503):** Google's servers for this specific model are temporarily overloaded. Switch to **gemini-2.0-flash** in the left sidebar or select **💻 Local Offline** above to extract instantly without cloud limits!")
                        st.error(f"Extraction failed: {err}")
            else:
                with st.status("🚀 Running Offline Local AI Extraction...", expanded=True) as status:
                    try:
                        t_start = time.time()
                        status.write("🔍 **Step 1/2:** Extracting text with RapidOCR...")
                        t_ocr_0 = time.time()
                        ocr_text = extract_document_text(active_bytes, active_mime)
                        t_ocr = time.time() - t_ocr_0
                        status.write(f"✓ RapidOCR extracted {len(ocr_text)} characters in **{t_ocr:.1f}s**")

                        status.write("🧠 **Step 2/2:** Structuring data with local model...")
                        t_llm_0 = time.time()
                        local_extractor = LlamaCppExtractor(
                            model_path=local_model_path,
                            n_ctx=2048,
                            n_threads=cpu_threads
                        )
                        extracted_doc, val_res = local_extractor.extract_from_text(
                            ocr_text=ocr_text,
                            custom_instructions=custom_guidance
                        )
                        t_llm = time.time() - t_llm_0
                        status.write(f"✓ Local AI structured all fields in **{t_llm:.1f}s**")

                        t_total = time.time() - t_start
                        status.update(label=f"✅ Local extraction finished in {t_total:.1f}s (OCR: {t_ocr:.1f}s, LLM: {t_llm:.1f}s)", state="complete", expanded=False)

                        st.session_state.single_doc_ocr_text = ocr_text
                        st.session_state.single_doc_data = extracted_doc
                        st.session_state.single_doc_val = val_res
                        st.session_state.single_doc_file_info = {
                            "name": active_filename,
                            "bytes": active_bytes,
                            "mime": active_mime
                        }
                        st.session_state.extraction_metrics = f"⚡ Offline Local AI completed in **{t_total:.1f}s** (OCR: {t_ocr:.1f}s | LLM: {t_llm:.1f}s)"
                        st.success(f"Extraction completed successfully in {t_total:.1f}s!")
                    except Exception as err:
                        status.update(label="❌ Extraction Failed", state="error", expanded=True)
                        st.error(f"Extraction failed: {err}")

    # Display Side-by-Side Review
    if active_bytes:
        col_preview, col_data = st.columns([1, 1], gap="medium")

        # LEFT COLUMN: Document Preview
        with col_preview:
            st.markdown(f"**Preview: `{active_filename}`**")
            if active_mime == "application/pdf":
                pdf_images = get_pdf_page_images(active_bytes)
                if pdf_images:
                    if len(pdf_images) > 1:
                        page_num = st.slider("Page Selector", 1, len(pdf_images), 1)
                        st.image(pdf_images[page_num - 1], use_container_width=True, caption=f"Page {page_num} of {len(pdf_images)}")
                    else:
                        st.image(pdf_images[0], use_container_width=True, caption="Page 1 of 1")
            else:
                img = Image.open(io.BytesIO(active_bytes))
                st.image(img, use_container_width=True, caption=active_filename)

            # If Local OCR text is available, show it here
            if st.session_state.single_doc_ocr_text:
                with st.expander("🔍 View Raw Local OCR Text (RapidOCR)", expanded=False):
                    st.text(st.session_state.single_doc_ocr_text)

        # RIGHT COLUMN: Structured Extraction & Review
        with col_data:
            doc: Optional[ExtractedInvoiceReceipt] = st.session_state.single_doc_data
            val = st.session_state.single_doc_val

            if doc:
                # Top KPI Row
                kpi1, kpi2, kpi3, kpi4 = st.columns([1.1, 1.3, 1.2, 0.8])
                with kpi1:
                    curr_sym = doc.currency_symbol or ("₹" if doc.currency == "INR" else (doc.currency or ""))
                    tot_display = f"{curr_sym} {doc.total_amount:,.2f}".strip() if doc.total_amount is not None else "N/A"
                    st.metric("Total Amount", tot_display, doc.currency or "")
                with kpi2:
                    vendor_name = doc.vendor.name if (doc.vendor and doc.vendor.name) else "N/A"
                    st.metric("Vendor", vendor_name)
                with kpi3:
                    inv_no = doc.invoice_number or "N/A"
                    st.metric("Invoice #", inv_no, doc.issue_date or "")
                with kpi4:
                    q_score = val.quality_score if val else int((doc.confidence_score or 0.9) * 100)
                    st.metric("Quality Score", f"{q_score}%")

                if "extraction_metrics" in st.session_state and st.session_state.extraction_metrics:
                    st.markdown(f'<div style="margin-top: 6px; margin-bottom: 12px; font-size: 0.88rem; color: #475569; background: #F1F5F9; padding: 6px 12px; border-radius: 6px;">⏱️ {st.session_state.extraction_metrics}</div>', unsafe_allow_html=True)

                # Validation & Mathematical Integrity Box
                if val:
                    math_stat = val.math_checks.get("status", "Unknown")
                    if "Balanced" in math_stat:
                        st.success(f"✓ **Audit Passed:** Math checks are mathematically consistent ({math_stat}).")
                    elif "Minor Rounding" in math_stat:
                        st.info(f"ℹ️ **Math Notice:** {math_stat}")
                    else:
                        st.warning(f"⚠️ **Math Discrepancy:** {math_stat}")

                    if val.warnings:
                        with st.expander(f"⚠️ Validation Warnings ({len(val.warnings)})", expanded=False):
                            for w in val.warnings:
                                st.write(f"- {w}")

                # Sub-Tabs
                review_t1, review_t_groups, review_t2, review_t3, review_t4, review_t5 = st.tabs([
                    "📋 Overview",
                    "🗂️ Product Groups",
                    "🛒 Line Items Editor",
                    "💰 Financial Breakdown",
                    "💳 Payment & Metadata",
                    "💻 Raw JSON"
                ])

                # 1. Overview
                with review_t1:
                    c_v, c_c = st.columns(2)
                    with c_v:
                        st.markdown("###### 🏢 Merchant / Vendor Details")
                        if doc.vendor:
                            st.write(f"**Name:** {doc.vendor.name or '—'}")
                            st.write(f"**Tax ID / VAT:** {doc.vendor.tax_id or '—'}")
                            st.write(f"**Address:** {doc.vendor.address or '—'}")
                            st.write(f"**Phone:** {doc.vendor.phone or '—'}")
                            st.write(f"**Email:** {doc.vendor.email or '—'}")
                            st.write(f"**Website:** {doc.vendor.website or '—'}")
                    with c_c:
                        st.markdown("###### 👤 Customer / Billed To")
                        if doc.customer:
                            st.write(f"**Name:** {doc.customer.name or '—'}")
                            st.write(f"**Company:** {doc.customer.company_name or '—'}")
                            st.write(f"**Tax ID:** {doc.customer.tax_id or '—'}")
                            st.write(f"**Billing Address:** {doc.customer.billing_address or '—'}")
                            st.write(f"**Shipping Address:** {doc.customer.shipping_address or '—'}")

                # 2. Product Groups & Categories
                with review_t_groups:
                    st.markdown("###### 🗂️ Product Groups & Category Breakdown")
                    st.caption("Items are automatically classified into supermarket groups (Vegetables, Fruits, Dairy, Snacks, Staples, etc.).")

                    grouped_data = group_line_items_by_category(doc.line_items or [])

                    if grouped_data:
                        num_cats = len(grouped_data)
                        grand_tot = doc.total_amount or sum(g["subtotal"] for g in grouped_data.values()) or 1.0

                        # Summary Metric Cards Grid
                        top_cols = st.columns(min(4, max(1, num_cats)))
                        for i, (c_name, c_data) in enumerate(list(grouped_data.items())[:4]):
                            with top_cols[i % len(top_cols)]:
                                pct = (c_data["subtotal"] / grand_tot * 100.0) if grand_tot > 0 else 0.0
                                st.metric(
                                    label=f"{c_data['emoji']} {c_name}",
                                    value=f"{doc.currency_symbol or doc.currency or ''} {c_data['subtotal']:,.2f}",
                                    delta=f"{c_data['count']} item(s) • {pct:.0f}%"
                                )

                        # Visual Spending Distribution Chart
                        chart_rows = [
                            {"Group": f"{d['emoji']} {c}", "Spend": d["subtotal"]}
                            for c, d in grouped_data.items()
                        ]
                        if chart_rows:
                            st.markdown("###### 📊 Spending Distribution by Group")
                            chart_df = pd.DataFrame(chart_rows).set_index("Group")
                            st.bar_chart(chart_df, y="Spend", use_container_width=True)

                        # Collapsible Category Group Details
                        st.markdown("###### 🛒 Items in Each Product Group")
                        for c_name, c_data in grouped_data.items():
                            exp_title = f"{c_data['emoji']} **{c_name}** — {c_data['count']} item(s) • Total: {doc.currency_symbol or doc.currency or ''} {c_data['subtotal']:,.2f}"
                            with st.expander(exp_title, expanded=True):
                                cat_rows = []
                                for itm in c_data["items"]:
                                    cat_rows.append({
                                        "Description": itm.description,
                                        "Quantity": itm.quantity or 1.0,
                                        "Unit Price": f"{doc.currency_symbol or doc.currency or ''} {itm.unit_price:,.2f}" if itm.unit_price is not None else "—",
                                        "Total Price": f"{doc.currency_symbol or doc.currency or ''} {itm.total_price:,.2f}" if itm.total_price is not None else "—",
                                    })
                                st.dataframe(pd.DataFrame(cat_rows), use_container_width=True, hide_index=True)
                    else:
                        st.info("No item groups detected.")

                # 3. Line Items (Editable Table)
                with review_t2:
                    st.markdown("###### 📝 Line Items (Double-click any cell to edit)")
                    if doc.line_items:
                        items_df = pd.DataFrame([{
                            "Item #": int(item.item_index or (i+1)),
                            "Description": str(item.description or ""),
                            "Category": str(item.category or "General"),
                            "SKU": str(item.sku or ""),
                            "Qty": float(item.quantity or 1.0),
                            "Unit": str(item.unit_of_measure or ""),
                            "Unit Price": float(item.unit_price or 0.0),
                            "Discount": float(item.discount_amount or 0.0),
                            "Line Total": float(item.total_price or 0.0),
                        } for i, item in enumerate(doc.line_items)])

                        category_options = list(CATEGORY_RULES.keys()) + ["General", "Other"]
                        edited_df = st.data_editor(
                            items_df,
                            column_config={
                                "Category": st.column_config.SelectboxColumn(
                                    "Category",
                                    help="Product group classification",
                                    options=category_options,
                                    required=True
                                )
                            },
                            num_rows="dynamic",
                            use_container_width=True,
                            key="line_items_editor"
                        )
                        calculated_table_sum = float(edited_df["Line Total"].sum())
                        st.caption(f"**Calculated Sum of Line Items:** {doc.currency_symbol or doc.currency or ''} {calculated_table_sum:,.2f}")
                    else:
                        st.info("No line items extracted.")

                # 3. Financial Breakdown
                with review_t3:
                    st.markdown("###### 📊 Financial Audit Summary")
                    def _fmt_money(val, is_neg=False):
                        if val is None:
                            return "—"
                        try:
                            f = float(val)
                            cur = f"{doc.currency_symbol or doc.currency or ''} " if (doc.currency_symbol or doc.currency) else ""
                            if is_neg and f > 0:
                                return f"-{cur}{f:,.2f}"
                            return f"{cur}{f:,.2f}"
                        except Exception:
                            return str(val)

                    fin_data = {
                        "Component": [
                            "Subtotal (Pre-tax)",
                            "Discount Total",
                            "Taxes Total",
                            "Shipping / Freight",
                            "Tip / Gratuity",
                            "Grand Total"
                        ],
                        "Amount": [
                            _fmt_money(doc.subtotal),
                            _fmt_money(doc.discount_total, is_neg=True),
                            _fmt_money(doc.tax_total),
                            _fmt_money(doc.shipping_fee),
                            _fmt_money(doc.tip_or_gratuity),
                            _fmt_money(doc.total_amount)
                        ]
                    }
                    st.table(pd.DataFrame(fin_data))

                    if doc.taxes:
                        st.markdown("###### Itemized Tax Breakdown")
                        tax_rows = []
                        for t in doc.taxes:
                            amt_str = _fmt_money(t.amount)
                            rate_str = f"{t.rate_percentage}%" if t.rate_percentage is not None else "—"
                            tax_rows.append({
                                "Tax Name": str(t.name or "Tax"),
                                "Rate (%)": rate_str,
                                "Amount": amt_str
                            })
                        st.dataframe(pd.DataFrame(tax_rows), use_container_width=True, hide_index=True)

                # 4. Payment & Metadata
                with review_t4:
                    st.markdown("###### 💳 Payment Transaction Details")
                    if doc.payment:
                        st.write(f"**Status:** {doc.payment.payment_status or '—'}")
                        st.write(f"**Method:** {doc.payment.payment_method or '—'}")
                        st.write(f"**Card Brand:** {doc.payment.card_brand or '—'}")
                        st.write(f"**Card Last 4:** {doc.payment.card_last_four or '—'}")
                        st.write(f"**Transaction Ref:** {doc.payment.transaction_reference or '—'}")
                    st.markdown("###### 📄 Document Metadata")
                    st.write(f"**Document Type:** {doc.document_type}")
                    st.write(f"**Payment Terms:** {doc.payment_terms or '—'}")
                    st.write(f"**Due Date:** {doc.due_date or '—'}")
                    st.write(f"**Confidence:** {int((doc.confidence_score or 0.9) * 100)}%")
                    if doc.notes_or_terms:
                        st.info(f"**Notes / Terms:** {doc.notes_or_terms}")

                # 5. Raw JSON
                with review_t5:
                    st.json(doc.model_dump())

                st.markdown("---")
                
                # Action Buttons Row
                btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)
                with btn_c1:
                    if st.button("💾 Save to History DB", use_container_width=True):
                        rec_id = save_extraction(
                            filename=active_filename,
                            doc=doc,
                            quality_score=val.quality_score if val else 90
                        )
                        st.success(f"Saved record #{rec_id} to database!")

                with btn_c2:
                    json_str = to_json_str(doc)
                    st.download_button(
                        label="📥 Download JSON",
                        data=json_str,
                        file_name=f"{active_filename.rsplit('.', 1)[0]}_extracted.json",
                        mime="application/json",
                        use_container_width=True
                    )

                with btn_c3:
                    csv_data = to_csv_bytes(doc)
                    st.download_button(
                        label="📊 Summary CSV",
                        data=csv_data,
                        file_name=f"{active_filename.rsplit('.', 1)[0]}_summary.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with btn_c4:
                    excel_data = to_excel_bytes([doc], filenames=[active_filename])
                    st.download_button(
                        label="📗 Multi-Sheet Excel",
                        data=excel_data,
                        file_name=f"{active_filename.rsplit('.', 1)[0]}_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                st.info("👈 Click **Extract Data** above to process this document.")


# =========================================================
# TAB 2: BATCH EXTRACTION MODE
# =========================================================
with tab_batch:
    st.markdown("##### Batch Receipt & Invoice Processing")
    st.write(f"Upload multiple documents to extract and consolidate them using **{mode_desc}**.")

    batch_files = st.file_uploader(
        "Upload multiple files",
        type=["png", "jpg", "jpeg", "webp", "pdf"],
        accept_multiple_files=True,
        key="batch_file_uploader"
    )

    if batch_files:
        st.write(f"**{len(batch_files)} files selected.**")
        
        if st.button("⚡ Process All Documents", type="primary"):
            if is_cloud and not st.session_state.api_key:
                st.error("⚠️ Please enter your Gemini API Key in the left sidebar first.")
            elif not is_cloud and not local_model_path:
                st.error("⚠️ Please download or specify a local GGUF model in the left sidebar first.")
            else:
                if is_cloud:
                    extractor = ReceiptExtractor(api_key=st.session_state.api_key, model_name=model_choice)
                else:
                    local_extractor = LlamaCppExtractor(model_path=local_model_path, n_ctx=2048, n_threads=cpu_threads)

                progress_bar = st.progress(0)
                status_text = st.empty()
                results = []

                for i, bf in enumerate(batch_files):
                    status_text.text(f"Processing ({i+1}/{len(batch_files)}): {bf.name}...")
                    file_bytes = bf.getvalue()
                    mime_type = determine_mime_type(bf.name)
                    try:
                        if is_cloud:
                            extracted_doc, val = extractor.extract_from_bytes(
                                file_bytes=file_bytes,
                                mime_type=mime_type,
                                custom_instructions=custom_guidance
                            )
                        else:
                            extracted_doc, val, _ = local_extractor.extract_from_bytes(
                                file_bytes=file_bytes,
                                mime_type=mime_type,
                                custom_instructions=custom_guidance
                            )
                        results.append({
                            "filename": bf.name,
                            "doc": extracted_doc,
                            "validation": val
                        })
                        save_extraction(filename=bf.name, doc=extracted_doc, quality_score=val.quality_score)
                    except Exception as b_err:
                        st.error(f"Error processing {bf.name}: {b_err}")

                    progress_bar.progress((i + 1) / len(batch_files))

                status_text.text("Batch processing completed!")
                st.session_state.batch_results = results
                st.success(f"Successfully processed {len(results)} documents!")

    # Display Batch Results
    if st.session_state.batch_results:
        st.markdown("---")
        st.markdown("### 📊 Consolidated Batch Summary")
        
        batch_docs = [r["doc"] for r in st.session_state.batch_results]
        batch_filenames = [r["filename"] for r in st.session_state.batch_results]

        summary_rows = [get_invoice_summary_dict(d, fn) for d, fn in zip(batch_docs, batch_filenames)]
        df_batch = pd.DataFrame(summary_rows)

        # Overview Metrics
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Documents", len(batch_docs))
        with m2:
            currencies = df_batch["Currency"].unique()
            primary_cur = currencies[0] if len(currencies) > 0 and currencies[0] else "Total"
            tot_spend = df_batch["Total Amount"].dropna().sum()
            st.metric(f"Total Spend ({primary_cur})", f"{tot_spend:,.2f}")
        with m3:
            avg_conf = df_batch["Confidence Score"].mean() * 100
            st.metric("Average Quality", f"{avg_conf:.1f}%")
        with m4:
            total_items = df_batch["Line Items Count"].sum()
            st.metric("Total Items Extracted", int(total_items))

        # Filterable Data Table
        st.dataframe(df_batch, use_container_width=True)

        # Consolidated Export Buttons
        col_ex1, col_ex2, col_ex3 = st.columns(3)
        with col_ex1:
            batch_excel = to_excel_bytes(batch_docs, filenames=batch_filenames)
            st.download_button(
                label="📗 Download Master Excel (.xlsx)",
                data=batch_excel,
                file_name="batch_invoices_consolidated.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col_ex2:
            batch_csv = to_csv_bytes(batch_docs)
            st.download_button(
                label="📊 Download Summary CSV",
                data=batch_csv,
                file_name="batch_invoices_summary.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_ex3:
            batch_json = to_json_str(batch_docs)
            st.download_button(
                label="📥 Download Consolidated JSON",
                data=batch_json,
                file_name="batch_invoices_consolidated.json",
                mime="application/json",
                use_container_width=True
            )


# =========================================================
# TAB 3: DATABASE HISTORY & SEARCH
# =========================================================
with tab_history:
    st.markdown("##### 🗄️ Extraction History (Local SQLite Storage)")
    records = get_all_extractions()
    
    if not records:
        st.info("No saved extractions found in database yet. Processed receipts can be saved here.")
    else:
        st.write(f"**Total Records:** {len(records)}")

        search_query = st.text_input("🔍 Search history by Vendor, Invoice Number, or File", "")

        filtered_records = records
        if search_query.strip():
            sq = search_query.lower()
            filtered_records = [
                r for r in records
                if (r["vendor_name"] and sq in r["vendor_name"].lower())
                or (r["invoice_number"] and sq in r["invoice_number"].lower())
                or (r["filename"] and sq in r["filename"].lower())
            ]

        # Display history table
        hist_table_data = []
        for r in filtered_records:
            hist_table_data.append({
                "ID": r["id"],
                "Date Processed": r["created_at"][:19].replace("T", " "),
                "Filename": r["filename"],
                "Doc Type": r["document_type"],
                "Vendor": r["vendor_name"],
                "Invoice #": r["invoice_number"],
                "Amount": f"{r['currency'] or ''} {r['total_amount']:,.2f}" if r["total_amount"] is not None else "—",
                "Quality": f"{r['quality_score']}%"
            })
        st.dataframe(pd.DataFrame(hist_table_data), use_container_width=True, hide_index=True)

        # Inspection Expander
        st.markdown("###### Inspect Stored Extraction")
        selected_id = st.selectbox("Select Record ID to Inspect", options=[r["id"] for r in filtered_records], index=0)
        selected_record = next((r for r in filtered_records if r["id"] == selected_id), None)
        
        if selected_record:
            rec_json = json.loads(selected_record["json_data"])
            with st.expander(f"Record #{selected_id} - {selected_record['vendor_name']} ({selected_record['invoice_number']})", expanded=True):
                st.json(rec_json)
                
                if st.button("🗑️ Delete this Record", key=f"del_{selected_id}"):
                    delete_extraction(selected_id)
                    st.success("Record deleted.")
                    st.rerun()

        # Clear All Button
        st.markdown("---")
        if st.button("⚠️ Clear All History Records"):
            clear_all_extractions()
            st.success("History database cleared.")
            st.rerun()
