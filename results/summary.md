# Results summary

Parameters: {"seed": 7, "start": "2024-01-01", "days": 730, "n_regions": 24, "n_facilities_initial": 30, "n_facilities_opened_later": 10, "n_orders": 300000, "mean_days_between_capacity_changes": 45.0, "short_lag_share": 0.2, "late_arrival_share": 0.1, "correction_share": 0.15, "correction_lag_days": [5, 30], "late_lag_days": [7, 60]}

Table sizes: {'facilities': 40, 'capacity': 673, 'assignment': 58, 'orders': 300000}

## Three reads on the main store

| semantics   |   rows |   leakage_rate |   facility_mismatch_rate |   impossible_rate |   mean_abs_rel_error |   missing_rate |
|:------------|-------:|---------------:|-------------------------:|------------------:|---------------------:|---------------:|
| current     | 300000 |       0.953043 |                0.37738   |          0.172287 |             0.506495 |              0 |
| valid       | 300000 |       0.13869  |                0.0175667 |          0        |             0.026876 |              0 |
| bitemporal  | 300000 |       0        |                0         |          0        |             0        |              0 |

## Control, no late arrivals and no corrections

| semantics   |   rows |   leakage_rate |   facility_mismatch_rate |   impossible_rate |   mean_abs_rel_error |   missing_rate |
|:------------|-------:|---------------:|-------------------------:|------------------:|---------------------:|---------------:|
| current     | 100000 |        0.92506 |                  0.39395 |           0.31679 |             0.420329 |              0 |
| valid       | 100000 |        0       |                  0       |           0       |             0        |              0 |
| bitemporal  | 100000 |        0       |                  0       |           0       |             0        |              0 |

## Sweep, late arrival share

| semantics   |   rows |   leakage_rate |   facility_mismatch_rate |   impossible_rate |   mean_abs_rel_error |   missing_rate |   late_arrival_share |
|:------------|-------:|---------------:|-------------------------:|------------------:|---------------------:|---------------:|---------------------:|
| current     | 100000 |        0.91623 |                  0.45924 |           0.24294 |            0.547768  |              0 |                 0    |
| valid       | 100000 |        0.06864 |                  0.01052 |           0       |            0.0109533 |              0 |                 0    |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |                 0    |
| current     | 100000 |        0.93114 |                  0.43447 |           0.27803 |            0.621916  |              0 |                 0.05 |
| valid       | 100000 |        0.07415 |                  0.0139  |           0       |            0.0215639 |              0 |                 0.05 |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |                 0.05 |
| current     | 100000 |        0.95276 |                  0.37736 |           0.1725  |            0.503811  |              0 |                 0.1  |
| valid       | 100000 |        0.13724 |                  0.01781 |           0       |            0.0272687 |              0 |                 0.1  |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |                 0.1  |
| current     | 100000 |        0.95003 |                  0.43866 |           0.11606 |            0.572824  |              0 |                 0.2  |
| valid       | 100000 |        0.15769 |                  0.01329 |           0       |            0.0204529 |              0 |                 0.2  |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |                 0.2  |
| current     | 100000 |        0.93496 |                  0.35745 |           0.17094 |            0.609521  |              0 |                 0.3  |
| valid       | 100000 |        0.21466 |                  0.0203  |           0       |            0.031373  |              0 |                 0.3  |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |                 0.3  |

## Sweep, correction share

| semantics   |   rows |   leakage_rate |   facility_mismatch_rate |   impossible_rate |   mean_abs_rel_error |   missing_rate |   correction_share |
|:------------|-------:|---------------:|-------------------------:|------------------:|---------------------:|---------------:|-------------------:|
| current     | 100000 |        0.94665 |                  0.39938 |           0.29993 |            0.427111  |              0 |               0    |
| valid       | 100000 |        0.06631 |                  0.00551 |           0       |            0.0109692 |              0 |               0    |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |               0    |
| current     | 100000 |        0.9361  |                  0.46481 |           0.24922 |            0.592144  |              0 |               0.05 |
| valid       | 100000 |        0.07619 |                  0.01551 |           0       |            0.0105522 |              0 |               0.05 |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |               0.05 |
| current     | 100000 |        0.95276 |                  0.37736 |           0.1725  |            0.503811  |              0 |               0.15 |
| valid       | 100000 |        0.13724 |                  0.01781 |           0       |            0.0272687 |              0 |               0.15 |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |               0.15 |
| current     | 100000 |        0.96059 |                  0.36948 |           0.11878 |            0.679156  |              0 |               0.3  |
| valid       | 100000 |        0.16419 |                  0.0204  |           0       |            0.032344  |              0 |               0.3  |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |               0.3  |
| current     | 100000 |        0.93281 |                  0.44076 |           0.17358 |            0.558513  |              0 |               0.5  |
| valid       | 100000 |        0.23029 |                  0.03025 |           0       |            0.0554253 |              0 |               0.5  |
| bitemporal  | 100000 |        0       |                  0       |           0       |            0         |              0 |               0.5  |

## Admission check

| variant                        | description                                                                                                         | interpretation_declared   | admission   | reason                                                                                 | interpretation_matches_question   |   leakage_rate_if_run |   impossible_rate_if_run |
|:-------------------------------|:--------------------------------------------------------------------------------------------------------------------|:--------------------------|:------------|:---------------------------------------------------------------------------------------|:----------------------------------|----------------------:|-------------------------:|
| J1 current value               | Join the current dimension rows. The incident in Section 1.                                                         | none                      | rejected    | no temporal interpretation declared                                                    | False                             |              0.953043 |                 0.172287 |
| J2 valid time only             | As of join on valid_from. Ignores when the store learned the fact.                                                  | as_known                  | rejected    | assignment join has no knowledge time predicate                                        | True                              |              0.13869  |                 0        |
| J3 knowledge bound to run date | Both clocks, but recorded_at is compared to the job's run date for every row.                                       | as_known                  | rejected    | assignment join binds the knowledge cutoff to 'job_run' instead of each label's cutoff | True                              |              0.13869  |                 0        |
| J4 boundary bug                | Correct declaration, but the SQL uses < instead of <= on valid_from.                                                | as_known                  | admitted    | declaration complete and consistent                                                    | True                              |              0.01855  |                 0        |
| J5 bitemporal                  | Both clocks bound to each order's date. The contract's intended read.                                               | as_known                  | admitted    | declaration complete and consistent                                                    | True                              |              0        |                 0        |
| J6 corrected history declared  | Declares the corrected history interpretation, consistently, for a question that needs the as known interpretation. | corrected                 | admitted    | declaration complete and consistent                                                    | False                             |              0.13869  |                 0        |
| J7 one join fixed              | Bitemporal on capacity, current value on the region assignment.                                                     | as_known                  | rejected    | assignment join has no valid time predicate                                            | True                              |              0.37738  |                 0.172287 |

## Cost

| item                     |   rows |   parquet_bytes |   median_query_seconds |
|:-------------------------|-------:|----------------:|-----------------------:|
| capacity table           |    673 |  7884           |               nan      |
| capacity_current table   |     40 |   772           |               nan      |
| assignment table         |     58 |  1410           |               nan      |
| assignment_current table |     24 |   598           |               nan      |
| orders table             | 300000 |     2.83344e+06 |               nan      |
| current snapshot join    |    nan |   nan           |                 0.1846 |
| current history read     |    nan |   nan           |                 1.1197 |
| valid history read       |    nan |   nan           |                 0.8343 |
| bitemporal history read  |    nan |   nan           |                 0.6334 |

## Reach report

# Reach report for subject 1781

| Artifact | Reached | Guarantee | Note |
|---|---|---|---|
| orders | 32 rows | tracked | base rows, deleted directly |
| region_week_demand | 32 aggregate cells | tracked | relational aggregate, recomputed without the subject and checked cell by cell |
| dataset v1 | 17 rows | tracked | manifest retained, re-materialised from inputs without the subject and checked row by row |
| dataset v2 | 18 rows | tracked | manifest retained, re-materialised from inputs without the subject and checked row by row |
| dataset v3 | 32 rows | tracked | manifest retained, re-materialised from inputs without the subject and checked row by row |
| model m1 | 1 model | consumed | model consumed the dataset version, influence on predictions unknown |
| model m2 | 1 model | consumed | model consumed the dataset version, influence on predictions unknown |
| model m3 | 1 model | recorded | retrain from scratch on v3 re-materialised without the subject (recorded, not executed) |
| exports outside the boundary |  | unknown | standing line, the store holds no manifest for reads that bypassed the admission point |

