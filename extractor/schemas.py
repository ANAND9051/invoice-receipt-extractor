"""
Structured Pydantic schemas for receipts and invoices extraction.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class VendorInfo(BaseModel):
    name: Optional[str] = Field(None, description="Legal or commercial name of the merchant/vendor")
    address: Optional[str] = Field(None, description="Full physical or registered address of the vendor")
    phone: Optional[str] = Field(None, description="Vendor phone or contact number")
    email: Optional[str] = Field(None, description="Vendor contact email address")
    website: Optional[str] = Field(None, description="Vendor website URL or domain")
    tax_id: Optional[str] = Field(None, description="Vendor Tax ID, VAT number, GSTIN, EIN, or business registration number")


class CustomerInfo(BaseModel):
    name: Optional[str] = Field(None, description="Name of the buyer or client")
    company_name: Optional[str] = Field(None, description="Company/organization name of the buyer")
    billing_address: Optional[str] = Field(None, description="Billing address of the customer")
    shipping_address: Optional[str] = Field(None, description="Shipping or delivery address of the customer")
    phone: Optional[str] = Field(None, description="Customer phone number")
    email: Optional[str] = Field(None, description="Customer email address")
    tax_id: Optional[str] = Field(None, description="Customer VAT/Tax/GST registration number if applicable")


class TaxItem(BaseModel):
    name: Optional[str] = Field(None, description="Tax name/category, e.g. VAT, Sales Tax, CGST, SGST, HST")
    rate_percentage: Optional[float] = Field(None, description="Tax rate in percentage, e.g. 18.0 for 18%")
    amount: Optional[float] = Field(None, description="Total amount of this specific tax")


class LineItem(BaseModel):
    item_index: Optional[int] = Field(None, description="Sequential line item number (1, 2, 3...)")
    description: str = Field(..., description="Description or title of the product or service")
    category: Optional[str] = Field("General", description="Product category: Vegetables, Fruits, Dairy & Eggs, Bakery, Beverages, Snacks & Confectionery, Meat & Seafood, Staples & Grains, Household & Cleaning, Personal Care, Prepared Food, General")
    sku: Optional[str] = Field(None, description="Product code, SKU, or part number if present")
    quantity: Optional[float] = Field(1.0, description="Quantity purchased or billed")
    unit_of_measure: Optional[str] = Field(None, description="Unit of measurement, e.g. kg, g, pcs, pack, ltr")
    unit_price: Optional[float] = Field(None, description="Price per individual unit")
    discount_amount: Optional[float] = Field(0.0, description="Discount amount applied to this line item")
    tax_rate: Optional[float] = Field(None, description="Tax rate percentage applied to this line")
    total_price: Optional[float] = Field(None, description="Total price for this line item before or including line discount")


class PaymentInfo(BaseModel):
    payment_status: Optional[str] = Field(None, description="Status: Paid, Unpaid, Partially Paid, Due, Refunded")
    payment_method: Optional[str] = Field(None, description="Method: Cash, Credit Card, Debit Card, Bank Wire, ACH, UPI, Cheque, PayPal")
    card_brand: Optional[str] = Field(None, description="Card network: Visa, Mastercard, Amex, Discover, etc.")
    card_last_four: Optional[str] = Field(None, description="Last 4 digits of the payment card if visible")
    transaction_reference: Optional[str] = Field(None, description="Transaction ID, auth code, or reference number")


class ExtractedInvoiceReceipt(BaseModel):
    document_type: str = Field("Invoice", description="Document type: Receipt, Invoice, Tax Invoice, Utility Bill, Credit Note, Expense Voucher")
    confidence_score: Optional[float] = Field(None, description="Overall extraction confidence score between 0.0 and 1.0")
    document_language: Optional[str] = Field("en", description="Primary language of the document (e.g. en, es, fr, de, hi)")
    invoice_number: Optional[str] = Field(None, description="Invoice or receipt reference number")
    order_number: Optional[str] = Field(None, description="Associated Order, Booking, or PO Number")
    issue_date: Optional[str] = Field(None, description="Date of issuance in YYYY-MM-DD format if possible")
    due_date: Optional[str] = Field(None, description="Payment due date in YYYY-MM-DD format if possible")
    payment_terms: Optional[str] = Field(None, description="Terms of payment, e.g. Due on Receipt, Net 30, Net 15")
    currency: Optional[str] = Field(None, description="Standard 3-letter currency code, e.g. USD, EUR, GBP, INR, CAD, AUD, JPY")
    currency_symbol: Optional[str] = Field(None, description="Currency symbol, e.g. $, €, £, ₹, ¥")
    
    vendor: Optional[VendorInfo] = Field(default_factory=VendorInfo, description="Vendor / Merchant details")
    customer: Optional[CustomerInfo] = Field(default_factory=CustomerInfo, description="Buyer / Customer details")
    line_items: List[LineItem] = Field(default_factory=list, description="List of all purchased items or billed line items")
    
    subtotal: Optional[float] = Field(None, description="Subtotal amount before taxes and additional fees")
    discount_total: Optional[float] = Field(0.0, description="Total discount amount deducted")
    taxes: List[TaxItem] = Field(default_factory=list, description="Itemized tax breakdowns")
    tax_total: Optional[float] = Field(0.0, description="Total tax amount across all tax items")
    shipping_fee: Optional[float] = Field(0.0, description="Shipping, delivery, or freight charges")
    tip_or_gratuity: Optional[float] = Field(0.0, description="Tip, gratuity, or service charge if applicable")
    total_amount: Optional[float] = Field(None, description="Final grand total amount payable")
    amount_paid: Optional[float] = Field(None, description="Amount already paid if indicated")
    balance_due: Optional[float] = Field(None, description="Remaining balance due to be paid")
    
    payment: Optional[PaymentInfo] = Field(default_factory=PaymentInfo, description="Payment transaction details")
    notes_or_terms: Optional[str] = Field(None, description="Additional notes, terms, bank details, or footer text")
