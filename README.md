# Feature store contracts: executable relational fragment

Artifact for *[Vision Paper] Composing Contracts Across the Feature Store
Lifecycle* by Sachidananda Singh, prepared for EDBT 2027. The corresponding
artifact snapshot is `edbt2027-v4`.

This package generates a synthetic fulfilment store and exercises three temporal
reads, a declaration checker, a restricted temporal execution API, and
hypothetical subject removal through a shared aggregate and retained datasets.
The paper proposes a broader contract and evidence interface; this artifact
implements a closed relational fragment of that proposal.

## Run the artifact

The reference run used CPython **3.9.6**. From this repository, use a Python 3.9
interpreter to create an isolated environment and install the tested pins:

```sh
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python run.py --threads 4
```

`requirements-lock.txt` pins the five direct dependencies and their active
runtime dependency closure as installed in the reference interpreter, including
Python-version markers for conditional dependencies. It excludes optional extras
and unrelated installed packages. The lock records package versions, not wheel
hashes, an operating-system image, or a Python installation. `requirements.txt`
retains the broader compatibility ranges; installing from it can select a
different environment and is not an exact recreation of the tested one.

The full run uses 300,000 orders for the main experiment and 100,000 orders per
seed and setting for the sweeps. It writes to `results/`, replacing generated
files there. To preserve the committed reference outputs, select another
destination:

```sh
.venv/bin/python run.py --threads 4 --output /tmp/feature-store-contracts-full
```

The smaller smoke run uses 20,000 orders for the main experiment and each sweep
setting. Its default destination is separate from the paper's results:

```sh
.venv/bin/python run.py --quick --threads 4
# Writes results/quick/
.venv/bin/python run.py --quick --threads 4 --output /tmp/feature-store-contracts-quick
```

`--output` overrides either default destination. `--threads` must be positive;
its default is the smaller of four and the machine's logical CPU count. Run time
depends on the machine and environment. Every run records its stage timings,
query samples and environment rather than assuming a fixed duration.

## Temporal experiment

The main store spans 730 days beginning January 1, 2024. It has 24 regions and
40 facilities: 30 exist initially and ten open later. Orders contain the decision
date, region, customer and units. The assignment dimension maps regions to
facilities; the capacity dimension records facility capacity changes. Both
dimensions retain `valid_from` and `recorded_at`.

The default recording-lag overlay assigns probabilities of 20% to a short lag
of one to three days and 10% to a lag of seven to 60 days. Initial dimension
rows are always known on their valid date. The correction overlay selects rows
with probability 15%, adding a version with the same valid date, a later
recorded date and a sampled value. These are generator parameters, not measured
production frequencies.

`fscontracts/reads.py` implements these selections on both dimension joins:

| Read | Eligible versions, then ordered by descending `(valid_from, recorded_at)` |
|---|---|
| `current` | All retained versions |
| `valid` | `valid_from <= order_date` |
| `bitemporal` | `valid_from <= order_date` and `recorded_at <= order_date` |

The bitemporal read is the reference for reconstructing information known at
each historical decision. The valid-time read instead represents corrected
history in the chosen input snapshot. Both interpretations can be legitimate.
Missing historical matches remain missing; equality at the cutoff is included.

**Reconstruction disagreement** is the fraction of order rows whose selected
facility or capacity differs from the bitemporal reference, treating two missing
values as equal. It is not a count of future-information violations: an
ineligible version might have an unchanged value, and a selection error might
reveal no future information. The reference's zero self-disagreement is
definitional; hand-calculated fixtures independently check selection behavior.

The sweeps use seeds `7, 11, 19, 23, 31`. Independent random streams keep each
seed's facilities, orders and base dimension values fixed across parameter
settings. Potential correction values and delays are drawn before selecting
corrections. The summaries report means and observed minimum/maximum across
seeds; the ranges are not confidence intervals for a production population.
A control with all lag and correction shares set to zero checks equality of the
valid-time and bitemporal outputs.

## Declarations and the restricted execution API

`fscontracts/admission.py` checks declarations for the built-in feature's two
required joins. It rejects malformed declarations, missing predicates, and
inconsistent cutoff bindings without inspecting SQL or inferring business
intent. Four of seven constructed job variants are rejected. Three pass,
including a strict-comparison implementation bug and a consistently declared
corrected-history request used for the wrong business objective.

`fscontracts/governed.py` accepts a registered feature version and an allowed
interpretation, then generates both joins. Its public API does not accept SQL,
comparison operators or per-join overrides. This executable example builds a
small store and returns a result and receipt:

```python
import duckdb

from fscontracts.generate import Params, generate
from fscontracts.governed import execute_contract
from run import load

tables = generate(Params(n_orders=100))
with duckdb.connect(config={"threads": 2}) as con:
    load(con, tables)
    result, receipt = execute_contract(
        con,
        interpretation="as_known",  # alternatively: "corrected"
        feature_version="capacity_v1",
        backend="duckdb",
        cutoff="order_date",
    )
    print(result.head())
    print(receipt["interpretation"], receipt["sources"]["orders"]["sha256"])
```

The API validates materialized source tables, required types and non-null
values, unique order IDs, and unique dimension ranking keys. Time columns must
be timezone-naive DuckDB dates/timestamps. It requires exclusive use of a trusted
connection without an existing transaction. Fingerprinting and execution occur
inside one transaction. Unsupported choices or schemas are rejected; unknown
keyword arguments raise `TypeError`.

The receipt records the contract/version, interpretation, cutoff, backend
version, generated SQL digest, source identities/schema/row counts/content
digests, result row count and scope limitations. It identifies the invocation
and inputs; it is unsigned and is not a proof that the implementation is correct.
The operator is not a security perimeter: direct SQL, modified code, hostile
catalog changes, external consumers and unregistered exports remain outside its
control. It also cannot choose the correct business interpretation for a caller.

`governed_comparison.csv` exercises analogous requests through this restricted
API. Five unsupported requests fail and the two legitimate interpretations
execute. This is not an arbitrary-SQL analyzer or evidence that centralization
reduces mistakes by independent engineers.

## Shared-feature reach and hypothetical recomputation

`fscontracts/reach.py` materializes regional demand by calendar week. Each
training row joins the bitemporal capacity feature with demand from the
**previous complete week** in its region. Orders are assumed known on their
order date; late or corrected fact rows are not modeled.

Three overlapping dataset versions retain date ranges, a definition identifier
and digest, input fingerprints, and recorded derived dependencies. The report
chooses a subject, omits that subject's orders from a scratch input, and reruns
the aggregate and feature construction. This can change other customers' feature
values, including rows in a dataset with no direct subject rows.

The reach example invokes the temporal read directly. Its manifests do not yet
retain a reference to a restricted-API execution receipt. Persistent handoffs
between those evidence records remain part of the proposed lifecycle design.

Verification compares recomputed aggregate cells with independently calculated
contribution deltas, checks dataset row identities and row-local values, checks
shared-feature changes, and checks unaffected rows. Missing or changed retained
inputs/artifacts cause an explicit failure. Fingerprints before and after the
operation verify that retained originals remain unchanged.

The report separates `lineage`, `consumption`, `action`, `verification`, and
`removal_certification`. They are distinct evidence fields, not levels on a
guarantee ladder. Three model identifiers have declared dataset associations;
one records a retraining method that is not executed. **No model is trained,
retained data is not deleted, and no removal is certified.** The action is
hypothetical recomputation. Unregistered exports appear as unknown coverage.

## Outputs and their schemas

These names are relative to the selected output directory. Rates are fractions
in `[0, 1]`; the figure displays percentages.

| Output | Contents |
|---|---|
| `main_reads.csv`, `control_no_lag_no_correction.csv` | `semantics`, `rows`, `disagreement_rate`, `facility_mismatch_rate`, `impossible_rate` (facility not open on order date), and `missing_rate` (missing selected capacity) |
| `sweep_late_per_seed.csv`, `sweep_correction_per_seed.csv` | The read metrics plus `seed` and the varied overlay share |
| `sweep_late.csv`, `sweep_correction.csv` | Parameter, semantics, number of seeds, rows per seed, and each rate's mean/min/max |
| `fig_disagreement.pdf`, `fig_disagreement.png` | Sweep means with observed seed-range error bars |
| `admission.csv` | Variant, description, declared interpretation, admission/reason, objective match, and disagreement/impossible rates if its SQL is run |
| `governed_comparison.csv` | Analogous request and JSON parameters, execution outcome, objective match and disagreement; unexecuted results are empty |
| `execution_receipts.json` | Receipts for the two successful restricted-API executions |
| `cost.csv` | Table row counts/Parquet bytes and query median/min/max seconds; non-applicable cells are empty |
| `query_timings.csv` | Query, repetition and seconds including result fetch for every measured sample |
| `reach_report.json` | Store manifests, model fixture associations, retained fingerprints and report with per-hop checks |
| `reach_report.md` | Readable evidence fields and direct/indirect reach counts |
| `environment.json` | Parameters, seeds, package/Python versions, hardware, thread setting, timing protocol and stage durations |
| `summary.md` | Readable tables and explanation of the run |
| `orders.parquet`, `capacity.parquet`, `assignment.parquet`, `capacity_current.parquet`, `assignment_current.parquet` | Generated tables exported for the storage measurement; regenerated locally rather than committed |

Source fingerprints depend on the recorded encoding and DuckDB version.
Timing records and rendering metadata can change between runs; regeneration
does not promise byte-identical output files. The dataset materializations used
by the reach experiment live in its DuckDB connection and are rebuilt by the
runner, not supplied as permanently available external datasets.

## Reference full run

The committed full results use seed 7 and 300,000 orders. Current-value and
valid-time reads disagree with the historical reference on **96.096%** and
**12.029%** of rows, respectively. The admitted strict-boundary variant disagrees
on **1.858%**. These magnitudes characterize this synthetic generator.

For subject `10751`, the hypothetical reach report identifies 32 source rows
and 32 regional-week cells. In the full-range dataset `v3`, it removes 32 subject
rows from the scratch result and changes the shared feature on 3,725 other
customers' rows. The original dataset remains unchanged.

The recorded machine is macOS 27.0, arm64, Apple M5 Pro, 48 GiB RAM, with four
DuckDB threads. The reference interpreter is CPython 3.9.6 (`/usr/bin/python3`);
direct package versions are DuckDB 1.4.5, pandas 2.3.3, NumPy 2.0.2, Matplotlib
3.9.4 and tabulate 0.9.0. The lock includes their runtime dependencies.

Each cost query has one warm-up and five measured executions on the same
connection, including result fetch into Python. The operational baseline joins
current snapshot tables; the history reads rank retained dimension versions.
Use `cost.csv`, `query_timings.csv` and `environment.json` for exact measurements.
These timings are hardware-dependent and do not isolate admission overhead.

## Scope and limitations

All data and workloads are synthetic. The constructed variants are illustrative
cases, not a sample of independent engineers' errors. The artifact does not
measure production prevalence, compare deployed feature-store products, or
establish performance at large dimension-history scale. It relies on correctly
captured clocks and a fixed deterministic relational definition.

Consumer semantic compatibility and migration enforcement, multi-engine access
control, complete export registration, retention-policy execution, arbitrary
transformation provenance, model influence, and verified model removal remain
outside this implemented fragment. The tests cover supported behavior and
explicit failures; they do not establish those broader guarantees.

## Licence

MIT; see `LICENSE`.
