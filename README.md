# VisionStream AI (vstream-rag)

VisionStream is an intelligent RAG (Retrieval-Augmented Generation) platform designed to extract, index, and query text from educational videos and slides. 

## Key Features

- **Video Processing & OCR**: Automatically extracts frames from uploaded videos, deduplicates them (via dHash), and uses EasyOCR to extract textual content.
- **RAG Architecture**: Integrates deeply with **ChromaDB** using `paraphrase-multilingual-MiniLM-L12-v2` embeddings for fast, multilingual document retrieval via MMR (Maximal Marginal Relevance) search.
- **Multi-Model Support**: Chat with your slides using your preferred LLM provider:
  - **Ollama** (Local execution, e.g., `qwen2.5:14b`)
  - **OpenAI** (e.g., `gpt-4o`)
  - **Google Gemini** (e.g., `gemini-1.5-pro`)
- **Interactive Chat Interface**: A modern chat UI with session memory, auto-titling based on conversation context, and message management.
- **Database Manager**: Directly view, search, and inline-edit OCR-extracted texts. Edits are automatically synced and re-embedded into the ChromaDB vector space.

## Architecture

- **Backend**: FastAPI (Python), SQLAlchemy (SQLite WAL mode for concurrency), ChromaDB.
- **Frontend**: React (Vite), Tailwind CSS, Lucide Icons, React Router.
- **Background Tasks**: Non-blocking async video processing and slide indexing.

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js & npm
- [Ollama](https://ollama.com/) (Optional, for local LLMs)

### Backend Setup
1. Create a virtual environment and install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install langchain-google-genai # For Gemini support
   ```
2. Run the FastAPI server:
   ```bash
   python -m uvicorn src.backend.main:app --reload
   ```

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd src/frontend
   ```
2. Install dependencies and start the dev server:
   ```bash
   npm install
   npm run dev
   ```

### Settings Configuration
Once the frontend is running, navigate to the Chat interface and click the Settings icon to configure your LLM provider and API keys.
