"""
Background worker entrypoint.

Run locally (from api/):  .venv/bin/python worker.py
Processes BACKGROUND_JOBS (simulation_run, pdf_generation,
strategy_evaluation) until interrupted.

On Cloud Run the worker deploys as a service, and services must accept
connections on $PORT — when PORT is set, a stdlib HTTP listener answers
health checks with 200 while the job loop runs in the main thread.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

load_dotenv()

from services.background_worker import run_worker


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # health probes would flood the job logs


def _start_health_server(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


if __name__ == "__main__":
    port = os.getenv("PORT")
    if port:
        _start_health_server(int(port))
    run_worker()
