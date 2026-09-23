"""The SSE feed must end on its own: an endless response blocks uvicorn's
graceful shutdown, which froze the whole API on every --reload."""

import threading
import time
import http.client

import uvicorn

from app.api.v1.endpoints import alerts
from app.main import app


def test_alert_stream_ends_and_does_not_block_shutdown(monkeypatch):
    monkeypatch.setattr(alerts, "STREAM_LIFETIME_S", 1)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8767, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.1)
    assert server.started

    conn = http.client.HTTPConnection("127.0.0.1", 8767, timeout=10)
    conn.request("GET", "/api/v1/alerts/stream")
    response = conn.getresponse()
    assert response.status == 200
    first = response.read1(200).decode()
    assert "retry:" in first and '"hello"' in first

    server.should_exit = True  # what Ctrl+C / --reload does
    thread.join(timeout=15)
    assert not thread.is_alive(), "graceful shutdown hung on the open alert stream"
