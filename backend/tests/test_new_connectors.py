import pytest
from unittest.mock import patch, MagicMock
from app.connectors.kaggle import KaggleConnector
from app.connectors.internet_archive import InternetArchiveConnector
from app.connectors.openalex import OpenAlexConnector
from app.connectors.crossref import CrossrefConnector
from app.connectors.openlibrary import OpenLibraryConnector
from app.core.config import settings

# 1. Kaggle Tests
@pytest.mark.asyncio
async def test_kaggle_not_configured():
    conn = KaggleConnector()
    with patch.object(settings, "KAGGLE_USERNAME", None), patch.object(settings, "KAGGLE_KEY", None):
        health = conn.check_health()
        assert health["status"] == "not_configured"
        diag = await conn.test_connection()
        assert diag["configured"] is False
        results = await conn.search("machine learning")
        assert results == []

@pytest.mark.asyncio
async def test_kaggle_authenticated_search():
    conn = KaggleConnector()
    with patch.object(settings, "KAGGLE_USERNAME", "myuser"), patch.object(settings, "KAGGLE_KEY", "mykey"):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": 1234,
                "ref": "owner/dataset-name",
                "title": "Clean Medical Imaging Dataset",
                "subtitle": "High resolution labeled clinical images",
                "creatorName": "Dr. Smith",
                "lastUpdated": "2024-01-15T12:00:00Z",
                "voteCount": 150,
                "downloadCount": 3200,
                "usabilityRating": 0.94
            }
        ]

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            diag = await conn.test_connection()
            assert diag["configured"] is True
            assert diag["connected"] is True

            results = await conn.search("imaging")
            assert len(results) == 1
            assert results[0].source_name == "kaggle"
            assert results[0].title == "Clean Medical Imaging Dataset"
            assert "https://www.kaggle.com/datasets/owner/dataset-name" == results[0].source_url
            assert results[0].content_type == "dataset"
            assert results[0].engagement_metrics["vote_count"] == 150

# 2. Internet Archive Tests
@pytest.mark.asyncio
async def test_internet_archive_search():
    conn = InternetArchiveConnector()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": {
            "docs": [
                {
                    "identifier": "computervision_handbook_1998",
                    "title": "Computer Vision Principles",
                    "description": "Comprehensive reference handbook on early digital image parsing.",
                    "creator": "Alan Turing Press",
                    "date": "1998-05-10T00:00:00Z",
                    "mediatype": "texts",
                    "downloads": 482
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        diag = await conn.test_connection()
        assert diag["connected"] is True

        results = await conn.search("computer vision")
        assert len(results) == 1
        assert results[0].source_name == "internet_archive"
        assert results[0].source_url == "https://archive.org/details/computervision_handbook_1998"
        assert results[0].engagement_metrics["downloads"] == 482

# 3. OpenAlex Tests
@pytest.mark.asyncio
async def test_openalex_search():
    conn = OpenAlexConnector()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "id": "https://openalex.org/W123456789",
                "title": "Deep Residual Learning for Image Recognition",
                "doi": "https://doi.org/10.1109/cvpr.2016.90",
                "publication_year": 2016,
                "publication_date": "2016-06-27",
                "authorships": [
                    {"author": {"display_name": "Kaiming He"}}
                ],
                "cited_by_count": 180000,
                "open_access": {"is_oa": True},
                "abstract_inverted_index": {
                    "Deeper": [0],
                    "neural": [1],
                    "networks": [2],
                    "are": [3],
                    "more": [4],
                    "difficult": [5],
                    "to": [6],
                    "train.": [7]
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        diag = await conn.test_connection()
        assert diag["connected"] is True

        results = await conn.search("resnet")
        assert len(results) == 1
        assert results[0].source_name == "openalex"
        assert results[0].title == "Deep Residual Learning for Image Recognition"
        assert results[0].author == "Kaiming He"
        assert results[0].engagement_metrics["citation_count"] == 180000
        assert "Deeper neural networks are more difficult to train." in results[0].content_snippet

# 4. Crossref Tests
@pytest.mark.asyncio
async def test_crossref_search():
    conn = CrossrefConnector()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "items": [
                {
                    "DOI": "10.1038/nature14539",
                    "title": ["Deep learning"],
                    "author": [
                        {"given": "Yann", "family": "LeCun"},
                        {"given": "Yoshua", "family": "Bengio"}
                    ],
                    "publisher": "Springer Science and Business Media LLC",
                    "published": {"date-parts": [[2015, 5, 28]]},
                    "URL": "http://dx.doi.org/10.1038/nature14539",
                    "is-referenced-by-count": 45000,
                    "type": "journal-article",
                    "abstract": "<jats:p>Deep learning enables computational models that are composed of multiple processing layers.</jats:p>"
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        diag = await conn.test_connection()
        assert diag["connected"] is True

        results = await conn.search("deep learning")
        assert len(results) == 1
        assert results[0].source_name == "crossref"
        assert results[0].title == "Deep learning"
        assert results[0].author == "Yann LeCun, Yoshua Bengio"
        assert results[0].engagement_metrics["citations"] == 45000
        assert "<jats:p>" not in results[0].content_snippet

# 5. Open Library Tests
@pytest.mark.asyncio
async def test_openlibrary_search():
    conn = OpenLibraryConnector()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "docs": [
            {
                "key": "/works/OL12345W",
                "title": "Artificial Intelligence: A Modern Approach",
                "author_name": ["Stuart Russell", "Peter Norvig"],
                "first_publish_year": 1995,
                "edition_count": 28,
                "subject": ["Artificial intelligence", "Computer science"],
                "ratings_average": 4.6,
                "ratings_count": 850
            }
        ]
    }

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        diag = await conn.test_connection()
        assert diag["connected"] is True

        results = await conn.search("norvig ai")
        assert len(results) == 1
        assert results[0].source_name == "openlibrary"
        assert results[0].title == "Artificial Intelligence: A Modern Approach"
        assert results[0].source_url == "https://openlibrary.org/works/OL12345W"
        assert results[0].content_type == "book"
        assert results[0].engagement_metrics["rating"] == 4.6
