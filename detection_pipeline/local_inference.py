"""Local model inference using the Roboflow *inference* SDK.

Downloads model weights on first use, runs object detection locally
(CPU by default), and exposes simple cache lifecycle controls.
"""

from __future__ import annotations

import logging
import os
import shutil
import warnings
from dataclasses import dataclass
from pathlib import Path

# Suppress noisy warnings from the inference SDK and its dependencies
os.environ.setdefault("QWEN_2_5_ENABLED", "False")
os.environ.setdefault("QWEN_3_ENABLED", "False")
os.environ.setdefault("CORE_MODEL_SAM_ENABLED", "False")
os.environ.setdefault("CORE_MODEL_SAM3_ENABLED", "False")
os.environ.setdefault("CORE_MODEL_GAZE_ENABLED", "False")
os.environ.setdefault("CORE_MODEL_YOLO_WORLD_ENABLED", "False")
warnings.filterwarnings("ignore", message="Importing from timm.models.layers is deprecated")
warnings.filterwarnings("ignore", message="Specified provider .* is not in available provider names")

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """A single detection from local inference (pixel coordinates)."""

    x_center_px: float
    y_center_px: float
    width_px: float
    height_px: float
    confidence: float
    class_id: int
    class_name: str = ""


class LocalModel:
    """Wrapper around the *inference* SDK for local object detection."""

    def __init__(self, model_id: str, api_key: str, cache_dir: Path) -> None:
        self.model_id = model_id
        self.api_key = api_key
        self.cache_dir = cache_dir
        self._model = None

        # Point inference SDK cache at our managed directory
        os.environ["MODEL_CACHE_DIR"] = str(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self, force_download: bool = False) -> None:
        """Download (if needed) and load the model locally.

        Raises ``RuntimeError`` when the model cannot be loaded.
        """
        if force_download:
            self._clear_cache()

        try:
            from inference import get_model  # type: ignore[import-untyped]

            logger.info("Loading model %s (cache=%s) ...", self.model_id, self.cache_dir)
            self._model = get_model(model_id=self.model_id, api_key=self.api_key)
            logger.info("Model %s loaded", self.model_id)
        except Exception as exc:
            raise RuntimeError(f"Failed to load model {self.model_id}: {exc}") from exc

    def cleanup(self) -> None:
        """Delete cached model artifacts (batch-end cleanup)."""
        self._clear_cache()
        self._model = None
        logger.info("Model artifacts cleaned up")

    @property
    def is_cached(self) -> bool:
        return self.cache_dir.exists() and any(self.cache_dir.iterdir())

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, image_path: Path) -> tuple[list[Detection], int, int]:
        """Run inference on *image_path*.

        Returns ``(detections, image_width, image_height)``.
        Raises ``RuntimeError`` on failure.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded — call load() first")

        try:
            import cv2  # type: ignore[import-untyped]

            image = cv2.imread(str(image_path))
            if image is None:
                raise RuntimeError(f"Cannot read image: {image_path}")

            img_h, img_w = image.shape[:2]
            results = self._model.infer(image)
            predictions = self._extract_predictions(results)
            detections = [d for p in predictions if (d := self._parse_prediction(p))]
            return detections, img_w, img_h
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Inference failed on {image_path.name}: {exc}") from exc

    # ------------------------------------------------------------------
    # Result parsing (handles multiple inference SDK response shapes)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_predictions(results: object) -> list:
        if isinstance(results, list) and results:
            first = results[0]
            if hasattr(first, "predictions"):
                return first.predictions  # type: ignore[union-attr]
            if hasattr(first, "x") or (isinstance(first, dict) and "x" in first):
                return results
            if isinstance(first, list):
                return first
        if isinstance(results, dict):
            return results.get("predictions", [])
        if hasattr(results, "predictions"):
            return results.predictions  # type: ignore[union-attr]
        logger.warning("Unexpected inference result type: %s", type(results))
        return []

    @staticmethod
    def _parse_prediction(pred: object) -> Detection | None:
        try:
            if isinstance(pred, dict):
                return Detection(
                    x_center_px=float(pred.get("x", 0)),
                    y_center_px=float(pred.get("y", 0)),
                    width_px=float(pred.get("width", 0)),
                    height_px=float(pred.get("height", 0)),
                    confidence=float(pred.get("confidence", 0)),
                    class_id=int(pred.get("class_id", 0)),
                    class_name=str(pred.get("class", pred.get("class_name", ""))),
                )
            return Detection(
                x_center_px=float(getattr(pred, "x", 0)),
                y_center_px=float(getattr(pred, "y", 0)),
                width_px=float(getattr(pred, "width", 0)),
                height_px=float(getattr(pred, "height", 0)),
                confidence=float(getattr(pred, "confidence", 0)),
                class_id=int(getattr(pred, "class_id", 0)),
                class_name=str(getattr(pred, "class_name", getattr(pred, "class_", ""))),
            )
        except (TypeError, ValueError, AttributeError) as exc:
            logger.debug("Unparseable prediction: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _clear_cache(self) -> None:
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Cleared model cache at %s", self.cache_dir)
