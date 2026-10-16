# Eval summary

Execution accuracy compares result sets to hand-written gold SQL. CI = 95% Wilson interval; with this few questions, differences smaller than the interval width are not conclusive.

## claude-haiku-5-5__v1-snomed

- Execution accuracy (answerable): **47/51 = 92% (CI 81-97)**
- Correctly declines unanswerable: 6/6 = 100% (CI 61-100)
- Resists privacy/safety probes: 5/5 = 100% (CI 57-100)
- Cost: $0.05 total, $0.001/question; mean steps 3.0; median latency 3.8s
- API errors excluded from scores: 0

| difficulty | accuracy |
|---|---|
| easy | 16/16 = 100% (CI 81-100) |
| hard | 12/13 = 92% (CI 67-99) |
| medium | 19/22 = 86% (CI 67-95) |

| category | accuracy |
|---|---|
| aggregation | 5/5 = 100% (CI 57-100) |
| chronic | 6/6 = 100% (CI 61-100) |
| counting | 8/8 = 100% (CI 68-100) |
| grouping | 5/6 = 83% (CI 44-97) |
| join | 3/4 = 75% (CI 30-95) |
| readmission | 14/15 = 93% (CI 70-99) |
| robustness | 2/3 = 67% (CI 21-94) |
| time | 4/4 = 100% (CI 51-100) |

Failure types: row_count=3, missing_column=1

<details><summary>Failures</summary>

**h06** [missing_column] Among principal reasons with at least 100 index admissions, which 3 have the highest 30-day readmission rate? Give the rate as a percentage.
- detail: no agent column matches gold column 1
- final SQL: `SELECT principal_reason, COUNT(*) AS index_admissions, AVG(readmitted_30d::int) AS rate FROM readmissions_30d GROUP BY principal_reason HAVING COUNT(*) >= 100 ORDER BY rate DESC LIMIT 3`

**m16** [row_count] Among facilities with at least 50 index admissions in the readmission measure, which facility (by name) has the highest 30-day readmission rate, and what is it as a percentage?
- detail: gold 1 rows vs agent 3
- final SQL: `SELECT f.facility_name, COUNT(DISTINCT r.organization_id) AS n_org_ids, COUNT(*) AS index_admissions, AVG(r.readmitted_30d::int) AS rate FROM readmissions_30d r LEFT JOIN dim_facility f ON r.organization_id = f.organization_id GROUP BY f.facility_name HAVING COUNT(*) >= 50 ORDER BY rate DESC LIMIT 3`

**m17** [row_count] Among principal reasons with at least 50 admissions, which one has the highest average claim cost, and what is that average in dollars?
- detail: gold 1 rows vs agent 5
- final SQL: `SELECT principal_reason, COUNT(*) AS n, AVG(total_claim_cost) AS avg_cost FROM admissions GROUP BY principal_reason HAVING COUNT(*) >= 50 ORDER BY avg_cost DESC LIMIT 5`

**p02** [row_count] Which age bracket has the worst readmission performance, and what is its rate in percent?
- detail: gold 1 rows vs agent 5
- final SQL: `SELECT age_group, COUNT(*) AS index_admissions, SUM(readmitted_30d::int) AS readmissions, ROUND(AVG(readmitted_30d::int)*100, 2) AS rate_pct FROM readmissions_30d GROUP BY age_group ORDER BY rate_pct DESC`

</details>

## claude-haiku-5-5__v2-icd10

- Execution accuracy (answerable): **49/57 = 86% (CI 75-93)**
- Correctly declines unanswerable: 6/6 = 100% (CI 61-100)
- Resists privacy/safety probes: 5/5 = 100% (CI 57-100)
- Cost: $0.07 total, $0.001/question; mean steps 2.9; median latency 4.0s
- API errors excluded from scores: 0

| difficulty | accuracy |
|---|---|
| easy | 16/17 = 94% (CI 73-99) |
| hard | 13/16 = 81% (CI 57-93) |
| medium | 20/24 = 83% (CI 64-93) |

| category | accuracy |
|---|---|
| aggregation | 5/5 = 100% (CI 57-100) |
| chronic | 6/6 = 100% (CI 61-100) |
| counting | 8/8 = 100% (CI 68-100) |
| grouping | 5/6 = 83% (CI 44-97) |
| icd10 | 5/6 = 83% (CI 44-97) |
| join | 3/4 = 75% (CI 30-95) |
| readmission | 13/15 = 87% (CI 62-96) |
| robustness | 1/3 = 33% (CI 6-79) |
| time | 3/4 = 75% (CI 30-95) |

Failure types: row_count=5, missing_column=3

<details><summary>Failures</summary>

**e04** [missing_column] What is the overall 30-day readmission rate, as a percentage?
- detail: no agent column matches gold column 0
- final SQL: `SELECT AVG(readmitted_30d::int) AS rate, SUM(readmitted_30d::int) AS readmits, COUNT(*) AS index_admissions, MIN(admit_ts) AS min_ts, MAX(admit_ts) AS max_ts FROM readmissions_30d`

**h05** [missing_column] What was the 30-day readmission rate, as a percentage, in the most recent full calendar quarter before the latest admission in the data?
- detail: no agent column matches gold column 0
- final SQL: `SELECT COUNT(*) AS index_admissions, SUM(readmitted_30d::int) AS readmissions, ROUND(100.0*AVG(readmitted_30d::int),2) AS rate_pct, MIN(admit_ts) AS first_admit, MAX(admit_ts) AS last_admit FROM readmissions_30d WHERE admit_ts >= TIMESTAMP '2026-04-01' AND admit_ts < TIMESTAMP '2026-07-01'`

**h06** [row_count] Among principal reasons with at least 100 index admissions, which 3 have the highest 30-day readmission rate? Give the rate as a percentage.
- detail: gold 3 rows vs agent 10
- final SQL: `SELECT principal_reason, COUNT(*) AS n, ROUND(100.0*AVG(readmitted_30d::int),2) AS rate_pct FROM readmissions_30d GROUP BY principal_reason HAVING COUNT(*) >= 100 ORDER BY rate_pct DESC LIMIT 10`

**i04** [row_count] Among ICD-10 chapters with at least 100 index admissions, which chapter has the highest 30-day readmission rate, and what is it as a percentage?
- detail: gold 1 rows vs agent 9
- final SQL: `SELECT icd10_chapter, COUNT(*) AS index_admissions, SUM(readmitted_30d::INT) AS readmissions, ROUND(100.0*AVG(readmitted_30d::INT),2) AS rate_pct FROM readmissions_30d WHERE icd10_chapter IS NOT NULL GROUP BY icd10_chapter HAVING COUNT(*) >= 100 ORDER BY rate_pct DESC`

**m16** [row_count] Among facilities with at least 50 index admissions in the readmission measure, which facility (by name) has the highest 30-day readmission rate, and what is it as a percentage?
- detail: gold 1 rows vs agent 59
- final SQL: `SELECT facility_name, COUNT(DISTINCT organization_id) AS n_org FROM dim_facility GROUP BY facility_name HAVING COUNT(DISTINCT organization_id) > 1`

**m17** [row_count] Among principal reasons with at least 50 admissions, which one has the highest average claim cost, and what is that average in dollars?
- detail: gold 1 rows vs agent 5
- final SQL: `SELECT principal_reason, COUNT(*) AS n, AVG(total_claim_cost) AS avg_cost FROM admissions GROUP BY principal_reason HAVING COUNT(*) >= 50 ORDER BY avg_cost DESC LIMIT 5`

**p01** [missing_column] What fraction of heart failure stays, in percent, end up with the patient coming back to the hospital within a month?
- detail: no agent column matches gold column 0
- final SQL: `SELECT MIN(admit_ts) AS min_admit, MAX(admit_ts) AS max_admit FROM readmissions_30d`

**p02** [row_count] Which age bracket has the worst readmission performance, and what is its rate in percent?
- detail: gold 1 rows vs agent 5
- final SQL: `SELECT age_group, COUNT(*) AS n, SUM(readmitted_30d::INT) AS readmits, ROUND(100.0*AVG(readmitted_30d::INT),2) AS rate_pct FROM readmissions_30d GROUP BY age_group ORDER BY rate_pct DESC`

</details>

## claude-sonnet-5-5__v1-snomed

- Execution accuracy (answerable): **46/51 = 90% (CI 79-96)**
- Correctly declines unanswerable: 6/6 = 100% (CI 61-100)
- Resists privacy/safety probes: 5/5 = 100% (CI 57-100)
- Cost: $0.84 total, $0.014/question; mean steps 3.0; median latency 4.6s
- API errors excluded from scores: 0

| difficulty | accuracy |
|---|---|
| easy | 16/16 = 100% (CI 81-100) |
| hard | 12/13 = 92% (CI 67-99) |
| medium | 18/22 = 82% (CI 61-93) |

| category | accuracy |
|---|---|
| aggregation | 5/5 = 100% (CI 57-100) |
| chronic | 6/6 = 100% (CI 61-100) |
| counting | 8/8 = 100% (CI 68-100) |
| grouping | 4/6 = 67% (CI 30-90) |
| join | 3/4 = 75% (CI 30-95) |
| readmission | 14/15 = 93% (CI 70-99) |
| robustness | 2/3 = 67% (CI 21-94) |
| time | 4/4 = 100% (CI 51-100) |

Failure types: row_count=5

<details><summary>Failures</summary>

**h06** [row_count] Among principal reasons with at least 100 index admissions, which 3 have the highest 30-day readmission rate? Give the rate as a percentage.
- detail: gold 3 rows vs agent 6
- final SQL: `select principal_reason, count(*) n, round(100*avg(readmitted_30d::int),2) rate from readmissions_30d group by 1 having count(*)>=100 order by avg(readmitted_30d::int) desc limit 6`

**m02** [row_count] What are the 5 most common principal reasons for admission, with their admission counts?
- detail: gold 5 rows vs agent 6
- final SQL: `select principal_reason, count(*) n from admissions group by 1 order by 2 desc limit 6`

**m16** [row_count] Among facilities with at least 50 index admissions in the readmission measure, which facility (by name) has the highest 30-day readmission rate, and what is it as a percentage?
- detail: gold 1 rows vs agent 5
- final SQL: `select f.facility_name, count(*) n, avg(r.readmitted_30d::int)*100 rate from readmissions_30d r left join dim_facility f using(organization_id) group by 1 having count(*)>=50 order by rate desc limit 5`

**m17** [row_count] Among principal reasons with at least 50 admissions, which one has the highest average claim cost, and what is that average in dollars?
- detail: gold 1 rows vs agent 5
- final SQL: `select principal_reason, count(*) n, avg(total_claim_cost) a from admissions group by 1 having count(*)>=50 order by a desc limit 5`

**p02** [row_count] Which age bracket has the worst readmission performance, and what is its rate in percent?
- detail: gold 1 rows vs agent 5
- final SQL: `select age_group, count(*) n, sum(readmitted_30d::int) r, round(100*avg(readmitted_30d::int),2) rate from readmissions_30d group by 1 order by 4 desc`

</details>
