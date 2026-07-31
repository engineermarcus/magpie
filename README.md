# Magpie Movie Box

A headless movie and series downloader for Android. Runs on Termux via a proot Ubuntu 24.04 container powered by Playwright and Python.

---

## Requirements

- Android with [Termux](https://f-droid.org/packages/com.termux/) 
- ~2GB free storage
- Internet connection

---

## Getting Started

### Step 1 — Install

Run this once on any fresh Termux installation:

```bash
pkg update -y && pkg update -y && pkg install git python3 curl wget -y 
```
##### Setup Storage 

```bash 
termux-setup-storage
```
## INSTALL THE BIRD 

```bash
curl -fsSL https://raw.githubusercontent.com/engineermarcus/moviebox-api/main/magpie -o $PREFIX/bin/magpie && chmod +x $PREFIX/bin/magpie && magpie install
```

This will:
- Install git if missing
- Clone the repo
- Set up Ubuntu 24.04 inside Termux
- Install Python, Playwright and Chromium
- Register `magpie` as a global command

### Step 2 — Enter Ubuntu

All downloads run inside the Ubuntu container:

```bash
magpie migrate
```

You are now inside Ubuntu. Your home directory is shared so files are accessible from both Termux and Ubuntu.

### Step 3 — Install Dependencies

Run this once inside Ubuntu after first entering:

```bash
magpie start
```

This installs all Python packages and Playwright browser dependencies.

---

### Step 2 — Download

You are already in the right environment — no container to enter. Go straight to downloading:

```bash
magpie --download "Breaking Bad" --pick1 --s1 --ep1
```

### Step3 - Move To Device Storage 

```bash
magpie --transfer-to-storage 
```

### Step 4  — Uninstall, well if you want to 

```bash
magpie remove
```

---

## Downloading

### Basic search

Search by title — results are listed and you pick:

```bash
magpie --download "Breaking Bad"
```

### Pick and download a specific episode

```bash
magpie --download "Breaking Bad" --pick1 --s1 --ep3
```

### Pick and download multiple episodes

```bash
magpie --download "The Flash" --pick1 --s1 --ep3 --ep4 --ep5
```

### Pick and download a full season

```bash
magpie --download "Breaking Bad" --pick1 --s2
```

### Pick and download multiple seasons

```bash
magpie --download "The Flash" --pick1 --s1 --s2 --s3
```

### Pick and download everything

```bash
magpie --download "Breaking Bad" --pick1 -a
```

### Show metadata only — no download

```bash
magpie --download "Breaking Bad" --pick1 --info
```

### Get stream URL only — no download

```bash
magpie --download "Inception" --pick1 --url
```

### Download and upload to Internet Archive

```bash
magpie --download "Breaking Bad" --pick1 -a --upload
```

The local file is deleted automatically after a successful upload.

---

## After Downloading

Once a download finishes, move the files into storage:

```bash
magpie --transfer-to-storage
```
## Get Future Updates 

```bash 
cd ~/moviebox-api && git pull origin main 
```
---

## Flags

| Flag | Description |
|------|-------------|
| `--pickN` | Pick search result N e.g. `--pick1`. Without this flag you are prompted interactively |
| `--sN` | Season N e.g. `--s1`. Stackable: `--s1 --s2 --s3` |
| `--epN` | Episode N e.g. `--ep3`. Stackable: `--ep3 --ep4 --ep5` |
| `-a` | Download all seasons |
| `--info` | Show show metadata from TVMaze only, no download |
| `--url` | Print stream URL only, no download |
| `--json` | Output results as JSON |
| `--upload` | Upload to Internet Archive after download, deletes local file |

---

## Internet Archive Upload

To enable uploading, add your credentials to a `.env` file in the project root:

```env
IA_ACCESS_KEY=your_access_key
IA_SECRET_KEY=your_secret_key
```

Get free keys at [archive.org/account/s3.php](https://archive.org/account/s3.php)

---

## Returning Users

If you have already installed magpie and want to start downloading again, just enter Ubuntu:

```bash
magpie migrate
```

---

## Uninstall

To remove everything — repo, Ubuntu container, global command and PATH entries:

```bash
magpie remove
```

Then run `hash -r` to clear the shell cache.

---

## How It Works

1. Playwright loads moviebox.ph headlessly and extracts search results from the page
2. Results are scored by title match, resource availability and season — best is picked automatically
3. Playwright loads the player page and intercepts the stream API response in real time
4. The highest resolution stream is selected and downloaded via httpx in 1MB chunks with live progress
5. Full seasons are bundled into a single zip archive and individual files deleted
6. With `--upload`, files stream to Internet Archive in 8MB chunks and are deleted locally after

---

## Project Structure

```
moviebox-api/
├── magpie           # CLI
├── downloader.py    # Core engine
├── setup.sh         # Ubuntu + Playwright setup
├── install.sh       # Dep installer (inside Ubuntu)
├── requirements.txt # Python dependencies
└── storage/
    └── movies/      # Downloads land here
```

---

## Linux (Debian / Ubuntu)

On Linux there is no container setup — magpie installs everything directly on your system.

### Step 1 — Install

```bash
curl -fsSL https://raw.githubusercontent.com/engineermarcus/moviebox-api/main/magpie -o magpie && chmod +x magpie && sudo mv magpie /usr/local/bin/magpie && magpie install
```

This will:
- Install Python, pip, git and zip via apt
- Clone the repo
- Install all Python dependencies
- Install Playwright and Chromium
- Register `magpie` as a global command



## Disclaimer

For personal and educational use only. Respect copyright laws in your jurisdiction.

---

## License

MIT

