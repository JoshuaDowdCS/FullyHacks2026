"""Tests for the Review UI API."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import api.main as api_mod
from api.main import app
from detection_pipeline.pipeline import ImageResult
from detection_pipeline.yolo import YoloBox


def _setup_dirs(images_dir: Path, labels_dir: Path):
    """Point the api module at temp directories."""
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    api_mod._images_dir = images_dir
    api_mod._labels_dir = labels_dir
    api_mod._conf_threshold = 0.7
    api_mod._pipeline_results = {}
    api_mod._config = MagicMock()
    api_mod._config.roboflow_api_key = "test-key"
    api_mod._config.gemini_configured = False


def _create_image(images_dir: Path, name: str = "test.jpg") -> Path:
    """Create a minimal valid JPEG file."""
    from PIL import Image as PILImage

    p = images_dir / name
    img = PILImage.new("RGB", (640, 480), color=(0, 128, 0))
    img.save(p, format="JPEG")
    return p


def _create_label(labels_dir: Path, stem: str, content: str = "0 0.5 0.5 0.3 0.4\n"):
    """Write a YOLO label file."""
    lp = labels_dir / f"{stem}.txt"
    lp.write_text(content)
    return lp


client = TestClient(app)


class TestListImages:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            _setup_dirs(Path(td) / "images", Path(td) / "labels")
            resp = client.get("/api/images")
            assert resp.status_code == 200
            data = resp.json()
            assert data["images"] == []
            assert data["total"] == 0

    def test_image_with_labels(self):
        with tempfile.TemporaryDirectory() as td:
            img_dir = Path(td) / "images"
            lbl_dir = Path(td) / "labels"
            _setup_dirs(img_dir, lbl_dir)
            img_path = _create_image(img_dir, "game001.jpg")
            api_mod._pipeline_results["game001.jpg"] = ImageResult(
                image_path=img_path,
                boxes=[YoloBox(class_id=0, x_center=0.5, y_center=0.5, width=0.3, height=0.4)],
                source="roboflow",
            )

            resp = client.get("/api/images")
            data = resp.json()
            assert data["total"] == 1
            img = data["images"][0]
            assert img["filename"] == "game001.jpg"
            assert img["width"] == 640
            assert img["height"] == 480
            assert len(img["labels"]) == 1
            assert img["labels"][0]["class_name"] == "basketball"

    def test_image_without_labels(self):
        with tempfile.TemporaryDirectory() as td:
            img_dir = Path(td) / "images"
            lbl_dir = Path(td) / "labels"
            _setup_dirs(img_dir, lbl_dir)
            img_path = _create_image(img_dir, "nolabel.jpg")
            api_mod._pipeline_results["nolabel.jpg"] = ImageResult(
                image_path=img_path, boxes=[], source="",
            )

            resp = client.get("/api/images")
            data = resp.json()
            # No boxes = not shown in labeled list
            assert data["total"] == 0


class TestServeImage:
    def test_valid_image(self):
        with tempfile.TemporaryDirectory() as td:
            img_dir = Path(td) / "images"
            lbl_dir = Path(td) / "labels"
            _setup_dirs(img_dir, lbl_dir)
            _create_image(img_dir, "photo.jpg")

            resp = client.get("/api/images/photo.jpg")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/jpeg"

    def test_missing_image(self):
        with tempfile.TemporaryDirectory() as td:
            _setup_dirs(Path(td) / "images", Path(td) / "labels")
            resp = client.get("/api/images/nope.jpg")
            assert resp.status_code == 404

    def test_path_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            img_dir = Path(td) / "images"
            _setup_dirs(img_dir, Path(td) / "labels")
            resp = client.get("/api/images/..%2F..%2Fetc%2Fpasswd")
            assert resp.status_code in (403, 404)


class TestDiscard:
    def test_deletes_image_and_label(self):
        with tempfile.TemporaryDirectory() as td:
            img_dir = Path(td) / "images"
            lbl_dir = Path(td) / "labels"
            _setup_dirs(img_dir, lbl_dir)
            img_path = _create_image(img_dir, "remove.jpg")
            lbl_path = _create_label(lbl_dir, "remove")

            resp = client.post("/api/images/remove.jpg/discard")
            assert resp.status_code == 204
            assert not img_path.exists()
            assert not lbl_path.exists()

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            _setup_dirs(Path(td) / "images", Path(td) / "labels")
            resp = client.post("/api/images/gone.jpg/discard")
            assert resp.status_code == 204


class TestStats:
    def test_returns_counts(self):
        with tempfile.TemporaryDirectory() as td:
            img_dir = Path(td) / "images"
            lbl_dir = Path(td) / "labels"
            _setup_dirs(img_dir, lbl_dir)
            img_a = _create_image(img_dir, "a.jpg")
            img_b = _create_image(img_dir, "b.jpg")
            api_mod._pipeline_results = {
                "a.jpg": ImageResult(
                    image_path=img_a,
                    boxes=[YoloBox(class_id=0, x_center=0.5, y_center=0.5, width=0.3, height=0.4)],
                    source="roboflow",
                ),
                "b.jpg": ImageResult(image_path=img_b, boxes=[], source=""),
            }

            resp = client.get("/api/stats")
            data = resp.json()
            assert data["total"] == 2
            assert data["labeled"] == 1
            assert data["conf_threshold"] == 0.7


class TestRestart:
    @patch("api.main.run_pipeline")
    def test_increments_threshold(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            img_dir = Path(td) / "images"
            lbl_dir = Path(td) / "labels"
            _setup_dirs(img_dir, lbl_dir)
            img_path = _create_image(img_dir, "x.jpg")
            result = ImageResult(
                image_path=img_path,
                boxes=[YoloBox(class_id=0, x_center=0.5, y_center=0.5, width=0.3, height=0.4)],
                source="roboflow",
            )
            mock_run.return_value = (MagicMock(), [result])

            resp = client.post("/api/restart")
            assert resp.status_code == 200
            data = resp.json()
            assert data["new_threshold"] == 0.75
            assert mock_run.called
