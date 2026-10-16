"""Natural-language -> SQL agent over the healthcare marts, using the Claude Messages API.

A manual tool-use loop (not the SDK tool runner) so every step, guardrail rejection, and
token count is captured for the eval harness.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from .db import SafeDB
from .guardrails import GuardrailError

SCHEMA_DOC = (Path(__file__).parent / "schema.md").read_text(encoding="utf-8")
DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """You are a healthcare analytics assistant answering questions about a synthetic \
hospital dataset by writing and running read-only SQL.

How to work:
- Call get_schema first if you are unsure about tables, columns, or definitions.
- Use run_sql to get numbers. Never state a figure you did not get from a query result.
- If a query is rejected or errors, read the message, fix the SQL, and retry.
- Follow the business definitions in the schema exactly (e.g. how readmission is defined).
- If the data cannot answer the question (missing table/field, ICD-10 codes, individual patients), say so \
plainly and explain what is available instead. Do not approximate with unrelated columns.
- If the question is ambiguous, state the interpretation you chose in one sentence and answer it.
- Results are aggregates only. Values shown as '<11' are suppressed small counts; mention that when it matters.
- Final answer: lead with the number or finding, then one or two sentences of context, then the date range \
or filters you used. Keep it short. The data is synthetic, so do not present rates as real-world benchmarks."""

TOOLS = [
    {
        "name": "get_schema",
        "description": "Return the table/column documentation, business definitions, and the date range "
                       "of the data. Takes no arguments.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_sql",
        "description": "Run ONE read-only DuckDB SELECT (CTEs allowed) against the analytic tables and "
                       "return up to 200 rows. Aggregates only: row-level identifiers cannot be returned.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single DuckDB SELECT statement."}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
]


@dataclass
class SqlCall:
    sql: str
    ok: bool
    error: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)


@dataclass
class AgentResult:
    answer: str
    sql_calls: list[SqlCall]
    steps: int
    stop_reason: str            # end_turn | refusal | max_steps | max_tokens
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def final_sql(self) -> SqlCall | None:
        ok = [c for c in self.sql_calls if c.ok]
        return ok[-1] if ok else None


def _format_result(res) -> str:
    payload = {"columns": res.columns, "rows": [list(r) for r in res.rows], "row_count": len(res.rows)}
    if res.truncated:
        payload["note"] = "Result truncated to the row limit."
    if res.suppressed_cells:
        payload["note_suppression"] = f"{res.suppressed_cells} small count(s) suppressed as '<11'."
    return json.dumps(payload, default=str)


def run_agent(question: str, db: SafeDB, client, model: str = DEFAULT_MODEL, max_steps: int = 8,
              effort: str = "medium", use_fallbacks: bool = False,
              schema_mode: str = "full") -> AgentResult:
    """Answer one question. `client` is an anthropic.Anthropic (or a test double).

    schema_mode: "full" gives the model schema.md (definitions + limits); "columns_only" gives just
    table/column names, for the semantic-layer ablation in the eval."""
    messages = [{"role": "user", "content": question}]
    calls: list[SqlCall] = []
    in_tok = out_tok = 0

    for step in range(1, max_steps + 1):
        kwargs = dict(model=model, max_tokens=16000, system=SYSTEM_PROMPT, tools=TOOLS,
                      messages=messages, output_config={"effort": effort})
        if use_fallbacks:  # Claude API only; routes policy refusals to a fallback model server-side
            resp = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        else:
            resp = client.messages.create(**kwargs)
        in_tok += resp.usage.input_tokens
        out_tok += resp.usage.output_tokens

        if resp.stop_reason == "refusal":
            return AgentResult("The request was declined by the model's safety system.", calls, step,
                               "refusal", in_tok, out_tok)
        if resp.stop_reason == "max_tokens":
            return AgentResult("The response was cut off before finishing.", calls, step,
                               "max_tokens", in_tok, out_tok)

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            return AgentResult(text, calls, step, "end_turn", in_tok, out_tok)

        messages.append({"role": "assistant", "content": resp.content})
        results = []  # all tool results go back in ONE user message
        for tu in tool_uses:
            results.append(_execute_tool(tu, db, calls, schema_mode))
        messages.append({"role": "user", "content": results})

    return AgentResult("I could not complete this within the step limit.", calls, max_steps,
                       "max_steps", in_tok, out_tok)


def _columns_only_doc(db: SafeDB) -> str:
    from .guardrails import ALLOWED_TABLES
    lines = []
    for t in sorted(ALLOWED_TABLES):
        cols = ", ".join(f"{r[0]} {r[1]}" for r in db.con.execute(f"describe {t}").fetchall())
        lines.append(f"{t}({cols})")
    return "Tables:\n" + "\n".join(lines)


def _execute_tool(tu, db: SafeDB, calls: list[SqlCall], schema_mode: str = "full") -> dict:
    if tu.name == "get_schema":
        info = db.data_as_of()
        doc = SCHEMA_DOC if schema_mode == "full" else _columns_only_doc(db)
        text = f"{doc}\n\ndata_as_of: first admission {info['first_admission']}, " \
               f"latest admission {info['last_admission']}"
        return {"type": "tool_result", "tool_use_id": tu.id, "content": text}
    if tu.name == "run_sql":
        sql = (tu.input or {}).get("sql", "")
        try:
            res = db.run(sql)
        except GuardrailError as e:
            calls.append(SqlCall(sql, False, str(e)))
            return {"type": "tool_result", "tool_use_id": tu.id, "content": f"REJECTED: {e}",
                    "is_error": True}
        calls.append(SqlCall(sql, True, None, res.columns, res.rows))
        return {"type": "tool_result", "tool_use_id": tu.id, "content": _format_result(res)}
    return {"type": "tool_result", "tool_use_id": tu.id, "content": f"Unknown tool {tu.name}",
            "is_error": True}
