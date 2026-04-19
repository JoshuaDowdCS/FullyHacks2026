"""Unit tests — Gemini client response parsing and routing."""

from detection_pipeline.gemini_client import GeminiClient, GeminiOutcome


class TestParseResponse:
    """Verify _parse_response covers every contract outcome."""

    def setup_method(self):
        self.client = GeminiClient(base_url="http://fake:8080")

    # -- OBJECT NOT FOUND sentinel --

    def test_sentinel_exact(self):
        out = self.client._parse_response({"result": "OBJECT NOT FOUND"})
        assert out.not_found and not out.has_detections and out.error is None

    def test_sentinel_case_insensitive(self):
        out = self.client._parse_response({"result": "object not found"})
        assert out.not_found

    def test_sentinel_with_whitespace(self):
        out = self.client._parse_response({"result": "  OBJECT NOT FOUND  "})
        assert out.not_found

    def test_sentinel_in_list(self):
        out = self.client._parse_response({"result": ["OBJECT NOT FOUND"]})
        assert out.not_found

    # -- valid YOLO lines --

    def test_single_yolo_line(self):
        out = self.client._parse_response({"result": "0 0.5 0.5 0.3 0.4"})
        assert out.has_detections and len(out.boxes) == 1

    def test_multiple_yolo_lines(self):
        out = self.client._parse_response({
            "result": "0 0.5 0.5 0.3 0.4\n1 0.2 0.3 0.1 0.2"
        })
        assert len(out.boxes) == 2

    def test_yolo_lines_as_list(self):
        out = self.client._parse_response({
            "result": ["0 0.5 0.5 0.3 0.4", "1 0.2 0.3 0.1 0.2"]
        })
        assert len(out.boxes) == 2

    # -- alternative response keys --

    def test_detections_key(self):
        out = self.client._parse_response({"detections": "0 0.5 0.5 0.3 0.4"})
        assert out.has_detections

    def test_labels_key(self):
        out = self.client._parse_response({"labels": "0 0.5 0.5 0.3 0.4"})
        assert out.has_detections

    # -- error / malformed --

    def test_garbage_string(self):
        out = self.client._parse_response({"result": "gibberish text"})
        assert out.error is not None and not out.not_found

    def test_empty_string(self):
        out = self.client._parse_response({"result": ""})
        assert out.error is not None

    def test_unexpected_type(self):
        out = self.client._parse_response({"result": 42})
        assert out.error is not None


class TestGeminiNoConfidenceFilter:
    """Spec §4.3: Gemini lines are written with NO further confidence filtering."""

    def test_all_lines_kept(self):
        client = GeminiClient("http://fake:8080")
        out = client._parse_response({
            "result": "0 0.5 0.5 0.3 0.4\n1 0.2 0.3 0.1 0.2\n2 0.8 0.8 0.05 0.05"
        })
        assert len(out.boxes) == 3  # all three kept, no threshold applied
