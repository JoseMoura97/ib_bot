from __future__ import annotations


def test_plot_data_refresh_returns_task_id(client, monkeypatch):
    from app.api.routes import plot_data as plot_routes

    class FakeAsyncResult:
        id = "abc123"

    monkeypatch.setattr(plot_routes.celery_app, "send_task", lambda *args, **kwargs: FakeAsyncResult())

    res = client.post("/plot-data/refresh?force=true&max_age_hours=0")
    assert res.status_code == 200
    assert res.json()["queued"] is True
    assert res.json()["task_id"] == "abc123"


def test_plot_data_refresh_status_reports_state(client, monkeypatch):
    from app.api.routes import plot_data as plot_routes

    class FakeResult:
        state = "SUCCESS"
        result = None

    monkeypatch.setattr(plot_routes.celery_app, "AsyncResult", lambda task_id: FakeResult())

    res = client.get("/plot-data/refresh/abc123")
    assert res.status_code == 200
    data = res.json()
    assert data["task_id"] == "abc123"
    assert data["state"] == "SUCCESS"
