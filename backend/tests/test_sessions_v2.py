"""Tests for difficulty modes and session list endpoint."""
import json
from unittest.mock import AsyncMock, patch

from app.agents.schemas import (
    CodingRound,
    ParsedJD,
    PersonaOutput,
    PipelineResult,
    QuestionBank,
    ScorecardResult,
)

JD_TEXT = "Google is hiring a Staff Engineer on the Search team."
PARSED = {"company": "Google", "role": "Staff Engineer", "level": "staff", "key_skills": ["algorithms"], "focus_areas": ["systems"]}
PERSONA = "You are Jordan, a Google interviewer."
OPENING = "Hi, I'm Jordan. Tell me about a large-scale system you designed."
QUESTION_BANK = {
    "warmup": ["Tell me about yourself"],
    "trivia": ["What is consistent hashing?", "Explain MapReduce", "How does GFS work?", "What is Paxos?"],
    "culture_fit": ["Describe a time you led without authority"],
    "coding": {"type": "system_design", "topic": "Design Google Search index", "hints": []},
}


def _pipeline_result() -> PipelineResult:
    return PipelineResult(
        parsed_jd=ParsedJD(
            company=PARSED["company"],
            role=PARSED["role"],
            level=PARSED["level"],
            key_skills=PARSED["key_skills"],
            focus_areas=PARSED["focus_areas"],
        ),
        persona=PersonaOutput(
            persona_text=PERSONA,
            question_bank=QuestionBank(
                warmup=QUESTION_BANK["warmup"],
                trivia=QUESTION_BANK["trivia"],
                culture_fit=QUESTION_BANK["culture_fit"],
                coding=CodingRound(**QUESTION_BANK["coding"]),
            ),
            prep_plan="1. Study Python",
            oa_platform=None,
        ),
    )


def _create_session(client, difficulty: str = "medium") -> int:
    async def fake_complete(*_, **__):
        return OPENING

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result())
        resp = client.post("/api/sessions/from-jd", json={"jd": JD_TEXT, "difficulty": difficulty})
    assert resp.status_code == 200
    return resp.json()["session_id"]


# --- difficulty field ---

def test_difficulty_defaults_to_medium(client):
    async def fake_complete(*_, **__):
        return OPENING

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result())
        resp = client.post("/api/sessions/from-jd", json={"jd": JD_TEXT})

    session_id = resp.json()["session_id"]
    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["difficulty"] == "medium"


def test_difficulty_stored_on_session(client):
    for diff in ("rare", "medium", "well_done"):
        sid = _create_session(client, difficulty=diff)
        session = client.get(f"/api/sessions/{sid}").json()
        assert session["difficulty"] == diff


def test_invalid_difficulty_rejected(client):
    async def fake_complete(*_, **__):
        return OPENING

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result())
        resp = client.post("/api/sessions/from-jd", json={"jd": JD_TEXT, "difficulty": "god_mode"})

    assert resp.status_code == 422


# --- GET /api/sessions/ ---

def test_list_sessions_empty(client):
    resp = client.get("/api/sessions/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_sessions_returns_created_sessions(client):
    _create_session(client, "rare")
    _create_session(client, "well_done")

    resp = client.get("/api/sessions/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    difficulties = {s["difficulty"] for s in data}
    assert difficulties == {"rare", "well_done"}


def test_list_sessions_ordered_newest_first(client):
    id1 = _create_session(client)
    id2 = _create_session(client)

    resp = client.get("/api/sessions/")
    ids = [s["id"] for s in resp.json()]
    assert ids[0] == id2
    assert ids[1] == id1


def test_list_sessions_includes_score_when_finished(client):
    sid = _create_session(client)
    with patch("app.routes.sessions.orchestrator") as mock_orch:
        mock_orch.run_scoring = AsyncMock(
            return_value=ScorecardResult(
                overall_score=9,
                strengths=["clear"],
                areas_to_improve=[],
                recommendation="hire",
            )
        )
        client.post(f"/api/sessions/{sid}/finish")

    resp = client.get("/api/sessions/")
    session = next(s for s in resp.json() if s["id"] == sid)
    assert session["overall_score"] == 9
    assert session["finished_at"] is not None
    assert session["total_tokens"] >= 0


def test_list_sessions_score_null_when_not_finished(client):
    sid = _create_session(client)
    resp = client.get("/api/sessions/")
    session = next(s for s in resp.json() if s["id"] == sid)
    assert session["overall_score"] is None
    assert session["finished_at"] is None


# --- system prompt difficulty instructions ---

def test_rare_mode_system_prompt_contains_hint_instruction(client):
    sid = _create_session(client, "rare")
    captured: list[str] = []

    async def fake_stream(_self, messages, **__):
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        captured.append(system)
        yield "ok"

    with patch("app.services.llm.LLMService.stream_chat", new=fake_stream):
        client.post(f"/api/sessions/{sid}/message", json={"content": "I'm not sure"})

    assert captured, "stream_chat was never called"
    assert "hint" in captured[0].lower(), f"Expected hint instruction in rare prompt, got: {captured[0][:300]}"


def test_well_done_mode_system_prompt_contains_no_hints_instruction(client):
    sid = _create_session(client, "well_done")
    captured: list[str] = []

    async def fake_stream(_self, messages, **__):
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        captured.append(system)
        yield "ok"

    with patch("app.services.llm.LLMService.stream_chat", new=fake_stream):
        client.post(f"/api/sessions/{sid}/message", json={"content": "I don't know"})

    assert captured, "stream_chat was never called"
    assert any(kw in captured[0].lower() for kw in ("never", "no hint", "fail")), \
        f"Expected strict instruction in well_done prompt, got: {captured[0][:300]}"
