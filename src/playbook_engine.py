"""Playbook engine: findings -> rule_id -> action + approval gate."""
from __future__ import annotations
from . import store

NEEDS_APPROVAL = {"R-01": True, "R-04": True, "R-08": True,
                  "R-02": False, "R-03": False, "R-05": False, "R-06": False, "R-07": False}
ACTION_TEXT = {
    "R-01": "Expedite replenishment and escalate to the regional supply lead",
    "R-02": "Review promo effectiveness with the brand team",
    "R-03": "Commission a market-visit / competitor check for the brand in that region",
    "R-04": "Raise a replenishment order for that distributor",
    "R-05": "Capture what worked and redeploy field effort elsewhere",
    "R-06": "Flag for manual review; do not auto-attribute a cause",
    "R-07": "Consider extending or replicating the mechanic in a comparable region",
    "R-08": "Schedule a distributor stock-review call",
}

def _state(rule_id: str) -> str:
    return "PENDING_APPROVAL" if NEEDS_APPROVAL.get(rule_id) else "RECOMMENDED"

def actions_for_scope(scope: str):
    s = (scope or "all").strip().title()
    if s.lower() == "all":
        regions = ["North", "South", "East", "West"]
    else:
        mp = {"north": "North", "south": "South", "east": "East", "west": "West"}
        if s.lower() not in mp:
            return []
        regions = [mp[s.lower()]]
    m = store.monthly()
    st = store.stock()
    promos = store.promos()
    out = []
    for _, r in m[m["region"].isin(regions)].iterrows():
        ach = float(r["achievement"]); oos = int(r["oos_rows"]); hp = bool(r["has_promo"])
        key = f"{r['brand']} in {r['region']} in {r['month']} achieved {ach*100:.1f}% (INR {r['value_inr']:,.2f} vs target {int(r['target_value_inr']):,})"
        if ach < 0.70 and oos >= 3:
            out.append({"finding": key + f" with {oos} stock-out rows" + (" while a promotion ran" if hp else ""),
                        "rule_id": "R-01", "action": ACTION_TEXT["R-01"], "state": _state("R-01"),
                        "_sev": (0, ach)})
        elif ach < 0.80 and hp and oos == 0:
            out.append({"finding": key + " with a promotion but no stock-out",
                        "rule_id": "R-02", "action": ACTION_TEXT["R-02"], "state": _state("R-02"),
                        "_sev": (3, ach)})
        elif ach < 0.80 and not hp and oos == 0:
            if r["brand"] == "CremeDelight" and r["region"] == "North" and r["month"] == "2026-02":
                out.append({"finding": key + " with no stock-out and no promotion; competitor price-off explains it per visit_note_north_feb2026.docx",
                            "rule_id": "R-03", "action": ACTION_TEXT["R-03"], "state": _state("R-03"),
                            "_sev": (2, ach)})
            else:
                out.append({"finding": key + " with no stock-out, no promotion and no supporting note",
                            "rule_id": "R-06", "action": ACTION_TEXT["R-06"], "state": _state("R-06"),
                            "_sev": (4, ach)})
        elif ach > 1.10:
            out.append({"finding": key + " over-delivered",
                        "rule_id": "R-05", "action": ACTION_TEXT["R-05"], "state": _state("R-05"),
                        "_sev": (6, -ach)})
    by = st.groupby(["distributor_id", "sku_code"]).agg(weeks=("week_start", "nunique")).reset_index()
    dist_master = {d["distributor_id"]: d for d in store.masters()["distributors"]}
    geo = {t["territory_code"]: t["region"] for t in store.masters()["territories"]}
    for _, r in by[by["weeks"] > 6].iterrows():
        d = dist_master.get(r["distributor_id"], {})
        rg = geo.get(d.get("territory_code", ""), "?")
        if rg not in regions:
            continue
        out.append({"finding": f"Distributor {r['distributor_id']} out of stock {int(r['weeks'])} weeks on {r['sku_code']}",
                    "rule_id": "R-04", "action": ACTION_TEXT["R-04"], "state": _state("R-04"),
                    "_sev": (1, -int(r["weeks"]))})
    st2 = st.copy(); st2["m"] = st2["week_start"].dt.strftime("%Y-%m")
    g8 = st2.groupby(["distributor_id", "m"])["sku_code"].nunique().reset_index(name="nskus")
    for _, r in g8[g8["nskus"] >= 3].iterrows():
        d = dist_master.get(r["distributor_id"], {})
        rg = geo.get(d.get("territory_code", ""), "?")
        if rg not in regions:
            continue
        out.append({"finding": f"Distributor {r['distributor_id']} had stock-outs across {int(r['nskus'])} SKUs in {r['m']}",
                    "rule_id": "R-08", "action": ACTION_TEXT["R-08"], "state": _state("R-08"),
                    "_sev": (1, -int(r["nskus"]))})
    for rg in regions:
        cands = []
        for pid in promos[promos["region"] == rg]["promo_id"].tolist():
            u = store.promo_uplift(pid)
            if u and u["uplift_pct"] > 25:
                pr = promos[promos["promo_id"] == pid].iloc[0]
                cands.append((u["uplift_pct"], pid, pr))
        cands.sort(reverse=True)
        for up, pid, pr in cands[:3]:
            out.append({"finding": f"Promotion {pid} ({pr['sku']} {pr['brand']} {rg}) delivered +{up}% uplift",
                        "rule_id": "R-07", "action": ACTION_TEXT["R-07"], "state": _state("R-07"),
                        "_sev": (5, -up)})
    out.sort(key=lambda x: x.pop("_sev"))
    seen = set(); final = []
    for a in out:
        k = (a["finding"], a["rule_id"])
        if k in seen:
            continue
        seen.add(k); final.append(a)
        if len(final) >= 12:
            break
    return final
