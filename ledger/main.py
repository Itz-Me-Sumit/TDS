import json
import os
import threading
import urllib.request

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import ledger

TOKEN = os.environ.get("AIPIPE_TOKEN", "")
MODEL = os.environ.get("LLM_MODEL", "openai/gpt-4.1-mini")
LLM_URL = "https://aipipe.org/openrouter/v1/chat/completions"

SYSTEM = """You convert a plain-English question about an order ledger into a JSON query spec. Reply with JSON only, no prose.

Data: orders from 2026-01-01 to 2026-06-30 (dates are in Asia/Kolkata time).
Regions: North, South, East, West, Central.
Products: Air Fryer, Blender, Grinder, Juicer, Kettle, Mixer, Rice Cooker, Toaster.
Customers look like C1084. Currencies: USD, EUR, INR. All money answers are in USD.
Order statuses: paid, refunded, void.

Output schema:
{"metric": one of ["revenue","refunds","net_revenue","orders","units","customers","avg_order_value"],
 "filters": {"region": str, "product": str, "customer": str, "currency": str, "month": "YYYY-MM", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
 "status": null or a list of statuses,
 "group_by": null or one of ["region","product","customer","month","currency"],
 "rank": null or "top" or "bottom",
 "limit": null or integer}

Rules:
- Include only the filters the question mentions. Use exact names from the lists above.
- "revenue"/"sales" = metric revenue (paid orders only, default). "refunds"/"refunded amount" = metric refunds. "net revenue" = net_revenue.
- "how many orders" = metric orders. "how many refunded orders" = metric orders with status ["refunded"].
- "units"/"items sold" = metric units. "how many customers" = metric customers. "average order value" = avg_order_value.
- A whole month: use filters.month. Any other range (quarter, week, between dates): use start and end, both inclusive.
- Q1 = 2026-01-01 to 2026-03-31, Q2 = 2026-04-01 to 2026-06-30.
- "which/top/best/highest" with a category: set group_by and rank "top" (limit 1 unless a number is given). "lowest/worst/least": rank "bottom".
- "by region"/"per product" with no ranking: set group_by and leave rank null.
"""

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def warm():
    threading.Thread(target=ledger.load, daemon=True).start()


def ask_llm(question):
    body = {
        "model": MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
    }
    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN, "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text)


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/")
@app.post("/ask")
async def ask(request: Request):
    try:
        payload = await request.json()
        question = str(payload.get("question", "")).strip()
    except Exception:
        return {"answer": None, "error": "bad request"}
    try:
        spec = ask_llm(question)
    except Exception as e:
        return {"answer": None, "error": "llm: " + str(e)[:200]}
    try:
        return {"answer": ledger.query(spec)}
    except Exception as e:
        return {"answer": None, "error": "data: " + str(e)[:200]}
