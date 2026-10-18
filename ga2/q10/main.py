import json
import os
import re
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    text: str


class Invoice(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str


DATE_RE = r"\d{4}-\d{2}-\d{2}"
SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
SUFFIX = {"Ltd", "Inc", "LLC", "Corp", "Co", "GmbH", "PLC", "Limited", "Pty", "SA", "AG"}
STOP = {"total", "amount", "invoice", "due", "date", "currency", "payment", "bill", "balance", "pay"}
NUM = r"(?<![\w\-.])(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)(?![\w\-])"
CUR = r"(?:USD|EUR|GBP|[$€£])"


def take_name(s):
    out = []
    for w in s.split()[:8]:
        core = w.rstrip(",;:")
        stop = core != w
        if not core:
            break
        if core.lower() in STOP:
            break
        if not (core[0].isupper() or core[0].isdigit() or core == "&"):
            break
        if core.endswith("."):
            base = core.rstrip(".")
            out.append(base + "." if base in SUFFIX else base)
            break
        out.append(core)
        if stop:
            break
    return " ".join(out).strip()


def find_vendor(text):
    label = r"\b(?:vendor|supplier|payee|seller|billed by|issued by|invoice from|from)\b\s*[:\-]?\s*"
    for m in re.finditer(label, text, re.I):
        name = take_name(text[m.end():])
        if name:
            return name
    m = re.search(r"\b[A-Z][A-Za-z]*-[A-Za-z0-9]+", text)
    if m:
        return take_name(text[m.start():])
    return ""


def find_date(text):
    m = re.search(r"(?:due|payable|pay by|payment)[^0-9]{0,40}(" + DATE_RE + ")", text, re.I)
    if m:
        return m.group(1)
    dates = re.findall(DATE_RE, text)
    return dates[-1] if dates else ""


def find_currency(text):
    m = re.search(r"\b(USD|EUR|GBP)\b", text, re.I)
    if m:
        return m.group(1).upper()
    for sym, code in SYMBOLS.items():
        if sym in text:
            return code
    return ""


def to_float(s):
    return float(s.replace(",", ""))


def find_amount(text):
    clean = re.sub(DATE_RE, " ", text)
    kw = list(re.finditer(
        r"(?:total|amount|balance|due|owed|pay)[^0-9\n]{0,40}?" + CUR + r"?\s*" + NUM, clean, re.I))
    if kw:
        return to_float(kw[-1].group(1))
    m = re.search(CUR + r"\s*" + NUM, clean) or re.search(NUM + r"\s*(?:USD|EUR|GBP)\b", clean, re.I)
    if m:
        return to_float(m.group(1))
    nums = [to_float(n) for n in re.findall(NUM, clean)]
    return max(nums) if nums else None


def llm_extract(text):
    url = os.getenv("OLLAMA_URL")
    if not url:
        return {}
    try:
        payload = {
            "model": os.getenv("OLLAMA_MODEL", "mistral:latest"),
            "messages": [
                {"role": "system", "content": "Extract invoice fields. Reply with JSON only: "
                 '{"vendor": string, "amount": number, "currency": "USD|EUR|GBP", "date": "YYYY-MM-DD" (payment due date)}'},
                {"role": "user", "content": text[:4000]},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read())
        return json.loads(body["choices"][0]["message"]["content"])
    except Exception:
        return {}


def parse_invoice(text):
    data = {
        "vendor": find_vendor(text),
        "amount": find_amount(text),
        "currency": find_currency(text),
        "date": find_date(text),
    }
    if not data["vendor"] or data["amount"] is None or not data["currency"] or not data["date"]:
        extra = llm_extract(text)
        for k in data:
            if data[k] in ("", None) and extra.get(k) not in (None, ""):
                data[k] = extra[k]
    return data


@app.post("/extract", response_model=Invoice)
def extract(req: ExtractRequest):
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    try:
        data = parse_invoice(req.text)
        amount = float(data.get("amount") or 0)
    except Exception:
        data, amount = {}, 0.0
    return Invoice(
        vendor=str(data.get("vendor") or ""),
        amount=amount,
        currency=str(data.get("currency") or "USD").upper()[:3],
        date=str(data.get("date") or ""),
    )


@app.get("/")
def root():
    return {"status": "ok"}
