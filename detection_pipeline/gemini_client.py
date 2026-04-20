"""Gemini client — calls the Gemini API directly via google.genai SDK.

Two logical outcomes per image:
  1. Detections  — one or more valid YOLO lines.
  2. OBJECT NOT FOUND — explicit sentinel → caller handles deletion.

Anything else (malformed, missing, transport error) is a non-destructive skip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

import re

from .yolo import YoloBox, parse_yolo_lines

logger = logging.getLogger(__name__)

OBJECT_NOT_FOUND_SENTINEL = "OBJECT NOT FOUND"

LABEL_PROMPT_TEMPLATE = """Detect all instances of {item} in this image.

If the object is NOT present, respond with exactly: OBJECT NOT FOUND

Otherwise, for each detected instance, return a bounding box on its own line in this format:
[ymin, xmin, ymax, xmax]

Coordinates must be integers between 0 and 1000 relative to image dimensions.
Do NOT include any labels, class names, or explanation — only bounding box lines.
"""

CLASSIFY_PROMPT_TEMPLATE = """Classify this image: does it contain {item}?

If the object is NOT present, respond with exactly: OBJECT NOT FOUND

If it IS present, respond with exactly: YES
Do NOT include any explanation — only YES or OBJECT NOT FOUND.
"""

EXPAND_QUERY_PROMPT = (
    "Rewrite the following into a short Roboflow Universe search query (2-4 words). "
    "Return ONLY the query, nothing else.\n\n"
)


@dataclass
class GeminiOutcome:
    """Result of a single Gemini labeling/classification call."""

    boxes: list[YoloBox] = field(default_factory=list)
    not_found: bool = False
    error: str | None = None
    classified_as: int | None = None  # class_id for classification tasks

    @property
    def has_detections(self) -> bool:
        return bool(self.boxes)

    @property
    def has_classification(self) -> bool:
        return self.classified_as is not None

    def __repr__(self) -> str:
        if self.error:
            return f"GeminiOutcome(error={self.error!r})"
        if self.not_found:
            return "GeminiOutcome(OBJECT_NOT_FOUND)"
        if self.classified_as is not None:
            return f"GeminiOutcome(class={self.classified_as})"
        return f"GeminiOutcome(boxes={len(self.boxes)})"


class GeminiClient:
    """Calls the Gemini API directly using the google.genai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        import google.genai as genai
        from google.genai import types

        self.client = genai.Client(api_key=api_key)
        self.model = model
        self._no_thinking = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

    # ------------------------------------------------------------------
    # Query expansion (batch-level, one call)
    # ------------------------------------------------------------------

    def expand_query(self, prompt: str) -> str:
        """Ask Gemini to rewrite *prompt* into a short Roboflow search query."""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[EXPAND_QUERY_PROMPT + prompt],
                config=self._no_thinking,
            )
            text = response.candidates[0].content.parts[0].text.strip()
            if text:
                logger.info("Gemini expanded query: %r -> %r", prompt, text)
                return text
        except Exception as exc:
            logger.warning("Gemini query expansion failed (%s) — using original prompt", exc)
        return prompt

    # ------------------------------------------------------------------
    # Per-image labeling
    # ------------------------------------------------------------------

    _MAX_GEMINI_PX = 1024

    def label_image(self, image_path: Path, prompt: str) -> GeminiOutcome:
        """Send *image_path* to Gemini and return the parsed outcome."""
        try:
            image = Image.open(image_path)
        except IOError as exc:
            return GeminiOutcome(error=f"Cannot read image: {exc}")

        # Downscale large images to reduce upload time; Gemini's 0-1000
        # coordinate system is resolution-independent so quality is unaffected.
        w, h = image.size
        if max(w, h) > self._MAX_GEMINI_PX:
            scale = self._MAX_GEMINI_PX / max(w, h)
            image = image.resize(
                (int(w * scale), int(h * scale)), Image.LANCZOS,
            )

        label_prompt = LABEL_PROMPT_TEMPLATE.format(item=prompt)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[label_prompt, image],
                config=self._no_thinking,
            )
            text = response.candidates[0].content.parts[0].text.strip()
        except Exception as exc:
            return GeminiOutcome(error=f"Gemini API error: {exc}")

        return self._parse_text(text)

    # ------------------------------------------------------------------
    # Per-image classification
    # ------------------------------------------------------------------

    def classify_image(self, image_path: Path, prompt: str) -> GeminiOutcome:
        """Send *image_path* to Gemini for binary classification."""
        try:
            image = Image.open(image_path)
        except IOError as exc:
            return GeminiOutcome(error=f"Cannot read image: {exc}")

        w, h = image.size
        if max(w, h) > self._MAX_GEMINI_PX:
            scale = self._MAX_GEMINI_PX / max(w, h)
            image = image.resize(
                (int(w * scale), int(h * scale)), Image.LANCZOS,
            )

        classify_prompt = CLASSIFY_PROMPT_TEMPLATE.format(item=prompt)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[classify_prompt, image],
                config=self._no_thinking,
            )
            text = response.candidates[0].content.parts[0].text.strip()
        except Exception as exc:
            return GeminiOutcome(error=f"Gemini API error: {exc}")

        return self._parse_classification_text(text)

    def _parse_classification_text(self, text: str) -> GeminiOutcome:
        if not text:
            return GeminiOutcome(error="Empty response from Gemini")

        if OBJECT_NOT_FOUND_SENTINEL in text.upper():
            return GeminiOutcome(not_found=True)

        if "YES" in text.upper():
            return GeminiOutcome(classified_as=0)

        return GeminiOutcome(error=f"Unparseable classification response: {text[:120]!r}")

    # ------------------------------------------------------------------
    # Batch classification (concurrent)
    # ------------------------------------------------------------------

    def classify_images_batch(
        self,
        image_paths: list[Path],
        prompt: str,
        max_workers: int = 10,
        on_result: "Callable[[int, int, Path, GeminiOutcome], None] | None" = None,
    ) -> dict[Path, GeminiOutcome]:
        """Send multiple images to Gemini for classification concurrently."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        outcomes: dict[Path, GeminiOutcome] = {}
        total = len(image_paths)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(self.classify_image, path, prompt): path
                for path in image_paths
            }
            for done, future in enumerate(as_completed(future_to_path), 1):
                path = future_to_path[future]
                try:
                    outcome = future.result()
                except Exception as exc:
                    outcome = GeminiOutcome(error=str(exc))
                outcomes[path] = outcome
                if on_result:
                    on_result(done, total, path, outcome)

        return outcomes

    # ------------------------------------------------------------------
    # Batch labeling (concurrent)
    # ------------------------------------------------------------------

    def label_images_batch(
        self,
        image_paths: list[Path],
        prompt: str,
        max_workers: int = 10,
        on_result: "Callable[[int, int, Path, GeminiOutcome], None] | None" = None,
    ) -> dict[Path, GeminiOutcome]:
        """Send multiple images to Gemini concurrently using a thread pool.

        *max_workers* defaults to 10 to stay within typical API rate limits.
        *on_result*, when provided, is called after each image with
        ``(done_count, total, path, outcome)``.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        outcomes: dict[Path, GeminiOutcome] = {}
        total = len(image_paths)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(self.label_image, path, prompt): path
                for path in image_paths
            }
            for done, future in enumerate(as_completed(future_to_path), 1):
                path = future_to_path[future]
                try:
                    outcome = future.result()
                except Exception as exc:
                    outcome = GeminiOutcome(error=str(exc))
                outcomes[path] = outcome
                if on_result:
                    on_result(done, total, path, outcome)

        return outcomes

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_text(self, text: str) -> GeminiOutcome:
        if not text:
            return GeminiOutcome(error="Empty response from Gemini")

        if OBJECT_NOT_FOUND_SENTINEL in text.upper():
            return GeminiOutcome(not_found=True)

        # Try Gemini's native [ymin, xmin, ymax, xmax] format (0-1000 scale)
        boxes = _parse_gemini_boxes(text)

        # Fallback: try YOLO format for backwards compatibility
        if not boxes:
            boxes = parse_yolo_lines(text)

        if boxes:
            return GeminiOutcome(boxes=boxes)

        return GeminiOutcome(error=f"Unparseable response: {text[:120]!r}")


_BBOX_RE = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]")


def _parse_gemini_boxes(text: str) -> list[YoloBox]:
    """Parse Gemini's native [ymin, xmin, ymax, xmax] (0-1000) into YOLO boxes."""
    boxes: list[YoloBox] = []
    for m in _BBOX_RE.finditer(text):
        ymin, xmin, ymax, xmax = (int(v) for v in m.groups())
        # Convert from 0-1000 corner format to 0-1 center format (YOLO)
        x_center = (xmin + xmax) / 2.0 / 1000.0
        y_center = (ymin + ymax) / 2.0 / 1000.0
        width = (xmax - xmin) / 1000.0
        height = (ymax - ymin) / 1000.0
        box = YoloBox(class_id=0, x_center=x_center, y_center=y_center, width=width, height=height)
        if box.is_valid():
            boxes.append(box)
    return boxes
