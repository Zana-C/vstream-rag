import pytest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.backend.main import app

def test_health():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": "3.1"}

def test_get_courses():
    with TestClient(app) as client:
        response = client.get("/api/courses")
        assert response.status_code == 200
        assert "courses" in response.json()
        assert response.json()["status"] == "success"

def test_get_slides():
    with TestClient(app) as client:
        response = client.get("/api/slides?course=All")
        assert response.status_code == 200
        assert "slides" in response.json()
        assert response.json()["status"] == "success"

def test_create_and_get_session():
    with TestClient(app) as client:
        response = client.post("/api/sessions?title=TestSession&course=All")
        assert response.status_code == 200
        session_id = response.json()["id"]
        assert session_id is not None
        
        response = client.get("/api/sessions")
        assert response.status_code == 200
        sessions = response.json()
        assert any(s["id"] == session_id for s in sessions)

def test_save_slide():
    with TestClient(app) as client:
        payload = {
            "course": "AutomatedTestCourse",
            "slides": [
                {"extracted_text": "This is an automated test slide.", "image_path": ""}
            ]
        }
        response = client.post("/api/slides/save", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["saved_count"] == 1

def test_get_courses_after_save():
    with TestClient(app) as client:
        response = client.get("/api/courses")
        assert response.status_code == 200
        assert "AutomatedTestCourse" in response.json()["courses"]

def test_get_slides_by_course():
    with TestClient(app) as client:
        response = client.get("/api/slides?course=AutomatedTestCourse")
        assert response.status_code == 200
        slides = response.json()["slides"]
        assert len(slides) > 0
        assert "This is an automated test slide." in slides[0]["text"]

def test_delete_slide():
    with TestClient(app) as client:
        response = client.get("/api/slides?course=AutomatedTestCourse")
        slides = response.json()["slides"]
        if len(slides) > 0:
            slide_id = slides[0]["id"]
            
            del_response = client.delete(f"/api/slides/{slide_id}")
            assert del_response.status_code == 200
            assert del_response.json()["status"] == "success"
            
            # Verify it is deleted
            response2 = client.get("/api/slides?course=AutomatedTestCourse")
            slides2 = response2.json()["slides"]
            assert not any(s["id"] == slide_id for s in slides2)

def test_get_slides_none_course():
    with TestClient(app) as client:
        # Simulate course=None or missing course param (defaults to All)
        response = client.get("/api/slides")
        assert response.status_code == 200
        assert "slides" in response.json()

def test_invalid_save_payload():
    with TestClient(app) as client:
        # Test missing fields
        payload = {
            "course": "BadCourse"
        }
        response = client.post("/api/slides/save", json=payload)
        # FastAPI should reject invalid schema with 422
        assert response.status_code == 422

def test_websocket_chat():
    with TestClient(app) as client:
        # Override the agent stream locally
        async def mock_stream(*args, **kwargs):
            yield "Hello"
            yield " World"
            
        app.state.agent.ask_stream_async = mock_stream

        # Create session first
        res = client.post("/api/sessions?title=WSTest&course=All")
        session_id = res.json()["id"]
        
        with client.websocket_connect(f"/ws/chat/{session_id}") as websocket:
            websocket.send_text("Hello AI")
            data1 = websocket.receive_text()
            assert data1 == "Hello"
            data2 = websocket.receive_text()
            assert data2 == " World"
            data3 = websocket.receive_text()
            assert data3 == "[DONE]"
