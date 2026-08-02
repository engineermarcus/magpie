import subprocess
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from crop import build_filter

SEGMENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../segments"))

_UA  = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36"
_ORG = "https://h5-api.aoneroom.com"


def _headers_arg(referer):
    return (
        f"Referer: {referer}\r\n"
        f"User-Agent: {_UA}\r\n"
        f"Origin: {_ORG}\r\n"
    )


def fast_cropdetect(source, referer=None, sample_duration=30):
    """
    Sample first N seconds of source for black bars.
    Returns crop dict or None.  Skipped for URL sources by default — callers decide.
    """
    cmd = ["ffmpeg"]
    if source.startswith("http"):
        cmd += ["-headers", _headers_arg(referer or _ORG)]

    cmd += [
        "-i", source,
        "-vf", "cropdetect=24:16:0",
        "-t", str(sample_duration),
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    matches = re.findall(r"crop=(\d+:\d+:\d+:\d+)", result.stderr)
    if not matches:
        return None
    w, h, x, y = Counter(matches).most_common(1)[0][0].split(":")
    return {"w": int(w), "h": int(h), "x": int(x), "y": int(y)}


def stream_to_hls(source, output_dir, target_width, target_height,
                  referer=None, crop=None, crf=23):
    """
    source  — local file path OR https:// URL
    Returns (process, playlist_path).
    FFmpeg writes segments immediately; caller polls for playlist file.

    Speed choices:
      - ultrafast preset      — lowest encode latency
      - zerolatency tune      — no lookahead buffering
      - hls_time 2            — 2-second segments → player starts faster
      - threads 0             — use all cores
      - audio aac copy/re-enc — always compatible
    """
    target_width  = target_width  if target_width  % 2 == 0 else target_width  - 1
    target_height = target_height if target_height % 2 == 0 else target_height - 1
    os.makedirs(output_dir, exist_ok=True)
    playlist        = os.path.join(output_dir, "index.m3u8")
    segment_pattern = os.path.join(output_dir, "seg%03d.ts")

    # Build vf filter
    if crop:
        vf = build_filter(crop, target_width, target_height)
    else:
        vf = f"scale={target_width}:{target_height}:flags=lanczos"

    cmd = ["ffmpeg", "-y"]

    # URL input — inject headers so the CDN doesn't reject us
    if source.startswith("http"):
        cmd += ["-headers", _headers_arg(referer or _ORG)]

    cmd += [
        "-i", source,
        # video
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-threads", "0",
        # audio — copy if already AAC, else re-encode
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        # HLS mux
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "0",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", segment_pattern,
        playlist,
    ]

    print(f"[segment] FFmpeg → {output_dir}  src={'URL' if source.startswith('http') else 'FILE'}")
    process = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    return process, playlist
