"""
Quick verification script to test schema validation, exporter, and DB operations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractor.schemas import ExtractedInvoiceReceipt, LineItem, VendorInfo, TaxItem
from extractor.validator import validate_extraction
from extractor.exporter import to_json_str, to_csv_bytes, to_excel_bytes
from extractor.db import save_extraction, get_all_extractions

def test_pipeline():
    doc = ExtractedInvoiceReceipt(
        document_type="Invoice",
        invoice_number="INV-2026-001",
        issue_date="2026-09-24",
        currency="USD",
        currency_symbol="$",
        vendor=VendorInfo(name="Test Vendor Inc.", tax_id="US-12345"),
        line_items=[
            LineItem(description="Widget A", quantity=2.0, unit_price=25.0, total_price=50.0),
            LineItem(description="Service Fee", quantity=1.0, unit_price=10.0, total_price=10.0),
        ],
        subtotal=60.0,
        tax_total=6.0,
        taxes=[TaxItem(name="Sales Tax", rate_percentage=10.0, amount=6.0)],
        total_amount=66.0,
    )

    # 1. Validation test
    val = validate_extraction(doc)
    assert val.is_valid is True, f"Validation failed: {val.errors}"
    assert "Balanced" in val.math_checks["status"], f"Math checks failed: {val.math_checks}"
    print(f"Validation passed: Quality Score = {val.quality_score}%")

    # 2. Exporter tests
    json_out = to_json_str(doc)
    assert "INV-2026-001" in json_out
    csv_bytes = to_csv_bytes(doc)
    assert len(csv_bytes) > 0
    excel_bytes = to_excel_bytes([doc], filenames=["test_inv.pdf"])
    assert len(excel_bytes) > 0
    print("Exporter passed: JSON, CSV, and Excel generated successfully!")

    # 3. Database test
    rec_id = save_extraction("test_inv.pdf", doc, val.quality_score, db_path="test_db.db")
    records = get_all_extractions(db_path="test_db.db")
    assert len(records) > 0
    print(f"DB passed: Saved record ID {rec_id} and retrieved {len(records)} record(s)!")

    # 4. Local OCR test
    from extractor.local_ocr import extract_document_text
    sample_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "sample_restaurant_receipt.png")
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            ocr_text = extract_document_text(f.read(), "image/png")
        assert "BISTRO" in ocr_text or len(ocr_text) > 20, f"OCR returned insufficient text: {ocr_text}"
        print(f"Local OCR passed: extracted {len(ocr_text)} characters from sample receipt!")

    # Cleanup test db
    if os.path.exists("test_db.db"):
        os.remove("test_db.db")
    print("All pipeline tests passed cleanly!")

if __name__ == "__main__":
    test_pipeline()
