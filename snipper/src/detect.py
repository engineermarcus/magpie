import subprocess
import re
import sys
from collections import Counter

def detect_crop(video_path, sample_duration=60):
    print(f"[snipper] Detecting crop values for: {video_path}")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", "cropdetect=24:16:0",
        "-t", str(sample_duration),
        "-f", "null",
        "-"
    ]

    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    output = result.stderr

    matches = re.findall(r"crop=(\d+:\d+:\d+:\d+)", output)

    if not matches:
        print("[snipper] No crop values detected — video may have no black bars")
        return None

    most_common = Counter(matches).most_common(1)[0][0]
    w, h, x, y = most_common.split(":")

    crop = {
        "w": int(w),
        "h": int(h),
        "x": int(x),
        "y": int(y),
        "filter": f"crop={w}:{h}:{x}:{y}"
    }

    print(f"[snipper] Crop detected → width:{w} height:{h} x:{x} y:{y}")
    return crop


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 detect.py <video_path> [sample_seconds]")
        sys.exit(1)

    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    result = detect_crop(sys.argv[1], duration)
    if result:
        print(f"[snipper] Crop filter: {result['filter']}")
