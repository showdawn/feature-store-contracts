"""A minimal admission check for training reads, and seven job variants.

The check reads a job's declaration, never its SQL. That is the point of the
paper's proposal and also its stated limit. A declaration that is missing a
predicate, or that binds the knowledge cutoff to a constant instead of to each
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
and the experiment reports the same leakage for J2, J3 and J6. The paper says
so in the caption of Table 3.
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


def admission_check(job: JobDecl, required_interpretation: str = "as_known") -> tuple[str, str]:
    """Return ('admitted' | 'rejected', reason).

    `required_interpretation` is what the store's contract requires for a
    read that reconstructs historical decisions. The check verifies that the
    declaration is complete and internally consistent with its own
    interpretation. It does not, and cannot, verify that the declared
    interpretation is the one the business question needs. That comparison is
    reported separately by the experiment as `interpretation_matches`.
    """
    if job.interpretation == "none":
        return "rejected", "no temporal interpretation declared"
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
