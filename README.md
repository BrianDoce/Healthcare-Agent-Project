# Healthcare Project

Synthetic-data healthcare analytics: a small data pipeline feeding (1) a natural-language-to-SQL agent and (2) a Power BI dashboard.

**Data:** [Synthea](https://synthetichealth.github.io/synthea/) synthetic patient records only. No real PHI.
Direct identifiers (names, SSN, addresses, etc.) are dropped at the staging layer and never reach the analytic tables.

## Pipeline

```
data/raw/*.csv -> raw_* (all-varchar) -> stg_* (typed, deduped, de-identified) -> marts -> exports/
```

| Stage | Where | What |
|---|---|---|
| Ingest | `pipeline/run.py` | Loads CSVs as text so bad values can't break the load |
| Staging | `sql/01_staging.sql` | Type casts (`try_cast`), dedupe, drop identifiers |
| Marts | `sql/02_marts.sql` | `admissions`, `readmissions_30d`, `dim_patient`, `dim_facility`, `condition_groups` |
| Data quality | `pipeline/run.py` | Printed report of duplicates, bad dates, orphans, excluded rows |
| Export | `pipeline/run.py` | Parquet + CSV in `exports/` for Power BI / Tableau |

**Readmission definition:** an index inpatient admission is "readmitted" if the same patient's next admission starts 0-30 days after discharge. Admissions ending in in-hospital death are excluded.

**Known simplification:** Synthea uses SNOMED codes, not ICD-10. Chronic-condition groups are assigned by description keyword.

## Run

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
# put Synthea CSVs in data/raw/
.venv\Scripts\python -m pipeline.run
.venv\Scripts\python -m pytest
```
