import db

customers = db.list_customers()
if not customers:
    raise SystemExit("Koi customer nahi hai.")

for c in customers:
    print(f"{c['id']}: {c['name']} ({c['phone']})")

customer_id = int(input("Delete karne wale customer ki ID: "))
confirm = input("Pakka delete karna hai? (y/n): ").strip().lower()

if confirm == "y":
    if db.delete_customer(customer_id):
        print("Customer delete ho gaya.")
    else:
        print("Ye ID mili nahi.")
else:
    print("Cancel kiya.")