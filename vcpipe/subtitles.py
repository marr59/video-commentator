"""Subtitle generation: word-level timestamps -> grouped SRT cues.

All functions here are pure and deterministic. The only non-deterministic part
of the real pipeline is the speech-to-text model itself (faster-whisper), which
produces the word list consumed by ``group_words``.
"""

import difflib
import re
from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class Word:
    """A single transcribed word with its start/end time in seconds."""
    text: str
    start: float
    end: float


# (start_seconds, end_seconds, text)
Cue = Tuple[float, float, str]


def group_words(words: Sequence[Word], per: int = 5) -> List[Cue]:
    """Group a flat word stream into on-screen cues of ``per`` words each.

    - The cue start time is the start of its first word.
    - The cue end time is the end of its last word.
    - A trailing partial group (fewer than ``per`` words) is still emitted, held
      on screen for 2 seconds after its first word so it never flashes by.
    """
    if per < 1:
        raise ValueError("per must be >= 1")

    cues: List[Cue] = []
    buf: List[Word] = []
    for w in words:
        buf.append(w)
        if len(buf) >= per:
            cues.append((buf[0].start, buf[-1].end, " ".join(x.text.strip() for x in buf)))
            buf = []
    if buf:
        cues.append((buf[0].start, buf[0].start + 2.0, " ".join(x.text.strip() for x in buf)))
    return cues


def format_timestamp(seconds: float) -> str:
    """Seconds -> ``HH:MM:SS,mmm`` SRT timestamp."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:  # rounding spill
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(cues: Sequence[Cue]) -> str:
    """Render grouped cues into a valid SRT document."""
    blocks = []
    for i, (start, end, text) in enumerate(cues, 1):
        blocks.append(f"{i}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n")
    return "\n".join(blocks)


def libass_rendered_px(font_size: float, frame_height: int, play_res_y: int = 288) -> float:
    """On-screen glyph height libass produces for an SRT ``FontSize``.

    libass renders SRT on a virtual canvas of height ``play_res_y`` (288 by
    default) and scales to the real frame height. This is *the* fact that makes
    caption sizing predictable: FontSize is not pixels.

    >>> round(libass_rendered_px(9, 1920))
    60
    """
    return font_size * (frame_height / play_res_y)


# Word-like tokens keep straight/curly apostrophes so contractions stay intact.
_WORD_RE = re.compile(r"[A-Za-z0-9\u2019']+[^\sA-Za-z0-9\u2019']*")


def _normalize(token: str) -> str:
    """Fold a token to bare ``[a-z0-9]`` for order-preserving matching.

    Apostrophes (straight or curly), case and punctuation are dropped so that
    ``"Nature\u2019s"``, ``"nature's"`` and ``"natures"`` all compare equal.
    """
    return re.sub(r"[^a-z0-9]", "", token.lower())


def script_tokens(script: str) -> List[str]:
    """Split an authoritative script into display tokens (word + trailing punct)."""
    return _WORD_RE.findall(script)


def reconcile_to_script(words: Sequence[Word], script: str) -> List[Word]:
    """Rewrite ASR ``words`` so the on-screen text is drawn verbatim from ``script``.

    The subtitle text in the real pipeline comes from re-transcribing the TTS
    audio with faster-whisper, which occasionally mishears a word -- the
    ``"Terraced" -> "Terrorist"`` incident being the motivating example. Since
    the narration script is authoritative, we align the ASR token stream to the
    script tokens with :class:`difflib.SequenceMatcher` and emit the *script*
    tokens carrying the ASR timings. The result can only ever contain words that
    appear in ``script``, so a mistranscription can never reach the screen.

    Timings are preserved for aligned words; for replaced or inserted spans they
    are interpolated across the corresponding ASR time range. Words the model
    hallucinated (present in ASR, absent from the script) are dropped.

    Returns a fresh, time-sorted list of :class:`Word`. If ``script`` has no
    tokens the input is returned unchanged.
    """
    disp = _WORD_RE.findall(script)
    if not disp or not words:
        return list(words)

    script_norm = [_normalize(d) for d in disp]
    asr_norm = [_normalize(w.text) for w in words]
    matcher = difflib.SequenceMatcher(a=asr_norm, b=script_norm, autojunk=False)

    out: List[Word] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                w = words[i1 + k]
                out.append(Word(disp[j1 + k], w.start, w.end))
        elif tag == "replace":
            nb = j2 - j1
            t0 = words[i1].start
            t1 = words[i2 - 1].end
            span = max(t1 - t0, 0.2)
            for m in range(nb):
                out.append(Word(disp[j1 + m], t0 + span * m / nb, t0 + span * (m + 1) / nb))
        elif tag == "insert":
            anchor = words[i1].start if i1 < len(words) else (out[-1].end if out else 0.0)
            for m in range(j2 - j1):
                out.append(Word(disp[j1 + m], anchor, anchor))
        # tag == "delete": ASR heard words the script never had -> drop them
    out.sort(key=lambda w: w.start)
    return out
