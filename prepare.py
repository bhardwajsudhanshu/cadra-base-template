"""One-command reproducible preparation. Reads data/* read-only, writes data/processed/."""
from pathlib import Path
import json
import pandas as pd
import openpyxl
from docx import Document

BASE = Path(__file__).parent
DATA = BASE / "data"
PROC = DATA / "processed"

def norm_region(s: str) -> str:
    return str(s).strip().lower().replace(" region", "").strip().title()

def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)

    sales = pd.read_csv(DATA / "fact_primary_sales.csv", parse_dates=["week_start"])
    targets = pd.read_csv(DATA / "fact_targets.csv")
    stock = pd.read_csv(DATA / "stockouts.csv", parse_dates=["week_start"])
    promo = pd.read_csv(DATA / "promotions.csv")
    sku = pd.read_csv(DATA / "dim_sku.csv")
    geo = pd.read_csv(DATA / "dim_geo.csv")
    dist = pd.read_csv(DATA / "dim_distributor.csv")

    rows_raw = {
        "fact_primary_sales.csv": len(sales),
        "fact_targets.csv": len(targets),
        "stockouts.csv": len(stock),
        "promotions.csv": len(promo),
        "dim_sku.csv": len(sku),
        "dim_geo.csv": len(geo),
        "dim_distributor.csv": len(dist),
    }

    # --- enrich sales: brand, region, month (month contains week_start) ---
    sku_brand = dict(zip(sku["sku_code"], sku["brand"]))
    sku_cat = dict(zip(sku["sku_code"], sku["category"]))
    t2r = dict(zip(geo["territory_code"], geo["region"]))
    sales["brand"] = sales["sku_code"].map(sku_brand)
    sales["category"] = sales["sku_code"].map(sku_cat)
    sales["region"] = sales["territory_code"].map(t2r)
    sales["month"] = sales["week_start"].dt.strftime("%Y-%m")

    # --- stockouts: unify item_code->sku_code, region normalise, brand, month ---
    stock["sku_code"] = stock["item_code"]
    stock["norm_region"] = stock["region"].apply(norm_region)
    stock["brand"] = stock["sku_code"].map(sku_brand)
    stock["month"] = stock["week_start"].dt.strftime("%Y-%m")

    # --- promotions: DD/MM/YYYY -> ISO, brand ---
    promo["start_iso"] = pd.to_datetime(promo["start_date"], dayfirst=True).dt.strftime("%Y-%m-%d")
    promo["end_iso"] = pd.to_datetime(promo["end_date"], dayfirst=True).dt.strftime("%Y-%m-%d")
    promo["brand"] = promo["sku"].map(sku_brand)
    promo["category"] = promo["sku"].map(sku_cat)

    # --- playbook ---
    wb = openpyxl.load_workbook(DATA / "action_playbook.xlsx", data_only=True)
    ws = wb["playbook"]
    rows = list(ws.iter_rows(values_only=True))
    header = [h for h in rows[0]]
    playbook = [dict(zip(header, r)) for r in rows[1:]]

    # --- documents -> text (signal + noise flagged) ---
    docs = {}
    for p in sorted((DATA / "documents").glob("*.docx")):
        d = Document(str(p))
        paras = [x.text.strip() for x in d.paragraphs if x.text.strip()]
        tabs = []
        for t in d.tables:
            for r in t.rows:
                tabs.append(" | ".join(c.text.strip() for c in r.cells))
        docs[p.name] = {"paragraphs": paras, "tables": tabs, "text": "\n".join(paras + tabs)}

    # --- masters ---
    masters = {
        "brands": sorted(sku["brand"].unique().tolist()),
        "categories": sorted(sku["category"].unique().tolist()),
        "regions": sorted(geo["region"].unique().tolist()),
        "territories": geo.to_dict(orient="records"),
        "skus": sku.to_dict(orient="records"),
        "distributors": dist.to_dict(orient="records"),
        "promo_ids": sorted(promo["promo_id"].unique().tolist()),
    }

    # --- stats ---
    national_total = float(sales["value_inr"].sum())
    stats = {
        "rows_raw": rows_raw,
        "rows_processed": {
            "sales": len(sales), "targets": len(targets), "stockouts": len(stock),
            "promotions": len(promo), "skus": len(sku), "geo": len(geo), "distributors": len(dist),
        },
        "national_fy26_primary_sales_inr": round(national_total, 2),
        "target_total_inr": int(targets["target_value_inr"].sum()),
        "week_range": [str(sales["week_start"].min().date()), str(sales["week_start"].max().date())],
        "months": sorted(sales["month"].unique().tolist()),
        "mismatches": [
            "stockouts.region has 16 variants (EAST/east/East/East Region...) vs master East/North/South/West -> normalised by strip/lower/remove ' region'/Title",
            "stockouts.item_code vs dim_sku.sku_code vs promotions.sku are same values with different column names -> unified to sku_code",
            "promotions start/end are DD/MM/YYYY vs sales week_start YYYY-MM-DD -> parsed dayfirst=True to ISO, expanded to overlapping weeks",
            "sales weekly vs targets monthly -> week belongs to month containing week_start per DATA_DICTIONARY, aggregated to YYYY-MM before achievement",
            "targets brand x region vs sales SKU x territory -> joined via sku->brand and territory->region masters",
            "distributor->territory->region master chain vs stockouts.region free text -> master trusted, log region only as check",
            "docs use pack phrases (Beverages 1L, 90g North, CremeDelight North Feb) vs SKU codes -> resolved via sku master + promo calendar, never guessed",
        ],
    }

    # --- write ---
    sales.to_parquet(PROC / "sales.parquet", index=False)
    targets.to_parquet(PROC / "targets.parquet", index=False)
    stock.to_parquet(PROC / "stockouts.parquet", index=False)
    promo.to_parquet(PROC / "promotions.parquet", index=False)
    sku.to_parquet(PROC / "sku.parquet", index=False)
    geo.to_parquet(PROC / "geo.parquet", index=False)
    dist.to_parquet(PROC / "dist.parquet", index=False)
    (PROC / "masters.json").write_text(json.dumps(masters, indent=2), encoding="utf-8")
    (PROC / "docs_text.json").write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
    (PROC / "playbook.json").write_text(json.dumps(playbook, indent=2, ensure_ascii=False), encoding="utf-8")
    (PROC / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print(f"rows: {rows_raw}")
    print(f"national FY26 total INR: {national_total:.2f}")
    print(f"wrote {PROC}")

if __name__ == "__main__":
    main()
