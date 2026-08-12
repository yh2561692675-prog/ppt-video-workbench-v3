from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

from scripts.performance_startup_probe import main


def _free_port() -> int:
    with socket.socket() as socket_handle:
        socket_handle.bind(("127.0.0.1", 0))
        return int(socket_handle.getsockname()[1])


def _health_server(path: Path) -> None:
    path.write_text(
        """from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == \"/health\" else 404)
        self.end_headers()

    def log_message(self, format, *args):
        return


ThreadingHTTPServer((\"127.0.0.1\", int(sys.argv[1])), HealthHandler).serve_forever()
""",
        encoding="utf-8",
    )


def test_startup_probe_records_successful_health_stage(tmp_path: Path) -> None:
    server = tmp_path / "health_server.py"
    _health_server(server)
    output = tmp_path / "evidence"
    port = _free_port()

    result = main(
        [
            "--output",
            str(output),
            "--temporary-root",
            str(tmp_path),
            "--health-url",
            f"http://127.0.0.1:{port}/health",
            "--timeout",
            "5",
            "--interval",
            "1",
            "--command",
            sys.executable,
            str(server),
            str(port),
        ]
    )

    assert result == 0
    summary_path = next(output.glob("*-summary.json"))
    events_path = next(output.glob("*.jsonl"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert summary["sample_count"] >= 2
    assert summary["roots"] == {"api": summary["roots"]["api"], "probe": summary["roots"]["probe"]}
    assert "launcher" not in summary["roots"]
    assert [event["event"] for event in summary["stage_events"]] == ["started", "finished"]
    assert events[-1]["type"] == "session_finished"
