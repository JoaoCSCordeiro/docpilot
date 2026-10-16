import json
from pathlib import Path

from src.evaluation.dataset import EVALUATION_DIR

BASELINE_PATH = EVALUATION_DIR / "baseline.json"


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_regressions(current: dict[str, float], baseline: dict) -> list[str]:
    tolerance = baseline["tolerance"]
    regressions = []
    for name, baseline_value in baseline["metrics"].items():
        current_value = current.get(name)
        if current_value is None:
            regressions.append(f"{name}: metrica em falta (baseline {baseline_value:.4f})")
        elif current_value < baseline_value - tolerance:
            regressions.append(
                f"{name}: {current_value:.4f} < baseline {baseline_value:.4f} "
                f"- tolerancia {tolerance}"
            )
    return regressions
