"""FastAPI server — thin wrapper around detection_pipeline for the Review UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
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
from detection_pipeline.pipeline import IMAGE_EXTENSIONS, ImageResult, run_pipeline
from detection_pipeline.upload import upload_to_roboflow
from detection_pipeline.yolo import YoloBox, write_label_file

from .models import (
    CLASS_NAMES,
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
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/images", response_model=ImagesResponse)
def list_images():
    """List images with detections from the last pipeline run."""
    global _keep_counter
    _keep_counter = 0  # reset on reload
    labeled = [r for r in _pipeline_results.values() if r.boxes and not r.not_found]
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
    labeled = sum(1 for r in _pipeline_results.values() if r.boxes and not r.not_found)
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
    """Re-run the pipeline with confidence threshold increased by +0.05."""
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

    try:
        _stats, results = run_pipeline(_config)
    except (RuntimeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    _pipeline_results = {r.image_path.name: r for r in results}

    total = len(_pipeline_results)
    labeled = sum(1 for r in _pipeline_results.values() if r.boxes and not r.not_found)

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
    global _pipeline_results, _conf_threshold, _prompt, _config, _keep_counter

    # Reset server state
    _pipeline_results = {}
    _conf_threshold = body.conf_threshold
    _prompt = body.prompt
    _keep_counter = 0
    _undo_stack.clear()
    if _trash_dir.is_dir():
        shutil.rmtree(_trash_dir, ignore_errors=True)

    _config = PipelineConfig(
        images_dir=_images_dir,
        labels_dir=_labels_dir,
        prompt=body.prompt,
        conf_threshold=body.conf_threshold,
        keep_model_cache=True,
        expand_query_with_gemini=bool(_config.gemini_configured),
    )

    progress_queue: queue.Queue[dict | None] = queue.Queue()

    def on_progress(step: str, data: dict) -> None:
        progress_queue.put({"step": step, **data})

    async def run_in_thread() -> None:
        global _pipeline_results
        try:
            _stats, results = await asyncio.to_thread(
                run_pipeline, _config, on_progress
            )
            # Write label files to disk immediately
            _labels_dir.mkdir(parents=True, exist_ok=True)
            for r in results:
                if r.boxes and not r.not_found:
                    write_label_file(_labels_dir / f"{r.image_path.stem}.txt", r.boxes)
            # Update global so GET /api/images sees the results
            globals()["_pipeline_results"] = {r.image_path.name: r for r in results}
        except Exception as exc:
            progress_queue.put({"step": "error", "message": str(exc)})
        finally:
            progress_queue.put(None)  # sentinel

    async def event_stream():
        task = asyncio.create_task(run_in_thread())
        try:
            while True:
                try:
                    event = await asyncio.to_thread(progress_queue.get, timeout=0.5)
                except queue.Empty:
                    continue
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
    project_name = f"{slug}-detection" if slug else "detection-pipeline"

    # Write label files for all results that have detections
    _labels_dir.mkdir(parents=True, exist_ok=True)
    labeled_count = 0
    for result in _pipeline_results.values():
        if result.boxes and not result.not_found:
            label_path = _labels_dir / f"{result.image_path.stem}.txt"
            write_label_file(label_path, result.boxes)
            labeled_count += 1

    if labeled_count == 0:
        raise HTTPException(status_code=400, detail="No labeled images to upload")

    try:
        upload_to_roboflow(
            images_dir=_images_dir,
            labels_dir=_labels_dir,
            api_key=_config.roboflow_api_key,
            project_name=project_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return UploadResponse(uploaded=labeled_count, project=project_name)
