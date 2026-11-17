"""Settings shared by the scripts: settings.json at the repo root (falls back to settings.example.json)."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LABELS = {
    "errors": "Common errors",
    "words": "Words you looked up",
    "grade": "Today",
    "since_last": "since last session",
    "accuracy": "Accuracy",
    "range": "Range",
    "fluency": "Fluency",
    "pronunciation": "Pronunciation",
    "times_seen": "×{count}",
    "chart_title": "Grade · last 365 days",
    "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


def load_settings() -> dict:
    path = REPO / "settings.json"
    if not path.exists():
        path = REPO / "settings.example.json"
    return json.loads(path.read_text())


def end_card_labels(session: Path) -> dict:
    """Labels in the target language, written by Claude into end_screen.json; English otherwise."""
    end_screen = session / "end_screen.json"
    custom = json.loads(end_screen.read_text()).get("labels", {}) if end_screen.exists() else {}
    return {**DEFAULT_LABELS, **custom}
