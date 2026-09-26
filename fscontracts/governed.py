"""Closed capacity operator for this prototype's materialized DuckDB tables.

The public API accepts a declared interpretation, not SQL or join overrides.
It builds both joins with inclusive valid-time boundaries. `as_known` also
bounds both recorded_at fields by each order_date; `corrected` uses all rows
in the input snapshot and ranks their recorded_at values. Both are legitimate
choices. No business-purpose policy is inferred.

This is an execution boundary within a trusted Python process, not a security
boundary. Direct SQL, altered code, hostile connection/catalog changes, and
consumers outside this API are not controlled. Receipts are unsigned evidence
of the invocation, not attestation or durable lineage registration.
"""

from __future__ import annotations

import hashlib
import json

import duckdb
import pandas as pd

from . import reads


_INTEGERS = {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
             "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT"}
_TIMES = {"DATE", "TIMESTAMP", "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP_NS"}
_REQUIRED = {
    "orders": {"order_id": "integer", "order_date": "time", "region_id": "integer",
               "customer_id": "integer", "units": "numeric"},
    "assignment": {"region_id": "integer", "facility_id": "integer",
                   "valid_from": "time", "recorded_at": "time"},
    "capacity": {"facility_id": "integer", "capacity": "numeric",
                 "valid_from": "time", "recorded_at": "time"},
}
_KEYS = {"orders": ("order_id",),
         "assignment": ("region_id", "valid_from", "recorded_at"),
         "capacity": ("facility_id", "valid_from", "recorded_at")}


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _numeric(kind: str) -> bool:
    return kind in _INTEGERS or kind in ("FLOAT", "DOUBLE") or kind.startswith("DECIMAL(")


def _source(con: duckdb.DuckDBPyConnection, name: str) -> dict:
    # Reject views (possibly volatile) and ambiguous same-name relations.
    relations = con.execute("""SELECT table_catalog, table_schema, table_name, table_type
                               FROM information_schema.tables WHERE table_name = ?""",
                            [name]).fetchall()
    if len(relations) != 1 or relations[0][3] not in ("BASE TABLE", "LOCAL TEMPORARY"):
        raise ValueError(f"{name} must name exactly one materialized table")
    relation = relations[0]
    qualified = ".".join(_quote(part) for part in relation[:3])
    schema = sorted((row[0], row[1]) for row in con.execute(f"DESCRIBE {qualified}").fetchall())
    types = dict(schema)
    for column, expected in _REQUIRED[name].items():
        kind = types.get(column)
        valid = ((expected == "integer" and kind in _INTEGERS)
                 or (expected == "time" and kind in _TIMES)
                 or (expected == "numeric" and kind is not None and _numeric(kind)))
        if not valid:
            raise ValueError(f"{name}.{column} requires {expected} type; found {kind or 'missing'}")
    # Scalar cast-to-text encodings below are reproducible for these types.
    for column, kind in schema:
        if not (_numeric(kind) or kind in _TIMES or kind in ("BOOLEAN", "VARCHAR", "BLOB")):
            raise ValueError(f"{name}.{column} has unsupported fingerprint type {kind}")
    nulls = " OR ".join(f"{_quote(c)} IS NULL" for c in _REQUIRED[name])
    if con.execute(f"SELECT EXISTS(SELECT 1 FROM {qualified} WHERE {nulls})").fetchone()[0]:
        raise ValueError(f"{name} contains NULL required values")
    keys = ", ".join(_quote(c) for c in _KEYS[name])
    if con.execute(f"SELECT EXISTS(SELECT 1 FROM {qualified} GROUP BY {keys} HAVING count(*) > 1)").fetchone()[0]:
        raise ValueError(f"{name} contains duplicate ranking keys")

    # Include every column and every row, retaining duplicate multiplicities.
    # Typed schema disambiguates values; SQL NULL remains JSON null, not text.
    # DuckDB casts avoid Python datetime's loss of nanosecond precision.
    columns = ", ".join(f"CAST({_quote(column)} AS VARCHAR)" for column, _ in schema)
    rows = con.execute(f"SELECT {columns} FROM {qualified}").fetchall()
    canonical = sorted(_json(row) for row in rows)
    digest = hashlib.sha256((_json(schema) + "\n").encode("utf-8"))
    for row in canonical:
        digest.update((row + "\n").encode("utf-8"))
    return {"source_id": qualified, "schema": [list(item) for item in schema],
            "row_count": len(rows), "sha256": digest.hexdigest()}


def execute_contract(con: duckdb.DuckDBPyConnection, interpretation: str = "as_known",
                     feature_version: str = "capacity_v1", backend: str = "duckdb",
                     cutoff: str = "order_date") -> tuple[pd.DataFrame, dict]:
    """Validate, execute the built-in feature, and return its JSON-ready receipt.

    Requires exclusive use of a trusted DuckDB connection without an active
    transaction and unambiguous materialized orders/assignment/capacity tables. Required values
    cannot be NULL; order IDs and dimension (key, valid_from, recorded_at) tuples
    must be unique so row ranking is defined. Missing historical matches in the
    result remain NULL. A single transaction binds fingerprints and execution.
    Unsupported choices/schema raise ValueError; unrecognized kwargs raise
    TypeError. Time columns are timezone-naive DuckDB dates/timestamps.
    """
    for name, value, allowed in (
        ("interpretation", interpretation, ("as_known", "corrected")),
        ("feature_version", feature_version, ("capacity_v1",)),
        ("backend", backend, ("duckdb",)),
        ("cutoff", cutoff, ("order_date",)),
    ):
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"unsupported {name}: {value!r}; supported: {allowed}")
    if not isinstance(con, duckdb.DuckDBPyConnection):
        raise ValueError("backend duckdb requires a DuckDBPyConnection")

    semantics = "bitemporal" if interpretation == "as_known" else "valid"
    sql = reads.sql_for(semantics, valid_op="<=")
    # BEGIN inside an existing DuckDB transaction aborts it. Two read-only
    # probes use distinct auto-commit transactions, or the same explicit one.
    # As with the rest of this API, the connection must not be used concurrently.
    first_tx = con.execute("SELECT current_transaction_id()").fetchone()[0]
    second_tx = con.execute("SELECT current_transaction_id()").fetchone()[0]
    if first_tx == second_tx:
        raise ValueError("execute_contract requires a connection without an active transaction")
    con.execute("BEGIN TRANSACTION")
    try:
        sources = {name: _source(con, name) for name in _REQUIRED}
        result = reads.run_read(con, sql)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    receipt = {
        "contract_id": "capacity", "contract_version": feature_version,
        "interpretation": interpretation, "backend": backend,
        "backend_version": duckdb.__version__, "cutoff": cutoff,
        "valid_comparator": "<=",
        "knowledge_cutoff": ("order_date" if interpretation == "as_known"
                             else "all_recorded_rows_in_input_snapshot"),
        "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        "sources": sources, "result_rows": len(result),
        "fingerprint_encoding": "sha256(schema_json + newline + sorted row_json lines); all scalar values cast to DuckDB VARCHAR; NULL is JSON null",
        "scope": "built-in capacity_v1; both joins generated; materialized source tables; one DuckDB transaction",
        "limitations": ["unsigned receipt in a trusted Python process",
                        "business-purpose interpretation is chosen by caller",
                        "direct SQL, modified code, external consumers and deletion actions are outside this boundary"],
    }
    return result, receipt
