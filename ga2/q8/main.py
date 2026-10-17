import json
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

EMAIL = "24f3000446@ds.study.iitm.ac.in"
START = time.time()

request_count = 0
LOGS = deque(maxlen=1000)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observe(request: Request, call_next):
    global request_count
    request_count += 1
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        entry = {
            "level": "error",
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
            "request_id": request_id,
            "method": request.method,
            "status": 500,
        }
        LOGS.append(entry)
        print(json.dumps(entry), flush=True)
        raise
    entry = {
        "level": "info" if status < 500 else "error",
        "ts": datetime.now(timezone.utc).isoformat(),
        "path": request.url.path,
        "request_id": request_id,
        "method": request.method,
        "status": status,
        "duration_ms": round((time.perf_counter() - start) * 1000, 3),
    }
    LOGS.append(entry)
    print(json.dumps(entry), flush=True)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/work")
def work(n: int = 1):
    n = max(0, n)
    total = 0
    for i in range(min(n, 100000)):
        total += i * i
    return {"email": EMAIL, "done": n}


@app.get("/metrics")
def metrics():
    body = (
        "# HELP http_requests_total Total HTTP requests handled.\n"
        "# TYPE http_requests_total counter\n"
        f"http_requests_total {request_count}\n"
    )
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "uptime_s": round(time.time() - START, 3)}


@app.get("/logs/tail")
def logs_tail(limit: int = 50):
    if limit <= 0:
        return []
    return list(LOGS)[-limit:]


@app.get("/")
def root():
    return {"status": "ok"}
