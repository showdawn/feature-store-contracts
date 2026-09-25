"""Synthetic bitemporal feature store for the EDBT 2027 vision paper
"Treat the Feature Store Like the Database It Is".

Everything here is synthetic. The generator produces one fulfilment style
store with a region to facility assignment dimension and a facility capacity
dimension, both kept as bitemporal histories, plus an orders fact table that
plays the role of the training labels.

Two clocks are recorded for every dimension row.

    valid_from    the day the fact became true in the world
    recorded_at   the day the store came to know it

recorded_at is valid_from plus a recording lag. By default 70 percent of
dimension rows are recorded on the day they become valid, 20 percent one to
three days later and 10 percent between 7 and 60 days later. Both late shares
are parameters. A configurable share of rows are later
corrected, and a correction is a new row with the same valid_from and a later
recorded_at. That is the standard bitemporal encoding, see Jensen and
Snodgrass, IEEE TKDE 1999.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

import numpy as np
import pandas as pd

DAY = dt.timedelta(days=1)


@dataclasses.dataclass
class Params:
    seed: int = 7
    start: dt.date = dt.date(2024, 1, 1)
    days: int = 730
    n_regions: int = 24
    n_facilities_initial: int = 30
    n_facilities_opened_later: int = 10
    n_orders: int = 300_000
    mean_days_between_capacity_changes: float = 45.0
    short_lag_share: float = 0.20        # share of dimension rows recorded 1 to 3 days late
    late_arrival_share: float = 0.10     # share of dimension rows recorded 7 to 60 days late
    correction_share: float = 0.15       # share of dimension rows later corrected
    correction_lag_days: tuple[int, int] = (5, 30)
    late_lag_days: tuple[int, int] = (7, 60)


def _rng(p: Params) -> np.random.Generator:
    return np.random.default_rng(p.seed)


def _recording_lag(rng: np.random.Generator, n: int, p: Params) -> np.ndarray:
    """Same day for most rows, one to three days for some, late for a share."""
    u = rng.random(n)
    lag = np.zeros(n, dtype=int)
    short = (u >= 1.0 - p.late_arrival_share - p.short_lag_share) & (u < 1.0 - p.late_arrival_share)
    lag[short] = rng.integers(1, 4, size=short.sum())
    late = u >= 1.0 - p.late_arrival_share
    lo, hi = p.late_lag_days
    lag[late] = rng.integers(lo, hi + 1, size=late.sum())
    return lag


def _add_corrections(rows: pd.DataFrame, rng: np.random.Generator, p: Params,
                     value_col: str, jitter) -> pd.DataFrame:
    """Pick a share of rows and add a correction row for each.

    A correction keeps valid_from, gets a later recorded_at and a new value.
    """
    n = len(rows)
    pick = rng.random(n) < p.correction_share
    corr = rows[pick].copy()
    lo, hi = p.correction_lag_days
    corr["recorded_at"] = corr["recorded_at"] + pd.to_timedelta(
        rng.integers(lo, hi + 1, size=len(corr)), unit="D")
    corr[value_col] = jitter(corr[value_col].to_numpy(), rng)
    corr["is_correction"] = True
    rows = rows.copy()
    rows["is_correction"] = False
    out = pd.concat([rows, corr], ignore_index=True)
    return out.sort_values(["key", "valid_from", "recorded_at"]).reset_index(drop=True)


def generate(p: Params) -> dict[str, pd.DataFrame]:
    rng = _rng(p)
    start = pd.Timestamp(p.start)
    end = start + pd.Timedelta(days=p.days - 1)

    # Facilities. Some exist from day 0, some open later in the window.
    n_fac = p.n_facilities_initial + p.n_facilities_opened_later
    open_offsets = np.concatenate([
        np.zeros(p.n_facilities_initial, dtype=int),
        rng.integers(90, p.days - 120, size=p.n_facilities_opened_later),
    ])
    facilities = pd.DataFrame({
        "facility_id": np.arange(n_fac),
        "open_date": start + pd.to_timedelta(open_offsets, unit="D"),
    })

    # Capacity history per facility. Initial value at open, then changes.
    cap_rows = []
    for fid, open_date in zip(facilities.facility_id, facilities.open_date):
        day = open_date
        value = float(rng.integers(800, 4000))
        cap_rows.append((fid, day, value))
        while True:
            gap = int(rng.exponential(p.mean_days_between_capacity_changes)) + 1
            day = day + pd.Timedelta(days=gap)
            if day > end:
                break
            value = max(200.0, value * float(rng.normal(1.0, 0.15)))
            cap_rows.append((fid, day, round(value)))
    cap = pd.DataFrame(cap_rows, columns=["key", "valid_from", "capacity"])
    cap["recorded_at"] = cap["valid_from"] + pd.to_timedelta(
        _recording_lag(rng, len(cap), p), unit="D")
    # The opening row of a facility is known on the day it opens.
    first = cap.groupby("key")["valid_from"].transform("min") == cap["valid_from"]
    cap.loc[first, "recorded_at"] = cap.loc[first, "valid_from"]
    cap = _add_corrections(
        cap, rng, p, "capacity",
        jitter=lambda v, r: np.round(v * r.normal(1.0, 0.10, size=len(v))))
    cap = cap.rename(columns={"key": "facility_id"})

    # Region to facility assignment history. A region is served by one
    # facility at a time. When a new facility opens it takes over one or two
    # regions, which is how an order from before the opening can be attributed
    # to a facility that did not exist yet under a current value join.
    assign_rows = []
    initial_fac = facilities[facilities.open_date == start].facility_id.to_numpy()
    for rid in range(p.n_regions):
        assign_rows.append((rid, start, int(rng.choice(initial_fac))))
    later = facilities[facilities.open_date > start]
    regions = np.arange(p.n_regions)
    for fid, open_date in zip(later.facility_id, later.open_date):
        for rid in rng.choice(regions, size=int(rng.integers(1, 3)), replace=False):
            assign_rows.append((int(rid), open_date, int(fid)))
    # Occasional reassignments between existing facilities.
    for _ in range(p.n_regions // 2):
        rid = int(rng.integers(0, p.n_regions))
        day = start + pd.Timedelta(days=int(rng.integers(30, p.days - 30)))
        cands = facilities[facilities.open_date <= day].facility_id.to_numpy()
        assign_rows.append((rid, day, int(rng.choice(cands))))
    asg = pd.DataFrame(assign_rows, columns=["key", "valid_from", "facility_id"])
    asg = asg.drop_duplicates(["key", "valid_from"], keep="last")
    asg["recorded_at"] = asg["valid_from"] + pd.to_timedelta(
        _recording_lag(rng, len(asg), p), unit="D")
    first = asg["valid_from"] == start
    asg.loc[first, "recorded_at"] = start
    asg = _add_corrections(
        asg, rng, p, "facility_id",
        jitter=lambda v, r: r.choice(initial_fac, size=len(v)))
    asg = asg.rename(columns={"key": "region_id"})

    # Orders. Uniform over the window and over regions. Each order has a
    # customer id so a deletion request has a subject to reach.
    order_offsets = rng.integers(0, p.days, size=p.n_orders)
    orders = pd.DataFrame({
        "order_id": np.arange(p.n_orders),
        "order_date": start + pd.to_timedelta(order_offsets, unit="D"),
        "region_id": rng.integers(0, p.n_regions, size=p.n_orders),
        "customer_id": rng.integers(0, 20_000, size=p.n_orders),
        "units": rng.integers(1, 12, size=p.n_orders),
    })

    for df in (cap, asg, orders):
        for c in df.columns:
            if str(df[c].dtype).startswith("datetime"):
                df[c] = df[c].dt.date
    facilities["open_date"] = facilities["open_date"].dt.date
    return {"facilities": facilities, "capacity": cap, "assignment": asg,
            "orders": orders}
