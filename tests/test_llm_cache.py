from pathlib import Path

from src.agent.llm_cache import get_cached_response, store_response

MODEL = "openai/gpt-oss-120b"


def test_get_cached_response_returns_none_when_not_cached(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    assert get_cached_response(MODEL, "pergunta nunca vista", db_path=db_path) is None


def test_store_and_retrieve_response(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    store_response(MODEL, "qual e a capital de Portugal?", "Lisboa", db_path=db_path)

    assert get_cached_response(MODEL, "qual e a capital de Portugal?", db_path=db_path) == "Lisboa"


def test_different_prompts_do_not_collide(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    store_response(MODEL, "prompt a", "resposta a", db_path=db_path)
    store_response(MODEL, "prompt b", "resposta b", db_path=db_path)

    assert get_cached_response(MODEL, "prompt a", db_path=db_path) == "resposta a"
    assert get_cached_response(MODEL, "prompt b", db_path=db_path) == "resposta b"


def test_storing_again_for_same_prompt_overwrites_previous_response(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    store_response(MODEL, "prompt", "resposta antiga", db_path=db_path)
    store_response(MODEL, "prompt", "resposta nova", db_path=db_path)

    assert get_cached_response(MODEL, "prompt", db_path=db_path) == "resposta nova"


def test_same_prompt_for_different_models_is_cached_separately(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    store_response("gerador", "mesmo prompt", "resposta do gerador", db_path=db_path)

    assert get_cached_response("juiz", "mesmo prompt", db_path=db_path) is None
    store_response("juiz", "mesmo prompt", "veredicto do juiz", db_path=db_path)
    assert get_cached_response("gerador", "mesmo prompt", db_path=db_path) == (
        "resposta do gerador"
    )
