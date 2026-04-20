"""CLI entrypoint: ``python -m detection_pipeline ...``

Single command that mirrors the UI flow:

    # Scrape images from the web, then label them:
    python -m detection_pipeline --prompt "tennis balls" --source web

    # Extract YouTube frames, then label them:
    python -m detection_pipeline --prompt "tennis balls" --source youtube --youtube-url "https://..."

    # Label images already in dataset/images/:
    python -m detection_pipeline --prompt "tennis balls"
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import PipelineConfig
from .pipeline import run_pipeline
from .yolo import write_classification_label, write_label_file

logger = logging.getLogger(__name__)

UNCLEAN_DIR = Path("unclean_images")


def _acquire_web(prompt: str, out_dir: Path, count: int) -> int:
    """Scrape images from the web and copy results into *out_dir*.

    Collects from ``review/keep/`` AND ``review/maybe_keep/`` to maximise
    yield — the detection pipeline already performs its own Roboflow + Gemini
    filtering, so the scraper's CLIP-uncertain images are fine to include.
    YOLO pre-filtering in the scraper is skipped for the same reason.
    """
    from tools.webscraper import run_scraper, slugify

    staging_dir = Path(".scraper_staging") / slugify(prompt)
    try:
        run_scraper(
            query=prompt, out_dir=staging_dir, count=count,
            require_yolo=False, vlm_review_enabled=False,
        )

        # Gather images from keep + maybe_keep + maybe_remove buckets.
        # The detection pipeline's own Roboflow + Gemini inference will
        # reject images where no target object is found, so it's safe to
        # be generous here.
        source_dirs = [
            staging_dir / "review" / "keep",
            staging_dir / "review" / "maybe_keep",
            staging_dir / "review" / "maybe_remove",
        ]

        out_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src_dir in source_dirs:
            if not src_dir.is_dir():
                continue
            for img in src_dir.iterdir():
                if img.is_file() and not img.name.startswith("."):
                    shutil.copy2(img, out_dir / img.name)
                    copied += 1
        if copied == 0:
            logger.warning("Web scraper produced no images.")
        else:
            logger.info("Copied %d scraped images to %s", copied, out_dir)
        return copied
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def _acquire_youtube(
    prompt: str, out_dir: Path, youtube_url: str | None, max_videos: int,
) -> int:
    """Extract frames from YouTube and copy results into *out_dir*."""
    from tools.webscraper import slugify
    from tools.ytwebscraper import run_yt_scraper

    staging_dir = Path(".scraper_staging") / f"yt_{slugify(prompt)}"
    try:
        run_yt_scraper(
            query=prompt,
            out_dir=staging_dir,
            youtube_url=youtube_url,
            max_videos=max_videos,
        )

        keep_dir = staging_dir / "review" / "keep"
        if not keep_dir.is_dir():
            logger.warning("YouTube scraper produced no frames.")
            return 0

        out_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for img in keep_dir.iterdir():
            if img.is_file():
                shutil.copy2(img, out_dir / img.name)
                copied += 1
        logger.info("Copied %d YouTube frames to %s", copied, out_dir)
        return copied
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detection labeling pipeline — scrape, label, and upload in one command",
    )
    parser.add_argument(
        "--prompt", required=True,
        help="What to detect or classify (e.g. 'tennis balls', 'fire hydrant')",
    )
    parser.add_argument(
        "--task", choices=["detection", "classification"], default="detection",
        help="Task type: 'detection' for bounding boxes, 'classification' for image-level labels (default: detection)",
    )

    # Image source
    parser.add_argument(
        "--source", choices=["existing", "web", "youtube"], default="existing",
        help="Where to get images: 'web' scrapes the internet, 'youtube' extracts "
             "frames, 'existing' uses what's already in --images-dir (default: existing)",
    )
    parser.add_argument(
        "--count", type=int, default=200,
        help="Target number of images to scrape (--source web only, default: 200)",
    )
    parser.add_argument(
        "--youtube-url", default=None,
        help="YouTube URL to extract frames from (--source youtube, optional — "
             "searches YouTube if omitted)",
    )
    parser.add_argument(
        "--max-videos", type=int, default=5,
        help="Max YouTube videos to process (default: 5)",
    )

    # Pipeline options
    parser.add_argument(
        "--images-dir", type=Path, default=Path("dataset/images"),
        help="Directory containing input images (default: dataset/images)",
    )
    parser.add_argument(
        "--labels-dir", type=Path, default=Path("dataset/labels"),
        help="Output directory for YOLO label files (default: dataset/labels)",
    )
    parser.add_argument(
        "--conf-threshold", type=float, default=0.7,
        help="Confidence threshold for Roboflow detections (default: 0.7)",
    )
    parser.add_argument(
        "--refresh-model", action="store_true",
        help="Force re-download of the selected model even if cached",
    )
    parser.add_argument(
        "--keep-model-cache", action="store_true",
        help="Skip end-of-batch deletion of model artifacts",
    )
    parser.add_argument(
        "--expand-query-with-gemini", action="store_true",
        help="Call Gemini once to rewrite the prompt into a shorter search query",
    )
    parser.add_argument(
        "--upload", action="store_true",
        help="Upload labeled images to Roboflow after pipeline finishes",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=Path(".cache/models"),
        help="Directory for cached model artifacts (default: .cache/models)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    load_dotenv()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("inference").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)

    # --- Step 1: Acquire images (if requested) → unclean_images/ ---
    scraped = args.source in ("web", "youtube")
    if args.source == "web":
        acquired = _acquire_web(args.prompt, UNCLEAN_DIR, args.count)
        if acquired == 0:
            logger.error("No images acquired from web scraping. Aborting.")
            sys.exit(1)
    elif args.source == "youtube":
        acquired = _acquire_youtube(
            args.prompt, UNCLEAN_DIR, args.youtube_url, args.max_videos,
        )
        if acquired == 0:
            logger.error("No frames acquired from YouTube. Aborting.")
            sys.exit(1)

    # --- Step 2: Run detection pipeline ---
    # When scraping, the pipeline processes unclean_images/;
    # for --source existing it processes --images-dir directly.
    pipeline_images_dir = UNCLEAN_DIR if scraped else args.images_dir

    upload_project = ""
    if args.upload:
        from .discovery import normalize_query
        slug = normalize_query(args.prompt).replace(" ", "-")
        suffix = "classification" if args.task == "classification" else "detection"
        upload_project = f"{slug}-{suffix}" if slug else f"{suffix}-pipeline"

    config = PipelineConfig(
        images_dir=pipeline_images_dir,
        labels_dir=args.labels_dir,
        prompt=args.prompt,
        conf_threshold=args.conf_threshold,
        task_type=args.task,
        refresh_model=args.refresh_model,
        keep_model_cache=args.keep_model_cache,
        expand_query_with_gemini=bool(args.expand_query_with_gemini),
        upload_project=upload_project,
        cache_dir=args.cache_dir,
    )

    if not config.roboflow_configured and not config.gemini_configured:
        parser.error(
            "At least one backend must be configured.\n"
            "Set ROBOFLOW_API_KEY and/or GEMINI_API_KEY environment variables."
        )

    try:
        stats, results = run_pipeline(config)

        # --- Step 3: Move clean images to dataset/images/, write labels ---
        output_images_dir = args.images_dir  # dataset/images (default)
        output_images_dir.mkdir(parents=True, exist_ok=True)
        config.labels_dir.mkdir(parents=True, exist_ok=True)

        for result in results:
            has_label = result.boxes or result.is_classified
            if has_label and not result.not_found:
                # Copy verified image from unclean_images/ → dataset/images/
                if scraped:
                    shutil.copy2(result.image_path, output_images_dir / result.image_path.name)
                label_path = config.labels_dir / f"{result.image_path.stem}.txt"
                if result.boxes:
                    write_label_file(label_path, result.boxes)
                elif result.is_classified:
                    write_classification_label(label_path, result.class_id)
            elif result.not_found:
                result.image_path.unlink(missing_ok=True)

        if scraped:
            clean_count = sum(1 for r in results if (r.boxes or r.is_classified) and not r.not_found)
            logger.info(
                "Moved %d clean images from %s → %s",
                clean_count, UNCLEAN_DIR, output_images_dir,
            )

        # --- Step 4: Upload (if requested) ---
        if config.upload_project and stats.labeled > 0:
            from .upload import upload_to_roboflow
            rf_project_type = (
                "single-label-classification" if config.task_type == "classification"
                else "object-detection"
            )
            upload_to_roboflow(
                images_dir=output_images_dir,
                labels_dir=config.labels_dir,
                api_key=config.roboflow_api_key,
                project_name=config.upload_project,
                project_type=rf_project_type,
            )

        sys.exit(0 if stats.labeled > 0 else 1)
    except (RuntimeError, FileNotFoundError) as exc:
        logging.error("Pipeline aborted: %s", exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
