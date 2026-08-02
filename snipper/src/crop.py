import subprocess
import os
import sys
from detect import detect_crop

def build_filter(crop, target_width, target_height):
    """
    Build FFmpeg filter chain that handles all boxing cases:
    - Letterbox (bars top/bottom) → scale to fill width, crop height
    - Pillarbox (bars left/right) → scale to fill height, crop width
    - Windowbox (bars all sides)  → cropdetect removes all, then scale
    - Already fits               → just scale
    """
    cw = crop["w"]
    ch = crop["h"]
    cx = crop["x"]
    cy = crop["y"]

    crop_aspect  = cw / ch
    target_aspect = target_width / target_height

    if crop_aspect > target_aspect:
        # Video is wider than screen → scale to fill width, trim top/bottom
        scale_w = target_width
        scale_h = int(target_width / crop_aspect)
        scale_h = scale_h if scale_h % 2 == 0 else scale_h - 1
        crop_y  = max(0, (scale_h - target_height) // 2)
        if scale_h >= target_height:
            filters = [
                f"crop={cw}:{ch}:{cx}:{cy}",
                f"scale={scale_w}:{scale_h}:flags=lanczos",
                f"crop={target_width}:{target_height}:0:{crop_y}",
            ]
        else:
            # scaled height is less than target — pad vertically
            pad_y = (target_height - scale_h) // 2
            filters = [
                f"crop={cw}:{ch}:{cx}:{cy}",
                f"scale={scale_w}:{scale_h}:flags=lanczos",
                f"pad={target_width}:{target_height}:0:{pad_y}:black",
            ]
    else:
        # Video is taller than (or same as) screen → scale to fill height, trim sides
        scale_h = target_height
        scale_w = int(target_height * crop_aspect)
        scale_w = scale_w if scale_w % 2 == 0 else scale_w - 1
        crop_x  = max(0, (scale_w - target_width) // 2)
        if scale_w >= target_width:
            filters = [
                f"crop={cw}:{ch}:{cx}:{cy}",
                f"scale={scale_w}:{scale_h}:flags=lanczos",
                f"crop={target_width}:{target_height}:{crop_x}:0",
            ]
        else:
            # scaled width is less than target — pad horizontally
            pad_x = (target_width - scale_w) // 2
            filters = [
                f"crop={cw}:{ch}:{cx}:{cy}",
                f"scale={scale_w}:{scale_h}:flags=lanczos",
                f"pad={target_width}:{target_height}:{pad_x}:0:black",
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
