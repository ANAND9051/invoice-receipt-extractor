"""
Export utilities for extracted receipts and invoices: JSON, CSV, and formatted Excel.
Includes full support for Product Categories & Grouped Breakdowns.
"""

import json
import io
import pandas as pd
from typing import List, Dict, Any, Union
from extractor.schemas import ExtractedInvoiceReceipt
from extractor.categorizer import group_line_items_by_category


def to_json_str(data: Union[ExtractedInvoiceReceipt, List[ExtractedInvoiceReceipt]]) -> str:
    """Exports data to formatted JSON string."""
    if isinstance(data, list):
        return json.dumps([item.model_dump(exclude_none=False) for item in data], indent=2, ensure_ascii=False)
    return json.dumps(data.model_dump(exclude_none=False), indent=2, ensure_ascii=False)


def get_invoice_summary_dict(doc: ExtractedInvoiceReceipt, filename: str = "") -> Dict[str, Any]:
    """Flattens main document fields into a single record."""
    return {
        "File": filename,
        "Document Type": doc.document_type,
        "Vendor Name": doc.vendor.name if doc.vendor else "",
        "Vendor Tax ID": doc.vendor.tax_id if doc.vendor else "",
        "Customer Name": doc.customer.name or (doc.customer.company_name if doc.customer else ""),
        "Invoice Number": doc.invoice_number or "",
        "Order Number": doc.order_number or "",
        "Issue Date": doc.issue_date or "",
        "Due Date": doc.due_date or "",
        "Currency": doc.currency or "",
        "Subtotal": doc.subtotal,
        "Tax Total": doc.tax_total,
        "Discount Total": doc.discount_total,
        "Shipping Fee": doc.shipping_fee,
        "Tip / Gratuity": doc.tip_or_gratuity,
        "Total Amount": doc.total_amount,
        "Payment Method": doc.payment.payment_method if doc.payment else "",
        "Payment Status": doc.payment.payment_status if doc.payment else "",
        "Line Items Count": len(doc.line_items) if doc.line_items else 0,
        "Confidence Score": doc.confidence_score,
    }


def get_line_items_df(doc: ExtractedInvoiceReceipt, filename: str = "") -> pd.DataFrame:
    """Converts line items to a pandas DataFrame including Product Category."""
    rows = []
    for idx, item in enumerate(doc.line_items or []):
        rows.append({
            "File": filename,
            "Invoice Number": doc.invoice_number or "",
            "Vendor": doc.vendor.name if doc.vendor else "",
            "Date": doc.issue_date or "",
            "Item #": item.item_index if item.item_index is not None else (idx + 1),
            "Description": item.description,
            "Category": item.category or "General",
            "SKU": item.sku or "",
            "Quantity": item.quantity or 1.0,
            "Unit": item.unit_of_measure or "",
            "Unit Price": item.unit_price,
            "Discount": item.discount_amount or 0.0,
            "Tax Rate %": item.tax_rate,
            "Total Price": item.total_price,
            "Currency": doc.currency or "",
        })
    return pd.DataFrame(rows)


def get_category_summary_df(doc: ExtractedInvoiceReceipt) -> pd.DataFrame:
    """Computes a category breakdown DataFrame with item counts, subtotal, and % of grand total."""
    grouped = group_line_items_by_category(doc.line_items or [])
    grand_total = doc.total_amount or sum(g["subtotal"] for g in grouped.values()) or 1.0

    rows = []
    for cat_name, data in grouped.items():
        sub = data["subtotal"]
        pct = (sub / grand_total * 100.0) if grand_total > 0 else 0.0
        rows.append({
            "Group": f"{data['emoji']} {cat_name}",
            "Category": cat_name,
            "Items Count": data["count"],
            "Subtotal": round(sub, 2),
            "% of Total": f"{pct:.1f}%",
        })

    return pd.DataFrame(rows)


def to_csv_bytes(data: Union[ExtractedInvoiceReceipt, List[ExtractedInvoiceReceipt]]) -> bytes:
    """Generates summary CSV bytes."""
    docs = data if isinstance(data, list) else [data]
    records = [get_invoice_summary_dict(doc) for doc in docs]
    df = pd.DataFrame(records)
    return df.to_csv(index=False).encode("utf-8")


def to_line_items_csv_bytes(docs: List[ExtractedInvoiceReceipt]) -> bytes:
    """Generates all line items CSV bytes with Category column."""
    dfs = [get_line_items_df(doc) for doc in docs]
    if dfs:
        combined_df = pd.concat(dfs, ignore_index=True)
    else:
        combined_df = pd.DataFrame()
    return combined_df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(docs: List[ExtractedInvoiceReceipt], filenames: List[str] = None) -> bytes:
    """
    Exports single or multiple receipts into a structured multi-tab Excel workbook
    including Summaries, Line Items with Categories, Category Groupings, and Taxes.
    """
    if filenames is None:
        filenames = [f"doc_{i+1}" for i in range(len(docs))]

    summary_records = []
    line_item_records = []
    tax_records = []
    category_records = []

    for doc, fn in zip(docs, filenames):
        summary_records.append(get_invoice_summary_dict(doc, filename=fn))

        for idx, item in enumerate(doc.line_items or []):
            line_item_records.append({
                "File": fn,
                "Invoice Number": doc.invoice_number or "",
                "Vendor": doc.vendor.name if doc.vendor else "",
                "Item #": item.item_index if item.item_index is not None else (idx + 1),
                "Description": item.description,
                "Category": item.category or "General",
                "SKU": item.sku or "",
                "Quantity": item.quantity or 1.0,
                "Unit": item.unit_of_measure or "",
                "Unit Price": item.unit_price,
                "Discount": item.discount_amount or 0.0,
                "Total Price": item.total_price,
                "Currency": doc.currency or "",
            })

        # Category records
        grouped = group_line_items_by_category(doc.line_items or [])
        grand_total = doc.total_amount or sum(g["subtotal"] for g in grouped.values()) or 1.0
        for cat_name, data in grouped.items():
            pct = (data["subtotal"] / grand_total * 100.0) if grand_total > 0 else 0.0
            category_records.append({
                "File": fn,
                "Invoice Number": doc.invoice_number or "",
                "Category": cat_name,
                "Items Count": data["count"],
                "Total Spent": data["subtotal"],
                "% Share": f"{pct:.1f}%",
                "Currency": doc.currency or "",
            })

        for tax in (doc.taxes or []):
            tax_records.append({
                "File": fn,
                "Invoice Number": doc.invoice_number or "",
                "Tax Name": tax.name or "",
                "Rate %": tax.rate_percentage,
                "Amount": tax.amount,
                "Currency": doc.currency or "",
            })

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_summary = pd.DataFrame(summary_records)
        df_summary.to_excel(writer, sheet_name="Invoice Summaries", index=False)

        if category_records:
            df_cats = pd.DataFrame(category_records)
            df_cats.to_excel(writer, sheet_name="Category Breakdown", index=False)

        df_items = pd.DataFrame(line_item_records)
        df_items.to_excel(writer, sheet_name="Line Items", index=False)

        if tax_records:
            df_taxes = pd.DataFrame(tax_records)
            df_taxes.to_excel(writer, sheet_name="Taxes Breakdown", index=False)

    return output.getvalue()
