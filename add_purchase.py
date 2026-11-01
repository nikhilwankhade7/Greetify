import db

customers = db.list_customers()
if not customers:
    raise SystemExit("Pehle koi customer enroll karo.")

for c in customers:
    print(f"{c['id']}: {c['name']} ({c['phone']})")

customer_id = int(input("Customer ID: "))
item = input("Kya khareeda (jaise Blue Shirt): ").strip()
amount = float(input("Amount: "))

db.add_purchase(customer_id, item, amount)
print("Purchase saved!")