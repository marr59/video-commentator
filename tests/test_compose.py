"""Tests for FFmpeg filter_complex and command construction."""

import pytest

from vcpipe import config
from vcpipe.compose import build_filtergraph, build_ffmpeg_command


def test_filtergraph_has_one_scale_per_clip():
    graph = build_filtergraph(4, "subs.srt")
    assert graph.count("scale=-2:1920") == 4
    for i in range(4):
        assert f"[{i}:v]scale=-2:1920,crop=1080:1920" in graph


def test_filtergraph_concat_count_matches():
    graph = build_filtergraph(3, "subs.srt")
    assert "concat=n=3:v=1:a=0" in graph
    assert "[c0][c1][c2]concat" in graph


def test_filtergraph_burns_subtitles_last():
    graph = build_filtergraph(2, "my subs.srt")
    assert graph.strip().endswith("[vout]")
    assert "subtitles=my subs.srt:force_style=" in graph
    assert config.SUBTITLE_STYLE in graph


def test_filtergraph_trim_duration():
    graph = build_filtergraph(1, "s.srt", clip_dur=7)
    assert "trim=0:7" in graph


def test_filtergraph_rejects_zero_clips():
    with pytest.raises(ValueError):
        build_filtergraph(0, "s.srt")


def test_ffmpeg_command_input_mapping():
    cmd = build_ffmpeg_command(["a.mp4", "b.mp4"], "voice.mp3", "s.srt", "out.mp4")
    # two video inputs + one audio input, each preceded by -i
    assert cmd.count("-i") == 3
    assert cmd[:2] == ["ffmpeg", "-y"]
    # audio is the input at index n (=2): mapped as "2:a"
    assert "-map" in cmd and "2:a" in cmd
    assert "[vout]" in cmd


def test_ffmpeg_command_orders_inputs_before_filter():
    cmd = build_ffmpeg_command(["a.mp4"], "voice.mp3", "s.srt", "out.mp4")
    i_filter = cmd.index("-filter_complex")
    i_last_input = len(cmd) - 1 - cmd[::-1].index("-i")
    assert i_last_input < i_filter


def test_ffmpeg_command_encoder_settings():
    cmd = build_ffmpeg_command(["a.mp4"], "voice.mp3", "s.srt", "out.mp4", crf=20)
    assert "libx264" in cmd
    assert cmd[cmd.index("-crf") + 1] == "20"
    assert "aac" in cmd
    assert cmd[-1] == "out.mp4"
    assert "-shortest" in cmd


def test_ffmpeg_command_requires_clips():
    with pytest.raises(ValueError):
        build_ffmpeg_command([], "voice.mp3", "s.srt", "out.mp4")
