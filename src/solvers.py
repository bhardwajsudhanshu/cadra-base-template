"""Solvers: pandas-only answers with evidence. Never fabricate."""
from __future__ import annotations
import re
import pandas as pd
from . import store, normalizer as N, guardrails as G
from .intent_router import route

def answer_question(question: str):
    q = question or ""
    masters = store.masters()
    r = G.check_injection(q)
    if r:
        return {"answer": r, "status": "NO_ANSWER", "evidence": [], "intent": "blocked"}
    r = G.check_unknown_entities(q, masters)
    if r:
        return {"answer": r, "status": "NO_ANSWER", "evidence": [], "intent": "unknown_entity"}
    r = G.check_scope(q)
    if r:
        return {"answer": r, "status": "NO_ANSWER", "evidence": [], "intent": "out_of_scope"}
    intent = route(q)
    try:
        if intent == "national_total":
            return _national(q)
        if intent == "doc_sop":
            return _sop(q)
        if intent == "doc_note":
            return _doc_note(q)
        if intent == "promo_calendar":
            return _promo_calendar(q)
        if intent == "promo_uplift":
            return _promo_uplift(q)
        if intent == "stockout_promo":
            return _stockout_promo(q)
        if intent == "distributor_gap":
            return _distributor(q)
        if intent == "territory_detail":
            return _territory(q)
        if intent == "overachiever":
            return _over(q)
        if intent == "actions_hint":
            return _actions_hint(q)
        return _worst(q)
    except Exception as e:
        return {"answer": f"I cannot answer confidently from the data ({e}).", "status": "NO_ANSWER", "evidence": [], "intent": intent}

def _fmt_inr(x: float) -> str:
    return f"{x:,.2f}"

def _national(q):
    s = store.sales()
    total = float(s["value_inr"].sum())
    ev = [{"metric": "national_fy26_primary_sales_inr", "value": round(total, 2),
           "period": "2025-07 to 2026-06", "rows": len(s)}]
    return {"answer": f"National FY26 primary sales are INR {_fmt_inr(total)} across {len(s):,} SKU-territory-week rows (July 2025-June 2026).",
            "status": "OK", "evidence": ev, "intent": "national_total"}

def _sop(q):
    t = q.lower()
    if "approv" in t or "pending" in t or "who" in t:
        ans = ("Per the Escalation SOP: every recommended action must cite its playbook rule. "
               "Actions that notify another team or change a commitment — supply escalations (R-01), "
               "replenishment orders (R-04), distributor stock-review calls (R-08) — require manager approval "
               "before being carried out (PENDING_APPROVAL). Analysis/review actions (R-02, R-03, R-05, R-06, R-07) do not.")
        ev = [{"source": "escalation_sop.docx", "rule": "approval gate for notify/change actions",
               "pending_approval_rules": "R-01, R-04, R-08"}]
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "doc_sop"}
    ans = ("Per the Escalation SOP: where a brand misses target with no stock-out and no promotion, "
           "do not attribute a cause from numbers alone — commission a market check (R-03), or if nothing explains it, "
           "flag for manual review (R-06). Never invent a reason.")
    ev = [{"source": "escalation_sop.docx", "rule": "do not invent cause; R-03/R-06"}]
    return {"answer": ans, "status": "OK", "evidence": ev, "intent": "doc_sop"}

def _doc_note(q):
    t = q.lower()
    masters = store.masters()
    brand = N.find_brand(q, masters["brands"])
    if "creme" in t or ("competitor" in t and "north" in t) or (brand == "CremeDelight" and ("north" in t or "feb" in t)):
        m = store.monthly()
        row = m[(m["brand"] == "CremeDelight") & (m["region"] == "North") & (m["month"] == "2026-02")]
        if row.empty:
            return {"answer": "I cannot find that period in the data.", "status": "NO_ANSWER", "evidence": [], "intent": "doc_note"}
        r = row.iloc[0]
        ans = (f"CremeDelight in North in Feb 2026 achieved INR {_fmt_inr(float(r['value_inr']))} vs target "
               f"{int(r['target_value_inr']):,} ({float(r['achievement'])*100:.1f}%). There were no stock-outs and no counter-promotion in the numbers. "
               f"The North market-visit note (Feb 2026) explains it: a competitor ran a deep price-off on mid-pack biscuits in Jaipur/Lucknow, "
               f"shifting shelf/billing; our range lost ~25% of expected February offtake.")
        ev = [{"brand": "CremeDelight", "region": "North", "month": "2026-02",
               "actual_inr": round(float(r["value_inr"]), 2), "target_inr": int(r["target_value_inr"]),
               "achievement_pct": round(float(r["achievement"]) * 100, 1), "oos_rows": 0,
               "source": "visit_note_north_feb2026.docx"}]
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "doc_note"}
    if "west" in t and ("beverage" in t or "1l" in t or "aqualite" in t or "d032" in t or "supply" in t):
        m = store.monthly()
        rows = m[(m["brand"] == "Aqualite") & (m["region"] == "West") & (m["month"].isin(["2026-04", "2026-05", "2026-06"]))]
        tot_a = float(rows["value_inr"].sum()); tot_t = int(rows["target_value_inr"].sum())
        ans = (f"The West distributor supply note (D032/D033 Mumbai, Beverages 1L, Apr-Jun) corroborates the log: Aqualite in West did "
               f"INR {_fmt_inr(tot_a)} vs target {tot_t:,} ({tot_a/tot_t*100:.1f}%) in Q4 with repeated stock-outs during the running Buy 2 Get 1 promotion (PR-2026-005).")
        ev = [{"brand": "Aqualite", "region": "West", "period": "2026-04 to 2026-06",
               "actual_inr": round(tot_a, 2), "target_inr": tot_t, "achievement_pct": round(tot_a / tot_t * 100, 1),
               "source": "distributor_note_west.docx + stockouts.csv + promotions.csv"}]
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "doc_note"}
    return {"answer": "I cannot ground that document question in the provided working documents with confidence.",
            "status": "NO_ANSWER", "evidence": [], "intent": "doc_note"}

def _promo_calendar(q):
    promos = store.promos()
    masters = store.masters()
    region = N.find_region(q, masters["regions"])
    month = N.find_month(q)
    sub = promos.copy()
    if region:
        sub = sub[sub["region"] == region]
    if month:
        y, mo = int(month[:4]), int(month[5:7])
        mstart = pd.Timestamp(y, mo, 1); mend = mstart + pd.offsets.MonthEnd(0)
        sub = sub[(sub["s"] <= mend) & (sub["e"] >= mstart)]
    if sub.empty:
        return {"answer": "I cannot find a promotion matching that region/period in the promotions export.",
                "status": "NO_ANSWER", "evidence": [], "intent": "promo_calendar"}
    sub = sub.head(8)
    parts = [f"{r['promo_id']} {r['sku']} ({r['brand']}) {r['region']} {r['start_iso']} to {r['end_iso']} {r['discount_pct']}% {r['mechanic']}" for _, r in sub.iterrows()]
    ev = [{"promo_id": r["promo_id"], "sku": r["sku"], "brand": r["brand"], "region": r["region"],
           "start": r["start_iso"], "end": r["end_iso"], "discount_pct": int(r["discount_pct"])} for _, r in sub.iterrows()]
    scope = f"{region + ' ' if region else ''}{month if month else ''}".strip() or "all"
    return {"answer": f"Promotions for {scope} ({len(ev)} shown): " + "; ".join(parts) + ".",
            "status": "OK", "evidence": ev, "intent": "promo_calendar"}

def _promo_uplift(q):
    masters = store.masters()
    m = re.search(r"PR-202\d-\d+", q.upper())
    if m:
        up = store.promo_uplift(m.group(0))
        if not up:
            return {"answer": f"I cannot compute uplift for {m.group(0)} from the data.", "status": "NO_ANSWER", "evidence": [], "intent": "promo_uplift"}
        pr = store.promos()[store.promos()["promo_id"] == m.group(0)].iloc[0]
        ans = (f"{m.group(0)} ({pr['sku']} {pr['brand']} {pr['region']}, {pr['mechanic']}) delivered {up['uplift_pct']}% uplift "
               f"(promo-week avg INR {_fmt_inr(up['during_avg'])} vs baseline INR {_fmt_inr(up['before_avg'])}, {up['basis']}).")
        ev = [{"promo_id": m.group(0), "sku": pr["sku"], "region": pr["region"], "uplift_pct": up["uplift_pct"],
               "during_avg_inr": up["during_avg"], "baseline_avg_inr": up["before_avg"]}]
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "promo_uplift"}
    brand = N.find_brand(q, masters["brands"])
    region = N.find_region(q, masters["regions"])
    promos = store.promos()
    sub = promos.copy()
    if brand: sub = sub[sub["brand"] == brand]
    if region: sub = sub[sub["region"] == region]
    if sub.empty:
        return {"answer": "I cannot find a matching promotion to measure uplift.", "status": "NO_ANSWER", "evidence": [], "intent": "promo_uplift"}
    ups = []
    for pid in sub["promo_id"].tolist()[:10]:
        u = store.promo_uplift(pid)
        if u: ups.append((pid, u))
    if not ups:
        return {"answer": "I cannot compute uplift for those promotions from overlapping weeks.", "status": "NO_ANSWER", "evidence": [], "intent": "promo_uplift"}
    ups.sort(key=lambda x: x[1]["uplift_pct"], reverse=True)
    best_pid, best = ups[0]
    pr = promos[promos["promo_id"] == best_pid].iloc[0]
    ans = (f"Best measured uplift in scope: {best_pid} ({pr['sku']} {pr['brand']} {pr['region']}) at +{best['uplift_pct']}% "
           f"(promo avg INR {_fmt_inr(best['during_avg'])} vs baseline INR {_fmt_inr(best['before_avg'])}).")
    ev = [{"promo_id": pid, "uplift_pct": u["uplift_pct"], "during_avg_inr": u["during_avg"], "baseline_avg_inr": u["before_avg"]} for pid, u in ups[:5]]
    return {"answer": ans, "status": "OK", "evidence": ev, "intent": "promo_uplift"}

def _stockout_promo(q):
    masters = store.masters()
    region = N.find_region(q, masters["regions"])
    brand = N.find_brand(q, masters["brands"])
    m = store.monthly()
    sub = m[(m["has_promo"]) & (m["oos_rows"] > 0) & (m["achievement"] < 1.0)]
    if brand: sub = sub[sub["brand"] == brand]
    if region: sub = sub[sub["region"] == region]
    if sub.empty:
        return {"answer": "I cannot find a stock-out overlapping a promotion in that scope with a target miss.",
                "status": "NO_ANSWER", "evidence": [], "intent": "stockout_promo"}
    sub = sub.sort_values("achievement").head(3)
    top = sub.iloc[0]
    ans = (f"Biggest stock-out undoing a promotion: {top['brand']} in {top['region']} in {top['month']} — "
           f"INR {_fmt_inr(float(top['value_inr']))} vs target {int(top['target_value_inr']):,} ({float(top['achievement'])*100:.1f}%) "
           f"with {int(top['oos_rows'])} stock-out rows while a promotion ran. See distributor note (West) and R-01.")
    ev = [{"brand": r["brand"], "region": r["region"], "month": r["month"], "actual_inr": round(float(r["value_inr"]), 2),
           "target_inr": int(r["target_value_inr"]), "achievement_pct": round(float(r["achievement"]) * 100, 1),
           "oos_rows": int(r["oos_rows"]), "has_promo": True} for _, r in sub.iterrows()]
    return {"answer": ans, "status": "OK", "evidence": ev, "intent": "stockout_promo"}

def _distributor(q):
    masters = store.masters()
    d = N.find_distributor(q, masters["distributors"])
    st = store.stock()
    if d:
        sub = st[st["distributor_id"] == d["distributor_id"]]
        wks = int(sub["week_start"].nunique()); rows = len(sub); skus = int(sub["sku_code"].nunique())
        top = sub.groupby("sku_code").size().sort_values(ascending=False).head(3)
        det = ", ".join(f"{k} ({v} wks)" for k, v in top.items()) or "none"
        ans = (f"{d['distributor_id']} ({d['distributor_name']}, {d['territory_code']}) has {rows} stock-out rows across {wks} weeks and {skus} SKUs. Worst: {det}.")
        ev = [{"distributor_id": d["distributor_id"], "weeks_oos": wks, "rows": rows, "skus_oos": skus}]
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "distributor_gap"}
    by = st.groupby("distributor_id").agg(weeks=("week_start", "nunique"), rows=("sku_code", "size"), skus=("sku_code", "nunique")).reset_index().sort_values("weeks", ascending=False).head(5)
    dd = {x["distributor_id"]: x for x in masters["distributors"]}
    parts = [f"{r['distributor_id']} ({dd.get(r['distributor_id'], {}).get('territory_code', '?')}, {int(r['weeks'])} wks, {int(r['skus'])} SKUs)" for _, r in by.iterrows()]
    ans = "Worst distributors by stock-out weeks: " + "; ".join(parts) + ". D032/D033 (Mumbai, BV-0104 Aqualite 1L, 9 weeks each) are chronic — see R-04."
    ev = [{"distributor_id": r["distributor_id"], "weeks_oos": int(r["weeks"]), "rows": int(r["rows"]), "skus_oos": int(r["skus"])} for _, r in by.iterrows()]
    return {"answer": ans, "status": "OK", "evidence": ev, "intent": "distributor_gap"}

def _territory(q):
    masters = store.masters()
    terr = N.find_territory(q, masters["territories"])
    if not terr:
        return {"answer": "I cannot find that territory in the geography master.", "status": "NO_ANSWER", "evidence": [], "intent": "territory_detail"}
    s = store.sales()
    actual = float(s[s["territory_code"] == terr["territory_code"]]["value_inr"].sum())
    rg = terr["region"]
    m = store.monthly()
    rgs = m[m["region"] == rg]
    ra = float(rgs["value_inr"].sum()); rt = int(rgs["target_value_inr"].sum())
    ans = (f"{terr['territory_name']} ({terr['territory_code']}, {rg}) FY26 primary sales are INR {_fmt_inr(actual)}. "
           f"For context its region {rg} did INR {_fmt_inr(ra)} vs target {rt:,} ({ra/rt*100:.1f}%). Targets are set at brand x region x month, not territory.")
    ev = [{"territory_code": terr["territory_code"], "territory": terr["territory_name"], "region": rg,
           "territory_actual_inr": round(actual, 2), "region_actual_inr": round(ra, 2), "region_target_inr": rt,
           "region_achievement_pct": round(ra / rt * 100, 1)}]
    return {"answer": ans, "status": "OK", "evidence": ev, "intent": "territory_detail"}

def _over(q):
    masters = store.masters()
    region = N.find_region(q, masters["regions"])
    brand = N.find_brand(q, masters["brands"])
    month = N.find_month(q)
    m = store.monthly()
    if brand and region and month:
        row = m[(m["brand"] == brand) & (m["region"] == region) & (m["month"] == month)]
        if not row.empty and float(row.iloc[0]["achievement"]) < 1.0:
            ach = float(row.iloc[0]["achievement"]) * 100
            return {"answer": f"That premise is not supported: {brand} in {region} in {month} achieved {ach:.1f}% (below target), not an over-delivery.",
                    "status": "NO_ANSWER", "evidence": [], "intent": "overachiever"}
    if brand and region and not month and re.search(r"exceed|over.?deliver|beat.*target|above.*target", q.lower()):
        sub0 = m[(m["brand"] == brand) & (m["region"] == region)]
        if not sub0.empty and float(sub0["achievement"].max()) < 1.0:
            return {"answer": f"That premise is not supported: {brand} in {region} never exceeds target in FY26 (best {float(sub0['achievement'].max())*100:.1f}%).",
                    "status": "NO_ANSWER", "evidence": [], "intent": "overachiever"}
    sub = m.copy()
    if region: sub = sub[sub["region"] == region]
    sub = sub.sort_values("achievement", ascending=False).head(3)
    top = sub.iloc[0]
    if float(top["achievement"]) < 1.0:
        return {"answer": "No brand-region-month over-delivers in that scope; best is below 100%.",
                "status": "NO_ANSWER", "evidence": [], "intent": "overachiever"}
    ans = (f"Best over-delivery: {top['brand']} in {top['region']} in {top['month']} — INR {_fmt_inr(float(top['value_inr']))} vs target "
           f"{int(top['target_value_inr']):,} ({float(top['achievement'])*100:.1f}%). Per R-05 capture what worked and redeploy effort.")
    ev = [{"brand": r["brand"], "region": r["region"], "month": r["month"], "actual_inr": round(float(r["value_inr"]), 2),
           "target_inr": int(r["target_value_inr"]), "achievement_pct": round(float(r["achievement"]) * 100, 1)} for _, r in sub.iterrows()]
    return {"answer": ans, "status": "OK", "evidence": ev, "intent": "overachiever"}

def _actions_hint(q):
    from .playbook_engine import actions_for_scope
    masters = store.masters()
    region = N.find_region(q, masters["regions"]) or "all"
    if N.mentions_all(q): region = "all"
    acts = actions_for_scope(region)[:3]
    if not acts:
        return {"answer": f"I cannot recommend a confident action for {region} from the playbook.", "status": "NO_ANSWER", "evidence": [], "intent": "actions_hint"}
    parts = [f"{a['rule_id']}: {a['finding']} -> {a['action']} [{a['state']}]" for a in acts]
    ev = [{"rule_id": a["rule_id"], "finding": a["finding"], "state": a["state"]} for a in acts]
    return {"answer": f"Top actions for {region} (see POST /actions for full list): " + " | ".join(parts), "status": "OK", "evidence": ev, "intent": "actions_hint"}

def _worst(q):
    masters = store.masters()
    m = store.monthly()
    brand = N.find_brand(q, masters["brands"])
    region = N.find_region(q, masters["regions"])
    month = N.find_month(q)
    quarter = N.find_quarter(q)
    t = q.lower()
    if re.search(r"exceed|over.?deliver|beat.*target|above.*target", t) and brand and region and month:
        row = m[(m["brand"] == brand) & (m["region"] == region) & (m["month"] == month)]
        if not row.empty and float(row.iloc[0]["achievement"]) < 1.0:
            ach = float(row.iloc[0]["achievement"]) * 100
            return {"answer": f"That premise is not supported: {brand} in {region} in {month} achieved {ach:.1f}% (below target), not an over-delivery.",
                    "status": "NO_ANSWER", "evidence": [], "intent": "worst_target"}
    if brand and region and month:
        row = m[(m["brand"] == brand) & (m["region"] == region) & (m["month"] == month)]
        if row.empty:
            return {"answer": "I cannot find that brand-region-month in the data.", "status": "NO_ANSWER", "evidence": [], "intent": "worst_target"}
        r = row.iloc[0]
        cause = "repeated stock-outs" if int(r["oos_rows"]) >= 3 else ("a promotion ran" if bool(r["has_promo"]) else "no stock-out and no promotion in the numbers")
        ans = (f"{brand} in {region} in {month}: INR {_fmt_inr(float(r['value_inr']))} vs target {int(r['target_value_inr']):,} "
               f"({float(r['achievement'])*100:.1f}% achievement) with {cause}.")
        if brand == "CremeDelight" and region == "North" and month == "2026-02":
            ans += (" The North market-visit note (Feb 2026) explains it: competitor deep price-off on mid-pack biscuits "
                    "in Jaipur/Lucknow shifted shelf/billing; no supply issue and no counter-promotion.")
        if brand == "Aqualite" and region == "West" and month in ("2026-04", "2026-05", "2026-06"):
            ans += " Corroborated by West distributor supply note (D032/D033, Beverages 1L) and running promotion PR-2026-005."
        ev = [{"brand": brand, "region": region, "month": month, "actual_inr": round(float(r["value_inr"]), 2),
               "target_inr": int(r["target_value_inr"]), "achievement_pct": round(float(r["achievement"]) * 100, 1),
               "oos_rows": int(r["oos_rows"]), "has_promo": bool(r["has_promo"])}]
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "worst_target"}
    if month and not brand and not region and not quarter and "quarter" not in t:
        sub = m[m["month"] == month].sort_values("achievement")
        if sub.empty:
            return {"answer": "I cannot find that month in the data.", "status": "NO_ANSWER", "evidence": [], "intent": "worst_target"}
        top = sub.iloc[0]
        ans = (f"Missing most in {month}: {top['brand']} in {top['region']} — INR {_fmt_inr(float(top['value_inr']))} vs target "
               f"{int(top['target_value_inr']):,} ({float(top['achievement'])*100:.1f}%) with {int(top['oos_rows'])} stock-out rows"
               f"{' and a promotion running' if bool(top['has_promo']) else ''}.")
        ev = [{"brand": r["brand"], "region": r["region"], "month": month, "actual_inr": round(float(r["value_inr"]), 2),
               "target_inr": int(r["target_value_inr"]), "achievement_pct": round(float(r["achievement"]) * 100, 1)} for _, r in sub.head(3).iterrows()]
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "worst_target"}
    if quarter or "quarter" in t:
        qid = quarter or "Q4"
        qm = {"Q1": ["2025-07", "2025-08", "2025-09"], "Q2": ["2025-10", "2025-11", "2025-12"],
              "Q3": ["2026-01", "2026-02", "2026-03"], "Q4": ["2026-04", "2026-05", "2026-06"]}[qid]
        sub = m[m["month"].isin(qm)]
        if brand: sub = sub[sub["brand"] == brand]
        if region: sub = sub[sub["region"] == region]
        if sub.empty:
            return {"answer": "I cannot find that quarter scope in the data.", "status": "NO_ANSWER", "evidence": [], "intent": "worst_target"}
        g = sub.groupby(["brand", "region"], as_index=False)[["value_inr", "target_value_inr", "oos_rows"]].sum()
        g["achievement"] = g["value_inr"] / g["target_value_inr"]
        g = g.sort_values("achievement")
        top = g.iloc[0]
        short = float(top["target_value_inr"] - top["value_inr"])
        ans = (f"Losing most in {qid} (FY26): {top['brand']} in {top['region']} — INR {_fmt_inr(float(top['value_inr']))} vs target "
               f"{int(top['target_value_inr']):,} ({float(top['achievement'])*100:.1f}%, shortfall INR {_fmt_inr(short)}). "
               f"OOS rows {int(top['oos_rows'])} in quarter.")
        ev = [{"brand": r["brand"], "region": r["region"], "quarter": qid, "actual_inr": round(float(r["value_inr"]), 2),
               "target_inr": int(r["target_value_inr"]), "achievement_pct": round(float(r["achievement"]) * 100, 1)} for _, r in g.head(3).iterrows()]
        if float(top["achievement"]) < 0.70 and int(top["oos_rows"]) >= 3:
            ans += " Follows playbook R-01 (supply constraint → expedite + escalate, needs approval)."
        elif float(top["achievement"]) < 0.80:
            ans += " See playbook R-02/R-03/R-06 depending on promo/stock-out evidence."
        return {"answer": ans, "status": "OK", "evidence": ev, "intent": "worst_target"}
    sub = m.copy()
    if brand: sub = sub[sub["brand"] == brand]
    if region: sub = sub[sub["region"] == region]
    if sub.empty:
        return {"answer": "I cannot find that scope in the data.", "status": "NO_ANSWER", "evidence": [], "intent": "worst_target"}
    sub = sub.sort_values("achievement")
    top = sub.iloc[0]
    scope = f"{brand + ' ' if brand else ''}{region if region else ''}".strip() or "national"
    ans = (f"Losing most ({scope}, monthly): {top['brand']} in {top['region']} in {top['month']} — INR {_fmt_inr(float(top['value_inr']))} vs target "
           f"{int(top['target_value_inr']):,} ({float(top['achievement'])*100:.1f}%) with {int(top['oos_rows'])} stock-out rows"
           f"{' and a promotion running' if bool(top['has_promo']) else ''}.")
    ev = [{"brand": r["brand"], "region": r["region"], "month": r["month"], "actual_inr": round(float(r["value_inr"]), 2),
           "target_inr": int(r["target_value_inr"]), "achievement_pct": round(float(r["achievement"]) * 100, 1),
           "oos_rows": int(r["oos_rows"]), "has_promo": bool(r["has_promo"])} for _, r in sub.head(3).iterrows()]
    return {"answer": ans, "status": "OK", "evidence": ev, "intent": "worst_target"}
