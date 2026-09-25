"""
Validation and data integrity verification for extracted receipt and invoice data.
"""

from typing import Dict, Any, List
from datetime import datetime
from extractor.schemas import ExtractedInvoiceReceipt


class ValidationResult:
    def __init__(self):
        self.is_valid: bool = True
        self.quality_score: int = 100
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.math_checks: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "quality_score": self.quality_score,
            "warnings": self.warnings,
            "errors": self.errors,
            "math_checks": self.math_checks,
        }


def validate_extraction(data: ExtractedInvoiceReceipt) -> ValidationResult:
    """
    Validates mathematical consistency, dates, and data completeness.
    """
    res = ValidationResult()
    deductions = 0

    # 1. Critical Field Checks
    if not data.vendor or not data.vendor.name:
        res.warnings.append("Missing vendor or merchant name.")
        deductions += 15

    if not data.issue_date:
        res.warnings.append("Missing transaction / issue date.")
        deductions += 15

    if data.total_amount is None:
        res.errors.append("Critical: Total amount could not be determined.")
        res.is_valid = False
        deductions += 30

    if not data.currency:
        res.warnings.append("Currency not explicitly identified.")
        deductions += 10

    if not data.line_items:
        res.warnings.append("No itemized line items found.")
        deductions += 15

    # 2. Line Items Math Check
    calculated_items_total = 0.0
    has_valid_items_total = False
    
    if data.line_items:
        items_sum = 0.0
        item_math_issues = 0
        for idx, item in enumerate(data.line_items):
            qty = item.quantity or 1.0
            price = item.unit_price
            tot = item.total_price

            if price is not None and tot is not None:
                calc = round(qty * price, 2)
                # Allow for discount on line item
                discount = item.discount_amount or 0.0
                calc_discounted = round(calc - discount, 2)
                if abs(calc - tot) > 0.05 and abs(calc_discounted - tot) > 0.05:
                    item_math_issues += 1

            if tot is not None:
                items_sum += tot

        calculated_items_total = round(items_sum, 2)
        has_valid_items_total = True
        
        if item_math_issues > 0:
            res.warnings.append(f"{item_math_issues} line item(s) have unit price * quantity mismatch.")
            deductions += 10

    # 3. Financial Totals Math Check
    subtotal = data.subtotal if data.subtotal is not None else (calculated_items_total if has_valid_items_total else None)
    discount = data.discount_total or 0.0
    tax = data.tax_total or 0.0
    shipping = data.shipping_fee or 0.0
    tip = data.tip_or_gratuity or 0.0
    total = data.total_amount

    math_status = "Inconclusive"
    discrepancy = 0.0

    if subtotal is not None and total is not None:
        # Check Formula 1: Subtotal is pre-discount (typical for B2B invoices)
        exp_pre_discount = round(subtotal - discount + tax + shipping + tip, 2)
        diff_pre_discount = round(abs(exp_pre_discount - total), 2)

        # Check Formula 2: Subtotal is already post-discount (typical for retail/supermarkets with 'Total Savings')
        exp_post_discount = round(subtotal + tax + shipping + tip, 2)
        diff_post_discount = round(abs(exp_post_discount - total), 2)

        # Best matching formula
        if diff_pre_discount <= 0.08 or (discount > 0 and diff_post_discount <= 0.08):
            math_status = "Balanced (Exact Match)"
            discrepancy = min(diff_pre_discount, diff_post_discount)
            expected_total = total
        elif diff_pre_discount <= 1.00 or (discount > 0 and diff_post_discount <= 1.00):
            discrepancy = min(diff_pre_discount, diff_post_discount)
            math_status = f"Minor Rounding Difference ({discrepancy:.2f})"
            expected_total = total
        else:
            discrepancy = diff_pre_discount
            expected_total = exp_pre_discount
            math_status = f"Discrepancy Detected (Diff: {discrepancy:.2f})"
            res.warnings.append(
                f"Math discrepancy: Subtotal ({subtotal}) - Discount ({discount}) + Tax ({tax}) + Shipping/Tip ({shipping+tip}) = {expected_total}, but Total is {total}."
            )
            deductions += 15

    res.math_checks = {
        "status": math_status,
        "calculated_line_items_sum": calculated_items_total if has_valid_items_total else None,
        "subtotal": subtotal,
        "tax_total": tax,
        "discount_total": discount,
        "shipping_and_tip": round(shipping + tip, 2),
        "expected_total": round(subtotal - discount + tax + shipping + tip, 2) if subtotal is not None else None,
        "reported_total": total,
        "discrepancy": discrepancy,
    }

    # 4. Date Logic Checks
    if data.issue_date:
        try:
            # Check ISO format
            datetime.strptime(data.issue_date[:10], "%Y-%m-%d")
        except ValueError:
            res.warnings.append(f"Issue date '{data.issue_date}' is not standard ISO YYYY-MM-DD.")

    if data.issue_date and data.due_date:
        try:
            issue_dt = datetime.strptime(data.issue_date[:10], "%Y-%m-%d")
            due_dt = datetime.strptime(data.due_date[:10], "%Y-%m-%d")
            if due_dt < issue_dt:
                res.warnings.append(f"Due date ({data.due_date}) is earlier than Issue date ({data.issue_date}).")
                deductions += 5
        except Exception:
            pass

    # Final Quality Score (bounded 0 to 100)
    res.quality_score = max(0, min(100, 100 - deductions))
    return res
