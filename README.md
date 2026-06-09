# VisionStream AI (vstream-rag)

VisionStream is an intelligent RAG (Retrieval-Augmented Generation) platform designed to extract, index, and query text from educational videos and slides.

## Key Features

- **Video Processing & OCR**: Automatically extracts frames from uploaded videos, deduplicates them (via dHash), and uses EasyOCR to extract textual content. Includes a two-path preprocessing pipeline that applies different contrast normalization strategies for projection vs. screen-recording scenarios.
- **RAG Architecture**: Integrates deeply with **ChromaDB** using `paraphrase-multilingual-MiniLM-L12-v2` embeddings for fast, multilingual document retrieval via MMR (Maximal Marginal Relevance) search.
- **Multi-Model Support**: Chat with your slides using your preferred LLM provider:
  - **Ollama** (Local execution, e.g., `qwen2.5:14b`) — configurable server URL (default: `http://127.0.0.1:11434`)
  - **OpenAI** (e.g., `gpt-4o`)
  - **Google Gemini** (e.g., `gemini-2.5-flash`)
- **Configurable AI Parameters**: Temperature, Top P, and Max Tokens are all adjustable from the Settings panel with a one-click reset to defaults.
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
   ```
2. Run the FastAPI server from the project root:
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
Once the frontend is running, navigate to the Chat interface and click the **Settings (⚙)** icon to configure:
- **LLM Provider**: Ollama, OpenAI, or Google Gemini
- **Model Name**: e.g. `qwen2.5:14b`, `gpt-4o`, `gemini-2.5-flash`
- **Ollama Server URL**: Customize the port if Ollama runs on a non-default address
- **API Key**: Required for OpenAI and Gemini providers
- **AI Parameters**: Temperature, Top P, Max Tokens

> **Note:** API keys are stored only in `workspace/settings.json` (excluded from git via `.gitignore`) and are never committed to the repository.
