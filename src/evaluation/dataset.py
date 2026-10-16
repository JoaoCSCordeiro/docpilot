import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

EVALUATION_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"
DATASET_V1_PATH = EVALUATION_DIR / "qa_dataset.json"
DATASET_V2_PATH = EVALUATION_DIR / "qa_dataset_v2.json"
POISONED_DIR = EVALUATION_DIR / "poisoned"
POISONED_SOURCE_PREFIX = "poisoned/"

Category = Literal["in_scope", "out_of_scope", "injection_direct", "injection_indirect"]


class EvalCase(BaseModel):
    id: int
    question: str = Field(min_length=1)
    language: Literal["pt", "en"]
    category: Category
    should_refuse: bool
    expected_sources: list[str]
    expected_answer_hint: str
    document_language: Literal["pt", "en", "mixed"] | None
    # "injection" e a coleccao de avaliacao com os documentos envenenados; a coleccao
    # principal nunca os recebe.
    collection: Literal["main", "injection"] = "main"
    forbidden_strings: list[str] = []


def load_cases(path: Path = DATASET_V2_PATH) -> list[EvalCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = [EvalCase.model_validate(raw_case) for raw_case in raw_cases]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"ids duplicados em {path}")
    return cases
