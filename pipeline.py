#!/usr/bin/env python3
"""Video Commentator - end-to-end automated YouTube Shorts pipeline.

topic -> Pixabay clips -> vision -> script -> TTS -> subtitles -> FFmpeg -> YouTube

Deterministic logic lives in the ``vcpipe`` package (unit-tested in CI). This
module wires the network / render / upload stages together. All secrets are
read from the environment (see .env.example); nothing is hard-coded.
"""

import asyncio
import base64
import json
import logging
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

from vcpipe import config
from vcpipe.compose import build_ffmpeg_command
from vcpipe.dedup import next_topic_pool, trim_memory, fresh_clips
from vcpipe.metadata import make_title, make_tags
from vcpipe.subtitles import Word, group_words, build_srt

BASE_DIR = Path(__file__).parent
WORK_DIR = BASE_DIR / "runs"
WORK_DIR.mkdir(exist_ok=True)

STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)
USED_TOPICS_FILE = STATE_DIR / "used_topics.json"
USED_VIDEOS_FILE = STATE_DIR / "used_videos.json"
UPLOAD_LOG = STATE_DIR / "upload_log.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(), logging.FileHandler(BASE_DIR / "pipeline.log", encoding="utf-8")],
)
log = logging.getLogger(__name__)


# --- tiny JSON-file wrappers around the pure dedup logic ---------------------
def _load_set(path: Path) -> set:
    return set(json.loads(path.read_text())) if path.exists() else set()


def pick_topic() -> str:
    pool = next_topic_pool(config.TOPICS, _load_set(USED_TOPICS_FILE))
    if pool == list(config.TOPICS):
        USED_TOPICS_FILE.write_text("[]")  # rotation reset
    return random.choice(pool)


def save_used_topic(topic: str) -> None:
    used = _load_set(USED_TOPICS_FILE) | {topic}
    USED_TOPICS_FILE.write_text(json.dumps(trim_memory(used, config.MAX_USED_TOPICS)))


def save_used_videos(video_ids) -> None:
    used = _load_set(USED_VIDEOS_FILE) | {str(v) for v in video_ids}
    USED_VIDEOS_FILE.write_text(json.dumps(trim_memory(used, config.MAX_USED_VIDEOS)))


# --- network / media stages --------------------------------------------------
def download_clips(query, work_dir, count=config.CLIP_COUNT):
    log.info(f"Pixabay search: {query!r} (need {count} clips)")
    key = config.require("PIXABAY_API_KEY")

    def search(extra):
        params = {"key": key, "q": query, "video_type": "film", "per_page": 20}
        params.update(extra)
        return requests.get("https://pixabay.com/api/videos/", params=params, timeout=30).json().get("hits", [])

    hits = search({"orientation": "vertical", "min_width": 720})
    if len(hits) < count:
        hits = search({}) or hits
    if not hits:
        raise RuntimeError(f"No videos for: {query!r}")

    ids = [str(h["id"]) for h in hits]
    preferred = set(fresh_clips(ids, _load_set(USED_VIDEOS_FILE), count))
    pool = [h for h in hits if str(h["id"]) in preferred] or hits
    selected = random.sample(pool[: min(len(pool), 15)], min(count, len(pool)))

    clips = []
    for i, hit in enumerate(selected):
        v = hit["videos"]
        url = (v.get("large") or v.get("medium") or v.get("small"))["url"]
        out = work_dir / f"clip_{i}.mp4"
        log.info(f"  Clip {i + 1}/{count}: id={hit['id']}")
        resp = requests.get(url, stream=True, timeout=120)
        with open(out, "wb") as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk)
        clips.append((out, hit["id"]))
    return clips


def extract_clip_frames(clips, work_dir):
    frames = []
    for i, (clip_path, _) in enumerate(clips):
        try:
            dur = float(subprocess.check_output(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(clip_path)]).decode().strip())
        except Exception:
            dur = 5.0
        t = min(dur * 0.4, dur - 0.5)
        out = work_dir / f"frame_{i}.jpg"
        subprocess.run(["ffmpeg", "-ss", str(t), "-i", str(clip_path),
                        "-frames:v", "1", "-q:v", "3", str(out), "-y"], capture_output=True, check=True)
        frames.append(out)
    return frames


def analyze_frames(frames):
    key = config.require("OPENROUTER_API_KEY")
    descs = []
    for frame in frames:
        b64 = base64.b64encode(frame.read_bytes()).decode()
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": config.VISION_MODEL, "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": "Describe what you see in 1-2 sentences. If you can identify a "
                 "specific location, country, or landmark, name it. Focus on what makes this place unique."},
            ]}], "max_tokens": 120}, timeout=30)
        descs.append(resp.json()["choices"][0]["message"]["content"].strip())
    combined = " | ".join(descs)
    log.info(f"Vision: {combined[:120]}...")
    return combined


def generate_script(topic, visual_desc):
    key = config.require("OPENROUTER_API_KEY")
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": config.SCRIPT_MODEL, "messages": [{"role": "user", "content":
              "You are a YouTube Shorts narrator. Write a punchy voiceover (60-80 words, ~28 seconds spoken) "
              f"for a montage about: {visual_desc}\n\n"
              "RULES: Start with the SPECIFIC location or subject name as the hook (e.g. 'This is Whitehaven "
              "Beach, Australia'). Include 2-3 surprising, specific facts about this place. Keep it upbeat. "
              "End with 'Would you visit?' or similar CTA. Plain text only, no markdown, no hashtags."}],
              "temperature": 0.85, "max_tokens": 300}, timeout=60)
    script = re.sub(r"\*+|#{1,6}\s", "", resp.json()["choices"][0]["message"]["content"].strip())
    log.info(f"Script: {script[:80]}...")
    return script


async def generate_tts(script, out_path):
    import edge_tts
    await edge_tts.Communicate(script, config.TTS_VOICE).save(str(out_path))
    log.info(f"TTS: {out_path}")


def generate_srt(audio_path, srt_path):
    from faster_whisper import WhisperModel
    model = WhisperModel(config.STT_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), word_timestamps=True, language="en")
    words = [Word(w.word, w.start, w.end)
             for seg in segments if getattr(seg, "words", None)
             for w in seg.words]
    cues = group_words(words, per=config.WORDS_PER_CUE)
    srt_path.write_text(build_srt(cues), encoding="utf-8")
    log.info(f"SRT: {len(cues)} cues")


def compose_video(clips, audio, srt, out, clip_dur=config.CLIP_DURATION):
    cmd = build_ffmpeg_command([c for c, _ in clips], audio, srt, out, clip_dur=clip_dur)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr[-600:]}")
    log.info(f"Video: {out.stat().st_size // 1024 // 1024}MB")


def notify_telegram(topic, url):
    token, chat = config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
    if not token or not chat:
        return  # notifications are optional
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": f"\U0001f3ac {topic}\n{url}"}, timeout=10)
    except Exception as e:
        log.warning(f"Telegram notify failed: {e}")


def upload_youtube(video_path, title, script, tags):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    td = json.loads(Path(config.YOUTUBE_TOKEN).read_text())
    sd = json.loads(Path(config.YOUTUBE_SECRET).read_text())
    creds = Credentials(
        token=td.get("token"), refresh_token=td.get("refresh_token"),
        token_uri=td.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=td.get("client_id") or sd["installed"]["client_id"],
        client_secret=td.get("client_secret") or sd["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(config.YOUTUBE_TOKEN).write_text(creds.to_json())

    yt = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body={
        "snippet": {"title": title[:100], "description": f"{script}\n\n#Shorts", "tags": tags, "categoryId": "19"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log.info(f"Upload: {int(status.progress() * 100)}%")

    vid_id = resp["id"]
    url = f"https://www.youtube.com/shorts/{vid_id}"
    with open(UPLOAD_LOG, "a") as f:
        f.write(json.dumps({"video_id": vid_id, "url": url, "title": title,
                            "uploaded_at": datetime.now().isoformat()}) + "\n")
    log.info(f"Uploaded: {url}")
    return vid_id, url


async def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = WORK_DIR / ts
    work_dir.mkdir(parents=True)
    log.info(f"=== Pipeline start {ts} ===")

    topic = pick_topic()
    log.info(f"Topic: {topic!r}")
    try:
        clips = download_clips(topic, work_dir)
        frames = extract_clip_frames(clips, work_dir)
        visual = analyze_frames(frames)
        script = generate_script(topic, visual)
        (work_dir / "script.txt").write_text(script)
        audio = work_dir / "voice.mp3"
        await generate_tts(script, audio)
        srt = work_dir / "subs.srt"
        generate_srt(audio, srt)
        final = work_dir / "final.mp4"
        compose_video(clips, audio, srt, final)

        title = make_title(script, topic)
        vid_id, url = upload_youtube(final, title, script, make_tags(topic))
        notify_telegram(topic, url)
        save_used_topic(topic)
        save_used_videos([cid for _, cid in clips])
        log.info(f"=== Pipeline done === {url}")
        print(f"SUCCESS: {url}")
        return 0
    except Exception as e:
        log.error(f"FAILED: {e}", exc_info=True)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
