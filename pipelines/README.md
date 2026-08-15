# Pipelines

Prefect project that implements the platform's **ingestion → Landing → Bronze** flow, and triggers dbt for everything downstream of Bronze.

See the [root README](../README.md) for the full platform architecture. This document covers only how this `pipelines/` project is organized.

## Design Principle

Extraction and loading logic is written **once per source/destination and reused**; only orchestration is written **once per dataset**:

- **`ingestion/`** and **`loading/`** hold generic, parameterized logic. They don't know about any specific table — they take a source/table/schema as arguments.
- **`orchestration/`** holds one concrete Prefect flow per dataset, gluing the generic pieces together with that dataset's specific parameters, then triggering dbt.

This means adding a new pipeline for a new table is (ideally) a new file in `orchestration/`, not new extraction/loading code.

## Structure

```
pipelines/
├── ingestion/
│   ├── ingest__tdb.py       # Generic CDC extractor for the simulated trading app DB
│   └── ingest__vns.py       # Generic extractor for the vnstock market-data API
├── loading/
│   └── load__bronze.py      # Generic loader: MinIO Landing → ClickHouse Bronze
├── orchestration/
│   └── orch__tdb__users.py  # Concrete pipeline: users CDC → Bronze → dbt trigger
├── config/
│   ├── schema/               # Per-table schema definitions (consumed by load__bronze)
│   └── watermark/            # Per-source/table incremental watermark state (gitignored)
├── credential/                # Local secrets — API tokens, app credentials (gitignored)
├── utils/common/
│   ├── credential_handler.py # Reads/validates credentials for auth & authorization
│   ├── datetime_handler.py   # Datetime/timezone helpers
│   └── watermark_loader.py   # Reads & advances watermark state
└── test/                      # Scratch scripts to sanity-check the local Prefect setup
```

## How a Pipeline Runs

Example: `orch__tdb__users`

1. **Extract** — calls `ingest__tdb(table="users", watermark_key="tdb.users", ...)`:
   - loads the last watermark for `users` via `watermark_loader`
   - pulls changed rows (CDC) from the trading app DB since that watermark
   - writes the batch to MinIO Landing as Parquet/ORC
   - advances the watermark once the write succeeds
2. **Load** — calls `load__bronze(schema="config/schema/orders.json", destination="bronze.users", ...)`:
   - reads the newly landed objects from MinIO
   - loads them into the ClickHouse Bronze table per the schema config
3. **Transform** — triggers `dbt run` (or `build`) so Silver/Gold models pick up the new Bronze rows as part of the same pipeline run, instead of waiting on a separate schedule.

Every `orch__*` flow follows this extract → load → dbt-trigger shape; only the source, table, schema, and destination change.

## Naming Convention

| Pattern | Meaning |
|---|---|
| `ingest__<source>` | Generic extractor for one source (`tdb` = simulated trading app DB, `vns` = vnstock API) |
| `load__<destination>` | Generic loader for one destination layer (`bronze` = ClickHouse Bronze) |
| `orch__<source>__<entity>` | One concrete Prefect flow per dataset — composes ingest + load + dbt trigger |

## Adding a New Pipeline

To onboard a new dataset (e.g. `tdb` orders):

1. Add its schema to `config/schema/`.
2. Add `orch__tdb__orders.py` calling `ingest__tdb(table="orders", ...)` then `load__bronze(schema=..., destination="bronze.orders")`.
3. Give it its own watermark key in `config/watermark/` (see `watermark.example.yml`).
4. Deploy the flow (Prefect deployment + schedule).

## Local Development

- Copy `config/watermark/watermark.example.yml` → `config/watermark/watermark.yml` (gitignored, holds live watermark state).
- Populate `credential/` with real secrets (`app_secrets.yml`, `vnstock_token.json`) — gitignored, read via `utils/common/credential_handler.py`. Never commit this folder.
- Run `test/01_getting_started.py` to confirm the local Prefect environment (work pool, deployment) is wired up.

## Status

This document describes the target design. Aside from the sample flow in `test/`, the files above are currently scaffolded but empty — implementation is in progress. See the root README's [Project Status](../README.md#project-status) for the platform-wide checklist.
