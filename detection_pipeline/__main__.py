"""CLI entrypoint: ``python -m detection_pipeline ...``"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import PipelineConfig
from .pipeline import run_pipeline
from .yolo import write_label_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detection labeling pipeline — batch YOLO label generation",
    )
    parser.add_argument(
        "--images-dir", type=Path, default=Path("dataset/images"),
        help="Directory containing input images (default: dataset/images)",
    )
    parser.add_argument(
        "--labels-dir", type=Path, default=Path("dataset/labels"),
        help="Output directory for YOLO label files (default: dataset/labels)",
    )
    parser.add_argument(
        "--prompt", required=True,
        help="Detection prompt (used for Roboflow discovery and Gemini)",
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
        help="Upload labeled images to Roboflow after pipeline finishes (project name derived from prompt)",
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

    load_dotenv()  # load .env before reading env vars into config

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    # Mute noisy version-upgrade nag from the inference SDK
    logging.getLogger("inference").setLevel(logging.ERROR)

    # Derive upload project name from prompt
    upload_project = ""
    if args.upload:
        from .discovery import normalize_query
        slug = normalize_query(args.prompt).replace(" ", "-")
        upload_project = f"{slug}-detection" if slug else "detection-pipeline"

    config = PipelineConfig(
        images_dir=args.images_dir,
        labels_dir=args.labels_dir,
        prompt=args.prompt,
        conf_threshold=args.conf_threshold,
        refresh_model=args.refresh_model,
        keep_model_cache=args.keep_model_cache,
        expand_query_with_gemini=args.expand_query_with_gemini,
        upload_project=upload_project,
        cache_dir=args.cache_dir,
    )

    if not config.roboflow_configured and not config.gemini_configured:
        parser.error(
            "At least one backend must be configured.\n"
            "Set ROBOFLOW_API_KEY and/or GEMINI_BASE_URL environment variables."
        )

    try:
        stats, results = run_pipeline(config)

        # CLI mode: write labels to disk so upload can find them
        config.labels_dir.mkdir(parents=True, exist_ok=True)
        for result in results:
            if result.boxes and not result.not_found:
                label_path = config.labels_dir / f"{result.image_path.stem}.txt"
                write_label_file(label_path, result.boxes)
            elif result.not_found:
                result.image_path.unlink(missing_ok=True)

        if config.upload_project and stats.labeled > 0:
            from .upload import upload_to_roboflow
            upload_to_roboflow(
                images_dir=config.images_dir,
                labels_dir=config.labels_dir,
                api_key=config.roboflow_api_key,
                project_name=config.upload_project,
            )

        sys.exit(0 if stats.labeled > 0 else 1)
    except (RuntimeError, FileNotFoundError) as exc:
        logging.error("Pipeline aborted: %s", exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
