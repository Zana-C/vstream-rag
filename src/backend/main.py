"""
VisionStream Backend — FastAPI V3.0

Architectural fixes:
  A. VisionStreamAgent initialized ONCE at startup via FastAPI lifespan.
     Stored in app.state — no per-request model reloading.
  B. ChromaDB delete uses agent.delete_slide() (proper ID-based deletion).
  C. SQLite WAL mode via database.py (concurrent access, no more locks).
  G. Timestamp metadata forwarded to ChromaDB when saving slides.
"""
import os
import sys
import uuid
import asyncio
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

# Ensure project root is on sys.path once, at import time
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .database import get_db, ChatSession, ChatMessage


# ── Fix A: Lifespan — load the AI model ONCE at startup ──────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Problem solved: VisionStreamAgent.__init__() downloads and loads the
    HuggingFace 'all-MiniLM-L6-v2' embedding model into RAM. Running this
    on every HTTP request (the previous Depends(get_agent) pattern) caused
    5–15 s delays on simple GET endpoints like /api/courses.

    Solution: load once in a thread pool (non-blocking), store in app.state,
    reuse for the entire application lifetime.
    """
    print("[VisionStream] Starting up — loading AI model (first run may take 30 s)...")
    from skills.agent_logic import VisionStreamAgent
    loop = asyncio.get_event_loop()
    # Run the blocking model load in a thread pool so the event loop stays free
    # Load settings from file if exists
    import json
    settings_path = os.path.join(_PROJECT_ROOT, "workspace", "settings.json")
    provider = "ollama"
    model_name = "qwen2.5:14b"
    api_key = None
    base_url = "http://127.0.0.1:11434"
    temperature = 0.7
    max_tokens = 2048
    top_p = 0.9
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                s = json.load(f)
                provider = s.get("provider", "ollama")
                model_name = s.get("model_name", "qwen2.5:14b")
                api_key = s.get("api_key")
                base_url = s.get("base_url", "http://127.0.0.1:11434")
                temperature = s.get("temperature", 0.7)
                max_tokens = s.get("max_tokens", 2048)
                top_p = s.get("top_p", 0.9)
        except:
            pass

    app.state.agent = await loop.run_in_executor(None, lambda: VisionStreamAgent(
        provider=provider, model_name=model_name, api_key=api_key, base_url=base_url,
        temperature=temperature, max_tokens=max_tokens, top_p=top_p
    ))
    print("[VisionStream] AI model ready. All endpoints available.")
    yield
    # Shutdown cleanup
    del app.state.agent
    print("[VisionStream] Shutdown complete.")

app = FastAPI(title="VisionStream API V3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_agent():
    """Return the shared, pre-loaded agent instance. O(1), no model loading."""
    return app.state.agent


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "3.2"}

# ── Settings ──────────────────────────────────────────────────────────────────

class SettingsModel(BaseModel):
    provider: str
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = "http://127.0.0.1:11434"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9

@app.get("/api/settings")
def get_settings():
    import json
    settings_path = os.path.join(_PROJECT_ROOT, "workspace", "settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                return json.load(f)
        except:
            pass
    return {"provider": "ollama", "model_name": "qwen2.5:14b", "api_key": "", "base_url": "http://127.0.0.1:11434", "temperature": 0.7, "max_tokens": 2048, "top_p": 0.9}

@app.post("/api/settings")
def update_settings(settings: SettingsModel):
    import json
    from skills.agent_logic import VisionStreamAgent
    settings_path = os.path.join(_PROJECT_ROOT, "workspace", "settings.json")
    
    with open(settings_path, "w") as f:
        json.dump(settings.model_dump(), f)
        
    try:
        # Re-initialize the agent
        app.state.agent = VisionStreamAgent(
            provider=settings.provider,
            model_name=settings.model_name,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
        )
        return {"status": "success", "message": "Settings updated and Agent re-initialized."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Sessions (SQLite) ─────────────────────────────────────────────────────────

@app.get("/api/sessions")
def get_sessions(db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()
    return sessions


@app.post("/api/sessions")
def create_session(
    title: str = "New Chat",
    course: str = "All",
    db: Session = Depends(get_db),
):
    session_id = str(uuid.uuid4())
    new_session = ChatSession(id=session_id, title=title, course=course)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session


@app.get("/api/sessions/{session_id}/messages")
def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.id).all()
    return [{"id": m.id, "role": m.role, "content": m.content} for m in msgs]

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    # Delete the session
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return {"status": "error", "message": "Session not found"}
    # Delete associated messages
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"status": "success"}

@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db)):
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not msg:
        return {"status": "error", "message": "Message not found"}
    db.delete(msg)
    db.commit()
    return {"status": "success"}


# ── Video Processing (V3.1 Async Job Queue) ───────────────────────────────────

from fastapi import BackgroundTasks
from .database import Video, Slide

def background_process_video(video_id: str, temp_path: str, sample_rate: float, similarity_threshold: float):
    from skills.vision_utils import extract_potential_slides
    from skills.text_analysis import analyze_slides, deduplicate_by_text
    
    db = next(get_db())
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return
            
        saved_texts = []
        frames_yielded = 0
        slides_saved = 0
        
        print(f"[VisionStream] Starting extraction for video {video_id}")
        
        for slide in analyze_slides(extract_potential_slides(temp_path, sample_rate=sample_rate, similarity_threshold=similarity_threshold)):
            frames_yielded += 1
            text = slide["text"].strip()
            print(f"[VisionStream] Frame {frames_yielded} OCR Text Length: {len(text)}")
            
            if not deduplicate_by_text(saved_texts, slide["text"], threshold=similarity_threshold):
                saved_texts.append(slide["text"])
                
                short_id = f"Q_{str(uuid.uuid4()).split('-')[0].upper()}"
                
                new_slide = Slide(
                    id=short_id,
                    video_id=video_id,
                    timestamp_ms=slide.get("timestamp_ms", 0.0),
                    ocr_text=slide["text"],
                    scenario=slide.get("scenario", "unknown"),
                    original_image=slide.get("original_b64", ""),
                    warped_image=slide.get("warped_b64", ""),
                    chroma_synced=False
                )
                db.add(new_slide)
                db.commit()
                slides_saved += 1
                print(f"[VisionStream] Saved slide {short_id} for video {video_id}")
                
                video.progress = min(99, video.progress + 5)
                db.commit()
                
        video.progress = 100
        video.status = "completed"
        db.commit()
        print(f"[VisionStream] Finished video {video_id}. Total frames yielded: {frames_yielded}, slides saved: {slides_saved}")
        
    except Exception as e:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = "error"
            db.commit()
        print(f"[VisionStream] Background Task Error: {e}")
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        db.close()


@app.post("/api/video/process", status_code=202)
async def process_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    sample_rate: float = Form(1.0),
    similarity_threshold: float = Form(0.85),
    db: Session = Depends(get_db)
):
    workspace = os.path.join(_PROJECT_ROOT, "workspace")
    os.makedirs(workspace, exist_ok=True)

    video_id = str(uuid.uuid4())
    safe_name = file.filename.replace(" ", "_")
    
    temp_filename = f"{video_id}_{safe_name}"
    temp_path = os.path.join(workspace, temp_filename)

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    new_video = Video(
        id=video_id,
        filename=safe_name,
        status="processing",
        progress=0
    )
    db.add(new_video)
    db.commit()

    background_tasks.add_task(
        background_process_video,
        video_id=video_id,
        temp_path=temp_path,
        sample_rate=sample_rate,
        similarity_threshold=similarity_threshold
    )

    return {"status": "success", "job_id": video_id, "message": "Video processing started"}


@app.get("/api/jobs/{job_id}/status")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == job_id).first()
    if not video:
        return {"status": "error", "message": "Job not found"}
        
    response = {
        "job_id": video.id,
        "status": video.status,
        "progress": video.progress,
        "filename": video.filename
    }
    
    if video.status == "completed":
        slides = db.query(Slide).filter(Slide.video_id == job_id).all()
        response["slides"] = [
            {
                "id": s.id,
                "text": s.ocr_text,
                "original": s.original_image,
                "warped": s.warped_image,
                "scenario": s.scenario,
                "timestamp_ms": s.timestamp_ms
            } for s in slides
        ]
        
    return response


# ── Slides (ChromaDB via Agent) ───────────────────────────────────────────────

class SlideData(BaseModel):
    extracted_text: str
    image_path:     str = ""
    timestamp_ms:   Optional[float] = None  # Fix G: accept timestamp from frontend


class SaveSlidesRequest(BaseModel):
    course:  str
    slides:  List[SlideData]


@app.post("/api/slides/save")
def save_slides(
    request: SaveSlidesRequest,
    agent=Depends(get_agent),
):
    try:
        formatted_slides = []
        for s in request.slides:
            short_id = f"Q_{str(uuid.uuid4()).split('-')[0].upper()}"
            final_text = (
                f"[Global ID: {short_id}] [Subject: {request.course}]\n"
                + s.extracted_text
            )
            formatted_slides.append({
                "global_id":      short_id,
                "extracted_text": final_text,
                "image_path":     s.image_path,
                "timestamp_ms":   s.timestamp_ms or 0,  # Fix G
            })

        agent.add_slides(formatted_slides, course=request.course)
        return {"status": "success", "saved_count": len(formatted_slides)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/courses")
def get_courses(agent=Depends(get_agent)):
    try:
        result  = agent.collection.get(include=["metadatas"])
        courses = set()
        for meta in result.get("metadatas", []):
            if meta and "course" in meta:
                courses.add(meta["course"])
        return {"status": "success", "courses": sorted(list(courses))}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/slides")
def get_slides(course: str = "All", agent=Depends(get_agent)):
    try:
        where_filter = {"course": course} if course and course != "All" else None
        kwargs = {"include": ["metadatas", "documents"]}
        if where_filter:
            kwargs["where"] = where_filter

        result = agent.collection.get(**kwargs)

        slides = []
        for doc, meta in zip(
            result.get("documents", []), result.get("metadatas", [])
        ):
            if not meta:
                continue
            slides.append({
                "id":           meta.get("global_id", ""),
                "course":       meta.get("course", ""),
                "text":         doc,
                "timestamp_ms": meta.get("timestamp_ms", ""),
            })

        # Deduplicate by global_id (text splitter creates multiple chunks per slide)
        unique_slides = list({s["id"]: s for s in slides}.values())
        return {"status": "success", "slides": unique_slides}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/api/slides/{slide_id}")
def delete_slide(slide_id: str, agent=Depends(get_agent)):
    """
    Fix B: Delegates to agent.delete_slide() which uses the proper
    get-then-delete-by-IDs pattern, not the broken where-filter-on-delete call.
    """
    try:
        deleted = agent.delete_slide(slide_id)
        if deleted:
            return {"status": "success"}
        return {"status": "error", "message": f"Slide '{slide_id}' not found in database."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

class SlideUpdateRequest(BaseModel):
    text: str

@app.put("/api/slides/{slide_id}")
def update_slide_text(slide_id: str, request: SlideUpdateRequest, agent=Depends(get_agent)):
    try:
        updated = agent.update_slide(slide_id, request.text)
        if updated:
            return {"status": "success"}
        return {"status": "error", "message": f"Slide '{slide_id}' not found or could not be updated."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── WebSocket Chat ────────────────────────────────────────────────────────────

@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db),
):
    """
    Fix A: Agent is taken from app.state — no per-connection model loading.
    """
    await websocket.accept()
    agent = get_agent()  # Instant — just reads app.state

    try:
        while True:
            data = await websocket.receive_text()

            session = (
                db.query(ChatSession)
                .filter(ChatSession.id == session_id)
                .first()
            )
            course = session.course if session else "All"

            if session and session.title == "New Chat":
                words = data.split()
                new_title = " ".join(words[:5]) + ("..." if len(words) > 5 else "")
                session.title = new_title

            user_msg = ChatMessage(
                session_id=session_id, role="user", content=data
            )
            db.add(user_msg)
            db.commit()

            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
                .all()
            )
            chat_history = [
                {"role": m.role, "content": m.content} for m in messages[:-1]
            ]

            full_response = ""
            async for chunk in agent.ask_stream_async(
                query=data, course=course, chat_history=chat_history
            ):
                full_response += chunk
                await websocket.send_text(chunk)

            ai_msg = ChatMessage(
                session_id=session_id, role="assistant", content=full_response
            )
            db.add(ai_msg)
            db.commit()

            await websocket.send_text("[DONE]")

    except WebSocketDisconnect:
        print(f"[VisionStream] Client disconnected from session {session_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.backend.main:app", host="0.0.0.0", port=8000, reload=False)
