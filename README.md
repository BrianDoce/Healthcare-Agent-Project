# Ask the Hospital Data: a Natural-Language → SQL Agent for Healthcare Analytics

**Business question:** Can a non-technical analyst or manager get trustworthy answers about readmissions, utilization,
and chronic disease by asking in plain English, without being able to leak patient data or get a confident wrong
answer? And how would we *know*?

**What this is:** a small end-to-end system on synthetic hospital data: a SQL data pipeline, an LLM agent that writes
and runs read-only queries, layered privacy guardrails, and a 62-question evaluation that measures it.

**Data:** [Synthea](https://synthetichealth.github.io/synthea/) synthetic patients (5,733 patients, 5,670 inpatient
admissions, Massachusetts). No real PHI anywhere in this repository.

## Results

Evaluated on 62 questions (51 answerable with hand-written gold SQL, 6 the data cannot answer, 5 privacy/injection
probes). A question counts as correct only if a query returns the gold result **and** the final answer states it.

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Answerable questions correct | **47/51 = 92%** (95% CI 81-97) | **46/51 = 90%** (95% CI 79-96) |
| Easy / medium / hard | 100% / 86% / 92% | 100% / 82% / 92% |
| Correctly declines unanswerable | 6/6 | 6/6 |
| Resists privacy / injection probes | 5/5 | 5/5 |
| Cost for all 62 questions | $0.05 | $0.84 |

**Findings**
1. **The two models are statistically indistinguishable here** (intervals overlap almost completely), but Haiku costs
   about 17x less. For this workload the cheap model is the sensible default.
2. **Easy questions are solved; the remaining errors are mostly about question *interpretation*, not SQL.** 6 of the 9
   total failures are the agent returning the top 3-5 rows when asked "which one is highest?". 1 is a rate reported as a
   fraction instead of a percentage (h06, Haiku). The remaining 2 (Sonnet's `limit 6` on "top 5" and "top 3" questions)
   I did not diagnose.
3. **It declines what it cannot know.** Asked for ICD-10 codes, medications, lab values, ED visits, insurer names, or a
   national benchmark, both models said the data does not contain them rather than inventing a number.
4. **Results vary run to run.** During development the same model answered the "most recent full quarter" question
   correctly once and incorrectly once (it picked the wrong quarter). One run per configuration is a noisy estimate.

**Recommendation.** Deploy the Haiku configuration with the semantic layer, show the SQL beside every answer, and treat
ranking and relative-date questions ("top N", "last quarter") as the ones needing human review. A prompt change telling the
agent to return exactly the number of rows asked would likely remove most observed failures; I have not tested that.

### What the synthetic data shows (and why not to trust it as real)
30-day readmission rate is **21.2%** (1,182 of 5,568 eligible admissions); 45-64 year olds 30.0%, 65-79 28.7%,
18-44 just 1.2%. But **74.5% of all readmissions follow a lung-cancer admission**, and small-cell lung cancer alone
readmits at 87.9%: the simulator models repeated inpatient treatment cycles as admissions. These are artifacts of Synthea,
not clinical insight, and must not be read as benchmarks. Measuring a method on data like this is fine; drawing
conclusions about hospitals from it is not.

## How it works

```
Synthea CSVs ─► pipeline (DuckDB) ─► analytic tables ─► NL→SQL agent ─► Streamlit app
                 │ ingest as text      admissions          │ get_schema      ▲
                 │ stg_*: type, dedupe readmissions_30d    │ run_sql ──► guardrails ─► read-only DB
                 │ drop identifiers    dim_patient/facility└─► eval harness (62 questions)
                 └ DQ report + exports condition_groups
```

### 1. Data pipeline (`pipeline/`, `sql/`)
Raw CSVs load as text so malformed values cannot break ingestion; staging casts types (bad values become NULL), removes
duplicates, and **drops direct identifiers (names, SSN, addresses) before anything downstream can see them.** A data-quality
report prints duplicates, unparseable dates, orphan records, and rows excluded from analysis. Marts include
`readmissions_30d`, computed with `LEAD()` over each patient's admissions. A readmission is a next admission 0-30 days after
discharge, and in-hospital deaths are excluded from the denominator (CMS-style). Parquet and CSV exports are written for BI tools.

### 2. The agent (`agent/`)
A manual tool-use loop on the Claude API with two tools (`get_schema`, `run_sql`). A **semantic layer** (`agent/schema.md`)
defines the business terms ("readmission", how relative dates work, what is *not* available) so the model does not guess.
Rejected queries return the reason to the model, which retries. Every attempt is logged for evaluation.

### 3. Guardrails (`agent/guardrails.py`, `agent/db.py`)
Defense in depth, so no single layer is trusted:
- SQL parsed to an AST; single `SELECT` only; table allow-list; no file/URL functions; no row-level identifier columns
  (checked through CTEs and subqueries).
- Database opened **read-only with external file access disabled at the engine level**, so even a validator bypass cannot
  write or read files. 
- Row limit, query timeout, a **result-level backstop** rejecting any UUID-shaped value however the SQL produced it, and
  small-count suppression (<11).

Adversarial tests cover DROP, multi-statement injection, file readers, identifier leaks via aliases/CTEs, and runaway queries.

### 4. Evaluation (`eval/`)
Gold-SQL execution accuracy (column order/names ignored, rounding tolerated, counts exact), an answer-grounding check, and an
LLM judge for decline/attack questions. **The judge itself was validated** with 14 hand-written good/bad answers: 0 errors.

## Privacy and HIPAA awareness
- Synthetic data only; no PHI is used, stored, or sent to a model provider.
- Aggregate-only outputs by design: identifiers are blocked statically, at the engine, and at the result.
- **What a real deployment would still need** (none of which this demo claims): a BAA with the model provider, role-based
  access and audit logging, minimum-necessary review of query results, re-identification risk review beyond a simple
  small-cell rule, and de-identified or access-controlled data. Small-cell suppression here is a heuristic on column names,
  not a formal disclosure-control method.

## Limitations
- Synthea is simulated: rates are not realistic, uses SNOMED rather than ICD-10 (chronic groups are keyword-matched), and
  admissions span 1922-2026.
- 62 questions, one run per model: wide confidence intervals; differences under ~10 points are inconclusive.
- Four questions ignore label columns in scoring, so a label swap would go undetected.
- Small-cell suppression is disabled during evaluation so small groups stay comparable to gold (it is unit-tested separately).
- Models are nondeterministic; results will vary slightly on re-run.
- Not run: Opus, and an ablation of the semantic layer (`--schema-mode columns_only` is implemented).

## Run it
```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
# Generate data (needs Java 17+) or place Synthea CSVs in data/raw/:  scripts\generate_data.ps1
.venv\Scripts\python -m pipeline.run                 # build DuckDB + exports
echo ANTHROPIC_API_KEY=... > .env                    # git-ignored
.venv\Scripts\streamlit run app\streamlit_app.py     # the app
.venv\Scripts\python -m agent.cli "What is the readmission rate for heart failure?"
.venv\Scripts\python -m eval.run_eval --model claude-haiku-5-5 --dry-run   # then without --dry-run
.venv\Scripts\python -m eval.report                  # eval/results/summary.md
.venv\Scripts\python -m pytest                       # 97 tests, no API key needed
```

## Layout
`pipeline/` + `sql/` data pipeline · `agent/` agent, guardrails, semantic layer · `eval/` questions, scorer, runner, report ·
`app/` Streamlit UI · `tests/` · `scripts/` data generation · `exports/` BI-ready Parquet/CSV (git-ignored)
