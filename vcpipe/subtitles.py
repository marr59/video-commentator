"""Subtitle generation: word-level timestamps -> grouped SRT cues.

All functions here are pure and deterministic. The only non-deterministic part
of the real pipeline is the speech-to-text model itself (faster-whisper), which
produces the word list consumed by ``group_words``.
"""

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
