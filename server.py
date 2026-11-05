import asyncio
from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.responses import FileResponse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import db

app = FastAPI(title="Greetify API")
db.init_db()


# ---------- WebSocket: dashboard yahan judta hai ----------
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
            await ws.receive_text()   # connection khula rakhne ke liye
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ---------- Recognition script yahan alert bhejti hai ----------
@app.post("/alert/{customer_id}")
async def send_alert(customer_id: int):
    info = db.get_customer_info(customer_id)
    if info is None:
        return {"ok": False, "error": "Customer not found"}
    await manager.broadcast({"type": "returning_customer", "customer": info})
    return {"ok": True}


# ---------- Customers aur purchases ----------
class PurchaseIn(BaseModel):
    item: str
    amount: float = 0


@app.get("/customers")
def customers():
    return db.list_customers()


@app.get("/customers/{customer_id}")
def customer(customer_id: int):
    info = db.get_customer_info(customer_id)
    return info or {"error": "Customer not found"}


@app.post("/customers/{customer_id}/purchases")
def add_purchase(customer_id: int, p: PurchaseIn):
    db.add_purchase(customer_id, p.item, p.amount)
    return {"ok": True}


@app.get("/")
def home():
    return {"app": "Greetify", "status": "running"}

@app.get("/dashboard")
def dashboard():
    return FileResponse("dashboard.html")
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