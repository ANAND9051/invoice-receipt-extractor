"""
Generates synthetic sample receipt image and sample invoice PDF for testing.
"""

from PIL import Image, ImageDraw, ImageFont
import pypdf
from pypdf import PdfWriter
import io
import os

SAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_sample_receipt():
    """Generates a realistic receipt PNG."""
    width, height = 450, 700
    img = Image.new("RGB", (width, height), color=(250, 250, 248))
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((150, 30), "BISTRO DELIGHT", fill=(20, 20, 20))
    draw.text((130, 50), "142 Market Street, Suite 4", fill=(80, 80, 80))
    draw.text((145, 65), "San Francisco, CA 94105", fill=(80, 80, 80))
    draw.text((155, 80), "Tel: (415) 555-0199", fill=(80, 80, 80))
    draw.text((140, 95), "Tax ID: US-8829104-SF", fill=(80, 80, 80))

    # Divider line
    draw.line([(30, 120), (420, 120)], fill=(180, 180, 180), width=1)

    # Receipt Info
    draw.text((30, 135), "Receipt #: REC-2026-9041", fill=(30, 30, 30))
    draw.text((30, 155), "Date: 2026-09-24 19:42", fill=(30, 30, 30))
    draw.text((30, 175), "Server: Sarah M. (Table 12)", fill=(30, 30, 30))
    draw.text((30, 195), "Order Type: Dine-In", fill=(30, 30, 30))

    draw.line([(30, 220), (420, 220)], fill=(180, 180, 180), width=1)

    # Column Headers
    draw.text((30, 230), "QTY  ITEM", fill=(40, 40, 40))
    draw.text((350, 230), "AMOUNT", fill=(40, 40, 40))

    draw.line([(30, 250), (420, 250)], fill=(200, 200, 200), width=1)

    # Line Items
    items = [
        ("2", "Artisan Truffle Burger", "2 x $18.50", "37.00"),
        ("1", "Crispy Rosemary Fries", "1 x $7.50", "7.50"),
        ("2", "Sparkling San Pellegrino", "2 x $4.00", "8.00"),
        ("1", "Warm Molten Lava Cake", "1 x $9.50", "9.50"),
    ]

    y = 265
    for qty, name, subtext, price in items:
        draw.text((30, y), f"{qty}   {name}", fill=(20, 20, 20))
        draw.text((60, y + 16), subtext, fill=(110, 110, 110))
        draw.text((360, y), f"${price}", fill=(20, 20, 20))
        y += 42

    draw.line([(30, y + 10), (420, y + 10)], fill=(180, 180, 180), width=1)
    y += 25

    # Totals
    draw.text((220, y), "Subtotal:", fill=(50, 50, 50))
    draw.text((360, y), "$62.00", fill=(50, 50, 50))
    y += 24

    draw.text((220, y), "Sales Tax (8.5%):", fill=(50, 50, 50))
    draw.text((360, y), "$5.27", fill=(50, 50, 50))
    y += 24

    draw.text((220, y), "Tip / Gratuity (18%):", fill=(50, 50, 50))
    draw.text((360, y), "$11.16", fill=(50, 50, 50))
    y += 28

    draw.line([(210, y), (420, y)], fill=(100, 100, 100), width=2)
    y += 10

    draw.text((220, y), "TOTAL:", fill=(10, 10, 10))
    draw.text((355, y), "$78.43", fill=(10, 10, 10))
    y += 40

    # Payment Info
    draw.text((30, y), "Payment: VISA ending in 4921", fill=(60, 60, 60))
    y += 18
    draw.text((30, y), "Auth Code: 839201 | Status: APPROVED", fill=(60, 60, 60))
    y += 35

    draw.text((120, y), "Thank You for Dining With Us!", fill=(70, 70, 70))
    draw.text((140, y + 18), "Please Visit Again Soon", fill=(100, 100, 100))

    receipt_path = os.path.join(SAMPLES_DIR, "sample_restaurant_receipt.png")
    img.save(receipt_path)
    print(f"Generated sample receipt at {receipt_path}")


def generate_sample_invoice():
    """Generates a clean synthetic invoice PDF."""
    from PIL import ImageDraw

    # Generate page as high-res image then convert to PDF
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Top brand bar
    draw.rectangle([(0, 0), (800, 15)], fill=(41, 128, 185))

    # Header
    draw.text((50, 45), "NOVASOFT CLOUD SOLUTIONS INC.", fill=(30, 40, 60))
    draw.text((50, 68), "742 Evergreen Terrace, Suite 500", fill=(100, 100, 100))
    draw.text((50, 85), "Seattle, WA 98101, United States", fill=(100, 100, 100))
    draw.text((50, 102), "contact@novasoftcloud.com | www.novasoftcloud.com", fill=(100, 100, 100))
    draw.text((50, 119), "EIN / Tax ID: US-94-3829104", fill=(100, 100, 100))

    # Right side Invoice Title
    draw.text((550, 45), "INVOICE", fill=(41, 128, 185))
    draw.text((550, 75), "Invoice #: INV-2026-0819", fill=(50, 50, 50))
    draw.text((550, 95), "PO Number: PO-77312", fill=(50, 50, 50))
    draw.text((550, 115), "Issue Date: 2026-09-15", fill=(50, 50, 50))
    draw.text((550, 135), "Due Date: 2026-10-15", fill=(50, 50, 50))
    draw.text((550, 155), "Terms: Net 30", fill=(50, 50, 50))

    draw.line([(50, 185), (750, 185)], fill=(220, 220, 220), width=1)

    # Bill To / Ship To
    draw.text((50, 205), "BILLED TO:", fill=(41, 128, 185))
    draw.text((50, 225), "Apex Global Logistics LLC", fill=(30, 30, 30))
    draw.text((50, 245), "Attn: Finance & Accounts Dept.", fill=(80, 80, 80))
    draw.text((50, 265), "1200 Industrial Parkway, Building B", fill=(80, 80, 80))
    draw.text((50, 285), "Chicago, IL 60607", fill=(80, 80, 80))
    draw.text((50, 305), "Client Tax ID: US-36-8192031", fill=(80, 80, 80))

    draw.text((450, 205), "PAYMENT DETAILS:", fill=(41, 128, 185))
    draw.text((450, 225), "Bank: JPMorgan Chase Bank, N.A.", fill=(60, 60, 60))
    draw.text((450, 245), "Account Name: NovaSoft Cloud Inc.", fill=(60, 60, 60))
    draw.text((450, 265), "Routing (ABA): 021000021", fill=(60, 60, 60))
    draw.text((450, 285), "Account #: 8492048192", fill=(60, 60, 60))
    draw.text((450, 305), "Status: UNPAID (Due in 30 days)", fill=(200, 50, 50))

    # Table Header
    draw.rectangle([(50, 345), (750, 375)], fill=(240, 244, 248))
    draw.text((65, 353), "ITEM / DESCRIPTION", fill=(50, 60, 80))
    draw.text((380, 353), "SKU", fill=(50, 60, 80))
    draw.text((460, 353), "QTY", fill=(50, 60, 80))
    draw.text((540, 353), "UNIT PRICE", fill=(50, 60, 80))
    draw.text((660, 353), "AMOUNT (USD)", fill=(50, 60, 80))

    items = [
        ("Enterprise Cloud Kubernetes Hosting (Sep 2026)", "HOST-K8S-ENT", "1", "$1,450.00", "$1,450.00"),
        ("Dedicated Database Cluster Backup & Replication", "DB-REPL-01", "2", "$320.00", "$640.00"),
        ("DevOps Engineering Architecture Consulting (Hours)", "CONS-DEV-HR", "15", "$150.00", "$2,250.00"),
        ("SSL Wildcard Multi-Domain Certificate (Annual)", "SEC-SSL-09", "1", "$210.00", "$210.00"),
    ]

    y = 390
    for desc, sku, qty, unit_price, amt in items:
        draw.text((65, y), desc, fill=(30, 30, 30))
        draw.text((380, y), sku, fill=(100, 100, 100))
        draw.text((470, y), qty, fill=(30, 30, 30))
        draw.text((550, y), unit_price, fill=(30, 30, 30))
        draw.text((670, y), amt, fill=(30, 30, 30))
        y += 28
        draw.line([(50, y), (750, y)], fill=(235, 235, 235), width=1)
        y += 12

    # Financial Summary
    y = 570
    draw.text((480, y), "Subtotal:", fill=(80, 80, 80))
    draw.text((660, y), "$4,550.00", fill=(30, 30, 30))
    y += 26

    draw.text((480, y), "Client Volume Discount (5%):", fill=(80, 80, 80))
    draw.text((655, y), "-$227.50", fill=(30, 130, 60))
    y += 26

    draw.text((480, y), "State Sales Tax (8.25%):", fill=(80, 80, 80))
    draw.text((660, y), "$356.61", fill=(30, 30, 30))
    y += 30

    draw.rectangle([(470, y), (750, y + 42)], fill=(245, 247, 250))
    draw.text((480, y + 12), "TOTAL AMOUNT DUE:", fill=(30, 40, 60))
    draw.text((645, y + 12), "$4,679.11 USD", fill=(41, 128, 185))

    # Footer
    draw.line([(50, 950), (750, 950)], fill=(220, 220, 220), width=1)
    draw.text((50, 970), "Payment Terms: Net 30 days from date of invoice. Late payments subject to 1.5% monthly finance charge.", fill=(120, 120, 120))
    draw.text((50, 990), "Thank you for your business! For billing inquiries, email billing@novasoftcloud.com.", fill=(120, 120, 120))

    pdf_path = os.path.join(SAMPLES_DIR, "sample_invoice.pdf")
    img.save(pdf_path, "PDF", resolution=100.0)
    print(f"Generated sample invoice PDF at {pdf_path}")


if __name__ == "__main__":
    generate_sample_receipt()
    generate_sample_invoice()
