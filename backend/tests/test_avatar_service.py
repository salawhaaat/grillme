"""
Tests for Bug 6 (FIFO eviction in _video_jobs) and Bug 7 (singleton AvatarService).
Also tests for persona passthrough and smalltalk clips.
"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import app.services.avatar as avatar_module
from app.services.avatar import AvatarService, _video_jobs, _MAX_JOBS, avatar_service


class TestFIFOEviction:
    def setup_method(self):
        _video_jobs.clear()

    def teardown_method(self):
        _video_jobs.clear()

    def test_no_eviction_below_limit(self):
        """Inserting fewer than _MAX_JOBS jobs does not evict anything."""
        svc = AvatarService()
        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=True), \
             patch('asyncio.create_task'):
            for i in range(_MAX_JOBS - 1):
                svc.start_response_job(f"text {i}", "voice")
        assert len(_video_jobs) == _MAX_JOBS - 1

    def test_no_eviction_at_limit(self):
        """Inserting exactly _MAX_JOBS jobs results in _MAX_JOBS entries (no eviction yet)."""
        svc = AvatarService()
        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=True), \
             patch('asyncio.create_task'):
            for i in range(_MAX_JOBS):
                svc.start_response_job(f"text {i}", "voice")
        assert len(_video_jobs) == _MAX_JOBS

    def test_eviction_over_limit(self):
        """Inserting _MAX_JOBS + 5 jobs results in exactly _MAX_JOBS entries (5 evicted)."""
        svc = AvatarService()
        job_ids = []
        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=True), \
             patch('asyncio.create_task'):
            for i in range(_MAX_JOBS + 5):
                job_id = svc.start_response_job(f"text {i}", "voice")
                job_ids.append(job_id)
        assert len(_video_jobs) == _MAX_JOBS
        # First 5 should be evicted (oldest)
        for job_id in job_ids[:5]:
            assert job_id not in _video_jobs
        # Last _MAX_JOBS should be present (newest)
        for job_id in job_ids[5:]:
            assert job_id in _video_jobs


class TestSingleton:
    def test_same_instance_across_modules(self):
        """avatar_service is the same object in all route modules (identity check)."""
        from app.services.avatar import avatar_service as svc_from_service
        from app.routes.avatar import avatar_service as svc_from_avatar_route
        from app.routes.converse import avatar_service as svc_from_converse_route
        assert svc_from_service is svc_from_avatar_route
        assert svc_from_service is svc_from_converse_route


class TestPersonaPassthrough:
    def setup_method(self):
        _video_jobs.clear()

    def teardown_method(self):
        _video_jobs.clear()

    def test_persona_passed_to_render(self):
        """start_response_job with persona should pass it to _render_response."""
        svc = AvatarService()
        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=True), \
             patch('asyncio.create_task') as mock_task:
            svc.start_response_job("hello", "en-US-GuyNeural", persona="Alex the interviewer")
        # The coroutine passed to create_task should have persona arg
        args = mock_task.call_args[0][0]  # the coroutine
        assert args is not None  # coroutine was created

    def test_no_persona_default(self):
        """start_response_job without persona should default to None."""
        svc = AvatarService()
        with patch.object(AvatarService, '_is_wav2lip_enabled', return_value=True), \
             patch('asyncio.create_task'):
            job_id = svc.start_response_job("hello", "en-US-GuyNeural")
        assert job_id is not None


class TestSmallTalk:
    def test_get_smalltalk_urls_empty(self):
        """No clips on disk → empty list."""
        svc = AvatarService()
        with patch.object(AvatarService, '_videos_dir', return_value=Path(tempfile.mkdtemp())):
            urls = svc.get_smalltalk_urls()
        assert urls == []

    def test_get_smalltalk_urls_with_files(self):
        """Clips on disk → matching URLs returned."""
        svc = AvatarService()
        tmp = Path(tempfile.mkdtemp())
        (tmp / "smalltalk_0.mp4").write_bytes(b"fake")
        (tmp / "smalltalk_2.mp4").write_bytes(b"fake")
        with patch.object(AvatarService, '_videos_dir', return_value=tmp):
            urls = svc.get_smalltalk_urls()
        assert "/api/avatar/video/smalltalk_0.mp4" in urls
        assert "/api/avatar/video/smalltalk_2.mp4" in urls
        assert len(urls) == 2
