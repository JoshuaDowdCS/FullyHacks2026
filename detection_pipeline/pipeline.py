"""Main pipeline orchestration.

End-to-end flow:
  1. Optional Gemini query expansion
  2. Roboflow discovery → select one model
  3. Download / cache model
  4. Per-image: local inference → threshold → Gemini fallback
  5. Return structured results (images + labels) — caller controls upload
  6. Batch-end model cleanup
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import PipelineConfig
from .discovery import DiscoveredModel, discover_model, normalize_query
from .gemini_client import GeminiClient, GeminiOutcome
from .local_inference import LocalModel
from .yolo import YoloBox, normalize_box

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"})


# -----------------------------------------------------------------------
# Per-image result
# -----------------------------------------------------------------------

@dataclass
class ImageResult:
    """Detection result for a single image — returned to caller."""

    image_path: Path
    boxes: list[YoloBox] = field(default_factory=list)
    source: str = ""  # "roboflow", "gemini", or ""
    not_found: bool = False  # Gemini said OBJECT NOT FOUND
    error: str = ""  # non-empty if processing failed


# -----------------------------------------------------------------------
# Batch statistics
# -----------------------------------------------------------------------

class BatchStats:
    """Accumulates per-image outcomes for the final summary."""

    def __init__(self) -> None:
        self.total = 0
        self.labeled = 0
        self.roboflow_labeled = 0
        self.gemini_labeled = 0
        self.deleted = 0
        self.skipped_error = 0
        self.gemini_calls = 0
        self.mode = "unknown"

    def log_summary(self) -> None:
        logger.info("=" * 60)
        logger.info("BATCH SUMMARY")
        logger.info("  Mode            : %s", self.mode)
        logger.info("  Total images    : %d", self.total)
        logger.info("  Labeled         : %d  (Roboflow %d | Gemini %d)",
                     self.labeled, self.roboflow_labeled, self.gemini_labeled)
        logger.info("  Deleted (absent): %d", self.deleted)
        logger.info("  Skipped (error) : %d", self.skipped_error)
        logger.info("  Gemini calls    : %d", self.gemini_calls)
        logger.info("=" * 60)


# -----------------------------------------------------------------------
# Top-level entry point
# -----------------------------------------------------------------------

def run_pipeline(config: PipelineConfig) -> tuple[BatchStats, list[ImageResult]]:
    """Execute the full detection-labeling pipeline.

    Returns (stats, results) where results is a list of ImageResult
    containing each image path and its detected boxes. The caller
    is responsible for writing labels and uploading.
    """
    stats = BatchStats()
    results: list[ImageResult] = []

    # --- validate inputs ---
    if not config.images_dir.is_dir():
        raise FileNotFoundError(f"Images directory not found: {config.images_dir}")

    images = sorted(
        p for p in config.images_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTENSIONS
    )
    stats.total = len(images)

    if not images:
        logger.warning("No images found in %s", config.images_dir)
        return stats, results

    logger.info("Found %d images in %s", len(images), config.images_dir)

    # --- Gemini client (if configured) ---
    gemini: GeminiClient | None = None
    if config.gemini_configured:
        gemini = GeminiClient(config.gemini_base_url, config.gemini_api_key)

    # --- Step 1: optional query expansion ---
    search_query = normalize_query(config.prompt)
    if config.expand_query_with_gemini and gemini:
        search_query = gemini.expand_query(config.prompt)
    logger.info("Search query: %r  (prompt: %r)", search_query, config.prompt)

    # --- Step 2: Roboflow discovery ---
    model_info: DiscoveredModel | None = None
    local_model: LocalModel | None = None

    if config.roboflow_configured:
        try:
            model_info = discover_model(search_query, config.roboflow_api_key)
        except Exception as exc:
            logger.error("Roboflow discovery failed: %s", exc)
            if not config.gemini_configured:
                raise RuntimeError(
                    "Roboflow discovery failed and Gemini is not configured — aborting"
                ) from exc

    # --- Step 3: download + load model ---
    if model_info is not None:
        try:
            local_model = LocalModel(
                model_id=model_info.model_id,
                api_key=config.roboflow_api_key,
                cache_dir=config.cache_dir,
            )
            local_model.load(force_download=config.refresh_model)
            stats.mode = f"Roboflow+local ({model_info.model_id})"
        except RuntimeError as exc:
            logger.error("Model load failed: %s — falling back", exc)
            local_model = None

    # Determine batch mode
    if local_model is None:
        if not config.gemini_configured:
            raise RuntimeError(
                "No Roboflow model available and Gemini is not configured — aborting"
            )
        stats.mode = (
            "Gemini-only (no model found)"
            if model_info is None
            else "Gemini-only (model load failed)"
        )
        logger.info("Running in %s", stats.mode)

    # --- Step 4: per-image processing ---
    try:
        for idx, image_path in enumerate(images, 1):
            logger.info("[%d/%d] %s", idx, stats.total, image_path.name)

            if local_model is not None and model_info is not None:
                result = _process_with_roboflow(image_path, config, local_model, model_info, gemini, stats)
            elif gemini is not None:
                result = _process_gemini_only(image_path, config, gemini, stats)
            else:
                logger.error("  No model and no Gemini — skipping")
                stats.skipped_error += 1
                result = ImageResult(image_path=image_path, error="No model and no Gemini")

            results.append(result)
    finally:
        # --- Step 5: batch-end cleanup (§4.2) ---
        if local_model is not None:
            if config.keep_model_cache:
                logger.info("Keeping model cache (--keep-model-cache)")
            else:
                logger.info("Cleaning up model artifacts ...")
                local_model.cleanup()

    stats.log_summary()
    return stats, results


# -----------------------------------------------------------------------
# Per-image routes
# -----------------------------------------------------------------------

def _process_with_roboflow(
    image_path: Path,
    config: PipelineConfig,
    model: LocalModel,
    model_info: DiscoveredModel,
    gemini: GeminiClient | None,
    stats: BatchStats,
) -> ImageResult:
    """Roboflow local inference → threshold → optional Gemini fallback."""
    try:
        detections, img_w, img_h = model.predict(image_path)
    except RuntimeError as exc:
        logger.warning("  Inference error: %s — skipping", exc)
        stats.skipped_error += 1
        return ImageResult(image_path=image_path, error=str(exc))

    raw_count = len(detections)
    filtered = [d for d in detections if d.confidence >= config.conf_threshold]
    logger.info(
        "  Roboflow: %d raw, %d after threshold (>=%.2f)  model=%s",
        raw_count, len(filtered), config.conf_threshold, model_info.model_id,
    )

    if filtered:
        boxes = [
            normalize_box(
                d.x_center_px, d.y_center_px, d.width_px, d.height_px,
                img_w, img_h, d.class_id,
            )
            for d in filtered
        ]
        logger.info("  -> %d detections from Roboflow", len(boxes))
        stats.labeled += 1
        stats.roboflow_labeled += 1
        return ImageResult(image_path=image_path, boxes=boxes, source="roboflow")
    elif gemini is not None:
        logger.info("  -> No detections after threshold — calling Gemini")
        return _handle_gemini(image_path, config.prompt, gemini, stats)
    else:
        logger.info("  -> No detections and Gemini not configured — skipping")
        stats.skipped_error += 1
        return ImageResult(image_path=image_path)


def _process_gemini_only(
    image_path: Path,
    config: PipelineConfig,
    gemini: GeminiClient,
    stats: BatchStats,
) -> ImageResult:
    """Gemini-only path (no Roboflow model available for this batch)."""
    return _handle_gemini(image_path, config.prompt, gemini, stats)


# -----------------------------------------------------------------------
# Gemini outcome handler (shared)
# -----------------------------------------------------------------------

def _handle_gemini(
    image_path: Path,
    prompt: str,
    gemini: GeminiClient,
    stats: BatchStats,
) -> ImageResult:
    """Call Gemini and return an ImageResult (no filesystem side-effects)."""
    stats.gemini_calls += 1
    outcome = gemini.label_image(image_path, prompt)

    if outcome.error:
        logger.warning("  Gemini error: %s — skipping", outcome.error)
        stats.skipped_error += 1
        return ImageResult(image_path=image_path, error=outcome.error)

    elif outcome.not_found:
        logger.info("  Gemini: OBJECT NOT FOUND")
        stats.deleted += 1
        return ImageResult(image_path=image_path, not_found=True)

    elif outcome.has_detections:
        logger.info("  Gemini: %d detections", len(outcome.boxes))
        stats.labeled += 1
        stats.gemini_labeled += 1
        return ImageResult(image_path=image_path, boxes=outcome.boxes, source="gemini")

    else:
        logger.warning("  Gemini returned empty detections — skipping")
        stats.skipped_error += 1
        return ImageResult(image_path=image_path)
