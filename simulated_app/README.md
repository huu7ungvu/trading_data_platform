# simulated_app

Postgres backing store for the simulated trading app, plus its CDC-via-WAL
setup (no Debezium/Kafka -- see [docs.md](docs.md) for how it works).

## Contents

| File | Role |
|---|---|
| `Dockerfile` | `postgres:16-alpine` + `wal2json` compiled from source (logical-decoding output plugin) |
| `generate_script.sql` | Schema (`test.users`), seed data, and CDC provisioning (publication + replication slot) -- run by the `pg-init` job |

## Quick start

```bash
docker compose up -d postgres     # builds the wal2json-enabled image (docker-compose.yml's `build:` on
                                   # the postgres service triggers this automatically -- add --build to
                                   # force a rebuild after changing Dockerfile/generate_script.sql)
docker compose run --rm pg-init   # applies generate_script.sql: schema + seed + CDC publication/slot
                                   # (waits for postgres to be healthy on its own, no manual wait needed)
```

No wrapper script needed -- `postgres` already builds from `Dockerfile` because `docker-compose.yml`
declares `build: context: ./simulated_app` on that service; a plain `docker compose up -d` (bringing up the
whole stack) builds it the same way.

## What gets created

- `test.users` -- table described in the root schema discussion (see the
  file itself for full column list), with 10 seed rows.
- `cdc_users_pub` -- a `PUBLICATION` on `test.users`.
- `cdc_users_slot` -- a logical replication slot using the `wal2json` plugin.

Check status any time:

```bash
docker compose exec postgres psql -U trading -d simulated_app -c \
  "SELECT slot_name, plugin, active, confirmed_flush_lsn FROM pg_replication_slots;"
```

## Resetting

- **Re-seed only** (keep the running container): `docker compose run --rm pg-init` again -- and again, and
  again. Every statement in `generate_script.sql` is guarded (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO
  NOTHING` on the seed insert, existence checks around the publication/slot), so re-running never errors and
  never duplicates rows. If you actually want different/fresh seed rows, truncate first:
  `docker compose exec postgres psql -U trading -d simulated_app -c "TRUNCATE test.users;"`.
- **Full reset** (wipe all Postgres data, including the CDC slot): `docker compose down -v postgres` (or
  `docker compose down -v` for the whole stack), then the two commands from **Quick start** again.

## Consuming the CDC stream

See [`pipelines/ingestion/ingest__tdb.py`](../pipelines/ingestion/ingest__tdb.py) -- `peek_cdc_batch()` /
`export_batch_to_minio()` / `advance_cdc_slot()`. Read [docs.md](docs.md) first if you're touching that file;
the peek-then-advance ordering is the part most likely to bite you if changed carelessly.
