"""FFmpeg command construction for the montage render.

The whole montage is produced in a *single* FFmpeg pass via ``filter_complex``:
every source clip is scaled to fill a 1080x1920 frame, hard-trimmed, concatenated,
then the burned-in subtitles are overlaid and the narration is muxed in. Building
the graph as a pure function makes it unit-testable without invoking FFmpeg.
"""

from typing import List, Sequence

from . import config


def build_filtergraph(
    n_clips: int,
    srt_path: str,
    clip_dur: int = config.CLIP_DURATION,
    style: str = config.SUBTITLE_STYLE,
    width: int = config.OUTPUT_W,
    height: int = config.OUTPUT_H,
) -> str:
    """Return the ``filter_complex`` string for an ``n_clips`` montage.

    Per clip: scale to the target height, centre-crop to the target width, force
    square pixels, trim to ``clip_dur`` and reset PTS. Then concat all clips and
    burn in the SRT with an explicit libass style.
    """
    if n_clips < 1:
        raise ValueError("n_clips must be >= 1")

    parts: List[str] = []
    for i in range(n_clips):
        parts.append(
            f"[{i}:v]scale=-2:{height},crop={width}:{height},setsar=1,"
            f"trim=0:{clip_dur},setpts=PTS-STARTPTS[c{i}]"
        )
    concat_in = "".join(f"[c{i}]" for i in range(n_clips))
    parts.append(f"{concat_in}concat=n={n_clips}:v=1:a=0,setsar=1[cv]")
    parts.append("[cv]setsar=1[vp]")
    parts.append(f"[vp]subtitles={srt_path}:force_style='{style}'[vout]")
    return ";".join(parts)


def build_ffmpeg_command(
    clip_paths: Sequence[str],
    audio_path: str,
    srt_path: str,
    out_path: str,
    clip_dur: int = config.CLIP_DURATION,
    crf: int = 18,
) -> List[str]:
    """Assemble the full ``ffmpeg`` argv for the render pass."""
    n = len(clip_paths)
    if n < 1:
        raise ValueError("need at least one clip")

    inputs: List[str] = []
    for c in clip_paths:
        inputs += ["-i", str(c)]
    inputs += ["-i", str(audio_path)]

    graph = build_filtergraph(n, srt_path, clip_dur=clip_dur)

    return (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", graph,
            "-map", "[vout]",
            "-map", f"{n}:a",
            "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_path),
        ]
    )
