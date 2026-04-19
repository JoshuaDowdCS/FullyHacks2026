"""Configuration for the detection labeling pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Pipeline configuration, populated from CLI args and environment."""

    images_dir: Path = field(default_factory=lambda: Path("dataset/images"))
    labels_dir: Path = field(default_factory=lambda: Path("dataset/labels"))
    prompt: str = ""
    conf_threshold: float = 0.7
    refresh_model: bool = False
    keep_model_cache: bool = False
    expand_query_with_gemini: bool = False

    # From environment
    roboflow_api_key: str = field(
        default_factory=lambda: os.environ.get("ROBOFLOW_API_KEY", "")
    )
    gemini_api_key: str = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY", "")
    )

    # Upload
    upload_project: str = ""  # Roboflow project name; empty = no upload

    # Cache
    cache_dir: Path = field(default_factory=lambda: Path(".cache/models"))

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def roboflow_configured(self) -> bool:
        return bool(self.roboflow_api_key)
