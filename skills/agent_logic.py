"""
agent_logic.py — VisionStreamAgent with Native ChromaDB + MMR + Multilingual Embeddings.

Tier 2 changes:
  - Switched to paraphrase-multilingual-MiniLM-L12-v2 for multilingual support.
  - Native chromadb.PersistentClient instead of Langchain's Chroma wrapper.
  - Implemented MMR (Maximal Marginal Relevance) retrieval logic manually.
  - LCEL-style prompt execution.
"""
import os
import numpy as np
from typing import Optional, Dict, Any, List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.documents import Document

from langchain_core.documents import Document

try:
    from langchain_ollama import OllamaLLM as _OllamaClass
except ImportError:
    try:
        from langchain_community.llms import Ollama as _OllamaClass  # type: ignore
    except ImportError:
        _OllamaClass = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

import chromadb

# ── Absolute paths ────────────────────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_WORKSPACE    = os.path.join(_PROJECT_ROOT, "workspace")
_CHROMA_DIR   = os.path.join(_WORKSPACE, "chroma_db")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Calculate cosine similarity between a vector and a matrix."""
    return np.dot(a, b.T) / (np.linalg.norm(a) * np.linalg.norm(b, axis=1) + 1e-10)


def maximal_marginal_relevance(
    query_embedding: np.ndarray,
    embedding_list: list,
    lambda_mult: float = 0.5,
    k: int = 4
) -> List[int]:
    """Calculate MMR and return the indices of selected documents."""
    if min(k, len(embedding_list)) <= 0:
        return []
    if k >= len(embedding_list):
        return list(range(len(embedding_list)))

    embeddings = np.array(embedding_list)
    query_embedding = np.array(query_embedding)
    
    similarity_to_query = cosine_similarity(query_embedding, embeddings)
    
    most_similar = int(np.argmax(similarity_to_query))
    idxs = [most_similar]
    selected = [embeddings[most_similar]]
    
    while len(idxs) < k:
        best_score = -np.inf
        idx_to_add = -1
        
        sims_to_query = similarity_to_query
        sims_to_selected = cosine_similarity(embeddings, np.array(selected))
        max_sim_to_selected = np.max(sims_to_selected, axis=1)
        
        for i in range(len(embeddings)):
            if i in idxs:
                continue
            
            # MMR Equation
            score = lambda_mult * sims_to_query[i] - (1 - lambda_mult) * max_sim_to_selected[i]
            if score > best_score:
                best_score = score
                idx_to_add = i
                
        idxs.append(idx_to_add)
        selected.append(embeddings[idx_to_add])
        
    return idxs


class VisionStreamAgent:
    def __init__(
        self,
        provider: str = "ollama",       # "ollama", "openai", "gemini"
        model_name: str = "qwen2.5:14b",
        api_key: Optional[str] = None,
        base_url: Optional[str] = "http://127.0.0.1:11434",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
    ):
        self.provider    = provider
        self.model_name  = model_name
        self.api_key     = api_key
        self.base_url    = base_url
        self.temperature = temperature
        self.max_tokens  = max_tokens
        self.top_p       = top_p

        os.makedirs(_CHROMA_DIR, exist_ok=True)

        # ── Embeddings (Fixed to paraphrase-multilingual-MiniLM-L12-v2 for compatibility) ──
        self.embeddings = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")

        # ── Native ChromaDB Client ─────────────────────────────────────────────
        self.chroma_client = chromadb.PersistentClient(path=_CHROMA_DIR)
        self.collection = self.chroma_client.get_or_create_collection(name="visionstream")

        # ── LLM ───────────────────────────────────────────────────────────────
        if self.provider == "ollama":
            if _OllamaClass is None:
                raise ImportError("Ollama LLM package not found.")
            self.llm = _OllamaClass(
                model=self.model_name,
                base_url=self.base_url,
                temperature=self.temperature,
                num_predict=self.max_tokens,
            )
        elif self.provider == "openai":
            if not self.api_key:
                raise ValueError("API key required for OpenAI.")
            os.environ["OPENAI_API_KEY"] = self.api_key
            self.llm = ChatOpenAI(
                model=self.model_name or "gpt-4o",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
            )
        elif self.provider == "gemini":
            if ChatGoogleGenerativeAI is None:
                raise ImportError("langchain-google-genai package not found. pip install langchain-google-genai")
            if not self.api_key:
                raise ValueError("API key required for Gemini.")
            os.environ["GOOGLE_API_KEY"] = self.api_key
            
            gemini_model = (self.model_name or "").strip()
            if not gemini_model or "1.5" in gemini_model:
                gemini_model = "gemini-2.5-flash"
                
            if gemini_model.startswith("models/"):
                gemini_model = gemini_model.replace("models/", "")
                
            self.llm = ChatGoogleGenerativeAI(
                model=gemini_model,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
                top_p=self.top_p,
            )
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    # ── Slide Ingestion ───────────────────────────────────────────────────────

    def add_slides(self, slides_data: List[Dict[str, Any]], course: str) -> None:
        """
        Ingest extracted slides into native ChromaDB.
        """
        docs = []
        for item in slides_data:
            text = item.get("extracted_text", "").strip()
            if not text:
                continue
            docs.append(Document(
                page_content=text,
                metadata={
                    "source":       item.get("image_path", ""),
                    "global_id":    item.get("global_id", ""),
                    "course":       course,
                    "timestamp_ms": str(item.get("timestamp_ms", "")),
                },
            ))

        if not docs:
            return

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        splits = text_splitter.split_documents(docs)

        texts = [s.page_content for s in splits]
        metadatas = [s.metadata for s in splits]
        ids = [f"{m.get('global_id', 'unknown')}__chunk{i}" for i, m in enumerate(metadatas)]
        
        # Batch embedding
        embedded_docs = self.embeddings.embed_documents(texts)

        self.collection.upsert(
            documents=texts,
            embeddings=embedded_docs,
            metadatas=metadatas,
            ids=ids
        )

    # ── Slide Deletion ────────────────────────────────────────────────────────

    def delete_slide(self, global_id: str) -> bool:
        """
        Delete ALL chunks belonging to a global_id using Native Chroma.
        """
        try:
            result = self.collection.get(where={"global_id": global_id})
            ids_to_delete = result.get("ids", [])
            if not ids_to_delete:
                return False
            self.collection.delete(ids=ids_to_delete)
            return True
        except Exception as exc:
            print(f"[VisionStream] delete_slide({global_id}) failed: {exc}")
            return False

    def update_slide(self, global_id: str, new_text: str) -> bool:
        """
        Update the text of a specific slide in ChromaDB.
        Since we chunk slides, we actually delete and re-insert.
        """
        try:
            # 1. Fetch old metadata to preserve it
            result = self.collection.get(where={"global_id": global_id}, include=["metadatas"])
            if not result or not result.get("metadatas"):
                return False
            
            # Extract common metadata (like course, timestamp, source) from first chunk
            old_metadata = result["metadatas"][0]
            
            # 2. Delete all existing chunks for this slide
            self.delete_slide(global_id)
            
            # 3. Add back the updated text
            self.add_slides([{
                "global_id": global_id,
                "extracted_text": new_text,
                "image_path": old_metadata.get("source", ""),
                "timestamp_ms": float(old_metadata.get("timestamp_ms", "0.0")),
            }], course=old_metadata.get("course", "All"))
            
            return True
        except Exception as exc:
            print(f"[VisionStream] update_slide({global_id}) failed: {exc}")
            return False

    # ── RAG: MMR Search ───────────────────────────────────────────────────────

    async def ask_stream_async(
        self,
        query: str,
        course: str = "All",
        chat_history: list = None,
    ):
        """
        Async generator for streaming LLM responses over WebSockets using MMR.
        """
        where_clause = {}
        if course and course != "All":
            where_clause = {"course": course}

        # Embed query
        query_emb = self.embeddings.embed_query(query)

        # Fetch K=20 for MMR
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=20,
            where=where_clause if where_clause else None,
            include=["embeddings", "documents", "metadatas"]
        )
        
        context_texts = []
        if results and results["ids"] and len(results["ids"][0]) > 0:
            doc_embeddings = results["embeddings"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            
            # Apply MMR to select 5
            selected_idxs = maximal_marginal_relevance(
                query_emb,
                doc_embeddings,
                lambda_mult=0.5,
                k=5
            )
            
            for idx in selected_idxs:
                m = metadatas[idx]
                d = documents[idx]
                context_texts.append(
                    f"[ID: {m.get('global_id', '?')}] [t={m.get('timestamp_ms', '?')}ms]\n{d}"
                )
                
        context = "\n\n---\n\n".join(context_texts) if context_texts else "No context found."

        # ── History ───────────────────────────────────────────────────────────
        history_text = ""
        if chat_history:
            history_text = "Recent conversation:\n"
            for msg in chat_history[-6:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history_text += f"{role}: {msg['content']}\n"
            history_text += "\n"

        # ── Prompt ────────────────────────────────────────────────────────────
        course_label = course if course and course != "All" else "all courses"
        prompt = f"""You are an AI assistant helping students review lecture slides.
Course filter: {course_label}

Retrieved slide context (most relevant chunks):
{context}

{history_text}Student question: {query}

Instructions:
- Answer based on the retrieved context above.
- Answer in the same language as the Student question.
- If you reference a specific slide, mention its Global ID (e.g. Q_XXXX).
- If the context does not contain enough information, say so clearly.
Answer:"""

        yield "*(Searching slides...)*\n\n"

        import asyncio

        if hasattr(self.llm, "astream"):
            async for chunk in self.llm.astream(prompt):
                yield chunk.content if hasattr(chunk, "content") else str(chunk)
        else:
            for chunk in self.llm.stream(prompt):
                yield chunk.content if hasattr(chunk, "content") else str(chunk)
                await asyncio.sleep(0.01)
