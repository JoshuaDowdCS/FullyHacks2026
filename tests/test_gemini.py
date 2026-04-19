"""Unit tests — Gemini client response parsing and routing."""

from detection_pipeline.gemini_client import GeminiClient, GeminiOutcome


class TestParseText:
    """Verify _parse_text covers every contract outcome."""

    def setup_method(self):
        # Create instance without __init__ (avoids google.genai import)
        self.client = object.__new__(GeminiClient)

    # -- OBJECT NOT FOUND sentinel --

    def test_sentinel_exact(self):
        out = self.client._parse_text("OBJECT NOT FOUND")
        assert out.not_found and not out.has_detections and out.error is None

    def test_sentinel_case_insensitive(self):
        out = self.client._parse_text("object not found")
        assert out.not_found

    def test_sentinel_with_whitespace(self):
        out = self.client._parse_text("OBJECT NOT FOUND  ")
        assert out.not_found

    # -- valid YOLO lines (fallback format) --

    def test_single_yolo_line(self):
        out = self.client._parse_text("0 0.5 0.5 0.3 0.4")
        assert out.has_detections and len(out.boxes) == 1

    def test_multiple_yolo_lines(self):
        out = self.client._parse_text("0 0.5 0.5 0.3 0.4\n1 0.2 0.3 0.1 0.2")
        assert len(out.boxes) == 2

    # -- Gemini native [ymin, xmin, ymax, xmax] format --

    def test_gemini_native_single_box(self):
        out = self.client._parse_text("[100, 200, 500, 700]")
        assert out.has_detections and len(out.boxes) == 1

    def test_gemini_native_multiple_boxes(self):
        out = self.client._parse_text("[100, 200, 500, 700]\n[300, 400, 600, 800]")
        assert len(out.boxes) == 2

    # -- error / malformed --

    def test_garbage_string(self):
        out = self.client._parse_text("gibberish text")
        assert out.error is not None and not out.not_found

    def test_empty_string(self):
        out = self.client._parse_text("")
        assert out.error is not None

    def test_unparseable_numbers(self):
        out = self.client._parse_text("42")
        assert out.error is not None


class TestGeminiNoConfidenceFilter:
    """Spec §4.3: Gemini lines are written with NO further confidence filtering."""

    def test_all_lines_kept(self):
        client = object.__new__(GeminiClient)
        out = client._parse_text(
            "0 0.5 0.5 0.3 0.4\n1 0.2 0.3 0.1 0.2\n2 0.8 0.8 0.05 0.05"
        )
        assert len(out.boxes) == 3  # all three kept, no threshold applied
