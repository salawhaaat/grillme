"""
Bug condition exploration tests for session-start-ux bugfix.

Property 1: Bug Condition — render_intro_video Enqueued on Session Creation

These tests assert that `avatar_service.render_intro_video` is NOT called when
a session is created. On UNFIXED code, `render_intro_video` IS called as a
background task, so these assertions FAIL — confirming the bug exists.

CRITICAL: These tests are EXPECTED TO FAIL on unfixed code.
DO NOT fix the code when these tests fail — failure proves the bug exists.

Validates: Requirements 1.1, 1.2
"""
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.schemas import (
    CodingRound,
    CodingProblem,
    InterviewPipelineResult,
    ParsedJD,
    PersonaOutput,
    PersonaVoice,
    PipelineResult,
    QuestionBank,
)


# ── Shared helpers ─────────────────────────────────────────────────────────

def _persona_output() -> PersonaOutput:
    return PersonaOutput(
        persona_text="You are Elon Musk, direct and impatient.",
        question_bank=QuestionBank(
            warmup=["Tell me about yourself"],
            trivia=["What is consistent hashing?", "Explain CAP theorem",
                    "What is a distributed transaction?", "How does a load balancer work?"],
            culture_fit=["Describe a time you disagreed with a teammate"],
            coding=CodingRound(type="leetcode", topic="Two Sum", hints=[]),
        ),
        prep_plan="Study algorithms.",
        oa_platform=None,
    )


def _pipeline_result_jd() -> PipelineResult:
    return PipelineResult(
        parsed_jd=ParsedJD(
            company="SpaceX",
            role="Software Engineer",
            level="senior",
            key_skills=["Python"],
            focus_areas=["algorithms"],
        ),
        persona=_persona_output(),
    )


def _coding_problem() -> CodingProblem:
    return CodingProblem(
        title="Two Sum",
        difficulty="Easy",
        problem_statement="Find two indices whose values sum to target.",
        full_problem="Given nums and target, return indices.",
        starter_code="class Solution:\n    def twoSum(self, nums, target):\n        pass\n",
        test_cases=[{"input": [[2, 7, 11, 15], 9], "expected": [0, 1]}],
        method_name="twoSum",
    )


def _persona_voice() -> PersonaVoice:
    return PersonaVoice(
        persona_text="You are Elon Musk, direct and impatient.",
        oa_platform=None,
    )


def _interview_pipeline_result() -> InterviewPipelineResult:
    return InterviewPipelineResult(
        parsed_jd=ParsedJD(
            company="Tesla",
            role="Backend Engineer",
            level="mid",
            key_skills=["Python"],
            focus_areas=["algorithms"],
        ),
        problem=None,
        raw_problem={
            "title": "Two Sum",
            "difficulty": "Easy",
            "description": "Given nums and target, return indices.",
        },
        persona=_persona_voice(),
        research=None,
    )


# ── Bug condition exploration tests ───────────────────────────────────────

def test_create_from_jd_does_not_call_render_intro_video(client):
    """
    POST /api/sessions/from-jd must NOT call avatar_service.render_intro_video.

    On UNFIXED code: FAILS — render_intro_video IS called as a background task.
    On FIXED code: PASSES — render_intro_video is never enqueued.

    Counterexample on unfixed code:
        render_intro_video(session_id=<id>, text="Hey, I'm Elon...", voice="en-US-GuyNeural")
        called once for every session created via POST /api/sessions/from-jd.
    """
    async def fake_complete(*_, **__):
        return "Hey, I'm Elon — what have you been building?"

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.services.avatar.AvatarService.render_intro_video",
               new_callable=AsyncMock) as mock_render:

        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result_jd())

        resp = client.post(
            "/api/sessions/from-jd",
            json={"jd": "SpaceX is hiring a Senior Software Engineer.", "difficulty": "medium"},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    # This assertion FAILS on unfixed code (render_intro_video IS called).
    # It PASSES on fixed code (render_intro_video is NOT called).
    mock_render.assert_not_called()


def test_create_session_does_not_call_render_intro_video(client):
    """
    POST /api/sessions/create must NOT call avatar_service.render_intro_video.

    On UNFIXED code: FAILS — render_intro_video IS called as a background task.
    On FIXED code: PASSES — render_intro_video is never enqueued.

    Counterexample on unfixed code:
        render_intro_video(session_id=<id>, text="Hey, I'm Elon...", voice="en-US-GuyNeural")
        called once for every session created via POST /api/sessions/create.
    """
    async def fake_complete(*_, **__):
        return "Hey, I'm Elon — tell me what you've been building."

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.routes.sessions._process_problem_background"), \
         patch("app.services.avatar.AvatarService.render_intro_video",
               new_callable=AsyncMock) as mock_render:

        mock_orch.run_interview_pipeline = AsyncMock(
            return_value=_interview_pipeline_result()
        )

        resp = client.post(
            "/api/sessions/create",
            json={"source": "text", "content": "Build a hash-map solution.", "difficulty": "medium"},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    # This assertion FAILS on unfixed code (render_intro_video IS called).
    # It PASSES on fixed code (render_intro_video is NOT called).
    mock_render.assert_not_called()


def test_create_from_problem_does_not_call_render_intro_video(client):
    """
    POST /api/sessions/from-problem must NOT call avatar_service.render_intro_video.

    On UNFIXED code: FAILS — render_intro_video IS called as a background task.
    On FIXED code: PASSES — render_intro_video is never enqueued.

    Counterexample on unfixed code:
        render_intro_video(session_id=<id>, text="Hey, I'm Elon...", voice="en-US-GuyNeural")
        called once for every session created via POST /api/sessions/from-problem.
    """
    async def fake_complete(*_, **__):
        return "Hey, I'm Elon — walk me through your approach."

    scraped_problem = {
        "title": "Two Sum",
        "difficulty": "Easy",
        "description": "Given an array of integers nums and an integer target, return indices.",
    }

    with patch("app.routes.sessions.scraper") as mock_scraper, \
         patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.services.avatar.AvatarService.render_intro_video",
               new_callable=AsyncMock) as mock_render:

        mock_scraper.scrape = AsyncMock(return_value=scraped_problem)
        mock_orch.build_problem_persona = AsyncMock(
            return_value="You are Elon Musk, direct and impatient."
        )

        resp = client.post(
            "/api/sessions/from-problem",
            json={
                "problem_url": "https://leetcode.com/problems/two-sum/",
                "difficulty": "medium",
            },
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    # This assertion FAILS on unfixed code (render_intro_video IS called).
    # It PASSES on fixed code (render_intro_video is NOT called).
    mock_render.assert_not_called()


# ── Preservation property tests ────────────────────────────────────────────
"""
Property 2: Preservation — Session Creation Response Shape and Avatar Endpoints Unchanged

These tests observe behavior on UNFIXED code for inputs where isBugCondition is false
(i.e., all non-session-creation interactions, plus the response shape of session creation).

EXPECTED OUTCOME: All preservation tests PASS on unfixed code.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from unittest.mock import patch, MagicMock


# ── 1. GET /api/avatar/session/{id}/intro shape preservation ──────────────

def test_intro_status_endpoint_returns_ready_bool(client):
    """
    GET /api/avatar/session/{id}/intro must return a dict with a 'ready' key of type bool.

    This endpoint is preserved by the fix — it must continue to work exactly as before.
    PASSES on unfixed code (the endpoint is unaffected by the session creation change).

    Validates: Requirement 3.6
    """
    with patch("app.services.avatar.AvatarService.get_intro_status") as mock_status:
        mock_status.return_value = {"ready": False}
        resp = client.get("/api/avatar/session/1/intro")

    assert resp.status_code == 200
    body = resp.json()
    assert "ready" in body, f"Response missing 'ready' key: {body}"
    assert isinstance(body["ready"], bool), f"'ready' must be bool, got {type(body['ready'])}: {body}"


def test_intro_status_endpoint_ready_true_includes_video_url(client):
    """
    When ready=True, the response may include a video_url.
    Shape is preserved by the fix.

    Validates: Requirement 3.6
    """
    with patch("app.services.avatar.AvatarService.get_intro_status") as mock_status:
        mock_status.return_value = {
            "ready": True,
            "video_url": "/api/avatar/video/session_1_intro.mp4",
        }
        resp = client.get("/api/avatar/session/1/intro")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert "video_url" in body


# ── 2. GET /api/avatar/scenarios shape preservation ───────────────────────

def test_scenarios_endpoint_returns_clips_list(client):
    """
    GET /api/avatar/scenarios must return {"clips": list}.

    This endpoint is unaffected by the fix.
    PASSES on unfixed code.

    Validates: Requirement 3.3
    """
    with patch("app.services.avatar.AvatarService.get_scenario_manifest") as mock_manifest:
        mock_manifest.return_value = {"clips": []}
        resp = client.get("/api/avatar/scenarios")

    assert resp.status_code == 200
    body = resp.json()
    assert "clips" in body, f"Response missing 'clips' key: {body}"
    assert isinstance(body["clips"], list), f"'clips' must be list, got {type(body['clips'])}: {body}"


def test_scenarios_endpoint_preserves_all_clips(client):
    """
    GET /api/avatar/scenarios returns the full clip list unchanged.

    Validates: Requirement 3.3
    """
    sample_clips = [
        {"phase": "intro", "index": 0, "text": "Hello", "path": "scenarios/intro_0.mp4"},
        {"phase": "intro", "index": 1, "text": "Hi there", "path": "scenarios/intro_1.mp4"},
        {"phase": "warmup", "index": 0, "text": "Let's begin", "path": "scenarios/warmup_0.mp4"},
    ]
    with patch("app.services.avatar.AvatarService.get_scenario_manifest") as mock_manifest:
        mock_manifest.return_value = {"clips": sample_clips}
        resp = client.get("/api/avatar/scenarios")

    assert resp.status_code == 200
    body = resp.json()
    assert body["clips"] == sample_clips


# ── 3. GET /api/avatar/smalltalk shape preservation ───────────────────────

def test_smalltalk_endpoint_returns_clips_list(client):
    """
    GET /api/avatar/smalltalk must return {"clips": list}.

    This endpoint is unaffected by the fix.
    PASSES on unfixed code.

    Validates: Requirement 3.5
    """
    with patch("app.services.avatar.AvatarService.get_smalltalk_urls") as mock_urls:
        mock_urls.return_value = []
        resp = client.get("/api/avatar/smalltalk")

    assert resp.status_code == 200
    body = resp.json()
    assert "clips" in body, f"Response missing 'clips' key: {body}"
    assert isinstance(body["clips"], list), f"'clips' must be list, got {type(body['clips'])}: {body}"


def test_smalltalk_endpoint_returns_provided_urls(client):
    """
    GET /api/avatar/smalltalk returns the URLs from get_smalltalk_urls() unchanged.

    Validates: Requirement 3.5
    """
    sample_urls = [
        "/api/avatar/video/smalltalk_0.mp4",
        "/api/avatar/video/smalltalk_1.mp4",
    ]
    with patch("app.services.avatar.AvatarService.get_smalltalk_urls") as mock_urls:
        mock_urls.return_value = sample_urls
        resp = client.get("/api/avatar/smalltalk")

    assert resp.status_code == 200
    body = resp.json()
    assert body["clips"] == sample_urls


# ── 4. Session creation response shape preservation ───────────────────────

def test_create_from_jd_response_shape_preserved(client):
    """
    POST /api/sessions/from-jd response body must contain:
    session_id, company, role, level, difficulty, opening_message.

    This shape must be preserved after removing the background task.
    PASSES on unfixed code (the response shape is unaffected by the background task removal).

    Validates: Requirement 3.4
    """
    async def fake_complete(*_, **__):
        return "Hey, I'm Elon — what have you been building?"

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.services.avatar.AvatarService.render_intro_video"):

        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result_jd())

        resp = client.post(
            "/api/sessions/from-jd",
            json={"jd": "SpaceX is hiring a Senior Software Engineer.", "difficulty": "medium"},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()

    required_fields = ["session_id", "company", "role", "level", "difficulty", "opening_message"]
    for field in required_fields:
        assert field in body, f"Response missing required field '{field}': {body}"

    # Validate types
    assert isinstance(body["session_id"], int), f"session_id must be int: {body['session_id']}"
    assert isinstance(body["difficulty"], str), f"difficulty must be str: {body['difficulty']}"
    assert isinstance(body["opening_message"], str), f"opening_message must be str: {body['opening_message']}"
    assert len(body["opening_message"]) > 0, "opening_message must not be empty"


# ── 5. Property-based: get_intro_clip() always returns intro URL or null ──

@pytest.mark.xfail(
    reason="get_intro_clip() does not exist yet on unfixed code — will pass after Task 3.2",
    strict=False,
)
@given(
    intro_clips=st.lists(
        st.fixed_dictionaries({
            "phase": st.just("intro"),
            "index": st.integers(min_value=0, max_value=9),
            "text": st.text(min_size=1, max_size=50),
            "path": st.builds(
                lambda i: f"scenarios/intro_{i}.mp4",
                st.integers(min_value=0, max_value=9),
            ),
        }),
        min_size=0,
        max_size=10,
    ),
    non_intro_clips=st.lists(
        st.fixed_dictionaries({
            "phase": st.sampled_from(["warmup", "trivia", "closing", "culture"]),
            "index": st.integers(min_value=0, max_value=4),
            "text": st.text(min_size=1, max_size=50),
            "path": st.builds(
                lambda phase, i: f"scenarios/{phase}_{i}.mp4",
                st.sampled_from(["warmup", "trivia", "closing", "culture"]),
                st.integers(min_value=0, max_value=4),
            ),
        }),
        min_size=0,
        max_size=5,
    ),
)
@h_settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
def test_get_intro_clip_returns_intro_url_or_null(intro_clips, non_intro_clips):
    """
    Property-based test: get_intro_clip() always returns either:
    - {"video_url": None} when no intro clips exist, OR
    - {"video_url": str} where the URL matches "/api/avatar/video/scenarios/intro_"

    The returned URL must NEVER come from a non-intro clip.

    Validates: Requirements 2.2, 2.6
    """
    from app.services.avatar import AvatarService

    all_clips = intro_clips + non_intro_clips
    manifest = {"clips": all_clips}

    service = AvatarService()
    with patch.object(service, "get_scenario_manifest", return_value=manifest):
        result = service.get_intro_clip()

    assert "video_url" in result, f"Result missing 'video_url' key: {result}"

    video_url = result["video_url"]

    if len(intro_clips) == 0:
        # No intro clips → must return None
        assert video_url is None, (
            f"Expected None when no intro clips, got: {video_url}"
        )
    else:
        # Intro clips exist → must return a valid intro URL
        assert video_url is not None, (
            f"Expected a URL when {len(intro_clips)} intro clip(s) exist, got None"
        )
        assert isinstance(video_url, str), f"video_url must be str, got {type(video_url)}"
        assert "/api/avatar/video/scenarios/intro_" in video_url, (
            f"URL must contain '/api/avatar/video/scenarios/intro_', got: {video_url}"
        )
        # Must NOT be a non-intro clip URL
        for non_intro in non_intro_clips:
            assert non_intro["path"] not in video_url or "intro_" in video_url, (
                f"URL {video_url!r} appears to come from a non-intro clip: {non_intro}"
            )
