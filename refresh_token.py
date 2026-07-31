import asyncio
from playwright.async_api import async_playwright

async def refresh():
    token = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox',
            '--disable-dev-shm-usage', '--disable-gpu',
            '--no-zygote', '--single-process'
        ])
        page = await browser.new_page()

        async def on_request(request):
            nonlocal token
            if token:
                return
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer ") and "wefeed" in request.url:
                token = auth.replace("Bearer ", "").strip()
                print(f"[✓] Token captured from: {request.url}")

        page.on("request", on_request)

        # go straight to a content page that triggers API calls
        print("[→] Loading player page...")
        await page.goto(
            "https://123movienow.cc/spa/videoPlayPage/movies/mayor-of-kingstown-adii5ts3MR6"
            "?id=5763754289126593304&type=/movie/detail&detailSe=4&detailEp=1&lang=en",
            wait_until="domcontentloaded", timeout=30000
        )
        # wait up to 10s for token
        for _ in range(20):
            if token:
                break
            await asyncio.sleep(0.5)

        await browser.close()

    if token:
        import os, base64, json, datetime
        path = os.path.join(os.path.dirname(__file__), ".mb_token")
        with open(path, "w") as f:
            f.write(token)
        payload = token.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        data = json.loads(base64.b64decode(payload))
        print(f"[✓] Saved to .mb_token")
        print(f"[i] Expires: {datetime.datetime.fromtimestamp(data['exp'])}")
    else:
        print("[✗] No token found")

asyncio.run(refresh())
