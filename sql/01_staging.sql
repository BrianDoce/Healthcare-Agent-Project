-- Staging: type-cast, dedupe, and drop direct identifiers (name, SSN, address, etc.).
-- Raw tables are all-varchar so messy values never break the load; try_cast turns bad values into NULL.

create or replace table stg_patients as
select
    Id                                   as patient_id,
    try_cast(BIRTHDATE as date)          as birth_date,
    try_cast(DEATHDATE as date)          as death_date,
    nullif(trim(GENDER), '')             as gender,
    nullif(trim(RACE), '')               as race,
    nullif(trim(ETHNICITY), '')          as ethnicity,
    nullif(trim(STATE), '')              as state,
    nullif(trim(COUNTY), '')             as county,
    try_cast(INCOME as integer)          as income
from raw_patients
qualify row_number() over (partition by Id order by BIRTHDATE) = 1;

create or replace table stg_organizations as
select
    Id                          as organization_id,
    trim(NAME)                  as facility_name,
    nullif(trim(CITY), '')      as city,
    nullif(trim(STATE), '')     as state
from raw_organizations
qualify row_number() over (partition by Id order by NAME) = 1;

create or replace table stg_payers as
select Id as payer_id, trim(NAME) as payer_name
from raw_payers
qualify row_number() over (partition by Id order by NAME) = 1;

create or replace table stg_encounters as
select
    Id                                                        as encounter_id,
    try_cast(START as timestamptz) at time zone 'UTC'         as start_ts,
    try_cast(STOP  as timestamptz) at time zone 'UTC'         as stop_ts,
    PATIENT                                                   as patient_id,
    ORGANIZATION                                              as organization_id,
    PAYER                                                     as payer_id,
    lower(trim(ENCOUNTERCLASS))                               as encounter_class,
    CODE                                                      as encounter_code,
    DESCRIPTION                                               as encounter_description,
    try_cast(TOTAL_CLAIM_COST as decimal(12,2))               as total_claim_cost,
    try_cast(PAYER_COVERAGE as decimal(12,2))                 as payer_coverage,
    nullif(REASONCODE, '')                                    as reason_code,
    nullif(REASONDESCRIPTION, '')                             as reason_description
from raw_encounters
qualify row_number() over (partition by Id order by START) = 1;

create or replace table stg_conditions as
select
    try_cast(START as date)     as onset_date,
    try_cast(STOP as date)      as resolved_date,
    PATIENT                     as patient_id,
    ENCOUNTER                   as encounter_id,
    CODE                        as condition_code,
    SYSTEM                      as code_system,
    DESCRIPTION                 as condition_description
from raw_conditions;
