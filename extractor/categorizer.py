"""
Intelligent Auto-Categorization & Product Grouping for Supermarket & Mart Receipts.
Automatically classifies line items into intuitive groups (Vegetables, Fruits, Dairy, Snacks, etc.).
"""

import re
from typing import List, Dict, Any, Optional
from extractor.schemas import ExtractedInvoiceReceipt, LineItem

# Category metadata with standard names, display emojis, and keyword matching patterns
CATEGORY_RULES: Dict[str, Dict[str, Any]] = {
    "Vegetables": {
        "emoji": "🥬",
        "keywords": [
            "tomato", "potato", "onion", "carrot", "cabbage", "cauliflower", "spinach", "palak",
            "broccoli", "cucumber", "capsicum", "pepper", "chili", "chilli", "mirch", "ginger",
            "adrak", "garlic", "lahsun", "coriander", "dhaniya", "mint", "pudina", "peas",
            "matar", "beans", "brinjal", "eggplant", "baingan", "bhindi", "okra", "ladyfinger",
            "mushroom", "lettuce", "zucchini", "beetroot", "radish", "mooli", "pumpkin", "kaddu",
            "methi", "fenugreek", "karela", "bitter gourd", "lauki", "bottle gourd", "tinda",
            "parwal", "sweet potato", "corn", "baby corn", "veg", "vegetable", "greens", "sprouts"
        ]
    },
    "Fruits": {
        "emoji": "🍎",
        "keywords": [
            "apple", "banana", "orange", "mango", "grapes", "strawberry", "watermelon", "melon",
            "pineapple", "papaya", "guava", "pomegranate", "anar", "kiwi", "lemon", "nimbu",
            "lime", "avocado", "peach", "pear", "plum", "cherry", "berry", "coconut", "nariyal",
            "dates", "khajoor", "figs", "muskmelon", "kharbooja", "mosambi", "sweet lime",
            "litchi", "lychee", "custard apple", "sitaphal", "fruit", "berries", "grapefruit"
        ]
    },
    "Dairy & Eggs": {
        "emoji": "🥛",
        "keywords": [
            "milk", "doodh", "butter", "makhan", "amul", "cheese", "paneer", "curd", "dahi",
            "yogurt", "ghee", "cream", "malai", "egg", "eggs", "anda", "lassi", "tofu",
            "buttermilk", "chaas", "cheddar", "mozzarella", "gouda", "mayo", "mayonnaise"
        ]
    },
    "Bakery & Breads": {
        "emoji": "🍞",
        "keywords": [
            "bread", "bun", "buns", "pav", "roti", "paratha", "naan", "kulcha", "toast",
            "rusk", "rusks", "pita", "bagel", "croissant", "muffin", "cake", "pastry",
            "bakery", "brownie", "doughnut", "donut", "tortilla", "wrap"
        ]
    },
    "Snacks & Confectionery": {
        "emoji": "🍫",
        "keywords": [
            "chips", "biscuit", "biscuits", "cookie", "cookies", "chocolate", "namkeen",
            "bhujia", "sev", "kurkure", "lays", "doritos", "bingo", "wafer", "wafers",
            "popcorn", "candy", "toffee", "bar", "noodles", "maggi", "pasta", "snack",
            "snacks", "pringles", "kitkat", "dairy milk", "munch", "snickers", "choco",
            "munchies", "haldiram", "bikaji", "parle", "britannia", "oreo", "bourbon"
        ]
    },
    "Beverages": {
        "emoji": "☕",
        "keywords": [
            "coffee", "tea", "chai", "juice", "water", "soda", "cola", "pepsi", "sprite",
            "coke", "fanta", "thums up", "limca", "maaza", "frooti", "beer", "wine",
            "energy drink", "red bull", "shake", "syrup", "squash", "drink", "beverage",
            "tonic", "mineral water", "kinley", "aquafina", "bisleri", "espresso", "latte"
        ]
    },
    "Staples & Grains": {
        "emoji": "🍚",
        "keywords": [
            "rice", "chawal", "basmati", "atta", "flour", "gehu", "wheat", "dal", "daal",
            "lentils", "pulse", "pulses", "sugar", "cheeni", "salt", "namak", "oil",
            "sunflower", "mustard", "sarson", "soya", "soyabean", "olive oil", "spices",
            "masala", "grain", "grains", "cereal", "cereals", "oats", "muesli", "cornflakes",
            "maida", "sooji", "suji", "besan", "rava", "chana", "rajma", "moong", "toor",
            "urad", "poha", "vermicelli", "seviyan", "aashirvaad", "fortune", "tata salt"
        ]
    },
    "Meat & Seafood": {
        "emoji": "🍗",
        "keywords": [
            "chicken", "mutton", "lamb", "fish", "machhli", "prawn", "prawns", "shrimp",
            "pork", "bacon", "sausage", "seafood", "beef", "meat", "salmon", "pomfret",
            "keema", "fillet", "tuna", "crab", "lobster"
        ]
    },
    "Household & Cleaning": {
        "emoji": "🧼",
        "keywords": [
            "soap", "detergent", "surf", "surf excel", "tide", "ariel", "vim", "dishwash",
            "cleaner", "phenyl", "tissue", "tissues", "napkin", "paper towel", "mop",
            "sponge", "foil", "aluminum foil", "bag", "garbage bag", "repellent", "harpic",
            "disinfectant", "lizol", "all out", "good knight", "scrubber", "colin", "comfort"
        ]
    },
    "Personal Care": {
        "emoji": "🧴",
        "keywords": [
            "shampoo", "toothpaste", "colgate", "sensodyne", "close up", "brush", "toothbrush",
            "face wash", "cream", "fair & lovely", "nivea", "lotion", "deodorant", "deo",
            "perfume", "fragrance", "razor", "shaving", "gillette", "sanitary", "pad",
            "stayfree", "whisper", "hair oil", "parachute", "body wash", "handwash", "dettol",
            "lifebuoy", "conditioner", "sunscreen"
        ]
    },
    "Prepared Food & Dining": {
        "emoji": "🍱",
        "keywords": [
            "burger", "pizza", "fries", "sandwich", "soup", "salad", "biryani", "curry",
            "paneer butter", "dal makhani", "combo", "meal", "tandoori", "tikka", "platter",
            "starter", "main course", "dessert", "ice cream", "kulfi", "gulab jamun", "beverage"
        ]
    }
}


def classify_item_category(description: str, existing_category: Optional[str] = None) -> str:
    """
    Classifies a product description into a standard category.
    Honors any specific existing category unless it is empty or 'General'.
    """
    if existing_category and existing_category.strip() not in ["", "General", "Other", "Unknown"]:
        # Standardize matching
        for std_cat in CATEGORY_RULES:
            if existing_category.lower() in std_cat.lower() or std_cat.lower() in existing_category.lower():
                return std_cat
        return existing_category.strip().title()

    desc_lower = description.lower()

    # Score categories by matched keywords
    best_category = "General"
    max_matches = 0

    for category, meta in CATEGORY_RULES.items():
        matches = 0
        for kw in meta["keywords"]:
            # Word boundary check for high precision
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, desc_lower):
                matches += 1
            elif kw in desc_lower and len(kw) > 4:
                matches += 1

        if matches > max_matches:
            max_matches = matches
            best_category = category

    return best_category


def get_category_emoji(category: str) -> str:
    """Returns the visual emoji for a category."""
    for cat, meta in CATEGORY_RULES.items():
        if cat.lower() in category.lower() or category.lower() in cat.lower():
            return meta["emoji"]
    return "📦"


def group_line_items_by_category(line_items: List[LineItem]) -> Dict[str, Dict[str, Any]]:
    """
    Groups line items by category, computing item count and category subtotal.
    Returns:
    {
        "Vegetables": {
            "emoji": "🥬",
            "count": 4,
            "subtotal": 180.50,
            "items": [LineItem, LineItem, ...]
        },
        ...
    }
    """
    grouped: Dict[str, Dict[str, Any]] = {}

    for item in line_items:
        cat = item.category or "General"
        # Standardize category name
        matched_cat = cat
        for standard_cat in CATEGORY_RULES:
            if standard_cat.lower() in cat.lower() or cat.lower() in standard_cat.lower():
                matched_cat = standard_cat
                break

        if matched_cat not in grouped:
            grouped[matched_cat] = {
                "emoji": get_category_emoji(matched_cat),
                "count": 0,
                "subtotal": 0.0,
                "items": []
            }

        grouped[matched_cat]["count"] += 1
        item_price = item.total_price or ((item.quantity or 1.0) * (item.unit_price or 0.0))
        if item_price:
            grouped[matched_cat]["subtotal"] += round(item_price, 2)
        grouped[matched_cat]["items"].append(item)

    # Sort groups by subtotal descending
    sorted_grouped = dict(sorted(grouped.items(), key=lambda kv: kv[1]["subtotal"], reverse=True))
    return sorted_grouped


def apply_auto_categorization(doc: ExtractedInvoiceReceipt) -> ExtractedInvoiceReceipt:
    """
    Processes all line items in a receipt document, assigning categories
    intelligently using keywords if not already tagged.
    """
    if not doc.line_items:
        return doc

    for item in doc.line_items:
        item.category = classify_item_category(
            description=item.description,
            existing_category=item.category
        )

    return doc
