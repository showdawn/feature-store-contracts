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
