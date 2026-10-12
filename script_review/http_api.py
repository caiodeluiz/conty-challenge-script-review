from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import unquote, urlsplit

from .service import ApiError, ScriptReviewService


MAX_BODY_BYTES = 1_048_576


def make_handler(service: ScriptReviewService) -> type[BaseHTTPRequestHandler]:
    class ScriptReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            try:
                path = [unquote(part) for part in urlsplit(self.path).path.split("/") if part]
                if method == "GET" and path == ["health"]:
                    self._send(200, {"status": "ok"})
                elif method == "POST" and path == ["scripts"]:
                    body = self._read_json()
                    script = service.create_script(body.get("creator_id"), body.get("content"))
                    self._send(201, {"script": script})
                elif len(path) == 2 and path[0] == "scripts" and method == "GET":
                    self._send(200, {"script": service.get_script(path[1])})
                elif len(path) == 3 and path[0] == "scripts" and method == "POST":
                    body = self._read_json()
                    if path[2] == "reviews":
                        script = service.review_script(
                            path[1], body.get("decision"), body.get("reason"), body.get("deadline_date")
                        )
                        self._send(200, {"script": script})
                    elif path[2] == "versions":
                        script = service.create_version(path[1], body.get("content"))
                        self._send(201, {"script": script})
                    else:
                        raise ApiError(404, "route_not_found", "Route not found")
                else:
                    raise ApiError(404, "route_not_found", "Route not found")
            except ApiError as error:
                self._send(error.status, {"error": {"code": error.code, "message": error.message}})
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"error": {"code": "invalid_json", "message": "Request body must be JSON"}})
            except Exception:
                self._send(500, {"error": {"code": "internal_error", "message": "Internal server error"}})

        def _read_json(self) -> dict[str, object]:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None or not raw_length.isdecimal():
                raise ApiError(400, "invalid_content_length", "A valid Content-Length is required")
            length = int(raw_length)
            if length > MAX_BODY_BYTES:
                raise ApiError(413, "body_too_large", "Request body exceeds one megabyte")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ApiError(400, "invalid_body", "Request body must be a JSON object")
            return body

        def _send(self, status: int, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ScriptReviewHandler
