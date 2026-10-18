import math
import threading
import time
import uuid
from collections import deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = "24f3000446@ds.study.iitm.ac.in"
ALLOWED_ORIGIN = "https://app-0kzs38.example.com"
EXAM_ORIGIN = "https://APNA-EXAM-PAGE-DOMAIN"
RATE_LIMIT = 15
WINDOW_SECONDS = 10

app = FastAPI()

_lock = threading.Lock()
_hits = {}


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
                {"detail": "rate limit exceeded", "request_id": request.state.request_id},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)
    return await call_next(request)


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "").strip()
    request_id = incoming[:200] if incoming else str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, EXAM_ORIGIN],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.get("/ping")
def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}


@app.get("/")
def root():
    return {"status": "ok"}
