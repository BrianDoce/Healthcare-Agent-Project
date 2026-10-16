import re
from pathlib import Path
from types import SimpleNamespace as NS

import duckdb
import pytest

from agent import guardrails
from agent.agent import SCHEMA_DOC, run_agent
from agent.db import DEFAULT_DB, SafeDB
from agent.guardrails import GuardrailError, validate_sql

needs_db = pytest.mark.skipif(not Path(DEFAULT_DB).exists(), reason="run the pipeline first")

OK_QUERIES = [
    "select avg(readmitted_30d::int) from readmissions_30d",
    "with x as (select age_group, count(*) n from admissions group by 1) select * from x",
    "select principal_reason, count(distinct patient_id) as n_patients from admissions group by 1",
    "select distinct age_group from admissions",
    "select f.facility_name, count(*) c from admissions a join dim_facility f using (organization_id) group by 1",
]
BAD_QUERIES = [
    ("drop table admissions", "SELECT"),
    ("delete from admissions", "SELECT"),
    ("select 1; drop table admissions", "Exactly one"),
    ("copy admissions to 'x.csv'", "SELECT"),
    ("select * from read_csv('data/raw/patients.csv')", "not allowed"),
    ("select count(*) from read_parquet('exports/admissions.parquet')", "not allowed"),
    ("select count(*) from raw_patients", "not available"),
    ("select count(*) from stg_patients", "not available"),
    ("select count(*) from main.admissions", "qualified"),
    ("select patient_id from admissions", "identifier"),
    ("select a.encounter_id as x from admissions a", "identifier"),
    ("select * from admissions", "row-level"),
    ("select age_group, length_of_stay_days from admissions", "Row-level output"),
    ("select getenv('HOME')", "not allowed"),
    ("pragma database_list", "SELECT"),
    ("attach 'x.db' as y", "SELECT"),
    ("this is not sql", ""),
    ("with x as (select patient_id from admissions) select * from x", "identifier"),
    ("select * from (select encounter_id from admissions) t", "identifier"),
    ("with x as (select age_group, length_of_stay_days from admissions) select * from x", "Row-level"),
]


@pytest.mark.parametrize("sql", OK_QUERIES)
def test_valid_queries_pass(sql):
    validate_sql(sql)


@pytest.mark.parametrize("sql,fragment", BAD_QUERIES)
def test_dangerous_queries_rejected(sql, fragment):
    with pytest.raises(GuardrailError) as e:
        validate_sql(sql)
    assert fragment.lower() in str(e.value).lower()


def test_small_cell_suppression():
    rows, n = guardrails.suppress_small_cells(["dx", "n_patients", "rate"], [("a", 3, 0.5), ("b", 40, 0.1)], 11)
    assert rows == [("a", "<11", 0.5), ("b", 40, 0.1)] and n == 1
    rows, n = guardrails.suppress_small_cells(["dx", "n_patients"], [("a", 3)], 1)
    assert rows == [("a", 3)] and n == 0


@needs_db
def test_schema_doc_matches_real_tables():
    con = duckdb.connect(str(DEFAULT_DB), read_only=True)
    for table in guardrails.ALLOWED_TABLES:
        cols = [r[0] for r in con.execute(f"describe {table}").fetchall()]
        section = re.search(rf"\*\*{table}\*\*(.*?)(?=\n\*\*|\n## )", SCHEMA_DOC, re.S).group(1)
        missing = [c for c in cols if c not in section]
        assert not missing, f"{table}: columns undocumented in schema.md: {missing}"


@needs_db
def test_db_enforces_limits_and_read_only():
    db = SafeDB(max_rows=5, min_cell=1)
    res = db.run("select principal_reason, count(*) n from admissions group by 1 order by 2 desc")
    assert len(res.rows) == 5 and res.truncated
    with pytest.raises(GuardrailError):
        db.run("select count(*) from admissions where nonexistent_col = 1")
    # even bypassing the validator, the connection itself must refuse writes and file access
    with pytest.raises(duckdb.Error):
        db.con.execute("create table t as select 1")
    with pytest.raises(duckdb.Error):
        db.con.execute("select * from read_csv('data/raw/patients.csv')")


@needs_db
def test_uuid_backstop_catches_aliased_identifier():
    db = SafeDB(min_cell=1)
    with pytest.raises(GuardrailError, match="identifiers"):
        db.run("select age_group, max(patient_id) as pid from admissions group by age_group")


@needs_db
def test_db_timeout():
    db = SafeDB(timeout_s=0.2, min_cell=1)
    slow = ("select count(*) c from admissions a, admissions b, admissions c, admissions d "
            "where a.length_of_stay_days + b.length_of_stay_days > c.length_of_stay_days * d.age_at_admission")
    with pytest.raises(GuardrailError, match="timeout"):
        db.run(slow)


# ---- agent loop with a scripted fake client ----

def _resp(content, stop="tool_use"):
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=100, output_tokens=20))


def _tool(id_, name, **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


class FakeClient:
    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        return self.script.pop(0)


@needs_db
def test_agent_recovers_from_rejected_sql_and_answers():
    client = FakeClient([
        _resp([_tool("t1", "run_sql", sql="select patient_id from admissions")]),
        _resp([_tool("t2", "run_sql", sql="select count(*) as n_admissions from admissions")]),
        _resp([NS(type="text", text="There were many admissions.")], stop="end_turn"),
    ])
    r = run_agent("how many admissions?", SafeDB(min_cell=1), client)
    assert r.stop_reason == "end_turn" and r.steps == 3
    assert [c.ok for c in r.sql_calls] == [False, True]
    assert r.final_sql.rows[0][0] > 0
    # the rejection reached the model as an error tool_result, and results go back in one user message
    second_req_msgs = client.requests[1]["messages"]
    assert second_req_msgs[-1]["role"] == "user"
    assert second_req_msgs[-1]["content"][0]["is_error"] is True
    assert (r.input_tokens, r.output_tokens) == (300, 60)


@needs_db
def test_agent_step_cap_and_refusal():
    loop = [_resp([_tool(f"t{i}", "get_schema")]) for i in range(3)]
    r = run_agent("q", SafeDB(), FakeClient(loop), max_steps=3)
    assert r.stop_reason == "max_steps"
    r = run_agent("q", SafeDB(), FakeClient([_resp([], stop="refusal")]))
    assert r.stop_reason == "refusal"
