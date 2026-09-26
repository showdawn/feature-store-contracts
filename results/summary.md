# Results summary

Parameters: {"seed": 7, "start": "2024-01-01", "days": 730, "n_regions": 24, "n_facilities_initial": 30, "n_facilities_opened_later": 10, "n_orders": 300000, "mean_days_between_capacity_changes": 45.0, "short_lag_share": 0.2, "late_arrival_share": 0.1, "correction_share": 0.15, "correction_lag_days": [5, 30], "late_lag_days": [7, 60]}

Table sizes: {'facilities': 40, 'capacity': 676, 'assignment': 67, 'orders': 300000}

Reconstruction disagreement counts null-safe differences in facility or capacity from the as-known reference. It does not count future-information predicate violations.

## Three reads on the main store

| semantics   |   rows |   disagreement_rate |   facility_mismatch_rate |   impossible_rate |   missing_rate |
|:------------|-------:|--------------------:|-------------------------:|------------------:|---------------:|
| current     | 300000 |             0.96096 |                0.472113  |           0.28511 |              0 |
| valid       | 300000 |             0.12029 |                0.0213367 |           0       |              0 |
| bitemporal  | 300000 |             0       |                0         |           0       |              0 |

## Control, no late arrivals and no corrections

| semantics   |   rows |   disagreement_rate |   facility_mismatch_rate |   impossible_rate |   missing_rate |
|:------------|-------:|--------------------:|-------------------------:|------------------:|---------------:|
| current     | 100000 |             0.96819 |                  0.46227 |           0.34704 |              0 |
| valid       | 100000 |             0       |                  0       |           0       |              0 |
| bitemporal  | 100000 |             0       |                  0       |           0       |              0 |

Sweeps use seeds [7, 11, 19, 23, 31] with 100,000 orders per seed and setting. The base facilities, capacity changes, assignments and orders are fixed within each seed. Only the specified overlay share changes. Means and observed minimum/maximum across seeds are shown below; these ranges are not confidence intervals. Raw observations are in the two `*_per_seed.csv` files.

## Late-arrival sweep

|   late_arrival_share | semantics   |   seeds |   disagreement_rate_mean |   disagreement_rate_min |   disagreement_rate_max |
|---------------------:|:------------|--------:|-------------------------:|------------------------:|------------------------:|
|              0.00000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|              0.00000 | current     |       5 |                  0.95394 |                 0.93981 |                 0.96529 |
|              0.00000 | valid       |       5 |                  0.06954 |                 0.05771 |                 0.07786 |
|              0.05000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|              0.05000 | current     |       5 |                  0.95543 |                 0.94434 |                 0.96541 |
|              0.05000 | valid       |       5 |                  0.09733 |                 0.07627 |                 0.11635 |
|              0.10000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|              0.10000 | current     |       5 |                  0.95736 |                 0.94768 |                 0.96717 |
|              0.10000 | valid       |       5 |                  0.11984 |                 0.09336 |                 0.14252 |
|              0.20000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|              0.20000 | current     |       5 |                  0.95942 |                 0.94979 |                 0.96779 |
|              0.20000 | valid       |       5 |                  0.16683 |                 0.14135 |                 0.19988 |
|              0.30000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|              0.30000 | current     |       5 |                  0.96074 |                 0.95018 |                 0.96940 |
|              0.30000 | valid       |       5 |                  0.21228 |                 0.19086 |                 0.24054 |

## Correction sweep

|   correction_share | semantics   |   seeds |   disagreement_rate_mean |   disagreement_rate_min |   disagreement_rate_max |
|-------------------:|:------------|--------:|-------------------------:|------------------------:|------------------------:|
|            0.00000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|            0.00000 | current     |       5 |                  0.95789 |                 0.94751 |                 0.97108 |
|            0.00000 | valid       |       5 |                  0.06330 |                 0.03861 |                 0.07909 |
|            0.05000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|            0.05000 | current     |       5 |                  0.95506 |                 0.94545 |                 0.96413 |
|            0.05000 | valid       |       5 |                  0.08402 |                 0.05850 |                 0.10694 |
|            0.15000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|            0.15000 | current     |       5 |                  0.95736 |                 0.94768 |                 0.96717 |
|            0.15000 | valid       |       5 |                  0.11984 |                 0.09336 |                 0.14252 |
|            0.30000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|            0.30000 | current     |       5 |                  0.95706 |                 0.94856 |                 0.96720 |
|            0.30000 | valid       |       5 |                  0.16886 |                 0.13513 |                 0.20937 |
|            0.50000 | bitemporal  |       5 |                  0.00000 |                 0.00000 |                 0.00000 |
|            0.50000 | current     |       5 |                  0.95947 |                 0.95139 |                 0.97125 |
|            0.50000 | valid       |       5 |                  0.23411 |                 0.21710 |                 0.26504 |

## Declaration admission

| variant                        | admission   | interpretation_matches_question   |   disagreement_rate_if_run |
|:-------------------------------|:------------|:----------------------------------|---------------------------:|
| J1 current value               | rejected    | False                             |                   0.96096  |
| J2 valid time only             | rejected    | True                              |                   0.12029  |
| J3 knowledge bound to run date | rejected    | True                              |                   0.12029  |
| J4 boundary bug                | admitted    | True                              |                   0.01858  |
| J5 bitemporal                  | admitted    | True                              |                   0        |
| J6 corrected history declared  | admitted    | False                             |                   0.12029  |
| J7 one join fixed              | rejected    | True                              |                   0.472113 |

## Closed contract API

The matched exercise sends analogous requests through the restricted API. It never imports arbitrary SQL. Corrected history remains an executable legitimate interpretation, even when the business question requires as-known history. Request details and errors are in `governed_comparison.csv`; successful execution evidence is in `execution_receipts.json`.

| variant                        | executed   | interpretation_matches_question   |   disagreement_rate |
|:-------------------------------|:-----------|:----------------------------------|--------------------:|
| J1 current value               | False      |                                   |           nan       |
| J2 valid time only             | False      |                                   |           nan       |
| J3 knowledge bound to run date | False      |                                   |           nan       |
| J4 boundary bug                | False      |                                   |           nan       |
| J5 bitemporal                  | True       | True                              |             0       |
| J6 corrected history declared  | True       | False                             |             0.12029 |
| J7 one join fixed              | False      |                                   |           nan       |

## Cost

| item                     |   rows |   parquet_bytes |   median_query_seconds |   min_query_seconds |   max_query_seconds |
|:-------------------------|-------:|----------------:|-----------------------:|--------------------:|--------------------:|
| capacity table           |    676 |  7960           |             nan        |          nan        |          nan        |
| capacity_current table   |     40 |   727           |             nan        |          nan        |          nan        |
| assignment table         |     67 |  1439           |             nan        |          nan        |          nan        |
| assignment_current table |     24 |   556           |             nan        |          nan        |          nan        |
| orders table             | 300000 |     2.83159e+06 |             nan        |          nan        |          nan        |
| current snapshot join    |    nan |   nan           |               0.07756  |            0.076489 |            0.081977 |
| current history read     |    nan |   nan           |               0.278521 |            0.275858 |            0.279795 |
| valid history read       |    nan |   nan           |               0.225657 |            0.224722 |            0.22906  |
| bitemporal history read  |    nan |   nan           |               0.196071 |            0.195507 |            0.196255 |

Darwin 27.0, Apple M5 Pro, 51539607552 bytes RAM; 4 DuckDB threads. Versions: {"duckdb": "1.4.5", "pandas": "2.3.3", "numpy": "2.0.2", "matplotlib": "3.9.4", "tabulate": "0.9.0", "python": "3.9.6", "python_implementation": "CPython"}. Query medians use five measured executions after one warm-up, including result fetch. `query_timings.csv` retains samples and `environment.json` retains stage timings.

## Reach report

# Counterfactual reach report for subject 10751

Hypothetical recomputation only. Retained originals remain unchanged; no model is trained and no removal is certified.

| Artifact | Reached | Lineage | Consumption | Action | Verification | Removal certification |
|---|---|---|---|---|---|---|
| orders | 32 rows | tracked_base_rows | not_applicable | hypothetical_filter | passed | none |
| region_week_demand | 32 aggregate cells | tracked_relational | input_dependencies_recorded | hypothetical_recomputation | passed | none |
| dataset v1 | 1591 rows | tracked_relational | input_dependencies_recorded | hypothetical_recomputation | passed | none |
| dataset v2 | 2050 rows | tracked_relational | input_dependencies_recorded | hypothetical_recomputation | passed | none |
| dataset v3 | 3757 rows | tracked_relational | input_dependencies_recorded | hypothetical_recomputation | passed | none |
| model m1 | 1 model identifier | dataset_dependency_recorded | declared_fixture_association | none | not_performed | none |
| model m2 | 1 model identifier | dataset_dependency_recorded | declared_fixture_association | none | not_performed | none |
| model m3 | 1 model identifier | dataset_dependency_recorded | declared_fixture_association | method_recorded_not_executed | not_performed | none |
| exports outside the boundary | unknown | unknown | unknown | unknown | unknown | unknown |

- **orders**: Subject omitted only from scratch input; retained base rows remain unchanged.
- **region_week_demand**: Recomputed from scratch orders; retained-minus-subject deltas checked cell by cell.
- **dataset v1**: Recomputed from scratch orders, temporal dimensions and shared aggregate; retained originals unchanged. Direct subject rows: 14; other customers' changed rows: 1577.
- **dataset v2**: Recomputed from scratch orders, temporal dimensions and shared aggregate; retained originals unchanged. Direct subject rows: 17; other customers' changed rows: 2033.
- **dataset v3**: Recomputed from scratch orders, temporal dimensions and shared aggregate; retained originals unchanged. Direct subject rows: 32; other customers' changed rows: 3725.
- **model m1**: Declared dataset association only; no model trained. Influence and removal unknown.
- **model m2**: Declared dataset association only; no model trained. Influence and removal unknown.
- **model m3**: Declared dataset association only; no model trained. Influence and removal unknown. Recorded method: retrain from scratch on the subject-free recomputed v3 (not executed).
- **exports outside the boundary**: Bypassing exports have no manifests; scope and removal are unknown.

