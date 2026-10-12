from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from zoneinfo import ZoneInfo

from script_review import ApiError, ScriptReviewService


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class ObservedClock(MutableClock):
    def __init__(self, current: datetime) -> None:
        super().__init__(current)
        self.called = threading.Event()

    def __call__(self) -> datetime:
        self.called.set()
        return self.current


class ScriptReviewServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "review.sqlite3"
        self.clock = MutableClock(datetime(2026, 10, 10, 12, tzinfo=SAO_PAULO))
        self.service = ScriptReviewService(self.database_path, self.clock)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_script(self) -> dict[str, object]:
        return self.service.create_script("creator-17", "Opening line\nSecond line")

    def request_changes(self, script_id: str, deadline: str = "2026-10-12") -> dict[str, object]:
        return self.service.review_script(
            script_id,
            "changes_requested",
            "Clarify the offer before the call to action.",
            deadline,
        )

    def test_complete_flow_keeps_old_versions_and_ends_on_approval(self) -> None:
        created = self.create_script()
        self.assertEqual("pending_review", created["state"])
        self.assertEqual(1, created["current_version"])
        self.assertEqual(["pending_review"], [version["state"] for version in created["versions"]])

        requested = self.request_changes(created["id"])
        self.assertEqual("changes_requested", requested["state"])
        self.assertEqual("open", requested["change_request"]["status"])
        self.assertEqual(["changes_requested"], [version["state"] for version in requested["versions"]])

        revised = self.service.create_version(created["id"], "Revised opening\nSame offer")
        self.assertEqual("pending_review", revised["state"])
        self.assertEqual(2, revised["current_version"])
        self.assertEqual(
            ["changes_requested", "pending_review"],
            [version["state"] for version in revised["versions"]],
        )
        self.assertEqual(
            ["Opening line\nSecond line", "Revised opening\nSame offer"],
            [version["content"] for version in revised["versions"]],
        )
        self.assertEqual(["changes_requested"], [event["decision"] for event in revised["reviews"]])

        approved = self.service.review_script(created["id"], "approved")
        self.assertEqual("approved", approved["state"])
        self.assertIsNotNone(approved["approved_at"])
        self.assertEqual(2, approved["reviews"][-1]["version"])
        self.assertEqual(
            ["changes_requested", "approved"],
            [version["state"] for version in approved["versions"]],
        )
        with self.assertRaises(ApiError) as new_version_error:
            self.service.create_version(created["id"], "A third draft")
        self.assertEqual(409, new_version_error.exception.status)
        with self.assertRaises(ApiError) as new_review_error:
            self.request_changes(created["id"])
        self.assertEqual(409, new_review_error.exception.status)
        self.assertEqual(approved["versions"], self.service.get_script(created["id"])["versions"])

    def test_invalid_unicode_is_rejected_without_changing_history(self) -> None:
        invalid = "\ud800"
        for creator, content in [(invalid, "text"), ("creator", invalid)]:
            with self.subTest(creator=repr(creator), content=repr(content)):
                with self.assertRaises(ApiError) as error:
                    self.service.create_script(creator, content)
                self.assertEqual(400, error.exception.status)
        with sqlite3.connect(self.database_path) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM scripts").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM script_versions").fetchone()[0])

        created = self.create_script()
        with self.assertRaises(ApiError) as review_error:
            self.service.review_script(created["id"], "changes_requested", invalid, "2026-10-12")
        self.assertEqual(400, review_error.exception.status)
        self.assertEqual(created, self.service.get_script(created["id"]))
        self.request_changes(created["id"])
        before = self.service.get_script(created["id"])
        with self.assertRaises(ApiError) as version_error:
            self.service.create_version(created["id"], invalid)
        self.assertEqual(400, version_error.exception.status)
        self.assertEqual(before, self.service.get_script(created["id"]))
        with self.assertRaises(ApiError) as identifier_error:
            self.service.get_script(invalid)
        self.assertEqual(400, identifier_error.exception.status)

    def test_valid_unicode_content_and_identity_are_preserved(self) -> None:
        created = self.service.create_script(" José ", "Olá 🙂")
        self.assertEqual("José", created["creator_id"])
        self.assertEqual("Olá 🙂", created["versions"][0]["content"])

    def test_change_request_requires_reason_and_valid_non_past_date(self) -> None:
        created = self.create_script()
        cases = [
            ("", "2026-10-12"),
            ("   ", "2026-10-12"),
            ("Explain the change", None),
            ("Explain the change", "2026-02-30"),
            ("Explain the change", "2026-10-09"),
        ]
        for reason, deadline in cases:
            with self.subTest(reason=reason, deadline=deadline):
                with self.assertRaises(ApiError) as error:
                    self.service.review_script(created["id"], "changes_requested", reason, deadline)
                self.assertEqual(400, error.exception.status)
                self.assertEqual("pending_review", self.service.get_script(created["id"])["state"])

    def test_inputs_must_be_strings_and_script_content_is_preserved(self) -> None:
        created = self.service.create_script(" creator-17 ", "  First line\nSecond line  ")
        self.assertEqual("creator-17", created["creator_id"])
        self.assertEqual("  First line\nSecond line  ", created["versions"][0]["content"])
        for creator, content in [(None, "text"), ("creator", 42), (" ", "text"), ("creator", "\n")]:
            with self.subTest(creator=creator, content=content):
                with self.assertRaises(ApiError) as error:
                    self.service.create_script(creator, content)
                self.assertEqual(400, error.exception.status)

    def test_local_date_not_utc_date_controls_deadline(self) -> None:
        # UTC is already the next day while São Paulo is still on the deadline date.
        self.clock.current = datetime(2026, 10, 11, 2, 59, 59, 999999, tzinfo=timezone.utc)
        created = self.create_script()
        requested = self.request_changes(created["id"], "2026-10-10")
        self.assertEqual("open", requested["change_request"]["status"])
        revised = self.service.create_version(created["id"], "Still on the local deadline")
        self.assertEqual(2, revised["current_version"])

    def test_last_instant_is_valid_and_first_instant_next_day_is_expired(self) -> None:
        self.clock.current = datetime(2026, 10, 10, 23, 59, 59, 999999, tzinfo=SAO_PAULO)
        on_time = self.create_script()
        self.request_changes(on_time["id"], "2026-10-10")
        self.assertEqual(2, self.service.create_version(on_time["id"], "On time")["current_version"])

        late = self.create_script()
        self.request_changes(late["id"], "2026-10-10")
        self.clock.current = datetime(2026, 10, 11, 0, 0, 0, tzinfo=SAO_PAULO)
        self.assertEqual("expired", self.service.get_script(late["id"])["change_request"]["status"])
        with self.assertRaises(ApiError) as error:
            self.service.create_version(late["id"], "One second too late")
        self.assertEqual(409, error.exception.status)

    def test_concurrent_version_submissions_create_only_one_next_version(self) -> None:
        created = self.create_script()
        self.request_changes(created["id"])
        barrier = threading.Barrier(2)

        def submit(content: str) -> str:
            barrier.wait()
            try:
                self.service.create_version(created["id"], content)
                return "created"
            except ApiError as error:
                return str(error.status)

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit, ("Draft A", "Draft B")))

        self.assertCountEqual(["created", "409"], outcomes)
        final = self.service.get_script(created["id"])
        self.assertEqual(2, final["current_version"])
        self.assertEqual(2, len(final["versions"]))

    def test_deadline_is_checked_after_waiting_for_the_write_transaction(self) -> None:
        created = self.create_script()
        self.request_changes(created["id"], "2026-10-10")
        clock = ObservedClock(datetime(2026, 10, 10, 23, 59, 59, 999999, tzinfo=SAO_PAULO))
        self.service.clock = clock
        blocker = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
        blocker.execute("BEGIN IMMEDIATE")
        started = threading.Event()

        def submit() -> int:
            started.set()
            try:
                self.service.create_version(created["id"], "Submitted after lock")
            except ApiError as error:
                return error.status
            return 201

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(submit)
                self.assertTrue(started.wait(timeout=1))
                self.assertFalse(clock.called.wait(timeout=0.1))
                clock.current = datetime(2026, 10, 11, 0, 0, 0, tzinfo=SAO_PAULO)
                blocker.commit()
                self.assertEqual(409, result.result(timeout=3))
        finally:
            blocker.close()

    def test_naive_clock_is_rejected(self) -> None:
        service = ScriptReviewService(
            Path(self.temporary_directory.name) / "naive.sqlite3",
            lambda: datetime(2026, 10, 10, 12),
        )
        with self.assertRaisesRegex(ValueError, "aware datetime"):
            service.create_script("creator", "text")


if __name__ == "__main__":
    unittest.main()
