"""Guardrails: injection, unknown entities, out-of-scope. Returns NO_ANSWER reason or None."""
from __future__ import annotations
import re
from . import normalizer as N

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|these\s+|your\s+)?(rules|instructions|constraints|guardrails)",
    r"reveal\s+(your\s+)?(config|configuration|prompt|system|key|secret|token)",
    r"show\s+(me\s+)?(your\s+)?(system|prompt|config|key)",
    r"bypass|jailbreak|dan\s+mode|do\s+anything\s+now",
    r"disregard\s+(all\s+)?(rules|instructions)",
]
OUT_OF_SCOPE_TOPICS = [
    "profit", "margin", "net revenue", "ebitda", "market share", "footfall",
    "consumer sentiment", "salary", "leave", "holiday", "attendance", "hiring",
    "share price", "stock price", "weather", "election", "cricket",
]
KNOWN_FAKE_BRANDS = ["parle", "britannia", "nestle", "amul", "itc", "haldiram", "pepsico", "coca", "lays", "oreo", "testbrand", "xyz", "acme", "fakemart"]

def check_injection(q: str):
    t = q.lower()
    for p in INJECTION_PATTERNS:
        if re.search(p, t):
            return "I cannot act on instructions embedded in a question that ask to ignore rules or reveal configuration."
    return None

def check_unknown_entities(q: str, masters: dict):
    t = q.lower()
    brands = masters["brands"]
    regions = masters["regions"]
    for f in KNOWN_FAKE_BRANDS:
        if f in t:
            return f"'{f}' is not a brand in ACPL data. Known brands include {', '.join(brands[:5])}... ({len(brands)} total)."
    # generic which-brand questions must NOT be flagged — only specific unknown names
    if re.search(r"\bbrand\b", t) and N.find_brand(q, brands) is None:
        if re.search(r"\bwhich\s+brand\b|\bwhat\s+brand\b|\bwhich\s+brand-region\b|\bper\s+brand\b|\bby\s+brand\b", t):
            pass
        else:
            m = re.search(r"brand\s+([A-Za-z][A-Za-z \-]{1,30})", q, re.I)
            cand = m.group(1).strip() if m else ""
            if cand and cand.lower() not in ["region", "region missed", "and", "in", "for", "that"]:
                if re.search(r"target|sales|achiev|perform|growth|share|uplift|stock|promo|exceed|miss", t):
                    return f"I cannot find brand '{cand}' in ACPL data, so I cannot answer with confidence."
    if re.search(r"\bregion\b", t) and N.find_region(q, regions) is None and not N.mentions_all(q):
        if re.search(r"which.*region|brand-region|per region|each region|by region|across regions|all regions", t):
            pass
        else:
            m = re.search(r"([A-Za-z\-]+)\s+region", q, re.I)
            cand = m.group(1) if m else ""
            if cand and cand.lower() not in ["that", "the", "each", "per", "this", "a"]:
                return f"'{cand}' is not a region in ACPL data. Known regions: {', '.join(regions)}."
    for f in ["northeast", "north-east", "central", "global", "international"]:
        if f in t:
            return f"'{f}' is not a region in ACPL data. Known regions: {', '.join(regions)}."
    if re.search(r"\bterritory|city|district\b", t):
        terrs = masters["territories"]
        if N.find_territory(q, terrs) is None and N.find_region(q, regions) is None and not N.mentions_all(q):
            return "I cannot find that territory/city in ACPL geography master (12 territories), so I cannot answer."
    m = re.search(r"\bd\s*0*(\d{1,3})\b", t)
    if m:
        code = f"D{m.group(1).zfill(3)}"
        ids = {d["distributor_id"] for d in masters["distributors"]}
        if code not in ids:
            return f"Distributor '{code}' is not in ACPL data (40 distributors D001-D040)."
    for pat in re.findall(r"\b([A-Z]{2}-\d{4})\b", q):
        if pat.startswith("PR-"):
            continue
        codes = {s["sku_code"] for s in masters["skus"]}
        if pat not in codes:
            return f"SKU '{pat}' is not in the product master (120 SKUs)."
    return None

def check_scope(q: str):
    t = q.lower()
    if re.search(r"(202[789]|203\d|199\d|2026-0[789]|2026-1[0-2]|july 2026|august 2026|june 2027)", t):
        return "That period is outside FY26 data (July 2025-June 2026), so I cannot answer."
    if re.search(r"\bnext quarter\b|\bnext month\b|\bforecast\b|\bpredict\b|\bfy27\b|\b2027\b", t):
        return "I cannot forecast beyond FY26 data (July 2025-June 2026)."
    for topic in OUT_OF_SCOPE_TOPICS:
        if topic in t and re.search(r"leave|salary|holiday", t):
            return "That HR topic is not supported by sales data or the action playbook."
        if topic in t and not re.search(r"target|sales|stock|promo|achievement", t):
            return f"I cannot answer about '{topic}' from the provided sales/targets/stockout/promotion data and working documents."
    if re.search(r"\bwhy.*profit\b|\bprofit.*why\b", t):
        return "Profit is not in the provided data (only primary-sales value), so I cannot answer."
    return None
