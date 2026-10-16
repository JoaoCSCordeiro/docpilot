import json

import pytest

from src.config import settings
from src.evaluation import judge
from src.evaluation.judge import (
    JUDGE_PROMPT_VERSION,
    JudgeError,
    JudgeVerdict,
    build_judge_prompt,
    get_judge_llm,
    judge_answer,
    judge_response_format,
)
from src.retrieval.retriever import RetrievedChunk

CHUNKS = [
    RetrievedChunk(
        source="trendpulse-ai-readme.md", position=3, text="Usa RandomForestRegressor.", score=2.0
    )
]
VALID_VERDICT = {
    "faithfulness_reasoning": "O contexto diz RandomForestRegressor.",
    "faithfulness": "supported",
    "relevance_reasoning": "Responde ao que foi pedido.",
    "relevance": "relevant",
}


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeJudgeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> FakeResponse:
        self.prompts.append(prompt)
        return FakeResponse(self.content)


def test_judge_prompt_contains_rubric_version_question_context_and_answer() -> None:
    prompt = build_judge_prompt("Que modelo?", "RandomForestRegressor", CHUNKS)

    assert f"Rubric version: {JUDGE_PROMPT_VERSION}" in prompt
    assert "Que modelo?" in prompt
    assert "[trendpulse-ai-readme.md] Usa RandomForestRegressor." in prompt
    assert prompt.rstrip().endswith("RandomForestRegressor")


def test_judge_answer_parses_a_valid_structured_verdict() -> None:
    fake_llm = FakeJudgeLLM(json.dumps(VALID_VERDICT))

    verdict = judge_answer(fake_llm, "Que modelo?", "RandomForestRegressor", CHUNKS)

    assert verdict == JudgeVerdict(**VALID_VERDICT)
    assert len(fake_llm.prompts) == 1


@pytest.mark.parametrize(
    "content",
    [
        "isto nao e JSON",
        json.dumps({**VALID_VERDICT, "faithfulness": "mostly"}),
        json.dumps({**VALID_VERDICT, "extra": "campo"}),
    ],
)
def test_judge_answer_rejects_output_outside_the_schema(content: str) -> None:
    with pytest.raises(JudgeError):
        judge_answer(FakeJudgeLLM(content), "q", "a", CHUNKS)


def test_response_format_is_strict_json_schema_without_additional_properties() -> None:
    response_format = judge_response_format()
    schema = response_format["json_schema"]["schema"]

    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(VALID_VERDICT)


def test_judge_llm_uses_the_configured_judge_model_and_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    monkeypatch.setattr(judge, "get_llm", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(settings, "judge_model", "qwen/qwen3.8-27b")
    monkeypatch.setattr(settings, "judge_reasoning_effort", "none")

    get_judge_llm()

    assert captured["model"] == "qwen/qwen3.8-27b"
    assert captured["model_kwargs"]["reasoning_effort"] == "none"
    assert captured["model_kwargs"]["response_format"] == judge_response_format()


def test_judge_llm_omits_reasoning_effort_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    monkeypatch.setattr(judge, "get_llm", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(settings, "judge_reasoning_effort", "")

    get_judge_llm()

    assert "reasoning_effort" not in captured["model_kwargs"]
