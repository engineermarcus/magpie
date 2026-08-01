#!/bin/bash
SUDO=""
if [ "$(id -u)" != "0" ]; then
    SUDO="sudo"
fi

$SUDO apt update && $SUDO apt install zip -y
pip install -r "$HOME/magpie/requirements.txt" --break-system-packages
python3 -m playwright install --with-deps chromium
