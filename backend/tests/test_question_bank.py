import json

import pytest

from app.services.question_bank import QuestionBankService


@pytest.fixture
def question_bank(tmp_path):
    path = tmp_path / "company_questions.json"
    seed = {
        "amazon": [
            {
                "title": "Word Ladder",
                "slug": "word-ladder",
                "difficulty": "Hard",
                "frequency": 3,
                "sources": ["swolecoder", "KushalVijay", "raleighlittles"],
                "topics": ["graph", "bfs", "string"],
                "last_seen": "2024",
            },
            {
                "title": "Two Sum",
                "slug": "two-sum",
                "difficulty": "Easy",
                "frequency": 1,
                "sources": ["swolecoder"],
                "topics": ["array", "hashmap"],
                "last_seen": "2024",
            },
            {
                "title": "LRU Cache",
                "slug": "lru-cache",
                "difficulty": "Medium",
                "frequency": 2,
                "sources": ["KushalVijay", "raleighlittles"],
                "topics": ["hashmap", "linked-list", "design"],
                "last_seen": "2024",
            },
        ],
        "google": [],
        "stripe": [],
    }
    path.write_text(json.dumps(seed))
    return QuestionBankService(path=path), path


def test_get_for_company_returns_frequency_desc(question_bank):
    service, _ = question_bank
    entries = service.get_for_company("amazon")
    assert [entry.frequency for entry in entries] == [3, 2, 1]


def test_get_for_company_is_case_insensitive(question_bank):
    service, _ = question_bank
    lower = service.get_for_company("amazon")
    mixed = service.get_for_company("Amazon")
    assert [entry.slug for entry in lower] == [entry.slug for entry in mixed]


def test_get_for_company_fuzzy_matches_amazon(question_bank):
    service, _ = question_bank
    entries = service.get_for_company("Amazon Web Services")
    assert len(entries) == 3
    assert entries[0].slug == "word-ladder"


def test_get_for_company_unknown_returns_empty(question_bank):
    service, _ = question_bank
    assert service.get_for_company("unknowncorp") == []


def test_get_for_company_empty_returns_empty(question_bank):
    service, _ = question_bank
    assert service.get_for_company("") == []


def test_companies_returns_top_level_keys(question_bank):
    service, _ = question_bank
    assert set(service.companies()) == {"amazon", "google", "stripe"}


def test_reload_picks_up_file_changes(question_bank):
    service, path = question_bank
    updated = {
        "amazon": [],
        "google": [
            {
                "title": "Merge Intervals",
                "slug": "merge-intervals",
                "difficulty": "Medium",
                "frequency": 2,
                "sources": ["swolecoder", "raleighlittles"],
                "topics": ["intervals", "sorting"],
                "last_seen": "2024",
            }
        ],
        "stripe": [],
    }
    path.write_text(json.dumps(updated))

    service.reload()

    google_entries = service.get_for_company("google")
    assert len(google_entries) == 1
    assert google_entries[0].slug == "merge-intervals"
