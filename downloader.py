
import asyncio
import httpx
import sys
import re
import json
import zipfile
import os
import time
import threading
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

# ── Snipper pipeline ──────────────────────────────────────────────────────────
_SNIPPER_SRC = os.path.join(os.path.dirname(__file__), "snipper", "src")
sys.path.insert(0, _SNIPPER_SRC)
from segment import stream_to_hls, fast_cropdetect
from queue_worker import get_job, set_job, job_exists
from device import resolve_dimensions

SEGMENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "snipper", "segments"))
WEB_DIR      = os.path.abspath(os.path.join(os.path.dirname(__file__), "snipper", "web"))

# ── TVMaze: fetch show metadata + exact episode counts ───────────────────────
async def tvmaze_info(title: str) -> dict:
    """Returns {id, name, genres, summary, poster, imdb, seasons: {1: 12, 2: 16, ...}}"""
    import urllib.request
    try:
        url  = f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote_plus(title)}"
        res  = json.loads(urllib.request.urlopen(url, timeout=10).read())
        if not res:
            return {}
        show = res[0]["show"]
        sid  = show["id"]
        seasons_raw = json.loads(urllib.request.urlopen(
            f"https://api.tvmaze.com/shows/{sid}/seasons", timeout=10
        ).read())
        seasons = {s["number"]: s["episodeOrder"] or 0 for s in seasons_raw}
        return {
            "id":      sid,
            "name":    show.get("name"),
            "genres":  show.get("genres", []),
            "summary": re.sub(r"<.*?>", "", show.get("summary") or ""),
            "poster":  (show.get("image") or {}).get("original"),
            "imdb":    (show.get("externals") or {}).get("imdb"),
            "rating":  (show.get("rating") or {}).get("average"),
            "status":  show.get("status"),
            "seasons": seasons,
        }
    except Exception as e:
        print(f"[!] TVMaze lookup failed: {e}")
        return {}

# ── Downloads folder ────────────────────────────────────────────────────────
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# ── Player URL template ───────────────────────────────────────────────────────
PLAYER_BASE = "https://123movienow.cc/spa/videoPlayPage/movies/{slug}?id={id}&type=/movie/detail&detailSe={season}&detailEp={episode}&lang=en"
PLAY_API    = "https://123movienow.cc/wefeed-h5api-bff/subject/play"

# ── Flag + query parser ───────────────────────────────────────────────────────
def parse_args(argv: list):
    if len(argv) < 2:
        return None, [], [], False, False, False, None, False, False

    query = argv[1]
    flags = argv[2:]

    download_all = "-a" in flags
    json_mode    = "--json" in flags
    info_mode    = "--info" in flags
    url_mode     = "--url" in flags
    upload_mode  = "--upload" in flags
    seasons      = []
    episodes     = []
    pick_index   = None

    for f in flags:
        m = re.match(r'^--s(\d+)$', f)
        if m:
            seasons.append(int(m.group(1)))
        m2 = re.match(r'^--ep(\d+)$', f)
        if m2:
            episodes.append(int(m2.group(1)))
        m3 = re.match(r'^--pick(\d+)$', f)
        if m3:
            pick_index = int(m3.group(1)) - 1

    return query, seasons, episodes, download_all, bool(seasons), json_mode, pick_index, info_mode, url_mode, upload_mode

# ── Natural language query parser ─────────────────────────────────────────────
def parse_query(query: str):
    q = query.lower()
    season, episode = 1, 1
    s = re.search(r'\b(?:season|s)\s*(\d+)', q)
    e = re.search(r'\b(?:episode|ep|e)\s*(\d+)', q)
    if s:
        season = int(s.group(1))
        q = q[:s.start()].strip()
    if e:
        episode = int(e.group(1))
    return re.sub(r'\s+', ' ', q).strip(), season, episode

# ── Auth token ───────────────────────────────────────────────────────────────
def _token_expired(tok: str) -> bool:
    try:
        import base64, json, datetime
        payload = tok.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        exp = json.loads(base64.b64decode(payload))["exp"]
        return datetime.datetime.fromtimestamp(exp) < datetime.datetime.now()
    except:
        return True

def get_auth_token() -> str:
    """Read JWT from MB_TOKEN env var or .mb_token file. Auto-refresh if expired."""
    tok = os.environ.get("MB_TOKEN", "").strip().strip('"')
    if not tok:
        token_file = os.path.join(os.path.dirname(__file__), ".mb_token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                tok = f.read().strip().strip('"')
    if tok and not _token_expired(tok):
        return tok
    print("[!] Token expired or missing — refreshing via Playwright...")
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "refresh_token.py")],
        capture_output=True, text=True
    )
    print(result.stdout.strip())
    # re-read after refresh
    token_file = os.path.join(os.path.dirname(__file__), ".mb_token")
    if os.path.exists(token_file):
        with open(token_file) as f:
            return f.read().strip().strip('"')
    return ""

# ── Search via direct API ─────────────────────────────────────────────────────
async def search_movie(title: str) -> list:
    token = get_auth_token()
    if not token:
        print("[✗] No auth token found. Set MB_TOKEN env var or create .mb_token file.")
        return []
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {token}",
        "X-Client-Info": json.dumps({"timezone": "Africa/Nairobi"}),
        "X-Request-Lang": "en",
        "Origin":        "https://themoviebox.xyz",
        "Referer":       "https://themoviebox.xyz/",
        "User-Agent":    "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36",
    }
    payload = {"keyword": title, "page": 1, "perPage": 10, "subjectType": 0}
    url = "https://h5-api.aoneroom.com/wefeed-h5api-bff/subject/search"
    print(f"[→] Searching: {url}?keyword={quote_plus(title)}")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json=payload, headers=headers)
    if r.status_code != 200:
        print(f"[✗] Search failed: HTTP {r.status_code} — {r.text[:200]}")
        return []
    data = r.json()
    if data.get("code") != 0:
        print(f"[✗] API error: {data.get('message')}")
        return []
    items = (data.get("data") or {}).get("items") or []
    print(f"[✓] Got {len(items)} results")
    return items

# ── Pick best match ───────────────────────────────────────────────────────────
def pick_best(items: list, title: str, season: int = 1) -> dict | None:
    title_words = set(title.lower().split())
    scored = []
    for item in items:
        name = (item.get("name") or item.get("title") or item.get("subjectName") or "").lower()
        title_score  = len(title_words & set(re.split(r'\W+', name)))
        has_res      = 3 if item.get("hasResource") else 0
        season_match = 2 if re.search(rf'\bs{season}\b', name, re.I) else 0
        bundle_pen   = -1 if re.search(r's\d+[-–]s\d+', name, re.I) else 0
        scored.append((title_score + has_res + season_match + bundle_pen, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1] if scored else None
    if best:
        print(f"[✓] Best match: {best.get('title') or best.get('name')}  "
              f"slug={best.get('detailPath')}  id={best.get('subjectId')}")
    return best

# ── Build player URL ──────────────────────────────────────────────────────────
def build_player_url(item: dict, season: int, episode: int) -> str:
    slug     = item.get("detailPath") or item.get("aliasName") or item.get("alias")
    movie_id = item.get("subjectId") or item.get("id")
    return PLAYER_BASE.format(slug=slug, id=movie_id, season=season, episode=episode)

# ── Get token for 123movienow.cc ─────────────────────────────────────────────
async def get_guest_token() -> str:
    return get_auth_token()

# ── Fetch streams via direct API (no Playwright) ──────────────────────────────
async def get_stream_url(player_url: str) -> dict:
    # extract params from player URL
    import re as _re
    m_id  = _re.search(r"[?&]id=([^&]+)", player_url)
    m_se  = _re.search(r"detailSe=([^&]+)", player_url)
    m_ep  = _re.search(r"detailEp=([^&]+)", player_url)
    m_slug = _re.search(r"/movies/([^?]+)", player_url)
    subject_id  = m_id.group(1)  if m_id  else ""
    season      = m_se.group(1)  if m_se  else "1"
    episode     = m_ep.group(1)  if m_ep  else "1"
    detail_path = m_slug.group(1) if m_slug else ""
    token = await get_guest_token()
    headers = {
        "Authorization":  f"Bearer {token}",
        "X-Client-Info":  json.dumps({"timezone": "Africa/Nairobi"}),
        "X-Request-Lang": "en",
        "x-vip-restrict": "0",
        "x-source":       "",
        "Origin":         "https://123movienow.cc",
        "Referer":        player_url,
        "User-Agent":     "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36",
        "Accept":         "application/json",
    }
    url = (f"https://123movienow.cc/wefeed-h5api-bff/subject/play"
           f"?subjectId={subject_id}&se={season}&ep={episode}"
           f"&detailPath={detail_path}&streamSignType=1")
    print(f"[→] Fetching streams: subjectId={subject_id} S{season}E{episode}")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=headers)
    if r.status_code != 200:
        print(f"[✗] Play API failed: HTTP {r.status_code}")
        return {}
    data = r.json()
    if data.get("code") != 0:
        print(f"[✗] Play API error: {data.get('message')}")
        return {}
    print(f"[API] streams={len(data['data'].get('streams', []))} hls={len(data['data'].get('hls', []))}")
    return {"data": data}

# ── Fetch streams for one episode via Playwright ──────────────────────────────
async def fetch_streams_direct(slug: str, movie_id: str, season: int, episode: int) -> list:
    player_url = PLAYER_BASE.format(slug=slug, id=movie_id, season=season, episode=episode)
    result = await get_stream_url(player_url)
    data = (result.get("data") or {}).get("data", {})
    streams = data.get("streams") or []
    hls     = data.get("hls") or []
    all_streams = streams + hls
    available = [s for s in all_streams if s.get("url") and not s.get("vipLocked")]
    return available

# ── Scan available episodes — sequential, one browser reused ─────────────────
async def scan_episodes(slug: str, movie_id: str, season: int, max_ep: int = 50) -> list:
    available = []
    sem = asyncio.Semaphore(5)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote', '--single-process'])

        async def check_ep(ep):
            async with sem:
                page  = await browser.new_page()
                event = asyncio.Event()
                found = []

                async def on_response(response, _ep=ep, _found=found, _event=event):
                    if "wefeed-h5api-bff/subject/play" in response.url:
                        try:
                            data    = await response.json()
                            streams = (data.get("data") or {}).get("streams") or []
                            if streams:
                                _found.append(_ep)
                        except:
                            pass
                        finally:
                            _event.set()

                page.on("response", on_response)
                player_url = PLAYER_BASE.format(slug=slug, id=movie_id, season=season, episode=ep)
                try:
                    await page.goto(player_url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.wait_for(event.wait(), timeout=5)
                except:
                    pass
                await page.close()
                return found[0] if found else None

        tasks   = [asyncio.create_task(check_ep(ep)) for ep in range(1, max_ep + 1)]
        results = await asyncio.gather(*tasks)
        await browser.close()

    for ep, result in enumerate(results, 1):
        if result is not None:
            print(f"    S{season:02d}E{ep:02d} ✓")
            available.append(ep)
        else:
            print(f"    S{season:02d}E{ep:02d} ✗")

    return available

# ── Download one video file ───────────────────────────────────────────────────
async def download(url: str, output: str, referer: str):
    import subprocess, time
    print(f"[→] Downloading → {output}")

    def build_cmd(splits: int) -> list:
        return [
            "aria2c", url,
            "--out", os.path.basename(output),
            "--dir", os.path.dirname(output),
            "--split=" + str(splits),
            "--max-connection-per-server=" + str(splits),
            "--min-split-size=10M",
            "--referer", referer,
            "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
            "--file-allocation=none",
            "--console-log-level=error",
            "--continue=true",
            "--auto-file-renaming=false",
            "--summary-interval=0",
            "--show-console-readout=false",
        ]

    async def show_progress(path: str, total: int):
        while True:
            try:
                done = os.path.getsize(path)
                pct  = done / total * 100
                bar  = "#" * int(pct / 2)
                print(f"\r[↓] {pct:5.1f}%  [{bar:<50}]  {done//1048576}MB / {total//1048576}MB", end="", flush=True)
                if done >= total:
                    break
            except FileNotFoundError:
                pass
            await asyncio.sleep(0.5)

    # get total size first
    import httpx as _httpx
    total = 0
    try:
        async with _httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.head(url, headers={"Referer": referer})
            total = int(r.headers.get("content-length", 0))
    except:
        pass

    for splits in (16, 1):
        if splits == 1:
            print("\n[!] Retrying with single connection...")
        proc = await asyncio.create_subprocess_exec(*build_cmd(splits))
        if total:
            progress_task = asyncio.create_task(show_progress(output, total))
        await proc.wait()
        if total:
            progress_task.cancel()
        print()
        if proc.returncode == 0:
            print(f"[✓] Saved: {output}")
            return
        if splits == 1:
            print(f"[✗] aria2c failed (exit {proc.returncode})")
# ── Upload to Internet Archive S3 ────────────────────────────────────────────
async def upload_to_archive(filepath: str, title: str) -> str | None:
    import secrets as _sec
    access = os.environ.get("IA_ACCESS_KEY", "519485iDXPo2XjhG")
    secret = os.environ.get("IA_SECRET_KEY", "a2OI2iEdx5mEgFGg")
    if not access or not secret:
        print("[✗] Missing env vars: IA_ACCESS_KEY and IA_SECRET_KEY")
        return None
    filename   = os.path.basename(filepath)
    _safe = re.sub(r"[^\w-]", "-", title.lower())[:40]
    identifier = f"cybernetics-{_safe}-{_sec.token_hex(4)}"
    file_size  = os.path.getsize(filepath)
    upload_url = f"https://s3.us.archive.org/{identifier}/{filename}"
    headers = {
        "Authorization":              f"LOW {access}:{secret}",
        "x-archive-meta-title":       title,
        "x-archive-meta-mediatype":   "movies",
        "x-archive-auto-make-bucket": "1",
        "Content-Length":             str(file_size),
        "Content-Type":               "video/mp4",
    }
    print(f"[→] Uploading → archive.org  [{file_size // 1048576}MB]")

    async def streamer():
        done = 0
        with open(filepath, "rb") as fh:
            while chunk := fh.read(8 * 1024 * 1024):   # 8 MB chunks — zero RAM bloat
                done += len(chunk)
                print(f"\r[↑] {done / file_size * 100:.1f}%  ({done // 1048576}MB / {file_size // 1048576}MB)", end="", flush=True)
                yield chunk

    async with httpx.AsyncClient(timeout=900) as client:
        r = await client.put(upload_url, content=streamer(), headers=headers)
    print()
    if r.status_code in (200, 201):
        url = f"https://archive.org/download/{identifier}/{filename}"
        print(f"[✓] Stream URL : {url}")
        os.remove(filepath)
        print(f"[✓] Disk cleared: {filename}")
        return url
    print(f"[✗] Upload failed {r.status_code}: {r.text[:200]}")
    return None

# ── Download one episode (with fallback to nearest available) ─────────────────
async def download_episode(movie: dict, title: str, season: int, episode: int, explicit: bool = False, upload: bool = False):
    slug     = movie["detailPath"]
    movie_id = movie["subjectId"]
    safe     = re.sub(r'[^\w-]', '', title.replace(' ', '-'))

    streams = await fetch_streams_direct(slug, movie_id, season, episode)

    if not streams:
        if explicit:
            print(f"[✗] Episode {episode} not available")
            return
        print(f"[✗] S{season:02d}E{episode:02d} has no streams — scanning season {season}...")
        available = await scan_episodes(slug, movie_id, season)
        if not available:
            print(f"[✗] Season {season} has no available episodes on this site.")
            return
        print(f"[✓] Available episodes in S{season:02d}: {available}")
        episode = available[0]
        print(f"[→] Falling back to episode {episode}")
        streams = await fetch_streams_direct(slug, movie_id, season, episode)

    best     = max(streams, key=lambda s: int(s["resolutions"]))
    size_mb  = int(best["size"]) // 1048576
    referer  = build_player_url(movie, season, episode)
    output   = os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}e{episode:02d}.mp4")
    print(f"[✓] {best['resolutions']}p | {size_mb}MB")
    url = best["url"]
    if url and not url.startswith(("http://", "https://")):
        url = "https:" + url if url.startswith("//") else "https://" + url
    await download(url, output, referer=referer)
    if upload:
        await upload_to_archive(output, title)

# ── Scan and display all available seasons/episodes (no download) ─────────────
async def scan_all_seasons_info(movie: dict, title: str):
    import urllib.request, urllib.parse
    name = movie.get("title") or movie.get("name") or title
    try:
        res  = json.loads(urllib.request.urlopen(
            f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote_plus(title)}", timeout=10
        ).read())
        show = res[0]["show"] if res else {}
        sid  = show.get("id")
        seasons_raw = json.loads(urllib.request.urlopen(
            f"https://api.tvmaze.com/shows/{sid}/seasons", timeout=10
        ).read()) if sid else []
        poster  = (show.get("image") or {}).get("original")
        genres  = ", ".join(show.get("genres") or [])
        rating  = (show.get("rating") or {}).get("average")
        summary = re.sub(r"<.*?>", "", show.get("summary") or "")
        imdb    = (show.get("externals") or {}).get("imdb")
        status  = show.get("status")
        print(f"\n[i] {name}")
        print(f"    Genres : {genres}")
        print(f"    Rating : {rating}")
        print(f"    Status : {status}")
        print(f"    IMDB   : {imdb}")
        print(f"    Poster : {poster}")
        print(f"    Summary: {summary[:150]}...")
        print(f"\n    Seasons:")
        for s in seasons_raw:
            print(f"      S{s['number']:02d} → {s['episodeOrder']} episodes")
        print(f"\n[✓] Done.")
    except Exception as e:
        print(f"[!] TVMaze lookup failed: {e}")

# ── Download a full season ────────────────────────────────────────────────────
async def download_season(movie: dict, title: str, season: int, upload: bool = False) -> list | bool:
    slug     = movie["detailPath"]
    movie_id = movie["subjectId"]
    safe     = re.sub(r'[^\w-]', '', title.replace(' ', '-'))

    print(f"\n[→] Scanning season {season}...")
    available = await scan_episodes(slug, movie_id, season)

    if not available:
        print(f"[i] Season {season} — not released yet or not available on this site.")
        return False

    print(f"[✓] Season {season} has {len(available)} episode(s): {available}")
    downloaded = []
    for ep in available:
        streams = await fetch_streams_direct(slug, movie_id, season, ep)
        if not streams:
            print(f"[!] S{season:02d}E{ep:02d} — no streams, skipping")
            continue
        best    = max(streams, key=lambda s: int(s["resolutions"]))
        size_mb = int(best["size"]) // 1048576
        referer = build_player_url(movie, season, ep)
        output  = os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}e{ep:02d}.mp4")
        print(f"[✓] S{season:02d}E{ep:02d} — {best['resolutions']}p | {size_mb}MB")
        url = best["url"]
        if url and not url.startswith(("http://", "https://")):
            url = "https:" + url if url.startswith("//") else "https://" + url
        await download(url, output, referer=referer)
        if upload:
            url = await upload_to_archive(output, title)
            if url:
                downloaded.append(url)
            continue
        downloaded.append(output)
    if not upload:
        bundle_videos(downloaded, os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}"))
    return downloaded

# ── Download all seasons ──────────────────────────────────────────────────────
async def download_all_seasons(movie: dict, title: str, upload: bool = False):
    safe      = re.sub(r'[^\w-]', '', title.replace(' ', '-'))
    all_files = []
    season    = 1
    while True:
        result = await download_season(movie, title, season, upload=upload)
        if result is False:
            print(f"[✓] No more seasons after season {season - 1}. Done.")
            break
        if isinstance(result, list):
            all_files.extend(result)
        season += 1
    bundle_videos(all_files, os.path.join(DOWNLOADS_DIR, safe))

# ── Bundle downloaded videos into a zip ───────────────────────────────────────
def bundle_videos(files: list, archive_name: str):
    if len(files) < 2:
        return
    zip_path = f"{archive_name}.zip"
    print(f"\n[→] Bundling {len(files)} files → {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for f in files:
            if os.path.exists(f):
                zf.write(f, arcname=os.path.basename(f))
                print(f"    + {f}")
    total_mb = os.path.getsize(zip_path) // 1048576
    print(f"[✓] Archive ready: {zip_path} ({total_mb}MB)")
    for f in files:
        if os.path.exists(f):
            os.remove(f)
            print(f"    - deleted {os.path.basename(f)}")

# ── Display results list + prompt user to pick ───────────────────────────────
def show_results(items: list):
    print()
    for i, item in enumerate(items):
        title   = item.get("title") or item.get("name") or "Unknown"
        year    = (item.get("releaseDate") or "")[:4]
        country = item.get("countryName") or ""
        genre   = item.get("genre") or ""
        cover   = (item.get("cover") or {}).get("url") or ""
        rating  = item.get("imdbRatingValue") or ""
        has_res = "✓" if item.get("hasResource") else "✗"
        print(f"  [{i+1}] {has_res} {title} ({year}) | {country} | {genre}")
        if rating:
            print(f"       IMDB: {rating}")
        if cover:
            print(f"       Cover: {cover}")
        print()

def prompt_pick(items: list, best: dict) -> dict:
    show_results(items)
    best_idx = items.index(best) + 1
    try:
        raw = input(f"Pick a number [Enter = auto best match #{best_idx}]: ").strip()
        if not raw:
            return best
        idx = int(raw) - 1
        if 0 <= idx < len(items):
            return items[idx]
        print(f"[!] Invalid choice, using best match #{best_idx}")
        return best
    except (ValueError, EOFError):
        return best

# ── Help text ────────────────────────────────────────────────────────────────
def print_help():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                     Movie Downloader CLI                         ║
╚══════════════════════════════════════════════════════════════════╝

USAGE:
  python downloader.py "<title>" [flags]

SEARCH & SELECTION:
  --json          Dump search results as JSON and exit (for AI tool use)
  --pickN         Select result #N without interactive prompt (e.g. --pick1)

DOWNLOAD MODES:
  (no flags)      Single movie or episode parsed from title
  -a              Download ALL seasons and episodes
  --sN            Download full season N (e.g. --s1, --s3)
  --sN --epM      Download specific episode M of season N
  --sN --epM --epK  Download multiple episodes from one season
  --s1 --s2 --s3  Download multiple full seasons

RULES:
  ✓  Multiple --ep flags require exactly one --s flag
  ✗  Multiple --s + multiple --ep is not allowed (ambiguous)

EXAMPLES:
  python downloader.py "suits"
  python downloader.py "suits season 9 episode 1"
  python downloader.py "the flash" --json
  python downloader.py "the flash" --pick1 --s1
  python downloader.py "the flash" --pick1 --s1 --ep3 --ep4 --ep5
  python downloader.py "the flash" --pick1 --s1 --s2 --s3
  python downloader.py "the flash" --pick1 -a
  python downloader.py "the flash" --pick1 --info

OUTPUT:
  Downloads saved to: ./downloads/
  2+ episodes are auto-zipped and source files deleted.
""")

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        sys.exit(0)

    if "--transfer-to-storage" in sys.argv:
        import shutil
        src = os.path.expanduser("~/Downloads/magpie")
        dst = "/sdcard/magpie"
        if not os.path.exists(src):
            print(f"[✗] {src} not found")
            sys.exit(1)
        print(f"[→] Moving {src} → {dst}")
        shutil.move(src, dst)
        print(f"[✓] Transferred to /sdcard/magpie")
        sys.exit(0)
    query, seasons, episodes, dl_all, dl_season, json_mode, pick_index, info_mode, url_mode, upload_mode = parse_args(sys.argv)

    known = {"-a", "--json", "--info", "--url", "--upload"}
    for f in sys.argv[2:]:
        if f.startswith("-") and f not in known:
            if not re.match(r'^--(s\d+|ep\d+|pick\d+)$', f):
                print(f"[✗] Unknown flag: {f}")
                print("    Run with --help to see usage.")
                sys.exit(1)

    if len(seasons) > 1 and len(episodes) > 1:
        print("[✗] Can't combine multiple --s flags with multiple --ep flags.")
        print("    Use multiple --s for full seasons, or one --s with multiple --ep.")
        print("    Run with --help to see usage.")
        sys.exit(1)

    title, q_season, q_episode = parse_query(query)

    if not seasons:
        seasons = [q_season]
    if not episodes:
        episodes = [q_episode]

    print(f"[i] Title={title!r}")

    items = await search_movie(title)
    if not items:
        sys.exit(1)

    if json_mode:
        out = []
        for item in items:
            out.append({
                "title":       item.get("title") or item.get("name"),
                "year":        (item.get("releaseDate") or "")[:4],
                "country":     item.get("countryName"),
                "genre":       item.get("genre"),
                "imdb":        item.get("imdbRatingValue"),
                "description": item.get("description"),
                "hasResource": item.get("hasResource"),
                "detailPath":  item.get("detailPath"),
                "subjectId":   item.get("subjectId"),
                "cover":       (item.get("cover") or {}).get("url"),
            })
        print(json.dumps(out, indent=2, ensure_ascii=False))
        sys.exit(0)
    if url_mode:
        best = pick_best(items, title, seasons[0])
        if pick_index is not None:
            movie = items[pick_index] if 0 <= pick_index < len(items) else best
        else:
            movie = best
        streams = await fetch_streams_direct(movie["detailPath"], movie["subjectId"], seasons[0], episodes[0])
        if not streams:
            print(json.dumps({"error": "No streams found"}))
            sys.exit(1)
        best_stream = max(streams, key=lambda s: int(s["resolutions"]))
        print(json.dumps({"url": best_stream["url"], "resolution": best_stream["resolutions"], "size": best_stream["size"], "title": movie.get("title"), "referer": build_player_url(movie, seasons[0], episodes[0])}))
        sys.exit(0)

    best = pick_best(items, title, seasons[0])
    if not best:
        print("[✗] No matching title found in results")
        sys.exit(1)

    if pick_index is not None:
        movie = items[pick_index] if 0 <= pick_index < len(items) else best
    else:
        movie = prompt_pick(items, best)
    print(f"[✓] Selected: {movie.get('title') or movie.get('name')}")

    if info_mode:
        await scan_all_seasons_info(movie, title)
        return

    if dl_all:
        print(f"[i] Mode: ALL seasons")
        await download_all_seasons(movie, title, upload=upload_mode)

    elif dl_season and len(episodes) == 1 and episodes[0] == q_episode and not any(f.startswith("--ep") for f in sys.argv[2:]):
        print(f"[i] Mode: full season(s) {seasons}")
        for s in seasons:
            await download_season(movie, title, s, upload=upload_mode)

    elif dl_season and len(seasons) == 1 and len(episodes) >= 1:
        s    = seasons[0]
        safe = re.sub(r'[^\w-]', '', title.replace(' ', '-'))
        print(f"[i] Mode: S{s:02d} episodes {episodes}")
        downloaded = []
        for ep in episodes:
            await download_episode(movie, title, s, ep, explicit=True, upload=upload_mode)
            output = os.path.join(DOWNLOADS_DIR, f"{safe}-s{s:02d}e{ep:02d}.mp4")
            if os.path.exists(output):
                downloaded.append(output)
        bundle_videos(downloaded, os.path.join(DOWNLOADS_DIR, f"{safe}-s{s:02d}"))

    else:
        s, ep = seasons[0], episodes[0]
        print(f"[i] Mode: S{s:02d}E{ep:02d}")
        await download_episode(movie, title, s, ep, explicit=True, upload=upload_mode)

# ── Flask API server ──────────────────────────────────────────────────────────
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

def wait_for_playlist(playlist_path, timeout=45):
    start = time.time()
    while not os.path.exists(playlist_path):
        if time.time() - start > timeout:
            return False
        time.sleep(0.4)
    return True

@app.route("/")
def index():
    return app.send_static_file("index.html")

# ── HLS segment serving ───────────────────────────────────────────────────────
@app.route("/<path:rel>")
def serve_any(rel):
    # HLS playlist
    if rel.endswith(".m3u8"):
        fp = os.path.join(SEGMENTS_DIR, rel)
        if os.path.exists(fp):
            with open(fp, "rb") as f:
                data = f.read()
            return Response(data, mimetype="application/vnd.apple.mpegurl",
                            headers={"Access-Control-Allow-Origin": "*",
                                     "Cache-Control": "no-cache"})
    # HLS segment
    if rel.endswith(".ts"):
        fp = os.path.join(SEGMENTS_DIR, rel)
        if os.path.exists(fp):
            with open(fp, "rb") as f:
                data = f.read()
            return Response(data, mimetype="video/mp2t",
                            headers={"Access-Control-Allow-Origin": "*"})
    # React static fallback
    try:
        return app.send_static_file(rel)
    except Exception:
        return jsonify({"error": "not found"}), 404

def run_async(coro):
    return asyncio.run(coro)

@app.route("/api/search", methods=["GET"])
def api_search():
    title = request.args.get("q", "").strip()
    if not title:
        return jsonify({"error": "Missing ?q="}), 400
    items = run_async(search_movie(title))
    out = [{"title": i.get("title") or i.get("name"), "year": (i.get("releaseDate") or "")[:4], "country": i.get("countryName"), "genre": i.get("genre"), "imdb": i.get("imdbRatingValue"), "description": i.get("description"), "hasResource": i.get("hasResource"), "detailPath": i.get("detailPath"), "subjectId": i.get("subjectId"), "cover": (i.get("cover") or {}).get("url")} for i in items]
    return jsonify(out)

@app.route("/api/streams", methods=["GET"])
def api_streams():
    detail_path = request.args.get("detailPath")
    subject_id  = request.args.get("subjectId")
    season      = int(request.args.get("season", 1))
    episode     = int(request.args.get("episode", 1))
    if not detail_path or not subject_id:
        return jsonify({"error": "Missing detailPath or subjectId"}), 400
    streams = run_async(fetch_streams_direct(detail_path, subject_id, season, episode))
    if not streams:
        return jsonify({"error": "No streams found"}), 404
    return jsonify(streams)

@app.route("/api/download", methods=["POST"])
def api_download():
    body        = request.get_json() or {}
    detail_path = body.get("detailPath")
    subject_id  = body.get("subjectId")
    title       = body.get("title", "unknown")
    season      = int(body.get("season", 1))
    episode     = int(body.get("episode", 1))
    upload      = bool(body.get("upload", False))
    if not detail_path or not subject_id:
        return jsonify({"error": "Missing detailPath or subjectId"}), 400
    streams = run_async(fetch_streams_direct(detail_path, subject_id, season, episode))
    if not streams:
        return jsonify({"error": "No streams found"}), 404
    best    = max(streams, key=lambda s: int(s["resolutions"]))
    movie   = {"detailPath": detail_path, "subjectId": subject_id}
    referer = build_player_url(movie, season, episode)
    if upload:
        safe   = re.sub(r"[^\w-]", "", title.replace(" ", "-"))
        output = os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}e{episode:02d}.mp4")
        def bg():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _url = best["url"]
            if _url and not _url.startswith(("http://", "https://")):
                _url = "https:" + _url if _url.startswith("//") else "https://" + _url
            loop.run_until_complete(download(_url, output, referer=referer))
            loop.run_until_complete(upload_to_archive(output, title))
            loop.close()
        threading.Thread(target=bg, daemon=True).start()
        return jsonify({"status": "downloading+uploading", "resolution": best["resolutions"]})
    safe   = re.sub(r"[^\w-]", "", title.replace(" ", "-"))
    output = os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}e{episode:02d}.mp4")
    def bg():
        _url = best["url"]
        if _url and not _url.startswith(("http://", "https://")):
            _url = "https:" + _url if _url.startswith("//") else "https://" + _url
        asyncio.run(download(_url, output, referer=referer))
    threading.Thread(target=bg, daemon=True).start()
    return jsonify({"status": "downloading", "resolution": best["resolutions"], "size_mb": int(best["size"]) // 1048576, "output": output})

@app.route("/api/info", methods=["GET"])
def api_info():
    title = request.args.get("q", "").strip()
    if not title:
        return jsonify({"error": "Missing ?q="}), 400
    return jsonify(run_async(tvmaze_info(title)))

# ── /api/play — resolve stream + run Snipper pipeline → return HLS URL ───────
@app.route("/api/play", methods=["POST"])
def api_play():
    body        = request.get_json() or {}
    detail_path = body.get("detailPath")
    subject_id  = str(body.get("subjectId", ""))
    title       = body.get("title", "video")
    season      = int(body.get("season", 1))
    episode     = int(body.get("episode", 1))
    screen_w    = int(body.get("screen_width",  1920))
    screen_h    = int(body.get("screen_height", 1080))
    orientation = body.get("orientation", "landscape-primary")

    if not detail_path or not subject_id:
        return jsonify({"error": "Missing detailPath or subjectId"}), 400

    target_w, target_h, needs_rotate = resolve_dimensions(screen_w, screen_h, orientation)
    target_w = target_w if target_w % 2 == 0 else target_w - 1
    target_h = target_h if target_h % 2 == 0 else target_h - 1

    safe    = re.sub(r"[^\w-]", "", title.replace(" ", "-"))
    job_key = f"{safe}-s{season:02d}e{episode:02d}_{target_w}x{target_h}"
    out_dir  = os.path.join(SEGMENTS_DIR, job_key)
    playlist = os.path.join(out_dir, "index.m3u8")

    # ── Cache hit ──────────────────────────────────────────────────────────────
    if os.path.exists(playlist):
        return jsonify({"status": "ok",
                        "stream_url": f"/{job_key}/index.m3u8",
                        "needs_rotate": needs_rotate})

    # ── Already running ────────────────────────────────────────────────────────
    if job_exists(job_key):
        ready = wait_for_playlist(playlist, timeout=45)
        if ready:
            return jsonify({"status": "ok",
                            "stream_url": f"/{job_key}/index.m3u8",
                            "needs_rotate": needs_rotate})
        return jsonify({"error": "Timeout waiting for stream"}), 500

    # ── Determine source ───────────────────────────────────────────────────────
    filename   = f"{safe}-s{season:02d}e{episode:02d}.mp4"
    local_file = os.path.join(DOWNLOADS_DIR, filename)
    aria2_ctrl = local_file + ".aria2"

    # Use local file only if fully downloaded (no .aria2 control file)
    if os.path.exists(local_file) and not os.path.exists(aria2_ctrl):
        source  = local_file
        referer = None
        use_crop = True
    else:
        # Stream directly from CDN — fastest path, no wait
        streams = run_async(fetch_streams_direct(detail_path, subject_id, season, episode))
        if not streams:
            return jsonify({"error": "No streams found"}), 404
        best = max(streams, key=lambda s: int(s["resolutions"]))
        url  = best["url"]
        if url and not url.startswith(("http://", "https://")):
            url = "https:" + url if url.startswith("//") else "https://" + url
        source   = url
        print(f"[DEBUG] Stream URL → {url}")
        referer  = build_player_url({"detailPath": detail_path, "subjectId": subject_id}, season, episode)
        use_crop = False  # skip cropdetect on live URL — adds latency

    # ── Launch pipeline ────────────────────────────────────────────────────────
    set_job(job_key, "starting")
    os.makedirs(out_dir, exist_ok=True)

    def run_pipeline():
        crop = None
        if use_crop:
            crop = fast_cropdetect(source, sample_duration=10)
        proc, _ = stream_to_hls(source, out_dir, target_w, target_h,
                                 referer=referer, crop=crop)
        set_job(job_key, "running", pid=proc.pid)
        for line in proc.stderr:
            if "frame=" in line or "time=" in line:
                print(f"\r[snipper] {line.strip()}", end="", flush=True)
        proc.wait()
        print()
        set_job(job_key, "done" if proc.returncode == 0 else "error",
                code=proc.returncode)

    threading.Thread(target=run_pipeline, daemon=True).start()

    ready = wait_for_playlist(playlist, timeout=45)
    if not ready:
        return jsonify({"error": "Timeout — FFmpeg did not produce segments"}), 500

    return jsonify({"status": "ok",
                    "stream_url": f"/{job_key}/index.m3u8",
                    "needs_rotate": needs_rotate})


@app.route("/api/jobs", methods=["GET"])
def api_jobs():
    from queue_worker import all_jobs
    return jsonify(all_jobs())


@app.route("/api/files", methods=["GET"])
def api_files():
    files = [{"name": f, "size_mb": os.path.getsize(os.path.join(DOWNLOADS_DIR, f)) // 1048576} for f in os.listdir(DOWNLOADS_DIR) if os.path.isfile(os.path.join(DOWNLOADS_DIR, f))]
    return jsonify(files)

@app.route("/api/proxy", methods=["GET"])
def api_proxy():
    url     = request.args.get("url")
    referer = request.args.get("referer", "https://netfilm.world/")
    if not url:
        return jsonify({"error": "Missing ?url="}), 400
    import httpx
    from flask import Response
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
        "Referer": referer,
        "Range": request.headers.get("Range", "bytes=0-"),
    }
    def generate():
        with httpx.stream("GET", url, headers=headers, timeout=300, follow_redirects=True) as r:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                yield chunk
    with httpx.stream("GET", url, headers=headers, timeout=10, follow_redirects=True) as r:
        status = r.status_code
        resp_headers = {
            "Content-Type": r.headers.get("Content-Type", "video/mp4"),
            "Content-Length": r.headers.get("Content-Length", ""),
            "Accept-Ranges": "bytes",
            "Content-Range": r.headers.get("Content-Range", ""),
        }
    return Response(generate(), status=status, headers=resp_headers, direct_passthrough=True)

@app.route("/api/files/<filename>", methods=["GET"])
def api_serve_file(filename):
    fp = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(fp):
        return jsonify({"error": "File not found"}), 404
    return send_file(fp, as_attachment=True)

def transfer_to_storage():
    src = os.path.expanduser("~/Downloads/magpie")
    dst = "/sdcard/magpie"
    if not os.path.exists(os.path.expanduser("~/Downloads")):
        print("[✗] ~/Downloads not found")
        return
    # Rename Downloads to magpie first if needed
    dl_dir = os.path.expanduser("~/Downloads")
    magpie_dir = os.path.expanduser("~/Downloads/magpie")
    if not os.path.exists(magpie_dir):
        print("[✗] No magpie folder found in ~/Downloads")
        return
    import shutil
    print(f"[→] Moving {magpie_dir} → {dst}")
    shutil.move(magpie_dir, dst)
    print(f"[✓] Transferred to /sdcard/magpie")

if __name__ == "__main__":
    os.system(os.path.join(os.path.dirname(__file__), "autoupdate.sh"))
    if "--server" in sys.argv:
        os.makedirs(SEGMENTS_DIR, exist_ok=True)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        print("[Flask] Starting on http://0.0.0.0:5000")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    else:
        asyncio.run(main())
