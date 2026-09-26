"""Counterfactual removal through a connected, retained feature pipeline.

Datasets consume bitemporal capacity and the previous *complete* calendar
week's regional demand. Orders are assumed known on their order_date; this
demonstration does not model late or corrected fact rows. Removing one
customer from a scratch input can therefore change other customers' features.

Original inputs and artifacts remain unchanged. The action is a hypothetical
recomputation, not an executed deletion. Model consumption is a declared
fixture association with an identifier: no model is trained or certified.
Lineage, consumption, action, verification, and removal certification are
independent evidence fields, not levels on a guarantee ladder.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import duckdb

from . import reads


_INPUTS = ('orders', 'assignment', 'capacity')
_RANGES = {
    'v1': (dt.date(2024, 1, 1), dt.date(2024, 12, 31)),
    'v2': (dt.date(2024, 7, 1), dt.date(2025, 6, 30)),
    'v3': (dt.date(2024, 1, 1), dt.date(2025, 12, 31)),
}
_DEFINITION_VERSION = 'capacity_and_previous_week_region_demand_v2'


def _fingerprint(con: duckdb.DuckDBPyConnection, table: str) -> dict:
    """Identify retained schema and row multiset, independent of row order.

    Names are internal constants, never user SQL. The algorithm uses DuckDB's
    JSON serialization, whose version is recorded by the experiment runner.
    """
    try:
        schema = [list(row[:2]) for row in con.execute(f'DESCRIBE {table}').fetchall()]
        rows, digest = con.execute(f"""
            SELECT count(*), sha256(coalesce(string_agg(h, '' ORDER BY h), ''))
            FROM (SELECT sha256(to_json(t)) h FROM {table} t)
        """).fetchone()
    except duckdb.Error as error:
        raise ValueError(f'Retained input or artifact {table!r} unavailable: {error}') from error
    payload = json.dumps({'schema': schema, 'row_digest': digest}, separators=(',', ':'))
    return {'algorithm': 'duckdb-json-row-multiset-sha256-v1', 'rows': rows,
            'sha256': hashlib.sha256(payload.encode()).hexdigest()}


def _aggregate_sql(orders_table: str) -> str:
    return f"""
        SELECT region_id, date_trunc('week', order_date) AS week, sum(units) AS units
        FROM main.{orders_table} GROUP BY 1, 2
    """


def _training_sql(orders_table: str, aggregate_table: str) -> str:
    # The outer CTE redirects the existing temporal query to a base-order
    # snapshot. No cached training rows participate in the recomputation.
    return f"""
        WITH orders AS (SELECT * FROM main.{orders_table}),
        temporal_features AS ({reads.sql_for('bitemporal')})
        SELECT f.*, coalesce(d.units, 0) AS previous_week_region_units
        FROM temporal_features f
        LEFT JOIN main.{aggregate_table} d
          ON d.region_id = f.region_id
         AND d.week = date_trunc('week', f.order_date) - INTERVAL '7 days'
        ORDER BY f.order_id
    """


def _materialize(con: duckdb.DuckDBPyConnection, suffix: str) -> None:
    orders, aggregate, training = ('orders' + suffix, 'region_week_demand' + suffix,
                                   'training_read' + suffix)
    con.execute(f'CREATE OR REPLACE TABLE {aggregate} AS {_aggregate_sql(orders)}')
    con.execute(f'CREATE OR REPLACE TABLE {training} AS {_training_sql(orders, aggregate)}')
    for version, (lo, hi) in _RANGES.items():
        con.execute(f"""
            CREATE OR REPLACE TABLE dataset_{version}{suffix} AS
            SELECT * FROM {training} WHERE order_date BETWEEN ? AND ?
        """, [lo, hi])


def build_store(con: duckdb.DuckDBPyConnection) -> dict:
    """Retain a connected pipeline, input identities, and model fixture records."""
    inputs = {name: _fingerprint(con, name) for name in _INPUTS}
    _materialize(con, '')
    definition = _aggregate_sql('orders') + _training_sql('orders', 'region_week_demand')
    definition_digest = hashlib.sha256(definition.encode()).hexdigest()
    manifests = {}
    for version, (lo, hi) in _RANGES.items():
        manifests[version] = {
            'definition_version': _DEFINITION_VERSION,
            'definition_sha256': definition_digest,
            'read_semantics': 'bitemporal capacity; knowledge cutoff = order_date; previous complete week demand',
            'order_availability_assumption': 'orders known on order_date; no late or corrected orders',
            'date_range': [str(lo), str(hi)],
            'input_fingerprints': inputs,
            'consumed_derived_artifacts': ['region_week_demand'],
            'rows': con.execute(f'SELECT count(*) FROM dataset_{version}').fetchone()[0],
        }
    models = {
        'm1': {'consumed': 'v1', 'removal_method': None},
        'm2': {'consumed': 'v2', 'removal_method': None},
        'm3': {'consumed': 'v3',
               'removal_method': 'retrain from scratch on the subject-free recomputed v3',
               'removal_status': 'recorded, not executed'},
    }
    for model in models.values():
        model['consumption_evidence'] = 'declared fixture association; no model trained'
    retained = dict(inputs)
    for name in ['region_week_demand', 'training_read'] + [f'dataset_{v}' for v in _RANGES]:
        retained[name] = _fingerprint(con, name)
    return {'manifests': manifests, 'models': models, 'retained_fingerprints': retained}


def pick_subject(con: duckdb.DuckDBPyConnection) -> int:
    """Prefer a customer spanning both years, then greatest row count."""
    row = con.execute("""
        SELECT customer_id FROM orders GROUP BY customer_id
        ORDER BY count(DISTINCT year(order_date)) DESC, count(*) DESC, customer_id
        LIMIT 1
    """).fetchone()
    if row is None:
        raise ValueError('Cannot select a subject from an empty orders table')
    return int(row[0])


def _verify_retained(con: duckdb.DuckDBPyConnection, store: dict) -> None:
    for table, expected in store['retained_fingerprints'].items():
        if _fingerprint(con, table) != expected:
            raise ValueError(f'Retained input or artifact {table!r} changed from its manifest')


def _verify_aggregate(con: duckdb.DuckDBPyConnection, subject: int) -> dict:
    # Derive expected deltas from the retained total and subject contributions,
    # separately from the scratch pipeline's aggregation of the remaining rows.
    wrong, touched, removed = con.execute("""
        WITH subject_cells AS (
            SELECT region_id, date_trunc('week', order_date) AS week,
                   sum(units) AS units, count(*) AS n
            FROM orders WHERE customer_id = ? GROUP BY 1, 2),
        all_counts AS (
            SELECT region_id, date_trunc('week', order_date) AS week, count(*) AS n
            FROM orders GROUP BY 1, 2),
        expected AS (
            SELECT b.region_id, b.week, b.units - coalesce(s.units, 0) AS units,
                   c.n - coalesce(s.n, 0) AS n, s.n AS subject_n
            FROM region_week_demand b JOIN all_counts c USING (region_id, week)
            LEFT JOIN subject_cells s USING (region_id, week))
        SELECT count(*) FILTER (WHERE
                 (e.n > 0 AND (a.region_id IS NULL OR a.units IS DISTINCT FROM e.units))
                 OR (e.n = 0 AND a.region_id IS NOT NULL) OR e.region_id IS NULL),
               count(*) FILTER (WHERE e.subject_n IS NOT NULL),
               count(*) FILTER (WHERE e.n = 0 AND a.region_id IS NULL)
        FROM expected e FULL OUTER JOIN region_week_demand_minus a USING (region_id, week)
    """, [subject]).fetchone()
    return {'wrong_cells': wrong, 'touched_cells': touched, 'removed_cells': removed,
            'verified': wrong == 0}


def _verify_dataset(con: duckdb.DuckDBPyConnection, version: str, subject: int) -> dict:
    # Row identity and row-local features must remain stable. The shared demand
    # feature must decrease by precisely this subject's previous-week units.
    missing, structural, incorrect, changed, unaffected = con.execute(f"""
        WITH subject_cells AS (
            SELECT region_id, date_trunc('week', order_date) AS week, sum(units) AS units
            FROM orders WHERE customer_id = ? GROUP BY 1, 2),
        before AS (SELECT * FROM dataset_{version} WHERE customer_id <> ?)
        SELECT
          count(*) FILTER (WHERE b.order_id IS NULL OR a.order_id IS NULL),
          count(*) FILTER (WHERE b.order_id IS NOT NULL AND a.order_id IS NOT NULL AND
            (b.order_date, b.region_id, b.customer_id, b.units, b.facility_id, b.capacity)
            IS DISTINCT FROM
            (a.order_date, a.region_id, a.customer_id, a.units, a.facility_id, a.capacity)),
          count(*) FILTER (WHERE a.previous_week_region_units IS DISTINCT FROM
            b.previous_week_region_units - coalesce(s.units, 0)),
          count(*) FILTER (WHERE b.order_id IS NOT NULL AND a.order_id IS NOT NULL AND
            b.previous_week_region_units IS DISTINCT FROM a.previous_week_region_units),
          count(*) FILTER (WHERE s.region_id IS NULL AND
            b.previous_week_region_units IS DISTINCT FROM a.previous_week_region_units)
        FROM before b FULL OUTER JOIN dataset_{version}_minus a USING (order_id)
        LEFT JOIN subject_cells s ON s.region_id = b.region_id
          AND s.week = date_trunc('week', b.order_date) - INTERVAL '7 days'
    """, [subject, subject]).fetchone()
    subject_after = con.execute(
        f'SELECT count(*) FROM dataset_{version}_minus WHERE customer_id = ?', [subject]
    ).fetchone()[0]
    return {'subject_rows_after': subject_after, 'missing_or_extra_rows': missing,
            'row_local_values_changed': structural, 'incorrect_shared_values': incorrect,
            'other_rows_changed': changed, 'unaffected_rows_changed': unaffected,
            'verified': not any((subject_after, missing, structural, incorrect, unaffected))}


def _hop(artifact: str, reached, unit: str, note: str, *, lineage='tracked_relational',
         consumption='input_dependencies_recorded', action='hypothetical_recomputation',
         verification='passed', removal_certification='none', **details) -> dict:
    return {'artifact': artifact, 'reached': reached, 'unit': unit, 'note': note,
            'lineage': lineage, 'consumption': consumption, 'action': action,
            'verification': verification, 'removal_certification': removal_certification,
            **details}


def reach_report(con: duckdb.DuckDBPyConnection, store: dict, subject: int) -> dict:
    """Recompute the connected pipeline in scratch tables, preserving originals.

    Missing or changed retained inputs fail explicitly. A cached training read
    cannot substitute for an unavailable input. No operation deletes retained
    rows, trains a model, or supplies a model-removal certificate.
    """
    if not isinstance(subject, int) or isinstance(subject, bool):
        raise ValueError('subject must be an integer customer identifier')
    _verify_retained(con, store)
    direct = con.execute('SELECT count(*) FROM orders WHERE customer_id = ?', [subject]).fetchone()[0]
    con.execute('CREATE OR REPLACE TABLE orders_minus AS SELECT * FROM orders WHERE customer_id <> ?',
                [subject])
    _materialize(con, '_minus')
    remaining_subject = con.execute(
        'SELECT count(*) FROM orders_minus WHERE customer_id = ?', [subject]).fetchone()[0]
    changed_base = con.execute("""
        SELECT count(*) FROM (
          (SELECT * FROM orders WHERE customer_id <> ? EXCEPT ALL SELECT * FROM orders_minus)
          UNION ALL
          (SELECT * FROM orders_minus EXCEPT ALL SELECT * FROM orders WHERE customer_id <> ?))
    """, [subject, subject]).fetchone()[0]
    base_check = {'subject_rows_after': remaining_subject, 'other_rows_changed': changed_base,
                  'verified': remaining_subject == 0 and changed_base == 0}
    hops = [_hop('orders', direct, 'rows',
                 'Subject omitted only from scratch input; retained base rows remain unchanged.',
                 lineage='tracked_base_rows', consumption='not_applicable',
                 action='hypothetical_filter', verification='passed' if base_check['verified'] else 'failed',
                 check=base_check)]
    aggregate = _verify_aggregate(con, subject)
    hops.append(_hop('region_week_demand', aggregate['touched_cells'], 'aggregate cells',
                     'Recomputed from scratch orders; retained-minus-subject deltas checked cell by cell.',
                     verification='passed' if aggregate['verified'] else 'failed', check=aggregate))
    reached_versions = set()
    for version in _RANGES:
        check = _verify_dataset(con, version, subject)
        n = con.execute(f'SELECT count(*) FROM dataset_{version} WHERE customer_id = ?',
                        [subject]).fetchone()[0]
        indirect = check['other_rows_changed']
        if not (n or indirect):
            continue
        reached_versions.add(version)
        hops.append(_hop(f'dataset {version}', n + indirect, 'rows',
                         'Recomputed from scratch orders, temporal dimensions and shared aggregate; '
                         'retained originals unchanged.',
                         verification='passed' if check['verified'] else 'failed',
                         direct_rows=n, indirect_rows=indirect, check=check))
    for model_id, model in store['models'].items():
        if model['consumed'] not in reached_versions:
            continue
        method = model.get('removal_method')
        hops.append(_hop(f'model {model_id}', 1, 'model identifier',
                         'Declared dataset association only; no model trained. Influence and removal unknown.'
                         + (f' Recorded method: {method} (not executed).' if method else ''),
                         lineage='dataset_dependency_recorded', consumption='declared_fixture_association',
                         action='method_recorded_not_executed' if method else 'none',
                         verification='not_performed', consumed_version=model['consumed']))
    hops.append(_hop('exports outside the boundary', None, 'unknown',
                     'Bypassing exports have no manifests; scope and removal are unknown.',
                     lineage='unknown', consumption='unknown', action='unknown',
                     verification='unknown', removal_certification='unknown'))
    _verify_retained(con, store)
    return {'subject': subject, 'mode': 'hypothetical_recomputation',
            'retained_originals_unchanged': True,
            'scope': 'Retained relational artifacts only; declared model associations; bypass exports unknown.',
            'hops': hops}


def render_markdown(report: dict) -> str:
    lines = [f"# Counterfactual reach report for subject {report['subject']}", '',
             'Hypothetical recomputation only. Retained originals remain unchanged; no model is trained '
             'and no removal is certified.', '',
             '| Artifact | Reached | Lineage | Consumption | Action | Verification | Removal certification |',
             '|---|---|---|---|---|---|---|']
    for hop in report['hops']:
        count = 'unknown' if hop['reached'] is None else f"{hop['reached']} {hop['unit']}"
        lines.append(f"| {hop['artifact']} | {count} | {hop['lineage']} | {hop['consumption']} | "
                     f"{hop['action']} | {hop['verification']} | {hop['removal_certification']} |")
    lines.append('')
    for hop in report['hops']:
        detail = (f" Direct subject rows: {hop['direct_rows']}; other customers' changed rows: "
                  f"{hop['indirect_rows']}." if 'direct_rows' in hop else '')
        lines.append(f"- **{hop['artifact']}**: {hop['note']}{detail}")
    return '\n'.join(lines) + '\n'


def dump(report: dict, path: str) -> None:
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2, default=str)
