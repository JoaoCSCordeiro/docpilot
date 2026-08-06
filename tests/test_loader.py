from pathlib import Path

from src.ingestion.loader import load_documents


def test_load_documents_reads_markdown_and_text_files(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("conteudo markdown", encoding="utf-8")
    (tmp_path / "b.txt").write_text("conteudo texto", encoding="utf-8")
    (tmp_path / "c.png").write_bytes(b"\x89PNG")

    documents = load_documents(tmp_path)

    sources = {document.source for document in documents}
    assert sources == {"a.md", "b.txt"}


def test_load_documents_returns_content_and_relative_source(tmp_path: Path) -> None:
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "nested.md").write_text("texto aninhado", encoding="utf-8")

    documents = load_documents(tmp_path)

    assert len(documents) == 1
    assert documents[0].content == "texto aninhado"
    assert documents[0].source == str(Path("sub") / "nested.md")


def test_load_documents_empty_directory_returns_empty_list(tmp_path: Path) -> None:
    assert load_documents(tmp_path) == []
