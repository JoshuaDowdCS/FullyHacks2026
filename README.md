# Superpowers

Automated object detection dataset labeling. Type a prompt, choose an image source, and get a YOLO-labeled dataset — reviewed and uploaded — without manual annotation.

## How It Works

1. **Acquire images** — use existing images, scrape the web (Bing, Baidu, Google, Open Images), or extract frames from YouTube videos
2. **Detect objects** — Roboflow Universe model discovery + local YOLO inference, with Gemini fallback for uncertain detections
3. **Review labels** — tinder-style swipe UI with bounding box overlays, undo support, and threshold restart
4. **Upload dataset** — push curated images + labels directly to a Roboflow project

The pipeline uses three-tier confidence routing: high-confidence detections are kept, uncertain ones get a Gemini second opinion, and low-confidence images are removed. Errors at any stage preserve images — no data loss from transient failures.

## Quick Start

```bash
# 1. Set up Python environment
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. Install frontend dependencies
cd ui && npm install && cd ..

# 3. Set API keys in .env
#    GEMINI_API_KEY=...
#    ROBOFLOW_API_KEY=...

# 4. Launch (starts backend on :8001 + frontend on :5173)
./start.sh
```

The home screen lets you choose an image source and prompt. For existing images, add them to `dataset/images/` before launching.

## CLI Usage

Run the labeling pipeline directly without the UI:

```bash
python -m detection_pipeline --prompt "basketball"
python -m detection_pipeline --prompt "fire hydrant" --source web --count 200
```

Options: `--threshold`, `--source` (existing/web/youtube), `--count`, `--image-dir`, `--label-dir`, `--keep-model-cache`, `--refresh-model`.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| CV inference | Roboflow `inference` SDK (local YOLO) |
| LLM fallback | Google Gemini API (`gemini-2.5-flash`) |
| Model search | Roboflow Universe API |
| Backend | FastAPI + uvicorn |
| Frontend | React 19 + TypeScript + Vite 5 |
| Styling | Tailwind CSS 4 + Framer Motion 12 |
| Image scraping | icrawler + CLIP dedup |
| Video frames | yt-dlp + ffmpeg |
| Testing | pytest (73 tests across 5 modules) |

## Project Structure

```
detection_pipeline/   # Core pipeline: discovery, inference, Gemini, YOLO utils
api/                  # FastAPI review server (keep/discard/undo/upload)
ui/                   # React + Vite review UI (ocean-themed)
tools/                # Image acquisition (web scraper, YouTube frame extractor)
tests/                # 73 unit + integration tests
models/               # YOLO weights (gitignored, auto-downloaded on first run)
dataset/              # images/ and labels/ (gitignored)
docs/                 # Design specs
```

## Tests

```bash
pytest tests/
```
