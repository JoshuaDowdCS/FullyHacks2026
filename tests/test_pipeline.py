"""Integration tests — pipeline filesystem behaviour with temp directories.

Covers:
  - Label writing on detections
  - Image+label deletion only on OBJECT NOT FOUND sentinel
  - Image preserved on errors (§7.1)
  - Confidence filtering routing (mixed above/below threshold)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from detection_pipeline.gemini_client import GeminiClient, GeminiOutcome
from detection_pipeline.local_inference import Detection
from detection_pipeline.pipeline import (
    BatchStats,
    _delete_image_and_label,
    _handle_gemini,
    _process_with_roboflow,
)
from detection_pipeline.discovery import DiscoveredModel
from detection_pipeline.config import PipelineConfig
from detection_pipeline.yolo import YoloBox


# -------------------------------------------------------------------
# _delete_image_and_label
# -------------------------------------------------------------------

class TestDeleteImageAndLabel:
    def test_deletes_both_files(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl = Path(d) / "test.txt"
            img.write_bytes(b"fake")
            lbl.write_text("0 0.5 0.5 0.3 0.4")

            _delete_image_and_label(img, lbl)

            assert not img.exists()
            assert not lbl.exists()

    def test_deletes_image_when_no_label_exists(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl = Path(d) / "test.txt"
            img.write_bytes(b"fake")

            _delete_image_and_label(img, lbl)

            assert not img.exists()
            # no error even though label didn't exist


# -------------------------------------------------------------------
# _handle_gemini
# -------------------------------------------------------------------

class TestHandleGemini:
    def test_detections_write_labels(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl = Path(d) / "labels" / "test.txt"
            img.write_bytes(b"fake")

            gemini = MagicMock(spec=GeminiClient)
            gemini.label_image.return_value = GeminiOutcome(
                boxes=[YoloBox(0, 0.5, 0.5, 0.3, 0.4)]
            )

            stats = BatchStats()
            _handle_gemini(img, lbl, "detect cats", gemini, stats)

            assert lbl.exists()
            assert stats.labeled == 1
            assert stats.gemini_labeled == 1
            assert img.exists()  # NOT deleted

    def test_not_found_deletes_image(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl = Path(d) / "test.txt"
            img.write_bytes(b"fake")

            gemini = MagicMock(spec=GeminiClient)
            gemini.label_image.return_value = GeminiOutcome(not_found=True)

            stats = BatchStats()
            _handle_gemini(img, lbl, "detect cats", gemini, stats)

            assert not img.exists()
            assert stats.deleted == 1

    def test_error_preserves_image(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl = Path(d) / "test.txt"
            img.write_bytes(b"fake")

            gemini = MagicMock(spec=GeminiClient)
            gemini.label_image.return_value = GeminiOutcome(error="timeout")

            stats = BatchStats()
            _handle_gemini(img, lbl, "detect cats", gemini, stats)

            assert img.exists()      # preserved
            assert not lbl.exists()  # no label written
            assert stats.skipped_error == 1


# -------------------------------------------------------------------
# Confidence filtering → Gemini routing
# -------------------------------------------------------------------

class TestConfidenceFilteringRouting:
    """Spec §4.3: mixed boxes above/below threshold."""

    def _make_model_mock(self, detections, img_w=640, img_h=480):
        model = MagicMock()
        model.predict.return_value = (detections, img_w, img_h)
        return model

    def _make_model_info(self):
        return DiscoveredModel(
            project_url="test/proj",
            model_id="proj/1",
            name="test",
            version=1,
            model_type="object-detection",
        )

    def test_some_above_threshold_writes_only_those(self):
        """Two boxes: one above, one below threshold → write only the above one."""
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl_dir = Path(d) / "labels"
            lbl_dir.mkdir()
            img.write_bytes(b"fake")

            detections = [
                Detection(320, 240, 100, 80, 0.9, 0, "cat"),   # above 0.7
                Detection(160, 120, 50, 40, 0.3, 1, "dog"),    # below 0.7
            ]
            model = self._make_model_mock(detections)
            config = PipelineConfig(
                images_dir=Path(d), labels_dir=lbl_dir,
                prompt="cats", conf_threshold=0.7,
            )

            stats = BatchStats()
            _process_with_roboflow(img, config, model, self._make_model_info(), None, stats)

            lbl = lbl_dir / "test.txt"
            assert lbl.exists()
            lines = lbl.read_text().strip().split("\n")
            assert len(lines) == 1  # only the above-threshold box
            assert stats.labeled == 1
            assert stats.roboflow_labeled == 1

    def test_all_below_threshold_calls_gemini(self):
        """All boxes below threshold → should invoke Gemini."""
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl_dir = Path(d) / "labels"
            lbl_dir.mkdir()
            img.write_bytes(b"fake")

            detections = [
                Detection(320, 240, 100, 80, 0.3, 0, "cat"),
                Detection(160, 120, 50, 40, 0.1, 1, "dog"),
            ]
            model = self._make_model_mock(detections)

            gemini = MagicMock(spec=GeminiClient)
            gemini.label_image.return_value = GeminiOutcome(
                boxes=[YoloBox(0, 0.5, 0.5, 0.3, 0.4)]
            )

            config = PipelineConfig(
                images_dir=Path(d), labels_dir=lbl_dir,
                prompt="cats", conf_threshold=0.7,
            )

            stats = BatchStats()
            _process_with_roboflow(img, config, model, self._make_model_info(), gemini, stats)

            gemini.label_image.assert_called_once()
            assert stats.gemini_calls == 1

    def test_no_detections_no_gemini_skips(self):
        """Zero detections and no Gemini → skipped."""
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            lbl_dir = Path(d) / "labels"
            lbl_dir.mkdir()
            img.write_bytes(b"fake")

            model = self._make_model_mock([])
            config = PipelineConfig(
                images_dir=Path(d), labels_dir=lbl_dir,
                prompt="cats", conf_threshold=0.7,
            )

            stats = BatchStats()
            _process_with_roboflow(img, config, model, self._make_model_info(), None, stats)

            assert stats.skipped_error == 1
            assert not (lbl_dir / "test.txt").exists()
