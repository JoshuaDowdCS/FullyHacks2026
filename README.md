# Superpowers

Automated object detection dataset labeling. Drop images, type a prompt, get YOLO-labeled data.

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

# 4. Add images to dataset/images/

# 5. Launch (starts backend on :8001 + frontend on :5173)
./start.sh
```

## CLI Usage

Run the labeling pipeline directly without the UI:

```bash
python -m detection_pipeline --prompt "basketball"
```

Options: `--threshold`, `--image-dir`, `--label-dir`, `--keep-model-cache`, `--refresh-model`.

## Project Structure

```
detection_pipeline/   # Core pipeline: discovery, inference, Gemini, YOLO utils
api/                  # FastAPI review server (keep/discard/undo/upload)
ui/                   # React + Vite review UI
tests/                # 74 unit + integration tests
tools/                # Standalone scrapers (web images, YouTube frames)
models/               # YOLO weights (gitignored, auto-downloaded on first run)
dataset/              # images/ and labels/ (gitignored)
docs/                 # Design specs
```

## Tests

```bash
pytest tests/
```
