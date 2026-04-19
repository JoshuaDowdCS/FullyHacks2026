"""Unit tests — YOLO format utilities."""

import tempfile
from pathlib import Path

import pytest

from detection_pipeline.yolo import (
    YoloBox,
    normalize_box,
    parse_yolo_lines,
    write_label_file,
)


# -------------------------------------------------------------------
# YoloBox
# -------------------------------------------------------------------

class TestYoloBox:
    def test_to_line(self):
        box = YoloBox(0, 0.5, 0.5, 0.3, 0.4)
        assert box.to_line() == "0 0.500000 0.500000 0.300000 0.400000"

    def test_from_line(self):
        box = YoloBox.from_line("2 0.123 0.456 0.789 0.321")
        assert box.class_id == 2
        assert abs(box.x_center - 0.123) < 1e-6
        assert abs(box.width - 0.789) < 1e-6

    def test_roundtrip(self):
        original = YoloBox(3, 0.123456, 0.789012, 0.456, 0.321)
        parsed = YoloBox.from_line(original.to_line())
        assert parsed.class_id == original.class_id
        assert abs(parsed.x_center - original.x_center) < 1e-5

    def test_from_line_rejects_wrong_count(self):
        with pytest.raises(ValueError, match="Expected 5"):
            YoloBox.from_line("0 0.5 0.5")

    def test_is_valid_good(self):
        assert YoloBox(0, 0.5, 0.5, 0.3, 0.4).is_valid()

    def test_is_valid_negative_class(self):
        assert not YoloBox(-1, 0.5, 0.5, 0.3, 0.4).is_valid()

    def test_is_valid_out_of_range_x(self):
        assert not YoloBox(0, 1.5, 0.5, 0.3, 0.4).is_valid()

    def test_is_valid_zero_width(self):
        assert not YoloBox(0, 0.5, 0.5, 0.0, 0.4).is_valid()

    def test_is_valid_boundary(self):
        # x_center=0 and y_center=0 are valid; width/height=1 is valid
        assert YoloBox(0, 0.0, 0.0, 1.0, 1.0).is_valid()


# -------------------------------------------------------------------
# normalize_box
# -------------------------------------------------------------------

class TestNormalizeBox:
    def test_center_of_image(self):
        box = normalize_box(320, 240, 100, 80, 640, 480, class_id=1)
        assert box.class_id == 1
        assert box.x_center == 0.5
        assert box.y_center == 0.5
        assert abs(box.width - 100 / 640) < 1e-9
        assert abs(box.height - 80 / 480) < 1e-9

    def test_full_image_box(self):
        box = normalize_box(500, 500, 1000, 1000, 1000, 1000, class_id=0)
        assert box.x_center == 0.5
        assert box.width == 1.0


# -------------------------------------------------------------------
# parse_yolo_lines
# -------------------------------------------------------------------

class TestParseYoloLines:
    def test_single_line(self):
        boxes = parse_yolo_lines("0 0.5 0.5 0.3 0.4")
        assert len(boxes) == 1

    def test_multiple_lines(self):
        boxes = parse_yolo_lines("0 0.5 0.5 0.3 0.4\n1 0.2 0.3 0.1 0.2\n")
        assert len(boxes) == 2

    def test_skips_garbage(self):
        boxes = parse_yolo_lines("0 0.5 0.5 0.3 0.4\nnot a box\n1 0.2 0.3 0.1 0.2")
        assert len(boxes) == 2

    def test_skips_out_of_range(self):
        boxes = parse_yolo_lines("0 0.5 0.5 0.3 0.4\n0 2.0 0.5 0.3 0.4")
        assert len(boxes) == 1

    def test_empty(self):
        assert parse_yolo_lines("") == []

    def test_blank_lines(self):
        assert parse_yolo_lines("\n\n  \n") == []


# -------------------------------------------------------------------
# write_label_file
# -------------------------------------------------------------------

class TestWriteLabelFile:
    def test_writes_correct_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "labels" / "img1.txt"
            boxes = [YoloBox(0, 0.5, 0.5, 0.3, 0.4), YoloBox(1, 0.2, 0.3, 0.1, 0.2)]
            write_label_file(path, boxes)

            lines = path.read_text().strip().split("\n")
            assert len(lines) == 2
            assert lines[0].startswith("0 ")
            assert lines[1].startswith("1 ")

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "a" / "b" / "c.txt"
            write_label_file(path, [YoloBox(0, 0.5, 0.5, 0.3, 0.4)])
            assert path.exists()
