"""Run every experiment in the paper and write results/.

    python run.py            full run: 300k main; five seeds x 100k per sweep point
    python run.py --quick    20k orders, isolated in results/quick
    python run.py --output PATH  explicitly select a destination

Outputs, all under results/:

    main_reads.csv       Table 2 of the paper, three read semantics on the main store
    sweep_late.csv       mean/min/max disagreement across seeds, late-arrival sweep
    sweep_correction.csv mean/min/max disagreement across seeds, correction sweep
    *_per_seed.csv       raw observations underlying each sweep summary
    fig_disagreement.pdf Figure 2 of the paper (also PNG)
    admission.csv        Table 3 of the paper, seven job variants
    cost.csv             storage and query time, bitemporal against current
    query_timings.csv    individual timed executions, including result fetch
    governed_comparison.csv analogous requests to the closed contract API
    execution_receipts.json receipts for the executed contracts
    environment.json     nonidentifying runtime, hardware and timing metadata
    reach_report.md      the worked deletion reach report
    reach_report.json
    summary.md           every number quoted in the paper, in one place
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import statistics
import subprocess
import time
from importlib import metadata

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from fscontracts import admission, generate, reach, reads

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
SEEDS = (7, 11, 19, 23, 31)


def output_directory(quick: bool, explicit: str | None = None) -> str:
    """Keep smoke-test output out of the paper's default result directory."""
    return os.path.abspath(explicit) if explicit else os.path.join(OUT, "quick") if quick else OUT


def load(con: duckdb.DuckDBPyConnection, tables: dict[str, pd.DataFrame]) -> None:
    for name, df in tables.items():
        con.register(f"_{name}", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _{name}")
        con.unregister(f"_{name}")


def three_reads(con: duckdb.DuckDBPyConnection, facilities: pd.DataFrame) -> pd.DataFrame:
    truth = reads.run_read(con, reads.sql_for("bitemporal"))
    out = []
    for sem in ("current", "valid", "bitemporal"):
        r = truth if sem == "bitemporal" else reads.run_read(con, reads.sql_for(sem))
        m = reads.compare(r, truth, facilities)
        m["semantics"] = sem
        out.append(m)
    return pd.DataFrame(out)[["semantics", "rows", "disagreement_rate", "facility_mismatch_rate",
                              "impossible_rate", "missing_rate"]]


def sweep(param: str, values: list[float], base: generate.Params,
          seeds: tuple[int, ...] = SEEDS, threads: int = 4) -> pd.DataFrame:
    """Paired parameter overlays on each seed's unchanged base world."""
    frames = []
    for seed in seeds:
        for v in values:
            p = dataclasses.replace(base, seed=seed, **{param: v})
            t = generate.generate(p)
            with duckdb.connect(config={"threads": threads}) as con:
                load(con, t)
                df = three_reads(con, t["facilities"])
            df[param] = v
            df["seed"] = seed
            frames.append(df)
    return pd.concat(frames, ignore_index=True)


def summarize_sweep(raw: pd.DataFrame, param: str) -> pd.DataFrame:
    """Observed ranges describe seed variability, not confidence intervals."""
    columns = {"seeds": ("seed", "nunique")}
    if "rows" in raw:
        columns["rows_per_seed"] = ("rows", "first")
    for metric in raw:
        if metric.endswith("_rate"):
            for stat in ("mean", "min", "max"):
                columns[f"{metric}_{stat}"] = (metric, stat)
    return raw.groupby([param, "semantics"], sort=True).agg(**columns).reset_index()


def figure(sw_late: pd.DataFrame, sw_corr: pd.DataFrame, path: str) -> None:
    """Single-column figure with observed seed ranges at its native size."""
    fig, axes = plt.subplots(1, 2, figsize=(3.4, 2.5), sharey=True)
    labels = {"valid": "valid time", "bitemporal": "bitemporal"}
    styles = {"valid": dict(marker="o", ls="--", color="#1f5fa8", ms=3, lw=1.1),
              "bitemporal": dict(marker="^", ls="-", color="#0a7a3a", ms=3, lw=1.1)}
    for ax, sw, param, xlabel in (
        (axes[0], sw_late, "late_arrival_share", "Late arrivals (%)"),
        (axes[1], sw_corr, "correction_share", "Corrections (%)"),
    ):
        cur = sw[sw.semantics == "current"]
        for sem in ("valid", "bitemporal"):
            d = sw[sw.semantics == sem].sort_values(param)
            mean = d["disagreement_rate_mean"] * 100
            low = d["disagreement_rate_min"] * 100
            high = d["disagreement_rate_max"] * 100
            ax.errorbar(d[param] * 100, mean, yerr=[mean-low, high-mean],
                        capsize=3, label=labels[sem], **styles[sem])
        ax.text(0.03, 0.97,
                f"Current value:\n{cur.disagreement_rate_min.min()*100:.1f}–"
                f"{cur.disagreement_rate_max.max()*100:.1f}%",
                transform=ax.transAxes, fontsize=7, va="top", color="#444444")
        ax.set_xlabel(xlabel, fontsize=8)
        ax.tick_params(labelsize=7)
        upper = max(35, max(sw_late.query("semantics == 'valid'").disagreement_rate_max.max(),
                            sw_corr.query("semantics == 'valid'").disagreement_rate_max.max()) * 115)
        ax.set_ylim(-1, upper + 3)
        ax.grid(True, lw=0.4, alpha=0.5)
    axes[0].set_ylabel("Reconstruction\ndisagreement (%)", fontsize=8)
    axes[0].legend(fontsize=6.8, frameon=False, loc="upper left", bbox_to_anchor=(0, .80),
                   handlelength=1.5, borderaxespad=0.2)
    fig.tight_layout(pad=0.6)
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
            "disagreement_rate_if_run": m["disagreement_rate"],
            "impossible_rate_if_run": m["impossible_rate"],
        })
    return pd.DataFrame(rows)


def governed_comparison(con: duckdb.DuckDBPyConnection,
                        facilities: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Exercise analogous requests, without importing the legacy jobs' SQL.

    Unsupported parameters demonstrate the API surface, not a SQL analyzer.
    Corrected history is executable and legitimate; intent still comes from
    the caller and can disagree with an as-known business question.
    """
    from fscontracts import governed

    attempts = [
        ({"interpretation": "current"}, "request a current-value interpretation"),
        ({"knowledge_time_predicate": False}, "request omission of knowledge predicates"),
        ({"cutoff": "job_run"}, "request one job-run cutoff"),
        ({"valid_op": "<"}, "request an exclusive valid-time boundary"),
        ({"interpretation": "as_known"}, "request built-in as-known history"),
        ({"interpretation": "corrected"}, "request built-in corrected history"),
        ({"assignment_semantics": "current"}, "request a current-value assignment join"),
    ]
    truth = reads.run_read(con, reads.sql_for("bitemporal"))
    rows, receipts = [], []
    for job, (request, explanation) in zip(admission.variants(), attempts):
        row = {"variant": job.name, "analogous_api_request": explanation,
               "request_parameters": json.dumps(request, sort_keys=True),
               "executed": False, "interpretation_matches_question": None,
               "disagreement_rate": None, "outcome": None}
        try:
            result, receipt = governed.execute_contract(con, **request)
        except (ValueError, TypeError) as exc:
            row["outcome"] = f"{type(exc).__name__}: {exc}"
        else:
            row["executed"] = True
            row["interpretation_matches_question"] = receipt["interpretation"] == "as_known"
            row["disagreement_rate"] = reads.compare(result, truth, facilities)["disagreement_rate"]
            row["outcome"] = f"executed built-in {receipt['interpretation']} contract"
            receipts.append(receipt)
        rows.append(row)
    return pd.DataFrame(rows), receipts


def _system_value(*command: str) -> str | None:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def environment_record(con: duckdb.DuckDBPyConnection, quick: bool,
                       base: generate.Params, timings: dict[str, float], elapsed: float) -> dict:
    """A publishable record: no hostname, login, executable or workspace path."""
    cpu = platform.processor() or platform.machine()
    memory = None
    if platform.system() == "Darwin":
        cpu = _system_value("sysctl", "-n", "machdep.cpu.brand_string") or cpu
        value = _system_value("sysctl", "-n", "hw.memsize")
        memory = int(value) if value else None
    else:
        try:
            memory = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
            with open("/proc/cpuinfo") as handle:
                for line in handle:
                    if line.startswith("model name"):
                        cpu = line.split(":", 1)[1].strip()
                        break
        except (OSError, ValueError):
            pass
    versions = {name: metadata.version(name)
                for name in ("duckdb", "pandas", "numpy", "matplotlib", "tabulate")}
    versions["python"] = platform.python_version()
    versions["python_implementation"] = platform.python_implementation()
    return {
        "os": platform.system(), "os_release": platform.release(),
        "os_version": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.release(),
        "architecture": platform.machine(), "cpu_model": cpu,
        "logical_cpus": os.cpu_count(), "ram_bytes": memory,
        "duckdb_threads": int(con.execute("SELECT current_setting('threads')").fetchone()[0]),
        "versions": versions, "quick": quick,
        "main_parameters": dataclasses.asdict(base),
        "sweep_seeds": list(SEEDS), "sweep_orders_per_seed": 20_000 if quick else 100_000,
        "controlled_world": "independent streams for facilities, capacity, assignment, orders, and overlays; "
                            "potential correction values and lags drawn for all rows before selection",
        "timing_protocol": "cost: one warm-up then five timed runs per query on the same connection; "
                           "each sample includes execute and fetchall; other stage times include result fetch",
        "stage_seconds": {name: round(seconds, 6) for name, seconds in timings.items()},
        "experiment_seconds": round(elapsed, 6),
    }


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
        sql_path = path.replace("'", "''")
        con.execute(f"COPY {t} TO '{sql_path}' (FORMAT PARQUET)")
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
    all_samples = []
    for name, sql in queries.items():
        con.execute(sql).fetchall()
        samples = []
        for repetition in range(1, 6):
            t0 = time.perf_counter()
            con.execute(sql).fetchall()
            seconds = time.perf_counter() - t0
            samples.append(seconds)
            all_samples.append({"query": name, "repetition": repetition,
                                "seconds_including_fetch": seconds})
        times[name] = samples
    rows = [{"item": f"{t} table", "rows": v["rows"], "parquet_bytes": v["parquet_bytes"],
             "median_query_seconds": None} for t, v in sizes.items()]
    rows += [{"item": name, "rows": None, "parquet_bytes": None,
              "median_query_seconds": round(statistics.median(samples), 6),
              "min_query_seconds": round(min(samples), 6),
              "max_query_seconds": round(max(samples), 6)} for name, samples in times.items()]
    pd.DataFrame(all_samples).to_csv(os.path.join(workdir, "query_timings.csv"), index=False)
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="write a smaller smoke run to results/quick")
    ap.add_argument("--output", help="explicit output directory (overrides the default)")
    ap.add_argument("--threads", type=int, default=min(4, os.cpu_count() or 1),
                    help="DuckDB worker threads (default: up to four)")
    args = ap.parse_args(argv)
    if args.threads < 1:
        ap.error("--threads must be positive")
    out = output_directory(args.quick, args.output)
    os.makedirs(out, exist_ok=True)
    started = time.perf_counter()
    timings = {}

    def timed(name, action):
        print(f"Running {name}...", flush=True)
        before = time.perf_counter()
        result = action()
        timings[name] = time.perf_counter() - before
        print(f"Completed {name}: {timings[name]:.2f}s", flush=True)
        return result

    base = generate.Params()
    if args.quick:
        base = dataclasses.replace(base, n_orders=20_000)
    sweep_base = dataclasses.replace(base, n_orders=20_000 if args.quick else 100_000)

    # 1. Main store and the three reads.
    t = timed("main generation", lambda: generate.generate(base))
    con = duckdb.connect(config={"threads": args.threads})
    timed("main loading", lambda: load(con, t))
    main_reads = timed("main reads", lambda: three_reads(con, t["facilities"]))
    main_reads.to_csv(os.path.join(out, "main_reads.csv"), index=False)

    # 1b. Control. With neither late arrivals nor corrections the valid time
    # read and the bitemporal read must coincide.
    ctrl_p = dataclasses.replace(sweep_base, late_arrival_share=0.0, short_lag_share=0.0,
                                 correction_share=0.0)
    def control_run():
        ctrl_t = generate.generate(ctrl_p)
        with duckdb.connect(config={"threads": args.threads}) as ctrl_con:
            load(ctrl_con, ctrl_t)
            result = three_reads(ctrl_con, ctrl_t["facilities"])
            pd.testing.assert_frame_equal(reads.run_read(ctrl_con, reads.sql_for("valid")),
                                          reads.run_read(ctrl_con, reads.sql_for("bitemporal")))
            return result
    control = timed("no-lag control", control_run)
    control.to_csv(os.path.join(out, "control_no_lag_no_correction.csv"), index=False)

    # 2. Sweeps and the figure.
    raw_late = timed("late-arrival sweep", lambda: sweep(
        "late_arrival_share", [0.0, 0.05, 0.10, 0.20, 0.30], sweep_base, threads=args.threads))
    raw_corr = timed("correction sweep", lambda: sweep(
        "correction_share", [0.0, 0.05, 0.15, 0.30, 0.50], sweep_base, threads=args.threads))
    sw_late = summarize_sweep(raw_late, "late_arrival_share")
    sw_corr = summarize_sweep(raw_corr, "correction_share")
    raw_late.to_csv(os.path.join(out, "sweep_late_per_seed.csv"), index=False)
    raw_corr.to_csv(os.path.join(out, "sweep_correction_per_seed.csv"), index=False)
    sw_late.to_csv(os.path.join(out, "sweep_late.csv"), index=False)
    sw_corr.to_csv(os.path.join(out, "sweep_correction.csv"), index=False)
    figure(sw_late, sw_corr, os.path.join(out, "fig_disagreement.pdf"))

    # 3. Admission check over the seven variants.
    adm = timed("declaration admission", lambda: admission_table(con, t["facilities"]))
    adm.to_csv(os.path.join(out, "admission.csv"), index=False)
    api, receipts = timed("closed contract API", lambda: governed_comparison(con, t["facilities"]))
    api.to_csv(os.path.join(out, "governed_comparison.csv"), index=False)
    with open(os.path.join(out, "execution_receipts.json"), "w") as handle:
        json.dump(receipts, handle, indent=2, default=str)

    # 4. Cost.
    c = timed("storage and timing", lambda: cost(con, out))
    c.to_csv(os.path.join(out, "cost.csv"), index=False)

    # 5. Reach report.
    store = timed("retained datasets", lambda: reach.build_store(con))
    subject = reach.pick_subject(con)
    rep = timed("hypothetical deletion recomputation", lambda: reach.reach_report(con, store, subject))
    with open(os.path.join(out, "reach_report.md"), "w") as f:
        f.write(reach.render_markdown(rep))
    reach.dump({"store": store, "report": rep}, os.path.join(out, "reach_report.json"))
    env = environment_record(con, args.quick, base, timings, time.perf_counter() - started)
    with open(os.path.join(out, "environment.json"), "w") as handle:
        json.dump(env, handle, indent=2, default=str)

    # 6. Summary.
    dim_rows = {k: len(v) for k, v in t.items()}
    with open(os.path.join(out, "summary.md"), "w") as f:
        f.write("# Results summary" + (" — smoke test" if args.quick else "") + "\n\n")
        f.write(f"Parameters: {json.dumps(dataclasses.asdict(base), default=str)}\n\n")
        f.write(f"Table sizes: {dim_rows}\n\n")
        f.write("Reconstruction disagreement counts null-safe differences in facility or capacity "
                "from the as-known reference. It does not count future-information predicate violations.\n\n")
        f.write("## Three reads on the main store\n\n")
        f.write(main_reads.to_markdown(index=False) + "\n\n")
        f.write("## Control, no late arrivals and no corrections\n\n" + control.to_markdown(index=False) + "\n\n")
        f.write(f"Sweeps use seeds {list(SEEDS)} with {sweep_base.n_orders:,} orders per seed and setting. "
                "The base facilities, capacity changes, assignments and orders are fixed within each seed. "
                "Only the specified overlay share changes. Means and observed minimum/maximum across seeds "
                "are shown below; these ranges are not confidence intervals. Raw observations are in the "
                "two `*_per_seed.csv` files.\n\n")
        for title, frame, parameter in (("Late-arrival sweep", sw_late, "late_arrival_share"),
                                         ("Correction sweep", sw_corr, "correction_share")):
            compact = frame[[parameter, "semantics", "seeds", "disagreement_rate_mean",
                             "disagreement_rate_min", "disagreement_rate_max"]]
            f.write(f"## {title}\n\n" + compact.to_markdown(index=False, floatfmt=".5f") + "\n\n")
        adm_columns = ["variant", "admission", "interpretation_matches_question", "disagreement_rate_if_run"]
        f.write("## Declaration admission\n\n" + adm[adm_columns].to_markdown(index=False) + "\n\n")
        api_columns = ["variant", "executed", "interpretation_matches_question", "disagreement_rate"]
        f.write("## Closed contract API\n\nThe matched exercise sends analogous requests through the restricted "
                "API. It never imports arbitrary SQL. Corrected history remains an executable legitimate "
                "interpretation, even when the business question requires as-known history. Request details "
                "and errors are in `governed_comparison.csv`; successful execution evidence is in "
                "`execution_receipts.json`.\n\n" + api[api_columns].to_markdown(index=False) + "\n\n")
        f.write("## Cost\n\n" + c.to_markdown(index=False) + "\n\n")
        f.write(f"{env['os']} {env['os_version']}, {env['cpu_model']}, "
                f"{env['ram_bytes']} bytes RAM; {env['duckdb_threads']} DuckDB threads. "
                f"Versions: {json.dumps(env['versions'])}. Query medians use five measured executions "
                "after one warm-up, including result fetch. `query_timings.csv` retains samples and "
                "`environment.json` retains stage timings.\n\n")
        f.write("## Reach report\n\n" + reach.render_markdown(rep) + "\n")
    con.close()
    with open(os.path.join(out, "summary.md")) as handle:
        print(handle.read())


if __name__ == "__main__":
    main()
