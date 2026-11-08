import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_discovery_status_configured():
    # settings loaded from backend/.env or config
    settings.AGNES_API_KEY = "sk-test-agnes-key"
    response = client.get("/api/discovery/status")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["provider"] == "Agnes AI"
    assert data["model"] == settings.AGNES_MODEL

def test_discovery_chat_when_not_configured():
    original_agnes = settings.AGNES_API_KEY
    original_openai = settings.OPENAI_API_KEY
    settings.AGNES_API_KEY = None
    settings.OPENAI_API_KEY = None

    try:
        response = client.post("/api/discovery/chat", json={
            "message": "I want to buy a computer but I don't know where to look",
            "history": []
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_configured"
        assert data["configured"] is False
        assert "AGNES_API_KEY" in data["message"]
    finally:
        settings.AGNES_API_KEY = original_agnes
        settings.OPENAI_API_KEY = original_openai

@pytest.mark.asyncio
async def test_discovery_chat_with_mocked_agnes_ai():
    settings.AGNES_API_KEY = "sk-test-agnes-key"

    mock_llm_json = {
        "detected_language": "en",
        "understanding": "You are looking for reliable computer stores and hardware sellers.",
        "message": "I can help you explore top computer stores. I've prepared a search plan across online and general web sources.",
        "needs_clarification": False,
        "clarification_question": None,
        "intent": {
            "objective": "Find stores to buy a computer",
            "category": "shopping",
            "main_topic": "Computer Hardware Stores",
            "related_topics": ["Laptops", "Desktops", "Electronics Retailers"],
            "detected_language": "en",
            "missing_information": None
        },
        "search_plan": {
            "queries": ["best online computer stores", "buy laptop computer electronics shops"],
            "recommended_sources": ["web_search", "wikipedia"],
            "resource_types": ["online shops", "retailers"],
            "reasoning": "Web search indexes major electronics retailers and hardware shops."
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_llm_json)}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        response = client.post("/api/discovery/chat", json={
            "message": "I want to buy a PC but I don't know which stores to check",
            "history": []
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["configured"] is True
        assert data["intent"]["category"] == "shopping"
        assert len(data["search_plan"]["queries"]) >= 1
        assert "web_search" in data["search_plan"]["recommended_sources"]

@pytest.mark.asyncio
async def test_discovery_chat_multilingual_latin_darija():
    settings.AGNES_API_KEY = "sk-test-agnes-key"

    mock_llm_json = {
        "detected_language": "darija",
        "understanding": "Bghiti t3ref 3la handasa dyal tomobilat (Automotive Engineering)",
        "message": "Fhemtek mezian! Handasa dyal tomobilat fiha bzzaf dyal t-takhassosat bhal Mechanical Engineering, Electric Vehicles, w Automotive Electronics.",
        "needs_clarification": False,
        "clarification_question": None,
        "intent": {
            "objective": "Explore automotive engineering resources and programs",
            "category": "education",
            "main_topic": "Automotive Engineering",
            "related_topics": ["Mechanical Engineering", "Electric Vehicles", "Automotive Electronics", "Vehicle Design"],
            "detected_language": "darija",
            "missing_information": None
        },
        "search_plan": {
            "queries": ["automotive engineering courses vehicle design", "electric vehicle engineering tutorial", "mechanical engineering fundamentals"],
            "recommended_sources": ["web_search", "openalex", "openlibrary", "wikipedia"],
            "resource_types": ["courses", "tutorials", "books"],
            "reasoning": "Combining web tutorials, academic works, and book catalogs for automotive engineering."
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_llm_json)}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        response = client.post("/api/discovery/chat", json={
            "message": "bghit chi handasa dyal tomobilat",
            "history": []
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["intent"]["main_topic"] == "Automotive Engineering"
        assert "Electric Vehicles" in data["intent"]["related_topics"]
        assert "openalex" in data["search_plan"]["recommended_sources"]

def test_discovery_search_execution():
    # Test that /api/discovery/search executes with actual connectors
    response = client.post("/api/discovery/search", json={
        "queries": ["automotive engineering", "vehicle design tutorial"],
        "sources": ["wikipedia", "web_search"],
        "mode": "general",
        "limit_per_source": 2,
        "original_objective": "Automotive engineering"
    })
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "total_results" in data
    assert "results" in data
    assert "grouped_by_type" in data
    assert isinstance(data["results"], list)
