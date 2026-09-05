"""Deterministic topic / clip deduplication logic.

Kept pure (no file or network I/O) so it can be unit-tested. The pipeline wraps
these with tiny JSON-file loaders in ``pipeline.py``.
"""

from typing import Iterable, List, Sequence, Set


def available_topics(all_topics: Sequence[str], used: Iterable[str]) -> List[str]:
    """Topics not yet used. Order-preserving w.r.t. ``all_topics``."""
    used_set = set(used)
    return [t for t in all_topics if t not in used_set]


def next_topic_pool(all_topics: Sequence[str], used: Iterable[str]) -> List[str]:
    """The pool to pick from.

    Returns the unused topics; if every topic has been used, the rotation
    resets and the full list becomes available again (so the pipeline never
    stalls). The caller does the random pick.
    """
    pool = available_topics(all_topics, used)
    return pool if pool else list(all_topics)


def trim_memory(items: Iterable[str], limit: int) -> List[str]:
    """Cap a rolling-memory set to the ``limit`` most-recent (sorted) entries.

    Mirrors the on-disk behaviour: de-duplicate, sort for stable output, and
    keep at most ``limit`` items.
    """
    unique = sorted(set(items))
    if len(unique) <= limit:
        return unique
    return unique[-limit:]


def fresh_clips(hits_ids: Sequence[str], used: Iterable[str], need: int) -> List[str]:
    """Given candidate clip ids and the used set, return the ids to prefer.

    Prefers clips never used before; only falls back to the full candidate list
    when there are not enough fresh ones to satisfy ``need``.
    """
    used_set = set(used)
    fresh = [h for h in hits_ids if h not in used_set]
    return fresh if len(fresh) >= need else list(hits_ids)
