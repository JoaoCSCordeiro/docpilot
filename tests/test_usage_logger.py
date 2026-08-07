from pathlib import Path

from src.agent.usage_logger import log_usage


def test_log_usage_creates_log_file_with_expected_fields(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "groq_usage.log"

    log_usage(
        prompt_preview="qual e a capital de Portugal?",
        input_tokens=42,
        output_tokens=8,
        total_tokens=50,
        log_path=log_path,
    )

    content = log_path.read_text(encoding="utf-8")
    assert "input_tokens=42" in content
    assert "output_tokens=8" in content
    assert "total_tokens=50" in content
    assert "capital de Portugal" in content


def test_log_usage_appends_multiple_calls(tmp_path: Path) -> None:
    log_path = tmp_path / "groq_usage.log"

    log_usage("primeira pergunta", 10, 5, 15, log_path=log_path)
    log_usage("segunda pergunta", 20, 10, 30, log_path=log_path)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "primeira pergunta" in lines[0]
    assert "segunda pergunta" in lines[1]
