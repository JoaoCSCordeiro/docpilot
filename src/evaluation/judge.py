from typing import Literal, Protocol

from groq import BadRequestError
from pydantic import BaseModel, ConfigDict, ValidationError

from src.agent.graph import build_context
from src.agent.llm import GROQ, GuardedLLM, get_llm
from src.config import settings
from src.retrieval.retriever import RetrievedChunk

# A versao faz parte do prompt enviado ao juiz, e por isso da chave da cache LLM
# (modelo + prompt): mudar o rubric sem mudar a versao continuaria a invalidar a cache,
# mas o relatorio deixaria de dizer que rubric produziu os veredictos.
JUDGE_PROMPT_VERSION = "v1"

LABEL_SCORES = {
    "supported": 1.0,
    "partially_supported": 0.5,
    "unsupported": 0.0,
    "relevant": 1.0,
    "partially_relevant": 0.5,
    "irrelevant": 0.0,
}

_JUDGE_PROMPT = """You are grading one answer produced by a retrieval-augmented assistant.
Rubric version: {version}

You receive the QUESTION, the CONTEXT passages the assistant was given (each one starts \
with its source file in square brackets) and the ANSWER. Grade two criteria independently.

1. faithfulness: is every factual claim in the ANSWER supported by the CONTEXT?
   Judge only against the CONTEXT, never against your own knowledge.
   - supported: every factual claim is stated in, or directly follows from, the CONTEXT.
   - partially_supported: the main claim is supported, but at least one secondary claim \
is not in the CONTEXT.
   - unsupported: the main claim is not in the CONTEXT, contradicts it, or attributes to \
the project in the QUESTION something the CONTEXT says about a different project or file.
   Source citations such as [file.md] are not factual claims. An answer that only says \
the information is not available makes no factual claim: grade it supported.

2. relevance: does the ANSWER address what the QUESTION asks, regardless of correctness?
   - relevant: it directly answers the question.
   - partially_relevant: it answers only part of the question, or mostly talks about \
something else.
   - irrelevant: it does not address the question, including answers that only say the \
information is not available.

Write each reasoning field before its label, in at most three sentences.

QUESTION:
{question}

CONTEXT:
{context}

ANSWER:
{answer}"""


class JudgeVerdict(BaseModel):
    # extra="forbid" gera additionalProperties: false, exigido pelo modo strict da Groq.
    model_config = ConfigDict(extra="forbid")

    faithfulness_reasoning: str
    faithfulness: Literal["supported", "partially_supported", "unsupported"]
    relevance_reasoning: str
    relevance: Literal["relevant", "partially_relevant", "irrelevant"]


class JudgeError(Exception):
    pass


class JudgeLLM(Protocol):
    def invoke(self, prompt: str): ...


def build_judge_prompt(question: str, answer: str, chunks: list[RetrievedChunk]) -> str:
    return _JUDGE_PROMPT.format(
        version=JUDGE_PROMPT_VERSION,
        question=question,
        context=build_context(chunks),
        answer=answer,
    )


def judge_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "judge_verdict",
            "strict": True,
            "schema": JudgeVerdict.model_json_schema(),
        },
    }


def get_judge_llm() -> GuardedLLM:
    model_kwargs: dict = {"response_format": judge_response_format()}
    if settings.judge_reasoning_effort:
        model_kwargs["reasoning_effort"] = settings.judge_reasoning_effort
    # O juiz e o modelo Groq calibrado no Bloco 18, qualquer que seja o LLM_PROVIDER.
    return get_llm(
        provider=GROQ,
        model=settings.judge_model,
        max_tokens=settings.judge_max_tokens,
        model_kwargs=model_kwargs,
    )


def judge_answer(
    judge_llm: JudgeLLM, question: str, answer: str, chunks: list[RetrievedChunk]
) -> JudgeVerdict:
    try:
        response = judge_llm.invoke(build_judge_prompt(question, answer, chunks))
    except BadRequestError as error:
        # Em modo strict, a Groq rejeita com 400 (json_validate_failed) uma geracao que
        # nao cumpre o schema; conta como veredicto invalido, nao aborta a avaliacao.
        raise JudgeError(f"Groq rejeitou a resposta do juiz: {error}") from error
    try:
        return JudgeVerdict.model_validate_json(response.content)
    except ValidationError as error:
        raise JudgeError(f"Resposta do juiz fora do schema: {response.content[:200]!r}") from error
