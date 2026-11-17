"""Burn corrections into a copy of the video as subtitles.

Usage: .venv/bin/python scripts/burn.py <video> <corrections.json>
corrections.json: [{"start": 12.3, "end": 15.0, "said": "...", "correct": "...", "why": "...",
                    "upgrade": false, "translation": false}]
("translation": an English word said mid-speech; shown with its translation instead of struck through.)
Writes reviewed.mp4 next to corrections.json.

Layout, bottom to top, so the eyes stay in one place:
- running transcript (from transcript.json), one line at a time, shaky words in orange
- a speech bubble above each shaky word saying why (from shaky.json)
- the current correction, sitting just above however many bubble rows are on screen during it
If end_screen.json sits next to it, appends an end card rendered by end_card.py
(with today's grade and the 365-day chart when grade.json from grade.py is there too):
{"errors": [{"pattern": "...", "examples": ["said → correct"], "sessions": 2}],
 "words": [{"looked_up": "esquema", "better": "una idea", "note": "..."}],
 "labels": {...end card headings in the target language, see settings.DEFAULT_LABELS}}
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

from end_card import render_end_card

FONT_FILE = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_NAME = "Helvetica Neue"
MIN_SECONDS_ON_SCREEN = 4.0
LINE_LINGER_SECONDS = 1.0
END_SCREEN_SECONDS = 20
END_CARD_FADE_SECONDS = 0.6
ORANGE = "&H00A5FF&"


def video_duration(video: Path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout.strip())


def video_size(video: Path) -> tuple[int, int]:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    width, height = output.split("x")
    return int(width), int(height)


def ass_time(seconds: float) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def dialogue(start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}"


class Layout:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.correction_size = round(height / 22)
        self.transcript_size = round(height / 27)
        self.bubble_size = round(height / 40)
        self.transcript_padding = round(self.transcript_size / 5)
        self.bubble_padding = round(self.bubble_size / 4)
        self.transcript_bottom = height - round(height / 20)
        self.transcript_top = self.transcript_bottom - round(self.transcript_size * 1.15) - 2 * self.transcript_padding
        self.pointer_height = round(self.bubble_size / 2)
        self.bubble_row_height = round(self.bubble_size * 1.15) + 2 * self.bubble_padding
        self.bubble_bottom = self.transcript_top - self.pointer_height
        self.stack_gap = round(height / 60)
        self.max_line_width = width * 0.9
        self.transcript_font = ImageFont.truetype(FONT_FILE, self.transcript_size)
        self.bubble_font = ImageFont.truetype(FONT_FILE, self.bubble_size)
        self.correction_font = ImageFont.truetype(FONT_FILE, self.correction_size)

    def correction_bottom(self, bubble_rows: int) -> int:
        if bubble_rows == 0:
            return self.transcript_top - self.stack_gap
        return self.bubble_bottom - bubble_rows * self.bubble_row_height - self.stack_gap

    def styles(self) -> str:
        def style(name, size, primary, outline, border_style, outline_width):
            return (f"Style: {name},{FONT_NAME},{size},{primary},&H00FFFFFF,{outline},&HB0000000,"
                    f"0,0,0,0,100,100,0,0,{border_style},{outline_width},0,2,0,0,0,1")
        return "\n".join([
            style("Transcript", self.transcript_size, "&H00FFFFFF", "&H00000000", 3, self.transcript_padding),
            style("Bubble", self.bubble_size, "&H00000000", "&H0000A5FF", 3, self.bubble_padding),
            style("Pointer", 1, "&H0000A5FF", "&H00000000", 1, 0),
            style("Fix", self.correction_size, "&H00FFFFFF", "&H00000000", 3, round(self.correction_size / 4)),
        ])


def split_into_lines(words: list[dict], layout: Layout) -> list[list[dict]]:
    lines, current = [], []
    for word in words:
        candidate = " ".join(w["word"].strip() for w in current + [word])
        if current and layout.transcript_font.getlength(candidate) > layout.max_line_width:
            lines.append(current)
            current = []
        current.append(word)
    return lines + [current] if current else lines


def word_centres(line: list[dict], layout: Layout) -> list[float]:
    texts = [w["word"].strip() for w in line]
    left = (layout.width - layout.transcript_font.getlength(" ".join(texts))) / 2
    centres = []
    for index, text in enumerate(texts):
        before = layout.transcript_font.getlength(" ".join(texts[:index]) + (" " if index else ""))
        centres.append(left + before + layout.transcript_font.getlength(text) / 2)
    return centres


def bubble_events(line: list[dict], shaky_by_start: dict, start: float, end: float, layout: Layout) -> tuple[list[str], int]:
    """Bubbles above the shaky words of one line, stacked into rows so none overlap. Returns events and rows used."""
    events, placed = [], []
    for word, centre in zip(line, word_centres(line, layout)):
        shaky = shaky_by_start.get(round(word["start"], 2))
        if not shaky:
            continue
        half_width = layout.bubble_font.getlength(shaky["why"]) / 2 + layout.bubble_padding
        left = min(max(centre - half_width, 0), layout.width - 2 * half_width)
        row = 0
        while any(r == row and left < right and other_left < left + 2 * half_width for r, other_left, right in placed):
            row += 1
        placed.append((row, left, left + 2 * half_width))
        bottom = layout.bubble_bottom - row * layout.bubble_row_height
        events.append(dialogue(start, end, "Bubble",
                               f"{{\\an2\\pos({left + half_width:.0f},{bottom - layout.bubble_padding})}}{ass_escape(shaky['why'])}"))
        if row == 0:
            half = layout.pointer_height
            events.append(dialogue(start, end, "Pointer",
                                   f"{{\\an7\\pos({centre - half:.0f},{layout.bubble_bottom})\\p1}}"
                                   f"m 0 0 l {2 * half} 0 l {half} {half}{{\\p0}}"))
    rows_used = max((row for row, _, _ in placed), default=-1) + 1
    return events, rows_used


def transcript_events(
    segments: list[dict], shaky: list[dict], layout: Layout
) -> tuple[list[str], list[tuple[float, float, int]]]:
    """Returns the events and, per transcript line, (start, end, bubble rows used) for stacking corrections."""
    shaky_by_start = {round(word["start"], 2): word for word in shaky}
    lines = [line for segment in segments for line in split_into_lines(segment["words"], layout)]
    events, spans = [], []
    for index, line in enumerate(lines):
        start = line[0]["start"]
        next_start = lines[index + 1][0]["start"] if index + 1 < len(lines) else float("inf")
        end = min(line[-1]["end"] + LINE_LINGER_SECONDS, next_start)
        text = " ".join(
            f"{{\\c{ORANGE}\\u1}}{ass_escape(word['word'].strip())}{{\\u0\\c&HFFFFFF&}}"
            if round(word["start"], 2) in shaky_by_start else ass_escape(word["word"].strip())
            for word in line
        )
        events.append(dialogue(start, end, "Transcript",
                               f"{{\\an2\\pos({layout.width // 2},{layout.transcript_bottom - layout.transcript_padding})}}{text}"))
        bubbles, rows_used = bubble_events(line, shaky_by_start, start, end, layout)
        events += bubbles
        spans.append((start, end, rows_used))
    return events, spans


def bubble_rows_during(start: float, end: float, spans: list[tuple[float, float, int]]) -> int:
    return max((rows for line_start, line_end, rows in spans if line_start < end and start < line_end), default=0)


def correction_events(corrections: list[dict], spans: list[tuple[float, float, int]], layout: Layout) -> list[str]:
    corrections = sorted(corrections, key=lambda correction: correction["start"])
    next_starts = [correction["start"] for correction in corrections[1:]] + [float("inf")]
    events = []
    for correction, next_start in zip(corrections, next_starts):
        end = min(max(correction["end"], correction["start"] + MIN_SECONDS_ON_SCREEN), next_start)
        # Shrink long corrections so every line fits the frame width.
        widest = max(layout.correction_font.getlength(correction[key]) for key in ("said", "correct"))
        widest = max(widest, layout.correction_font.getlength(correction["why"]) * 0.75)
        size = round(layout.correction_size * min(1, layout.max_line_width / widest))
        said_style = "\\c&HF0C060&" if correction.get("translation") else "\\c&H5050FF&\\s1"
        text = (
            f"{{\\an2\\pos({layout.width // 2},{layout.correction_bottom(bubble_rows_during(correction['start'], end, spans))})"
            f"\\fs{size}}}"
            f"{{{said_style}}}{ass_escape(correction['said'])}{{\\s0}}\\N"
            f"{{\\c&H60E060&}}{ass_escape(correction['correct'])}\\N"
            f"{{\\c&HFFFFFF&\\fs{round(size * 0.75)}}}{ass_escape(correction['why'])}"
        )
        events.append(dialogue(correction["start"], end, "Fix", text))
    return events


def without_translated(shaky: list[dict], corrections: list[dict]) -> list[dict]:
    """English words said mid-speech already get a translation; don't also flag their pronunciation."""
    translated = [(c["start"], c["end"]) for c in corrections if c.get("translation")]
    return [word for word in shaky if not any(start <= word["start"] <= end for start, end in translated)]


def build_ass(events: list[str], layout: Layout) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {layout.width}
PlayResY: {layout.height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{layout.styles()}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"


def main() -> None:
    video = Path(sys.argv[1]).expanduser().resolve()
    corrections_path = Path(sys.argv[2]).expanduser().resolve()
    layout = Layout(*video_size(video))

    corrections = json.loads(corrections_path.read_text())
    events, spans = [], []
    transcript_path = corrections_path.with_name("transcript.json")
    shaky_path = corrections_path.with_name("shaky.json")
    if transcript_path.exists():
        shaky = json.loads(shaky_path.read_text()) if shaky_path.exists() else []
        events, spans = transcript_events(json.loads(transcript_path.read_text()), without_translated(shaky, corrections), layout)
    events += correction_events(corrections, spans, layout)

    ass_path = corrections_path.with_name("corrections.ass")
    inputs, video_filter, audio_filter = ["-i", str(video)], f"[0:v]ass={ass_path}[out]", "anull"
    end_screen_path = corrections_path.with_name("end_screen.json")
    if end_screen_path.exists():
        end_card_start = video_duration(video)
        end_card_path = corrections_path.with_name("end_card.png")
        render_end_card(corrections_path.parent, layout.width, layout.height).save(end_card_path)
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{end_card_start + END_SCREEN_SECONDS:.2f}", "-i", str(end_card_path)]
        video_filter = (
            f"[0:v]tpad=stop_mode=add:stop_duration={END_SCREEN_SECONDS},ass={ass_path}[base];"
            f"[1:v]format=rgba,fade=in:st={end_card_start:.2f}:d={END_CARD_FADE_SECONDS}:alpha=1[card];"
            f"[base][card]overlay=0:0:enable='gte(t,{end_card_start:.2f})'[out]"
        )
        audio_filter = f"apad=pad_dur={END_SCREEN_SECONDS}"

    ass_path.write_text(build_ass(events, layout))
    output = corrections_path.with_name("reviewed.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", video_filter, "-map", "[out]", "-map", "0:a",
         "-af", audio_filter, "-c:v", "h264_videotoolbox", "-b:v", "6M", "-c:a", "aac", str(output)],
        check=True,
    )
    print(output)


if __name__ == "__main__":
    main()
