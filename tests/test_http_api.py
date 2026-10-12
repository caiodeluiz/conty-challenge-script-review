from datetime import datetime
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from script_review import ScriptReviewService
from script_review.http_api import make_handler


class ScriptReviewHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        service = ScriptReviewService(
            Path(self.temporary_directory.name) / "api.sqlite3",
            lambda: datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self.temporary_directory.cleanup()

    def request(self, method: str, path: str, payload: object | None = None) -> tuple[int, dict[str, object]]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data is not None else {},
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def test_http_workflow_and_error_response(self) -> None:
        status, body = self.request("POST", "/scripts", {"creator_id": "c-1", "content": "Draft one"})
        self.assertEqual(201, status)
        script = body["script"]
        script_id = script["id"]
        self.assertEqual("pending_review", script["state"])

        status, body = self.request(
            "POST",
            f"/scripts/{script_id}/reviews",
            {"decision": "changes_requested", "reason": "Name the audience", "deadline_date": "2026-10-12"},
        )
        self.assertEqual(200, status)
        self.assertEqual("changes_requested", body["script"]["state"])

        status, body = self.request(
            "POST", f"/scripts/{script_id}/versions", {"content": "Draft two"}
        )
        self.assertEqual(201, status)
        self.assertEqual(["Draft one", "Draft two"], [item["content"] for item in body["script"]["versions"]])

        status, body = self.request("POST", f"/scripts/{script_id}/reviews", {"decision": "approved"})
        self.assertEqual(200, status)
        self.assertEqual("approved", body["script"]["state"])

        status, body = self.request(
            "POST", f"/scripts/{script_id}/versions", {"content": "Must be rejected"}
        )
        self.assertEqual(409, status)
        self.assertEqual("invalid_state", body["error"]["code"])

        status, body = self.request("GET", f"/scripts/{script_id}")
        self.assertEqual(200, status)
        self.assertEqual("approved", body["script"]["state"])
        self.assertEqual(2, len(body["script"]["reviews"]))

    def test_malformed_json_and_non_object_body_are_rejected(self) -> None:
        request = Request(
            self.base_url + "/scripts",
            data=b"not json",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)
        self.assertEqual(400, error.exception.code)
        error.exception.close()

        status, body = self.request("POST", "/scripts", ["not", "an", "object"])
        self.assertEqual(400, status)
        self.assertEqual("invalid_body", body["error"]["code"])

    def test_isolated_surrogate_returns_400_through_http(self) -> None:
        for payload, field in (
            ({"creator_id": "creator", "content": "\ud800"}, "content"),
            ({"creator_id": "\ud800", "content": "Draft"}, "creator_id"),
        ):
            with self.subTest(field=field):
                status, body = self.request("POST", "/scripts", payload)
                self.assertEqual(400, status)
                self.assertEqual("invalid_" + field, body["error"]["code"])

        status, body = self.request("POST", "/scripts", {"creator_id": "creator", "content": "Draft"})
        self.assertEqual(201, status)
        script_id = body["script"]["id"]
        status, body = self.request(
            "POST", f"/scripts/{script_id}/reviews",
            {"decision": "changes_requested", "reason": "\ud800", "deadline_date": "2026-10-12"},
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_reason", body["error"]["code"])
        status, body = self.request("GET", f"/scripts/{script_id}")
        self.assertEqual(200, status)
        self.assertEqual("pending_review", body["script"]["versions"][0]["state"])
        self.assertEqual([], body["script"]["reviews"])


if __name__ == "__main__":
    unittest.main()
