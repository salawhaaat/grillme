from unittest.mock import AsyncMock, patch


PROBLEM_URL = "https://leetcode.com/problems/two-sum/"
PROBLEM = {
    "title": "Two Sum",
    "difficulty": "Easy",
    "description": "Given an array of integers...",
}


def _create_problem_session(client):
    async def fake_complete(*_, **__):
        return "Hi, let's begin."

    with patch("app.routes.sessions.scraper") as mock_scraper, \
         patch("app.routes.sessions.jd_service") as mock_jds, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_scraper.scrape = AsyncMock(return_value=PROBLEM)
        mock_jds.build_problem_persona = AsyncMock(return_value="You are Sam, interviewer.")
        return client.post(
            "/api/sessions/from-problem",
            json={"problem_url": PROBLEM_URL},
        )


def test_get_problems_empty_initially(client):
    resp = client.get("/api/problems")
    assert resp.status_code == 200
    assert resp.json() == []


def test_from_problem_adds_problem_to_cache(client):
    create_resp = _create_problem_session(client)
    assert create_resp.status_code == 200

    resp = client.get("/api/problems")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Two Sum"
    assert data[0]["difficulty"] == "Easy"
    assert data[0]["url"] == PROBLEM_URL


def test_get_problems_filters_by_query(client):
    create_resp = _create_problem_session(client)
    assert create_resp.status_code == 200

    resp = client.get("/api/problems?q=two+sum")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Two Sum"

    resp_none = client.get("/api/problems?q=nonexistent")
    assert resp_none.status_code == 200
    assert resp_none.json() == []


def test_same_problem_url_not_duplicated(client):
    first = _create_problem_session(client)
    assert first.status_code == 200
    second = _create_problem_session(client)
    assert second.status_code == 200

    resp = client.get("/api/problems")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
