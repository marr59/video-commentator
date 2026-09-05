"""Tests for subtitle grouping, SRT formatting and libass sizing."""

import pytest

from vcpipe.subtitles import (
    Word, group_words, format_timestamp, build_srt, libass_rendered_px,
)


def _words(*pairs):
    """Helper: build Words from (text, start, end) tuples."""
    return [Word(t, s, e) for t, s, e in pairs]


def test_group_words_exact_multiple():
    ws = _words(("a", 0.0, 0.5), ("b", 0.5, 1.0), ("c", 1.0, 1.5),
                ("d", 1.5, 2.0), ("e", 2.0, 2.5),
                ("f", 2.5, 3.0), ("g", 3.0, 3.5), ("h", 3.5, 4.0),
                ("i", 4.0, 4.5), ("j", 4.5, 5.0))
    cues = group_words(ws, per=5)
    assert len(cues) == 2
    assert cues[0] == (0.0, 2.5, "a b c d e")
    assert cues[1] == (2.5, 5.0, "f g h i j")


def test_group_words_partial_trailing_group():
    ws = _words(("a", 0.0, 0.5), ("b", 0.5, 1.0), ("c", 1.0, 1.5))
    cues = group_words(ws, per=5)
    assert len(cues) == 1
    start, end, text = cues[0]
    assert text == "a b c"
    assert start == 0.0
    assert end == pytest.approx(2.0)  # held 2s after first word


def test_group_words_cue_uses_first_start_and_last_end():
    ws = _words(("one", 1.2, 1.4), ("two", 1.4, 1.9), ("three", 1.9, 2.6),
                ("four", 2.6, 3.0), ("five", 3.0, 3.7))
    (start, end, _), = group_words(ws, per=5)
    assert start == 1.2
    assert end == 3.7


def test_group_words_strips_whitespace():
    ws = _words((" hi ", 0.0, 0.5), (" there ", 0.5, 1.0))
    (_, _, text), = group_words(ws, per=5)
    assert text == "hi there"


def test_group_words_empty():
    assert group_words([], per=5) == []


def test_group_words_invalid_per():
    with pytest.raises(ValueError):
        group_words([], per=0)


def test_format_timestamp_basic():
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(1.5) == "00:00:01,500"


def test_format_timestamp_hours_minutes():
    # 1h 1m 1s 250ms
    assert format_timestamp(3661.25) == "01:01:01,250"


def test_format_timestamp_negative_clamped():
    assert format_timestamp(-5) == "00:00:00,000"


def test_format_timestamp_millisecond_rounding_spill():
    # 0.9999s rounds to 1000ms -> must roll into the next second
    assert format_timestamp(0.9999) == "00:00:01,000"


def test_build_srt_structure():
    cues = [(0.0, 1.5, "hello world"), (1.5, 3.0, "second cue")]
    srt = build_srt(cues)
    expected = (
        "1\n00:00:00,000 --> 00:00:01,500\nhello world\n\n"
        "2\n00:00:01,500 --> 00:00:03,000\nsecond cue\n"
    )
    assert srt == expected


def test_build_srt_empty():
    assert build_srt([]) == ""


def test_libass_rendered_px_default_canvas():
    # The core caption-sizing fact: FontSize=9 on 1920p -> ~60px on screen.
    assert round(libass_rendered_px(9, 1920)) == 60


def test_libass_rendered_px_scales_with_height():
    assert libass_rendered_px(9, 3840) == pytest.approx(120.0)
    assert libass_rendered_px(18, 1920) == pytest.approx(120.0)


def test_config_font_size_is_readable():
    """Guardrail: the shipped FontSize must land in a sane on-screen range.

    This is the regression guard for the 'titanic subtitles' incident - a
    FontSize that renders far outside ~40-90px would fail here.
    """
    from vcpipe import config
    import re
    m = re.search(r"FontSize=(\d+)", config.SUBTITLE_STYLE)
    assert m, "SUBTITLE_STYLE must declare a FontSize"
    px = libass_rendered_px(int(m.group(1)), config.OUTPUT_H)
    assert 40 <= px <= 90, f"caption would render at {px:.0f}px (out of readable range)"
