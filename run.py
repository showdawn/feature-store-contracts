"""Run every experiment in the paper and write results/.

    python run.py            full run, under a minute on one machine
    python run.py --quick    smaller order counts, for a smoke test

Outputs, all under results/:

    main_reads.csv       Table 2 of the paper, three read semantics on the main store
    sweep_late.csv       leakage as the late arrival share grows
    sweep_correction.csv leakage as the correction share grows
    fig_leakage.pdf      Figure 2 of the paper
    admission.csv        Table 3 of the paper, seven job variants
    cost.csv             storage and query time, bitemporal against current
    reach_report.md      the worked deletion reach report
    reach_report.json
    summary.md           every number quoted in the paper, in one place
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import statistics
import time

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from fscontracts import admission, generate, reach, reads

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")


def load(con: duckdb.DuckDBPyConnection, tables: dict[str, pd.DataFrame]) -> None:
    for name, df in tables.items():
        con.register(f"_{name}", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _{name}")
        con.unregister(f"_{name}")


def three_reads(con: duckdb.DuckDBPyConnection, facilities: pd.DataFrame) -> pd.DataFrame:
    truth = reads.run_read(con, reads.sql_for("bitemporal"))
    out = []
    for sem in ("current", "valid", "bitemporal"):
        r = reads.run_read(con, reads.sql_for(sem))
        m = reads.compare(r, truth, facilities)
        m["semantics"] = sem
        out.append(m)
    return pd.DataFrame(out)[["semantics", "rows", "leakage_rate", "facility_mismatch_rate",
                              "impossible_rate", "mean_abs_rel_error", "missing_rate"]]


def sweep(param: str, values: list[float], base: generate.Params) -> pd.DataFrame:
    frames = []
    for v in values:
        p = dataclasses.replace(base, **{param: v})
        t = generate.generate(p)
        con = duckdb.connect()
        load(con, t)
        df = three_reads(con, t["facilities"])
        df[param] = v
        frames.append(df)
        con.close()
    return pd.concat(frames, ignore_index=True)


def figure(sw_late: pd.DataFrame, sw_corr: pd.DataFrame, path: str) -> None:
    """Single column figure. The current value read sits at 92 to 96 percent on
    every point and is reported as a band in the text of the panel so the
    valid time and bitemporal lines stay readable."""
    fig, axes = plt.subplots(1, 2, figsize=(3.4, 1.9), sharey=True)
    labels = {"valid": "valid time only", "bitemporal": "bitemporal"}
    styles = {"valid": dict(marker="o", ls="--", color="#1f5fa8", ms=3.5, lw=1.1),
              "bitemporal": dict(marker="^", ls="-", color="#0a7a3a", ms=3.5, lw=1.1)}
    for ax, sw, param, xlabel in (
        (axes[0], sw_late, "late_arrival_share", "rows recorded 7 to 60 days late (%)"),
        (axes[1], sw_corr, "correction_share", "rows later corrected (%)"),
    ):
        cur = sw[sw.semantics == "current"]["leakage_rate"] * 100
        for sem in ("valid", "bitemporal"):
            d = sw[sw.semantics == sem]
            ax.plot(d[param] * 100, d["leakage_rate"] * 100, label=labels[sem], **styles[sem])
        import math
        ax.text(0.03, 0.95, f"current value: {math.floor(cur.min())} to {math.ceil(cur.max())}%",
                transform=ax.transAxes, fontsize=6, va="top", color="#555555")
        ax.set_xlabel(xlabel, fontsize=7)
        ax.tick_params(labelsize=6.5)
        ax.set_ylim(-1, 30)
        ax.grid(True, lw=0.3, alpha=0.5)
    axes[0].set_ylabel("leaked training rows (%)", fontsize=7)
    axes[1].legend(fontsize=6, frameon=False, loc="lower right")
    fig.tight_layout(pad=0.3)
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def admission_table(con: duckdb.DuckDBPyConnection, facilities: pd.DataFrame) -> pd.DataFrame:
    truth = reads.run_read(con, reads.sql_for("bitemporal"))
    rows = []
    for job in admission.variants():
        decision, reason = admission.admission_check(job)
        r = reads.run_read(con, job.sql)
        m = reads.compare(r, truth, facilities)
        rows.append({
            "variant": job.name,
            "description": job.description,
            "interpretation_declared": job.interpretation,
            "admission": decision,
            "reason": reason,
            "interpretation_matches_question": job.interpretation == "as_known",
            "leakage_rate_if_run": m["leakage_rate"],
            "impossible_rate_if_run": m["impossible_rate"],
        })
    return pd.DataFrame(rows)


def cost(con: duckdb.DuckDBPyConnection, workdir: str) -> pd.DataFrame:
    # Storage. The bitemporal history against a current snapshot of each dimension.
    con.execute("""
        CREATE OR REPLACE TABLE capacity_current AS
        SELECT facility_id, capacity FROM (
          SELECT *, row_number() OVER (PARTITION BY facility_id
                    ORDER BY valid_from DESC, recorded_at DESC) rn FROM capacity) WHERE rn = 1""")
    con.execute("""
        CREATE OR REPLACE TABLE assignment_current AS
        SELECT region_id, facility_id FROM (
          SELECT *, row_number() OVER (PARTITION BY region_id
                    ORDER BY valid_from DESC, recorded_at DESC) rn FROM assignment) WHERE rn = 1""")
    sizes = {}
    for t in ("capacity", "capacity_current", "assignment", "assignment_current", "orders"):
        path = os.path.join(workdir, f"{t}.parquet")
        con.execute(f"COPY {t} TO '{path}' (FORMAT PARQUET)")
        sizes[t] = {"rows": con.execute(f"SELECT count(*) FROM {t}").fetchone()[0],
                    "parquet_bytes": os.path.getsize(path)}
    # Query time. Median of five runs each, on the same connection. The
    # "current snapshot" read is the operational join an engineer would write
    # against the snapshot tables above. The three history reads all rank the
    # full history, and "current" among them is the same query with no
    # temporal predicate, which is not how a current value join is written in
    # practice and is kept only for completeness.
    snapshot_sql = """
        SELECT o.order_id, o.order_date, o.region_id, o.customer_id, o.units,
               a.facility_id, c.capacity
        FROM orders o
        LEFT JOIN assignment_current a USING (region_id)
        LEFT JOIN capacity_current c USING (facility_id)
        ORDER BY o.order_id"""
    queries = {"current snapshot join": snapshot_sql}
    for sem in ("current", "valid", "bitemporal"):
        queries[f"{sem} history read"] = reads.sql_for(sem)
    times = {}
    for name, sql in queries.items():
        samples = []
        for _ in range(5):
            t0 = time.perf_counter()
            con.execute(sql).fetchall()
            samples.append(time.perf_counter() - t0)
        times[name] = statistics.median(samples)
    rows = [{"item": f"{t} table", "rows": v["rows"], "parquet_bytes": v["parquet_bytes"],
             "median_query_seconds": None} for t, v in sizes.items()]
    rows += [{"item": name, "rows": None, "parquet_bytes": None,
              "median_query_seconds": round(sec, 4)} for name, sec in times.items()]
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    base = generate.Params()
    if args.quick:
        base = dataclasses.replace(base, n_orders=20_000)
    sweep_base = dataclasses.replace(base, n_orders=20_000 if args.quick else 100_000)

    # 1. Main store and the three reads.
    t = generate.generate(base)
    con = duckdb.connect()
    load(con, t)
    main_reads = three_reads(con, t["facilities"])
    main_reads.to_csv(os.path.join(OUT, "main_reads.csv"), index=False)

    # 1b. Control. With neither late arrivals nor corrections the valid time
    # read and the bitemporal read must coincide.
    ctrl_p = dataclasses.replace(sweep_base, late_arrival_share=0.0, short_lag_share=0.0,
                                 correction_share=0.0)
    ctrl_t = generate.generate(ctrl_p)
    ctrl_con = duckdb.connect()
    load(ctrl_con, ctrl_t)
    control = three_reads(ctrl_con, ctrl_t["facilities"])
    control.to_csv(os.path.join(OUT, "control_no_lag_no_correction.csv"), index=False)
    ctrl_con.close()

    # 2. Sweeps and the figure.
    sw_late = sweep("late_arrival_share", [0.0, 0.05, 0.10, 0.20, 0.30], sweep_base)
    sw_corr = sweep("correction_share", [0.0, 0.05, 0.15, 0.30, 0.50], sweep_base)
    sw_late.to_csv(os.path.join(OUT, "sweep_late.csv"), index=False)
    sw_corr.to_csv(os.path.join(OUT, "sweep_correction.csv"), index=False)
    figure(sw_late, sw_corr, os.path.join(OUT, "fig_leakage.pdf"))

    # 3. Admission check over the seven variants.
    adm = admission_table(con, t["facilities"])
    adm.to_csv(os.path.join(OUT, "admission.csv"), index=False)

    # 4. Cost.
    c = cost(con, OUT)
    c.to_csv(os.path.join(OUT, "cost.csv"), index=False)

    # 5. Reach report.
    store = reach.build_store(con)
    subject = reach.pick_subject(con)
    rep = reach.reach_report(con, store, subject)
    with open(os.path.join(OUT, "reach_report.md"), "w") as f:
        f.write(reach.render_markdown(rep))
    reach.dump({"store": store, "report": rep}, os.path.join(OUT, "reach_report.json"))

    # 6. Summary.
    dim_rows = {k: len(v) for k, v in t.items()}
    with open(os.path.join(OUT, "summary.md"), "w") as f:
        f.write("# Results summary\n\n")
        f.write(f"Parameters: {json.dumps(dataclasses.asdict(base), default=str)}\n\n")
        f.write(f"Table sizes: {dim_rows}\n\n")
        f.write("## Three reads on the main store\n\n")
        f.write(main_reads.to_markdown(index=False) + "\n\n")
        f.write("## Control, no late arrivals and no corrections\n\n" + control.to_markdown(index=False) + "\n\n")
        f.write("## Sweep, late arrival share\n\n" + sw_late.to_markdown(index=False) + "\n\n")
        f.write("## Sweep, correction share\n\n" + sw_corr.to_markdown(index=False) + "\n\n")
        f.write("## Admission check\n\n" + adm.to_markdown(index=False) + "\n\n")
        f.write("## Cost\n\n" + c.to_markdown(index=False) + "\n\n")
        f.write("## Reach report\n\n" + reach.render_markdown(rep) + "\n")
    con.close()
    print(open(os.path.join(OUT, "summary.md")).read())


if __name__ == "__main__":
    main()
