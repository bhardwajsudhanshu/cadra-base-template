"""Entity normalisation: synonyms + fuzzy matching. Code decides, no LLM."""
from __future__ import annotations
import re
from rapidfuzz import process, fuzz

REGION_ALIASES = {
    "north": "North", "northern": "North",
    "south": "South", "southern": "South",
    "east": "East", "eastern": "East",
    "west": "West", "western": "West",
}
CATEGORY_ALIASES = {
    "biscuit": "Biscuits", "biscuits": "Biscuits", "cookie": "Biscuits", "cookies": "Biscuits",
    "snack": "Snacks", "snacks": "Snacks", "namkeen": "Snacks",
    "beverage": "Beverages", "beverages": "Beverages", "drink": "Beverages", "drinks": "Beverages", "cola": "Beverages",
    "home care": "Home Care", "home-care": "Home Care", "homecare": "Home Care",
    "personal care": "Personal Care", "personal-care": "Personal Care", "personalcare": "Personal Care",
}
MONTH_NAMES = {
    "jan": "01", "january": "01", "feb": "02", "february": "02", "mar": "03", "march": "03",
    "apr": "04", "april": "04", "may": "05", "jun": "06", "june": "06",
    "jul": "07", "july": "07", "aug": "08", "august": "08", "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10", "nov": "11", "november": "11", "dec": "12", "december": "12",
}

def _fuzzy_one(q: str, choices: list[str], thresh: int = 85):
    if not q or not choices:
        return None
    hit = process.extractOne(q, choices, scorer=fuzz.WRatio)
    if hit and hit[1] >= thresh:
        return hit[0]
    return None

def find_region(text: str, regions: list[str]):
    t = text.lower()
    for alias, canon in REGION_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", t):
            if canon in regions:
                return canon
    words = re.findall(r"[a-z]+", t)
    for w in words:
        hit = _fuzzy_one(w, [r.lower() for r in regions], 88)
        if hit:
            for r in regions:
                if r.lower() == hit:
                    return r
    return None

def find_brand(text: str, brands: list[str]):
    t = text.lower()
    for b in brands:
        if b.lower() in t:
            return b
    hit = _fuzzy_one(t, [b.lower() for b in brands], 90)
    if hit:
        for b in brands:
            if b.lower() == hit:
                return b
    for tok in re.findall(r"[a-zA-Z][a-zA-Z\- ]{2,}", text):
        h = _fuzzy_one(tok.strip().lower(), [b.lower() for b in brands], 92)
        if h:
            for b in brands:
                if b.lower() == h:
                    return b
    return None

def find_category(text: str):
    t = text.lower()
    for alias, canon in CATEGORY_ALIASES.items():
        if alias in t:
            return canon
    return None

def find_territory(text: str, territories: list[dict]):
    t = text.lower()
    for terr in territories:
        if terr["territory_name"].lower() in t or terr["territory_code"].lower() in t:
            return terr
    names = [x["territory_name"] for x in territories]
    hit = _fuzzy_one(t, [n.lower() for n in names], 88)
    if hit:
        for terr in territories:
            if terr["territory_name"].lower() == hit:
                return terr
    return None

def find_month(text: str):
    """Return YYYY-MM or None. FY26 only: 2025-07..2026-06."""
    t = text.lower()
    m = re.search(r"(202[56])[-/](0[1-9]|1[0-2])", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    for name, num in MONTH_NAMES.items():
        mm = re.search(r"\b" + name + r"[a-z]*\s*,?\s*(202[56])\b", t)
        if mm:
            return f"{mm.group(1)}-{num}"
    for name, num in MONTH_NAMES.items():
        if re.search(r"\b" + name + r"[a-z]*\b", t):
            n = int(num)
            year = "2026" if 1 <= n <= 6 else "2025"
            return f"{year}-{num}"
    return None

def find_quarter(text: str):
    t = text.lower()
    m = re.search(r"\bq\s*([1-4])\b", t)
    if m:
        return f"Q{m.group(1)}"
    if "this quarter" in t or "current quarter" in t:
        return "Q4"
    if "last quarter" in t:
        return "Q3"
    if "first quarter" in t:
        return "Q1"
    return None

def find_sku(text: str, skus: list[dict]):
    t = text.lower()
    for s in skus:
        if s["sku_code"].lower() in t:
            return s
    return None

def find_distributor(text: str, dists: list[dict]):
    t = text.lower()
    m = re.search(r"\bd\s*0*(\d{1,3})\b", t)
    if m:
        code = f"D{m.group(1).zfill(3)}"
        for d in dists:
            if d["distributor_id"] == code:
                return d
    for d in dists:
        if d["distributor_name"].lower() in t:
            return d
    return None

def mentions_all(text: str) -> bool:
    return bool(re.search(r"\ball\b|\bnational\b|\bacross (all )?regions\b|\bpan-?india\b", text.lower()))
