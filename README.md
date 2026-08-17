# Trading Data Platform

A self-hosted, end-to-end **analytics data platform** built around a simulated stock/digital-asset trading app — designed and run the way an internal data platform team at a financial company would build one.

This is a personal side project. The goal is to practice building a production-style platform end-to-end: ingestion, medallion-layered storage, transformation, semantic modeling, and governance — not just a notebook pipeline.

## Table of Contents

- [Scenario](#scenario)
- [Architecture](#architecture)
- [Data Sources](#data-sources)
- [Tech Stack](#tech-stack)
- [Why This Stack](#why-this-stack)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Project Status](#project-status)
- [License](#license)

## Scenario

> A financial company runs a trading app for stocks and other digital assets. The internal data/analytics team needs a platform that turns raw app events and external market data into trustworthy, query-ready metrics — for BI dashboards, ad-hoc analysis, and (eventually) AI-assisted analytics — without depending on the app's production database.

This repo simulates that environment end-to-end: a fake trading app generates realistic order/execution/portfolio events, real Vietnamese market data comes in from a public API, and everything flows through a governed, layered data platform.

## Architecture

**Layer responsibilities**

| Layer | Storage | Purpose |
|---|---|---|
| **Landing** | MinIO (Parquet/ORC) | Immutable dump of every source payload, as received. Cheap object storage, full audit trail, replayable. |
| **Bronze** | ClickHouse | Raw data loaded and typed against a schema. Nothing is dropped or corrected yet. |
| **Silver** | ClickHouse | Cleaned, deduplicated, standardized (units, timestamps, enums, keys). |
| **Gold** | ClickHouse | Business-level data modeling — star/snowflake schemas, ready for joins and aggregation. |
| **Semantic** | Cube | Analytics-ready metrics and dimensions, decoupled from physical schema, served to every consumer through one API. |

**Cross-cutting layers**

- **Orchestration** — Prefect schedules and monitors every ingestion, load, and transformation flow.
- **Governance** *(AI-assisted)* — lineage, ownership, and SLAs (OpenMetadata); data quality via dbt tests and data contracts; documentation via a metrics catalog and lineage UI; change management via version control and CI/CD.

## Data Sources

| Source | What it provides | Notes |
|---|---|---|
| **Simulated Trading App** | User orders, executions, portfolio state | Custom-built app that emulates real trading activity for testing the platform without touching a real production system. |
| **vnstock API** | Vietnamese stock market data | Built on [`thinh-vu/vnstock`](https://github.com/thinh-vu/vnstock). |

## Tech Stack

| Concern | Tool | Role |
|---|---|---|
| Source database | **PostgreSQL** | Backing store for the simulated trading app; CDC source for `ingest__tdb` |
| Orchestration | **Prefect** | Schedules, runs, and monitors pipelines |
| Object storage | **MinIO** | S3-compatible landing zone |
| Transformation | **dbt** | SQL modeling, testing, versioning (Bronze → Silver → Gold) |
| Warehouse engine | **ClickHouse** | Columnar OLAP store for Bronze/Silver/Gold |
| Semantic layer | **Cube** | Metrics & dimensions API for all analytics consumers |
| Compute | **AWS EC2** | Self-hosted infrastructure |
| Monitoring | **Prometheus + Grafana** | Infra & pipeline observability |
| Alerting | **Telegram** | Real-time failure/ops notifications |
| Repo & CI/CD | **GitHub** | Source control and deployments |
| Governance | **OpenMetadata** | Lineage, ownership, catalog, quality |

## Why This Stack

An open-source, self-hosted stack (Prefect + MinIO + ClickHouse + dbt + Cube) was chosen for three reasons:

1. **Low cost, no vendor lock-in** — the entire platform runs on a single EC2 instance for roughly **$50/month**.
2. **Best-of-breed per task** — Prefect for orchestration, ClickHouse for analytics-speed queries, dbt for modeling *and* versioning, rather than one tool trying to do everything.
3. **The 5-layer architecture earns its keep at every stage** — Landing gives an audit trail and replayability, Bronze gives fast raw-data access, Silver gives consistency, Gold + Semantic give a single source of truth for metrics, and OpenMetadata ties governance across all of it.

This design comfortably handles the current ~1TB of data and is expected to scale to 10–100TB over the next 3–5 years without a redesign.

## Repository Structure

```
trading_data_platform/
├── docker-compose.yml      # Postgres, MinIO, ClickHouse + one-off init jobs (see Getting Started)
├── .env.example            # Template for .env (gitignored) — copy before first run
├── simulated_app/          # Postgres schema/seed + CDC-via-WAL setup (Dockerfile, generate_script.sql — see simulated_app/README.md)
├── minio/                  # generate_scipt.bash — creates Landing buckets
├── clickhouse/             # generate_scipt.bash — creates Bronze/Silver/Gold schemas
├── pipelines/              # Prefect project
│   ├── ingestion/          #   Pull raw data from sources → Landing
│   ├── loading/            #   Load Landing data → Bronze
│   ├── orchestration/      #   Prefect flow & deployment definitions
│   ├── config/             #   Per-source schemas and watermarks
│   ├── credential/         #   Local secrets (gitignored, not committed)
│   ├── credential_example/ #   Template showing the shape of credential/
│   └── utils/common/       #   Shared helpers (credentials, datetime, watermark loading)
└── transformations/        # dbt project — Silver & Gold modeling
```

## Getting Started

> ⚠️ The platform is under active construction — see [Project Status](#project-status) for what's wired up today.

**Prerequisites**: Docker, Python 3.12+, [`uv`](https://github.com/astral-sh/uv) (or `pip`), a Prefect account/server.

```bash
# 1. Clone and configure
git clone https://github.com/huu7ungvu/trading_data_platform.git
cd trading_data_platform
cp .env.example .env   # adjust credentials/ports if you need to

# 2. Bring up Postgres, MinIO, and ClickHouse
# (postgres builds from simulated_app/Dockerfile the first time — a plain
# postgres:16-alpine plus wal2json compiled in for CDC-via-WAL, see
# simulated_app/README.md; add --build to force a rebuild after changing it)
docker compose up -d

# 3. Seed / reset data — safe to run any time, as many times as you want
docker compose run --rm pg-init      # simulated trading app schema + seed data + CDC publication/slot
docker compose run --rm minio-init   # Landing buckets
docker compose run --rm ch-init      # Bronze/Silver/Gold schemas

# 4. Set up the Python/Prefect environment
uv venv && source .venv/bin/activate
uv pip install prefect  # dependency manifest not committed yet — see Project Status

# 5. Run a pipeline
cd pipelines
python test/01_getting_started.py   # sample Prefect flow to confirm the setup works
```

> The three `*-init` jobs above are one-off containers, not part of `docker compose up` — they only run when explicitly invoked, so re-seeding never requires wiping a volume. `simulated_app/generate_script.sql` is implemented (schema, seed data, CDC publication/slot — see [simulated_app/README.md](simulated_app/README.md)); `minio/generate_scipt.bash` and `clickhouse/generate_scipt.bash` are still empty stubs, so those two currently run and do nothing — implementation is in progress (see [Project Status](#project-status)).

Configuration lives in `.env` (infra credentials/ports — copy from `.env.example`), `pipelines/config/` (source schemas, watermarks), and `pipelines/credential/` (API tokens — copy from `pipelines/credential_example/`). None of these are committed — see `.gitignore`.

## Project Status

Built incrementally, layer by layer:

- [x] Repo scaffolding & environment setup
- [x] Prefect orchestration project bootstrapped (sample flow deploys locally)
- [x] Local infra composed — Postgres, MinIO, ClickHouse + one-off init jobs (`docker-compose.yml`)
- [ ] Simulated trading app generating order/execution/portfolio events
- [ ] Landing layer — ingestion into MinIO
- [ ] Bronze layer — load into ClickHouse
- [ ] Silver layer — dbt cleaning & standardization
- [ ] Gold layer — star/snowflake data modeling
- [ ] Semantic layer — Cube metrics & dimensions
- [ ] BI / embedded dashboard / AI-MCP consumption
- [ ] Monitoring — Prometheus + Grafana, Telegram alerts
- [ ] Governance — OpenMetadata lineage, dbt tests, data contracts
- [ ] CI/CD

## License

TBD.
