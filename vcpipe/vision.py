"""Vision-analysis helpers: parse structured replies and decide whether a
single specific location is confidently identifiable across the clips.

Pure and deterministic — the network call to the vision model lives in
``pipeline.py``. Keeping the parsing/consensus logic here makes the core
content-integrity guard testable: *never caption a montage with a place the
footage does not actually, consistently show.*
"""

import re
from collections import Counter
from typing import Optional, Sequence, Tuple

# Values that mean "no identifiable place" in a vision reply.
_UNKNOWN = {
    "UNKNOWN", "N/A", "NONE", "UNIDENTIFIED",
    "NOT CLEAR", "NOT IDENTIFIABLE", "UNSURE", "",
}


def parse_vision_reply(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a two-line vision reply into ``(location, description)``.

    Expected shape::

        LOCATION: <place name or UNKNOWN>
        DESC: <one sentence>

    ``location`` is ``None`` when the model returned UNKNOWN (or a synonym),
    which is the signal that the script must stay generic and truthful.
    """
    loc, desc = None, None
    for line in text.splitlines():
        s = line.strip()
        up = s.upper()
        if up.startswith("LOCATION:"):
            v = s.split(":", 1)[1].strip().strip(".")
            if v.upper() not in _UNKNOWN:
                loc = v
        elif up.startswith("DESC:"):
            desc = s.split(":", 1)[1].strip()
    return loc, desc


def _norm(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def consensus_location(locations: Sequence[str], n_frames: int) -> Optional[str]:
    """Return a place name only if a clear majority of frames agree on it.

    A single frame naming a landmark is **not** enough to caption the whole
    montage — the other clips may be somewhere else entirely (the failure mode
    this guards against: footage of New York/Toronto narrated as "Bangkok").
    Require at least half the frames, and at least 2, to agree on the same
    normalized name.
    """
    if not locations:
        return None
    counts = Counter(_norm(l) for l in locations)
    top_norm, top_n = counts.most_common(1)[0]
    if top_n >= max(2, (n_frames + 1) // 2):
        for l in locations:
            if _norm(l) == top_norm:
                return l
    return None
