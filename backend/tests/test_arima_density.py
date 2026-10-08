import unittest
from datetime import datetime, timezone

from app.services.arima_density import (
    _bucket_time,
    _moving_average_forecast,
    _parse_bbox,
    _arima_or_fallback,
    _h3_polygon_wkt,
)


class ArimaDensityTests(unittest.TestCase):
    def test_buckets_time_to_requested_interval(self):
        value = datetime(2026, 10, 8, 8, 29, 59, tzinfo=timezone.utc)
        self.assertEqual(_bucket_time(value, 15).isoformat(), '2026-10-08T08:15:00+00:00')

    def test_moving_average_uses_last_three_intervals(self):
        self.assertEqual(_moving_average_forecast([2, 4, 8, 10], 2), [7.33, 7.33])
        self.assertEqual(_moving_average_forecast([], 2), [0.0, 0.0])

    def test_sparse_or_constant_history_uses_fallback(self):
        predictions, model, status = _arima_or_fallback([1, 2, 3], 2, (1, 1, 1))
        self.assertEqual(predictions, [2.0, 2.0])
        self.assertEqual(model, 'MOVING_AVERAGE')
        self.assertEqual(status, 'fallback')

    def test_varied_history_uses_arima(self):
        values = [10, 12, 11, 15, 14, 18, 17, 21, 19, 23, 22, 25]
        predictions, model, status = _arima_or_fallback(values, 3, (1, 1, 1))
        self.assertEqual(model, 'ARIMA')
        self.assertEqual(status, 'ok')
        self.assertEqual(len(predictions), 3)
        self.assertTrue(all(value >= 0 for value in predictions))

    def test_bbox_validation(self):
        self.assertEqual(_parse_bbox('70,20,90,35'), (70.0, 20.0, 90.0, 35.0))
        with self.assertRaisesRegex(ValueError, 'ordering'):
            _parse_bbox('90,20,70,35')

    def test_h3_cell_converts_to_spatial_polygon(self):
        polygon = _h3_polygon_wkt('872830828ffffff')
        self.assertTrue(polygon.startswith('POLYGON(('))
        self.assertTrue(polygon.endswith('))'))
        coordinates = polygon.removeprefix('POLYGON((').removesuffix('))').split(',')
        self.assertEqual(coordinates[0], coordinates[-1])


if __name__ == '__main__':
    unittest.main()
