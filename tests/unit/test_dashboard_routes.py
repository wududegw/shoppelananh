from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agent.api import dashboard


def test_spa_routes_serve_same_entry_without_swallowing_api(monkeypatch, tmp_path):
    (tmp_path / 'index.html').write_text('<div id="root">dashboard</div>')
    monkeypatch.setattr(dashboard, 'DIST', tmp_path)
    app = FastAPI()
    app.include_router(dashboard.router)
    client = TestClient(app)
    for route in ['/', '/studio', '/projects', '/projects/test-project', '/gallery', '/logs', '/guide', '/settings']:
        response = client.get(route)
        assert response.status_code == 200
        assert 'id="root"' in response.text
        assert response.headers['cache-control'] == 'no-cache'
    assert client.get('/api/unknown').status_code == 404


def test_missing_build_reports_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, 'DIST', tmp_path)
    app = FastAPI()
    app.include_router(dashboard.router)
    response = TestClient(app).get('/')
    assert response.status_code == 503
    assert 'npm run build' in response.json()['detail']
