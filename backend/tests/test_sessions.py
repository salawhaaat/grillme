import json
from unittest.mock import AsyncMock, patch

JD_TEXT = "Stripe is hiring a Senior Software Engineer to build payment infrastructure."

PARSED = {
    "company": "Stripe",
    "role": "Senior Software Engineer",
    "level": "senior",
    "key_skills": ["Python", "distributed systems"],
    "focus_areas": ["system design"],
}
PERSONA = "You are Alex, a Stripe interviewer."
OPENING = "Hi, I'm Alex from Stripe. Walk me through a distributed system you've designed."
QUESTION_BANK = {
    "warmup": ["Tell me about yourself", "Why Stripe?"],
    "trivia": ["What is consistent hashing?", "How does a load balancer work?",
               "Explain CAP theorem", "What is a distributed transaction?"],
    "culture_fit": ["Tell me about a time you disagreed with a teammate"],
    "coding": {"type": "system_design", "topic": "Design a payment retry system",
               "hints": ["Consider idempotency", "Think about backoff strategies"]},
}


def _create_session(client) -> int:
    async def fake_complete(*_, **__):
        return OPENING

    with patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_jds.process_jd = AsyncMock(return_value=(PARSED, PERSONA, QUESTION_BANK))
        resp = client.post("/api/sessions/from-jd", json={"jd": JD_TEXT})
    assert resp.status_code == 200
    return resp.json()["session_id"]


# --- POST /api/sessions/from-jd ---

def test_create_session_from_jd(client):
    async def fake_complete(*_, **__):
        return OPENING

    with patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_jds.process_jd = AsyncMock(return_value=(PARSED, PERSONA, QUESTION_BANK))
        resp = client.post("/api/sessions/from-jd", json={"jd": JD_TEXT})

    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["company"] == "Stripe"
    assert data["role"] == "Senior Software Engineer"
    assert data["opening_message"] == OPENING


def test_create_session_missing_jd_field(client):
    resp = client.post("/api/sessions/from-jd", json={})
    assert resp.status_code == 422


# --- GET /api/sessions/{id} ---

def test_get_session(client):
    session_id = _create_session(client)
    resp = client.get(f"/api/sessions/{session_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert data["company"] == "Stripe"
    # opening message is pre-saved as first assistant message
    assert data["messages"][0] == {"role": "assistant", "content": OPENING}


def test_get_session_not_found(client):
    resp = client.get("/api/sessions/9999")
    assert resp.status_code == 404


# --- POST /api/sessions/{id}/message ---

def test_send_message_streams_response(client):
    session_id = _create_session(client)

    async def fake_stream(*_):
        yield "Tell me about yourself."

    with patch("app.services.llm.LLMService.stream_chat", new=fake_stream):
        resp = client.post(f"/api/sessions/{session_id}/message", json={"content": "Hi"})

    assert resp.status_code == 200
    assert "Tell me about yourself." in resp.text


def test_send_message_saves_messages_to_db(client):
    session_id = _create_session(client)

    async def fake_stream(*_):
        yield "Tell me about yourself."

    with patch("app.services.llm.LLMService.stream_chat", new=fake_stream):
        client.post(f"/api/sessions/{session_id}/message", json={"content": "Hi"})

    resp = client.get(f"/api/sessions/{session_id}")
    msgs = resp.json()["messages"]
    assert len(msgs) == 3  # opening + user + assistant
    assert msgs[0] == {"role": "assistant", "content": OPENING}
    assert msgs[1] == {"role": "user", "content": "Hi"}
    assert msgs[2] == {"role": "assistant", "content": "Tell me about yourself."}


def test_send_message_session_not_found(client):
    resp = client.post("/api/sessions/9999/message", json={"content": "Hi"})
    assert resp.status_code == 404


# --- POST /api/sessions/{id}/finish ---

def test_finish_session(client):
    session_id = _create_session(client)
    scorecard = json.dumps({
        "overall_score": 8,
        "strengths": ["clear thinking"],
        "areas_to_improve": ["depth on distributed systems"],
        "recommendation": "hire",
    })

    with patch("app.routes.sessions.jd_service") as mock_jds:
        mock_jds.generate_scorecard = AsyncMock(return_value=scorecard)
        resp = client.post(f"/api/sessions/{session_id}/finish")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scorecard"]["overall_score"] == 8
    assert data["scorecard"]["recommendation"] == "hire"


def test_finish_session_not_found(client):
    resp = client.post("/api/sessions/9999/finish")
    assert resp.status_code == 404
