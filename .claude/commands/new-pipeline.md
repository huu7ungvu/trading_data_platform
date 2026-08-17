---
description: Scaffold a new dataset pipeline (schema + orch file + watermark key)
---

Add a new pipeline for source `$1`, entity `$2`, following the convention documented in
pipelines/README.md ("Adding a New Pipeline" and the generic-ingest/load design principle):

1. Create `pipelines/config/schema/$2.json` — a per-table schema definition consumed by
   `load__bronze.py`. Ask me for the column list if it isn't already clear from context
   (e.g. from `simulated_app/generate_script.sql` or an existing schema file to match the shape).
2. Create `pipelines/orchestration/orch__$1__$2.py`: a concrete Prefect flow that calls
   `ingest__$1(table="$2", watermark_key="$1.$2", ...)` then
   `load__bronze(schema="config/schema/$2.json", destination="bronze.$2")`, then triggers the
   dbt run/build step — mirror the shape of `orch__tdb__users.py` if it already has real logic.
3. Add a `$1: { $2: { last_watermark: ... } }` entry to
   `pipelines/config/watermark/watermark.example.yml` (never edit the real, gitignored
   `watermark.yml`).
4. Do NOT modify `pipelines/ingestion/ingest__$1.py` or `pipelines/loading/load__bronze.py` to
   special-case this dataset — they must stay generic, parameterized by source/table/schema. If
   the new dataset needs something those generic files don't support, stop and flag it to me
   instead of hardcoding around it.
5. Remind me that the Prefect deployment + schedule for the new flow is still a manual step.

If `$1` or `$2` wasn't given, ask me for the source (e.g. `tdb`, `vns`) and entity/table name
before doing anything.
