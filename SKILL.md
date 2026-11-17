---
name: rewind
description: Daily speaking practice in a foreign language. Gives the learner 3 speaking topics to pick from; when they say "done", finds the recording, transcribes it locally, flags grammar mistakes and shaky pronunciation, burns them into a reviewed video with an end card (common errors, looked-up words, grade, 365-day progress chart), and opens it. Use for /rewind, "give me a topic to talk about", "review my speaking video", or "done" after a topic.
---

# Rewind: speak, then rewatch with corrections

`<skill>` below means this file's directory. Scripts run with `<skill>/.venv/bin/python <skill>/scripts/<name>.py`.

## Settings

Read `<skill>/settings.json` first (if it's missing, tell the learner to run `<skill>/setup.sh` and stop). It sets:
- `learner_name`: what to call the learner.
- `language` (Whisper code) / `language_name`: the language being practised. Topics, corrections, explanations and end-card labels are all written in this language.
- `variety`: the target variety, e.g. "Colombian Spanish". Suggest phrasing from that variety, never forms specific to other varieties, and don't flag that variety's normal pronunciation as an error.
- `level`: the CEFR level of the *language* the topics should demand, e.g. C1.
- `native_language`: the learner's first language; watch for calques from it.
- `sessions_folder`: where sessions are saved, one folder per day `<YYYY-MM-DD>` (`<date>-2`, `-3`… if that day already has a `reviewed.mp4`). It also holds `common-errors.json`, the learner's recurring-error memory.
- `recordings_folder`: where new recordings land (Photo Booth by default).
- `espeak_voice`, `whisper_prompt`, `flag_english_vowels`: used by the scripts directly.
- `extra_instructions`: anything else the learner wants done after each review. Follow it at the end of Step 2.

## Step 1: give 3 topics

1. Pick 3 topics with everyday subjects that demand `level` *language*, varied in theme: relatable and debatable, needing no specialist knowledge (no history/politics/academic themes; at higher levels, no basic routine description). Don't repeat any topic in `<sessions_folder>/*/topic.txt`.
2. Show them as a numbered list: the question in the target language plus one short line of sub-prompts that force structures typical of `level` (e.g. at C1: hypotheticals, subjunctive triggers, concession, hedging, register). Where `common-errors.json` has recurring errors, aim at least one topic at practising them.
3. Tell the learner: pick one, record 3-5 minutes (Photo Booth or anything that saves into `recordings_folder`), then say **done**. Stop and wait. They don't need to say which topic; work it out from the transcript.

## Step 2: on "done", run everything without asking

0. Clean up previous sessions: keep only the finished output, delete every intermediate file:
   `find <sessions_folder> -mindepth 2 -maxdepth 2 -type f ! -name reviewed.mp4 ! -name summary.md ! -name topic.txt ! -name grade.json -delete`
   (`grade.json` must stay: the 365-day chart is built from them.)
1. Video: newest video in `recordings_folder` (or a path the learner gives).
2. `transcribe.py "<video>" "<session>"` → `transcript.txt/json`, `pauses.json`. Work out which topic was chosen and write it to `<session>/topic.txt`.
3. `pronunciation.py "<video>" "<session>"` → `shaky.json`: words whose phonemes don't match what espeak expects, English vowels where pure vowels belong (if `flag_english_vowels`), or low Whisper confidence; repeats/restarts are skipped. Each entry's `why` is in English: rewrite every `why` in the target language (≤ 6 words) and save the file. You cannot hear audio, so pronunciation feedback is only what this file shows.
4. Write `<session>/corrections.json`: `[{"start", "end", "said", "correct", "why", "upgrade"}]`
   - Real errors: grammar, agreement, prepositions, verb forms, mood, calques from `native_language`, wrong word. Sparse upgrades to more natural phrasing get `"upgrade": true` (they don't count against the grade), with `why` starting with the target-language equivalent of "More natural:".
   - Times from word timestamps in transcript.json; `said`/`correct` short chunks; `why` in the target language, ≤ 8 words. No two within ~2s of each other.
   - Whisper sometimes tidies grammar: if the transcript looks suspiciously clean somewhere, don't invent errors.
5. Looked-up words: read `pauses.json`. A long pause (especially after fillers) followed by a content word = the learner looked that word up. For each, decide whether it fit what they meant; if not, give the better word with a short note on what the looked-up word really means.
6. Update `<sessions_folder>/common-errors.json` (`{id: {pattern, dates[], examples[]}}`): add today's date to patterns seen again, add new ones. Keep ids stable across sessions so the counts mean something.
7. Write `<session>/end_screen.json`:
   `{"errors": [{"pattern", "examples": [correct forms], "sessions": len(dates)}], "words": [{"looked_up", "better", "note"}], "labels": {...}}`
   - Max 4 errors (today's most frequent, recurring ones first), max 3 examples each. Keep patterns ≤ 30 characters and examples/notes ≤ 45 so they fit the column. If no word was looked up, use the best 1-2 vocabulary upgrades instead.
   - `labels`: every key of `DEFAULT_LABELS` in `scripts/settings.py`, translated into the target language (`times_seen` keeps its `{count}` placeholder; `months` is 12 short month names).
8. Grade: judge **range** 0-100 (CEFR-anchored: A2 20, B1 40, B2 60, C1 80, native 100) from the structures and vocabulary actually used, then `grade.py "<session>" <range>` → `grade.json` (overall % = accuracy 35%, range 25%, fluency 20%, pronunciation 20%). Judge range the same way every session so the trend means something.
9. `burn.py "<video>" "<session>/corrections.json"` → `<session>/reviewed.mp4`: a transcript along the bottom with shaky words in orange and a reason bubble above each, the correction just above that, and a 20s end card (topic, grade ring with sub-scores and change since last session, 365-day chart, common errors, looked-up words). Grab a mid frame and the last frame with ffmpeg and look at them before opening.
10. Write `<session>/summary.md` (patterns, what went well, pronunciation, looked-up words, phrases to use next time), then `open "<session>/reviewed.mp4"`.
11. Reply briefly: the grade (and change since last session), top patterns (flag recurring ones with their session count), looked-up words, one thing done well. Then follow `extra_instructions`, if set.
