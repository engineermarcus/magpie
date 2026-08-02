#!/bin/bash
REPO="engineermarcus/magpie"
BRANCH="main"
DIR="$(dirname "$0")"

echo "[update] Checking for updates..."

# Fetch remote without merging
git -C "$DIR" fetch origin "$BRANCH" --quiet

LOCAL=$(git -C "$DIR" rev-parse HEAD)
REMOTE=$(git -C "$DIR" rev-parse origin/$BRANCH)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[update] Up to date."
else
    echo "[update] Pulling latest changes..."
    git -C "$DIR" merge --ff-only origin/$BRANCH \
        && echo "[update] Done." \
        || echo "[update] Fast-forward failed — you may have local changes. Run 'git pull' manually."
fi
