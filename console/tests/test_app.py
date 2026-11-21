"""Отдача страниц консоли и ролевых страниц."""
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_index_serves_console():
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.text
    assert "Консоль оператора" in text
    assert "/api/orders/" in text
    assert "/api/coordinator/" in text
    assert "data-handle=\"coordinate\"" in text
    assert "id=\"autoPlan\"" in text
    assert "/api/coordinator/auto/coordinate" in text


def test_role_pages_served():
    cases = {
        "/kitchen": ["Кухня", "auto/kitchen/dishes", "dish/ready"],
        "/assembly": ["Сборка", "order/ready"],
        "/courier": ["Курьеры", "/courier/"],
        "/courier/7": ["Курьер", "auto/courier/", "setAvailable", "Я на точке",
                       "order/attach", "order/pickup", "order/finish"],
    }
    for path, markers in cases.items():
        resp = client.get(path)
        assert resp.status_code == 200, path
        for marker in markers:
            assert marker in resp.text, (path, marker)


def test_static_assets_served():
    assert client.get("/static/role.js").status_code == 200
    assert client.get("/static/role.css").status_code == 200
