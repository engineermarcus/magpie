#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh — Get Playwright working in Termux via proot-distro
# Run FROM TERMUX: bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────

DISTRO="pw24"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         Playwright Setup — Termux + proot-distro         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: proot-distro ─────────────────────────────────────────────────────
echo "[1/4] Checking proot-distro..."
command -v proot-distro &>/dev/null || pkg install -y proot-distro
echo "[✓] proot-distro ready"

# ── Step 2: Ensure pw24 exists ───────────────────────────────────────────────
echo ""
echo "[2/4] Setting up $DISTRO..."
if proot-distro login "$DISTRO" -- /bin/true 2>/dev/null; then
    echo "[✓] $DISTRO already exists, skipping install"
else
    proot-distro install ubuntu:24.04 --override-alias "$DISTRO"
    echo "[✓] $DISTRO installed"

    # ── Step 3: Python + Playwright + deps ───────────────────────────────────
    echo ""
    echo "[3/4] Installing Python, Playwright and dependencies..."
    proot-distro login "$DISTRO" --bind "$HOME:/root" --bind /sdcard:/sdcard -- /bin/bash -c '
        set -e
        apt update -y &&
        apt install -y python3 python3-pip ffmpeg aria2 &&
        pip3 install --break-system-packages playwright &&
        python3 -m playwright install chromium &&
        python3 -m playwright install-deps chromium &&
        echo "[✓] All done"
    '

    # ── Step 4: Smoke test ───────────────────────────────────────────────────
    echo ""
    echo "[4/4] Smoke test..."
    proot-distro login "$DISTRO" --bind "$HOME:/root" --bind /sdcard:/sdcard -- /bin/bash -c '
    python3 -c "
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[\"--no-sandbox\",\"--disable-setuid-sandbox\",
                  \"--disable-dev-shm-usage\",\"--disable-gpu\",
                  \"--no-zygote\",\"--single-process\"]
        )
        page = await browser.new_page()
        await page.goto(\"https://example.com\", wait_until=\"domcontentloaded\")
        title = await page.title()
        await browser.close()
        print(\"[OK] Playwright works! Title: \" + title)

asyncio.run(test())
"
    '
fi

echo "$DISTRO" > "$HOME/.playwright_distro"


