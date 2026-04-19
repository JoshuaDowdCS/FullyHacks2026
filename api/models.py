"""Pydantic response schemas for the Review UI API."""

from __future__ import annotations

from pydantic import BaseModel

CLASS_NAMES: dict[int, str] = {0: "object"}


class ImageLabel(BaseModel):
    class_id: int
    class_name: str
    x_center: float
    y_center: float
    width: float
    height: float


class ImageInfo(BaseModel):
    filename: str
    width: int
    height: int
    labels: list[ImageLabel]


class ImagesResponse(BaseModel):
    images: list[ImageInfo]
    conf_threshold: float
    total: int


class StatsResponse(BaseModel):
    total: int
    labeled: int
    conf_threshold: float


class RestartResponse(BaseModel):
    stats: StatsResponse
    new_threshold: float


class KeepResponse(BaseModel):
    new_filename: str


class UploadResponse(BaseModel):
    uploaded: int
    project: str


class UndoResponse(BaseModel):
    action: str
    filename: str


class RunRequest(BaseModel):
    prompt: str
    conf_threshold: float = 0.7


class AcquireWebRequest(BaseModel):
    prompt: str
    count: int = 200


class AcquireYouTubeRequest(BaseModel):
    prompt: str
    youtube_url: str
    max_videos: int = 5
