import json
from collections import Counter
from pathlib import Path

import pytest

from src.evaluation.dataset import (
    DATASET_V1_PATH,
    POISONED_DIR,
    POISONED_SOURCE_PREFIX,
    EvalCase,
    load_cases,
)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
CANARY = "DOCPILOT-CANARY-7Q2X"


@pytest.fixture(scope="module")
def cases() -> list[EvalCase]:
    return load_cases()


def test_v2_keeps_the_25_original_questions_unchanged(cases: list[EvalCase]) -> None:
    originals = json.loads(DATASET_V1_PATH.read_text(encoding="utf-8"))
    by_id = {case.id: case for case in cases}

    for original in originals:
        case = by_id[original["id"]]
        assert case.question == original["question"]
        assert case.expected_sources == original["expected_sources"]
        assert case.expected_answer_hint == original["expected_answer_hint"]
        assert (case.language, case.category) == ("pt", "in_scope")


def test_v2_covers_every_category_planned_for_the_llm_evaluation(cases: list[EvalCase]) -> None:
    counts = Counter(case.category for case in cases)

    assert counts["in_scope"] >= 40
    assert counts["out_of_scope"] >= 8
    assert counts["injection_direct"] + counts["injection_indirect"] >= 10
    assert Counter(case.language for case in cases if case.category == "in_scope")["en"] >= 15


def test_out_of_scope_cases_must_be_refused_and_have_no_expected_sources(
    cases: list[EvalCase],
) -> None:
    for case in cases:
        if case.category == "out_of_scope":
            assert case.should_refuse and case.expected_sources == []


def test_expected_sources_of_main_collection_cases_exist_in_the_indexed_corpus(
    cases: list[EvalCase],
) -> None:
    for case in cases:
        for source in case.expected_sources:
            if source.startswith(POISONED_SOURCE_PREFIX):
                assert case.collection == "injection"
                assert (POISONED_DIR / source.removeprefix(POISONED_SOURCE_PREFIX)).is_file()
            else:
                assert (RAW_DIR / source).is_file()


def test_poisoned_documents_live_outside_data_raw_and_contain_the_canary() -> None:
    poisoned_files = list(POISONED_DIR.glob("*.md"))

    assert poisoned_files
    assert RAW_DIR not in POISONED_DIR.parents
    assert all(CANARY in path.read_text(encoding="utf-8") for path in poisoned_files)
    assert not any(CANARY in path.read_text(encoding="utf-8") for path in RAW_DIR.rglob("*.md"))


def test_indirect_injection_cases_check_that_the_canary_does_not_leak(
    cases: list[EvalCase],
) -> None:
    indirect = [case for case in cases if case.category == "injection_indirect"]

    assert indirect
    assert all(CANARY in case.forbidden_strings for case in indirect)


def test_load_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    case = {
        "id": 1,
        "question": "q",
        "language": "pt",
        "category": "in_scope",
        "should_refuse": False,
        "expected_sources": ["a.md"],
        "expected_answer_hint": "h",
        "document_language": "pt",
    }
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps([case, case]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_cases(path)
