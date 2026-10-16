"""SQL guardrails for the NL->SQL agent.

Defense in depth: (1) this static validator, (2) a read-only DuckDB connection with external
access disabled (see db.py), (3) row limit + timeout, (4) small-cell suppression on results.
The validator is deliberately strict: anything it cannot positively classify as a plain
SELECT over the allowed analytic tables is rejected, and the model sees the reason.
"""
import re

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"admissions", "readmissions_30d", "dim_patient", "dim_facility", "condition_groups",
                  "dim_icd10_crosswalk"}
ROW_LEVEL_TABLES = {"admissions", "readmissions_30d", "dim_patient", "condition_groups"}
# Row-level identifiers may be used inside aggregates (COUNT(DISTINCT patient_id)) but never returned.
IDENTIFIER_COLUMNS = {"patient_id", "encounter_id", "next_encounter_id"}
FUNCTION_BLOCKLIST = re.compile(
    r"^(read_|glob|copy|export|import|install|load|pragma|attach|detach|duckdb_|sniff_|parquet_|http|query|"
    r"current_setting|getenv|system|shell|write_)", re.I)
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command,
                   exp.Copy, exp.Set, exp.Use)


class GuardrailError(ValueError):
    """Raised with a message that is safe and useful to show back to the model."""


def validate_sql(sql: str) -> exp.Expression:
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardrailError(f"SQL could not be parsed: {str(e)[:200]}") from e
    if len(statements) != 1:
        raise GuardrailError("Exactly one SQL statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise GuardrailError("Only SELECT queries are allowed (CTEs are fine).")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise GuardrailError(f"{type(node).__name__} statements are not allowed.")
        if isinstance(node, exp.Func):
            name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            if FUNCTION_BLOCKLIST.match(name or ""):
                raise GuardrailError(f"Function '{name}' is not allowed.")
        if isinstance(node, exp.Table) and not isinstance(node.this, exp.Identifier):
            raise GuardrailError("Table functions (file/URL readers) are not allowed.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        if table.args.get("db") or table.args.get("catalog"):
            raise GuardrailError("Schema/catalog-qualified table names are not allowed.")
        if name not in ALLOWED_TABLES and name not in cte_names:
            raise GuardrailError(
                f"Table '{table.name}' is not available. Allowed tables: {sorted(ALLOWED_TABLES)}.")

    _check_output_columns(tree)
    return tree


def _final_select(tree: exp.Expression) -> exp.Select | None:
    node = tree
    while isinstance(node, exp.Union):
        node = node.this
    return node if isinstance(node, exp.Select) else None


def _sources(select: exp.Select) -> list[exp.Expression]:
    """Direct FROM/JOIN sources of this select (not tables nested in subqueries or CTEs)."""
    out = []
    from_ = select.args.get("from") or select.args.get("from_")
    if from_ is not None:
        out.append(from_.this)
    out.extend(j.this for j in select.args.get("joins") or [])
    return out


def _check_output_columns(tree: exp.Expression) -> None:
    """Static aggregate-only check on the final output. Identifiers hidden behind aliases or CTEs
    are caught by the result-level backstop in check_result_values()."""
    select = _final_select(tree)
    if select is None:
        return
    ctes = {c.alias_or_name.lower(): c.this for c in tree.find_all(exp.CTE)}
    reason = _row_level_reason(select, ctes)
    if reason:
        raise GuardrailError(reason)


def _row_level_reason(select: exp.Select, ctes: dict, depth: int = 0) -> str | None:
    if depth > 5:
        return "Query nesting is too deep to verify."
    for projection in select.expressions:
        inner = projection.this if isinstance(projection, exp.Alias) else projection
        if isinstance(inner, exp.Column) and inner.name.lower() in IDENTIFIER_COLUMNS:
            return (f"Column '{inner.name}' is a patient/encounter identifier and cannot be returned. "
                    "Use it only inside aggregates such as COUNT(DISTINCT patient_id).")
    sources = _sources(select)
    has_star = any(isinstance(p.this if isinstance(p, exp.Alias) else p, exp.Star) or
                   (isinstance(p, exp.Column) and isinstance(p.this, exp.Star)) for p in select.expressions)
    aggregated = any(isinstance(n, exp.AggFunc) for n in select.walk()) or         bool(select.args.get("group")) or bool(select.args.get("distinct"))
    derived_ok = bool(sources)
    touches_row_level = False   # reference tables (the ICD-10 crosswalk) hold no patient records
    # Inspect derived sources only when this select passes their columns through (SELECT *) or is not
    # itself aggregating. An aggregating outer query may legitimately read ids inside a subquery.
    recurse = has_star or not aggregated
    for src in sources:
        if isinstance(src, exp.Table):
            name = (src.name or "").lower()
            if name in ctes:
                sub = _final_select(ctes[name])
                sub_reason = _row_level_reason(sub, ctes, depth + 1) if (sub is not None and recurse) else None
                if sub_reason:
                    return sub_reason
            else:
                derived_ok = False
                touches_row_level = touches_row_level or name in ROW_LEVEL_TABLES
                if has_star and name in ROW_LEVEL_TABLES:
                    return ("SELECT * returns row-level records. Aggregate (COUNT, AVG, ...) or "
                            "name non-identifier columns explicitly.")
        elif isinstance(src, exp.Subquery) and isinstance(src.this, (exp.Select, exp.Union)):
            sub = _final_select(src.this)
            sub_reason = _row_level_reason(sub, ctes, depth + 1) if (sub is not None and recurse) else None
            if sub_reason:
                return sub_reason
        else:
            derived_ok = False
    if not aggregated and not derived_ok and touches_row_level:
        return ("Row-level output is not allowed. Use aggregates (COUNT/AVG/SUM) with GROUP BY, "
                "or SELECT DISTINCT.")
    return None


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def check_result_values(rows: list[tuple]) -> None:
    """Backstop: refuse to return any identifier-shaped (UUID) value, however the SQL produced it."""
    for row in rows:
        for v in row:
            if isinstance(v, str) and UUID_RE.match(v):
                raise GuardrailError("Result contains patient/encounter identifiers; return aggregates only.")


def apply_row_limit(sql: str, limit: int) -> str:
    return f"SELECT * FROM ({sql.rstrip().rstrip(';')}) AS _q LIMIT {int(limit)}"


COUNT_LIKE = re.compile(r"(^n$|^n_|_n$|count|patients|admissions|encounters|readmissions|denominator|"
                        r"numerator|cases|people)", re.I)


def suppress_small_cells(columns: list[str], rows: list[tuple], min_cell: int) -> tuple[list[tuple], int]:
    """Replace count-like integer cells in 1..min_cell-1 with '<min_cell'. Returns (rows, n_suppressed)."""
    if min_cell <= 1:
        return rows, 0
    idx = [i for i, c in enumerate(columns) if COUNT_LIKE.search(c)]
    out, hits = [], 0
    for row in rows:
        row = list(row)
        for i in idx:
            v = row[i]
            if isinstance(v, int) and not isinstance(v, bool) and 0 < v < min_cell:
                row[i] = f"<{min_cell}"
                hits += 1
        out.append(tuple(row))
    return out, hits
