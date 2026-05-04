"""Tests for pre-rendered interview scenario system: registry, clip selector, manifest, routes."""
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.scenarios import (
    SCENARIO_PHRASES,
    VALID_PHASES,
    ScenarioPhrase,
    get_phrases_by_phase,
)
from app.services.clip_selector import (
    SIMILARITY_THRESHOLD,
    find_match,
    jaccard_similarity,
    normalize_text,
)
from app.services.avatar import AvatarService


# ── 12.1 Registry structure tests ────────────────────────────────────────────


class TestRegistryStructure:
    def test_all_phases_present(self):
        phases_in_registry = {p["phase"] for p in SCENARIO_PHRASES}
        assert phases_in_registry == VALID_PHASES

    def test_all_phases_valid(self):
        for phrase in SCENARIO_PHRASES:
            assert phrase["phase"] in VALID_PHASES

    def test_unique_phase_index_pairs(self):
        pairs = [(p["phase"], p["index"]) for p in SCENARIO_PHRASES]
        assert len(pairs) == len(set(pairs))

    def test_indices_contiguous_per_phase(self):
        for phase in VALID_PHASES:
            indices = sorted(p["index"] for p in SCENARIO_PHRASES if p["phase"] == phase)
            assert indices == list(range(len(indices)))

    def test_non_empty_text(self):
        for phrase in SCENARIO_PHRASES:
            assert phrase["text"].strip()

    def test_intro_count(self):
        count = len(get_phrases_by_phase("intro"))
        assert 3 <= count <= 5

    def test_behavioral_count(self):
        count = len(get_phrases_by_phase("behavioral"))
        assert 8 <= count <= 10

    def test_coding_intro_count(self):
        count = len(get_phrases_by_phase("coding_intro"))
        assert 3 <= count <= 5

    def test_coding_feedback_count(self):
        count = len(get_phrases_by_phase("coding_feedback"))
        assert 10 <= count <= 15

    def test_closing_count(self):
        count = len(get_phrases_by_phase("closing"))
        assert 3 <= count <= 5

    def test_get_phrases_by_phase_filters(self):
        intro = get_phrases_by_phase("intro")
        for p in intro:
            assert p["phase"] == "intro"

    def test_get_phrases_by_phase_unknown(self):
        assert get_phrases_by_phase("nonexistent") == []


# ── 12.2 Clip selector tests ────────────────────────────────────────────────


class TestNormalizeText:
    def test_lowercase(self):
        assert "hello" in normalize_text("Hello")

    def test_strip_punctuation(self):
        words = normalize_text("Hello, world!")
        assert words == {"hello", "world"}

    def test_empty_string(self):
        assert normalize_text("") == set()


class TestJaccardSimilarity:
    def test_identical_sets(self):
        s = {"a", "b", "c"}
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets(self):
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        # {a, b, c} ∩ {b, c, d} = {b, c}, union = {a, b, c, d}
        assert jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)

    def test_empty_sets(self):
        assert jaccard_similarity(set(), set()) == 0.0
        assert jaccard_similarity({"a"}, set()) == 0.0


class TestFindMatch:
    CLIPS = [
        {"phase": "intro", "index": 0, "text": "Hey I'm Elon let's get started", "path": "scenarios/intro_0.mp4"},
        {"phase": "intro", "index": 1, "text": "Tell me about yourself briefly", "path": "scenarios/intro_1.mp4"},
        {"phase": "behavioral", "index": 0, "text": "Tell me more about that", "path": "scenarios/behavioral_0.mp4"},
        {"phase": "coding_feedback", "index": 0, "text": "What's your initial approach", "path": "scenarios/coding_feedback_0.mp4"},
    ]

    def test_exact_match(self):
        result = find_match("Hey I'm Elon let's get started", "intro", self.CLIPS)
        assert result is not None
        assert result["phase"] == "intro"
        assert result["index"] == 0
        assert result["score"] == 1.0

    def test_no_match_below_threshold(self):
        # Clip selector now always returns the best available clip for the phase
        # (threshold removed to maximize pre-rendered clip usage)
        result = find_match("completely unrelated text about weather", "intro", self.CLIPS)
        assert result is not None  # always returns best available clip
        assert result["phase"] == "intro"

    def test_phase_filtering(self):
        # "Tell me more about that" is behavioral, should not match when phase is intro
        result = find_match("Tell me more about that", "intro", self.CLIPS)
        assert result is None

    def test_phase_filtering_correct_phase(self):
        result = find_match("Tell me more about that", "behavioral", self.CLIPS)
        assert result is not None
        assert result["phase"] == "behavioral"

    def test_highest_score_wins(self):
        clips = [
            {"phase": "intro", "index": 0, "text": "hello world foo bar baz", "path": "scenarios/intro_0.mp4"},
            {"phase": "intro", "index": 1, "text": "hello world foo bar baz qux", "path": "scenarios/intro_1.mp4"},
        ]
        # "hello world foo bar baz" is exact match for index 0 (score=1.0)
        result = find_match("hello world foo bar baz", "intro", clips)
        assert result is not None
        assert result["index"] == 0
        assert result["score"] == 1.0

    def test_empty_manifest(self):
        result = find_match("hello", "intro", [])
        assert result is None

    def test_empty_response(self):
        result = find_match("", "intro", self.CLIPS)
        assert result is None

    def test_no_match_wrong_phase(self):
        result = find_match("What's your initial approach", "closing", self.CLIPS)
        assert result is None


# ── 12.3 Prerender scenario clips tests ─────────────────────────────────────


class TestPrerenderScenarioClips:
    @pytest.mark.asyncio
    async def test_skip_existing_clips(self):
        svc = AvatarService()
        tmp = Path(tempfile.mkdtemp())
        scenarios_dir = tmp / "scenarios"
        scenarios_dir.mkdir()
        # Create one existing clip
        (scenarios_dir / "intro_0.mp4").write_bytes(b"existing")

        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=True), \
             patch.object(AvatarService, '_videos_dir', return_value=tmp), \
             patch('httpx.AsyncClient') as mock_client_cls:
            mock_response = MagicMock()
            mock_response.content = b"video_bytes"
            mock_response.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await svc.prerender_scenario_clips()

            # intro_0 should NOT have been re-rendered
            calls = mock_client.post.call_args_list
            rendered_texts = [c.kwargs["json"]["text"] for c in calls]
            intro_0_text = SCENARIO_PHRASES[0]["text"]
            assert intro_0_text not in rendered_texts

    @pytest.mark.asyncio
    async def test_wav2lip_disabled_skips(self):
        svc = AvatarService()
        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=False):
            # Should return without error
            await svc.prerender_scenario_clips()

    @pytest.mark.asyncio
    async def test_connect_error_continues(self):
        """Avatar service unreachable — should log warning and continue."""
        import httpx as httpx_mod
        svc = AvatarService()
        tmp = Path(tempfile.mkdtemp())

        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=True), \
             patch.object(AvatarService, '_videos_dir', return_value=tmp), \
             patch.object(AvatarService, '_wait_for_avatar_service', new=AsyncMock(return_value=False)), \
             patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx_mod.ConnectError("unreachable"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Should not raise
            await svc.prerender_scenario_clips()

            # Manifest should still be written (with 0 clips)
            manifest_path = tmp / "scenarios" / "manifest.json"
            assert manifest_path.exists()
            data = json.loads(manifest_path.read_text())
            assert data["clips"] == []


# ── 12.3b Manifest tests ────────────────────────────────────────────────────


class TestScenarioManifest:
    def test_get_manifest_missing(self):
        svc = AvatarService()
        tmp = Path(tempfile.mkdtemp())
        with patch.object(AvatarService, '_videos_dir', return_value=tmp):
            result = svc.get_scenario_manifest()
        assert result == {"clips": []}

    def test_get_manifest_present(self):
        svc = AvatarService()
        tmp = Path(tempfile.mkdtemp())
        scenarios_dir = tmp / "scenarios"
        scenarios_dir.mkdir()
        manifest = {"clips": [{"phase": "intro", "index": 0, "text": "hi", "path": "scenarios/intro_0.mp4"}]}
        (scenarios_dir / "manifest.json").write_text(json.dumps(manifest))
        with patch.object(AvatarService, '_videos_dir', return_value=tmp):
            result = svc.get_scenario_manifest()
        assert len(result["clips"]) == 1
        assert result["clips"][0]["phase"] == "intro"

    def test_get_manifest_corrupted(self):
        svc = AvatarService()
        tmp = Path(tempfile.mkdtemp())
        scenarios_dir = tmp / "scenarios"
        scenarios_dir.mkdir()
        (scenarios_dir / "manifest.json").write_text("not json{{{")
        with patch.object(AvatarService, '_videos_dir', return_value=tmp):
            result = svc.get_scenario_manifest()
        assert result == {"clips": []}

    def test_write_manifest_includes_existing_clips(self):
        svc = AvatarService()
        tmp = Path(tempfile.mkdtemp())
        scenarios_dir = tmp / "scenarios"
        scenarios_dir.mkdir()
        # Create a few clips
        (scenarios_dir / "intro_0.mp4").write_bytes(b"fake")
        (scenarios_dir / "behavioral_0.mp4").write_bytes(b"fake")

        with patch.object(AvatarService, '_videos_dir', return_value=tmp):
            svc._write_scenario_manifest()

        manifest = json.loads((scenarios_dir / "manifest.json").read_text())
        paths = [c["path"] for c in manifest["clips"]]
        assert "scenarios/intro_0.mp4" in paths
        assert "scenarios/behavioral_0.mp4" in paths


# ── 12.4 GET /api/avatar/scenarios endpoint tests ───────────────────────────


class TestScenariosEndpoint:
    def test_scenarios_endpoint_empty(self, client):
        with patch.object(AvatarService, 'get_scenario_manifest', return_value={"clips": []}):
            res = client.get("/api/avatar/scenarios")
        assert res.status_code == 200
        assert res.json() == {"clips": []}

    def test_scenarios_endpoint_with_clips(self, client):
        manifest = {"clips": [{"phase": "intro", "index": 0, "text": "hi", "path": "scenarios/intro_0.mp4"}]}
        with patch.object(AvatarService, 'get_scenario_manifest', return_value=manifest):
            res = client.get("/api/avatar/scenarios")
        assert res.status_code == 200
        assert len(res.json()["clips"]) == 1


# ── 12.5 Extended video route tests ─────────────────────────────────────────


class TestVideoRoute:
    def test_scenario_path_valid(self, client):
        tmp = Path(tempfile.mkdtemp())
        scenarios_dir = tmp / "scenarios"
        scenarios_dir.mkdir()
        (scenarios_dir / "intro_0.mp4").write_bytes(b"fake_video")
        with patch("app.routes.avatar.settings") as mock_settings:
            mock_settings.videos_dir = str(tmp)
            res = client.get("/api/avatar/video/scenarios/intro_0.mp4")
        assert res.status_code == 200

    def test_scenario_path_404(self, client):
        tmp = Path(tempfile.mkdtemp())
        scenarios_dir = tmp / "scenarios"
        scenarios_dir.mkdir()
        with patch("app.routes.avatar.settings") as mock_settings:
            mock_settings.videos_dir = str(tmp)
            res = client.get("/api/avatar/video/scenarios/intro_99.mp4")
        assert res.status_code == 404

    def test_traversal_rejected(self, client):
        res = client.get("/api/avatar/video/scenarios/..%2F..%2Fetc%2Fpasswd")
        assert res.status_code in (400, 404)  # path normalization may produce 404

    def test_traversal_dotdot_rejected(self, client):
        # Direct ".." in path segment
        res = client.get("/api/avatar/video/scenarios/..intro_0.mp4")
        assert res.status_code == 400

    def test_invalid_scenario_path_rejected(self, client):
        # Invalid scenario path format (not matching regex)
        res = client.get("/api/avatar/video/scenarios/UPPER_0.mp4")
        assert res.status_code == 400

    def test_backslash_rejected(self, client):
        res = client.get("/api/avatar/video/test\\file.mp4")
        assert res.status_code == 400

    def test_simple_filename_still_works(self, client):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "smalltalk_0.mp4").write_bytes(b"fake_video")
        with patch("app.routes.avatar.settings") as mock_settings:
            mock_settings.videos_dir = str(tmp)
            res = client.get("/api/avatar/video/smalltalk_0.mp4")
        assert res.status_code == 200
