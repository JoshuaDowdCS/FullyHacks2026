"""YOLO format utilities — box representation, normalization, parsing, file I/O."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class YoloBox:
    """A single YOLO-format bounding box (normalized coordinates)."""

    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float

    def to_line(self) -> str:
        return (
            f"{self.class_id} "
            f"{self.x_center:.6f} {self.y_center:.6f} "
            f"{self.width:.6f} {self.height:.6f}"
        )

    @classmethod
    def from_line(cls, line: str) -> YoloBox:
        parts = line.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Expected 5 values, got {len(parts)}: {line!r}")
        class_id = int(parts[0])
        x_center, y_center, w, h = (float(p) for p in parts[1:])
        return cls(class_id=class_id, x_center=x_center, y_center=y_center, width=w, height=h)

    def is_valid(self) -> bool:
        """Values in reasonable YOLO range."""
        return (
            self.class_id >= 0
            and 0.0 <= self.x_center <= 1.0
            and 0.0 <= self.y_center <= 1.0
            and 0.0 < self.width <= 1.0
            and 0.0 < self.height <= 1.0
        )


def normalize_box(
    x_center_px: float,
    y_center_px: float,
    width_px: float,
    height_px: float,
    image_width: int,
    image_height: int,
    class_id: int,
) -> YoloBox:
    """Convert pixel-coordinate box to normalized YOLO format."""
    return YoloBox(
        class_id=class_id,
        x_center=x_center_px / image_width,
        y_center=y_center_px / image_height,
        width=width_px / image_width,
        height=height_px / image_height,
    )


def parse_yolo_lines(text: str) -> list[YoloBox]:
    """Parse multiple YOLO lines from text, returning only valid boxes."""
    boxes: list[YoloBox] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            box = YoloBox.from_line(line)
            if box.is_valid():
                boxes.append(box)
        except (ValueError, IndexError):
            continue
    return boxes


def write_label_file(path: Path, boxes: list[YoloBox]) -> None:
    """Write YOLO label file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for box in boxes:
            f.write(box.to_line() + "\n")
