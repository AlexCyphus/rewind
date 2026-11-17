"""Grade a session 0-100%.

Usage: .venv/bin/python scripts/grade.py <session dir> <range score 0-100>
Range is Claude's CEFR-anchored judgement of structures/vocab used: B1 40, B2 60, C1 80, native 100.
Reads transcript.json, corrections.json, shaky.json, pauses.json from the session.
Writes <session>/grade.json (the end card charts every grade.json in the sessions folder).
"""
import json
import sys
from pathlib import Path

NATIVE_WORDS_PER_MINUTE = 150
WEIGHTS = {"accuracy": 0.35, "range": 0.25, "fluency": 0.2, "pronunciation": 0.2}


def clamp(score: float) -> int:
    return round(min(100, max(0, score)))


def grade(session: Path, range_score: int) -> dict:
    words = [w for s in json.loads((session / "transcript.json").read_text()) for w in s["words"]]
    corrections = json.loads((session / "corrections.json").read_text())
    shaky = json.loads((session / "shaky.json").read_text())
    pauses = json.loads((session / "pauses.json").read_text())

    real_errors = [c for c in corrections if not c.get("upgrade")]
    pause_seconds = sum(p["seconds"] for p in pauses)
    speaking_minutes = (words[-1]["end"] - words[0]["start"] - pause_seconds) / 60
    total_minutes = (words[-1]["end"] - words[0]["start"]) / 60
    per_hundred_words = 100 / len(words)

    scores = {
        "accuracy": clamp(100 - 10 * len(real_errors) * per_hundred_words),
        "range": clamp(range_score),
        "fluency": clamp(len(words) / speaking_minutes / NATIVE_WORDS_PER_MINUTE * 100 - 4 * len(pauses) / total_minutes),
        "pronunciation": clamp(100 - 4 * len(shaky) * per_hundred_words),
    }
    overall = clamp(sum(scores[name] * weight for name, weight in WEIGHTS.items()))
    return {"date": session.name[:10], "overall": overall, **scores, "words": len(words)}


def main() -> None:
    session = Path(sys.argv[1]).expanduser().resolve()
    result = grade(session, int(sys.argv[2]))
    (session / "grade.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
