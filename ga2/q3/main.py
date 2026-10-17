import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

EMAIL = "24f3000446@ds.study.iitm.ac.in"
ALLOWED_ORIGIN = "https://dash-yerflv.example.com"

app = FastAPI()


@app.middleware("http")
async def core_middleware(request: Request, call_next):
    start = time.perf_counter()
    origin = request.headers.get("origin")
    allowed = origin == ALLOWED_ORIGIN
    is_preflight = (
        request.method == "OPTIONS"
        and request.headers.get("access-control-request-method") is not None
    )

    if is_preflight:
        if allowed:
            response = Response(status_code=200)
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = request.headers.get(
                "access-control-request-headers", "*"
            )
            response.headers["Access-Control-Max-Age"] = "600"
        else:
            response = Response(status_code=403)
    else:
        response = await call_next(request)

    if allowed:
        response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Vary"] = "Origin"
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.6f}"
    return response


@app.get("/stats")
def stats(values: str = ""):
    try:
        nums = [int(v.strip()) for v in values.split(",") if v.strip() != ""]
    except ValueError:
        return JSONResponse({"error": "values must be comma-separated integers"}, status_code=422)
    if not nums:
        return JSONResponse({"error": "values is required"}, status_code=422)
    return {
        "email": EMAIL,
        "count": len(nums),
        "sum": sum(nums),
        "min": min(nums),
        "max": max(nums),
        "mean": sum(nums) / len(nums),
    }


@app.get("/")
def root():
    return {"status": "ok"}
