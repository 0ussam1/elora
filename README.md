# ELORA — AI-Powered Multi-Source Search Engine

> *"Whatever you're looking for, we'll find a way."*

ELORA is an AI-powered multi-source intelligence and research platform designed to search across technical communities, academic literature, web search engines, knowledge bases, and developer repositories simultaneously. It deduplicates records, normalizes citations, ranks evidence transparently, and presents unified intelligence reports with zero hallucinations and full source traceability.

---

## 🌟 Key Features

### 1. Modular Multi-Source Connectors (12 Engines)
- **Web Search**: DuckDuckGo compliant web search endpoint.
- **Wikipedia**: Encyclopedic background knowledge and summaries.
- **Hacker News**: Algolia Search API for technical discussions, community sentiment, and comments.
- **GitHub**: Search across public issues, discussions, and repositories.
- **Stack Overflow / Stack Exchange**: Filtered technical questions, answers, and score metrics.
- **arXiv**: Academic paper preprints with XML Atom metadata parsing.
- **OpenAlex**: Global scholarly works, citation counts, open-access status, and author metadata.
- **Crossref**: Direct scholarly DOI metadata via the polite pool API.
- **Internet Archive**: Books, media, archived documents, and metadata endpoints.
- **Open Library**: Curated book records, authors, subjects, and editions.
- **Reddit**: Compliant OAuth integration with diagnostic health status monitoring.
- **Kaggle**: Dataset metadata search and exploration.

### 2. Evidence-Grounded Pipeline
- **Normalization**: Canonical URL resolution, parameter sanitization, whitespace scrubbing, and structured schema mapping.
- **Deduplication**: Exact canonical URL matching and normalized title matching across platforms.
- **Transparent Ranking**: TF-IDF cosine similarity, query token overlap, and engagement weight bonuses.
- **Research Modes**:
  - `General Research`: Balanced discovery across active web and knowledge sources.
  - `Technical Research`: Prioritizes GitHub code, Stack Overflow, Kaggle, arXiv, and academic papers.
  - `Problem Discovery (Deep Research)`: Boosts pain points, bug tickets, and complaints.

### 3. Traceable Report Generation
- Synthesizes findings, recurring problem patterns, existing solutions, and market opportunities.
- **Zero Hallucination Guarantee**: Every claim directly references concrete source IDs and URLs.

### 4. Modern UI & Data Export
- React 19 + TypeScript + Vite + Tailwind CSS with a clean, dark SaaS aesthetic.
- Search-first homepage with fast filters and mode shortcuts.
- Full operational dashboard with real-time progress tracking and metrics.
- One-click CSV and JSON data export.
- Diagnostic connector testing directly from the interface.

---

## 🛠️ Tech Stack

- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4, Lucide Icons, Axios.
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, Uvicorn.
- **Database**: SQLite (local) / PostgreSQL ready.
- **Algorithms**: scikit-learn (TF-IDF cosine similarity), async parallel coordination (`asyncio`).

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+
- Node.js 20+ and npm

### 2. Backend Setup
```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

#### Optional: Configure API Keys
Copy `.env.example` to `.env` in the `backend` folder:
```bash
cp ../.env.example .env
```
*(The engine works out-of-the-box with open sources even without optional API keys).*

Start the FastAPI server:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Docs: `http://127.0.0.1:8000/docs`

### 3. Frontend Setup
In a new terminal:
```bash
cd frontend
npm install
npm run dev
```
- Interface: `http://localhost:5173`

---

## 🔒 Security & Compliance

- Official APIs and compliant endpoints used.
- Sensitive credentials loaded strictly from environment variables and never exposed to the frontend or logs.
- SQLite database, `.env`, and caches excluded from version control.

---

## 📄 License

MIT License.
