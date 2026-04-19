# Superpowers: Auto-Label Any Object Detection Dataset

> **v1 — 2026-04-19**
> Do not modify this section — append new versions below.

## What it does

Drop a folder of images, type what you're looking for ("basketball", "fire hydrant"), and Superpowers automatically labels every image with YOLO bounding boxes — then lets you review, filter, and upload the finished dataset to Roboflow in a deep-ocean-themed UI.

## How we built it

### Pipeline Overview

```
User types a prompt (e.g. "basketball")
  │
  ├─[1] Query Expansion ─── Gemini rewrites prompt into search terms
  │
  ├─[2] Model Discovery ── Search Roboflow Universe for detection models
  │       └─ Hard filters (must be detection, must have weights)
  │       └─ Relevance scoring (name match +3, class match +2.5, focus bonus, etc.)
  │       └─ Top 5 ranked candidates
  │
  ├─[3] Local Inference ── Download best model, run on every image locally
  │       └─ Three-tier confidence routing:
  │           ├─ conf ≥ 0.7  →  write YOLO label (done)
  │           ├─ 0.4–0.7    →  defer to Gemini (uncertain)
  │           └─ conf < 0.4  →  delete image (object absent)
  │
  ├─[4] Gemini Fallback ── Batch-send uncertain images to Gemini
  │       └─ Returns bounding boxes OR "OBJECT NOT FOUND" sentinel
  │       └─ Boxes → write label; sentinel → delete image; error → skip
  │
  ├─[5] Review UI ───────── Tinder-style card swipe interface
  │       └─ Keep (rename sequentially) / Discard (delete) / Undo (3 levels)
  │       └─ Restart at higher threshold if quality is low
  │
  └─[6] Upload ─────────── Concurrent upload to Roboflow project
```

### Key Technical Details

- **Relevance-scored model discovery:** We search Roboflow Universe and score each model transparently — exact name match (+3.0), search term in class list (+2.5), substring in name (+2.0), focus bonus (+1.5/N classes), description/tag match (+1.0), dataset size bonuses (+0.5/+1.0). Only detection models pass hard filters; minimum score 1.0. All scoring is our own logic, not Roboflow's ranking.

- **Three-tier confidence routing:** Instead of a binary keep/drop, we route images through three tiers. High-confidence Roboflow detections (>=0.7) are kept directly. Uncertain detections (0.4-0.7) are deferred to Gemini for a second opinion. Low-confidence (<0.4) images are deleted. This avoids both false positives and false negatives.

- **Gemini bounding box contract:** We call Gemini with a strict contract — return `[ymin, xmin, ymax, xmax]` lines in 0-1000 scale, or the exact string `OBJECT NOT FOUND`. We parse with three fallback strategies (Gemini native format, YOLO format, validation). Only the explicit sentinel triggers deletion; errors and malformed responses are non-destructive skips.

- **Deterministic filesystem rules:** Images are only deleted when Gemini explicitly says the object is absent. Errors at any stage (discovery failure, model load failure, inference timeout, Gemini error) always preserve the image. This prevents data loss from transient failures.

- **Two-pass image renaming:** To avoid filename collisions during batch rename, we use a two-pass strategy: first rename all to `_tmp_*` prefixed names, then rename sequentially to `0001.jpg`, `0002.jpg`, etc.

- **SSE streaming pipeline progress:** The backend runs the pipeline in a background thread, posting events to an `asyncio.Queue`. The frontend consumes Server-Sent Events for real-time per-step progress (discovery, download, inference, gemini_batch, done) with current/total counts.

- **Bounding box visualization:** Review UI renders cyan bounding boxes with a dark SVG overlay that cuts out each detection region using `fillRule="evenodd"`, plus corner accents and class labels in uppercase monospace.

- **Ocean creature action buttons:** Discard = anglerfish (pink, glowing lure), restart = nautilus (blue, spiral shell), keep = sea turtle (mint, stroking flippers). Each has idle animations, hover spring physics (scale 1.12x, lift -6px), and thematic connection to its action.

### What we used

| Layer | Technology |
|-------|-----------|
| CV inference | Roboflow `inference` SDK (local YOLO execution) |
| LLM fallback | Google Gemini API (`gemini-2.5-flash`) |
| Model search | Roboflow Universe API |
| Backend | FastAPI + uvicorn |
| Frontend | React 19 + TypeScript + Vite 5 |
| Styling | Tailwind CSS 4 + custom CSS animations |
| Animation | Framer Motion 12 |
| Image processing | Pillow + OpenCV (headless) |
| Testing | pytest (74 tests) |
| Dataset upload | Roboflow Upload API |

## Challenges we ran into

- **Model download failures:** Roboflow Universe models sometimes fail to load locally. We try up to 5 ranked candidates sequentially and fall back to Gemini-only labeling if all fail — the pipeline never crashes, it degrades gracefully.

- **Confidence gating complexity:** A single threshold is too rigid. Setting it high misses uncertain objects; setting it low floods labels with false positives. The three-tier routing with Gemini fallback for the uncertain band solved this without requiring the user to tune parameters.

- **Safe image deletion:** Deleting images on errors would lose data. We designed the Gemini contract with an explicit `OBJECT NOT FOUND` sentinel — only that exact string (case-insensitive) triggers deletion. Empty responses, timeouts, and malformed output all result in non-destructive skips.

- **Concurrent Gemini calls at scale:** Batching 100+ images to Gemini required a ThreadPoolExecutor with per-image result callbacks so the progress UI updates in real-time via SSE, rather than blocking until the entire batch completes.

- **Restart mid-review:** When the user restarts the pipeline at a higher confidence threshold, the label set changes under the review UI. We handle this with a full state reset — clear undo stack, reset counters, reload image list from the API — behind a confirmation modal showing the new threshold.

## What we learned

- Transparent scoring systems (showing judges your own math, not just "we used AI") make the technical depth visible even when the final UX looks simple.
- Multi-system orchestration (Roboflow discovery + local inference + Gemini fallback) is more robust than relying on any single service, and the fallback chain itself is a demonstrable engineering decision.
- Streaming progress feedback (SSE) transforms a batch process from "loading spinner for 2 minutes" into a visible, trustworthy pipeline.

---

> **v2 — 2026-04-19**

## What changed

Added multi-source image acquisition so users no longer need to bring their own images.

## New features

### Image Acquisition Pipeline

Users now choose an image source from the home screen before running detection:

```
User types a prompt and picks a source
  │
  ├─ Existing images ── Use what's already in dataset/images/
  │
  ├─ Web scraping ───── icrawler across 4 engines (Bing, Baidu, Google, Open Images)
  │       └─ Gemini bootstraps topic spec (search queries, COCO classes, distractors)
  │       └─ Dedup: byte hash → perceptual hash (imagehash) → CLIP semantic filtering
  │       └─ Streamed progress via SSE
  │
  └─ YouTube frames ── yt-dlp search + ffmpeg frame extraction at 1fps
          └─ Metadata heuristics: filter by duration, exclude livestreams/shorts
          └─ Gemini scores video title+description for relevance
          └─ Same dedup pipeline as web scraping
```

### Key Technical Details

- **Multi-source image acquisition:** Web scraping uses icrawler across four engines with CLIP-based deduplication to filter scene distractors. YouTube acquisition uses yt-dlp to search and download videos, then ffmpeg extracts frames at 1fps with byte + perceptual hash dedup. Both paths stream progress via SSE so the UI updates in real-time. The topic bootstrap (Gemini call → search queries, COCO class matching, distractor descriptions) is shared between both scrapers.

- **Layered deduplication:** Byte-identical hashes catch exact copies, perceptual hashing (imagehash) catches near-duplicates (re-encoded, slightly cropped), and CLIP embeddings filter semantic duplicates — scene distractors that happen to contain the target object.

### Updated tech stack

| Layer | Technology |
|-------|-----------|
| Web scraping | icrawler (Bing, Baidu, Google, Open Images) |
| Video frames | yt-dlp + ffmpeg |
| Deduplication | imagehash (perceptual) + CLIP (semantic) |
| Testing | pytest (73 tests across 5 modules) |

## New challenges

- **Image deduplication at scale:** Web scraping across four engines and YouTube frame extraction at 1fps both generate heavy duplicates. Byte-identical hashes catch exact copies, but near-duplicates (re-encoded, slightly cropped) required perceptual hashing. For semantic deduplication — filtering scene distractors — we use CLIP embeddings to remove images too similar to known distractor descriptions.

## What we learned

- Multi-source data acquisition (web scraping + YouTube frames) with layered deduplication (byte hash → perceptual hash → CLIP embeddings) gives users flexible starting points without drowning in duplicates.
