"""FastAPI server — thin wrapper around detection_pipeline for the Review UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image

from detection_pipeline.config import PipelineConfig
from detection_pipeline.discovery import normalize_query
from detection_pipeline.pipeline import IMAGE_EXTENSIONS, ImageResult, refilter_results, run_pipeline
from detection_pipeline.upload import upload_to_roboflow
from detection_pipeline.yolo import YoloBox, write_classification_label, write_label_file

from . import models
from .models import (
    CLASS_NAMES,
    AcquireWebRequest,
    AcquireYouTubeRequest,
    ImageInfo,
    ImageLabel,
    ImagesResponse,
    KeepResponse,
    RestartResponse,
    RunRequest,
    StatsResponse,
    UndoResponse,
    UploadResponse,
)

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("inference").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Server state
# ---------------------------------------------------------------------------

_project_root = Path(__file__).resolve().parent.parent
_prompt: str = os.environ.get("PIPELINE_PROMPT", "basketball")
_images_dir = Path(os.environ.get("IMAGES_DIR", str(_project_root / "dataset" / "images")))
_labels_dir = Path(os.environ.get("LABELS_DIR", str(_project_root / "dataset" / "labels")))
_conf_threshold: float = float(os.environ.get("CONF_THRESHOLD", "0.7"))
_task_type: str = "detection"

_trash_dir = _images_dir.parent / ".trash"

_config = PipelineConfig(
    images_dir=_images_dir,
    labels_dir=_labels_dir,
    prompt=_prompt,
    conf_threshold=_conf_threshold,
    keep_model_cache=True,
)

# Pipeline results keyed by filename — populated after run_pipeline
_pipeline_results: dict[str, ImageResult] = {}


@dataclass
class _UndoEntry:
    action: str  # "keep" or "discard"
    original_filename: str
    new_filename: str | None  # only for keep
    result: ImageResult
    keep_counter_before: int


_undo_stack: list[_UndoEntry] = []
_MAX_UNDO = 3

# Guards against concurrent /api/run calls: two pipelines renaming the same
# files at once shreds the dataset via the two-pass rename race.
_pipeline_running: bool = False

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Review UI API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_images(labeled_only: bool = False) -> list[Path]:
    """Return sorted image paths from the images directory."""
    if not _images_dir.is_dir():
        return []
    images = sorted(
        p for p in _images_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if labeled_only:
        images = [p for p in images if _label_path(p).exists()]
    return images


# Counter for sequential renaming
_keep_counter: int = 0


def _label_path(image_path: Path) -> Path:
    """Derive the YOLO label file path for a given image."""
    return _labels_dir / f"{image_path.stem}.txt"


def _build_image_info(result: ImageResult) -> ImageInfo:
    """Build an ImageInfo object from a pipeline result."""
    labels = [
        ImageLabel(
            class_id=b.class_id,
            class_name=CLASS_NAMES.get(b.class_id, f"class_{b.class_id}"),
            x_center=b.x_center,
            y_center=b.y_center,
            width=b.width,
            height=b.height,
        )
        for b in result.boxes
    ]

    # Use cached dimensions from pipeline when available, avoid re-opening image
    w, h = result.img_width, result.img_height
    if not w or not h:
        try:
            with Image.open(result.image_path) as img:
                w, h = img.size
        except Exception:
            w, h = 0, 0

    return ImageInfo(
        filename=result.image_path.name,
        width=w,
        height=h,
        labels=labels,
        class_id=result.class_id,
        class_name=result.class_name or None,
        class_confidence=result.class_confidence if result.is_classified else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/images", response_model=ImagesResponse)
def list_images():
    """List images with detections from the last pipeline run.

    Skips entries whose on-disk file has vanished (e.g. from a partial
    rename crash in a previous run) so the UI never tries to render a
    broken image tag."""
    global _keep_counter
    _keep_counter = 0  # reset on reload
    labeled = [
        r for r in _pipeline_results.values()
        if (r.boxes or r.is_classified) and not r.not_found and r.image_path.exists()
    ]
    # Also prune the dict so subsequent keep/discard don't reference ghosts.
    stale = [
        name for name, r in _pipeline_results.items()
        if not r.image_path.exists()
    ]
    for name in stale:
        _pipeline_results.pop(name, None)
    if stale:
        logger.warning("Pruned %d stale pipeline entries with missing files", len(stale))
    images = [_build_image_info(r) for r in labeled]
    return ImagesResponse(
        images=images,
        conf_threshold=_conf_threshold,
        total=len(images),
    )


@app.get("/api/images/{filename}")
def serve_image(filename: str):
    """Serve a single image file."""
    resolved = (_images_dir / filename).resolve()
    if not resolved.parent.samefile(_images_dir.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(resolved, media_type="image/jpeg")


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    """Return current batch stats."""
    total = len(_pipeline_results)
    labeled = sum(1 for r in _pipeline_results.values() if (r.boxes or r.is_classified) and not r.not_found)
    return StatsResponse(
        total=total,
        labeled=labeled,
        conf_threshold=_conf_threshold,
    )


@app.post("/api/images/{filename}/keep", response_model=KeepResponse)
def keep_image(filename: str):
    """Rename an image to a clean sequential name and update pipeline results."""
    global _keep_counter
    resolved = (_images_dir / filename).resolve()
    if not resolved.parent.samefile(_images_dir.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    counter_before = _keep_counter
    _keep_counter += 1
    ext = resolved.suffix.lower()
    new_name = f"img_{_keep_counter:04d}{ext}"
    new_image = _images_dir / new_name

    resolved.rename(new_image)

    old_result = _pipeline_results.pop(filename, None)
    if old_result is not None:
        _undo_stack.append(_UndoEntry(
            action="keep",
            original_filename=filename,
            new_filename=new_name,
            result=old_result,
            keep_counter_before=counter_before,
        ))
        if len(_undo_stack) > _MAX_UNDO:
            _undo_stack.pop(0)
        old_result.image_path = new_image
        _pipeline_results[new_name] = old_result

    return KeepResponse(new_filename=new_name)


@app.post("/api/images/{filename}/discard", status_code=204)
def discard_image(filename: str):
    """Move an image to trash (supports undo)."""
    resolved = (_images_dir / filename).resolve()
    if not resolved.parent.samefile(_images_dir.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden")

    result = _pipeline_results.pop(filename, None)

    _trash_dir.mkdir(parents=True, exist_ok=True)
    if resolved.exists():
        resolved.rename(_trash_dir / filename)
    label = _label_path(resolved)
    if label.exists():
        label.rename(_trash_dir / label.name)

    if result is not None:
        _undo_stack.append(_UndoEntry(
            action="discard",
            original_filename=filename,
            new_filename=None,
            result=result,
            keep_counter_before=_keep_counter,
        ))
        if len(_undo_stack) > _MAX_UNDO:
            evicted = _undo_stack.pop(0)
            if evicted.action == "discard":
                (_trash_dir / evicted.original_filename).unlink(missing_ok=True)
                (_trash_dir / f"{Path(evicted.original_filename).stem}.txt").unlink(missing_ok=True)


@app.post("/api/undo", response_model=UndoResponse)
def undo():
    """Undo the last keep or discard action."""
    global _keep_counter
    if not _undo_stack:
        raise HTTPException(status_code=400, detail="Nothing to undo")

    entry = _undo_stack.pop()

    if entry.action == "keep":
        new_path = _images_dir / entry.new_filename
        original_path = _images_dir / entry.original_filename
        if new_path.exists():
            new_path.rename(original_path)
        _pipeline_results.pop(entry.new_filename, None)
        entry.result.image_path = original_path
        _pipeline_results[entry.original_filename] = entry.result
        _keep_counter = entry.keep_counter_before
        return UndoResponse(action="keep", filename=entry.original_filename)

    # discard — restore from trash
    trash_image = _trash_dir / entry.original_filename
    original_path = _images_dir / entry.original_filename
    if trash_image.exists():
        trash_image.rename(original_path)
    trash_label = _trash_dir / f"{Path(entry.original_filename).stem}.txt"
    label_path = _label_path(original_path)
    if trash_label.exists():
        trash_label.rename(label_path)
    entry.result.image_path = original_path
    _pipeline_results[entry.original_filename] = entry.result
    return UndoResponse(action="discard", filename=entry.original_filename)


@app.post("/api/restart", response_model=RestartResponse)
def restart_pipeline():
    """Re-filter results at a higher threshold without re-running the full pipeline."""
    global _conf_threshold, _config, _pipeline_results

    _conf_threshold = round(_conf_threshold + 0.05, 2)

    _config = PipelineConfig(
        images_dir=_images_dir,
        labels_dir=_labels_dir,
        prompt=_prompt,
        conf_threshold=_conf_threshold,
        keep_model_cache=True,
        expand_query_with_gemini=bool(_config.gemini_configured),
    )

    previous = list(_pipeline_results.values())

    try:
        _stats, results = refilter_results(
            previous,
            new_threshold=_conf_threshold,
            gemini_api_key=_config.gemini_api_key,
            prompt=_prompt,
            task_type=_task_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    _pipeline_results = {r.image_path.name: r for r in results}

    # Write updated labels
    _labels_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        if r.not_found:
            continue
        label_path = _labels_dir / f"{r.image_path.stem}.txt"
        if r.boxes:
            write_label_file(label_path, r.boxes)
        elif r.is_classified:
            write_classification_label(label_path, r.class_id)

    total = len(_pipeline_results)
    labeled = sum(1 for r in _pipeline_results.values() if (r.boxes or r.is_classified) and not r.not_found)

    return RestartResponse(
        stats=StatsResponse(
            total=total,
            labeled=labeled,
            conf_threshold=_conf_threshold,
        ),
        new_threshold=_conf_threshold,
    )


@app.post("/api/run")
async def run(body: RunRequest):
    """Launch the pipeline and stream progress as SSE events."""
    global _pipeline_results, _conf_threshold, _prompt, _config, _keep_counter, _pipeline_running, _task_type

    if _pipeline_running:
        raise HTTPException(
            status_code=409,
            detail="A pipeline run is already in progress. Wait for it to finish.",
        )
    _pipeline_running = True

    # Reset server state
    _pipeline_results = {}
    _conf_threshold = body.conf_threshold
    _prompt = body.prompt
    _task_type = body.task_type
    _keep_counter = 0
    models.CLASS_NAMES = {0: body.prompt}
    _undo_stack.clear()
    if _trash_dir.is_dir():
        shutil.rmtree(_trash_dir, ignore_errors=True)

    _config = PipelineConfig(
        images_dir=_images_dir,
        labels_dir=_labels_dir,
        prompt=body.prompt,
        conf_threshold=body.conf_threshold,
        task_type=body.task_type,
        keep_model_cache=True,
        expand_query_with_gemini=bool(_config.gemini_configured),
    )

    progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_progress(step: str, data: dict) -> None:
        # Called from pipeline thread — use threadsafe put
        loop.call_soon_threadsafe(progress_queue.put_nowait, {"step": step, **data})

    async def run_in_thread() -> None:
        global _pipeline_results, _pipeline_running
        try:
            _stats, results = await asyncio.to_thread(
                run_pipeline, _config, on_progress
            )
            # Write label files to disk immediately
            _labels_dir.mkdir(parents=True, exist_ok=True)
            for r in results:
                if r.not_found:
                    continue
                label_path = _labels_dir / f"{r.image_path.stem}.txt"
                if r.boxes:
                    write_label_file(label_path, r.boxes)
                elif r.is_classified:
                    write_classification_label(label_path, r.class_id)
            # Update global so GET /api/images sees the results
            globals()["_pipeline_results"] = {r.image_path.name: r for r in results}
        except Exception as exc:
            loop.call_soon_threadsafe(
                progress_queue.put_nowait, {"step": "error", "message": str(exc)}
            )
        finally:
            _pipeline_running = False
            loop.call_soon_threadsafe(progress_queue.put_nowait, None)  # sentinel

    async def event_stream():
        task = asyncio.create_task(run_in_thread())
        try:
            while True:
                event = await progress_queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/upload", response_model=UploadResponse)
def upload():
    """Write labels to disk from pipeline results, then upload to Roboflow."""
    if not _config.roboflow_api_key:
        raise HTTPException(status_code=400, detail="ROBOFLOW_API_KEY not configured")

    slug = normalize_query(_prompt).replace(" ", "-")
    suffix = "classification" if _task_type == "classification" else "detection"
    project_name = f"{slug}-{suffix}" if slug else f"{suffix}-pipeline"

    # Labels are already written to disk by the run() endpoint;
    # just count how many we have.
    labeled_count = sum(
        1 for r in _pipeline_results.values() if (r.boxes or r.is_classified) and not r.not_found
    )

    if labeled_count == 0:
        raise HTTPException(status_code=400, detail="No labeled images to upload")

    rf_project_type = (
        "single-label-classification" if _task_type == "classification"
        else "object-detection"
    )
    try:
        upload_to_roboflow(
            images_dir=_images_dir,
            labels_dir=_labels_dir,
            api_key=_config.roboflow_api_key,
            project_name=project_name,
            project_type=rf_project_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return UploadResponse(uploaded=labeled_count, project=project_name)


# ---------------------------------------------------------------------------
# Image acquisition endpoints
# ---------------------------------------------------------------------------

@app.post("/api/acquire/web")
async def acquire_web(body: AcquireWebRequest):
    """Acquire images from the web and stream progress as SSE events."""
    progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_progress(step: str, data: dict) -> None:
        # Swallow the scraper's own "done" — we emit our own after copy so the
        # client sees exactly one terminal event (prevents double launch).
        if step == "done":
            return
        loop.call_soon_threadsafe(progress_queue.put_nowait, {"step": step, **data})

    async def run_in_thread() -> None:
        try:
            from tools.webscraper import run_scraper, slugify

            staging_dir = _project_root / ".scraper_staging" / slugify(body.prompt)
            try:
                count = await asyncio.to_thread(
                    run_scraper,
                    query=body.prompt,
                    out_dir=staging_dir,
                    count=body.count,
                    on_progress=on_progress,
                )

                # Copy acquired images to dataset/images/
                keep_dir = staging_dir / "review" / "keep"
                if keep_dir.is_dir():
                    _images_dir.mkdir(parents=True, exist_ok=True)
                    copied = 0
                    for img in keep_dir.iterdir():
                        if img.is_file():
                            shutil.copy2(img, _images_dir / img.name)
                            copied += 1
                    loop.call_soon_threadsafe(
                        progress_queue.put_nowait,
                        {"step": "done", "message": f"Acquired {copied} images.", "images_acquired": copied},
                    )
            finally:
                shutil.rmtree(staging_dir, ignore_errors=True)
        except ImportError:
            loop.call_soon_threadsafe(
                progress_queue.put_nowait,
                {"step": "error", "message": "Web scraper dependencies not installed (pip install icrawler)"},
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                progress_queue.put_nowait,
                {"step": "error", "message": str(exc)},
            )
        finally:
            loop.call_soon_threadsafe(progress_queue.put_nowait, None)

    async def event_stream():
        task = asyncio.create_task(run_in_thread())
        try:
            while True:
                event = await progress_queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/acquire/youtube")
async def acquire_youtube(body: AcquireYouTubeRequest):
    """Acquire frames from YouTube and stream progress as SSE events."""
    progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_progress(step: str, data: dict) -> None:
        # Swallow the scraper's own "done" — we emit our own after copy so the
        # client sees exactly one terminal event (prevents double launch).
        if step == "done":
            return
        loop.call_soon_threadsafe(progress_queue.put_nowait, {"step": step, **data})

    async def run_in_thread() -> None:
        try:
            from tools.webscraper import slugify
            from tools.ytwebscraper import run_yt_scraper

            staging_dir = _project_root / ".scraper_staging" / f"yt_{slugify(body.prompt)}"
            try:
                count = await asyncio.to_thread(
                    run_yt_scraper,
                    query=body.prompt,
                    out_dir=staging_dir,
                    youtube_url=body.youtube_url,
                    max_videos=body.max_videos,
                    on_progress=on_progress,
                )

                keep_dir = staging_dir / "review" / "keep"
                if keep_dir.is_dir():
                    _images_dir.mkdir(parents=True, exist_ok=True)
                    copied = 0
                    for img in keep_dir.iterdir():
                        if img.is_file():
                            shutil.copy2(img, _images_dir / img.name)
                            copied += 1
                    loop.call_soon_threadsafe(
                        progress_queue.put_nowait,
                        {"step": "done", "message": f"Acquired {copied} frames.", "images_acquired": copied},
                    )
            finally:
                shutil.rmtree(staging_dir, ignore_errors=True)
        except ImportError:
            loop.call_soon_threadsafe(
                progress_queue.put_nowait,
                {"step": "error", "message": "YouTube scraper dependencies not installed (pip install yt-dlp imagehash)"},
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                progress_queue.put_nowait,
                {"step": "error", "message": str(exc)},
            )
        finally:
            loop.call_soon_threadsafe(progress_queue.put_nowait, None)

    async def event_stream():
        task = asyncio.create_task(run_in_thread())
        try:
            while True:
                event = await progress_queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
