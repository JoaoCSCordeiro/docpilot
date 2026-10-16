# Judge calibration

- Judge: `openai/gpt-oss-20b`, rubric v1
- Evaluation run: 2026-10-16T21:13:35+01:00 (commit d2bdf48 (working tree with uncommitted changes))
- Sample: 10 judged answers, labelled blind by the project author. Selection: up to 5 hard cases (verdict not supported/relevant, or a forbidden string leaked into the answer), the rest drawn at random (seed 18).

| Criterion | Exact agreement | Binary agreement (positive vs. not) |
|---|---|---|
| faithfulness | 10/10 (100%) | 10/10 (100%) |
| relevance | 9/10 (90%) | 9/10 (90%) |

## Disagreements

| Case | Criterion | Judge | Human |
|---|---|---|---|
| 29 | relevance | relevant | partially_relevant |
