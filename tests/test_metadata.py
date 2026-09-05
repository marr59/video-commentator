"""Tests for YouTube metadata formatting."""

from vcpipe.metadata import make_slug, first_sentence, make_title, make_tags


def test_make_slug_camelcases():
    assert make_slug("ocean waves sunset") == "OceanWavesSunset"
    assert make_slug("volcano") == "Volcano"


def test_first_sentence_splits_on_punctuation():
    script = "This is Whitehaven Beach, Australia. It has the whitest sand on Earth!"
    assert first_sentence(script) == "This is Whitehaven Beach, Australia."


def test_first_sentence_single_sentence():
    assert first_sentence("Just one line with no terminator") == "Just one line with no terminator"


def test_make_title_combines_hook_and_slug():
    script = "This is Mount Bromo, Indonesia. An active volcano."
    title = make_title(script, "volcano")
    assert title.startswith("This is Mount Bromo, Indonesia.")
    assert title.endswith("#Volcano")


def test_make_title_strips_invalid_chars():
    script = "Look <at> this | place. More text."
    title = make_title(script, "coral reef underwater")
    assert "<" not in title and ">" not in title and "|" not in title


def test_make_title_respects_length_limit():
    script = "A" * 200 + ". tail"
    title = make_title(script, "dubai skyline")
    assert len(title) <= 100


def test_make_tags_includes_topic_words_and_defaults():
    tags = make_tags("northern lights")
    assert "northern" in tags and "lights" in tags
    assert {"Shorts", "Nature", "Travel"}.issubset(set(tags))
