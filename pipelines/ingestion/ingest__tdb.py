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

from io import BytesIO
import json
import os
from dataclasses import dataclass, field
from tempfile import NamedTemporaryFile
from turtle import pd

import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq
from ruamel.yaml import BytesIO
from minio import Minio
from psycopg2 import sql
import pandas as pd


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
    port: int = int(os.environ.get("POSTGRES_PORT", 5433)),
    dbname: str = os.environ.get("POSTGRES_DB", "simulated_app"),
    user: str = os.environ.get("POSTGRES_USER", "trading"),
    password: str = os.environ.get("POSTGRES_PASSWORD", "trading"),
):
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)

def _minio_connect(
    endpoint: str = os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
    access_key: str = os.environ.get("MINIO_ROOT_USER", "minioadmin"),
    secret_key: str = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
):
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)


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

    client = _minio_connect()
    tmp = NamedTemporaryFile(suffix=".parquet", delete=False)
    tmp.close()  # Bắt buộc đóng trên Windows trước khi pyarrow có thể ghi vào
    try:
        pq.write_table(table, tmp.name)
        client.fput_object(bucket, object_key, tmp.name)
    finally:
        os.unlink(tmp.name)

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

def create_bucket(client, bucket):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        print(f"Bucket '{bucket}' created.")
    else:
        print(f"Bucket '{bucket}' already exists.")

def get_min_max_ids(conn, schema_name, table_name):
    cursor = conn.cursor()
    query = sql.SQL("SELECT MIN(id), MAX(id) FROM {}.{};").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name)
    )
    cursor.execute(query)
    min_id, max_id = cursor.fetchone()
    cursor.close()
    return min_id, max_id

def read_data_from_postgres(conn, current_id, next_id, column_names, schema_name, table_name):
    cursor = conn.cursor()
    query = sql.SQL("SELECT * FROM {}.{} where id >= %s AND id <= %s;").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name)
    )
    cursor.execute(query, (current_id, next_id))
    data = cursor.fetchall()
    if len(column_names) == 0:
        column_names.extend([desc[0] for desc in cursor.description])
    cursor.close()
    return data

def convert(data, column_names):
    buffer = BytesIO()
    # Convert the data to a pandas DataFrame
    df = pd.DataFrame(data, columns=column_names)
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    print(df)
    return buffer

def put_data_to_minio(client, buffer, file_name, bucket):
    client.put_object(
        bucket,
        file_name,
        buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream"
    )
    print("Data uploaded to MinIO successfully.")
    
def back_fill_data(bucket: str, prefix: str, schema_name: str, table_name: str,max_changes: int = 1000) -> None:
    """Backfill all pending changes in the slot until there are no more.
    This is useful for catching up after a long downtime or for initial
    backfill after creating a new slot.
    """
    client = _minio_connect()
    conn = _pg_connect()
    create_bucket(client, bucket)
    part_number = 1
    column_names = []
    current_id, max_id = get_min_max_ids(conn, schema_name, table_name)
    while current_id <= max_id:
        next_id = current_id + max_changes
        data = read_data_from_postgres(conn, current_id, next_id, column_names, schema_name, table_name)
        if data:
            buffer = convert(data, column_names)
            file_name = f"{prefix}/{table_name}_backfill_part_{part_number}.parquet"
            put_data_to_minio(client, buffer, file_name, bucket)
            part_number += 1
        current_id = next_id + 1
    conn.close()
