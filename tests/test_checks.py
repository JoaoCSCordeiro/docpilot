from src.agent.graph import ABSTENTION_MESSAGES, build_generation_prompt
from src.evaluation.checks import citation_check, cited_sources, is_abstention, leaked_strings
from src.retrieval.retriever import RetrievedChunk


def test_cited_sources_extracts_file_names_in_square_brackets_without_duplicates() -> None:
    answer = (
        "Usa MediaPipe [asl-translator-readme.md] e RabbitMQ [trendpulse-ai-readme.md]. "
        "Tambem MediaPipe [asl-translator-readme.md]."
    )

    assert cited_sources(answer) == ["asl-translator-readme.md", "trendpulse-ai-readme.md"]


def test_cited_sources_ignores_brackets_that_are_not_document_files() -> None:
    assert cited_sources("Ver [1] e [nota] e [external/FastAPI-readme.md]") == [
        "external/FastAPI-readme.md"
    ]


def test_citation_check_flags_sources_missing_from_the_context() -> None:
    result = citation_check("Resposta [a.md] [inventado.md]", context_sources=["a.md", "b.md"])

    assert result["has_citation"] is True
    assert result["invalid_citations"] == ["inventado.md"]
    assert result["all_citations_in_context"] is False


def test_answer_without_citations_does_not_count_as_all_citations_valid() -> None:
    result = citation_check("Resposta sem fontes.", context_sources=["a.md"])

    assert result["has_citation"] is False
    assert result["all_citations_in_context"] is False


def test_is_abstention_recognizes_both_languages_ignoring_case_and_spacing() -> None:
    assert is_abstention(ABSTENTION_MESSAGES[0].upper())
    assert is_abstention(f'"{ABSTENTION_MESSAGES[1]}"')
    assert not is_abstention("O classificador usado e o RandomForestClassifier.")


def test_generation_prompt_asks_for_citations_and_contains_both_abstention_phrases() -> None:
    chunk = RetrievedChunk(source="pasta/doc.md", position=0, text="texto", score=1.0)

    prompt = build_generation_prompt("pergunta?", [chunk])

    assert "[pasta/doc.md] texto" in prompt
    assert all(message in prompt for message in ABSTENTION_MESSAGES)
    assert prompt.endswith("Pergunta: pergunta?")


def test_leaked_strings_matches_forbidden_text_case_insensitively() -> None:
    answer = "A resposta e X. docpilot-canary-7q2x"

    assert leaked_strings(answer, ["DOCPILOT-CANARY-7Q2X", "Java 17"]) == ["DOCPILOT-CANARY-7Q2X"]


def test_cited_sources_accepts_the_native_gpt_oss_brackets_and_nested_forms() -> None:
    answer = "MediaPipe【asl-translator-readme.md】 e 3.10+【[external/psfrequests-readme.md]】."

    assert cited_sources(answer) == ["asl-translator-readme.md", "external/psfrequests-readme.md"]


def test_citation_check_reports_whether_the_requested_format_was_used() -> None:
    native = citation_check("Resposta【a.md】", context_sources=["a.md"])
    requested = citation_check("Resposta [a.md]", context_sources=["a.md"])

    assert native["all_citations_in_context"] is True
    assert native["uses_requested_format"] is False
    assert requested["uses_requested_format"] is True
