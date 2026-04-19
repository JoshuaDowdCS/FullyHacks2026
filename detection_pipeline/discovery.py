"""Roboflow Universe model discovery and ranking.

Searches public Universe models, applies hard filters (must be object-detection,
must be downloadable), and ranks by textual relevance to the user prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

UNIVERSE_SEARCH_URL = "https://api.roboflow.com/universe/search"


@dataclass
class DiscoveredModel:
    """A model discovered from Roboflow Universe."""

    project_url: str  # workspace/project-slug
    model_id: str  # project-slug/version  (for inference SDK)
    name: str
    version: int
    model_type: str
    relevance_score: float = 0.0
    description: str = ""
    classes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    # English stop words
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "about", "that", "this", "it", "its", "and", "or", "but",
    "not", "no", "do", "does", "did", "will", "would", "can", "could",
    "should", "may", "might", "i", "we", "you", "they", "he", "she",
    "my", "our", "your", "their", "me", "us", "him", "her",
    # Domain filler — words that appear in every prompt but carry no signal
    "detect", "detection", "detector", "detecting",
    "find", "finding", "finder",
    "identify", "identifying", "identification",
    "recognize", "recognizing", "recognition",
    "model", "models", "dataset", "set", "data",
    "image", "images", "photo", "photos", "picture", "pictures",
    "please", "want", "need", "looking", "look", "search",
    # Action verbs users put in prompts
    "make", "making", "create", "creating", "build", "building",
    "generate", "generating", "get", "getting", "give", "show",
    "run", "use", "using", "start", "train", "training",
})


def normalize_query(prompt: str) -> str:
    """Strip stop words and domain filler from a user prompt for search.

    "A detection set for basketballs" → "basketballs"
    """
    query = prompt.lower().strip()
    query = re.sub(r"[^\w\s-]", "", query)
    words = [w for w in query.split() if w not in _STOP_WORDS]
    # Fall back to original (minus punctuation) if stripping removes everything
    if not words:
        words = re.sub(r"\s+", " ", query).split()
    return " ".join(words)


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def _compute_relevance(model_info: dict, query_terms: list[str]) -> float:
    """Score a model's relevance to the query via text-matching heuristics.

    Weights (documented for judges):
      +3.0  exact word in project name
      +2.5  term appears in class list
      +2.0  substring in project name
      +1.5/N focus bonus (N = number of classes; single-purpose models score higher)
      +1.0  substring in description or tags
      +0.5  popularity tier bonus (>1 000 images)
      +0.5  extra popularity tier (>5 000 images)
    """
    name = (model_info.get("name") or model_info.get("id") or "").lower()
    description = (model_info.get("description") or "").lower()
    tags = " ".join(model_info.get("tags") or []).lower()
    classes = " ".join(model_info.get("classes") or []).lower()

    score = 0.0
    for term in query_terms:
        t = term.lower()
        # Name signals (strongest)
        name_tokens = set(re.split(r"[-_ ]", name))
        if t in name_tokens:
            score += 3.0
        elif t in name:
            score += 2.0
        # Class list (model can actually detect the thing)
        if t in classes:
            score += 2.5
        # Description / tags
        if t in description:
            score += 1.0
        if t in tags:
            score += 1.0

    # Focus bonus: single-purpose models are generally more accurate
    classes_list = model_info.get("classes") or []
    num_classes = len(classes_list) if classes_list else 1
    score += 1.5 / num_classes  # +1.5 for 1 class, +0.75 for 2, etc.

    # Popularity tie-breaker
    images = model_info.get("images") or model_info.get("image_count") or 0
    if isinstance(images, (int, float)):
        if images > 5000:
            score += 1.0
        elif images > 1000:
            score += 0.5

    return score


# ---------------------------------------------------------------------------
# Search API
# ---------------------------------------------------------------------------

def search_models(query: str, api_key: str, max_pages: int = 3) -> list[dict]:
    """Search Roboflow Universe for public models.

    Endpoint returns 12 results per page; we fetch up to *max_pages*.
    """
    all_results: list[dict] = []
    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                UNIVERSE_SEARCH_URL,
                params={"q": query, "page": page, "api_key": api_key},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("Universe search returned %d", resp.status_code)
                break
            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            all_results.extend(results)
            logger.debug("Discovery page %d: %d results", page, len(results))
            if len(results) < 12:
                break  # last page
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Universe search failed: %s", exc)
            break

    logger.info("Discovery: %d total results for %r", len(all_results), query)
    return all_results


# ---------------------------------------------------------------------------
# Field extraction helpers (matched to /universe/search response shape)
# ---------------------------------------------------------------------------

def _extract_version(result: dict) -> int | None:
    """Return the latest version number, or *None* if unavailable."""
    v = result.get("latestVersion")
    if isinstance(v, int) and v > 0:
        return v
    # Fallback paths for alternative response shapes
    if "versions" in result:
        versions = result["versions"]
        if isinstance(versions, int) and versions > 0:
            return versions
        if isinstance(versions, list) and versions:
            entry = versions[-1]
            raw = entry.get("id") or entry if isinstance(entry, dict) else entry
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str):
                try:
                    return int(raw.split("/")[-1])
                except ValueError:
                    pass
    if "version" in result:
        raw = result["version"]
        return int(raw) if isinstance(raw, int) else 1
    return 1


def _extract_model_id(result: dict, version: int) -> str | None:
    """Build an inference-SDK model ID from a Universe search result.

    The URL field looks like:
      https://universe.roboflow.com/<workspace-slug>/<project-slug>
    The inference SDK needs: ``<project-slug>/<version>``
    """
    url = result.get("url") or ""
    path = url.rstrip("/")
    if "universe.roboflow.com/" in path:
        path = path.split("universe.roboflow.com/", 1)[1]
    parts = path.strip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[1]}/{version}"

    # Fallback: id or slug field
    proj_slug = result.get("id") or result.get("slug") or ""
    if proj_slug:
        return f"{proj_slug}/{version}"
    return None


def _extract_project_id(result: dict) -> str:
    """Extract a human-readable project identifier."""
    url = result.get("url") or ""
    if "universe.roboflow.com/" in url:
        parts = url.rstrip("/").split("universe.roboflow.com/", 1)[1].split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    for key in ("id", "project", "slug"):
        val = result.get(key)
        if val:
            return str(val)
    return ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def discover_models(
    query: str,
    api_key: str,
    min_relevance: float = 1.0,
    max_candidates: int = 5,
) -> list[DiscoveredModel]:
    """Discover the best object-detection models for *query*.

    Returns a ranked list (best first). Empty when nothing passes filters.
    """
    raw_results = search_models(query, api_key)
    if not raw_results:
        logger.warning("No models found for query: %r", query)
        return []

    query_terms = normalize_query(query).split()
    candidates: list[DiscoveredModel] = []

    for result in raw_results:
        # --- hard filter: object detection only ---
        model_type = (
            result.get("type") or result.get("project_type") or ""
        ).lower()
        if "detection" not in model_type:
            logger.debug("Skipping non-detection: %s (%s)", result.get("name"), model_type)
            continue

        # --- hard filter: must have a trained model ---
        if result.get("modelCount", 0) < 1:
            logger.debug("Skipping (no trained model): %s", result.get("name"))
            continue

        version = _extract_version(result)
        if version is None:
            continue

        model_id = _extract_model_id(result, version)
        if not model_id:
            continue

        project_id = _extract_project_id(result)
        relevance = _compute_relevance(result, query_terms)

        candidates.append(
            DiscoveredModel(
                project_url=result.get("url") or project_id,
                model_id=model_id,
                name=result.get("name") or project_id,
                version=version,
                model_type=model_type,
                relevance_score=relevance,
                description=result.get("description") or "",
                classes=result.get("classes") or [],
            )
        )

    if not candidates:
        logger.warning("No object-detection models passed hard filters")
        return []

    candidates.sort(key=lambda m: m.relevance_score, reverse=True)

    if candidates[0].relevance_score < min_relevance:
        logger.warning(
            "Best model %s scored %.1f (below min %.1f) — Gemini-only fallback",
            candidates[0].model_id,
            candidates[0].relevance_score,
            min_relevance,
        )
        return []

    top = candidates[:max_candidates]
    for m in top:
        logger.info(
            "Candidate model: %s  name=%s  score=%.1f  classes=%s",
            m.model_id, m.name, m.relevance_score, m.classes[:5],
        )
    return top
