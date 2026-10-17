import secrets
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = "24f3000446@ds.study.iitm.ac.in"
API_KEY = "ak_4pntwk834yljycis1wsk27xe"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def unauthorized():
    return JSONResponse({"detail": "invalid or missing API key"}, status_code=401)


@app.post("/analytics")
async def analytics(request: Request, x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        return unauthorized()

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "invalid JSON body"}, status_code=422)

    events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(events, list):
        return JSONResponse({"detail": "events must be a list"}, status_code=422)

    users = set()
    positive_totals = {}
    revenue = 0.0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        user = ev.get("user")
        users.add(user)
        try:
            amount = float(ev.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if amount > 0:
            revenue += amount
            positive_totals[user] = positive_totals.get(user, 0.0) + amount

    top_user = max(positive_totals, key=positive_totals.get) if positive_totals else None

    return {
        "email": EMAIL,
        "total_events": len(events),
        "unique_users": len(users),
        "revenue": round(revenue, 6),
        "top_user": top_user,
    }


@app.get("/")
def root():
    return {"status": "ok"}
