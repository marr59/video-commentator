"""YouTube metadata formatting: title, slug, tags. Pure and deterministic."""

import re
from typing import List


def make_slug(topic: str) -> str:
    """Topic -> CamelCase hashtag slug. 'ocean waves sunset' -> 'OceanWavesSunset'."""
    return topic.title().replace(" ", "")


def first_sentence(script: str) -> str:
    """Return the first sentence of a narration script."""
    return re.split(r"(?<=[.!?])\s", script.strip())[0].strip()


def make_title(script: str, topic: str, limit: int = 100) -> str:
    """Build a YouTube title from the hook sentence plus a hashtag slug.

    Strips characters YouTube rejects in titles (``< > |``) and caps length.
    """
    hook = first_sentence(script)[:65]
    title = f"{hook} #{make_slug(topic)}"
    title = re.sub(r"[<>|]", "", title)
    return title[:limit]


def make_tags(topic: str) -> List[str]:
    """Base tags for a topic: its words plus the evergreen channel tags."""
    return topic.split() + ["Shorts", "Nature", "Travel"]
