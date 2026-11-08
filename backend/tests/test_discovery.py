import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_discovery_status():
    response = client.get("/api/discovery/status")
    assert response.status_code == 200
    data = response.json()
    assert "configured" in data
    assert "provider" in data

def test_discovery_chat_when_not_configured():
    original_zai = settings.ZAI_API_KEY
    original_openai = settings.OPENAI_API_KEY
    settings.ZAI_API_KEY = None
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
        assert "ZAI_API_KEY" in data["message"]
    finally:
        settings.ZAI_API_KEY = original_zai
        settings.OPENAI_API_KEY = original_openai

@pytest.mark.asyncio
async def test_discovery_chat_with_mocked_ai():
    settings.ZAI_API_KEY = "test_key_123"

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
async def test_discovery_chat_multilingual_darija():
    settings.ZAI_API_KEY = "test_key_123"

    mock_llm_json = {
        "detected_language": "darija",
        "understanding": "باغي تقلب على كورسات ديال لانفورماتيك فمعالجة البيانات (Data Processing)",
        "message": "فهمتك مزيان! كتهتم بمعالجة البيانات، هاد المجال كيتفرع لـ Data Science و Data Engineering. وجدت ليك خطة بحث شاملة.",
        "needs_clarification": False,
        "clarification_question": None,
        "intent": {
            "objective": "Find computer science courses in data processing",
            "category": "education",
            "main_topic": "Data Processing & Data Science",
            "related_topics": ["Data Analytics", "Data Engineering", "Python"],
            "detected_language": "darija",
            "missing_information": None
        },
        "search_plan": {
            "queries": ["best data processing computer science courses", "cours informatique traitement de donnees", "data engineering fundamentals tutorial"],
            "recommended_sources": ["web_search", "openalex", "openlibrary"],
            "resource_types": ["courses", "tutorials", "books"],
            "reasoning": "Combining web tutorials, academic courses, and books for data processing."
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
            "message": "بغيت شي cours ديال informatique لي فيه traitement de données",
            "history": []
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["intent"]["detected_language"] == "darija"
        assert "openalex" in data["search_plan"]["recommended_sources"]

def test_discovery_search_execution():
    # Test that /api/discovery/search executes with actual connectors
    response = client.post("/api/discovery/search", json={
        "queries": ["data science tutorial", "python data analysis"],
        "sources": ["wikipedia", "web_search"],
        "mode": "general",
        "limit_per_source": 2,
        "original_objective": "Learn data science"
    })
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "total_results" in data
    assert "results" in data
    assert "grouped_by_type" in data
    assert isinstance(data["results"], list)
