"""Training reads over the synthetic store, in DuckDB SQL.

Each read produces one row per order with the facility the order is attributed
to and that facility's capacity. The three semantics differ only in the
temporal predicates on the two dimension joins.

    current      no temporal predicate. The latest row per key, as an
                 operational dimension table looks on the day the job runs.
    valid        valid_from <= order_date. Uses everything the store knows
                 today about the past, including late arrivals and corrections
                 that were not known on the order date.
    bitemporal   valid_from <= order_date AND recorded_at <= order_date.
                 What was knowable on the order date. This is the ground
                 truth for a read whose declared interpretation is
                 "reconstruct the information available at the decision".

`valid` is also the correct read for the other declared interpretation,
"train on corrected history". The two interpretations are both legitimate and
give different rows, which is why the paper asks for the interpretation to be
declared rather than inferred.
"""

from __future__ import annotations

import duckdb
import pandas as pd


def _assignment_cte(valid_pred: str, know_pred: str) -> str:
    return f"""
    asg_ranked AS (
        SELECT o.order_id, a.facility_id,
               row_number() OVER (PARTITION BY o.order_id
                                  ORDER BY a.valid_from DESC, a.recorded_at DESC) AS rn
        FROM orders o
        JOIN assignment a ON a.region_id = o.region_id {valid_pred} {know_pred}
    ),
    asg AS (SELECT order_id, facility_id FROM asg_ranked WHERE rn = 1)
    """


def _capacity_cte(valid_pred: str, know_pred: str) -> str:
    return f"""
    cap_ranked AS (
        SELECT o.order_id, c.capacity,
               row_number() OVER (PARTITION BY o.order_id
                                  ORDER BY c.valid_from DESC, c.recorded_at DESC) AS rn
        FROM orders o
        JOIN asg USING (order_id)
        JOIN capacity c ON c.facility_id = asg.facility_id {valid_pred} {know_pred}
    ),
    cap AS (SELECT order_id, capacity FROM cap_ranked WHERE rn = 1)
    """


_FINAL = """
    SELECT o.order_id, o.order_date, o.region_id, o.customer_id, o.units,
           asg.facility_id, cap.capacity
    FROM orders o
    LEFT JOIN asg USING (order_id)
    LEFT JOIN cap USING (order_id)
    ORDER BY o.order_id
"""


def sql_for(semantics: str, *, valid_op: str = "<=",
            assignment_semantics: str | None = None) -> str:
    """Build the read SQL.

    semantics             'current', 'valid' or 'bitemporal' for the capacity join
    valid_op              comparison operator on valid_from, '<=' is correct,
                          '<' is the boundary bug used by one job variant
    assignment_semantics  override for the assignment join, defaults to the
                          same semantics as the capacity join
    """
    a_sem = assignment_semantics or semantics

    def preds(sem: str, alias: str) -> tuple[str, str]:
        if sem == "current":
            return "", ""
        v = f"AND {alias}.valid_from {valid_op} o.order_date"
        if sem == "valid":
            return v, ""
        if sem == "bitemporal":
            return v, f"AND {alias}.recorded_at <= o.order_date"
        raise ValueError(sem)

    av, ak = preds(a_sem, "a")
    cv, ck = preds(semantics, "c")
    return "WITH " + _assignment_cte(av, ak) + ", " + _capacity_cte(cv, ck) + _FINAL


def run_read(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def compare(read: pd.DataFrame, truth: pd.DataFrame,
            facilities: pd.DataFrame) -> dict[str, float]:
    """Leakage and impossibility rates of one read against the ground truth."""
    m = read.merge(truth[["order_id", "facility_id", "capacity"]],
                   on="order_id", suffixes=("", "_truth"))
    m = m.merge(facilities, on="facility_id", how="left")
    diff_fac = m["facility_id"] != m["facility_id_truth"]
    diff_cap = m["capacity"].fillna(-1) != m["capacity_truth"].fillna(-1)
    leaked = diff_fac | diff_cap
    impossible = pd.to_datetime(m["open_date"]) > pd.to_datetime(m["order_date"])
    rel = ((m["capacity"] - m["capacity_truth"]).abs() / m["capacity_truth"]).fillna(0)
    return {
        "rows": int(len(m)),
        "leakage_rate": float(leaked.mean()),
        "facility_mismatch_rate": float(diff_fac.mean()),
        "impossible_rate": float(impossible.mean()),
        "mean_abs_rel_error": float(rel.mean()),
        "missing_rate": float(m["capacity"].isna().mean()),
    }
