import unittest
from datetime import datetime

from api.dashboard import _status_pode_ficar_em_atraso
from api.painel import _deadline_sla_por_expected, _to_aware_utc


class _CargaFake:
    def __init__(self, expected_arrival_date):
        self.expected_arrival_date = expected_arrival_date
        self.arrived_at = None


class SlaTimezoneLogicTests(unittest.TestCase):
    def test_naive_datetime_from_db_is_interpreted_as_utc(self):
        dt = datetime(2026, 3, 5, 19, 0, 0)  # 16:00 BRT armazenado como 19:00 UTC
        aware = _to_aware_utc(dt)
        self.assertIsNotNone(aware)
        self.assertEqual(aware.isoformat(), "2026-03-05T19:00:00+00:00")

    def test_deadline_stays_4h_after_expected(self):
        carga = _CargaFake(datetime(2026, 3, 5, 19, 0, 0))
        deadline = _deadline_sla_por_expected(carga)
        self.assertIsNotNone(deadline)
        self.assertEqual(deadline.isoformat(), "2026-03-05T23:00:00+00:00")  # 20:00 BRT

    def test_no_show_does_not_stay_in_overdue_list(self):
        self.assertFalse(_status_pode_ficar_em_atraso("no_show"))

    def test_active_statuses_can_stay_in_overdue_list(self):
        self.assertTrue(_status_pode_ficar_em_atraso("arrival_scheduled"))
        self.assertTrue(_status_pode_ficar_em_atraso("arrival"))
        self.assertTrue(_status_pode_ficar_em_atraso("checkin"))
        self.assertTrue(_status_pode_ficar_em_atraso("closed"))


if __name__ == "__main__":
    unittest.main()
