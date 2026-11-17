# ⏪ rewind

Record yourself speaking a foreign language, then rewatch the video with your mistakes on screen.

`rewind` is a [Claude Code](https://claude.com/claude-code) skill. Run `/rewind` and it gives you three topics to talk about. Pick one, record a few minutes, and say **done**. A few minutes later a new video opens. It's your recording, with:

- **Corrections at the moment you made them:** what you said in red, the fix in green, and a short reason.
- **A running transcript:** words you probably mispronounced are in orange, each with a bubble saying what sounded off.
- **An end card** showing:
  - your most common errors (and how many sessions they've come up in)
  - the words you paused to look up, and whether there was a better one
  - today's grade from 0 to 100%
  - a chart of your grade over the last 365 days

Speech recognition, pronunciation analysis and video rendering all run on your Mac. Claude reads the transcript to write the corrections, just as it reads anything else in your session.

## How it works

| Step | Tool |
|---|---|
| Transcribe with word timestamps | [Whisper large-v3-turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo) on MLX |
| Find shaky words | [wav2vec2 phoneme model](https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft) (what you said) vs [espeak-ng](https://github.com/espeak-ng/espeak-ng) (what a native says), aligned per word |
| Spot looked-up words | Silences of 2s or more before a content word |
| Write the corrections, topics and grade | Claude, following `SKILL.md` |
| Burn it into the video | ffmpeg + libass subtitles, Pillow for the chart |

The grade is 35% accuracy (errors per 100 words), 25% range (Claude's CEFR-anchored judgement), 20% fluency (speaking speed and long pauses) and 20% pronunciation (shaky words per 100 words). 0% means you don't speak the language and 100% means native.

## Languages

🇪🇸 Spanish · 🇫🇷 French · 🇩🇪 German · 🇮🇹 Italian · 🇧🇷 Portuguese · 🇳🇱 Dutch · 🇵🇱 Polish · 🇷🇺 Russian · 🇺🇦 Ukrainian · 🇸🇪 Swedish · 🇳🇴 Norwegian · 🇩🇰 Danish · 🇹🇷 Turkish · 🇬🇷 Greek · 🇯🇵 Japanese · 🇰🇷 Korean · 🇨🇳 Mandarin · 🇮🇩 Indonesian · 🇻🇳 Vietnamese · 🇮🇳 Hindi

## Requirements

- A Mac with Apple Silicon (Whisper runs on MLX)
- [Homebrew](https://brew.sh), Python 3.10+
- [Claude Code](https://claude.com/claude-code)
- About 3 GB of disk space for the models, which download on first run

## Install

```sh
git clone https://github.com/AlexCyphus/rewind ~/.claude/skills/rewind
~/.claude/skills/rewind/setup.sh
```

`setup.sh` installs ffmpeg and espeak-ng if they're missing, creates a `.venv` inside the skill folder, and copies `settings.example.json` to `settings.json`.

## Settings

Edit `settings.json`:

| Key | Example | What it does |
|---|---|---|
| `learner_name` | `"Sam"` | What Claude calls you |
| `language` | `"es"` | [Whisper language code](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py) |
| `language_name` | `"Spanish"` | Shown in prompts |
| `variety` | `"Colombian Spanish"` | Corrections use this variety's phrasing, and its normal accent isn't flagged |
| `level` | `"C1"` | The CEFR level the topics demand (the language, not the subject) |
| `native_language` | `"English"` | Claude watches for calques from it |
| `espeak_voice` | `"es-419"` | Reference pronunciation. List voices with `espeak-ng --voices=<lang>`, e.g. `fr-fr`, `pt-br`, `de`, `it`, `ja` |
| `sessions_folder` | `"~/Desktop/Rewind"` | One folder per day, plus your error log and progress chart |
| `recordings_folder` | Photo Booth library | Where to look for the newest recording |
| `whisper_prompt` | `"Eh, pues... o sea, este..."` | Fillers in your language. They stop Whisper tidying up your grammar. |
| `flag_english_vowels` | `true` | Flag English vowels (*uh*, short *i*/*u*). Turn off for languages that have them, e.g. French, German, Portuguese, Dutch, Russian |
| `extra_instructions` | `"Add the corrections to my Anki deck"` | Anything else to do after each review |

## Usage

1. Run `/rewind` in Claude Code. You get three topics.
2. Record yourself answering one of them for 3–5 minutes in Photo Booth.
3. Say **done**.

Each session is saved in `<sessions_folder>/<date>/`. Next time you say **done**, the previous sessions are trimmed to `reviewed.mp4`, `summary.md`, `topic.txt` and `grade.json`, so the folder stays small.

## License

MIT
