from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass
class Document:
    source: str
    content: str


def load_documents(raw_dir: str | Path) -> list[Document]:
    raw_dir = Path(raw_dir)
    documents = []
    for path in sorted(raw_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            content = path.read_text(encoding="utf-8")
            documents.append(Document(source=str(path.relative_to(raw_dir)), content=content))
    return documents
