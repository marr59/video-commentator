"""Tests for topic / clip deduplication logic."""

from vcpipe import config
from vcpipe.dedup import available_topics, next_topic_pool, trim_memory, fresh_clips


def test_available_topics_excludes_used():
    all_t = ["a", "b", "c", "d"]
    assert available_topics(all_t, {"b", "d"}) == ["a", "c"]


def test_available_topics_preserves_order():
    all_t = ["z", "y", "x"]
    assert available_topics(all_t, {"y"}) == ["z", "x"]


def test_next_topic_pool_returns_unused_when_available():
    all_t = ["a", "b", "c"]
    assert next_topic_pool(all_t, {"a"}) == ["b", "c"]


def test_next_topic_pool_resets_when_all_used():
    all_t = ["a", "b", "c"]
    # every topic used -> rotation resets to the full list
    assert next_topic_pool(all_t, {"a", "b", "c"}) == ["a", "b", "c"]


def test_next_topic_pool_never_empty_on_real_config():
    # even if the caller somehow marked everything used, we still get a pool
    assert next_topic_pool(config.TOPICS, set(config.TOPICS)) == list(config.TOPICS)


def test_trim_memory_caps_to_limit():
    items = [str(i) for i in range(100)]
    out = trim_memory(items, 60)
    assert len(out) == 60


def test_trim_memory_keeps_most_recent_sorted():
    # sorted order is lexical; keep the last `limit` of the sorted unique set
    items = ["01", "02", "03", "04", "05"]
    assert trim_memory(items, 3) == ["03", "04", "05"]


def test_trim_memory_deduplicates():
    assert trim_memory(["a", "a", "b", "b", "b"], 10) == ["a", "b"]


def test_trim_memory_under_limit_returns_all_sorted():
    assert trim_memory(["c", "a", "b"], 10) == ["a", "b", "c"]


def test_fresh_clips_prefers_unused():
    ids = ["1", "2", "3", "4", "5"]
    # 3 fresh (3,4,5) is enough for need=2 -> return only fresh
    assert fresh_clips(ids, {"1", "2"}, need=2) == ["3", "4", "5"]


def test_fresh_clips_falls_back_when_not_enough_fresh():
    ids = ["1", "2", "3"]
    # only "3" is fresh but we need 2 -> fall back to full candidate list
    assert fresh_clips(ids, {"1", "2"}, need=2) == ["1", "2", "3"]
