"""Intent router: question -> intent. Pure regex/keywords, no LLM."""
from __future__ import annotations
import re

def route(q: str) -> str:
    t = q.lower()
    if re.search(r"approv|escalat|who.*approve|needs?\s+approval|pending approval|sop|procedure", t):
        return "doc_sop"
    if re.search(r"competitor|market visit|visit note|why.*(feb|north.*creme|creme.*north)", t):
        return "doc_note"
    if re.search(r"which.*promo|list.*promo|promo.*calendar|circular|mechanic|discount.*when|when.*promo", t):
        return "promo_calendar"
    if re.search(r"uplift|effectiveness|did.*promo.*work|promo.*work|lift|roi|mechanic.*work", t):
        return "promo_uplift"
    if re.search(r"stock.?out|out.?of.?stock|oos|supply.*promo|promo.*stock|undoing.*promo|depot|replenish", t):
        return "stockout_promo"
    if re.search(r"distributor|d0\d|mumbai.*dist|delhi.*dist", t):
        return "distributor_gap"
    if re.search(r"over|exceed|above.*target|beat.*target|best|working|110%", t):
        return "overachiever"
    if re.search(r"territor|city|delhi|jaipur|lucknow|bengaluru|chennai|hyderabad|kolkata|patna|guwahati|mumbai|pune|ahmedabad", t) and re.search(r"target|achiev|sales|gap|miss|perform", t):
        return "territory_detail"
    if re.search(r"los|miss|slip|lag|behind|shortfall|gap|worst|weak|under|vs\.? target|against target|achiev", t):
        return "worst_target"
    if re.search(r"action|what.*do|recommend|focus|this week|next week|priority|priorities", t):
        return "actions_hint"
    if re.search(r"how much|total|national|overall sales|fy26.*total", t):
        return "national_total"
    return "worst_target"
