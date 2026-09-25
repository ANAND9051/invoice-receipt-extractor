import json
import json_repair

# Scenario 1: Unescaped quotes inside string
broken_1 = '{"vendor": {"name": "Star "Hypermarket""}, "total_amount": 150.0}'
try:
    json.loads(broken_1)
except Exception as e:
    print("Standard json.loads error:", e)

fixed_1 = json_repair.loads(broken_1)
print("json_repair fixed 1:", fixed_1)

# Scenario 2: Missing comma between items
broken_2 = '{"line_items": [{"description": "Item 1" "price": 10.0}]}'
try:
    json.loads(broken_2)
except Exception as e:
    print("Standard json.loads error 2:", e)

fixed_2 = json_repair.loads(broken_2)
print("json_repair fixed 2:", fixed_2)

# Scenario 3: Truncated JSON at char 921
broken_3 = '{"vendor": {"name": "Trent Hypermarket"}, "line_items": [{"description": "Biscuits", "quantity": 2, "price": 40.0}, {"description": "Maggi Noodles 280g'
fixed_3 = json_repair.loads(broken_3)
print("json_repair fixed 3:", fixed_3)
