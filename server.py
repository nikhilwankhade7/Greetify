import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import db
import logging


class _HideFrameLogs(logging.Filter):
    def filter(self, record):
        return "/frame" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_HideFrameLogs())

app = FastAPI(title="Greetify API")
db.init_db()


class PurchaseIn(BaseModel):
    item: str
    amount: float = 0


class ItemIn(BaseModel):
    item: str
    amount: float = 0


class CartIn(BaseModel):
    items: list[ItemIn]


class UnknownIn(BaseModel):
    encodings: list[list[float]]


class RegisterIn(BaseModel):
    name: str
    phone: str = ""
    consent: bool = False


# consent ka record rakhne ke liye column (pehle se ho to ignore)
try:
    with db.get_conn() as _c:
        _c.execute("ALTER TABLE customers ADD COLUMN consent_at TEXT")
except Exception:
    pass


# ---------- Live messages (SSE + WebSocket dono) ----------
class ConnectionManager:
    def __init__(self):
        self.connections = []   # WebSocket clients
        self.queues = []        # SSE clients

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        for q in list(self.queues):
            q.put_nowait(data)
        for ws in list(self.connections):
            try:
                await ws.send_text(data)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


@app.get("/events")
async def events():
    q = asyncio.Queue()
    manager.queues.append(q)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            yield ": connected\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            if q in manager.queues:
                manager.queues.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        manager.disconnect(ws)


# ---------- Pages ----------
@app.get("/")
def home():
    return {"app": "Greetify", "status": "running"}


@app.get("/dashboard")
def dashboard():
    return FileResponse("dashboard.html")


@app.get("/pay")
def pay_page():
    return FileResponse("pay.html")


# ---------- Alert (recognize.py yahan bhejta hai) ----------
@app.post("/alert/{customer_id}")
async def send_alert(customer_id: int):
    info = db.get_customer_info(customer_id)
    if info is None:
        return {"ok": False, "error": "Customer not found"}
    await manager.broadcast({"type": "returning_customer", "customer": info})
    return {"ok": True}


# ---------- Customers ----------
@app.get("/customers")
def customers():
    return db.list_customers()


@app.get("/customers/{customer_id}")
def customer(customer_id: int):
    return db.get_customer_info(customer_id) or {"error": "Customer not found"}


@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int):
    return {"ok": db.delete_customer(customer_id)}


@app.post("/customers/{customer_id}/purchases")
def add_purchase(customer_id: int, p: PurchaseIn):
    db.add_purchase(customer_id, p.item, p.amount)
    return {"ok": True}


@app.post("/customers/{customer_id}/purchases/bulk")
def add_purchases_bulk(customer_id: int, cart: CartIn):
    for it in cart.items:
        db.add_purchase(customer_id, it.item, it.amount)
    return {"ok": True, "count": len(cart.items)}


# ---------- Naya customer register ----------
pending_new = {"encodings": None}


@app.post("/unknown")
async def unknown(u: UnknownIn):
    if len(u.encodings) < 2:
        return {"ok": False, "error": "Kam samples"}
    pending_new["encodings"] = u.encodings
    await manager.broadcast({"type": "new_customer"})
    return {"ok": True}


@app.post("/unknown/skip")
async def unknown_skip():
    pending_new["encodings"] = None
    return {"ok": True}


@app.post("/register")
async def register(r: RegisterIn):
    name = r.name.strip()
    phone = "".join(ch for ch in r.phone if ch.isdigit() or ch == "+")
    if not r.consent:
        return {"ok": False, "error": "Customer ki permission zaroori hai"}
    if not name:
        return {"ok": False, "error": "Naam likho"}
    if phone and len(phone) < 10:
        return {"ok": False, "error": "Phone number 10 digit ka hona chahiye"}
    if not pending_new["encodings"]:
        return {"ok": False, "error": "Chehra nahi mila, customer ko camera ke saamne laao"}

    cid = db.add_customer(name, phone, pending_new["encodings"])
    from datetime import datetime
    with db.get_conn() as c:
        c.execute("UPDATE customers SET consent_at = ? WHERE id = ?",
                  (datetime.now().isoformat(timespec="seconds"), cid))
    pending_new["encodings"] = None
    return {"ok": True, "customer": db.get_customer_info(cid)}


# ---------- Aaj ki report ----------
@app.get("/stats/today")
def stats_today():
    from datetime import datetime
    today = datetime.now().date().isoformat() + "%"
    with db.get_conn() as c:
        try:
            row = c.execute(
                "SELECT COUNT(*) AS items, COALESCE(SUM(amount),0) AS sales, "
                "COALESCE(SUM(discount_amount),0) AS disc, COUNT(DISTINCT customer_id) AS buyers "
                "FROM purchases WHERE purchased_at LIKE ?", (today,)).fetchone()
        except Exception:
            row = c.execute(
                "SELECT COUNT(*) AS items, COALESCE(SUM(amount),0) AS sales, 0 AS disc, "
                "COUNT(DISTINCT customer_id) AS buyers FROM purchases WHERE purchased_at LIKE ?",
                (today,)).fetchone()
        top = c.execute(
            "SELECT item, COUNT(*) AS n, COALESCE(SUM(amount),0) AS total FROM purchases "
            "WHERE purchased_at LIKE ? GROUP BY item ORDER BY n DESC, total DESC LIMIT 5",
            (today,)).fetchall()
        visitors = c.execute(
            "SELECT COUNT(*) FROM customers WHERE last_visit LIKE ?", (today,)).fetchone()[0]
        new_customers = c.execute(
            "SELECT COUNT(*) FROM customers WHERE created_at LIKE ?", (today,)).fetchone()[0]
    return {
        "visitors": visitors, "new_customers": new_customers, "buyers": row["buyers"],
        "items": row["items"], "sales": round(row["sales"], 2),
        "discount": round(row["disc"], 2),
        "top_items": [dict(r) for r in top],
    }


# ---------- Live video ----------
latest_frame = {"jpg": None}


@app.post("/frame")
async def receive_frame(request: Request):
    latest_frame["jpg"] = await request.body()
    return {"ok": True}


@app.get("/video")
async def video():
    async def stream():
        while True:
            jpg = latest_frame["jpg"]
            if jpg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            await asyncio.sleep(0.05)
    return StreamingResponse(stream(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---------- Scratch card checkout ----------
pending_checkouts = {}


@app.post("/customers/{customer_id}/checkout")
async def start_checkout(customer_id: int, cart: CartIn):
    info = db.get_customer_info(customer_id)
    if info is None:
        return {"ok": False, "error": "Customer not found"}
    if not cart.items:
        return {"ok": False, "error": "No items"}

    bill = round(sum(i.amount for i in cart.items), 2)
    if bill < db.MIN_BILL:
        offer = db.make_offer("none", 0)
    elif db.purchase_count(customer_id) == 0:
        offer = db.welcome_offer()
    else:
        offer = db.spin_wheel(customer_id)

    discount = db.calc_discount(bill, offer["percent"])
    scratch = offer["type"] != "none"
    pending_checkouts[customer_id] = {
        "items": [{"item": i.item, "amount": i.amount} for i in cart.items],
        "item": ", ".join(i.item for i in cart.items),
        "bill": bill, "percent": offer["percent"],
        "discount": discount, "final": round(bill - discount, 2),
        "kind": offer["type"], "tier": offer.get("tier"),
        "scratch": scratch, "revealed": False,
    }
    await manager.broadcast({"type": "checkout_started", "cid": customer_id,
                             "name": info["name"], "bill": bill, "scratch": scratch})
    return {"ok": True, "scratch": scratch}


@app.post("/checkout/{customer_id}/reveal")
def reveal(customer_id: int):
    return pending_checkouts.get(customer_id) or {"error": "No active checkout"}


@app.post("/checkout/{customer_id}/shown")
async def shown(customer_id: int):
    co = pending_checkouts.get(customer_id)
    if not co:
        return {"ok": False}
    co["revealed"] = True
    await manager.broadcast({"type": "checkout_revealed", "cid": customer_id, **co})
    return {"ok": True}


@app.post("/checkout/{customer_id}/confirm")
async def confirm(customer_id: int):
    co = pending_checkouts.get(customer_id)
    if not co:
        return {"ok": False, "error": "No active checkout"}
    if co["scratch"] and not co["revealed"]:
        return {"ok": False, "error": "Customer ne abhi scratch nahi kiya"}

    # discount har item me uski keemat ke hisaab se baant do
    for it in co["items"]:
        share = co["discount"] * it["amount"] / co["bill"] if co["bill"] else 0
        paid = round(it["amount"] - share, 2)
        db.add_purchase(customer_id, it["item"], paid,
                        co["percent"] if co["discount"] > 0 else 0, round(share, 2))

    pending_checkouts.pop(customer_id, None)
    await manager.broadcast({"type": "checkout_done", "cid": customer_id})
    return {"ok": True, **co}


@app.post("/checkout/{customer_id}/cancel")
async def cancel(customer_id: int):
    pending_checkouts.pop(customer_id, None)
    await manager.broadcast({"type": "checkout_cancelled", "cid": customer_id})
    return {"ok": True}