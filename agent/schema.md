# Analytic schema (DuckDB) and business definitions

All data is SYNTHETIC (Synthea, Massachusetts). Query only the tables below.

## Tables

**admissions** - one row per inpatient admission.
encounter_id, patient_id, organization_id (facility), payer_id, admit_ts, discharge_ts,
length_of_stay_days, age_at_admission, age_group ('0-17','18-44','45-64','65-79','80+'),
reason_code, principal_reason (text, SNOMED description, 'Unspecified' if missing),
icd10_code, icd10_description, icd10_category (3-character, e.g. 'I50'), icd10_chapter, icd10_match,
total_claim_cost, died_during_stay (bool).

**readmissions_30d** - one row per *index* admission that is eligible for readmission measurement
(admissions where the patient died in hospital are excluded).
encounter_id, patient_id, organization_id, admit_ts, discharge_ts, length_of_stay_days,
age_at_admission, age_group, principal_reason, reason_code, icd10_code, icd10_description,
icd10_category, icd10_chapter, icd10_match, total_claim_cost,
next_encounter_id, days_to_next_admit, readmitted_30d (bool).

**dim_patient** - patient_id, gender ('M'/'F'), race, ethnicity, state, county, income,
birth_date, death_date, is_deceased.

**dim_facility** - organization_id, facility_name, city, state.
Join: admissions.organization_id = dim_facility.organization_id.

**condition_groups** - one row per diagnosed disorder: patient_id, condition_code,
condition_description, onset_date, icd10_code, icd10_description, icd10_category, icd10_chapter,
icd10_match, chronic_group. chronic_group is one of 'Hypertension', 'Diabetes',
'Chronic kidney disease', 'Asthma', 'Heart failure', 'COPD', or NULL (not chronic-tracked). It is
derived from ICD-10 category: E08-E13 Diabetes, I10-I16 Hypertension, J43-J44 COPD, I50 Heart failure,
N18 Chronic kidney disease (includes end-stage renal disease), J45 Asthma.

**dim_icd10_crosswalk** - the SNOMED -> ICD-10-CM reference (no patient data): snomed_code,
icd10_code, icd10_description, icd10_category, icd10_chapter, match_type, confidence, note.

## ICD-10 (read this before answering any ICD-10 question)

- The source data is coded in SNOMED. **ICD-10-CM codes here are assigned by an analyst-built
  crosswalk (FY2027 code set), not original coding.** Say so when you report ICD-10 results.
- icd10_match says how faithful the mapping is: 'E' equivalent concept, 'B' the ICD-10 code is
  BROADER than the SNOMED concept (detail lost, e.g. lung cancer stage/histology), 'N' a default
  detail was assumed (laterality, encounter type), 'S' a status/encounter code (Z-codes such as
  Z95.1 'presence of bypass graft'). Roughly half of admissions are 'B' mappings.
- icd10_chapter values (exact strings): 'Neoplasms'; 'Diseases of the circulatory system';
  'Diseases of the respiratory system'; 'Diseases of the digestive system';
  'Diseases of the nervous system'; 'Endocrine, nutritional and metabolic diseases';
  'Mental, behavioral and neurodevelopmental disorders'; 'Pregnancy, childbirth and the puerperium';
  'Injury, poisoning and certain other consequences of external causes';
  'Factors influencing health status and contact with health services' (Z-codes);
  'Codes for special purposes' (U07.1 COVID-19); 'Symptoms, signs and abnormal clinical and
  laboratory findings, not elsewhere classified';
  'Congenital malformations, deformations and chromosomal abnormalities'; and others.
- Some SNOMED concepts have NO ICD-10-CM equivalent (icd10_code is NULL, match_type 'X').
- Only ICD-10-CM diagnosis codes exist. CPT/HCPCS procedure codes and ICD-10-PCS are NOT available.

## Definitions (use these exactly)

- **30-day readmission rate** = AVG(readmitted_30d::int) over readmissions_30d (or
  SUM(readmitted_30d::int) / COUNT(*)). Denominator is index admissions in readmissions_30d.
  A readmission = the same patient's next admission starts 0-30 days after discharge.
- **Group by diagnosis**: by ICD-10 use icd10_code / icd10_category / icd10_chapter; for the original
  clinical wording use principal_reason. Condition families can be matched with ILIKE on
  principal_reason, e.g. heart failure -> '%heart failure%'; lung cancer -> '%lung%'. Heart failure
  by ICD-10 is icd10_category = 'I50'.
- **Facility name** requires joining dim_facility.
- **Prevalence** of a chronic condition = COUNT(DISTINCT patient_id) in condition_groups with that
  chronic_group, divided by COUNT(*) in dim_patient.
- **Relative dates** ("last quarter", "last year", "recent") are relative to the latest admission in the
  data (see data_as_of from get_schema), NOT today's date. State the date range you used.
- Admissions span many decades; if the user gives no period, say you used all years.
- Cost = total_claim_cost (USD, per admission). There is no per-diagnosis charge table.

## Not available (say so instead of guessing)

Medications, labs, procedures and procedure codes (CPT/HCPCS/ICD-10-PCS), individual patient lookups,
outpatient/ER visits, real-world benchmarks. Individual patient or encounter IDs are never returned -
aggregates only.
