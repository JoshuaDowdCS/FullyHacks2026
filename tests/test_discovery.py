"""Unit tests — Roboflow model discovery ranking and filtering."""

from detection_pipeline.discovery import (
    DiscoveredModel,
    _compute_relevance,
    _extract_model_id,
    _extract_project_id,
    _extract_version,
    normalize_query,
)


class TestNormalizeQuery:
    def test_strips_stop_words(self):
        assert normalize_query("Find CATS") == "cats"

    def test_strips_domain_filler(self):
        assert normalize_query("A detection set for basketballs") == "basketballs"

    def test_removes_punctuation(self):
        assert normalize_query("cats!!! dogs???") == "cats dogs"

    def test_collapses_whitespace(self):
        assert normalize_query("  cat   dog  ") == "cat dog"

    def test_keeps_hyphens(self):
        assert normalize_query("license-plate") == "license-plate"

    def test_preserves_subject_words(self):
        assert normalize_query("detecting license plates in images") == "license plates"

    def test_fallback_when_all_stripped(self):
        # If every word is a stop word, fall back to the full string
        result = normalize_query("find it")
        assert len(result) > 0


class TestComputeRelevance:
    def test_exact_name_match_scores_high(self):
        model = {"name": "cat-detector", "id": "cat-detector"}
        score = _compute_relevance(model, ["cat"])
        assert score >= 3.0

    def test_class_match(self):
        model = {"name": "generic-model", "classes": ["cat", "dog"]}
        assert _compute_relevance(model, ["cat"]) >= 2.5

    def test_no_match_is_focus_bonus_only(self):
        model = {"name": "something-else", "description": "unrelated"}
        # No textual match — only the focus bonus (1.5 / 1 class) applies
        assert _compute_relevance(model, ["cat"]) == 1.5

    def test_description_match(self):
        model = {"name": "model", "description": "detects cat faces"}
        score = _compute_relevance(model, ["cat"])
        assert score >= 1.0

    def test_popularity_bonus(self):
        base = {"name": "cat-model"}
        popular = {**base, "images": 10000}
        unpopular = {**base, "images": 50}
        assert _compute_relevance(popular, ["cat"]) > _compute_relevance(unpopular, ["cat"])

    def test_multi_term_accumulates(self):
        model = {"name": "license-plate-detector", "classes": ["plate"]}
        single = _compute_relevance(model, ["license"])
        multi = _compute_relevance(model, ["license", "plate"])
        assert multi > single


class TestExtractVersion:
    def test_latest_version(self):
        assert _extract_version({"latestVersion": 3}) == 3

    def test_versions_list_of_dicts(self):
        assert _extract_version({"versions": [{"id": "proj/3"}]}) == 3

    def test_versions_int(self):
        assert _extract_version({"versions": 2}) == 2

    def test_version_key(self):
        assert _extract_version({"version": 5}) == 5

    def test_defaults_to_1(self):
        assert _extract_version({}) == 1


class TestExtractModelId:
    def test_from_universe_url(self):
        result = {"url": "https://universe.roboflow.com/my-ws/my-proj"}
        assert _extract_model_id(result, 3) == "my-proj/3"

    def test_from_id_field(self):
        result = {"id": "my-proj"}
        assert _extract_model_id(result, 1) == "my-proj/1"

    def test_none_when_missing(self):
        assert _extract_model_id({}, 1) is None


class TestExtractProjectId:
    def test_from_universe_url(self):
        assert _extract_project_id({"url": "https://universe.roboflow.com/ws/proj"}) == "ws/proj"

    def test_id_key(self):
        assert _extract_project_id({"id": "my-project"}) == "my-project"

    def test_empty(self):
        assert _extract_project_id({}) == ""
