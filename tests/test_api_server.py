"""Tests for api_server.py."""
from fastapi.testclient import TestClient
from jarvis.api_server import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "JARVIS API" in response.json()["message"]


def test_task_unauthorized():
    response = client.post("/task", json={"task": "hello"})
    assert response.status_code == 401
