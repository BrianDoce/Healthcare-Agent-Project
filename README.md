# Ask the Hospital Data: a Natural-Language → SQL Agent for Healthcare Analytics

**Business question:** Can a non-technical analyst or manager get trustworthy answers about readmissions, utilization,
and chronic disease by asking in plain English, without being able to leak patient data or get a confident wrong
answer? And how would we *know*?

**What this is:** a small end-to-end system on synthetic hospital data: a SQL data pipeline, an LLM agent that writes
and runs read-only queries, layered privacy guardrails, an ICD-10-CM diagnosis layer, and a 68-question evaluation that
measures it.

**Data:** [Synthea](https://synthetichealth.github.io/synthea/) synthetic patients (5,733 patients, 5,670 inpatient
admissions, Massachusetts). No real PHI anywhere in this repository.

## Results

A question counts as correct only if a query returns the gold result set **and** the final answer states it (strict:
extra rows or a fraction where a percentage was asked fail, even when the answer text is right).

**Current (v2, with ICD-10 layer): 68 questions** = 57 answerable with hand-written gold SQL, 6 the data cannot answer,
5 privacy/injection probes. Haiku 5.5 only.

| Haiku 5.5, v2 | |
|---|---|
| Answerable questions correct | **49/57 = 86%** (95% CI 75-93) |
| Easy / medium / hard | 94% / 83% / 81% |
| ICD-10 questions (6) | 5/6 |
| Correctly declines unanswerable | 6/6 |
| Resists privacy / injection probes | 5/5 |
| Cost for all 68 questions | $0.07 |

**Earlier (v1, SNOMED only): 62 questions**, both models. Not directly comparable to v2 (different question set).

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Answerable questions correct | **47/51 = 92%** (95% CI 81-97) | **46/51 = 90%** (95% CI 79-96) |
| Easy / medium / hard | 100% / 86% / 92% | 100% / 82% / 92% |
| Declines unanswerable / resists probes | 6/6 / 5/5 | 6/6 / 5/5 |
| Cost for all 62 questions | $0.05 | $0.84 |

**Findings**
1. **Haiku and Sonnet were statistically indistinguishable in v1** (intervals overlap almost completely), but Haiku costs
   about 17x less. Sonnet was not re-run on v2, so that comparison has not been repeated.
2. **Most failures are strict-scoring misses, not wrong answers.** Across v1 the dominant failure (6 of 9) was returning
   the top 3-5 rows when asked "which one is highest?". Another (v1 h06, v2 e04) is a SQL result column holding a
   fraction (0.212) where a percentage was asked, while the answer *text* gave the correct percentage. Genuine errors exist
   too: for "most recent full quarter" (h05) Haiku sometimes answered with Q2 2026 instead of Q3 (it reasoned that
   April-June was the last full quarter before an October 11 cutoff).
3. **Adding the ICD-10 layer did not obviously help or hurt accuracy, but it costs more tokens.** On the 51 answerable
   questions common to both versions Haiku went 47 -> 44: three questions flipped pass -> fail (e04, h05, p01) and none
   flipped the other way. Three flips cannot be separated from run-to-run noise, but the direction is worth watching;
   a plausible cause is the larger schema document (mean input tokens per question rose 29%, 5,605 -> 7,223).
4. **It declines what it cannot know.** Asked for CPT procedure codes, medications, lab values, ED visits, insurer names,
   or a national benchmark, the models said the data does not contain them rather than inventing a number.
5. **Results vary run to run.** Across four runs Haiku answered the "most recent full quarter" question correctly twice
   and incorrectly twice. One run per configuration is a noisy estimate.

**Recommendation.** Deploy the Haiku configuration with the semantic layer, show the SQL beside every answer, and treat
ranking and relative-date questions ("top N", "last quarter") as the ones needing human review. A prompt change telling the
agent to return exactly the number of rows asked, in the units asked, would likely remove most observed failures; I have
not tested that.

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
                 │ drop identifiers    dim_patient/facility└─► eval harness (68 questions)
                 └ DQ report + exports condition_groups
```

### 1. Data pipeline (`pipeline/`, `sql/`)
Raw CSVs load as text so malformed values cannot break ingestion; staging casts types (bad values become NULL), removes
duplicates, and **drops direct identifiers (names, SSN, addresses) before anything downstream can see them.** A data-quality
report prints duplicates, unparseable dates, orphan records, and rows excluded from analysis. Marts include
`readmissions_30d`, computed with `LEAD()` over each patient's admissions. A readmission is a next admission 0-30 days after
discharge, and in-hospital deaths are excluded from the denominator (CMS-style). Parquet and CSV exports are written for BI tools.

### 1b. ICD-10-CM diagnosis layer (`reference/`)
Synthea only emits SNOMED, so ICD-10-CM is added through a **crosswalk I built by hand** for all 209 SNOMED concepts that
appear as admission reasons or conditions, mapped to 179 distinct ICD-10-CM (FY2027) codes. It is *not* an authoritative
map (NLM's official one requires a UMLS license) and is labelled "analyst-assigned" everywhere it surfaces.
- **Validated against the official CMS code list** (`reference/build_icd10_reference.py`): every code must exist and be a
  billable leaf. This caught 7 of my first-draft codes (invalid or non-billable headers). Validation proves a code *exists*,
  not that it is the *right* one; I also reviewed all 209 pairs by eye. A coder or clinician should review before any real use.
- **Each row says how faithful it is:** 128 equivalent, 48 broader than the SNOMED concept, 24 where I assumed a default
  detail (laterality, encounter), 6 status codes (Z-codes), 3 with no equivalent (spinal injuries need a vertebral level that
  SNOMED does not carry). 21 low-confidence rows each carry a note.
- **It matters for results:** 53% of admissions land on a "broader" mapping, mostly lung cancer, where ICD-10-CM codes the
  site (C34.90) but the SNOMED concept carried stage and histology. ICD-10 groupings are therefore coarser than the
  principal-reason text, and 22% of admissions are Z-code status/encounter reasons (e.g. "sterilization requested").
- Chronic-condition groups are now defined by ICD-10 category (E08-E13, I10-I16, I50, J43-J44, J45, N18) instead of keyword
  matching. Results were identical except chronic kidney disease (477 -> 481 patients), which now includes end-stage renal disease.
- The FY2027 code set is applied to encounters dating back to 1922, which is a simplification.

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
- Synthea is simulated: rates are not realistic, its native coding is SNOMED (ICD-10 here is my crosswalk, see 1b), and
  admissions span 1922-2026.
- 68 questions, one run per model, and v1/v2 question sets differ: wide confidence intervals; differences under ~10 points
  are inconclusive. Sonnet was not re-run on v2.
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
.venv\Scripts\python -m pytest                       # 111 tests, no API key needed
```

## Layout
`pipeline/` + `sql/` data pipeline · `agent/` agent, guardrails, semantic layer · `eval/` questions, scorer, runner, report ·
`app/` Streamlit UI · `tests/` · `scripts/` data generation · `exports/` BI-ready Parquet/CSV (git-ignored)
