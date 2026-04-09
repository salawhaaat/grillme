import pytest
from unittest.mock import AsyncMock, patch


VALID_URL = "https://leetcode.com/problems/two-sum/"
MOCK_PROBLEM = {
    "title": "Two Sum",
    "difficulty": "Easy",
    "description": "Given an array of integers...",
}


def test_scrape_happy_path(client):
    with patch("app.services.scraper.ScraperService.scrape", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_PROBLEM

        response = client.post("/api/problems/scrape", json={"url": VALID_URL})

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Two Sum"
        assert data["difficulty"] == "Easy"
        assert "description" in data


def test_scrape_invalid_url(client):
    response = client.post("/api/problems/scrape", json={"url": "https://google.com"})
    assert response.status_code == 422


def test_scrape_missing_url(client):
    response = client.post("/api/problems/scrape", json={})
    assert response.status_code == 422


def test_scrape_problem_not_found(client):
    with patch("app.services.scraper.ScraperService.scrape", new_callable=AsyncMock) as mock:
        mock.return_value = None

        response = client.post("/api/problems/scrape", json={"url": VALID_URL})

        assert response.status_code == 404
