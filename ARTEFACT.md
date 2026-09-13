# ARTEFACT — honest self-audit (real numbers, reproducible via `python prepare.py` + `python eval/run.py`)

## 1. Rows held after preparation (`data/processed/stats.json`)

- `fact_primary_sales.csv`: 74880 → `sales.parquet`: 74880
- `fact_targets.csv`: 720 → `targets.parquet`: 720
- `stockouts.csv`: 520 → `stockouts.parquet`: 520
- `promotions.csv`: 40 → `promotions.parquet`: 40
- `dim_sku.csv`: 120 → `sku.parquet`: 120
- `dim_geo.csv`: 12 → `geo.parquet`: 12
- `dim_distributor.csv`: 40 → `dist.parquet`: 40
- Plus `masters.json`, `docs_text.json` (6 docs), `playbook.json` (8 rules), `stats.json`

## 2. National FY26 primary-sales total (as system computes it)

- **1357631078.74 INR** (`sales.value_inr.sum()`, July 2025–June 2026, 52 weeks, 74880 rows). Target total 1360880000 INR.

## 3. Cross-source mismatches reconciled (one line apiece)

- `stockouts.region` 16 variants (EAST/east/East/East Region…) vs master East/North/South/West → normalised strip/lower/remove ' region'/Title in `prepare.py:norm_region`.
- `stockouts.item_code` vs `dim_sku.sku_code` vs `promotions.sku` same values, different names → unified to `sku_code`.
- `promotions` DD/MM/YYYY vs `sales` YYYY-MM-DD → parsed `dayfirst=True` to ISO, expanded to overlapping weeks for uplift.
- Weekly sales vs monthly targets → week belongs to month containing `week_start` per dictionary, aggregated to YYYY-MM before `achievement=actual/target`.
- Targets brand×region vs sales SKU×territory → joined via `sku→brand` + `territory→region` masters.
- Distributor→territory→region chain vs log free-text region → master trusted, log region only a check.
- Docs pack phrases (Beverages 1L, 90g North, CremeDelight North Feb) vs SKU codes → resolved via SKU master + promo calendar, never guessed.

## 4. Evaluation (`eval/questions.jsonl` 35, `eval/run.py` → `eval/results.json`)

- First smoke accuracy: **32/35 = 91.4%** pattern (guardrail false positives — generic “which brand-region…” flagged as unknown, promo ID `PR-2025-058` misread as SKU, “Why did Aqualite exceed…” missed false-premise check).
- Biggest gap: guardrail precision + missing month-only worst-month branch + false-premise miss in over-delivery path.
- One change: guardrail precision (skip generic which/brand-region/per-region; exclude `PR-` from SKU check) + `month-only` branch + false-premise check in `_over` + doc grounding for CremeDelight-Feb/Aqualite-West (`src/guardrails.py`, `src/solvers.py`).
- Accuracy after: **35/35 = 100.0%**; median cost per question **0.0 USD**; latency **p50 1.8ms / p95 98.2ms** (min 0.0, max 1792.2 cold-load; warm ~2ms). Actions checks pass: West/all/North return `rule_id` + `PENDING_APPROVAL` where required (e.g. West R-01 Aqualite Jun 62.0%, R-04 D032/D033 BV-0104 9 weeks).