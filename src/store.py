"""Central data store: loads processed parquet once, exposes helpers."""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"

_sales = None
_targets = None
_stock = None
_promo = None
_masters = None
_docs = None
_playbook = None
_monthly = None

FY_QMAP = {
    "2025-07": "Q1", "2025-08": "Q1", "2025-09": "Q1",
    "2025-10": "Q2", "2025-11": "Q2", "2025-12": "Q2",
    "2026-01": "Q3", "2026-02": "Q3", "2026-03": "Q3",
    "2026-04": "Q4", "2026-05": "Q4", "2026-06": "Q4",
}

def _load():
    global _sales, _targets, _stock, _promo, _masters, _docs, _playbook, _monthly
    if _sales is not None:
        return
    if not (PROC / "sales.parquet").exists():
        raise RuntimeError("Processed data missing. Run: python prepare.py")
    _sales = pd.read_parquet(PROC / "sales.parquet")
    _targets = pd.read_parquet(PROC / "targets.parquet")
    _stock = pd.read_parquet(PROC / "stockouts.parquet")
    _promo = pd.read_parquet(PROC / "promotions.parquet")
    _masters = json.loads((PROC / "masters.json").read_text(encoding="utf-8"))
    _docs = json.loads((PROC / "docs_text.json").read_text(encoding="utf-8"))
    _playbook = json.loads((PROC / "playbook.json").read_text(encoding="utf-8"))
    _sales["week_start"] = pd.to_datetime(_sales["week_start"])
    _stock["week_start"] = pd.to_datetime(_stock["week_start"])
    _promo["s"] = pd.to_datetime(_promo["start_iso"])
    _promo["e"] = pd.to_datetime(_promo["end_iso"])
    _monthly = _build_monthly()

def _build_monthly():
    agg = _sales.groupby(["month", "brand", "region"], as_index=False)["value_inr"].sum()
    m = agg.merge(_targets, left_on=["month", "brand", "region"],
                  right_on=["month", "brand_name", "region_name"], how="left")
    m["achievement"] = m["value_inr"] / m["target_value_inr"]
    oos = _stock.groupby(["month", "brand", "norm_region"]).size().reset_index(name="oos_rows")
    m = m.merge(oos, left_on=["month", "brand", "region"],
                right_on=["month", "brand", "norm_region"], how="left")
    m["oos_rows"] = m["oos_rows"].fillna(0).astype(int)
    m["has_promo"] = m.apply(lambda r: _brand_month_has_promo(r["brand"], r["region"], r["month"]), axis=1)
    m["quarter"] = m["month"].map(FY_QMAP)
    return m

def _brand_month_has_promo(brand, region, month):
    y, mo = int(month[:4]), int(month[5:7])
    mstart = pd.Timestamp(y, mo, 1)
    mend = (mstart + pd.offsets.MonthEnd(0))
    sub = _promo[(_promo["brand"] == brand) & (_promo["region"] == region)]
    for _, r in sub.iterrows():
        if r["s"] <= mend and r["e"] >= mstart:
            return True
    return False

def sales(): _load(); return _sales
def targets(): _load(); return _targets
def stock(): _load(); return _stock
def promos(): _load(); return _promo
def masters(): _load(); return _masters
def docs(): _load(); return _docs
def playbook(): _load(); return _playbook
def monthly(): _load(); return _monthly
def quarterly():
    _load()
    q = _monthly.groupby(["quarter", "brand", "region"], as_index=False)[["value_inr", "target_value_inr", "oos_rows"]].sum()
    q["achievement"] = q["value_inr"] / q["target_value_inr"]
    return q

def promo_uplift(promo_id: str):
    """SKU-region weekly avg during promo vs 4 weeks before. Returns dict or None."""
    _load()
    row = _promo[_promo["promo_id"] == promo_id]
    if row.empty:
        return None
    row = row.iloc[0]
    sk, rg, s, e = row["sku"], row["region"], row["s"], row["e"]
    sub = _sales[(_sales["sku_code"] == sk) & (_sales["region"] == rg)]
    before = sub[(sub["week_start"] >= s - pd.Timedelta(days=28)) & (sub["week_start"] < s)]
    during = sub[(sub["week_start"] >= s) & (sub["week_start"] <= e)]
    if before.empty or during.empty:
        after = sub[(sub["week_start"] > e) & (sub["week_start"] <= e + pd.Timedelta(days=28))]
        if after.empty or during.empty:
            return None
        up = float(during["value_inr"].mean() / after["value_inr"].mean() - 1)
        return {"promo_id": promo_id, "uplift_pct": round(up * 100, 1),
                "before_avg": round(float(after["value_inr"].mean()), 2),
                "during_avg": round(float(during["value_inr"].mean()), 2),
                "n_before": len(after), "n_during": len(during), "basis": "vs_4w_after"}
    up = float(during["value_inr"].mean() / before["value_inr"].mean() - 1)
    return {"promo_id": promo_id, "uplift_pct": round(up * 100, 1),
            "before_avg": round(float(before["value_inr"].mean()), 2),
            "during_avg": round(float(during["value_inr"].mean()), 2),
            "n_before": len(before), "n_during": len(during), "basis": "vs_4w_before"}
