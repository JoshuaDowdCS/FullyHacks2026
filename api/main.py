"""FastAPI server — thin wrapper around detection_pipeline for the Review UI."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
    StatsResponse,
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

# ---------------------------------------------------------------------------
# Server state
# ---------------------------------------------------------------------------

_project_root = Path(__file__).resolve().parent.parent
_prompt: str = os.environ.get("PIPELINE_PROMPT", "basketball")
_images_dir = Path(os.environ.get("IMAGES_DIR", str(_project_root / "dataset" / "images")))
_labels_dir = Path(os.environ.get("LABELS_DIR", str(_project_root / "dataset" / "labels")))
_conf_threshold: float = float(os.environ.get("CONF_THRESHOLD", "0.7"))

_config = PipelineConfig(
    images_dir=_images_dir,
    labels_dir=_labels_dir,
    prompt=_prompt,
    conf_threshold=_conf_threshold,
    keep_model_cache=True,
)

# Pipeline results keyed by filename — populated after run_pipeline
_pipeline_results: dict[str, ImageResult] = {}

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

    _keep_counter += 1
    ext = resolved.suffix.lower()
    new_name = f"img_{_keep_counter:04d}{ext}"
    new_image = _images_dir / new_name

    resolved.rename(new_image)

    # Update pipeline results with new filename/path
    old_result = _pipeline_results.pop(filename, None)
    if old_result is not None:
        old_result.image_path = new_image
        _pipeline_results[new_name] = old_result

    return KeepResponse(new_filename=new_name)


@app.post("/api/images/{filename}/discard", status_code=204)
def discard_image(filename: str):
    """Delete an image and remove it from pipeline results."""
    resolved = (_images_dir / filename).resolve()
    if not resolved.parent.samefile(_images_dir.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden")

    resolved.unlink(missing_ok=True)
    _label_path(resolved).unlink(missing_ok=True)
    _pipeline_results.pop(filename, None)


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
