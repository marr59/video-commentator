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


# --- reconcile_to_script: subtitles must be verbatim from the script ---------

from vcpipe.subtitles import reconcile_to_script, script_tokens


def _asr(*texts):
    """Build a Word stream with simple 0.5s slots from plain ASR strings."""
    return [Word(t, i * 0.5, i * 0.5 + 0.5) for i, t in enumerate(texts)]


def _norm_seq(text):
    import re
    return [re.sub(r"[^a-z0-9]", "", t.lower()) for t in text.split()]


def test_reconcile_fixes_terraced_terrorist():
    """The motivating incident: faster-whisper heard 'Terraced' as 'Terrorist'."""
    script = "Terraced rice fields are nature's stairway to the sky."
    asr = _asr("Terrorist", "rice", "fields", "are", "nature's",
              "to", "the", "sky")
    fixed = reconcile_to_script(asr, script)
    assert fixed[0].text == "Terraced"
    assert "Terrorist" not in " ".join(w.text for w in fixed)


def test_reconcile_fixes_mangled_place_name():
    script = "Cappadocia, Turkey is famous for hot air balloons."
    asr = _asr("Capodosia", "Turkey", "is", "famous", "for",
              "hot", "air", "balloons")
    fixed = reconcile_to_script(asr, script)
    assert fixed[0].text == "Cappadocia,"


def test_reconcile_output_is_verbatim_script():
    """Whatever the ASR said, the emitted words are exactly the script words."""
    script = "Some terraces are centuries old, hand-carved into mountainsides."
    asr = _asr("Some", "terrace", "our", "centuries", "old",
              "hand", "craved", "into", "mountain", "sides")
    fixed = reconcile_to_script(asr, script)
    assert [w.text for w in fixed] == script_tokens(script)


def test_reconcile_never_emits_word_absent_from_script():
    script = "Peaceful terraced valleys at dawn."
    asr = _asr("Peaceful", "Terrorist", "valleys", "at", "dawn")
    fixed = reconcile_to_script(asr, script)
    script_norm = set(_norm_seq(" ".join(script_tokens(script))))
    for w in fixed:
        import re
        assert re.sub(r"[^a-z0-9]", "", w.text.lower()) in script_norm


def test_reconcile_drops_hallucinated_words():
    script = "Golden dunes roll on."
    asr = _asr("Golden", "shiny", "dunes", "roll", "on")  # 'shiny' not in script
    fixed = reconcile_to_script(asr, script)
    assert [w.text for w in fixed] == ["Golden", "dunes", "roll", "on."]


def test_reconcile_inserts_missed_words():
    script = "The deep blue ocean."
    asr = _asr("The", "blue", "ocean")  # ASR skipped 'deep'
    fixed = reconcile_to_script(asr, script)
    assert [w.text for w in fixed] == ["The", "deep", "blue", "ocean."]


def test_reconcile_preserves_timings_for_aligned_words():
    script = "hello world"
    asr = [Word("hello", 1.0, 1.4), Word("world", 1.4, 2.2)]
    fixed = reconcile_to_script(asr, script)
    assert (fixed[0].start, fixed[0].end) == (1.0, 1.4)
    assert (fixed[1].start, fixed[1].end) == (1.4, 2.2)


def test_reconcile_empty_script_returns_unchanged():
    asr = _asr("anything", "goes")
    assert reconcile_to_script(asr, "") == asr


def test_reconcile_feeds_group_words_cleanly():
    """End-to-end: reconciled words group into cues carrying the fixed text."""
    script = "Terraced rice fields nature's stairway"
    asr = _asr("Terrorist", "rice", "fields", "nature's", "stairway")
    cues = group_words(reconcile_to_script(asr, script), per=5)
    assert cues[0][2] == "Terraced rice fields nature's stairway"
