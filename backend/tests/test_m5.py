"""
M5 tests — Planning, Reflection, Problem mode.

Covers:
  - prep_plan returned by from-jd and stored on session
  - POST /api/sessions/from-problem happy path
  - from-problem with invalid URL rejected
  - from-problem when scraper returns None (bad URL)
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

JD_TEXT = "Stripe is hiring a Senior Software Engineer."
PARSED = {"company": "Stripe", "role": "Senior Software Engineer", "level": "senior",
          "key_skills": ["Python"], "focus_areas": ["distributed systems"]}
PERSONA = "You are Alex, a Stripe interviewer."
OPENING = "Hi, I'm Alex. Walk me through a system you've designed."
QUESTION_BANK = {
    "warmup": ["Tell me about yourself"],
    "trivia": ["What is consistent hashing?", "Explain CAP", "What is Paxos?", "How does GFS work?"],
    "culture_fit": ["Describe a conflict"],
    "coding": {"type": "system_design", "topic": "Design a payment system", "hints": []},
}
PREP_PLAN = "1. Study distributed systems\n2. Practice system design"

PROBLEM = {
    "title": "Two Sum",
    "difficulty": "Easy",
    "description": "Given an array of integers, return indices of the two numbers that add up to target.",
}
PROBLEM_PERSONA = "You are Sam, a Google coding interviewer."
PROBLEM_OPENING = "Hi, I'm Sam. Today's problem is Two Sum. Walk me through your approach."


# ── Planning: prep_plan in from-jd ──────────────────────────────────────────

def test_from_jd_returns_prep_plan(client):
    async def fake_complete(*_, **__):
        return OPENING

    with patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_jds.process_jd = AsyncMock(
            return_value=(PARSED, PERSONA, QUESTION_BANK, PREP_PLAN)
        )
        resp = client.post("/api/sessions/from-jd", json={"jd": JD_TEXT})

    assert resp.status_code == 200
    data = resp.json()
    assert data["prep_plan"] == PREP_PLAN


def test_prep_plan_stored_on_session(client):
    async def fake_complete(*_, **__):
        return OPENING

    with patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_jds.process_jd = AsyncMock(
            return_value=(PARSED, PERSONA, QUESTION_BANK, PREP_PLAN)
        )
        resp = client.post("/api/sessions/from-jd", json={"jd": JD_TEXT})

    sid = resp.json()["session_id"]
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["prep_plan"] == PREP_PLAN


# ── Problem mode: POST /api/sessions/from-problem ───────────────────────────

def test_create_from_problem_happy_path(client):
    async def fake_complete(*_, **__):
        return PROBLEM_OPENING

    with patch("app.routes.sessions.scraper") as mock_scraper, \
         patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_scraper.scrape = AsyncMock(return_value=PROBLEM)
        mock_jds.build_problem_persona = AsyncMock(return_value=PROBLEM_PERSONA)

        resp = client.post(
            "/api/sessions/from-problem",
            json={"problem_url": "https://leetcode.com/problems/two-sum/"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["problem_title"] == "Two Sum"
    assert data["problem_difficulty"] == "Easy"
    assert data["opening_message"] == PROBLEM_OPENING
    assert "session_id" in data


def test_create_from_problem_session_has_mode_problem(client):
    async def fake_complete(*_, **__):
        return PROBLEM_OPENING

    with patch("app.routes.sessions.scraper") as mock_scraper, \
         patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_scraper.scrape = AsyncMock(return_value=PROBLEM)
        mock_jds.build_problem_persona = AsyncMock(return_value=PROBLEM_PERSONA)

        resp = client.post(
            "/api/sessions/from-problem",
            json={"problem_url": "https://leetcode.com/problems/two-sum/"},
        )

    sid = resp.json()["session_id"]
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["mode"] == "problem"
    assert session["problem_url"] == "https://leetcode.com/problems/two-sum/"


def test_create_from_problem_invalid_url_rejected(client):
    resp = client.post(
        "/api/sessions/from-problem",
        json={"problem_url": "https://github.com/not-leetcode"},
    )
    assert resp.status_code == 422


def test_create_from_problem_scraper_failure_returns_422(client):
    with patch("app.routes.sessions.scraper") as mock_scraper:
        mock_scraper.scrape = AsyncMock(return_value=None)
        resp = client.post(
            "/api/sessions/from-problem",
            json={"problem_url": "https://leetcode.com/problems/nonexistent-problem/"},
        )
    assert resp.status_code == 422


def test_create_from_problem_respects_difficulty(client):
    async def fake_complete(*_, **__):
        return PROBLEM_OPENING

    with patch("app.routes.sessions.scraper") as mock_scraper, \
         patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_scraper.scrape = AsyncMock(return_value=PROBLEM)
        mock_jds.build_problem_persona = AsyncMock(return_value=PROBLEM_PERSONA)

        resp = client.post(
            "/api/sessions/from-problem",
            json={"problem_url": "https://leetcode.com/problems/two-sum/", "difficulty": "well_done"},
        )

    sid = resp.json()["session_id"]
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["difficulty"] == "well_done"
