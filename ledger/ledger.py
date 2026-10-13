import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

IST = timezone(timedelta(hours=5, minutes=30))
BASE = "https://exam.sanand.workers.dev/questionData?email=24f3000446%40ds.study.iitm.ac.in&quizSign=0abl7kFSYLbrZib%2F08ibmGJ80O%2FdauWy1MOf6FYs%2FQUFWNupKbdUtAFZZGvmx4GiAE6y3bS%2FSPpvdWdGkPPEwsg11ryeknhQ4iLNO2sS28sKxJtf23JioyHel64IQX5FPQLu1QTKKJLVhKtkJygPWfHDrRjhSbHj0F%2Fc%2Fgt6ov5uBz57Q8jB9dTqUhisbYAOVtv1aEhiytieZxA2Dr7Zdyx32kZkCUR0cIp7KoKoeZX%2BZgdOt55rP94LGT2Td2bC%2BCouf3%2FYS7AO1EjaTuXPcK5A6HrnkLc4lr5FX%2B6ym%2BU0YwKAHJg%2BsRuaV7YFa5jd7volMP%2F0ALSDtQUG0gqlPQ%3D%3D&questionId=q-ledger-agent-server"
TTL = 300

_lock = threading.Lock()
_cache = {"at": 0.0, "rows": [], "rates": {}}

DEFAULT_STATUS = {
    "revenue": ["paid"],
    "refunds": ["refunded"],
    "orders": ["paid"],
    "units": ["paid"],
    "avg_order_value": ["paid"],
    "customers": ["paid"],
}
MONEY = {"revenue", "refunds", "avg_order_value", "net_revenue"}


def _fetch(path):
    url = BASE + "&path=" + urllib.parse.quote(path, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def _utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def load(force=False):
    with _lock:
        if not force and _cache["rows"] and time.time() - _cache["at"] < TTL:
            return _cache["rows"], _cache["rates"]
        raw_rates = json.loads(_fetch("/rates"), parse_float=Decimal)
        rates = {k: Decimal(str(v)) for k, v in raw_rates["usd_per_unit"].items()}
        latest = {}
        for line in _fetch("/export").split("\n"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line, parse_float=Decimal)
            r["_upd"] = _utc(r["updated_at"])
            old = latest.get(r["id"])
            if old is None or r["_upd"] >= old["_upd"]:
                latest[r["id"]] = r
        rows = []
        for r in latest.values():
            created = _utc(r["created_at"]).astimezone(IST)
            r["status"] = str(r["status"]).strip().lower()
            r["_date"] = created.date()
            r["_month"] = created.strftime("%Y-%m")
            r["_usd"] = Decimal(r["amount"]) * rates[r["currency"]]
            rows.append(r)
        _cache.update({"at": time.time(), "rows": rows, "rates": rates})
        return rows, rates


def _match(r, f):
    for key, field in (("region", "region"), ("product", "product"), ("customer", "customer"), ("currency", "currency")):
        want = f.get(key)
        if want and str(r[field]).lower() != str(want).lower():
            return False
    if f.get("month") and r["_month"] != f["month"]:
        return False
    if f.get("start") and r["_date"] < date.fromisoformat(f["start"]):
        return False
    if f.get("end") and r["_date"] > date.fromisoformat(f["end"]):
        return False
    return True


def _agg(rows, metric, statuses):
    if metric == "net_revenue":
        paid = sum((r["_usd"] for r in rows if r["status"] == "paid"), Decimal(0))
        ref = sum((r["_usd"] for r in rows if r["status"] == "refunded"), Decimal(0))
        return paid - ref
    if statuses != ["any"]:
        rows = [r for r in rows if r["status"] in statuses]
    if metric in ("revenue", "refunds"):
        return sum((r["_usd"] for r in rows), Decimal(0))
    if metric == "orders":
        return len(rows)
    if metric == "units":
        return sum(int(r["qty"]) for r in rows)
    if metric == "customers":
        return len(set(r["customer"] for r in rows))
    if metric == "avg_order_value":
        return (sum((r["_usd"] for r in rows), Decimal(0)) / len(rows)) if rows else Decimal(0)
    raise ValueError("unknown metric: " + str(metric))


def _fmt(v, metric):
    if isinstance(v, Decimal):
        return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return v


def query(spec):
    rows, _ = load()
    metric = spec.get("metric", "revenue")
    f = spec.get("filters") or {}
    statuses = spec.get("status") or DEFAULT_STATUS.get(metric, ["paid"])
    if isinstance(statuses, str):
        statuses = [statuses]
    statuses = [s.lower() for s in statuses]
    rows = [r for r in rows if _match(r, f)]

    group = spec.get("group_by")
    if not group:
        return _fmt(_agg(rows, metric, statuses), metric)

    keymap = {"region": "region", "product": "product", "customer": "customer", "month": "_month", "currency": "currency"}
    buckets = {}
    for r in rows:
        buckets.setdefault(r[keymap[group]], []).append(r)
    values = {k: _agg(v, metric, statuses) for k, v in buckets.items()}

    rank = spec.get("rank")
    if rank in ("top", "bottom"):
        order = sorted(values.items(), key=lambda kv: ((-kv[1]) if rank == "top" else kv[1], str(kv[0])))
        n = int(spec.get("limit") or 1)
        names = [k for k, _ in order[:n]]
        return names[0] if n == 1 and names else names
    return {k: _fmt(v, metric) for k, v in sorted(values.items(), key=lambda kv: str(kv[0]))}
