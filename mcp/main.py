import hashlib

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

EMAIL = "24f3000446@ds.study.iitm.ac.in"
SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"]

TOOL = {
    "name": "solve_challenge",
    "description": "Returns the exam response for the current request challenge header.",
    "inputSchema": {"type": "object", "properties": {}},
}

app = FastAPI()


def answer(challenge):
    digest = hashlib.sha256(f"{challenge}:{EMAIL}".encode("utf-8")).hexdigest()
    return digest[:16]


def handle(msg, headers):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if mid is None:
        return None  # notification, no response

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED else SUPPORTED[0]
        return ok({
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "exam-mcp", "version": "1.0.0"},
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [TOOL]})
    if method == "tools/call":
        if params.get("name") != "solve_challenge":
            return err(-32602, "Unknown tool")
        challenge = (headers.get("x-exam-challenge") or "").strip()
        return ok({"content": [{"type": "text", "text": answer(challenge)}], "isError": False})
    return err(-32601, "Method not found")


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/")
@app.post("/mcp")
async def mcp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)

    if isinstance(body, list):
        out = [r for r in (handle(m, request.headers) for m in body) if r is not None]
        if not out:
            return Response(status_code=202)
        return JSONResponse(out)

    res = handle(body, request.headers)
    if res is None:
        return Response(status_code=202)
    return JSONResponse(res)
