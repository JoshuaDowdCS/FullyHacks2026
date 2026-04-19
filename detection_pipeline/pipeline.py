"""Main pipeline orchestration.

End-to-end flow:
  1. Optional Gemini query expansion
  2. Roboflow discovery → select one model
  3. Download / cache model
  4a. Per-image: local inference → threshold → flag uncertain for Gemini
  4b. Batch all flagged images to Gemini concurrently (thread pool)
  5. Return structured results (images + labels) — caller controls upload
  6. Batch-end model cleanup
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .config import PipelineConfig
from .discovery import DiscoveredModel, discover_models, normalize_query
from .gemini_client import GeminiClient
from .local_inference import Detection, LocalModel
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
    img_width: int = 0
    img_height: int = 0
    # Raw YOLO detections (all confidences) for threshold re-filtering on restart
    raw_detections: list[Detection] = field(default_factory=list)


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
# Terminal progress display
# -----------------------------------------------------------------------

class _ProgressDisplay:
    """In-place two-line progress bar written to stderr (TTY only)."""

    BAR_W = 30

    def __init__(self, enabled: bool = True) -> None:
        self._lock = threading.Lock()
        self._lines = 0
        self._active = enabled and sys.stderr.isatty()

    def _bar(self, current: int, total: int) -> str:
        filled = int(self.BAR_W * current / total) if total else 0
        return "⣿" * filled + "⣀" * (self.BAR_W - filled)

    def update(self, *lines: str) -> None:
        if not self._active:
            return
        with self._lock:
            if self._lines:
                sys.stderr.write(f"\033[{self._lines}A\033[J")
            sys.stderr.write("\n".join(lines) + "\n")
            sys.stderr.flush()
            self._lines = len(lines)


# -----------------------------------------------------------------------
# Top-level entry point
# -----------------------------------------------------------------------

def run_pipeline(
    config: PipelineConfig,
    on_progress: Callable[[str, dict], None] | None = None,
) -> tuple[BatchStats, list[ImageResult]]:
    """Execute the full detection-labeling pipeline.

    Returns (stats, results) where results is a list of ImageResult
    containing each image path and its detected boxes. The caller
    is responsible for writing labels and uploading.

    *on_progress*, when provided, is called at key pipeline steps with
    ``(step_name, data_dict)`` — used by the API to stream SSE events.
    """

    def _emit(step: str, **data: object) -> None:
        if on_progress:
            on_progress(step, data)
    stats = BatchStats()
    results: list[ImageResult] = []

    # --- validate inputs ---
    if not config.images_dir.is_dir():
        raise FileNotFoundError(f"Images directory not found: {config.images_dir}")

    # Recover from a previous run that crashed between Pass 1 and Pass 2.
    # If _tmp_XX.ext files are lying around, they ARE your data — don't
    # delete them. Rename them to non-clashing names so the next two-pass
    # rename handles them cleanly.
    for stale in config.images_dir.glob("_tmp_*"):
        if stale.is_file():
            # Strip the `_tmp_` prefix so it re-enters the listing as a
            # normal image. If the derived name already exists, append a
            # suffix so we don't overwrite.
            recovered = stale.with_name(stale.name.removeprefix("_tmp_"))
            suffix = 1
            while recovered.exists():
                recovered = stale.with_name(f"rec_{suffix}_{stale.name.removeprefix('_tmp_')}")
                suffix += 1
            try:
                stale.rename(recovered)
            except OSError as exc:
                logger.warning("Couldn't recover tmp file %s: %s", stale.name, exc)

    raw_images = sorted(
        p for p in config.images_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTENSIONS
        and not p.name.startswith("_tmp_")  # belt-and-suspenders
    )

    if not raw_images:
        logger.warning("No images found in %s", config.images_dir)
        return stats, results

    # --- rename images to clean sequential names (two-pass to avoid collisions) ---
    images: list[Path] = []
    width = len(str(len(raw_images)))

    # Check if images are already in sequential {1..N}.{ext} format — skip rename if so
    already_sequential = all(
        p.stem == f"{i:0{width}}" for i, p in enumerate(raw_images, 1)
    )

    if already_sequential:
        images = list(raw_images)
        logger.debug("Images already sequentially named — skipping rename")
    else:
        # Pass 1: move to temporary names so no target can collide with a source.
        # Use missing_ok semantics so a source file that vanished between
        # listing and rename (e.g. from a concurrent UI keep/discard) doesn't
        # crash the whole pipeline.
        tmp_paths: list[Path] = []
        for i, p in enumerate(raw_images, 1):
            if not p.exists():
                logger.warning("Source vanished before rename; skipping: %s", p.name)
                continue
            tmp_name = f"_tmp_{i:0{width}}{p.suffix.lower()}"
            tmp_path = p.parent / tmp_name
            try:
                p.rename(tmp_path)
            except FileNotFoundError:
                logger.warning("Race: %s disappeared mid-rename; skipping.", p.name)
                continue
            tmp_paths.append(tmp_path)
        # Pass 2: move from temporary names to final sequential names
        renamed = 0
        for i, tmp in enumerate(tmp_paths, 1):
            clean_name = f"{i:0{width}}{tmp.suffix.lower()}"
            new_path = tmp.parent / clean_name
            try:
                tmp.rename(new_path)
            except FileNotFoundError:
                logger.warning("Race: %s disappeared mid-rename; skipping.", tmp.name)
                continue
            renamed += 1
            images.append(new_path)
        if renamed:
            logger.info("Renamed %d images → %s … %s", renamed, images[0].name, images[-1].name)

    stats.total = len(images)
    logger.info("Found %d images in %s", len(images), config.images_dir)
    _emit("inference", message=f"Found {len(images)} images to process")

    # --- Gemini client (if configured) ---
    gemini: GeminiClient | None = None
    if config.gemini_configured:
        gemini = GeminiClient(config.gemini_api_key)

    # --- Step 1: optional query expansion ---
    search_query = normalize_query(config.prompt)
    if config.expand_query_with_gemini and gemini:
        search_query = gemini.expand_query(config.prompt)
    logger.info("Search query: %r  (prompt: %r)", search_query, config.prompt)

    # --- Step 2: Roboflow discovery ---
    _emit("discovery", message="Finding model...")
    model_info: DiscoveredModel | None = None
    local_model: LocalModel | None = None
    candidates: list[DiscoveredModel] = []

    if config.roboflow_configured:
        try:
            candidates = discover_models(
                search_query, config.roboflow_api_key,
                bypass_cache=config.refresh_model,
            )
            if candidates:
                _emit("discovery", message=f"Found {len(candidates)} candidate model(s)")
            else:
                _emit("discovery", message="No models found on Roboflow")
        except Exception as exc:
            logger.error("Roboflow discovery failed: %s", exc)
            _emit("discovery", message=f"Roboflow discovery failed: {exc}")
            if not config.gemini_configured:
                raise RuntimeError(
                    "Roboflow discovery failed and Gemini is not configured — aborting"
                ) from exc

    # --- Step 3: try each candidate until one loads ---
    _emit("download", message="Downloading model...")
    for candidate in candidates:
        try:
            local_model = LocalModel(
                model_id=candidate.model_id,
                api_key=config.roboflow_api_key,
                cache_dir=config.cache_dir,
            )
            local_model.load(force_download=config.refresh_model)
            model_info = candidate
            stats.mode = f"Roboflow+local ({candidate.model_id})"
            _emit("download", message=f"Model ready: {candidate.model_id}")
            break
        except RuntimeError as exc:
            logger.warning("Model %s failed to load: %s — trying next", candidate.model_id, exc)
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
        _emit("download", message=f"Falling back to {stats.mode}")
        logger.info("Running in %s", stats.mode)

    # --- Step 4a: per-image Roboflow inference (or flag for Gemini) ---
    pending_gemini: list[tuple[int, Path]] = []  # (result_index, image_path)
    progress = _ProgressDisplay(enabled=on_progress is None)

    try:
        for idx, image_path in enumerate(images, 1):
            _emit("inference", message="Processing images", current=idx, total=stats.total)
            logger.debug("[%d/%d] %s", idx, stats.total, image_path.name)

            if local_model is not None and model_info is not None:
                result, needs_gemini = _process_roboflow_phase(
                    image_path, config, local_model, model_info, stats,
                )
                results.append(result)
                if needs_gemini:
                    pending_gemini.append((len(results) - 1, image_path))
            elif gemini is not None:
                # Gemini-only mode — defer all images to batch
                results.append(ImageResult(image_path=image_path))
                pending_gemini.append((len(results) - 1, image_path))
            else:
                logger.debug("  No model and no Gemini — skipping")
                stats.skipped_error += 1
                results.append(ImageResult(image_path=image_path, error="No model and no Gemini"))

            progress.update(
                f"  YOLO  {progress._bar(idx, stats.total)}  {idx}/{stats.total}  "
                f"labeled: {stats.roboflow_labeled}  → gemini: {len(pending_gemini)}  skip: {stats.skipped_error}"
            )

        # Emit inference summary
        _emit("inference", message=f"Inference done: {stats.roboflow_labeled} labeled, {len(pending_gemini)} uncertain, {stats.deleted} removed")

        # --- Step 4b: batch Gemini calls (concurrent) ---
        if pending_gemini and gemini is not None:
            gemini_paths = [path for _, path in pending_gemini]
            _emit("gemini_batch", message=f"Labeling {len(gemini_paths)} images with Gemini",
                  current=0, total=len(gemini_paths))

            yolo_final = (
                f"  YOLO  {progress._bar(stats.total, stats.total)}  {stats.total}/{stats.total}  "
                f"labeled: {stats.roboflow_labeled}  → gemini: {len(pending_gemini)}  skip: {stats.skipped_error}"
            )
            g_counts = {"labeled": 0, "absent": 0, "err": 0}

            def _on_gemini_result(
                done: int, total: int, path: Path, outcome: "GeminiOutcome",
            ) -> None:
                if outcome.has_detections:
                    g_counts["labeled"] += 1
                elif outcome.not_found:
                    g_counts["absent"] += 1
                else:
                    g_counts["err"] += 1
                progress.update(
                    yolo_final,
                    f"Gemini  {progress._bar(done, total)}  {done}/{total}  "
                    f"labeled: {g_counts['labeled']}  absent: {g_counts['absent']}  err: {g_counts['err']}"
                )
                _emit("gemini_batch", message="Labeling images with Gemini",
                      current=done, total=total)

            outcomes = gemini.label_images_batch(
                gemini_paths, config.prompt, on_result=_on_gemini_result,
            )

            for result_idx, image_path in pending_gemini:
                outcome = outcomes[image_path]
                results[result_idx] = _apply_gemini_outcome(image_path, outcome, stats)

            _emit("gemini_batch", message=f"Gemini done: {g_counts['labeled']} labeled, {g_counts['absent']} absent, {g_counts['err']} errors")

    finally:
        # --- Step 5: batch-end cleanup (§4.2) ---
        if local_model is not None:
            if config.keep_model_cache:
                logger.info("Keeping model cache (--keep-model-cache)")
            else:
                logger.info("Cleaning up model artifacts ...")
                local_model.cleanup()

    stats.log_summary()
    _emit("done", message="Pipeline complete", labeled=stats.labeled, total=stats.total)
    return stats, results


# -----------------------------------------------------------------------
# Per-image routes
# -----------------------------------------------------------------------

def _process_roboflow_phase(
    image_path: Path,
    config: PipelineConfig,
    model: LocalModel,
    model_info: DiscoveredModel,
    stats: BatchStats,
) -> tuple[ImageResult, bool]:
    """Roboflow local inference → threshold check.

    Returns (result, needs_gemini).  When *needs_gemini* is True the
    result is a placeholder that will be replaced by the Gemini batch.
    """
    try:
        detections, img_w, img_h = model.predict(image_path)
    except RuntimeError as exc:
        logger.debug("  Inference error: %s — skipping", exc)
        stats.skipped_error += 1
        return ImageResult(image_path=image_path, error=str(exc)), False

    filtered = [d for d in detections if d.confidence >= config.conf_threshold]
    logger.debug(
        "  Roboflow: %d raw, %d after threshold (>=%.2f)",
        len(detections), len(filtered), config.conf_threshold,
    )

    if filtered:
        boxes = [
            normalize_box(
                d.x_center_px, d.y_center_px, d.width_px, d.height_px,
                img_w, img_h, d.class_id,
            )
            for d in filtered
        ]
        stats.labeled += 1
        stats.roboflow_labeled += 1
        return ImageResult(image_path=image_path, boxes=boxes, source="roboflow",
                           img_width=img_w, img_height=img_h,
                           raw_detections=detections), False

    # Check uncertain band — only defer to Gemini if the model saw *something*
    gemini_floor = max(0.0, config.conf_threshold - 0.3)
    uncertain = [d for d in detections if d.confidence >= gemini_floor]
    if uncertain:
        logger.debug(
            "  -> %d uncertain detections (>=%.2f) — deferring to Gemini",
            len(uncertain), gemini_floor,
        )
        return ImageResult(image_path=image_path, img_width=img_w, img_height=img_h,
                           raw_detections=detections), True

    logger.debug("  -> No detections above %.2f — deleting", gemini_floor)
    image_path.unlink(missing_ok=True)
    stats.deleted += 1
    return ImageResult(image_path=image_path, not_found=True, img_width=img_w, img_height=img_h,
                       raw_detections=detections), False


# -----------------------------------------------------------------------
# Gemini outcome → ImageResult (applied after batch completes)
# -----------------------------------------------------------------------

def _apply_gemini_outcome(
    image_path: Path,
    outcome: "GeminiOutcome",
    stats: BatchStats,
) -> ImageResult:
    """Convert a GeminiOutcome into an ImageResult and update stats."""
    stats.gemini_calls += 1

    if outcome.error:
        logger.debug("  Gemini error (%s): %s", image_path.name, outcome.error)
        stats.skipped_error += 1
        return ImageResult(image_path=image_path, error=outcome.error)

    if outcome.not_found:
        image_path.unlink(missing_ok=True)
        stats.deleted += 1
        return ImageResult(image_path=image_path, not_found=True)

    if outcome.has_detections:
        stats.labeled += 1
        stats.gemini_labeled += 1
        return ImageResult(image_path=image_path, boxes=outcome.boxes, source="gemini")

    logger.debug("  Gemini empty response — skipping (%s)", image_path.name)
    stats.skipped_error += 1
    return ImageResult(image_path=image_path)


# -----------------------------------------------------------------------
# Restart re-filtering (avoids full pipeline re-run)
# -----------------------------------------------------------------------

def refilter_results(
    previous_results: list[ImageResult],
    new_threshold: float,
    gemini_api_key: str = "",
    prompt: str = "",
    on_progress: Callable[[str, dict], None] | None = None,
) -> tuple[BatchStats, list[ImageResult]]:
    """Re-filter cached raw detections at a new threshold.

    Avoids re-running model discovery, download, and YOLO inference.
    Only calls Gemini for images that newly fall into the uncertain band.
    """
    def _emit(step: str, **data: object) -> None:
        if on_progress:
            on_progress(step, data)

    stats = BatchStats()
    stats.mode = "refilter"
    results: list[ImageResult] = []
    pending_gemini: list[tuple[int, Path]] = []
    gemini_floor = max(0.0, new_threshold - 0.3)

    _emit("inference", message="Re-filtering at new threshold", current=0,
          total=len(previous_results))

    for idx, prev in enumerate(previous_results):
        stats.total += 1
        _emit("inference", message="Re-filtering", current=idx + 1,
              total=len(previous_results))

        # Gemini-labeled or already not_found — keep as-is
        if prev.source == "gemini" or prev.not_found or prev.error:
            results.append(prev)
            if prev.source == "gemini" and prev.boxes:
                stats.labeled += 1
                stats.gemini_labeled += 1
            elif prev.not_found:
                stats.deleted += 1
            elif prev.error:
                stats.skipped_error += 1
            continue

        # No raw detections stored (e.g., Gemini-only mode) — keep as-is
        if not prev.raw_detections:
            results.append(prev)
            if prev.boxes:
                stats.labeled += 1
            continue

        # Re-filter raw detections at new threshold
        filtered = [d for d in prev.raw_detections if d.confidence >= new_threshold]

        if filtered:
            boxes = [
                normalize_box(
                    d.x_center_px, d.y_center_px, d.width_px, d.height_px,
                    prev.img_width, prev.img_height, d.class_id,
                )
                for d in filtered
            ]
            stats.labeled += 1
            stats.roboflow_labeled += 1
            results.append(ImageResult(
                image_path=prev.image_path, boxes=boxes, source="roboflow",
                img_width=prev.img_width, img_height=prev.img_height,
                raw_detections=prev.raw_detections,
            ))
            continue

        # Check uncertain band
        uncertain = [d for d in prev.raw_detections if d.confidence >= gemini_floor]
        if uncertain:
            results.append(ImageResult(
                image_path=prev.image_path,
                img_width=prev.img_width, img_height=prev.img_height,
                raw_detections=prev.raw_detections,
            ))
            pending_gemini.append((len(results) - 1, prev.image_path))
            continue

        # Below floor — delete
        prev.image_path.unlink(missing_ok=True)
        stats.deleted += 1
        results.append(ImageResult(
            image_path=prev.image_path, not_found=True,
            img_width=prev.img_width, img_height=prev.img_height,
            raw_detections=prev.raw_detections,
        ))

    # Batch Gemini for newly-uncertain images
    if pending_gemini and gemini_api_key:
        gemini = GeminiClient(gemini_api_key)
        gemini_paths = [path for _, path in pending_gemini]
        _emit("gemini_batch", message=f"Labeling {len(gemini_paths)} images with Gemini",
              current=0, total=len(gemini_paths))

        def _on_result(done: int, total: int, path: Path, outcome: "GeminiOutcome") -> None:
            _emit("gemini_batch", message="Labeling images with Gemini",
                  current=done, total=total)

        outcomes = gemini.label_images_batch(gemini_paths, prompt, on_result=_on_result)

        for result_idx, image_path in pending_gemini:
            outcome = outcomes[image_path]
            results[result_idx] = _apply_gemini_outcome(image_path, outcome, stats)

    stats.log_summary()
    _emit("done", message="Pipeline complete", labeled=stats.labeled, total=stats.total)
    return stats, results
