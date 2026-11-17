"""Flag words that were probably pronounced badly.

Usage: .venv/bin/python scripts/pronunciation.py <video> <session dir>
(espeak voice, language and English-vowel check come from settings.json)
Needs <session>/transcript.json from transcribe.py. Writes <session>/shaky.json.

Two signals per word:
- Whisper's own confidence in the word.
- Phonemes actually heard (wav2vec2 phoneme model) vs the phonemes espeak expects for the word.
- English vowels (ə ɪ ʊ ʌ…) where a pure vowel should be: the classic English-speaker accent.
  Only meaningful for target languages without those vowels (flag_english_vowels in settings).
`why` is written in English; the skill translates it into the target language.
"""
import json
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

import numpy as np
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

from settings import load_settings

ESPEAK = shutil.which("espeak-ng") or shutil.which("espeak")
PHONEME_MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
SAMPLE_RATE = 16000
MIN_PHONEMES_TO_JUDGE = 3
MAX_PHONEME_ERROR_RATE = 0.5
MIN_WHISPER_PROBABILITY = 0.2
RESTART_WINDOW = 3
# Variants that shouldn't count as errors. The phoneme model writes ɡ for g in every language.
# English vowels (ə ɪ ʊ ʌ æ) are deliberately never here: those are the accent errors worth flagging.
UNIVERSAL_EQUIVALENTS = {"ɡ": "g"}
EQUIVALENTS_BY_LANGUAGE = {
    # Spanish allophones plus Latin American variants (seseo, aspirated j, b/v).
    "es": {
        "β": "b", "v": "b", "ð": "d", "ɣ": "g", "ɛ": "e", "ɔ": "o", "ʝ": "j", "ɟ": "j", "ʎ": "j",
        "ŋ": "n", "θ": "s", "x": "h", "r": "ɾ",
    },
    "it": {"ɛ": "e", "ɔ": "o", "ŋ": "n"},
    "pt": {"ɐ": "a", "ɛ": "e", "ɔ": "o", "ʁ": "x", "ɾ": "r"},
}
ENGLISH_VOWELS = {"ə", "ɪ", "ʊ", "ʌ", "æ", "ɐ", "ɜ", "ɚ", "ɑ", "ɒ"}
ENGLISH_VOWEL_NAMES = {
    "ə": "a relaxed English 'uh'", "ɐ": "a relaxed English 'uh'", "ʌ": "an English 'uh' (cup)",
    "ɪ": "a short English 'i' (sit)", "ʊ": "a short English 'u' (put)", "æ": "an English 'a' (cat)",
    "ɜ": "an English 'er'", "ɚ": "an English 'er'", "ɑ": "an English 'a' (father)", "ɒ": "an English 'o' (hot)",
}
VOWEL_LETTERS = {"a": "a", "e": "e", "ɛ": "e", "i": "i", "o": "o", "ɔ": "o", "u": "u"}
DIPHTHONGS = {"aɪ": ["a", "i"], "eɪ": ["e", "i"], "oɪ": ["o", "i"], "aʊ": ["a", "u"]}


def load_audio(video: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


FLAG_ENGLISH_VOWELS = load_settings().get("flag_english_vowels", True)
EQUIVALENT = {**UNIVERSAL_EQUIVALENTS, **EQUIVALENTS_BY_LANGUAGE.get(load_settings()["language"], {})}


def normalise(phoneme: str) -> str:
    return EQUIVALENT.get(phoneme, phoneme)


def tokenise(ipa: str, vocabulary: set[str]) -> list[str]:
    ipa = "".join(ch for ch in ipa if ch not in "ˈˌː ")
    tokens, position = [], 0
    while position < len(ipa):
        for length in (3, 2, 1):
            candidate = ipa[position:position + length]
            if candidate in vocabulary:
                tokens.append(candidate)
                position += length
                break
        else:
            position += 1
    return tokens


@cache
def expected_ipa(word: str, voice: str) -> str:
    return subprocess.run([ESPEAK, "-q", "--ipa", "-v", voice, word], capture_output=True, text=True).stdout.strip()


def align_by_word(
    expected: list[tuple[str, int]], heard: list[str], word_count: int
) -> tuple[list[int], list[list[str]], list[list[tuple[str, str]]]]:
    """Levenshtein-align expected phonemes (tagged with word index) to heard ones.

    Returns per word: number of errors, the heard phonemes aligned to it,
    and (expected, heard) pairs where a target-language sound came out as an English vowel.
    """
    rows, cols = len(expected) + 1, len(heard) + 1
    cost = np.zeros((rows, cols), dtype=int)
    cost[:, 0] = np.arange(rows)
    cost[0, :] = np.arange(cols)
    for i in range(1, rows):
        for j in range(1, cols):
            mismatch = normalise(expected[i - 1][0]) != normalise(heard[j - 1])
            cost[i, j] = min(cost[i - 1, j] + 1, cost[i, j - 1] + 1, cost[i - 1, j - 1] + mismatch)
    errors = [0] * word_count
    heard_per_word: list[list[str]] = [[] for _ in range(word_count)]
    english_swaps: list[list[tuple[str, str]]] = [[] for _ in range(word_count)]
    i, j = rows - 1, cols - 1
    while i > 0 or j > 0:
        word_index = expected[max(i - 1, 0)][1] if expected else 0
        mismatch = i > 0 and j > 0 and normalise(expected[i - 1][0]) != normalise(heard[j - 1])
        if i > 0 and j > 0 and cost[i, j] == cost[i - 1, j - 1] + mismatch:
            errors[word_index] += mismatch
            heard_per_word[word_index].insert(0, heard[j - 1])
            if heard[j - 1] in ENGLISH_VOWELS and FLAG_ENGLISH_VOWELS:
                english_swaps[word_index].insert(0, (expected[i - 1][0], heard[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and cost[i, j] == cost[i - 1, j] + 1:
            errors[word_index] += 1
            i -= 1
        else:
            j -= 1  # extra heard phoneme: usually bleed from a neighbouring word, so not attributed
    return errors, heard_per_word, english_swaps


def explain(english_swaps: list[tuple[str, str]], heard: list[str], whisper_unsure: bool) -> str:
    for expected_phoneme, heard_phoneme in english_swaps:
        letter = VOWEL_LETTERS.get(expected_phoneme)
        if letter:
            return f"'{letter}' sounded like {ENGLISH_VOWEL_NAMES[heard_phoneme]}"
    if english_swaps:
        return f"Heard {ENGLISH_VOWEL_NAMES[english_swaps[0][1]]}"
    if whisper_unsure:
        return "Unclear"
    return f"Heard '{''.join(heard)}'"


def clean(word: str) -> str:
    return word.strip().strip(".,¿?¡!…;:\"'").lower()


def main() -> None:
    video = Path(sys.argv[1]).expanduser().resolve()
    session = Path(sys.argv[2]).expanduser().resolve()
    settings = load_settings()
    voice = settings["espeak_voice"]
    segments = json.loads((session / "transcript.json").read_text())

    processor = Wav2Vec2Processor.from_pretrained(PHONEME_MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(PHONEME_MODEL).eval()
    vocabulary = set(processor.tokenizer.get_vocab())
    audio = load_audio(video)

    shaky = []
    recent_words: list[str] = []
    for segment in segments:
        words = [w for w in segment["words"] if clean(w["word"])]
        if not words:
            continue
        start = max(0, int((words[0]["start"] - 0.1) * SAMPLE_RATE))
        end = int((words[-1]["end"] + 0.1) * SAMPLE_RATE)
        inputs = processor(audio[start:end], sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with torch.no_grad():
            ids = model(inputs.input_values).logits.argmax(-1)
        heard = [
            part
            for phoneme in processor.batch_decode(ids)[0].replace("ː", "").split()
            for part in DIPHTHONGS.get(phoneme, [phoneme])
        ]

        expected_per_word = [tokenise(expected_ipa(clean(w["word"]), voice), vocabulary) for w in words]
        expected = [(p, index) for index, phonemes in enumerate(expected_per_word) for p in phonemes]
        errors, heard_per_word, swaps_per_word = align_by_word(expected, heard, len(words))

        for word, phonemes, error_count, word_heard, english_swaps in zip(
            words, expected_per_word, errors, heard_per_word, swaps_per_word
        ):
            # Restarts like "yo, yo" or "mis amigos, mis amigos" aren't pronunciation problems.
            is_repeat = clean(word["word"]) in recent_words
            recent_words = (recent_words + [clean(word["word"])])[-RESTART_WINDOW:]
            if is_repeat:
                continue
            error_rate = error_count / len(phonemes) if phonemes else 0
            sounds_off = len(phonemes) >= MIN_PHONEMES_TO_JUDGE and error_rate >= MAX_PHONEME_ERROR_RATE
            whisper_unsure = word["probability"] < MIN_WHISPER_PROBABILITY
            if sounds_off or english_swaps or whisper_unsure:
                shaky.append({
                    "word": word["word"].strip(), "start": word["start"], "end": word["end"],
                    "expected": "".join(phonemes), "heard": "".join(word_heard),
                    "why": explain(english_swaps, word_heard, whisper_unsure), "error_rate": round(error_rate, 2),
                    "whisper_probability": round(word["probability"], 2),
                })
        print(f"[{segment['start']:.1f}] heard: {' '.join(heard)}")

    (session / "shaky.json").write_text(json.dumps(shaky, ensure_ascii=False, indent=2))
    print(f"{len(shaky)} shaky words")


if __name__ == "__main__":
    main()
