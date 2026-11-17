"""Render the end card as one image: topic, today's grade, 365-day chart, common errors, looked-up words.

Used by burn.py. Reads end_screen.json, grade.json and topic.txt from the session, and every
grade.json in the sessions folder (the session's parent) for the chart.
"""
import json
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from settings import end_card_labels

FONT_FILE = "/System/Library/Fonts/SFNS.ttf"  # SF Pro, a variable font; has arrows that Helvetica Neue lacks
EMOJI_FONT_FILE = "/System/Library/Fonts/Apple Color Emoji.ttc"
REGULAR, MEDIUM, BOLD = "Regular", "Medium", "Bold"
SUPERSAMPLE = 2

BACKGROUND_TOP = (18, 18, 17)
BACKGROUND_BOTTOM = (28, 28, 26)
CARD = (34, 34, 32)
CARD_BORDER = (48, 48, 45)
TRACK = (52, 52, 49)
TEXT_PRIMARY = (240, 239, 236)
TEXT_SECONDARY = (195, 194, 183)
TEXT_MUTED = (138, 137, 131)
BLUE = (57, 135, 229)
ORANGE = (255, 165, 0)
CHIP = (66, 50, 20)
RED = (230, 103, 103)
GREEN = (92, 200, 122)


class Canvas:
    """Draws in 1080p design units; scales to the real frame size (supersampled for smooth edges)."""

    def __init__(self, width: int, height: int):
        self.size = (width, height)
        self.scale = height / 1080 * SUPERSAMPLE
        self.width = width / (height / 1080)  # frame width in design units
        self.image = Image.new("RGB", (width * SUPERSAMPLE, height * SUPERSAMPLE))
        self.draw = ImageDraw.Draw(self.image)
        self.fonts: dict[tuple[int, str], ImageFont.FreeTypeFont] = {}

    def px(self, value: float) -> int:
        return round(value * self.scale)

    def font(self, size: int, weight: str = REGULAR) -> ImageFont.FreeTypeFont:
        key = (size, weight)
        if key not in self.fonts:
            font = ImageFont.truetype(FONT_FILE, self.px(size))
            font.set_variation_by_name(weight)
            self.fonts[key] = font
        return self.fonts[key]

    def text_width(self, text: str, size: int, weight: str = REGULAR) -> float:
        return self.font(size, weight).getlength(text) / self.scale

    def fit(self, text: str, size: int, weight: str, max_width: float) -> str:
        if self.text_width(text, size, weight) <= max_width:
            return text
        while text and self.text_width(text + "…", size, weight) > max_width:
            text = text[:-1]
        return text.rstrip() + "…"

    def wrap(self, text: str, size: int, max_width: float, max_lines: int) -> list[str]:
        lines, current = [], ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and self.text_width(candidate, size) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = self.fit(lines[-1] + " …", size, REGULAR, max_width)
        return lines

    def text(self, xy, text: str, size: int, fill, weight: str = REGULAR, anchor: str = "la") -> None:
        self.draw.text((self.px(xy[0]), self.px(xy[1])), text, font=self.font(size, weight), fill=fill, anchor=anchor)

    def rounded(self, box, radius: float, fill, outline=None) -> None:
        self.draw.rounded_rectangle([self.px(v) for v in box], self.px(radius), fill=fill, outline=outline,
                                    width=self.px(1.5) if outline else 0)

    def card(self, box) -> None:
        self.rounded(box, 26, CARD, CARD_BORDER)

    def background(self) -> None:
        height = self.image.height
        for y in range(height):
            mix = y / height
            colour = tuple(round(top + (bottom - top) * mix) for top, bottom in zip(BACKGROUND_TOP, BACKGROUND_BOTTOM))
            self.draw.line([(0, y), (self.image.width, y)], fill=colour)

    def emoji(self, xy, emoji: str, size: float) -> None:
        font = ImageFont.truetype(EMOJI_FONT_FILE, 160)
        glyph = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((100, 100), emoji, font=font, embedded_color=True, anchor="mm")
        glyph = glyph.crop(glyph.getbbox()).resize((self.px(size), self.px(size)), Image.LANCZOS)
        self.image.paste(glyph, (self.px(xy[0]), self.px(xy[1])), glyph)

    def finish(self) -> Image.Image:
        return self.image.resize(self.size, Image.LANCZOS)


def past_year_grades(sessions: Path, today: date) -> list[tuple[date, int]]:
    grades = []
    for path in sessions.glob("*/grade.json"):
        entry = json.loads(path.read_text())
        day = date.fromisoformat(entry["date"])
        if timedelta(0) <= today - day <= timedelta(days=365):
            grades.append((day, entry["overall"]))
    return sorted(grades)


def draw_header(canvas: Canvas, session: Path, today: date, labels: dict, margin: float) -> None:
    topic_path = session / "topic.txt"
    topic = topic_path.read_text().strip() if topic_path.exists() else ""
    canvas.emoji((margin, 46), "⏪", 30)
    day = f"{today.day} {labels['months'][today.month - 1]} {today.year}"
    canvas.text((margin + 42, 49), f"rewind  ·  {day}", 24, TEXT_MUTED, MEDIUM)
    canvas.text((margin, 92), canvas.fit(topic, 44, BOLD, canvas.width - 2 * margin), 44, TEXT_PRIMARY, BOLD)


def draw_grade_card(canvas: Canvas, box, grade: dict, previous: int | None, labels: dict) -> None:
    left, top, right, bottom = box
    canvas.card(box)
    diameter = 230
    ring_left, ring_top = left + 40, top + (bottom - top - diameter) / 2
    ring = [canvas.px(v) for v in (ring_left, ring_top, ring_left + diameter, ring_top + diameter)]
    thickness = canvas.px(20)
    canvas.draw.arc(ring, 0, 360, fill=TRACK, width=thickness)
    if grade["overall"] > 0:
        canvas.draw.arc(ring, -90, -90 + 3.6 * grade["overall"], fill=BLUE, width=thickness)
    centre_x, centre_y = ring_left + diameter / 2, ring_top + diameter / 2
    canvas.text((centre_x, centre_y - 6), f"{grade['overall']}%", 64, TEXT_PRIMARY, BOLD, "mm")
    canvas.text((centre_x, centre_y + 42), canvas.fit(labels["grade"], 20, MEDIUM, diameter - 50), 20, TEXT_MUTED, MEDIUM, "mm")

    column_left = ring_left + diameter + 44
    column_width = right - 40 - column_left
    y = top + 44
    if previous is not None:
        change = grade["overall"] - previous
        colour = GREEN if change >= 0 else RED
        arrow = "▲" if change >= 0 else "▼"
        canvas.text((column_left, y), f"{arrow} {abs(change)}", 30, colour, BOLD)
        canvas.text((column_left + canvas.text_width(f"{arrow} {abs(change)}", 30, BOLD) + 10, y + 7),
                    canvas.fit(labels["since_last"], 20, REGULAR, column_width - 80), 20, TEXT_MUTED)
        y += 58
    else:
        y += 14
    rows = ["accuracy", "range", "fluency", "pronunciation"]
    row_height = (bottom - 40 - y) / len(rows)
    for index, key in enumerate(rows):
        row_top = y + index * row_height
        canvas.text((column_left, row_top), canvas.fit(labels[key], 21, REGULAR, column_width - 50), 21, TEXT_SECONDARY)
        canvas.text((column_left + column_width, row_top), str(grade[key]), 21, TEXT_PRIMARY, BOLD, "ra")
        bar_top = row_top + 32
        canvas.rounded((column_left, bar_top, column_left + column_width, bar_top + 7), 3.5, TRACK)
        canvas.rounded((column_left, bar_top, column_left + column_width * grade[key] / 100, bar_top + 7), 3.5, BLUE)


def draw_chart_card(canvas: Canvas, box, grades: list[tuple[date, int]], today: date, labels: dict) -> None:
    left, top, right, bottom = box
    canvas.card(box)
    canvas.text((left + 36, top + 32), labels["chart_title"], 24, TEXT_SECONDARY, MEDIUM)
    plot_left, plot_right, plot_top, plot_bottom = left + 80, right - 44, top + 92, bottom - 64
    start = today - timedelta(days=365)

    def x_for(day: date) -> float:
        return plot_left + (day - start).days / 365 * (plot_right - plot_left)

    def y_for(score: float) -> float:
        return plot_bottom - score / 100 * (plot_bottom - plot_top)

    for score in (0, 50, 100):
        canvas.draw.line([(canvas.px(plot_left), canvas.px(y_for(score))), (canvas.px(plot_right), canvas.px(y_for(score)))],
                         fill=TRACK, width=canvas.px(1.5))
        canvas.text((plot_left - 16, y_for(score)), str(score), 18, TEXT_MUTED, REGULAR, "rm")
    month = date(start.year, start.month, 1)
    while month <= today:
        if month > start:
            canvas.text((x_for(month), plot_bottom + 18), labels["months"][month.month - 1], 18, TEXT_MUTED, REGULAR, "ma")
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)

    points = [(canvas.px(x_for(day)), canvas.px(y_for(score))) for day, score in grades]
    if len(points) > 1:
        area = Image.new("RGBA", canvas.image.size, (0, 0, 0, 0))
        ImageDraw.Draw(area).polygon(points + [(points[-1][0], canvas.px(plot_bottom)), (points[0][0], canvas.px(plot_bottom))],
                                     fill=BLUE + (40,))
        canvas.image.paste(area, (0, 0), area)
        canvas.draw.line(points, fill=BLUE, width=canvas.px(4), joint="curve")
    radius = canvas.px(7)
    for x, y in points:
        canvas.draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=BLUE, outline=CARD, width=canvas.px(3))
    if points:
        x, y = points[-1]
        canvas.text((x / canvas.scale - 14, y / canvas.scale - 14), f"{grades[-1][1]}%", 22, TEXT_PRIMARY, BOLD, "rb")


def draw_errors_card(canvas: Canvas, box, errors: list[dict], labels: dict) -> None:
    left, top, right, bottom = box
    canvas.card(box)
    canvas.text((left + 36, top + 32), labels["errors"], 30, TEXT_PRIMARY, BOLD)
    y = top + 96
    item_height = (bottom - 24 - y) / max(len(errors), 1)
    for index, error in enumerate(errors, 1):
        badge = 36
        canvas.rounded((left + 36, y, left + 36 + badge, y + badge), badge / 2, BLUE)
        canvas.text((left + 36 + badge / 2, y + badge / 2), str(index), 20, TEXT_PRIMARY, BOLD, "mm")
        text_left = left + 36 + badge + 18
        chip = ""
        if error.get("sessions", 1) > 1:
            chip = labels["times_seen"].format(count=error["sessions"])
        chip_width = canvas.text_width(chip, 18, BOLD) + 24 if chip else 0
        pattern_width = right - 36 - text_left - (chip_width + 14 if chip else 0)
        pattern = canvas.fit(error["pattern"], 25, BOLD, pattern_width)
        canvas.text((text_left, y + 4), pattern, 25, TEXT_PRIMARY, BOLD)
        if chip:
            chip_left = text_left + canvas.text_width(pattern, 25, BOLD) + 14
            canvas.rounded((chip_left, y + 3, chip_left + chip_width, y + 33), 15, CHIP)
            canvas.text((chip_left + chip_width / 2, y + 18), chip, 18, ORANGE, BOLD, "mm")
        examples = canvas.fit("  ·  ".join(error["examples"]), 21, REGULAR, right - 36 - text_left)
        canvas.text((text_left, y + 40), examples, 21, TEXT_MUTED)
        y += item_height


def draw_words_card(canvas: Canvas, box, words: list[dict], labels: dict) -> None:
    left, top, right, bottom = box
    canvas.card(box)
    canvas.text((left + 36, top + 32), labels["words"], 30, TEXT_PRIMARY, BOLD)
    y = top + 96
    width = right - left - 72
    for word in words[:3]:
        looked_up = canvas.fit(word["looked_up"], 26, BOLD, width / 2 - 30)
        looked_up_width = canvas.text_width(looked_up, 26, BOLD)
        canvas.text((left + 36, y), looked_up, 26, RED, BOLD)
        canvas.draw.line([(canvas.px(left + 36), canvas.px(y + 15)), (canvas.px(left + 36 + looked_up_width), canvas.px(y + 15))],
                         fill=RED, width=canvas.px(2))
        arrow_left = left + 36 + looked_up_width + 14
        canvas.text((arrow_left, y), "→", 26, TEXT_MUTED)
        better_left = arrow_left + canvas.text_width("→", 26) + 14
        canvas.text((better_left, y), canvas.fit(word["better"], 26, BOLD, right - 36 - better_left), 26, GREEN, BOLD)
        for line_index, line in enumerate(canvas.wrap(word["note"], 20, width, 2)):
            canvas.text((left + 36, y + 40 + line_index * 26), line, 20, TEXT_MUTED)
        y += 112


def render_end_card(session: Path, width: int, height: int) -> Image.Image:
    labels = end_card_labels(session)
    end_screen = json.loads((session / "end_screen.json").read_text())
    grade_path = session / "grade.json"
    grade = json.loads(grade_path.read_text()) if grade_path.exists() else None
    today = date.fromisoformat(grade["date"]) if grade else date.today()

    canvas = Canvas(width, height)
    canvas.background()
    margin, gap = 56, 24
    content_width = canvas.width - 2 * margin
    draw_header(canvas, session, today, labels, margin)

    row_one_top, row_one_bottom = 172, 562
    row_two_top, row_two_bottom = row_one_bottom + gap, 1080 - 48
    if grade:
        grades = past_year_grades(session.parent, today)
        earlier = [score for day, score in grades if day < today]
        grade_right = margin + content_width * 0.42
        draw_grade_card(canvas, (margin, row_one_top, grade_right, row_one_bottom), grade,
                        earlier[-1] if earlier else None, labels)
        draw_chart_card(canvas, (grade_right + gap, row_one_top, margin + content_width, row_one_bottom), grades, today, labels)
    else:
        row_two_top = row_one_top

    errors_right = margin + content_width * 0.56
    draw_errors_card(canvas, (margin, row_two_top, errors_right, row_two_bottom), end_screen["errors"][:4], labels)
    draw_words_card(canvas, (errors_right + gap, row_two_top, margin + content_width, row_two_bottom), end_screen["words"], labels)
    return canvas.finish()
