"""Summarize eval runs:  python -m eval.report  ->  eval/results/summary.md"""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def fmt(k: int, n: int) -> str:
    if n == 0:
        return "-"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% (CI {100 * lo:.0f}-{100 * hi:.0f})"


def load(path: Path) -> list[dict]:
    latest = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["id"]] = r            # a later record for an id (a retry) replaces the earlier one
    return list(latest.values())


def summarize(label: str, recs: list[dict]) -> str:
    scored = [r for r in recs if r.get("passed") is not None]
    errs = len(recs) - len(scored)
    sql = [r for r in scored if r["kind"] == "sql"]
    lines = [f"## {label}", "",
             f"- Execution accuracy (answerable): **{fmt(sum(r['passed'] for r in sql), len(sql))}**"]
    for kind, name in (("decline", "Correctly declines unanswerable"), ("attack", "Resists privacy/safety probes")):
        rs = [r for r in scored if r["kind"] == kind]
        lines.append(f"- {name}: {fmt(sum(r['passed'] for r in rs), len(rs))}")
    tot_cost = sum(r.get("cost_usd", 0) + r.get("judge_cost_usd", 0) for r in scored)
    lines += [f"- Cost: ${tot_cost:.2f} total, ${tot_cost / max(len(scored), 1):.3f}/question; "
              f"mean steps {sum(r['steps'] for r in scored) / max(len(scored), 1):.1f}; "
              f"median latency {sorted(r['latency_s'] for r in scored)[len(scored) // 2] if scored else 0}s",
              f"- API errors excluded from scores: {errs}", ""]
    for dim in ("difficulty", "category"):
        groups = defaultdict(list)
        for r in sql:
            groups[r[dim]].append(r["passed"])
        lines += [f"| {dim} | accuracy |", "|---|---|"]
        lines += [f"| {g} | {fmt(sum(v), len(v))} |" for g, v in sorted(groups.items())]
        lines.append("")
    ft = Counter(r["failure_type"] for r in scored if not r["passed"])
    if ft:
        lines += ["Failure types: " + ", ".join(f"{k}={v}" for k, v in ft.most_common()), ""]
        lines += ["<details><summary>Failures</summary>", ""]
        for r in sorted((r for r in scored if not r["passed"]), key=lambda r: r["id"]):
            final = next((c["sql"] for c in reversed(r["sql_calls"]) if c["ok"]), "(none)")
            lines += [f"**{r['id']}** [{r['failure_type']}] {r['question']}",
                      f"- detail: {r.get('failure_detail') or r.get('judge', '')}"[:400],
                      f"- final SQL: `{' '.join(final.split())[:300]}`", ""]
        lines += ["</details>", ""]
    return "\n".join(lines)


def main() -> None:
    paths = sorted(p for p in RESULTS.glob("*.jsonl"))
    out = ["# Eval summary", "",
           "Execution accuracy compares result sets to hand-written gold SQL. CI = 95% Wilson interval; "
           "with this few questions, differences smaller than the interval width are not conclusive.", ""]
    out += [summarize(p.stem, load(p)) for p in paths]
    (RESULTS / "summary.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
