"""Eval: accuracy + cost + latency. Calls solvers directly (no HTTP) for determinism."""
import json, time, statistics
from pathlib import Path
from src.solvers import answer_question
from src.playbook_engine import actions_for_scope
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

BASE = Path(__file__).parent
Qs = [json.loads(l) for l in (BASE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

def check(got, exp):
    if exp == "OK": return got == "OK"
    if exp == "NO_ANSWER": return got == "NO_ANSWER"
    if exp == "OK_OR_NO": return got in ("OK", "NO_ANSWER")
    return False

def main():
    lat = []; ok = 0; fails = []
    for item in Qs:
        t0 = time.perf_counter()
        r = answer_question(item["q"])
        ms = (time.perf_counter() - t0) * 1000
        lat.append(ms)
        good = check(r["status"], item["expect_status"])
        if r["status"] == "OK" and not r["evidence"]:
            good = False
        if r["status"] == "NO_ANSWER" and not r["answer"]:
            good = False
        if good: ok += 1
        else: fails.append({"q": item["q"], "expect": item["expect_status"], "got": r["status"], "answer": r["answer"][:200]})
    for scope in ["West", "all", "North"]:
        acts = actions_for_scope(scope)
        assert all("rule_id" in a and "finding" in a and "action" in a and "state" in a for a in acts), scope
    lat_sorted = sorted(lat)
    p50 = statistics.median(lat_sorted)
    p95 = lat_sorted[int(len(lat_sorted) * 0.95) - 1] if len(lat_sorted) > 1 else lat_sorted[0]
    res = {"n": len(Qs), "correct": ok, "accuracy": round(ok / len(Qs), 4),
           "fails": fails, "latency_ms": {"p50": round(p50, 1), "p95": round(p95, 1),
           "min": round(min(lat_sorted), 1), "max": round(max(lat_sorted), 1)},
           "cost_usd_median": 0.0, "actions_checks": "West/all/North have rule_id+state"}
    (BASE / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"accuracy {ok}/{len(Qs)} = {ok/len(Qs):.1%}  p50 {p50:.1f}ms p95 {p95:.1f}ms")
    for f in fails: print("FAIL:", f)

if __name__ == "__main__":
    main()
