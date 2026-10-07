import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.models import Aircraft
from app.services.kalman_eta import estimate_eta


class Query:
    def __init__(self, result):
        self.result = result
    def filter(self, *args):
        return self
    def order_by(self, *args):
        return self
    def first(self):
        return self.result
    def all(self):
        return self.result


class Database:
    def __init__(self, aircraft):
        self.aircraft = aircraft
    def query(self, model):
        return Query(self.aircraft)


class KalmanEtaTests(unittest.TestCase):
    def positions(self, east=True):
        start = datetime.now(timezone.utc) - timedelta(minutes=3)
        direction = 1 if east else -1
        return [SimpleNamespace(
            id=index + 1,
            created_at=start + timedelta(minutes=index),
            position=SimpleNamespace(x=direction * index * 0.1, y=0.0),
        ) for index in range(4)]

    @patch('app.services.kalman_eta.to_shape', side_effect=lambda point: point)
    @patch('app.services.kalman_eta.aircraft_sessions')
    def test_estimates_eta_when_closing_on_destination(self, sessions, _):
        sessions.return_value = [self.positions()]
        db = Database(SimpleNamespace(id=1, icao24='abc123', call_sign='TEST1'))
        result = estimate_eta(db, 'abc123', 0.0, 1.0)
        self.assertEqual(result['status'], 'approaching')
        self.assertIsNotNone(result['eta'])
        self.assertGreater(result['filtered_speed_mps'], 0)
        self.assertEqual(result['observations'], 4)

    @patch('app.services.kalman_eta.to_shape', side_effect=lambda point: point)
    @patch('app.services.kalman_eta.aircraft_sessions')
    def test_withholds_eta_when_moving_away(self, sessions, _):
        sessions.return_value = [self.positions(east=False)]
        db = Database(SimpleNamespace(id=1, icao24='abc123', call_sign='TEST1'))
        result = estimate_eta(db, 'abc123', 0.0, 1.0)
        self.assertEqual(result['status'], 'not_approaching')
        self.assertIsNone(result['eta'])

    @patch('app.services.kalman_eta.to_shape', side_effect=lambda point: point)
    @patch('app.services.kalman_eta.aircraft_sessions')
    def test_requires_two_distinct_positions(self, sessions, _):
        position = self.positions()[0]
        sessions.return_value = [[position]]
        db = Database(SimpleNamespace(id=1, icao24='abc123', call_sign='TEST1'))
        with self.assertRaisesRegex(ValueError, 'At least two'):
            estimate_eta(db, 'abc123', 0.0, 1.0)


if __name__ == '__main__':
    unittest.main()
