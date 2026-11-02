import db


def parse_amount(text):
    """45k, 1.5k, 2L, 1,200, Rs 500, 499.50 sab chalega."""
    t = text.strip().lower()
    t = t.replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").strip()

    multiplier = 1
    if t.endswith("k"):
        multiplier, t = 1_000, t[:-1]
    elif t.endswith("l") or t.endswith("lakh"):
        multiplier, t = 100_000, t.rstrip("lakh")
    elif t.endswith("cr"):
        multiplier, t = 10_000_000, t[:-2]

    return round(float(t) * multiplier, 2)


customers = db.list_customers()
if not customers:
    raise SystemExit("Pehle koi customer enroll karo.")

for c in customers:
    print(f"{c['id']}: {c['name']} ({c['phone']})")

customer_id = int(input("Customer ID: "))
item = input("Kya khareeda (jaise Blue Shirt): ").strip()

while True:
    try:
        amount = parse_amount(input("Amount (jaise 499.50, 45k, 2L): "))
        break
    except ValueError:
        print("Amount samajh nahi aaya. Dobara likho (jaise 499.50 ya 45k).")

db.add_purchase(customer_id, item, amount)
print(f"Purchase saved! {item} = Rs {amount:,.2f}")