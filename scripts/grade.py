"""Grade a session 0-100% and chart the last 365 days.

Usage: .venv/bin/python scripts/grade.py <session dir> <range score 0-100>
Range is Claude's CEFR-anchored judgement of structures/vocab used: B1 40, B2 60, C1 80, native 100.
Reads transcript.json, corrections.json, shaky.json, pauses.json from the session.
Writes <session>/grade.json and <session>/progress.png (also copied to the sessions folder,
i.e. the session's parent, which is also where past grade.json files are read from).
"""
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from settings import end_card_labels

NATIVE_WORDS_PER_MINUTE = 150
WEIGHTS = {"accuracy": 0.35, "range": 0.25, "fluency": 0.2, "pronunciation": 0.2}
FONT_FILE = "/System/Library/Fonts/HelveticaNeue.ttc"
SURFACE = "#1a1a19"
TEXT_PRIMARY = "#f0efec"
TEXT_SECONDARY = "#c3c2b7"
GRID = "#383835"
SERIES = "#3987e5"
CHART_SIZE = (660, 380)
SUPERSAMPLE = 3


def clamp(score: float) -> int:
    return round(min(100, max(0, score)))


def grade(session: Path, range_score: int) -> dict:
    words = [w for s in json.loads((session / "transcript.json").read_text()) for w in s["words"]]
    corrections = json.loads((session / "corrections.json").read_text())
    shaky = json.loads((session / "shaky.json").read_text())
    pauses = json.loads((session / "pauses.json").read_text())

    real_errors = [c for c in corrections if not c["why"].startswith("Más natural")]
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


def past_year_grades(sessions: Path, today: date) -> list[tuple[date, int]]:
    grades = []
    for path in sessions.glob("*/grade.json"):
        entry = json.loads(path.read_text())
        day = date.fromisoformat(entry["date"])
        if today - day <= timedelta(days=365):
            grades.append((day, entry["overall"]))
    return sorted(grades)


def draw_chart(grades: list[tuple[date, int]], today: date, labels: dict) -> Image.Image:
    scale = SUPERSAMPLE
    width, height = CHART_SIZE[0] * scale, CHART_SIZE[1] * scale
    image = Image.new("RGB", (width, height), SURFACE)
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(FONT_FILE, 26 * scale)
    axis_font = ImageFont.truetype(FONT_FILE, 17 * scale)
    label_font = ImageFont.truetype(FONT_FILE, 20 * scale)

    left, right, top, bottom = 52 * scale, width - 40 * scale, 56 * scale, height - 34 * scale
    start = today - timedelta(days=365)

    def x_for(day: date) -> float:
        return left + (day - start).days / 365 * (right - left)

    def y_for(score: float) -> float:
        return bottom - score / 100 * (bottom - top)

    draw.text((0, 0), labels["chart_title"], font=title_font, fill=TEXT_PRIMARY)
    for score in (0, 25, 50, 75, 100):
        draw.line([(left, y_for(score)), (right, y_for(score))], fill=GRID, width=scale)
        draw.text((left - 10 * scale, y_for(score)), str(score), font=axis_font, fill=TEXT_SECONDARY, anchor="rm")
    month = date(start.year, start.month, 1)
    while month <= today:
        if month >= start:
            draw.text((x_for(month), bottom + 8 * scale), labels["months"][month.month - 1],
                      font=axis_font, fill=TEXT_SECONDARY, anchor="mt")
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)

    points = [(x_for(day), y_for(score)) for day, score in grades]
    if len(points) > 1:
        draw.line(points, fill=SERIES, width=3 * scale, joint="curve")
    radius = 5 * scale
    for x, y in points:
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=SERIES, outline=SURFACE, width=2 * scale)
    if points:
        x, y = points[-1]
        draw.text((x - 12 * scale, y - 12 * scale), f"{grades[-1][1]}%", font=label_font, fill=TEXT_PRIMARY, anchor="rb")
    return image.resize(CHART_SIZE, Image.LANCZOS)


def main() -> None:
    session = Path(sys.argv[1]).expanduser().resolve()
    result = grade(session, int(sys.argv[2]))
    (session / "grade.json").write_text(json.dumps(result, indent=2))

    today = date.fromisoformat(result["date"])
    draw_chart(past_year_grades(session.parent, today), today, end_card_labels(session)).save(session / "progress.png")
    shutil.copy(session / "progress.png", session.parent / "progress.png")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
