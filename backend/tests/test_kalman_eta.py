import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.models import Aircraft
from app.services.kalman_eta import estimate_eta, eta_confidence_score


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
    def test_confidence_score_levels_and_unavailable_eta(self):
        high = eta_confidence_score(430, 12, 75.4, 600)
        medium = eta_confidence_score(4000, 5, 20, 1200)
        unavailable = eta_confidence_score(100, 12, None, None)

        self.assertEqual(high['level'], 'HIGH')
        self.assertEqual(high['score'], 93)
        self.assertEqual(medium['level'], 'MEDIUM')
        self.assertEqual(unavailable['score'], 0)
        self.assertEqual(unavailable['level'], 'LOW')

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
        self.assertGreater(result['eta_confidence']['score'], 0)

    @patch('app.services.kalman_eta.to_shape', side_effect=lambda point: point)
    @patch('app.services.kalman_eta.aircraft_sessions')
    def test_withholds_eta_when_moving_away(self, sessions, _):
        sessions.return_value = [self.positions(east=False)]
        db = Database(SimpleNamespace(id=1, icao24='abc123', call_sign='TEST1'))
        result = estimate_eta(db, 'abc123', 0.0, 1.0)
        self.assertEqual(result['status'], 'not_approaching')
        self.assertIsNone(result['eta'])
        self.assertEqual(result['eta_confidence']['score'], 0)
        self.assertEqual(result['eta_confidence']['level'], 'LOW')

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
