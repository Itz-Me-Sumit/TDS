import base64
import math
import threading
import time
import uuid
from collections import deque
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

TOTAL_ORDERS = 50
RATE_LIMIT = 18
WINDOW_SECONDS = 10

app = FastAPI()

_lock = threading.Lock()
_hits = {}
_idempotent = {}


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    client_id = request.headers.get("x-client-id")
    if request.method == "OPTIONS" or not client_id:
        return await call_next(request)

    now = time.monotonic()
    with _lock:
        window = _hits.setdefault(client_id, deque())
        while window and now - window[0] >= WINDOW_SECONDS:
            window.popleft()
        if len(window) >= RATE_LIMIT:
            retry_after = max(1, math.ceil(WINDOW_SECONDS - (now - window[0])))
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "Idempotent-Replayed"],
)


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def decode_cursor(cursor: str) -> int:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    if not raw.startswith("o:"):
        raise ValueError("bad cursor")
    offset = int(raw[2:])
    if offset < 0:
        raise ValueError("bad cursor")
    return offset


@app.post("/orders")
async def create_order(request: Request, idempotency_key: Optional[str] = Header(default=None)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    if idempotency_key:
        with _lock:
            existing = _idempotent.get(idempotency_key)
            if existing is None:
                existing = {
                    "id": f"ord_{uuid.uuid4().hex[:12]}",
                    "status": "created",
                    "created_at": int(time.time()),
                    "data": body,
                }
                _idempotent[idempotency_key] = existing
                replayed = False
            else:
                replayed = True
        return JSONResponse(
            existing,
            status_code=201,
            headers={"Idempotent-Replayed": "true" if replayed else "false"},
        )

    order = {
        "id": f"ord_{uuid.uuid4().hex[:12]}",
        "status": "created",
        "created_at": int(time.time()),
        "data": body,
    }
    return JSONResponse(order, status_code=201)


@app.get("/orders")
def list_orders(limit: int = 10, cursor: Optional[str] = None):
    limit = max(1, min(limit, 100))
    offset = 0
    if cursor:
        try:
            offset = decode_cursor(cursor)
        except Exception:
            return JSONResponse({"detail": "invalid cursor"}, status_code=400)

    start = offset + 1
    end = min(offset + limit, TOTAL_ORDERS)
    items = [{"id": i, "status": "confirmed"} for i in range(start, end + 1)]
    next_cursor = encode_cursor(end) if end < TOTAL_ORDERS else None
    return {"items": items, "next_cursor": next_cursor}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "ok"}
