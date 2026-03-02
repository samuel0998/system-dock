import unittest
from datetime import timezone

from api.upload import _to_utc_aware, _status_do_sistema


class UploadTimeParsingTests(unittest.TestCase):
    def test_brt_string_is_converted_to_utc(self):
        dt = _to_utc_aware("2026/03/01 08:00 BRT")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.isoformat(), "2026-03-01T11:00:00+00:00")

    def test_naive_string_is_treated_as_local_brt_then_converted(self):
        dt = _to_utc_aware("2026-03-01 08:15:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.isoformat(), "2026-03-01T11:15:00+00:00")

    def test_status_deleted_and_closed_are_ignored(self):
        self.assertIsNone(_status_do_sistema("DELETED"))
        self.assertIsNone(_status_do_sistema("CLOSED"))
        self.assertEqual(_status_do_sistema("ARRIVAL_SCHEDULED"), "arrival_scheduled")


if __name__ == "__main__":
    unittest.main()
