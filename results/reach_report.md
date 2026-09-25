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
