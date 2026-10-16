# Analytic schema (DuckDB) and business definitions

All data is SYNTHETIC (Synthea, Massachusetts). Query only the tables below.

## Tables

**admissions** - one row per inpatient admission.
encounter_id, patient_id, organization_id (facility), payer_id, admit_ts, discharge_ts,
length_of_stay_days, age_at_admission, age_group ('0-17','18-44','45-64','65-79','80+'),
reason_code, principal_reason (text, SNOMED description, 'Unspecified' if missing),
total_claim_cost, died_during_stay (bool).

**readmissions_30d** - one row per *index* admission that is eligible for readmission measurement
(admissions where the patient died in hospital are excluded).
encounter_id, patient_id, organization_id, admit_ts, discharge_ts, length_of_stay_days,
age_at_admission, age_group, principal_reason, reason_code, total_claim_cost,
next_encounter_id, days_to_next_admit, readmitted_30d (bool).

**dim_patient** - patient_id, gender ('M'/'F'), race, ethnicity, state, county, income,
birth_date, death_date, is_deceased.

**dim_facility** - organization_id, facility_name, city, state.
Join: admissions.organization_id = dim_facility.organization_id.

**condition_groups** - one row per diagnosed disorder: patient_id, condition_code,
condition_description, onset_date, chronic_group. chronic_group is one of 'Hypertension',
'Diabetes', 'Chronic kidney disease', 'Asthma', 'Heart failure', 'COPD', or NULL (not chronic-tracked).

## Definitions (use these exactly)

- **30-day readmission rate** = AVG(readmitted_30d::int) over readmissions_30d (or
  SUM(readmitted_30d::int) / COUNT(*)). Denominator is index admissions in readmissions_30d.
  A readmission = the same patient's next admission starts 0-30 days after discharge.
- **Group by diagnosis** using principal_reason. Condition families are matched with ILIKE, e.g. heart
  failure -> principal_reason ILIKE '%heart failure%'; lung cancer -> '%lung%'.
  Diagnoses are SNOMED descriptions; there are NO ICD-10 codes in this dataset.
- **Facility name** requires joining dim_facility.
- **Prevalence** of a chronic condition = COUNT(DISTINCT patient_id) in condition_groups with that
  chronic_group, divided by COUNT(*) in dim_patient.
- **Relative dates** ("last quarter", "last year", "recent") are relative to the latest admission in the
  data (see data_as_of from get_schema), NOT today's date. State the date range you used.
- Admissions span many decades; if the user gives no period, say you used all years.
- Cost = total_claim_cost (USD, per admission). There is no per-diagnosis charge table.

## Not available (say so instead of guessing)

Medications, labs, procedures, ICD-10 codes, individual patient lookups, outpatient/ER visits,
real-world benchmarks. Individual patient or encounter IDs are never returned - aggregates only.
