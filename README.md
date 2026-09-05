# Video Commentator

**A fully autonomous pipeline that researches, narrates, edits, and publishes
vertical short-form videos — with zero human input, on a 90-minute cron.**

Each run picks a topic, sources stock footage, *looks* at the footage with a
vision model to ground the narration in what's actually on screen, writes a
voiceover, speaks it, transcribes it back to word-accurate subtitles, and
renders a finished 1080×1920 short in a single FFmpeg pass — then uploads it to
YouTube and pings Telegram. Cost: **~$0.02–0.03 per video.**

![CI](https://github.com/marr59/video-commentator/actions/workflows/ci.yml/badge.svg)

---

## What it does (end to end)

```
topic ─▶ stock clips ─▶ vision analysis ─▶ script ─▶ TTS ─▶ subtitles ─▶ FFmpeg montage ─▶ YouTube ─▶ Telegram
```

| # | Stage | Tooling | Notes |
|---|-------|---------|-------|
| 1 | **Topic selection** | in-process | 28-topic rotation with rolling de-dup memory |
| 2 | **Footage** | Pixabay API | 4 vertical clips/topic; prefers never-used clip IDs |
| 3 | **Vision grounding** | OpenRouter → Llama 4 Scout | one frame/clip described so the script names the *real* place |
| 4 | **Script** | OpenRouter → DeepSeek v3 | 60–80-word hook-fact-CTA voiceover |
| 5 | **Narration** | Microsoft Edge TTS | neural voice, no API key |
| 6 | **Subtitles** | faster-whisper (local) | word-level timestamps → 5-word cues |
| 7 | **Render** | FFmpeg `filter_complex` | scale/crop/concat/burn-in subs in **one pass** |
| 8 | **Publish** | YouTube Data API v3 | resumable upload, OAuth refresh |
| 9 | **Notify** | Telegram Bot API | topic + link on success |

## Engineering highlights

- **Single-pass FFmpeg montage.** Every clip is scaled to fill the frame,
  centre-cropped to 1080×1920, square-pixel-normalised, hard-trimmed, then
  concatenated and overlaid with burned-in subtitles — all in one
  `filter_complex` graph (no intermediate files, no re-encode passes). See
  [`vcpipe/compose.py`](vcpipe/compose.py).

- **Predictable caption sizing (a real bug fixed).** libass renders SRT on a
  virtual `PlayResY=288` canvas and scales glyphs to the frame height, so
  `FontSize` is **not** pixels — on-screen size is `FontSize × (height / 288)`.
  Getting this wrong produces either invisible or screen-filling "titanic"
  captions. The relationship is encoded and unit-tested
  ([`libass_rendered_px`](vcpipe/subtitles.py)), with a regression guard that
  fails CI if the shipped `FontSize` would render outside a readable range.

- **Vision-grounded scripts.** The narration is written *after* a vision model
  describes the actual footage, so a "cherry blossom" clip that is really Mount
  Yoshino gets named correctly instead of generic filler.

- **Local, word-accurate STT.** Subtitles come from faster-whisper running on
  CPU with word-level timestamps, grouped into fixed-width cues — no paid STT,
  no network dependency for captioning.

- **Idempotent de-duplication.** Topics and clip IDs carry rolling memory
  (capped at 60 / 200) so the channel doesn't repeat itself, with an automatic
  rotation reset when the topic pool is exhausted.

- **Secrets never touch the code.** All credentials come from the environment;
  OAuth/token files are gitignored. See [Security](#security).

## Architecture

Deterministic logic is separated from I/O so it can be unit-tested without
network, keys, or a GPU:

```
vcpipe/
  config.py      # constants, env-var loading, topic list, subtitle style
  dedup.py       # topic + clip de-duplication (pure)
  subtitles.py   # word timestamps → cues → SRT; libass sizing (pure)
  compose.py     # FFmpeg filter_complex + argv builder (pure)
  metadata.py    # YouTube title / slug / tags (pure)
pipeline.py      # orchestration: download, vision, TTS, render, upload
tests/           # unit tests for every pure module
```

## Testing

**What CI covers** (deterministic, runs on every push — Python 3.10/3.11/3.12):

- Topic & clip de-duplication, rotation reset, rolling-memory caps
- Subtitle grouping (exact + partial cues, timing, whitespace)
- SRT timestamp formatting incl. millisecond rounding spill
- libass caption-sizing math + readable-range regression guard
- FFmpeg `filter_complex` and argv construction (per-clip scaling, concat
  arity, input/audio mapping, encoder flags)
- YouTube title/slug/tag formatting incl. length limit and illegal-char stripping

**What is verified locally** (needs API keys, network, and FFmpeg, so it is
*not* in CI): the media stages — Pixabay download, OpenRouter vision/script,
Edge TTS, faster-whisper transcription, the FFmpeg render itself, and the
YouTube upload. This split is deliberate: CI proves the logic, the operator
proves the media path.

```bash
pip install -r requirements-dev.txt
pytest            # 42 tests, all green
```

## Running the full pipeline

```bash
# 1. System deps
#    ffmpeg + ffprobe on PATH (e.g. `brew install ffmpeg`)

# 2. Python deps
pip install -r requirements.txt

# 3. Secrets
cp .env.example .env      # fill in the keys
# place YouTube OAuth files under credentials/ (gitignored)

# 4. Run one video
python pipeline.py
```

Automate it with cron (every 90 minutes):

```cron
0 */1 * * *  cd /path/to/video-commentator && ./.venv/bin/python pipeline.py
```

## Security

- No API keys, tokens, or OAuth secrets are committed. All are read from
  environment variables via `vcpipe/config.py`.
- `.env`, `credentials/`, and any `*token*.json` / `*client_secret*.json` are
  gitignored.
- `.env.example` documents the required variables with **no values**.

## License

MIT — see [LICENSE](LICENSE).
