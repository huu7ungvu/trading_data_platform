"""Generic CDC extractor for the simulated trading app DB (Postgres logical
replication via wal2json). Table-agnostic: publication/slot/table/destination
are all parameters, per the design principle in pipelines/README.md.

Requires (see simulated_app/generate_script.sql for the matching setup):
    CREATE PUBLICATION <publication> FOR TABLE <schema.table>;
    SELECT pg_create_logical_replication_slot('<slot>', 'wal2json');

Pattern: peek (non-destructive) -> caller durably writes the batch -> advance
the slot only once the write has succeeded. This is what makes the export
at-least-once instead of at-most-once: if the process dies between the write
and the advance, the next run re-peeks the same rows and re-writes them under
a new object key -- safe, since Landing is an immutable, replayable dump and
load__bronze is expected to dedupe (e.g. by lsn) when loading into Bronze.

NOTE: a replication slot only streams changes created *after* the slot
existed. The first run against a freshly-created slot should be preceded by
one full snapshot (SELECT * FROM <schema.table>) as a baseline -- this module
only covers the incremental/CDC side.

New dependencies this module needs (not yet in pyproject/.venv as of writing):
    uv pip install psycopg2-binary pyarrow minio
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from tempfile import NamedTemporaryFile

import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio


@dataclass
class CDCChange:
    lsn: str
    committed_at: str
    kind: str  # insert | update | delete
    schema: str
    table: str
    after: dict = field(default_factory=dict)      # new/current column values (empty for delete)
    before_keys: dict = field(default_factory=dict)  # replica-identity key values (update/delete only)


def _pg_connect(
    host: str = os.environ.get("POSTGRES_HOST", "localhost"),
    port: int = int(os.environ.get("POSTGRES_PORT", 5432)),
    dbname: str = os.environ.get("POSTGRES_DB", "simulated_app"),
    user: str = os.environ.get("POSTGRES_USER", "trading"),
    password: str = os.environ.get("POSTGRES_PASSWORD", "trading"),
):
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def peek_cdc_batch(slot_name: str, max_changes: int = 5000) -> list[CDCChange]:
    """Non-destructive read of up to `max_changes` pending wal2json records.
    Does NOT move the slot forward -- call advance_cdc_slot() after the batch
    has been durably written, not before.
    """
    changes: list[CDCChange] = []
    with _pg_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT lsn::text, data FROM pg_logical_slot_peek_changes(%s, NULL, %s, "
            "'include-timestamp', '1')",
            (slot_name, max_changes),
        )
        for lsn, data in cur.fetchall():
            payload = json.loads(data)
            committed_at = payload["timestamp"]
            for change in payload["change"]:
                after = dict(zip(change.get("columnnames", []), change.get("columnvalues", [])))
                before_keys = {}
                if "oldkeys" in change:
                    before_keys = dict(zip(change["oldkeys"]["keynames"], change["oldkeys"]["keyvalues"]))
                changes.append(CDCChange(
                    lsn=lsn,
                    committed_at=committed_at,
                    kind=change["kind"],
                    schema=change["schema"],
                    table=change["table"],
                    after=after,
                    before_keys=before_keys,
                ))
    return changes


def export_batch_to_minio(changes: list[CDCChange], bucket: str, prefix: str) -> str | None:
    """Write one batch as a single Parquet file to MinIO Landing.
    Returns the written object key, or None if `changes` was empty.

    NOTE: bucket must already exist -- minio/generate_scipt.bash (bucket
    creation) is still an empty stub as of writing, so `bucket` won't exist
    yet on a fresh MinIO unless created some other way first.
    """
    if not changes:
        return None

    table = pa.table({
        "lsn": [c.lsn for c in changes],
        "committed_at": [c.committed_at for c in changes],
        "op": [c.kind for c in changes],
        "schema_name": [c.schema for c in changes],
        "table_name": [c.table for c in changes],
        "after": [json.dumps(c.after) for c in changes],
        "before_keys": [json.dumps(c.before_keys) for c in changes],
    })

    last = changes[-1]
    ts_slug = last.committed_at.replace(" ", "T").replace(":", "-")
    lsn_slug = last.lsn.replace("/", "-")
    object_key = f"{prefix}/{ts_slug}_{lsn_slug}.parquet"

    client = Minio(
        os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
        secure=False,
    )
    with NamedTemporaryFile(suffix=".parquet") as tmp:
        pq.write_table(table, tmp.name)
        client.fput_object(bucket, object_key, tmp.name)

    return object_key


def advance_cdc_slot(slot_name: str, lsn: str) -> None:
    """Move the slot forward to `lsn`. Call ONLY after everything up to and
    including `lsn` has been durably written -- this ack is what the
    at-least-once guarantee depends on.
    """
    with _pg_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_replication_slot_advance(%s, %s::pg_lsn)", (slot_name, lsn))
        conn.commit()


def run_cdc_export(slot_name: str, bucket: str, prefix: str, max_changes: int = 5000) -> str | None:
    """One drain cycle: peek -> export -> advance. Meant to be called on a
    schedule (e.g. from orch__tdb__users.py as a Prefect task) rather than
    run as a long-lived streaming process.
    """
    changes = peek_cdc_batch(slot_name, max_changes=max_changes)
    if not changes:
        return None
    object_key = export_batch_to_minio(changes, bucket=bucket, prefix=prefix)
    advance_cdc_slot(slot_name, changes[-1].lsn)
    return object_key


if __name__ == "__main__":
    result = run_cdc_export(slot_name="cdc_users_slot", bucket="landing", prefix="tdb/users")
    print(f"Exported: {result}" if result else "Nothing to export.")
