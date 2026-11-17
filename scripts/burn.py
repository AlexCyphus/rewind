"""Burn corrections into a copy of the video as subtitles.

Usage: .venv/bin/python scripts/burn.py <video> <corrections.json>
corrections.json: [{"start": 12.3, "end": 15.0, "said": "...", "correct": "...", "why": "..."}]
Writes reviewed.mp4 next to corrections.json.

Layout, bottom to top, so the eyes stay in one place:
- running transcript (from transcript.json), one line at a time, shaky words in orange
- a speech bubble above each shaky word saying why (from shaky.json)
- the current correction
If end_screen.json sits next to it, appends an end card (plus today's grade and the
365-day chart when grade.json and progress.png from grade.py are there too):
{"errors": [{"pattern": "...", "examples": ["said → correct"], "sessions": 2}],
 "words": [{"looked_up": "esquema", "better": "una idea", "note": "..."}],
 "labels": {...end card headings in the target language, see settings.DEFAULT_LABELS}}
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

from settings import end_card_labels

FONT_FILE = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_NAME = "Helvetica Neue"
MIN_SECONDS_ON_SCREEN = 4.0
LINE_LINGER_SECONDS = 1.0
END_SCREEN_SECONDS = 20
END_CARD_BACKGROUND = "0x1a1a19"
CHART_SIZE = (660, 380)
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
        self.correction_bottom = self.bubble_bottom - self.bubble_row_height - round(height / 60)
        self.max_line_width = width * 0.9
        self.transcript_font = ImageFont.truetype(FONT_FILE, self.transcript_size)
        self.bubble_font = ImageFont.truetype(FONT_FILE, self.bubble_size)

    def styles(self) -> str:
        def style(name, size, primary, outline, border_style, outline_width):
            return (f"Style: {name},{FONT_NAME},{size},{primary},&H00FFFFFF,{outline},&HB0000000,"
                    f"0,0,0,0,100,100,0,0,{border_style},{outline_width},0,2,0,0,0,1")
        return "\n".join([
            style("Transcript", self.transcript_size, "&H00FFFFFF", "&H00000000", 3, self.transcript_padding),
            style("Bubble", self.bubble_size, "&H00000000", "&H0000A5FF", 3, self.bubble_padding),
            style("Pointer", 1, "&H0000A5FF", "&H00000000", 1, 0),
            style("EndCard", self.transcript_size, "&H00FFFFFF", "&H00000000", 1, 0),
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


def bubble_events(line: list[dict], shaky_by_start: dict, start: float, end: float, layout: Layout) -> list[str]:
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
    return events


def transcript_events(segments: list[dict], shaky: list[dict], layout: Layout) -> list[str]:
    shaky_by_start = {round(word["start"], 2): word for word in shaky}
    lines = [line for segment in segments for line in split_into_lines(segment["words"], layout)]
    events = []
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
        events += bubble_events(line, shaky_by_start, start, end, layout)
    return events


def correction_events(corrections: list[dict], layout: Layout) -> list[str]:
    corrections = sorted(corrections, key=lambda correction: correction["start"])
    next_starts = [correction["start"] for correction in corrections[1:]] + [float("inf")]
    small = round(layout.correction_size * 0.75)
    events = []
    for correction, next_start in zip(corrections, next_starts):
        end = min(max(correction["end"], correction["start"] + MIN_SECONDS_ON_SCREEN), next_start)
        text = (
            f"{{\\an2\\pos({layout.width // 2},{layout.correction_bottom})}}"
            f"{{\\c&H5050FF&\\s1}}{ass_escape(correction['said'])}{{\\s0}}\\N"
            f"{{\\c&H60E060&}}{ass_escape(correction['correct'])}\\N"
            f"{{\\c&HFFFFFF&\\fs{small}}}{ass_escape(correction['why'])}"
        )
        events.append(dialogue(correction["start"], end, "Fix", text))
    return events


def end_card_margin(layout: Layout) -> int:
    return round(layout.width / 16)


def chart_position(layout: Layout) -> tuple[int, int]:
    margin = end_card_margin(layout)
    column = (layout.width - 3 * margin) // 2
    return 2 * margin + column, layout.height - round(layout.height / 18) - CHART_SIZE[1]


def grade_event(grade: dict, labels: dict, start: float, layout: Layout) -> str:
    x, chart_top = chart_position(layout)
    title = round(layout.height / 15)
    small = round(layout.height / 34)
    text = (
        f"{{\\an1\\pos({x},{chart_top - round(layout.height / 40)})}}"
        f"{{\\fs{title}\\b1}}{ass_escape(labels['grade'])}: {grade['overall']}%{{\\b0}}\\N"
        f"{{\\fs{small}\\c&HB7C2C3&}}{ass_escape(labels['accuracy'])} {grade['accuracy']} · "
        f"{ass_escape(labels['range'])} {grade['range']}\\N"
        f"{ass_escape(labels['fluency'])} {grade['fluency']} · {ass_escape(labels['pronunciation'])} {grade['pronunciation']}"
    )
    return dialogue(start, start + END_SCREEN_SECONDS, "EndCard", text)


def end_screen_events(end_screen: dict, labels: dict, start: float, layout: Layout) -> list[str]:
    end = start + END_SCREEN_SECONDS
    title = round(layout.height / 15)
    body = round(layout.height / 26)
    small = round(layout.height / 34)
    gap = f"{{\\fs{round(small / 2)}}}\\h"
    margin = end_card_margin(layout)
    top = round(layout.height / 10)
    column = (layout.width - 3 * margin) // 2

    error_lines = [f"{{\\fs{title}\\b1}}{ass_escape(labels['errors'])}{{\\b0}}", gap]
    for index, error in enumerate(end_screen["errors"], 1):
        times_seen = labels["times_seen"].format(count=error.get("sessions", 1))
        repeat = f"  {{\\c{ORANGE}}}· {ass_escape(times_seen)}{{\\c&HFFFFFF&}}" if error.get("sessions", 1) > 1 else ""
        error_lines.append(f"{{\\fs{body}}}{index}. {ass_escape(error['pattern'])}{repeat}")
        error_lines += [f"{{\\fs{small}\\c&HBBBBBB&}}\\h\\h\\h\\h{ass_escape(example)}{{\\c&HFFFFFF&}}" for example in error["examples"]]
        error_lines.append(gap)

    word_lines = [f"{{\\fs{title}\\b1}}{ass_escape(labels['words'])}{{\\b0}}", gap]
    for word in end_screen["words"]:
        word_lines.append(
            f"{{\\fs{body}\\c&H5050FF&}}{ass_escape(word['looked_up'])}{{\\c&HFFFFFF&}} → "
            f"{{\\c&H60E060&}}{ass_escape(word['better'])}{{\\c&HFFFFFF&}}"
        )
        word_lines.append(f"{{\\fs{small}\\c&HBBBBBB&}}{ass_escape(word['note'])}{{\\c&HFFFFFF&}}")
        word_lines.append(gap)

    return [
        dialogue(start, end, "EndCard", f"{{\\an7\\pos({margin},{top})}}" + "\\N".join(error_lines)),
        dialogue(start, end, "EndCard", f"{{\\an7\\pos({2 * margin + column},{top})}}" + "\\N".join(word_lines)),
    ]


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

    events = correction_events(json.loads(corrections_path.read_text()), layout)
    transcript_path = corrections_path.with_name("transcript.json")
    shaky_path = corrections_path.with_name("shaky.json")
    if transcript_path.exists():
        shaky = json.loads(shaky_path.read_text()) if shaky_path.exists() else []
        events = transcript_events(json.loads(transcript_path.read_text()), shaky, layout) + events

    ass_path = corrections_path.with_name("corrections.ass")
    inputs, video_filter, audio_filter = ["-i", str(video)], f"[0:v]ass={ass_path}[out]", "anull"
    end_screen_path = corrections_path.with_name("end_screen.json")
    if end_screen_path.exists():
        end_card_start = video_duration(video)
        labels = end_card_labels(corrections_path.parent)
        events += end_screen_events(json.loads(end_screen_path.read_text()), labels, end_card_start, layout)
        video_filter = (f"[0:v]tpad=stop_mode=add:stop_duration={END_SCREEN_SECONDS}:color={END_CARD_BACKGROUND},"
                        f"ass={ass_path}[out]")
        audio_filter = f"apad=pad_dur={END_SCREEN_SECONDS}"
        grade_path = corrections_path.with_name("grade.json")
        chart_path = corrections_path.with_name("progress.png")
        if grade_path.exists() and chart_path.exists():
            events.append(grade_event(json.loads(grade_path.read_text()), labels, end_card_start, layout))
            x, y = chart_position(layout)
            inputs += ["-i", str(chart_path)]
            video_filter = (video_filter.removesuffix("[out]") + "[base];"
                            f"[base][1:v]overlay={x}:{y}:enable='gte(t,{end_card_start:.2f})'[out]")

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
