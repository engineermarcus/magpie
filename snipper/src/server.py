import http.server
import socketserver
import json
import os
import threading
import urllib.parse
import time
from crop import crop_to_hls

SEGMENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../segments"))
ORIGINALS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../web"))
PORT = 8080

active_jobs = {}
jobs_lock = threading.Lock()

def get_job_key(video_name, width, height):
    return f"{video_name}_{width}x{height}"

def wait_for_playlist(playlist_path, timeout=60):
    start = time.time()
    while not os.path.exists(playlist_path):
        if time.time() - start > timeout:
            return False
        time.sleep(0.5)
    return True

def start_processing(video_path, output_dir, width, height):
    def run():
        crop_to_hls(
            video_path=video_path,
            output_dir=output_dir,
            target_width=width,
            target_height=height
        )
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t

def resolve_dimensions(screen_width, screen_height, orientation):
    """
    For landscape videos:
    - If device is portrait → assume user will rotate → use landscape dimensions
    - If device is landscape → use as-is
    Returns (target_width, target_height, needs_rotate_prompt)
    """
    is_portrait = "portrait" in orientation.lower()

    if is_portrait:
        # Swap — treat as if rotated
        return screen_height, screen_width, True
    else:
        return screen_width, screen_height, False


class SnipperHandler(http.server.SimpleHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[snipper] {self.address_string()} - {format % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/detect.js":
            self._serve_file(os.path.join(WEB_DIR, "detect.js"), "application/javascript")
            return

        if path.endswith(".m3u8"):
            rel = path.lstrip("/")
            file_path = os.path.join(SEGMENTS_DIR, rel)
            self._serve_file(file_path, "application/vnd.apple.mpegurl")
            return

        if path.endswith(".ts"):
            rel = path.lstrip("/")
            file_path = os.path.join(SEGMENTS_DIR, rel)
            self._serve_file(file_path, "video/mp2t")
            return

        if path == "/" or path == "/index.html":
            self._serve_player()
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/device":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                screen_width = data.get("screen_width")
                screen_height = data.get("screen_height")
                orientation = data.get("orientation", "landscape-primary")
                video_name = data.get("video", "ozark-s03e01")
                refresh = data.get("refresh_rate")

                # Resolve correct dimensions based on orientation
                target_w, target_h, needs_rotate = resolve_dimensions(
                    screen_width, screen_height, orientation
                )

                print(f"[snipper] Device → {screen_width}x{screen_height} @ {refresh}Hz {orientation}")
                print(f"[snipper] Target → {target_w}x{target_h} rotate_prompt:{needs_rotate}")

                video_path = os.path.join(ORIGINALS_DIR, f"{video_name}.mp4")
                job_key = get_job_key(video_name, target_w, target_h)
                output_dir = os.path.join(SEGMENTS_DIR, job_key)
                playlist = os.path.join(output_dir, "index.m3u8")

                with jobs_lock:
                    if job_key not in active_jobs and not os.path.exists(playlist):
                        print(f"[snipper] Starting job → {job_key}")
                        os.makedirs(output_dir, exist_ok=True)
                        active_jobs[job_key] = start_processing(
                            video_path, output_dir, target_w, target_h
                        )
                    elif job_key in active_jobs:
                        print(f"[snipper] Job already running → {job_key}")
                    else:
                        print(f"[snipper] Cache hit → {playlist}")

                print(f"[snipper] Waiting for first segments...")
                ready = wait_for_playlist(playlist, timeout=60)

                if ready:
                    stream_url = f"/{job_key}/index.m3u8"
                    self._json_response({
                        "status": "ok",
                        "stream_url": stream_url,
                        "needs_rotate": needs_rotate
                    })
                else:
                    self._json_response({"status": "error", "message": "Timeout"}, 500)

            except BrokenPipeError:
                pass
            except Exception as e:
                print(f"[snipper] Error: {e}")
                try:
                    self._json_response({"status": "error", "message": str(e)}, 500)
                except BrokenPipeError:
                    pass
            return

        self.send_error(404, "Not found")

    def _serve_file(self, path, content_type):
        if not os.path.exists(path):
            self.send_error(404, f"File not found: {path}")
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(data))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json_response(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_player(self):
        html = """<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Snipper</title>
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; }
    video { width: 100vw; height: 100vh; object-fit: cover; }
    #rotate-prompt {
      display: none;
      position: fixed;
      bottom: 30px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(255,255,255,0.15);
      color: #fff;
      padding: 10px 22px;
      border-radius: 20px;
      font-family: sans-serif;
      font-size: 14px;
      backdrop-filter: blur(8px);
      z-index: 99;
      pointer-events: none;
    }
  </style>
</head>
<body>
  <video id="player" controls autoplay playsinline></video>
  <div id="rotate-prompt">↺ Rotate for fullscreen</div>
  <script src="/detect.js"></script>
  <script>
    const video = document.getElementById("player");
    const rotatePrompt = document.getElementById("rotate-prompt");
    let hlsInstance = null;

    function loadStream(streamUrl) {
      if (hlsInstance) { hlsInstance.destroy(); }
      if (Hls.isSupported()) {
        hlsInstance = new Hls({ enableWorker: true, lowLatencyMode: false });
        hlsInstance.loadSource(streamUrl);
        hlsInstance.attachMedia(video);
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => video.play());
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = streamUrl;
        video.play();
      }
    }

    // Expose stream loader for detect.js to call on orientation change
    window.__snipperLoadStream = function(streamUrl, needsRotate) {
      loadStream(streamUrl);
      if (needsRotate) {
        rotatePrompt.style.display = "block";
        setTimeout(() => rotatePrompt.style.display = "none", 4000);
      } else {
        rotatePrompt.style.display = "none";
      }
    };
  </script>
</body>
</html>"""
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


def run(port=PORT):
    os.makedirs(SEGMENTS_DIR, exist_ok=True)
    os.makedirs(ORIGINALS_DIR, exist_ok=True)
    with socketserver.ThreadingTCPServer(("", port), SnipperHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"[snipper] Server running → http://localhost:{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    run()
