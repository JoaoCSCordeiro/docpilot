import datetime as dt
from pathlib import Path

_DEFAULT_LOG_PATH = Path("logs/groq_usage.log")


def log_usage(
    prompt_preview: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    log_path: Path = _DEFAULT_LOG_PATH,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    safe_preview = prompt_preview.replace("\n", " ").strip()
    line = (
        f"{timestamp}\tinput_tokens={input_tokens}\toutput_tokens={output_tokens}"
        f"\ttotal_tokens={total_tokens}\tprompt_preview={safe_preview!r}\n"
    )
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(line)
