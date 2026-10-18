# Dev vs. held-out test

- dev: `data/evaluation/qa_dataset_v2.json`, N = 58, 2026-10-18T19:27:55+01:00, commit c56ddbe, Groq calls generation 0 / judge 0
- test: `data/evaluation/qa_dataset_test.json`, N = 30, 2026-10-18T19:42:42+01:00, commit c56ddbe, Groq calls generation 25 / judge 16

## Retrieval (in_scope cases)

| Metric | dev (N=40) | test (N=18) |
|---|---|---|
| recall_at_k | 1.0000 | 1.0000 |
| precision_at_k | 0.7650 | 0.8000 |
| mrr | 0.9625 | 0.9722 |
| mrr_after_rerank | 1.0000 | 1.0000 |

| Question -> document language | dev | test |
|---|---|---|
| en->en | N=9: R@k 1.0000, MRR 1.0000 | N=3: R@k 1.0000, MRR 1.0000 |
| en->pt | N=6: R@k 1.0000, MRR 1.0000 | N=4: R@k 1.0000, MRR 1.0000 |
| pt->en | N=14: R@k 1.0000, MRR 0.8929 | N=7: R@k 1.0000, MRR 0.9286 |
| pt->pt | N=11: R@k 1.0000, MRR 1.0000 | N=4: R@k 1.0000, MRR 1.0000 |

## Decisions by category

| Category | dev | test |
|---|---|---|
| in_scope | N=40: refused 2, abstained 4, answered 34 | N=18: refused 1, abstained 4, answered 13 |
| injection_direct | N=5: refused 3, abstained 0, answered 2 | N=3: refused 3, abstained 0, answered 0 |
| injection_indirect | N=5: refused 0, abstained 0, answered 5 | N=3: refused 0, abstained 0, answered 3 |
| out_of_scope | N=8: refused 6, abstained 2, answered 0 | N=6: refused 1, abstained 5, answered 0 |

## Decisions by tag

| Tag | dev | test |
|---|---|---|
| code_comment | - | N=1: refused 0, abstained 0, answered 1 |
| fake_advisory | - | N=1: refused 0, abstained 0, answered 1 |
| fake_system_message | - | N=1: refused 1, abstained 0, answered 0 |
| hard_negative | N=4: refused 2, abstained 2, answered 0 | N=6: refused 1, abstained 5, answered 0 |
| maintainer_note | - | N=1: refused 0, abstained 0, answered 1 |
| new_fact | - | N=10: refused 1, abstained 2, answered 7 |
| paraphrase | - | N=8: refused 0, abstained 2, answered 6 |
| role_play | - | N=1: refused 1, abstained 0, answered 0 |
| task_wrapper | - | N=1: refused 1, abstained 0, answered 0 |

## Refusal (in_scope + out_of_scope + injection_direct)

| Refusal counted as | Set | N | Precision | Recall | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| guardrail only | dev | 53 | 0.7273 | 0.8000 | 8 | 3 | 2 |
| guardrail only | test | 27 | 0.4000 | 0.2857 | 2 | 3 | 5 |
| guardrail or LLM abstention | dev | 53 | 0.5882 | 1.0000 | 10 | 7 | 0 |
| guardrail or LLM abstention | test | 27 | 0.5000 | 1.0000 | 7 | 7 | 0 |

## Deterministic checks and judge

| Check | dev | test |
|---|---|---|
| Answers whose citations all exist in the context | 41/41 | 16/16 |
| Injection cases with a forbidden string in the answer | 2/10 | 1/6 |
| Indirect cases with the poisoned passage in the context | 5/5 | 3/3 |
| Answers to PT questions written in PT | 23/23 | 8/8 |
| Answers to EN questions written in EN | 8/18 | 1/8 |
| LLM-as-a-judge faithfulness mean | N=41: 1.0000 | N=16: 1.0000 |
| LLM-as-a-judge relevance mean | N=41: 0.9634 | N=16: 1.0000 |
