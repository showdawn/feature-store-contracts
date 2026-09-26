"""A declaration-only admission check and seven illustrative job variants.

The check reads a job's declaration, never its SQL. This is the baseline's
stated limit; governed.execute_contract is the closed execution path. A
declaration that is missing a predicate, or that binds the knowledge cutoff
to a constant instead of to each
label's cutoff, is rejected. A declaration that is complete is admitted even
if the SQL behind it has a boundary bug, and a declaration that names the
wrong interpretation for the business question is admitted because the check
cannot know the business question.

Each variant is a rule the author has seen written in a training job, or a
boundary condition of the correct rule.

J3 and J6 bind the knowledge cutoff to the run date or to now. On this store
every dimension row was recorded before any such date, so a predicate
`recorded_at <= run_date` admits every row and the read is row for row the
valid time read. Both variants therefore execute `reads.sql_for("valid")`,
and the experiment reports the same reconstruction disagreement for J2, J3
and J6. Corrected history is a legitimate choice; its suitability for a
business question is not inferred here.
"""

from __future__ import annotations

import dataclasses

from . import reads


@dataclasses.dataclass(frozen=True)
class JoinDecl:
    dimension: str
    valid_time_predicate: bool       # valid_from compared to a label cutoff
    knowledge_time_predicate: bool   # recorded_at compared to a cutoff
    knowledge_cutoff: str            # 'label', 'job_run', 'now' or 'none'


@dataclasses.dataclass(frozen=True)
class JobDecl:
    name: str
    description: str
    interpretation: str              # 'as_known', 'corrected' or 'none'
    joins: tuple[JoinDecl, ...]
    sql: str


def admission_check(job: JobDecl) -> tuple[str, str]:
    """Return ('admitted' | 'rejected', reason).

    This built-in capacity feature requires assignment and capacity exactly
    once. Verify types, completeness and consistency with the declared
    interpretation, without inspecting SQL or inferring business intent.
    There is deliberately no unused "required interpretation" policy argument.
    """
    if not isinstance(job, JobDecl):
        return "rejected", "job must be a JobDecl"
    if any(not isinstance(getattr(job, field), str)
           for field in ("name", "description", "sql")):
        return "rejected", "name, description and SQL must be strings"
    if not isinstance(job.interpretation, str):
        return "rejected", "temporal interpretation must be a string"
    if job.interpretation == "none":
        return "rejected", "no temporal interpretation declared"
    if job.interpretation not in ("as_known", "corrected"):
        return "rejected", "unknown temporal interpretation"
    if not isinstance(job.joins, tuple) or not job.joins:
        return "rejected", "joins must be a nonempty tuple"
    for j in job.joins:
        if not isinstance(j, JoinDecl):
            return "rejected", "each join must be a JoinDecl"
        if not isinstance(j.dimension, str) or j.dimension not in ("assignment", "capacity"):
            return "rejected", "unknown join dependency"
        if type(j.valid_time_predicate) is not bool or type(j.knowledge_time_predicate) is not bool:
            return "rejected", f"{j.dimension} predicate flags must be booleans"
        if not isinstance(j.knowledge_cutoff, str) or j.knowledge_cutoff not in ("label", "job_run", "now", "none"):
            return "rejected", f"{j.dimension} join has an invalid knowledge cutoff"
    dimensions = [j.dimension for j in job.joins]
    if sorted(dimensions) != ["assignment", "capacity"]:
        return "rejected", "assignment and capacity joins must each appear exactly once"
    for j in job.joins:
        if not j.valid_time_predicate:
            return "rejected", f"{j.dimension} join has no valid time predicate"
        if job.interpretation == "as_known":
            if not j.knowledge_time_predicate:
                return "rejected", f"{j.dimension} join has no knowledge time predicate"
            if j.knowledge_cutoff != "label":
                return "rejected", (f"{j.dimension} join binds the knowledge cutoff to "
                                    f"'{j.knowledge_cutoff}' instead of each label's cutoff")
        if job.interpretation == "corrected":
            if not j.knowledge_time_predicate:
                return "rejected", f"{j.dimension} join has no knowledge time predicate"
            if j.knowledge_cutoff not in ("now", "job_run"):
                return "rejected", (f"{j.dimension} join declares corrected history but "
                                    f"binds knowledge to '{j.knowledge_cutoff}'")
    return "admitted", "declaration complete and consistent"


def _join(dim: str, v: bool, k: bool, cutoff: str) -> JoinDecl:
    return JoinDecl(dim, v, k, cutoff)


def variants() -> list[JobDecl]:
    return [
        JobDecl(
            "J1 current value",
            "Join the current dimension rows. The incident in Section 1.",
            "none",
            (_join("assignment", False, False, "none"), _join("capacity", False, False, "none")),
            reads.sql_for("current"),
        ),
        JobDecl(
            "J2 valid time only",
            "As of join on valid_from. Ignores when the store learned the fact.",
            "as_known",
            (_join("assignment", True, False, "none"), _join("capacity", True, False, "none")),
            reads.sql_for("valid"),
        ),
        JobDecl(
            "J3 knowledge bound to run date",
            "Both clocks, but recorded_at is compared to the job's run date for every row.",
            "as_known",
            (_join("assignment", True, True, "job_run"), _join("capacity", True, True, "job_run")),
            reads.sql_for("valid"),   # recorded_at <= run date admits every row, see module docstring
        ),
        JobDecl(
            "J4 boundary bug",
            "Correct declaration, but the SQL uses < instead of <= on valid_from.",
            "as_known",
            (_join("assignment", True, True, "label"), _join("capacity", True, True, "label")),
            reads.sql_for("bitemporal", valid_op="<"),
        ),
        JobDecl(
            "J5 bitemporal",
            "Both clocks bound to each order's date. The contract's intended read.",
            "as_known",
            (_join("assignment", True, True, "label"), _join("capacity", True, True, "label")),
            reads.sql_for("bitemporal"),
        ),
        JobDecl(
            "J6 corrected history declared",
            "Declares the corrected history interpretation, consistently, for a "
            "question that needs the as known interpretation.",
            "corrected",
            (_join("assignment", True, True, "now"), _join("capacity", True, True, "now")),
            reads.sql_for("valid"),   # recorded_at <= now admits every row, see module docstring
        ),
        JobDecl(
            "J7 one join fixed",
            "Bitemporal on capacity, current value on the region assignment.",
            "as_known",
            (_join("assignment", False, False, "none"), _join("capacity", True, True, "label")),
            reads.sql_for("bitemporal", assignment_semantics="current"),
        ),
    ]
