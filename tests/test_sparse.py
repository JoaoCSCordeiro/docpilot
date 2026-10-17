from src.retrieval.sparse import (
    NO_STEMMING,
    average_token_count,
    embed_sparse_passages,
    embed_sparse_query,
)


def test_query_and_passage_share_token_ids_for_the_same_stemmed_word() -> None:
    passage = embed_sparse_passages(["The containers are running"], "english")[0]
    query = embed_sparse_query("container", "english")

    assert set(query.indices) <= set(passage.indices)


def test_query_terms_have_unit_weight() -> None:
    query = embed_sparse_query("docker compose volumes", "english")

    assert query.values == [1.0] * len(query.indices)


def test_no_stemming_keeps_inflected_forms_apart() -> None:
    passage = embed_sparse_passages(["containers"], NO_STEMMING)[0]
    query = embed_sparse_query("container", NO_STEMMING)

    assert not set(query.indices) & set(passage.indices)


def test_average_token_count_ignores_stopwords() -> None:
    assert average_token_count(["the docker image", "a compose file"], "english") == 2.0
