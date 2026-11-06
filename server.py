import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import db

app = FastAPI(title="Greetify API")
db.init_db()


class PurchaseIn(BaseModel):
    item: str
    amount: float = 0


# ---------- WebSocket ----------
class ConnectionManager:
    def __init__(self):
        self.connections = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, message: dict):
        for ws in list(self.connections):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
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
async def start_checkout(customer_id: int, p: PurchaseIn):
    info = db.get_customer_info(customer_id)
    if info is None:
        return {"ok": False, "error": "Customer not found"}

    if p.amount < db.MIN_BILL:
        offer = db.make_offer("none", 0)
    elif db.purchase_count(customer_id) == 0:
        offer = db.welcome_offer()
    else:
        offer = db.spin_wheel(customer_id)

    discount = db.calc_discount(p.amount, offer["percent"])
    scratch = offer["type"] != "none"
    pending_checkouts[customer_id] = {
        "item": p.item, "bill": p.amount, "percent": offer["percent"],
        "discount": discount, "final": round(p.amount - discount, 2),
        "kind": offer["type"], "tier": offer.get("tier"),
        "scratch": scratch, "revealed": False,
    }
    await manager.broadcast({"type": "checkout_started", "cid": customer_id,
                             "name": info["name"], "bill": p.amount, "scratch": scratch})
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
    db.add_purchase(customer_id, co["item"], co["final"],
                    co["percent"] if co["discount"] > 0 else 0, co["discount"])
    pending_checkouts.pop(customer_id, None)
    await manager.broadcast({"type": "checkout_done", "cid": customer_id})
    return {"ok": True, **co}


@app.post("/checkout/{customer_id}/cancel")
async def cancel(customer_id: int):
    pending_checkouts.pop(customer_id, None)
    await manager.broadcast({"type": "checkout_cancelled", "cid": customer_id})
    return {"ok": True}