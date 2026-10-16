"""Read-only DuckDB access with a timeout, row limit, and small-cell suppression."""
import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb

from . import guardrails

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "healthcare.duckdb"


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    suppressed_cells: int = 0
    sql: str = ""


class SafeDB:
    def __init__(self, path: Path = DEFAULT_DB, max_rows: int = 200, timeout_s: float = 10.0,
                 min_cell: int = 11):
        # Block file/URL access from SQL even if the validator were bypassed. Passed at connect time
        # (not via SET) because DuckDB shares config across connections to the same file in-process.
        self.con = duckdb.connect(str(path), read_only=True,
                                  config={"enable_external_access": False, "lock_configuration": True})
        self.max_rows, self.timeout_s, self.min_cell = max_rows, timeout_s, min_cell

    def run(self, sql: str) -> QueryResult:
        guardrails.validate_sql(sql)
        limited = guardrails.apply_row_limit(sql, self.max_rows + 1)
        timer = threading.Timer(self.timeout_s, self.con.interrupt)
        timer.start()
        try:
            cur = self.con.execute(limited)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        except duckdb.InterruptException as e:
            raise guardrails.GuardrailError(f"Query exceeded {self.timeout_s}s timeout.") from e
        except duckdb.Error as e:
            raise guardrails.GuardrailError(f"Database error: {str(e)[:300]}") from e
        finally:
            timer.cancel()
        guardrails.check_result_values(rows)
        truncated = len(rows) > self.max_rows
        rows, hits = guardrails.suppress_small_cells(columns, rows[: self.max_rows], self.min_cell)
        return QueryResult(columns, rows, truncated, hits, sql)

    def data_as_of(self) -> dict:
        lo, hi = self.con.execute("select min(admit_ts), max(admit_ts) from admissions").fetchone()
        return {"first_admission": str(lo)[:10], "last_admission": str(hi)[:10]}
