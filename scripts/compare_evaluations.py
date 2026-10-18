import argparse
import json
from pathlib import Path


def fmt(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def ratio(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator}"


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def decision_cell(stats: dict | None) -> str:
    if not stats:
        return "-"
    return (
        f"N={stats['n']}: refused {stats['refused_by_guardrail']}, "
        f"abstained {stats['abstained']}, answered {stats['answered']}"
    )


def render_comparison(dev: dict, test: dict) -> str:
    runs = {"dev": dev, "test": test}
    lines = ["# Dev vs. held-out test", ""]
    for name, results in runs.items():
        run = results["run"]
        lines.append(
            f"- {name}: `{run['dataset']}`, N = {run['n_cases']}, {run['date']}, "
            f"commit {run['commit']}, Groq calls generation {run['groq_calls']['generation']} "
            f"/ judge {run['groq_calls']['judge']}"
        )

    retrieval_metrics = ("recall_at_k", "precision_at_k", "mrr", "mrr_after_rerank")
    lines += ["", "## Retrieval (in_scope cases)", ""]
    lines += table(
        ["Metric", f"dev (N={dev['retrieval']['n']})", f"test (N={test['retrieval']['n']})"],
        [
            [metric, fmt(dev["retrieval"][metric]), fmt(test["retrieval"][metric])]
            for metric in retrieval_metrics
        ],
    )
    pairs = sorted(
        set(dev["retrieval"]["by_language_pair"]) | set(test["retrieval"]["by_language_pair"])
    )

    def pair_cell(results: dict, pair: str) -> str:
        stats = results["retrieval"]["by_language_pair"].get(pair)
        if not stats:
            return "-"
        return (
            f"N={stats['n']}: R@k {fmt(stats['recall_at_k'])}, MRR {fmt(stats['reciprocal_rank'])}"
        )

    lines += ["", "| Question -> document language | dev | test |", "|---|---|---|"]
    lines += [f"| {pair} | {pair_cell(dev, pair)} | {pair_cell(test, pair)} |" for pair in pairs]

    lines += ["", "## Decisions by category", ""]
    categories = sorted(
        set(dev["summary"]["decisions_by_category"]) | set(test["summary"]["decisions_by_category"])
    )
    lines += table(
        ["Category", "dev", "test"],
        [
            [
                category,
                decision_cell(dev["summary"]["decisions_by_category"].get(category)),
                decision_cell(test["summary"]["decisions_by_category"].get(category)),
            ]
            for category in categories
        ],
    )
    tags = sorted(
        set(dev["summary"].get("decisions_by_tag", {}))
        | set(test["summary"].get("decisions_by_tag", {}))
    )
    if tags:
        lines += ["", "## Decisions by tag", ""]
        lines += table(
            ["Tag", "dev", "test"],
            [
                [
                    tag,
                    decision_cell(dev["summary"].get("decisions_by_tag", {}).get(tag)),
                    decision_cell(test["summary"].get("decisions_by_tag", {}).get(tag)),
                ]
                for tag in tags
            ],
        )

    lines += ["", "## Refusal (in_scope + out_of_scope + injection_direct)", ""]
    rows = []
    for label, key in (
        ("guardrail only", "refusal_guardrail_only"),
        ("guardrail or LLM abstention", "refusal_end_to_end"),
    ):
        for name, results in runs.items():
            stats = results["summary"][key]
            rows.append(
                [
                    label,
                    name,
                    str(stats["n"]),
                    fmt(stats["precision"]),
                    fmt(stats["recall"]),
                    str(stats["true_refusals"]),
                    str(stats["false_refusals"]),
                    str(stats["missed_refusals"]),
                ]
            )
    lines += table(
        ["Refusal counted as", "Set", "N", "Precision", "Recall", "TP", "FP", "FN"], rows
    )

    def check_rows(results: dict) -> list[str]:
        summary = results["summary"]
        citations = summary["citations"]
        injection = summary["injection"]
        judge = summary["judge"]
        language = summary.get("answer_language", {})
        indirect_n = summary["decisions_by_category"].get("injection_indirect", {}).get("n", 0)
        return [
            ratio(citations["all_citations_in_context"], citations["n"]),
            ratio(injection["with_forbidden_string_leaked"], injection["n"]),
            ratio(injection["indirect_with_injection_in_context"], indirect_n),
            *(
                ratio(language[lang]["same_language"], language[lang]["n"])
                if lang in language
                else "n/a"
                for lang in ("pt", "en")
            ),
            f"N={judge['n']}: {fmt(judge['faithfulness_mean'])}",
            f"N={judge['n']}: {fmt(judge['relevance_mean'])}",
        ]

    check_names = [
        "Answers whose citations all exist in the context",
        "Injection cases with a forbidden string in the answer",
        "Indirect cases with the poisoned passage in the context",
        "Answers to PT questions written in PT",
        "Answers to EN questions written in EN",
        "LLM-as-a-judge faithfulness mean",
        "LLM-as-a-judge relevance mean",
    ]
    lines += ["", "## Deterministic checks and judge", ""]
    lines += table(
        ["Check", "dev", "test"],
        [
            [name, dev_value, test_value]
            for name, dev_value, test_value in zip(check_names, check_rows(dev), check_rows(test))
        ],
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara dois llm-eval-results.json (dev vs. test)"
    )
    parser.add_argument("dev", type=Path)
    parser.add_argument("test", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dev = json.loads(args.dev.read_text(encoding="utf-8"))
    test = json.loads(args.test.read_text(encoding="utf-8"))
    args.output.write_text(render_comparison(dev, test), encoding="utf-8")
    print(f"Escrito {args.output}")


if __name__ == "__main__":
    main()
