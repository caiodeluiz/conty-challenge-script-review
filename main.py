from http.server import ThreadingHTTPServer
import os
from pathlib import Path

from script_review import ScriptReviewService
from script_review.http_api import make_handler


def main() -> None:
    root = Path(__file__).resolve().parent
    database_path = Path(os.environ.get("SCRIPT_REVIEW_DB", root / "data" / "review.sqlite3"))
    port = int(os.environ.get("PORT", "8000"))
    service = ScriptReviewService(database_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(service))
    print(f"Script review API listening at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
