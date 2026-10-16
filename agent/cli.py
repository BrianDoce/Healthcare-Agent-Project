"""Ask the agent a question:  python -m agent.cli "What was the readmission rate for heart failure?" """
import argparse

import anthropic

from .agent import DEFAULT_MODEL, run_agent
from .db import SafeDB


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--min-cell", type=int, default=11, help="suppress counts below this (1 = off)")
    args = ap.parse_args()

    result = run_agent(args.question, SafeDB(min_cell=args.min_cell), anthropic.Anthropic(),
                       model=args.model, effort=args.effort)
    for i, c in enumerate(result.sql_calls, 1):
        print(f"--- SQL {i} ({'ok' if c.ok else 'REJECTED: ' + str(c.error)}) ---\n{c.sql}\n")
    print(result.answer)
    print(f"\n[{result.stop_reason}; {result.steps} steps; {result.input_tokens} in / "
          f"{result.output_tokens} out tokens]")


if __name__ == "__main__":
    main()
