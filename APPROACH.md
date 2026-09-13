# Approach

## Problem Summary

I built the Monday assistant for ACPL sales-ops: where we lose vs target and what to do in West, North, South, East.

I cover 10 question types myself: worst vs target by month, quarter, brand, region, over-delivery, promo uplift via promo-week vs 4 weeks before, stockout undoing promo, distributor gaps, territory actual plus region context because targets are only brand x region x month, promo calendar, SOP and field notes, national total, and action hints.

I cover all 8 playbook rules: R-01 below 70% plus 3 or more OOS rows, R-02 below 80% plus promo no OOS, R-03 below 80% no OOS no promo with note like CremeDelight North Feb, R-06 same with no note, R-05 above 110%, R-07 uplift above 25%, R-04 distributor SKU over 6 weeks, R-08 distributor 3 plus SKUs in a month.

I left out by design: FY27 forecast, profit, margin, market share, HR leave, territory targets which do not exist in fact_targets, and inventing causes. SOP says do not invent, so R-06 flags manual review. Code is in app.py, prepare.py, src/store.py, normalizer.py, intent_router.py, solvers.py, playbook_engine.py, guardrails.py, metrics.py. Eval is in eval/questions.jsonl, run.py, results.json.

## Technical Approach

I kept one FastAPI service with POST /ask, POST /actions, GET /health. No DB server, no runtime model. prepare.py reads data as-is and writes parquet plus masters, docs_text, playbook and stats to data/processed. Store loads once on startup.

My request flow: normalizer with synonyms plus RapidFuzz for brand, region, territory, SKU, distributor, month and quarter, then guardrails for injection, unknown entity and out-of-FY26 or out-of-scope, then regex router, then pandas solvers, then playbook map. Q1 Jul-Sep 25, Q2 Oct-Dec 25, Q3 Jan-Mar 26, Q4 Apr-Jun 26. Week belongs to month containing week_start.

For grounding I use escalation_sop for approval, visit_note_north for CremeDelight North Feb 72%, distributor_note_west for Aqualite West Q4 62% plus PR-2026-005, promo circular for mechanics. hr_circular and weekly_summary_w32 I ignore. I reconciled in prepare.py: 16 region variants normalised, item_code and sku unified to sku_code, DD/MM/YYYY parsed dayfirst and expanded to weeks, weekly aggregated to monthly before achievement, SKU x territory joined to brand x region, master chain trusted over log text, doc phrases resolved via masters.

An action is finding plus rule_id plus action plus state. I emit only when threshold plus evidence match, else empty list. R-01, R-04, R-08 are PENDING_APPROVAL because they notify or change commitment. R-02, R-03, R-05, R-06, R-07 are RECOMMENDED.

I measure cost and latency myself with perf_counter in app.py via metrics.py. Cost is 0.0 with no tokens. Actions keeps list body exact and puts measured values in X-Cost-Usd and X-Latency-Ms headers. My eval is 35 questions with OK, NO_ANSWER and OK_OR_NO plus rule_id checks for West, all and North. Result is 35/35 100%, p50 2.4ms p95 103.8ms, median $0, cold first load about 1500ms then about 2ms warm. Unknown scope returns empty list, false premise like Aqualite exceeded in West May returns NO_ANSWER.

## AI Tool Usage

I used Cadra sparingly for scaffolding and debugging. Design, playbook mapping, guardrails and eval cases were mine. I asked for small file-level changes, ran prepare.py and eval/run.py myself after each change, and kept deterministic pandas logic so runtime needs no model. Most time went to manual checks of totals, mismatches and NO_ANSWER cases.

## Trade-offs & Limitations

I chose code-not-LLM for $0, speed and zero hallucination, gave up fluent chat and fixed to 8 intents. I chose local parquet for one-command repro and audit, gave up big-data scale past a few million rows. I chose manual synonyms for offline phrasing, gave up zero-config NLU. I capped at 12 actions to keep Monday usable, gave up exhaustive list. Approval gates add PENDING friction but follow SOP. Territory apportioning I refused to do because data has no territory targets.