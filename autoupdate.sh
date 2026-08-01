#!/bin/bash

REPO="engineermarcus/magpie"
FILE="downloader.py"
LOCAL="$(dirname "$0")/$FILE"
BRANCH="main"

remote_hash=$(curl -sf "https://raw.githubusercontent.com/$REPO/$BRANCH/$FILE" | md5sum | cut -d' ' -f1)
local_hash=$(md5sum "$LOCAL" | cut -d' ' -f1)

if [ "$remote_hash" != "$local_hash" ]; then
    echo "[update] Pulling..."
    git -C "$(dirname "$0")" pull origin "$BRANCH"
else
    echo "[update] Up to date."
fi
