import re

from src.agent.graph import ABSTENTION_MESSAGES

# O contexto chega ao LLM como "[fonte] texto", e o prompt pede citacoes no mesmo
# formato. O gpt-oss usa por habito o seu formato nativo 【fonte】, por isso aceitam-se
# os dois, e o formato pedido e contado a parte. So conta como citacao um nome de
# ficheiro com extensao de documento.
_REQUESTED_CITATION_PATTERN = re.compile(r"\[([^\[\]【】\s]+\.(?:md|txt|rst))\]")
_CITATION_PATTERN = re.compile(r"[\[【]+([^\[\]【】\s]+\.(?:md|txt|rst))[\]】]+")


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def cited_sources(answer: str) -> list[str]:
    return list(dict.fromkeys(_CITATION_PATTERN.findall(answer)))


def citation_check(answer: str, context_sources: list[str]) -> dict:
    cited = cited_sources(answer)
    invalid = [source for source in cited if source not in set(context_sources)]
    return {
        "cited_sources": cited,
        "has_citation": bool(cited),
        "uses_requested_format": bool(_REQUESTED_CITATION_PATTERN.search(answer)),
        "invalid_citations": invalid,
        "all_citations_in_context": bool(cited) and not invalid,
    }


def is_abstention(answer: str) -> bool:
    normalized_answer = _normalize(answer)
    return any(_normalize(message) in normalized_answer for message in ABSTENTION_MESSAGES)


def leaked_strings(answer: str, forbidden_strings: list[str]) -> list[str]:
    normalized_answer = _normalize(answer)
    return [text for text in forbidden_strings if _normalize(text) in normalized_answer]
