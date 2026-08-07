from pathlib import Path

from src.agent.llm_cache import get_cached_response, store_response


def test_get_cached_response_returns_none_when_not_cached(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    assert get_cached_response("pergunta nunca vista", db_path=db_path) is None


def test_store_and_retrieve_response(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    store_response("qual e a capital de Portugal?", "Lisboa", db_path=db_path)

    assert get_cached_response("qual e a capital de Portugal?", db_path=db_path) == "Lisboa"


def test_different_prompts_do_not_collide(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    store_response("prompt a", "resposta a", db_path=db_path)
    store_response("prompt b", "resposta b", db_path=db_path)

    assert get_cached_response("prompt a", db_path=db_path) == "resposta a"
    assert get_cached_response("prompt b", db_path=db_path) == "resposta b"


def test_storing_again_for_same_prompt_overwrites_previous_response(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"

    store_response("prompt", "resposta antiga", db_path=db_path)
    store_response("prompt", "resposta nova", db_path=db_path)

    assert get_cached_response("prompt", db_path=db_path) == "resposta nova"
