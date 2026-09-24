"""Serve the built PWA, ingested data, and capture/ingest API."""

from __future__ import annotations

import json
import threading
import uuid
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from encoding_remover.ingest import capture_and_ingest


def resolve_web_root(repo_root: Path) -> Path:
    dist = repo_root / "web" / "dist"
    if dist.is_dir() and (dist / "index.html").exists():
        return dist
    raise FileNotFoundError(
        "Built PWA not found. Run: cd web && npm install && npm run build"
    )


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 4173,
    open_browser: bool = True,
    repo_root: Path | None = None,
) -> None:
    root = (repo_root or Path.cwd()).resolve()
    web_root = resolve_web_root(root)
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    jobs: dict[str, dict[str, Any]] = {}
    jobs_lock = threading.Lock()
    capture_lock = threading.Lock()

    def start_job(query: str, include_preferred_terms: bool) -> str:
        job_id = uuid.uuid4().hex[:12]
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id,
                "query": query,
                "status": "running",
                "message": f"Fetching {query} from VigiAccess…",
            }

        def worker() -> None:
            try:
                with capture_lock:
                    with jobs_lock:
                        jobs[job_id]["message"] = (
                            f"Capturing {query} (this can take a few minutes)…"
                        )
                    entry = capture_and_ingest(
                        query,
                        data_dir,
                        include_preferred_terms=include_preferred_terms,
                    )
                with jobs_lock:
                    jobs[job_id].update(
                        {
                            "status": "done",
                            "message": f"Ingested {entry['name']}",
                            "entry": entry,
                        }
                    )
            except Exception as exc:  # noqa: BLE001 — surface to UI
                with jobs_lock:
                    jobs[job_id].update(
                        {
                            "status": "error",
                            "message": str(exc),
                            "error": str(exc),
                        }
                    )

        threading.Thread(target=worker, daemon=True, name=f"ingest-{job_id}").start()
        return job_id

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def _json(self, code: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            if not raw:
                return {}
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def do_OPTIONS(self):  # noqa: N802
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                return
            self.send_error(404)

        def do_POST(self):  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/ingest":
                try:
                    body = self._read_json()
                    query = str(body.get("query") or "").strip()
                    if not query:
                        self._json(400, {"error": "query is required"})
                        return
                    if len(query) > 120:
                        self._json(400, {"error": "query too long"})
                        return
                    include_pts = bool(body.get("include_preferred_terms", True))
                    job_id = start_job(query, include_pts)
                    self._json(
                        202,
                        {
                            "job_id": job_id,
                            "status": "running",
                            "message": f"Started ingest for {query}",
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    self._json(400, {"error": str(exc)})
                return
            self.send_error(404)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path.startswith("/api/ingest/"):
                job_id = path[len("/api/ingest/") :].strip("/")
                with jobs_lock:
                    job = jobs.get(job_id)
                if not job:
                    self._json(404, {"error": "job not found"})
                    return
                self._json(200, job)
                return

            if path == "/data" or path.startswith("/data/"):
                rel = path[len("/data") :].lstrip("/")
                target = (data_dir / rel).resolve()
                if not str(target).startswith(str(data_dir.resolve())):
                    self.send_error(403)
                    return
                if target.is_dir() or not target.is_file():
                    self.send_error(404)
                    return
                try:
                    payload = target.read_bytes()
                except OSError:
                    self.send_error(404)
                    return
                ctype = (
                    "application/json"
                    if target.suffix == ".json"
                    else "application/octet-stream"
                )
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(payload)
                return
            return super().do_GET()

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with ThreadingServer((host, port), Handler) as httpd:
        url = f"http://{host}:{port}/"
        print(f"Serving PWA from {web_root}", flush=True)
        print(f"Data from {data_dir}", flush=True)
        print(f"API POST /api/ingest  GET /api/ingest/{{job_id}}", flush=True)
        print(f"Open {url}", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
