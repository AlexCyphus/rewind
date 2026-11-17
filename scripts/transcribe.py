"""Transcribe a speaking video locally with Whisper (language and filler prompt from settings.json).

Usage: .venv/bin/python scripts/transcribe.py <video> <session dir>
Writes <session>/transcript.json, <session>/transcript.txt and <session>/pauses.json
(long silences, usually a word being looked up).
"""
import json
import sys
from pathlib import Path

import mlx_whisper

from settings import load_settings

MODEL = "mlx-community/whisper-large-v3-turbo"
MIN_LOOKUP_PAUSE_SECONDS = 2.0


def transcribe(video: Path, settings: dict) -> dict:
    return mlx_whisper.transcribe(
        str(video),
        path_or_hf_repo=MODEL,
        language=settings["language"],
        word_timestamps=True,
        condition_on_previous_text=False,
        # A disfluent prompt in the target language nudges Whisper to keep what was actually said
        # instead of tidying the grammar.
        initial_prompt=settings.get("whisper_prompt"),
    )


def format_timestamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"


def long_pauses(segments: list[dict]) -> list[dict]:
    words = [word for segment in segments for word in segment["words"]]
    return [
        {"at": after["start"], "seconds": round(after["start"] - before["end"], 1),
         "before": " ".join(w["word"].strip() for w in words[max(0, index - 4):index + 1]),
         "after": " ".join(w["word"].strip() for w in words[index + 1:index + 5])}
        for index, (before, after) in enumerate(zip(words, words[1:]))
        if after["start"] - before["end"] >= MIN_LOOKUP_PAUSE_SECONDS
    ]


def main() -> None:
    video = Path(sys.argv[1]).expanduser().resolve()
    session = Path(sys.argv[2]).expanduser()
    session.mkdir(parents=True, exist_ok=True)

    result = transcribe(video, load_settings())
    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip(), "words": s.get("words", [])}
        for s in result["segments"]
    ]
    (session / "transcript.json").write_text(json.dumps(segments, ensure_ascii=False, indent=2))
    lines = [f"[{format_timestamp(s['start'])}-{format_timestamp(s['end'])}] {s['text']}" for s in segments]
    (session / "transcript.txt").write_text("\n".join(lines) + "\n")
    (session / "pauses.json").write_text(json.dumps(long_pauses(segments), ensure_ascii=False, indent=2))
    print(session)


if __name__ == "__main__":
    main()
