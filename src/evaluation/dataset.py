import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

EVALUATION_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"
DATASET_V1_PATH = EVALUATION_DIR / "qa_dataset.json"
DATASET_V2_PATH = EVALUATION_DIR / "qa_dataset_v2.json"
DATASET_TEST_PATH = EVALUATION_DIR / "qa_dataset_test.json"
POISONED_DIR = EVALUATION_DIR / "poisoned"
POISONED_TEST_DIR = EVALUATION_DIR / "poisoned_test"
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
    # Subtipos usados para agrupar o relatorio (ex.: "hard_negative", "paraphrase").
    tags: list[str] = []


class DatasetSpec(BaseModel):
    path: Path
    poisoned_dir: Path


# Cada conjunto traz os seus documentos envenenados: os do held-out nao podem entrar na
# coleccao de injecao do dev, senao mudariam os resultados ja publicados do dev.
DATASETS = {
    "dev": DatasetSpec(path=DATASET_V2_PATH, poisoned_dir=POISONED_DIR),
    "test": DatasetSpec(path=DATASET_TEST_PATH, poisoned_dir=POISONED_TEST_DIR),
}


def load_cases(path: Path = DATASET_V2_PATH) -> list[EvalCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = [EvalCase.model_validate(raw_case) for raw_case in raw_cases]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"ids duplicados em {path}")
    return cases
