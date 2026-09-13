"""ACPL Sales Focus & Action Assistant — FastAPI service (contract-exact)."""
from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.solvers import answer_question
from src.playbook_engine import actions_for_scope
from src.metrics import Timer, inference_cost_usd
from src import store

app = FastAPI(title="ACPL Sales Focus & Action Assistant")

@app.on_event("startup")
def _warm():
    try:
        store.monthly()
    except Exception:
        pass

class AskReq(BaseModel):
    question: str = ""

class ActionsReq(BaseModel):
    scope: str = "all"

@app.get("/")
def root():
    return {"ok": True, "service": "acpl-assistant", "health": "/health"}

@app.get("/health")
def health():
    try:
        m = store.masters()
        return {"ok": True, "brands": len(m["brands"]), "regions": m["regions"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.post("/ask")
def ask(req: AskReq):
    t = Timer()
    q = (req.question or "").strip()
    if not q:
        ms = t.ms()
        return {"answer": "No question was provided.", "status": "NO_ANSWER",
                "evidence": [], "cost_usd": inference_cost_usd(), "latency_ms": ms}
    try:
        res = answer_question(q)
    except Exception as e:
        ms = t.ms()
        return {"answer": f"I cannot answer confidently from the data ({e}).", "status": "NO_ANSWER",
                "evidence": [], "cost_usd": inference_cost_usd(), "latency_ms": ms}
    ms = t.ms()
    return {"answer": res["answer"], "status": res["status"], "evidence": res["evidence"],
            "cost_usd": inference_cost_usd(), "latency_ms": ms}

@app.post("/actions")
def actions(req: ActionsReq):
    t = Timer()
    scope = (req.scope or "all").strip()
    low = scope.lower()
    valid = {"north", "south", "east", "west", "all"}
    if low not in valid:
        return JSONResponse(status_code=200, content=[])
    try:
        acts = actions_for_scope(scope)
    except Exception:
        acts = []
    ms = t.ms()
    resp = JSONResponse(content=acts)
    resp.headers["X-Latency-Ms"] = str(ms)
    resp.headers["X-Cost-Usd"] = str(inference_cost_usd())
    return resp

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
