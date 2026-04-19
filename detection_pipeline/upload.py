"""Upload labeled dataset to Roboflow after pipeline completes."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"})

MAX_WORKERS = 50
UPLOAD_TIMEOUT = 90  # seconds per upload


def upload_to_roboflow(
    images_dir: Path,
    labels_dir: Path,
    api_key: str,
    project_name: str,
) -> None:
    """Upload all labeled images to a Roboflow project.

    Creates the project if it doesn't exist. Only uploads images
    that have a matching label file. Uses concurrent uploads for speed.
    """
    from roboflow import Roboflow  # type: ignore[import-untyped]

    rf = Roboflow(api_key=api_key)
    workspace = rf.workspace()

    # Get or create project
    project = _get_or_create_project(workspace, project_name)

    # Find all images that have labels
    pairs = _find_labeled_pairs(images_dir, labels_dir)
    if not pairs:
        logger.warning("No labeled images found to upload")
        return

    logger.info("Uploading %d labeled images to project %r (%d workers) ...",
                len(pairs), project_name, MAX_WORKERS)

    uploaded = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_upload_one, project, img, lbl): img.name
            for img, lbl in pairs
        }

        for i, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            try:
                future.result(timeout=UPLOAD_TIMEOUT)
                uploaded += 1
            except TimeoutError:
                logger.warning("  [%d/%d] Timed out: %s", i, len(pairs), name)
                errors += 1
            except Exception as exc:
                logger.warning("  [%d/%d] Failed: %s — %s", i, len(pairs), name, exc)
                errors += 1

            if i % 50 == 0 or i == len(pairs):
                logger.info("  Progress: %d/%d done (%d errors)", i, len(pairs), errors)

    logger.info(
        "Upload complete: %d uploaded, %d errors (project: %s)",
        uploaded, errors, project_name,
    )


def _upload_one(project, image_path: Path, label_path: Path) -> None:
    """Upload a single image+label pair."""
    project.upload(
        image_path=str(image_path),
        annotation_path=str(label_path),
        split="train",
    )


def _get_or_create_project(workspace, project_name: str):
    """Return existing project or create a new one."""
    try:
        project = workspace.project(project_name)
        logger.info("Using existing Roboflow project: %s", project_name)
        return project
    except Exception:
        pass

    logger.info("Creating new Roboflow project: %s", project_name)
    project = workspace.create_project(
        project_name=project_name,
        project_type="object-detection",
        project_license="MIT",
        annotation="basketball",
    )
    return project


def _find_labeled_pairs(
    images_dir: Path, labels_dir: Path,
) -> list[tuple[Path, Path]]:
    """Find image/label pairs where both files exist."""
    pairs = []
    for image_path in sorted(images_dir.iterdir()):
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label_path = labels_dir / f"{image_path.stem}.txt"
        if label_path.exists():
            pairs.append((image_path, label_path))
    return pairs
