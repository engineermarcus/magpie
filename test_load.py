"""
Magpie Load Test — Real flows
Usage:
  python3 test_load.py --host http://localhost:5000 --users 30
  python3 test_load.py --host http://localhost:5000 --users 50
"""

import asyncio
import httpx
import time
import random
import argparse
import json
from dataclasses import dataclass
from typing import Optional

SEARCH_QUERIES = [
    "Breaking Bad", "The Flash", "Ozark", "Inception", "Interstellar",
    "The Wire", "Suits", "Prison Break", "Money Heist", "Peaky Blinders",
    "Game of Thrones", "Stranger Things", "Dark", "Narcos", "Yellowstone",
]

@dataclass
class Result:
    user_id:    int
    behavior:   str
    endpoint:   str
    status:     int
    latency_ms: float
    error:      Optional[str] = None
    ok:         bool = True

results: list[Result] = []
results_lock = asyncio.Lock()

async def record(r: Result):
    async with results_lock:
        results.append(r)

async def req(client, method, url, user_id, behavior, endpoint, **kwargs):
    start = time.perf_counter()
    try:
        r = await client.request(method, url, timeout=120, **kwargs)
        latency = (time.perf_counter() - start) * 1000
        ok = r.status_code < 500
        result = Result(user_id, behavior, endpoint, r.status_code, latency, ok=ok)
        if not ok:
            result.error = r.text[:120]
        body = None
        try:
            body = r.json()
        except:
            pass
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        result = Result(user_id, behavior, endpoint, 0, latency,
                        error=str(e)[:120], ok=False)
        body = None
    await record(result)
    icon = "✓" if result.ok else "✗"
    print(f"  [{icon}] user={user_id:03d} {behavior:<12} {endpoint:<25} "
          f"{result.status} {latency:.0f}ms"
          + (f"  ← {result.error}" if result.error else ""))
    return result, body

# ── Real search — returns (Result, first_item|None) ──────────────────────────
async def real_search(client, host, user_id, behavior, query):
    result, body = await req(client, "GET", f"{host}/api/search?q={query}",
                             user_id, behavior, "/api/search")
    if not result.ok or not body:
        return None
    items = body if isinstance(body, list) else []
    available = [i for i in items if i.get("hasResource")]
    return available[0] if available else (items[0] if items else None)

# ── User behaviors ────────────────────────────────────────────────────────────
async def user_searcher(client, host, user_id):
    for _ in range(random.randint(2, 4)):
        await real_search(client, host, user_id, "searcher", random.choice(SEARCH_QUERIES))
        await asyncio.sleep(random.uniform(0.5, 2.0))

async def user_browser(client, host, user_id):
    await req(client, "GET", f"{host}/", user_id, "browser", "GET /")
    await asyncio.sleep(random.uniform(0.2, 0.8))
    await req(client, "GET", f"{host}/api/files", user_id, "browser", "/api/files")
    await asyncio.sleep(random.uniform(0.2, 0.8))
    await req(client, "GET", f"{host}/api/jobs", user_id, "browser", "/api/jobs")
    await asyncio.sleep(random.uniform(0.2, 0.8))
    await real_search(client, host, user_id, "browser", random.choice(SEARCH_QUERIES))

async def user_streamer(client, host, user_id):
    item = await real_search(client, host, user_id, "streamer", random.choice(SEARCH_QUERIES))
    if not item:
        print(f"  [!] user={user_id:03d} streamer — no result, skipping play")
        return
    await asyncio.sleep(random.uniform(0.5, 1.5))
    payload = {
        "detailPath":    item.get("detailPath") or item.get("title"),
        "subjectId":     str(item.get("subjectId") or item.get("id", "")),
        "title":         item.get("title", ""),
        "season":        random.randint(1, 2),
        "episode":       random.randint(1, 5),
        "screen_width":  2160,
        "screen_height": 3840,
        "orientation":   "portrait-primary",
    }
    await req(client, "POST", f"{host}/api/play",
              user_id, "streamer", "/api/play", json=payload)
    for _ in range(4):
        await asyncio.sleep(3)
        await req(client, "GET", f"{host}/api/jobs", user_id, "streamer", "/api/jobs")

async def user_downloader(client, host, user_id):
    item = await real_search(client, host, user_id, "downloader", random.choice(SEARCH_QUERIES))
    if not item:
        print(f"  [!] user={user_id:03d} downloader — no result, skipping download")
        return
    await asyncio.sleep(random.uniform(0.5, 1.5))
    ep_count = random.choices([1, 2, 3, 5], weights=[40, 30, 20, 10])[0]
    season   = random.randint(1, 2)
    for ep in range(1, ep_count + 1):
        payload = {
            "detailPath": item.get("detailPath") or item.get("title"),
            "subjectId":  str(item.get("subjectId") or item.get("id", "")),
            "title":      item.get("title", ""),
            "season":     season,
            "episode":    ep,
        }
        await req(client, "POST", f"{host}/api/download",
                  user_id, "downloader", "/api/download", json=payload)
        await asyncio.sleep(random.uniform(0.2, 0.8))

async def user_mixed(client, host, user_id):
    item = await real_search(client, host, user_id, "mixed", random.choice(SEARCH_QUERIES))
    if not item:
        return
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await req(client, "GET", f"{host}/api/files", user_id, "mixed", "/api/files")
    await asyncio.sleep(0.5)
    if random.random() > 0.5:
        payload = {
            "detailPath":   item.get("detailPath") or item.get("title"),
            "subjectId":    str(item.get("subjectId") or item.get("id", "")),
            "title":        item.get("title", ""),
            "season":       1, "episode": 1,
            "screen_width": 2160, "screen_height": 3840,
            "orientation":  "portrait-primary",
        }
        await req(client, "POST", f"{host}/api/play",
                  user_id, "mixed", "/api/play", json=payload)
    else:
        payload = {
            "detailPath": item.get("detailPath") or item.get("title"),
            "subjectId":  str(item.get("subjectId") or item.get("id", "")),
            "title":      item.get("title", ""),
            "season": 1, "episode": random.randint(1, 3),
        }
        await req(client, "POST", f"{host}/api/download",
                  user_id, "mixed", "/api/download", json=payload)

BEHAVIOR_MAP = {
    "searcher":   user_searcher,
    "streamer":   user_streamer,
    "downloader": user_downloader,
    "browser":    user_browser,
    "mixed":      user_mixed,
}

def assign_behavior(user_id, total):
    pct = user_id / total
    if pct < 0.25: return "searcher"
    if pct < 0.50: return "streamer"
    if pct < 0.70: return "downloader"
    if pct < 0.85: return "browser"
    return "mixed"

async def run_load_test(host, total_users):
    print(f"\n{'═'*60}")
    print(f"  Magpie Load Test — {total_users} users → {host}")
    print(f"{'═'*60}\n")

    async def spawn_user(user_id):
        await asyncio.sleep(random.uniform(0, 8.0))
        behavior = assign_behavior(user_id, total_users)
        async with httpx.AsyncClient() as client:
            try:
                await BEHAVIOR_MAP[behavior](client, host, user_id)
            except Exception as e:
                print(f"  [!] user={user_id:03d} {behavior} crashed: {e}")

    start = time.perf_counter()
    await asyncio.gather(*[spawn_user(i) for i in range(1, total_users + 1)])
    total_time = time.perf_counter() - start

    print(f"\n{'═'*60}")
    print(f"  RESULTS — {len(results)} requests in {total_time:.1f}s")
    print(f"{'═'*60}")

    ok     = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    lat    = [r.latency_ms for r in results]

    print(f"  Total requests : {len(results)}")
    print(f"  Successful     : {len(ok)}  ({len(ok)/len(results)*100:.1f}%)")
    print(f"  Failed         : {len(failed)}  ({len(failed)/len(results)*100:.1f}%)")
    print(f"  Avg latency    : {sum(lat)/len(lat):.0f}ms")
    print(f"  Max latency    : {max(lat):.0f}ms")
    print(f"  Min latency    : {min(lat):.0f}ms")
    print(f"  Requests/sec   : {len(results)/total_time:.1f}")

    endpoints = {}
    for r in results:
        e = endpoints.setdefault(r.endpoint, {"ok": 0, "fail": 0, "lat": []})
        e["lat"].append(r.latency_ms)
        if r.ok: e["ok"] += 1
        else:    e["fail"] += 1

    print(f"\n  {'Endpoint':<28} {'OK':>5} {'Fail':>5} {'Avg ms':>8} {'Max ms':>8}")
    print(f"  {'-'*58}")
    for ep, d in sorted(endpoints.items()):
        avg = sum(d["lat"]) / len(d["lat"])
        print(f"  {ep:<28} {d['ok']:>5} {d['fail']:>5} {avg:>8.0f} {max(d['lat']):>8.0f}")

    behaviors = {}
    for r in results:
        b = behaviors.setdefault(r.behavior, {"ok": 0, "fail": 0})
        if r.ok: b["ok"] += 1
        else:    b["fail"] += 1

    print(f"\n  {'Behavior':<15} {'OK':>5} {'Fail':>5}")
    print(f"  {'-'*27}")
    for beh, d in sorted(behaviors.items()):
        print(f"  {beh:<15} {d['ok']:>5} {d['fail']:>5}")

    if failed:
        print(f"\n  Failed requests:")
        for r in failed[:15]:
            print(f"    user={r.user_id:03d} {r.endpoint:<25} {r.status} {r.error}")
        if len(failed) > 15:
            print(f"    ... and {len(failed)-15} more")

    print(f"\n{'═'*60}\n")

    with open("load_test_report.json", "w") as f:
        json.dump({
            "host": host, "users": total_users,
            "total_requests": len(results),
            "success_rate": len(ok) / len(results),
            "avg_latency_ms": sum(lat) / len(lat),
            "max_latency_ms": max(lat),
            "requests_per_sec": len(results) / total_time,
            "failures": [{"user": r.user_id, "endpoint": r.endpoint,
                          "status": r.status, "error": r.error} for r in failed],
        }, f, indent=2)
    print(f"  Report saved → load_test_report.json\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",  default="http://localhost:5000")
    parser.add_argument("--users", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(run_load_test(args.host, args.users))
