# LinkedIn post draft (edit freely; add a screenshot of the app)

I built a "ask the hospital data" agent, then spent more effort trying to break it than building it.

The question: can a manager ask readmission or chronic-disease questions in plain English and get answers they can trust, without the system leaking patient data or confidently making things up?

What I built (all on synthetic Synthea data, no real PHI):
- A SQL pipeline: raw patient records -> cleaned tables -> a 30-day readmission measure using window functions
- A Claude-powered agent that writes read-only SQL, with a "semantic layer" so it uses the right definition of a readmission
- Layered guardrails: SQL parsing, a read-only database with file access off, and a backstop that blocks any patient identifier from leaving
- A 68-question evaluation with hand-written gold SQL, plus an ICD-10-CM layer built from a hand-made, officially-validated crosswalk

What I measured:
- 86% (Haiku, strict scoring) on answerable questions after adding ICD-10; on the earlier SNOMED-only set Haiku and Sonnet scored 92% vs 90%: inside the noise, but Haiku is ~17x cheaper
- Both declined every question the data can't answer (ICD-10 codes, labs, national benchmarks) instead of inventing a number
- Most errors weren't bad SQL: they were the agent returning the top 5 when asked "which one"

Two things I'd tell anyone building this:
1. The eval is the project. A demo tells you it works once; 62 questions tell you where it doesn't. I even had to test my LLM judge with deliberately bad answers to make sure it could fail things.
2. Synthetic data lies in interesting ways: 75% of readmissions in my dataset trace back to lung-cancer treatment cycles. That's a simulator artifact, not a clinical finding, which is exactly why I wouldn't quote any rate from it.

Code, eval set, and write-up: [link]

#healthcareanalytics #SQL #python #llm #dataanalytics
