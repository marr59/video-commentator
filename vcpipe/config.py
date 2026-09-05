"""Configuration and constants.

Secrets are read from environment variables (see ``.env.example``). The module
imports cleanly with no secrets present so the test-suite can run in CI; the
values are only *required* when the corresponding network stage actually runs.
"""

import os

# --- Secrets (never hard-coded; supplied via environment) --------------------
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# YouTube OAuth credential file locations (the files themselves are gitignored).
YOUTUBE_TOKEN = os.environ.get("YOUTUBE_TOKEN_FILE", "credentials/token.json")
YOUTUBE_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "credentials/client_secret.json")

# --- Tunables ----------------------------------------------------------------
CLIP_COUNT = 4        # clips stitched per video
CLIP_DURATION = 9     # seconds per clip -> 4 x 9 = 36s, always exceeds audio
WORDS_PER_CUE = 5     # subtitle words per on-screen cue
OUTPUT_W, OUTPUT_H = 1080, 1920   # vertical 9:16

# libass renders SRT on a virtual canvas of PlayResY=288 and scales the glyphs
# to the real frame height. So the on-screen pixel size is
# FontSize * (frame_height / 288). FontSize=9 -> 9 * (1920/288) = 60px, which is
# a clean, readable caption. See vcpipe.subtitles.libass_rendered_px.
SUBTITLE_STYLE = (
    "FontName=Arial,FontSize=9,Bold=1,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV=40"
)

MAX_USED_TOPICS = 60     # rolling memory of recently-used topics
MAX_USED_VIDEOS = 200    # rolling memory of recently-used clip ids

TOPICS = [
    "waterfall nature", "ocean waves sunset", "mountain landscape", "forest rain",
    "cherry blossom", "aurora borealis", "desert sand dunes", "tropical beach",
    "snow winter landscape", "volcano", "coral reef underwater", "city skyline night",
    "starry night sky", "bamboo forest", "tulip field", "autumn leaves",
    "river canyon", "glacier ice", "savanna sunset", "dubai skyline",
    "northern lights", "mediterranean sea", "rice terrace", "lavender field",
    "rainforest waterfall", "coastal cliffs", "hot air balloon", "fjord norway",
]

# Voice + models (no secrets).
TTS_VOICE = "en-AU-NatashaNeural"
VISION_MODEL = "meta-llama/llama-4-scout"
SCRIPT_MODEL = "deepseek/deepseek-chat-v3-0324"
STT_MODEL = "base"


def require(name: str) -> str:
    """Return an env var or raise a clear error naming the missing key."""
    val = os.environ.get(name, "")
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val
