"""Gemini HTTP client — implements the agreed labeling contract.

Two logical outcomes per image:
  1. Detections  — one or more valid YOLO lines (written verbatim, no confidence gate).
  2. OBJECT NOT FOUND — explicit sentinel → image + label deletion.

Anything else (malformed, missing, transport error) is a non-destructive skip.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .yolo import YoloBox, parse_yolo_lines

logger = logging.getLogger(__name__)

OBJECT_NOT_FOUND_SENTINEL = "OBJECT NOT FOUND"


@dataclass
class GeminiOutcome:
    """Result of a single Gemini labeling call."""

    boxes: list[YoloBox] = field(default_factory=list)
    not_found: bool = False
    error: str | None = None

    @property
    def has_detections(self) -> bool:
        return bool(self.boxes)

    def __repr__(self) -> str:
        if self.error:
            return f"GeminiOutcome(error={self.error!r})"
        if self.not_found:
            return "GeminiOutcome(OBJECT_NOT_FOUND)"
        return f"GeminiOutcome(boxes={len(self.boxes)})"


class GeminiClient:
    """Thin HTTP wrapper for the Gemini labeling/expansion endpoints."""

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    # ------------------------------------------------------------------
    # Query expansion (batch-level, one call)
    # ------------------------------------------------------------------

    def expand_query(self, prompt: str) -> str:
        """Ask Gemini to rewrite *prompt* into a short Roboflow search query."""
        url = f"{self.base_url}/expand-query"
        payload = {
            "prompt": prompt,
            "task": "rewrite as a short Roboflow Universe search query (2-4 words)",
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            query = (
                data.get("query")
                or data.get("result")
                or data.get("text")
                or ""
            )
            if query:
                logger.info("Gemini expanded query: %r -> %r", prompt, query)
                return query.strip()
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.warning("Gemini query expansion failed (%s) — using original prompt", exc)
        return prompt

    # ------------------------------------------------------------------
    # Per-image labeling
    # ------------------------------------------------------------------

    def label_image(self, image_path: Path, prompt: str) -> GeminiOutcome:
        """Send *image_path* to Gemini and return the parsed outcome."""
        url = f"{self.base_url}/label"

        try:
            image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except IOError as exc:
            return GeminiOutcome(error=f"Cannot read image: {exc}")

        payload = {
            "image": image_b64,
            "prompt": prompt,
            "filename": image_path.name,
        }

        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except requests.Timeout:
            return GeminiOutcome(error="Gemini timeout")
        except requests.RequestException as exc:
            return GeminiOutcome(error=f"Gemini transport error: {exc}")
        except ValueError:
            return GeminiOutcome(error="Gemini returned non-JSON response")

        return self._parse_response(data)

    # ------------------------------------------------------------------
    # Response parsing (contract §4.5)
    # ------------------------------------------------------------------

    def _parse_response(self, data: dict) -> GeminiOutcome:
        # Try several plausible response-body keys
        result = (
            data.get("result")
            or data.get("detections")
            or data.get("labels")
            or data.get("text")
            or ""
        )

        if isinstance(result, str):
            if result.strip().upper() == OBJECT_NOT_FOUND_SENTINEL:
                return GeminiOutcome(not_found=True)
            boxes = parse_yolo_lines(result)
            if boxes:
                return GeminiOutcome(boxes=boxes)
            if result.strip():
                return GeminiOutcome(error=f"Unparseable response: {result[:120]!r}")
            return GeminiOutcome(error="Empty result string")

        if isinstance(result, list):
            if any(
                str(item).strip().upper() == OBJECT_NOT_FOUND_SENTINEL
                for item in result
            ):
                return GeminiOutcome(not_found=True)
            text = "\n".join(str(line) for line in result)
            boxes = parse_yolo_lines(text)
            if boxes:
                return GeminiOutcome(boxes=boxes)
            return GeminiOutcome(error="List result contained no valid YOLO lines")

        return GeminiOutcome(error=f"Unexpected result type: {type(result).__name__}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h
