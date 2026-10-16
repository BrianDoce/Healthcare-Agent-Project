-- Analytic layer: this is what the dashboard and the NL->SQL agent query.

create or replace table dim_patient as
select
    patient_id, gender, race, ethnicity, state, county, income, birth_date, death_date,
    death_date is not null as is_deceased
from stg_patients;

create or replace table dim_facility as
select organization_id, facility_name, city, state from stg_organizations;

-- One row per inpatient admission. Rows with a missing or inverted stay window are excluded here
-- and counted in the data-quality report instead of silently distorting length of stay.
create or replace table admissions as
select
    e.encounter_id,
    e.patient_id,
    e.organization_id,
    e.payer_id,
    e.start_ts                                              as admit_ts,
    e.stop_ts                                               as discharge_ts,
    date_diff('day', e.start_ts::date, e.stop_ts::date)     as length_of_stay_days,
    date_diff('year', p.birth_date, e.start_ts::date)       as age_at_admission,
    case
        when date_diff('year', p.birth_date, e.start_ts::date) < 18 then '0-17'
        when date_diff('year', p.birth_date, e.start_ts::date) < 45 then '18-44'
        when date_diff('year', p.birth_date, e.start_ts::date) < 65 then '45-64'
        when date_diff('year', p.birth_date, e.start_ts::date) < 80 then '65-79'
        else '80+'
    end                                                     as age_group,
    e.reason_code,
    coalesce(e.reason_description, 'Unspecified')           as principal_reason,
    e.total_claim_cost,
    (p.death_date is not null
        and p.death_date between e.start_ts::date and e.stop_ts::date) as died_during_stay
from stg_encounters e
join stg_patients p using (patient_id)
where e.encounter_class = 'inpatient'
  and e.start_ts is not null
  and e.stop_ts is not null
  and e.stop_ts >= e.start_ts;

-- Readmission logic: look at each patient's next admission (LEAD). The index admission is
-- "readmitted" if the next admission starts 0-30 days after the index discharge.
-- Index admissions where the patient died in hospital are not eligible (CMS-style exclusion).
create or replace table readmissions_30d as
with sequenced as (
    select
        a.*,
        lead(admit_ts) over w as next_admit_ts,
        lead(encounter_id) over w as next_encounter_id
    from admissions a
    window w as (partition by patient_id order by admit_ts)
)
select
    encounter_id, patient_id, organization_id, admit_ts, discharge_ts, length_of_stay_days,
    age_at_admission, age_group, principal_reason, reason_code, total_claim_cost,
    next_encounter_id,
    date_diff('day', discharge_ts::date, next_admit_ts::date) as days_to_next_admit,
    coalesce(date_diff('day', discharge_ts::date, next_admit_ts::date) between 0 and 30, false)
                                                              as readmitted_30d
from sequenced
where not died_during_stay;

-- Chronic-condition flag for the prevalence dashboard. Synthea codes conditions in SNOMED, so
-- groups are assigned by description keyword; documented as a simplification in the README.
create or replace table condition_groups as
select
    c.patient_id, c.condition_code, c.condition_description, c.onset_date,
    case
        when condition_description ilike '%diabetes%'                           then 'Diabetes'
        when condition_description ilike '%hypertension%'                       then 'Hypertension'
        when condition_description ilike '%COPD%'
          or condition_description ilike '%chronic obstructive%'
          or condition_description ilike '%emphysema%'                          then 'COPD'
        when condition_description ilike '%heart failure%'                      then 'Heart failure'
        when condition_description ilike '%chronic kidney%'                     then 'Chronic kidney disease'
        when condition_description ilike '%asthma%'                             then 'Asthma'
    end as chronic_group
from stg_conditions c
where condition_description ilike '%(disorder)%';
