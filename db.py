import sqlite3
import numpy as np
from datetime import datetime

DB_PATH = "greetify.db"


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


def add_customer(name, phone, encodings):
    """Naya customer save karo. encodings = chehre ke numbers ki list."""
    blob = np.array(encodings, dtype=np.float64).tobytes()
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO customers (name, phone, encodings, created_at) VALUES (?, ?, ?, ?)",
            (name, phone, blob, now),
        )
        return cur.lastrowid


def load_known_faces():
    """Saare customers ke chehre load karo. Return: encodings, ids, names (teeno parallel lists)."""
    encodings, ids, names = [], [], []
    with get_conn() as conn:
        for row in conn.execute("SELECT id, name, encodings FROM customers"):
            data = np.frombuffer(row["encodings"], dtype=np.float64).reshape(-1, 128)
            for enc in data:
                encodings.append(enc)
                ids.append(row["id"])
                names.append(row["name"])
    return encodings, ids, names


def add_purchase(customer_id, item, amount):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO purchases (customer_id, item, amount, purchased_at) VALUES (?, ?, ?, ?)",
            (customer_id, item, amount, now),
        )


def update_last_visit(customer_id):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("UPDATE customers SET last_visit = ? WHERE id = ?", (now, customer_id))


def get_customer_info(customer_id):
    """Pop-up ke liye saari jaankari: naam, last visit, pichli khareedari, favourite items."""
    with get_conn() as conn:
        c = conn.execute(
            "SELECT id, name, phone, last_visit FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if c is None:
            return None

        last = conn.execute(
            "SELECT item, purchased_at FROM purchases WHERE customer_id = ? "
            "ORDER BY purchased_at DESC LIMIT 1", (customer_id,)
        ).fetchone()

        top = conn.execute(
            "SELECT item, COUNT(*) AS n FROM purchases WHERE customer_id = ? "
            "GROUP BY item ORDER BY n DESC LIMIT 3", (customer_id,)
        ).fetchall()

    return {
        "id": c["id"],
        "name": c["name"],
        "phone": c["phone"],
        "last_visit": c["last_visit"],
        "last_purchase": last["item"] if last else None,
        "preferences": [r["item"] for r in top],
    }


def list_customers():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT id, name, phone FROM customers")]


if __name__ == "__main__":
    init_db()
    print("Database ready:", DB_PATH)