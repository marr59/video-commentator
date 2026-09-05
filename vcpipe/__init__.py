"""Video Commentator - automated vertical-video pipeline.

The package is split so that all *deterministic* logic (topic/clip
deduplication, subtitle grouping, FFmpeg command construction, metadata
formatting) lives in importable, side-effect-free modules that are unit
tested in CI. The network / render / upload stages live in ``pipeline.py``.
"""

__version__ = "1.0.0"
