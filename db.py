import sqlite3
import random
import numpy as np
from datetime import datetime

DB_PATH = "greetify.db"

# ---------- Discount settings ----------
WELCOME_PERCENT = 10
MIN_BILL = 999
MAX_DISCOUNT_RS = 500

# (discount %, chance weight)  -> weights ka total 100
SPIN_TABLES = {
    "Regular": [(0, 24), (3, 30), (5, 25), (8, 12), (10, 6), (15, 2), (20, 1)],
    "Silver":  [(0, 14), (3, 25), (5, 30), (8, 15), (10, 10), (15, 5), (20, 1)],
    "Gold":    [(0, 9),  (3, 20), (5, 30), (8, 20), (10, 12), (15, 8), (20, 1)],
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Tables banao (pehle se hain to kuch nahi hoga)."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                encodings BLOB NOT NULL,
                created_at TEXT NOT NULL,
                last_visit TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                amount REAL,
                purchased_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        """)
    # purani table me naye columns jodo (pehle se ho to ignore)
    for col in ("discount_percent REAL DEFAULT 0", "discount_amount REAL DEFAULT 0"):
        try:
            with get_conn() as conn:
                conn.execute(f"ALTER TABLE purchases ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass


# ---------- Customers ----------
def add_customer(name, phone, encodings):
    blob = np.array(encodings, dtype=np.float64).tobytes()
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO customers (name, phone, encodings, created_at) VALUES (?, ?, ?, ?)",
            (name, phone, blob, now),
        )
        return cur.lastrowid


def load_known_faces():
    encodings, ids, names = [], [], []
    with get_conn() as conn:
        for row in conn.execute("SELECT id, name, encodings FROM customers"):
            data = np.frombuffer(row["encodings"], dtype=np.float64).reshape(-1, 128)
            for enc in data:
                encodings.append(enc)
                ids.append(row["id"])
                names.append(row["name"])
    return encodings, ids, names


def list_customers():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT id, name, phone FROM customers")]


def update_last_visit(customer_id):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("UPDATE customers SET last_visit = ? WHERE id = ?", (now, customer_id))


def delete_customer(customer_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM purchases WHERE customer_id = ?", (customer_id,))
        cur = conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        return cur.rowcount > 0


# ---------- Purchases ----------
def add_purchase(customer_id, item, amount, discount_percent=0, discount_amount=0):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO purchases (customer_id, item, amount, purchased_at, "
            "discount_percent, discount_amount) VALUES (?, ?, ?, ?, ?, ?)",
            (customer_id, item, amount, now, discount_percent, discount_amount),
        )


def purchase_count(customer_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM purchases WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0]


def get_customer_info(customer_id):
    """Pop-up ke liye saari jaankari: naam, last visit, history, favourite items."""
    with get_conn() as conn:
        c = conn.execute(
            "SELECT id, name, phone, last_visit FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if c is None:
            return None

        history = conn.execute(
            "SELECT item, amount, purchased_at FROM purchases WHERE customer_id = ? "
            "ORDER BY purchased_at DESC, id DESC LIMIT 40", (customer_id,)
        ).fetchall()

        top = conn.execute(
            "SELECT item, COUNT(*) AS n FROM purchases WHERE customer_id = ? "
            "GROUP BY item ORDER BY n DESC LIMIT 3", (customer_id,)
        ).fetchall()

    return {
        "id": c["id"],
        "name": c["name"],
        "phone": c["phone"],
        "last_visit": c["last_visit"],
        "last_purchase": history[0]["item"] if history else None,
        "history": [dict(r) for r in history],
        "preferences": [r["item"] for r in top],
    }


# ---------- Lucky discount ----------
def get_tier(count):
    if count >= 6:
        return "Gold"
    if count >= 3:
        return "Silver"
    return "Regular"


def make_offer(kind, percent, tier=None):
    return {"type": kind, "percent": percent, "tier": tier,
            "min_bill": MIN_BILL, "max_discount": MAX_DISCOUNT_RS}


def welcome_offer():
    return make_offer("welcome", WELCOME_PERCENT)


def spin_wheel(customer_id):
    tier = get_tier(purchase_count(customer_id))
    table = SPIN_TABLES[tier]
    percent = random.choices([p for p, _ in table], weights=[w for _, w in table])[0]
    return make_offer("lucky", percent, tier)


def calc_discount(bill, percent):
    if percent <= 0 or bill < MIN_BILL:
        return 0.0
    return round(min(bill * percent / 100, MAX_DISCOUNT_RS), 2)


def expected_discount(tier):
    table = SPIN_TABLES[tier]
    total = sum(w for _, w in table)
    return sum(p * w for p, w in table) / total


if __name__ == "__main__":
    init_db()
    print("Database ready:", DB_PATH)