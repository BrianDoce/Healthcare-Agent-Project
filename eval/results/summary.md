# Eval summary

Execution accuracy compares result sets to hand-written gold SQL. CI = 95% Wilson interval; with this few questions, differences smaller than the interval width are not conclusive.

## claude-haiku-5-5__full

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

## claude-sonnet-5-5__full

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
