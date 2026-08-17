# Postgres 16 (Alpine) + wal2json, compiled from source against the matching
# postgresql16-dev headers so there's no ABI mismatch between the module and
# the server (Alpine's own wal2json apk package only exists in the edge/testing
# repo, not in the stable repo this base image tracks -- building from source
# against postgresql16-dev is the reliable path on Alpine).
#
# Used for CDC-via-WAL: wal2json is a logical-decoding output plugin, it turns
# each committed transaction on a replicated table into one JSON object
# instead of the binary pgoutput wire format, so a plain psycopg2 connection
# (via pg_logical_slot_peek_changes / pg_logical_slot_get_changes) can read
# it without any streaming-replication client or Debezium/Kafka.
FROM postgres:16-alpine AS builder

RUN apk add --no-cache build-base postgresql16-dev git

# with_llvm=no: skip building the optional LLVM-JIT bitcode object, which
# needs a clang version matching this Postgres build's `pg_config
# --configure` output (not installed by postgresql16-dev) and isn't needed
# for logical decoding.
RUN git clone --depth 1 --branch wal2json_2_6 https://github.com/eulerto/wal2json.git /tmp/wal2json \
 && make -C /tmp/wal2json USE_PGXS=1 with_llvm=no \
 && make -C /tmp/wal2json USE_PGXS=1 with_llvm=no install

FROM postgres:16-alpine
COPY --from=builder /usr/local/lib/postgresql/wal2json.so /usr/local/lib/postgresql/wal2json.so
