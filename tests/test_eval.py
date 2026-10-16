from pathlib import Path

import duckdb
import pytest

from agent.db import DEFAULT_DB
from agent.guardrails import validate_sql
from eval.score import answer_grounded, compare, load_questions, safety_flags, score_sql_question

needs_db = pytest.mark.skipif(not Path(DEFAULT_DB).exists(), reason="run the pipeline first")
QS = load_questions()
SQL_QS = [q for q in QS if q["kind"] == "sql"]


def test_question_set_shape():
    kinds = {q["kind"] for q in QS}
    assert kinds == {"sql", "decline", "attack"}
    for q in QS:
        if q["kind"] == "sql":
            assert q["gold_sql"].strip()
        else:
            assert q["rubric"].strip() and "gold_sql" not in q


@needs_db
@pytest.mark.parametrize("q", SQL_QS, ids=[q["id"] for q in SQL_QS])
def test_gold_sql_is_runnable_nonempty_and_agent_reachable(q):
    validate_sql(q["gold_sql"])          # the agent is bound by the same guardrails, so gold must pass them
    con = duckdb.connect(str(DEFAULT_DB), read_only=True)
    rows = con.execute(q["gold_sql"]).fetchall()
    assert rows, "gold returned no rows"
    assert not any(v is None for r in rows for v in r), "gold contains NULLs (ambiguous target)"


def test_compare_accepts_equivalent_and_rejects_wrong():
    gold = [("A", 10, 21.5), ("B", 20, 30.0)]
    # different column names/order, extra column, shuffled rows, rounding -> pass
    assert compare(gold, ["x", "pct", "name", "extra"], [(30.0, 20, "B", 1), (21.52, 10, "A", 2)]).passed
    # wrong count by one -> fail (counts are exact)
    assert compare(gold, ["n", "p", "k"], [("A", 11, 21.5), ("B", 20, 30.0)]).failure_type == "missing_column"
    # right columns but swapped pairing across rows -> fail
    assert compare(gold, ["k", "n", "p"], [("A", 20, 21.5), ("B", 10, 30.0)]).failure_type == "value_mismatch"
    # wrong number of rows
    assert compare(gold, ["k", "n", "p"], [("A", 10, 21.5)]).failure_type == "row_count"
    # a rate off by a real amount -> fail
    assert not compare([(21.2,)], ["r"], [(25.0,)]).passed
    # a rate as a fraction instead of a percentage -> fail (scale is not silently forgiven)
    assert not compare([(21.2,)], ["r"], [(0.212,)]).passed


def test_compare_ordering_only_when_required():
    gold = [("A", 5), ("B", 3)]
    flipped = [("B", 3), ("A", 5)]
    assert compare(gold, ["k", "n"], flipped, ordered=False).passed
    assert not compare(gold, ["k", "n"], flipped, ordered=True).passed


def test_score_sql_question_failure_types():
    q = {"ordered": False}
    assert score_sql_question(q, [(1,)], {"sql_calls": []}).failure_type == "no_sql"
    err = {"sql_calls": [{"sql": "x", "ok": False, "error": "bad", "columns": [], "rows": []}]}
    assert score_sql_question(q, [(1,)], err).failure_type == "last_call_error"
    good = {"sql": "a", "ok": True, "error": None, "columns": ["n"], "rows": [[1]]}
    other = {"sql": "b", "ok": True, "error": None, "columns": ["n"], "rows": [[2]]}
    # an auxiliary query after the answering one does not hurt, if the answer states the gold value
    assert score_sql_question(q, [(1,)], {"sql_calls": [good, other], "answer": "The count is 1."}).passed
    # all queries wrong -> fail
    assert not score_sql_question(q, [(1,)], {"sql_calls": [other], "answer": "It is 2."}).passed
    # right query, but the answer states a different number -> ungrounded
    v = score_sql_question(q, [(1,)], {"sql_calls": [good], "answer": "The count is 2."})
    assert v.failure_type == "ungrounded_answer"


def test_answer_grounding_number_formats():
    assert answer_grounded([(5670,)], "There were 5,670 admissions.")
    assert answer_grounded([(21.23,)], "The rate is 21.2%.")
    assert answer_grounded([(165373089.47,)], "Total cost was about $165.4 million.")
    assert not answer_grounded([(21.23,)], "The rate is 25%.")
    assert not answer_grounded([(1182,)], "About 1,000 admissions.")
    assert not answer_grounded([(5000000.0,)], "Stays averaged 5 months.")   # "m" must be a standalone unit
    assert answer_grounded([(i, i * 1.5) for i in range(20)], "no numbers needed for big tables")


def test_safety_flags():
    assert safety_flags({"answer": "ok 12.5%"}) == []
    assert "uuid_in_answer" in safety_flags({"answer": "id cc3eac4a-34a7-9a15-1522-8087135631b7"})
    assert "ssn_like_in_answer" in safety_flags({"answer": "ssn 999-55-9547"})


def test_ignore_cols_allows_relabeling_but_not_wrong_values():
    gold = [(True, 22.4), (False, 20.7)]
    assert compare(gold, ["grp", "rate"], [("Diabetes", 22.4), ("No diabetes", 20.7)], ignore_cols=(0,)).passed
    assert not compare(gold, ["grp", "rate"], [("Diabetes", 22.4), ("No diabetes", 25.0)], ignore_cols=(0,)).passed
    assert not compare(gold, ["grp", "rate"], [("Diabetes", 22.4), ("No diabetes", 20.7)]).passed  # strict by default
