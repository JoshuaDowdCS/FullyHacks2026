"""Integration tests — pipeline filesystem behaviour with temp directories.

Covers:
  - Image+label deletion only on OBJECT NOT FOUND sentinel
  - Image preserved on errors (§7.1)
  - Confidence filtering routing (mixed above/below threshold)
  - Restart re-filtering at new threshold
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from detection_pipeline.gemini_client import GeminiClient, GeminiOutcome
from detection_pipeline.local_inference import Detection
from detection_pipeline.pipeline import (
    BatchStats,
    ImageResult,
    _apply_gemini_outcome,
    _process_roboflow_phase,
    refilter_results,
)
from detection_pipeline.discovery import DiscoveredModel
from detection_pipeline.config import PipelineConfig
from detection_pipeline.yolo import YoloBox


# -------------------------------------------------------------------
# _apply_gemini_outcome
# -------------------------------------------------------------------

class TestApplyGeminiOutcome:
    def test_detections_returns_labeled_result(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            img.write_bytes(b"fake")

            outcome = GeminiOutcome(
                boxes=[YoloBox(0, 0.5, 0.5, 0.3, 0.4)]
            )

            stats = BatchStats()
            result = _apply_gemini_outcome(img, outcome, stats)

            assert result.boxes
            assert stats.labeled == 1
            assert stats.gemini_labeled == 1
            assert img.exists()  # NOT deleted

    def test_not_found_deletes_image(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            img.write_bytes(b"fake")

            outcome = GeminiOutcome(not_found=True)

            stats = BatchStats()
            _apply_gemini_outcome(img, outcome, stats)

            assert not img.exists()
            assert stats.deleted == 1

    def test_error_preserves_image(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            img.write_bytes(b"fake")

            outcome = GeminiOutcome(error="timeout")

            stats = BatchStats()
            result = _apply_gemini_outcome(img, outcome, stats)

            assert img.exists()      # preserved
            assert not result.boxes   # no labels
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

    def test_some_above_threshold_keeps_only_those(self):
        """Two boxes: one above, one below threshold → keep only the above one."""
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            img.write_bytes(b"fake")

            detections = [
                Detection(320, 240, 100, 80, 0.9, 0, "cat"),   # above 0.7
                Detection(160, 120, 50, 40, 0.3, 1, "dog"),    # below 0.7
            ]
            model = self._make_model_mock(detections)
            config = PipelineConfig(
                images_dir=Path(d), labels_dir=Path(d) / "labels",
                prompt="cats", conf_threshold=0.7,
            )

            stats = BatchStats()
            result, needs_gemini = _process_roboflow_phase(
                img, config, model, self._make_model_info(), stats,
            )

            assert len(result.boxes) == 1  # only the above-threshold box
            assert not needs_gemini
            assert stats.labeled == 1
            assert stats.roboflow_labeled == 1

    def test_uncertain_band_flags_for_gemini(self):
        """Detections in uncertain band (0.4-0.7) → needs_gemini=True."""
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            img.write_bytes(b"fake")

            detections = [
                Detection(320, 240, 100, 80, 0.5, 0, "cat"),  # in uncertain band
            ]
            model = self._make_model_mock(detections)
            config = PipelineConfig(
                images_dir=Path(d), labels_dir=Path(d) / "labels",
                prompt="cats", conf_threshold=0.7,
            )

            stats = BatchStats()
            result, needs_gemini = _process_roboflow_phase(
                img, config, model, self._make_model_info(), stats,
            )

            assert needs_gemini
            assert not result.boxes  # placeholder, no labels yet

    def test_no_detections_deletes_image(self):
        """Zero detections → image deleted."""
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            img.write_bytes(b"fake")

            model = self._make_model_mock([])
            config = PipelineConfig(
                images_dir=Path(d), labels_dir=Path(d) / "labels",
                prompt="cats", conf_threshold=0.7,
            )

            stats = BatchStats()
            result, needs_gemini = _process_roboflow_phase(
                img, config, model, self._make_model_info(), stats,
            )

            assert not img.exists()
            assert result.not_found
            assert stats.deleted == 1

    def test_raw_detections_stored_for_refilter(self):
        """Raw detections are stored in the result for restart re-filtering."""
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "test.jpg"
            img.write_bytes(b"fake")

            detections = [
                Detection(320, 240, 100, 80, 0.9, 0, "cat"),
                Detection(160, 120, 50, 40, 0.5, 1, "dog"),
            ]
            model = self._make_model_mock(detections)
            config = PipelineConfig(
                images_dir=Path(d), labels_dir=Path(d) / "labels",
                prompt="cats", conf_threshold=0.7,
            )

            stats = BatchStats()
            result, _ = _process_roboflow_phase(
                img, config, model, self._make_model_info(), stats,
            )

            assert len(result.raw_detections) == 2
            assert result.img_width == 640
            assert result.img_height == 480


# -------------------------------------------------------------------
# refilter_results
# -------------------------------------------------------------------

class TestRefilterResults:
    def test_raises_threshold_keeps_fewer(self):
        """Higher threshold → detections that were above old threshold may drop."""
        results = [
            ImageResult(
                image_path=Path("/fake/1.jpg"),
                boxes=[YoloBox(0, 0.5, 0.5, 0.3, 0.4)],
                source="roboflow",
                img_width=640, img_height=480,
                raw_detections=[
                    Detection(320, 240, 192, 192, 0.75, 0, "cat"),
                ],
            ),
        ]

        stats, new_results = refilter_results(results, new_threshold=0.8)
        # 0.75 < 0.8 → no longer above threshold, but in uncertain band (0.5-0.8)
        assert len(new_results) == 1
        assert not new_results[0].boxes  # dropped below new threshold

    def test_gemini_results_preserved(self):
        """Gemini-labeled results should not be re-filtered."""
        results = [
            ImageResult(
                image_path=Path("/fake/1.jpg"),
                boxes=[YoloBox(0, 0.5, 0.5, 0.3, 0.4)],
                source="gemini",
            ),
        ]

        stats, new_results = refilter_results(results, new_threshold=0.9)
        assert new_results[0].source == "gemini"
        assert new_results[0].boxes  # preserved
        assert stats.gemini_labeled == 1
