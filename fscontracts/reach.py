"""A deletion reach report over the synthetic store.

The store holds three retained training dataset versions, each with a
manifest, a relational aggregate that training reads consume, and three
model identifiers that consumed the dataset versions. The report for one
subject lists every artifact the subject's rows reached and labels each hop
with the kind of guarantee the store can give about removal from it.

The labels are the four the paper asks for.

    tracked      the path is in the tracked relational domain and the artifact
                 was recomputed without the subject and checked against the
                 retained one, see _verify_aggregate and _verify_dataset
    consumed     the artifact is known to have consumed a dataset version that
                 contains the subject, and nothing more is known
    recorded     a removal method is recorded for the artifact but has not
                 been executed or verified
    unknown      the store has no path and cannot say

Nothing here trains a model. Models are identifiers with manifests.
"""

from __future__ import annotations

import datetime as dt
import json

import duckdb
import pandas as pd

from . import reads


def build_store(con: duckdb.DuckDBPyConnection) -> dict:
    """Materialise dataset versions, the aggregate, and model manifests."""
    truth_sql = reads.sql_for("bitemporal")
    con.execute(f"CREATE OR REPLACE TABLE training_read AS {truth_sql}")
    ranges = {
        "v1": (dt.date(2024, 1, 1), dt.date(2024, 12, 31)),
        "v2": (dt.date(2024, 7, 1), dt.date(2025, 6, 30)),
        "v3": (dt.date(2024, 1, 1), dt.date(2025, 12, 31)),
    }
    snap = con.execute(
        "SELECT max(recorded_at) FROM capacity").fetchone()[0]
    manifests = {}
    for v, (lo, hi) in ranges.items():
        con.execute(f"""
            CREATE OR REPLACE TABLE dataset_{v} AS
            SELECT * FROM training_read
            WHERE order_date BETWEEN DATE '{lo}' AND DATE '{hi}'""")
        n = con.execute(f"SELECT count(*) FROM dataset_{v}").fetchone()[0]
        manifests[v] = {
            "definition_version": "feature_def_v1",
            "read_semantics": "bitemporal, knowledge cutoff = order_date",
            "date_range": [str(lo), str(hi)],
            "input_snapshot_recorded_at": str(snap),
            "rows": int(n),
        }
    con.execute("""
        CREATE OR REPLACE TABLE region_week_demand AS
        SELECT region_id, date_trunc('week', order_date) AS week, sum(units) AS units
        FROM orders GROUP BY 1, 2""")
    models = {
        "m1": {"consumed": "v1", "removal_method": None},
        "m2": {"consumed": "v2", "removal_method": None},
        "m3": {"consumed": "v3",
               "removal_method": "retrain from scratch on v3 re-materialised without the subject",
               "removal_status": "recorded, not executed"},
    }
    return {"manifests": manifests, "models": models}


def pick_subject(con: duckdb.DuckDBPyConnection) -> int:
    """A customer with orders in both years so every dataset version is reached."""
    row = con.execute("""
        SELECT customer_id FROM orders
        GROUP BY customer_id
        HAVING count(DISTINCT year(order_date)) = 2
        ORDER BY count(*) DESC, customer_id LIMIT 1""").fetchone()
    return int(row[0])


def _verify_aggregate(con: duckdb.DuckDBPyConnection, subject: int) -> dict:
    """Recompute the aggregate without the subject and check the difference.

    Every cell the subject touched must drop by exactly the subject's units,
    every other cell must be unchanged, and no cell may remain that only the
    subject contributed to.
    """
    con.execute(f"""
        CREATE OR REPLACE TABLE region_week_demand_minus AS
        SELECT region_id, date_trunc('week', order_date) AS week, sum(units) AS units
        FROM orders WHERE customer_id <> {subject} GROUP BY 1, 2""")
    diff = con.execute(f"""
        WITH s AS (
            SELECT region_id, date_trunc('week', order_date) AS week, sum(units) AS units
            FROM orders WHERE customer_id = {subject} GROUP BY 1, 2)
        SELECT
          count(*) FILTER (WHERE b.units - coalesce(a.units, 0) <> coalesce(s.units, 0)) AS wrong_cells,
          count(*) FILTER (WHERE s.units IS NOT NULL) AS touched_cells,
          count(*) FILTER (WHERE a.units IS NULL) AS removed_cells
        FROM region_week_demand b
        LEFT JOIN region_week_demand_minus a USING (region_id, week)
        LEFT JOIN s USING (region_id, week)""").fetchone()
    return {"wrong_cells": int(diff[0]), "touched_cells": int(diff[1]),
            "removed_cells": int(diff[2]), "verified": diff[0] == 0}


def _verify_dataset(con: duckdb.DuckDBPyConnection, v: str, lo: str, hi: str,
                    subject: int) -> dict:
    """Re-materialise a dataset version from the inputs without the subject.

    The result must contain no row of the subject and must be row for row
    identical to the retained version on every other row.
    """
    con.execute(f"""
        CREATE OR REPLACE TABLE dataset_{v}_minus AS
        SELECT * FROM training_read
        WHERE order_date BETWEEN DATE '{lo}' AND DATE '{hi}' AND customer_id <> {subject}""")
    subject_rows = con.execute(
        f"SELECT count(*) FROM dataset_{v}_minus WHERE customer_id = {subject}").fetchone()[0]
    changed = con.execute(f"""
        SELECT count(*) FROM (
          (SELECT * FROM dataset_{v} WHERE customer_id <> {subject} EXCEPT SELECT * FROM dataset_{v}_minus)
          UNION ALL
          (SELECT * FROM dataset_{v}_minus EXCEPT SELECT * FROM dataset_{v} WHERE customer_id <> {subject})
        )""").fetchone()[0]
    return {"subject_rows_after": int(subject_rows), "other_rows_changed": int(changed),
            "verified": subject_rows == 0 and changed == 0}


def reach_report(con: duckdb.DuckDBPyConnection, store: dict, subject: int) -> dict:
    rows = con.execute(
        "SELECT order_id FROM orders WHERE customer_id = ?", [subject]).df()
    cells = con.execute("""
        SELECT DISTINCT region_id, date_trunc('week', order_date) AS week
        FROM orders WHERE customer_id = ?""", [subject]).df()
    report = {
        "subject": subject,
        "hops": [],
    }
    report["hops"].append({
        "artifact": "orders",
        "reached": int(len(rows)),
        "unit": "rows",
        "guarantee": "tracked",
        "note": "base rows, deleted directly",
    })
    agg = _verify_aggregate(con, subject)
    report["hops"].append({
        "artifact": "region_week_demand",
        "reached": int(len(cells)),
        "unit": "aggregate cells",
        "guarantee": "tracked" if agg["verified"] else "unknown",
        "note": ("relational aggregate, recomputed without the subject and checked cell by cell"
                 if agg["verified"] else "recomputation check failed"),
        "check": agg,
    })
    for v, m in store["manifests"].items():
        n = con.execute(
            f"SELECT count(*) FROM dataset_{v} WHERE customer_id = ?", [subject]).fetchone()[0]
        if n:
            lo, hi = m["date_range"]
            chk = _verify_dataset(con, v, lo, hi, subject)
            report["hops"].append({
                "artifact": f"dataset {v}",
                "reached": int(n),
                "unit": "rows",
                "guarantee": "tracked" if chk["verified"] else "unknown",
                "note": ("manifest retained, re-materialised from inputs without the subject "
                         "and checked row by row" if chk["verified"] else "re-materialisation check failed"),
                "check": chk,
            })
    for mid, m in store["models"].items():
        v = m["consumed"]
        n = con.execute(
            f"SELECT count(*) FROM dataset_{v} WHERE customer_id = ?", [subject]).fetchone()[0]
        if not n:
            continue
        if m["removal_method"]:
            g, note = "recorded", f"{m['removal_method']} ({m['removal_status']})"
        else:
            g, note = "consumed", "model consumed the dataset version, influence on predictions unknown"
        report["hops"].append({
            "artifact": f"model {mid}",
            "reached": 1,
            "unit": "model",
            "guarantee": g,
            "note": note,
        })
    # A standing line. The store cannot count reads that bypassed the
    # admission point, so the report says so on every subject rather than
    # implying the list above is complete.
    report["hops"].append({
        "artifact": "exports outside the boundary",
        "reached": None,
        "unit": None,
        "guarantee": "unknown",
        "note": "standing line, the store holds no manifest for reads that bypassed the admission point",
    })
    return report


def render_markdown(report: dict) -> str:
    lines = [f"# Reach report for subject {report['subject']}", "",
             "| Artifact | Reached | Guarantee | Note |", "|---|---|---|---|"]
    for h in report["hops"]:
        reached = "" if h["reached"] is None else f"{h['reached']} {h['unit']}"
        lines.append(f"| {h['artifact']} | {reached} | {h['guarantee']} | {h['note']} |")
    return "\n".join(lines) + "\n"


def dump(report: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
