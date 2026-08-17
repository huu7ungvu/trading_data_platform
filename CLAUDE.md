# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status — read this before touching code

This is an early-stage personal side project, built incrementally. As of now, almost every
Python/SQL/bash file under `pipelines/`, `simulated_app/`, `minio/`, `clickhouse/`, and
`transformations/` is a **committed empty stub** (0 bytes) — scaffolded on purpose, not broken.
The only things that actually run today are:

- `docker-compose.yml` — Postgres, MinIO, ClickHouse + one-off `*-init` jobs
- `pipelines/test/01_getting_started.py` — a sample Prefect flow proving the local Prefect setup works

Do not assume `ingest__*.py`, `load__bronze.py`, `orch__*.py`, the dbt project, or the init
scripts have any logic in them unless you just wrote it. Check `## Project Status` in the root
[README.md](README.md) for the current build checklist before assuming a layer is implemented.

## Commands

No linter or test suite is committed yet (see status above) — don't invent `pytest`/`ruff`/`make`
commands. A pinned dependency manifest (`requirements.txt`, `pip freeze` output) is committed.
What actually exists:

```bash
# Local infra: Postgres (simulated app DB), MinIO (Landing), ClickHouse (Bronze/Silver/Gold)
docker compose up -d
docker compose down

# One-off seed/reset jobs (profile "init" — never run by plain `up`, safe to re-run anytime)
docker compose run --rm pg-init      # simulated_app/generate_script.sql   -> Postgres schema/seed
docker compose run --rm minio-init   # minio/generate_scipt.bash           -> Landing buckets
docker compose run --rm ch-init      # clickhouse/generate_scipt.bash      -> Bronze/Silver/Gold schemas

# Python/Prefect env (uv)
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Run/deploy the sample flow
cd pipelines && python test/01_getting_started.py
```

Config is layered across three untracked locations, each with a committed `*_example`/`.env.example`
template to copy from: `.env` (infra credentials/ports), `pipelines/config/watermark/watermark.yml`
(incremental-load state), `pipelines/credential/` (API tokens for `ingest__vns.py` etc.).

## Architecture

Medallion pipeline, cross-cut by orchestration and governance (full detail in root [README.md](README.md)):

| Layer | Storage | Purpose |
|---|---|---|
| Landing | MinIO (Parquet/ORC) | Immutable dump of every source payload, as received |
| Bronze | ClickHouse | Raw data loaded and typed against a schema; nothing dropped/corrected |
| Silver | ClickHouse | Cleaned, deduplicated, standardized |
| Gold | ClickHouse | Star/snowflake business data model |
| Semantic | Cube | Metrics/dimensions API decoupled from physical schema |

Orchestration is Prefect; transformation (Silver/Gold) is dbt, triggered from within each Prefect flow.

### `pipelines/` design principle

Extraction/loading logic is generic and written **once per source or destination**; orchestration is
the only thing written **once per dataset**. Concretely:

- `ingestion/ingest__<source>.py` and `loading/load__<destination>.py` take source/table/schema as
  parameters — they must stay dataset-agnostic. Don't hardcode a table name into these.
- `orchestration/orch__<source>__<entity>.py` is where dataset-specific wiring lives: one concrete
  Prefect flow per dataset, composing `ingest__*` + `load__*`, then triggering the dbt run.
- **Adding a new dataset should only ever mean adding a new `orch__*` file** (+ its schema in
  `config/schema/` + a watermark key), not new extraction/loading code. If a change touches
  `ingest__tdb.py` or `load__bronze.py` to special-case one table, that's a signal to reconsider.

A flow's shape is always **extract → load → trigger dbt**:
1. `ingest__<source>` reads the last watermark (`watermark_loader`), pulls only changed rows since
   then (CDC for Postgres, incremental pull for the vnstock API), writes to MinIO Landing, then
   advances the watermark — only after the write succeeds.
2. `load__bronze` reads the newly landed objects and loads them into ClickHouse per the table's
   `config/schema/*.json`.
3. The flow triggers `dbt run`/`build` so Silver/Gold pick up the new Bronze rows in the same run
   rather than waiting on a separate schedule.

Full naming convention and the "adding a new pipeline" checklist are in
[pipelines/README.md](pipelines/README.md) — read it before adding a new `orch__*` flow.
