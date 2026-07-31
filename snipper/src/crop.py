import subprocess
import os
import sys
from detect import detect_crop

def build_filter(crop, target_width, target_height):
    """
    Build FFmpeg filter chain:
    1. Crop black bars
    2. Scale up to fill target height
    3. Zoom crop excess width to fill screen exactly
    """
    cw = crop["w"]
    ch = crop["h"]
    cx = crop["x"]
    cy = crop["y"]

    # Scale to fill height
    scale_factor = target_height / ch
    scaled_width = int(cw * scale_factor)
    scaled_height = target_height

    # Zoom crop — trim sides equally
    crop_x = max(0, (scaled_width - target_width) // 2)

    filters = [
        f"crop={cw}:{ch}:{cx}:{cy}",
        f"scale={scaled_width}:{scaled_height}:flags=lanczos",
        f"crop={target_width}:{target_height}:{crop_x}:0"
    ]

    return ",".join(filters)


def crop_to_hls(video_path, output_dir, target_width=1920, target_height=1080, sample_duration=60, crf=23):
    crop = detect_crop(video_path, sample_duration)

    if not crop:
        print("[snipper] No crop needed")
        vf = f"scale={target_width}:{target_height}:flags=lanczos"
    else:
        vf = build_filter(crop, target_width, target_height)

    print(f"[snipper] Filter chain → {vf}")

    os.makedirs(output_dir, exist_ok=True)
    playlist = os.path.join(output_dir, "index.m3u8")
    segment_pattern = os.path.join(output_dir, "seg%03d.ts")

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "ultrafast",
        "-threads", "0",
        "-c:a", "copy",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "0",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", segment_pattern,
        playlist
    ]

    print(f"[snipper] Encoding started → {output_dir}")
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

    for line in process.stderr:
        if "frame=" in line or "time=" in line:
            print(f"\r[snipper] {line.strip()}", end="", flush=True)

    process.wait()
    print()

    if process.returncode == 0:
        print(f"[snipper] ✅ Done → {playlist}")
        return playlist
    else:
        print(f"[snipper] ❌ Failed with code {process.returncode}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 crop.py <video_path> <output_dir> <width> <height>")
        sys.exit(1)

    crop_to_hls(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
