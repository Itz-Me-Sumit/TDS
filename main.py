import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# OS env layer: set as fallback here so the host needs no extra setup
os.environ.setdefault("APP_WORKERS", "7")
os.environ.setdefault("APP_LOG_LEVEL", "info")
os.environ.setdefault("APP_API_KEY", "key-ejjhmcyyal")

BASE = Path(__file__).resolve().parent

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}
KNOWN = set(DEFAULTS)
ALIASES = {"num_workers": "workers"}
ORDER = ["port", "workers", "debug", "log_level", "api_key"]


def norm_key(k):
    k = str(k).strip().lower()
    return ALIASES.get(k, k)


def load_yaml():
    p = BASE / "config.development.yaml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {norm_key(k): v for k, v in data.items()}


def load_dotenv():
    out = {}
    p = BASE / ".env"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k.upper().startswith("APP_"):
            k = k[4:]
        out[norm_key(k)] = v.strip().strip('"').strip("'")
    return out


def load_os_env():
    out = {}
    for k, v in os.environ.items():
        if k.startswith("APP_"):
            key = norm_key(k[4:])
            if key in KNOWN:
                out[key] = v
    return out


def parse_sets(items):
    out = {}
    for item in items:
        if "=" in item:
            k, v = item.split("=", 1)
            out[norm_key(k)] = v.strip()
    return out


def coerce(key, value):
    if key in ("port", "workers"):
        try:
            return int(str(value).strip())
        except ValueError:
            return value
    if key == "debug":
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/effective-config")
def effective_config(overrides: list[str] = Query(default=[], alias="set")):
    merged = {}
    for layer in (DEFAULTS, load_yaml(), load_dotenv(), load_os_env(), parse_sets(overrides)):
        merged.update(layer)
    result = {k: coerce(k, merged[k]) for k in ORDER}
    for k, v in merged.items():
        if k not in result:
            result[k] = str(v)
    result["api_key"] = "****"
    return result
