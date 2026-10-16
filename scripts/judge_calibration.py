import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation.dataset import EVALUATION_DIR  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = REPO_ROOT / "docs" / "evaluation" / "llm-eval-results.json"
SHEET_PATH = REPO_ROOT / "docs" / "evaluation" / "judge-calibration-sheet.md"
REPORT_PATH = REPO_ROOT / "docs" / "evaluation" / "judge-calibration.md"
LABELS_PATH = EVALUATION_DIR / "judge_calibration_labels.json"
SAMPLE_SIZE = 10
MAX_HARD_CASES = 5
SAMPLE_SEED = 18
CRITERIA = ("faithfulness", "relevance")
POSITIVE_LABELS = {"faithfulness": "supported", "relevance": "relevant"}


def judged_cases(results: dict) -> list[dict]:
    return [case for case in results["cases"] if "judge" in case and "error" not in case["judge"]]


def is_hard_case(case: dict) -> bool:
    non_positive_verdict = any(case["judge"][c] != POSITIVE_LABELS[c] for c in CRITERIA)
    return non_positive_verdict or bool(case.get("leaked_strings"))


def select_sample(cases: list[dict]) -> list[dict]:
    # Uma amostra so aleatoria teria quase so veredictos positivos e diria pouco sobre
    # os casos dificeis; entram primeiro os veredictos nao positivos e as respostas que
    # falharam uma verificacao deterministica (fuga de injecao).
    hard = [case for case in cases if is_hard_case(case)][:MAX_HARD_CASES]
    remaining = [case for case in cases if case not in hard]
    fill = random.Random(SAMPLE_SEED).sample(
        remaining, min(SAMPLE_SIZE - len(hard), len(remaining))
    )
    return sorted(hard + fill, key=lambda case: case["id"])


def write_sheet(sample: list[dict]) -> None:
    lines = [
        "# Judge calibration sheet",
        "",
        "Blind review: the judge's verdicts are not shown. For each case, label",
        "faithfulness (supported / partially_supported / unsupported, against the context",
        "only) and relevance (relevant / partially_relevant / irrelevant).",
        "",
    ]
    for case in sample:
        lines += [f"## Case {case['id']} ({case['category']}, {case['language']})", ""]
        lines += [f"**Question:** {case['question']}", "", "**Context:**", ""]
        for chunk in case["context"]:
            text = " ".join(chunk["text"].split())
            lines.append(f"- `[{chunk['source']}]` {text}")
        lines += ["", "**Answer:**", "", case["answer"].strip(), ""]
    SHEET_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not LABELS_PATH.exists():
        template = [{"id": case["id"], "faithfulness": None, "relevance": None} for case in sample]
        LABELS_PATH.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")


def agreement_report(results: dict, labels: list[dict]) -> str:
    by_id = {case["id"]: case for case in results["cases"]}
    lines = [
        "# Judge calibration",
        "",
        f"- Judge: `{results['run']['judge_model']}`, rubric "
        f"{results['run']['judge_prompt_version']}",
        f"- Evaluation run: {results['run']['date']} (commit {results['run']['commit']})",
        f"- Sample: {len(labels)} judged answers, labelled blind by the project author. "
        f"Selection: up to {MAX_HARD_CASES} hard cases (verdict not supported/relevant, "
        f"or a forbidden string leaked into the answer), the rest drawn at random "
        f"(seed {SAMPLE_SEED}).",
        "",
        "| Criterion | Exact agreement | Binary agreement (positive vs. not) |",
        "|---|---|---|",
    ]
    disagreements = []
    for criterion in CRITERIA:
        exact = binary = 0
        for label in labels:
            judge_label = by_id[label["id"]]["judge"][criterion]
            human_label = label[criterion]
            exact += judge_label == human_label
            positive = POSITIVE_LABELS[criterion]
            binary += (judge_label == positive) == (human_label == positive)
            if judge_label != human_label:
                disagreements.append((label["id"], criterion, judge_label, human_label))
        n = len(labels)
        lines.append(
            f"| {criterion} | {exact}/{n} ({exact / n:.0%}) | {binary}/{n} ({binary / n:.0%}) |"
        )
    lines += ["", "## Disagreements", ""]
    if not disagreements:
        lines.append("None.")
    else:
        lines += ["| Case | Criterion | Judge | Human |", "|---|---|---|---|"]
        lines += [f"| {d[0]} | {d[1]} | {d[2]} | {d[3]} |" for d in disagreements]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibracao do juiz LLM")
    parser.add_argument("command", choices=["sheet", "agreement"])
    args = parser.parse_args()

    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    if args.command == "sheet":
        sample = select_sample(judged_cases(results))
        write_sheet(sample)
        print(f"Folha com {len(sample)} casos: {SHEET_PATH.relative_to(REPO_ROOT)}")
        print(f"Etiquetas a preencher: {LABELS_PATH.relative_to(REPO_ROOT)}")
        return

    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    missing = [
        label["id"] for label in labels if None in (label["faithfulness"], label["relevance"])
    ]
    if missing:
        sys.exit(f"Etiquetas por preencher nos casos {missing}")
    report = agreement_report(results, labels)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
