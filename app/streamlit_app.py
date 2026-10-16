"""Streamlit front end:  streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agent.agent import run_agent
from agent.db import SafeDB
from eval.run_eval import PRICES, cost

load_dotenv()
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]
EXAMPLES = [
    "What is the overall 30-day readmission rate?",
    "Which age group has the highest readmission rate?",
    "What percentage of patients have diabetes?",
    "Which 5 facilities have the most admissions?",
    "What is the average HbA1c of our diabetic patients?",  # not in the data: the agent should decline
]

st.set_page_config(page_title="Healthcare NL→SQL", page_icon="🏥", layout="centered")
st.title("Ask the hospital data")
st.caption("Natural-language questions → read-only SQL → answers. **Synthetic data only** (Synthea, Massachusetts). "
           "Aggregates only; counts under 11 are suppressed.")

with st.sidebar:
    model = st.selectbox("Model", MODELS, help="Haiku is ~17x cheaper; both scored similarly in the eval.")
    st.markdown("**Try one**")
    for ex in EXAMPLES:
        if st.button(ex, width="stretch"):
            st.session_state["q"] = ex
    st.divider()
    st.caption("Synthetic data: rates here are artifacts of the simulator (e.g. lung-cancer treatment cycles "
               "inflate readmissions) and are not real-world benchmarks.")


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


question = st.text_input("Question", key="q", placeholder="e.g. What was the readmission rate for heart failure?")
if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Writing and running SQL..."):
        try:
            res = run_agent(question.strip(), SafeDB(min_cell=11), get_client(), model=model)
        except anthropic.APIError as e:
            st.error(f"Model API error: {type(e).__name__}. Check ANTHROPIC_API_KEY in .env.")
            st.stop()
    st.markdown(res.answer)
    ok = res.final_sql
    if ok is not None:
        st.dataframe(pd.DataFrame(ok.rows, columns=ok.columns), hide_index=True, width="stretch")
    with st.expander(f"SQL ({len(res.sql_calls)} attempt{'s' if len(res.sql_calls) != 1 else ''})"):
        for i, c in enumerate(res.sql_calls, 1):
            st.markdown(f"**{i}. {'✅ ran' if c.ok else '⛔ rejected: ' + str(c.error)}**")
            st.code(c.sql, language="sql")
    st.caption(f"{res.steps} model calls · {res.input_tokens:,} in / {res.output_tokens:,} out tokens · "
               f"≈ ${cost(model, res.input_tokens, res.output_tokens):.4f} · {res.stop_reason}")
