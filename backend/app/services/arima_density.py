"""Forecast aircraft density in fixed time buckets with ARIMA."""
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from math import isfinite
import warnings

import h3
from geoalchemy2 import Geometry
from numpy.linalg import LinAlgError
from sqlalchemy import cast, func
from sqlalchemy.orm import Session

from ..models import AircraftPosition


def _bucket_time(dt: datetime, interval_minutes: int) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    interval_seconds = interval_minutes * 60
    timestamp = int(dt.timestamp())
    bucket_timestamp = timestamp - (timestamp % interval_seconds)
    return datetime.fromtimestamp(bucket_timestamp, tz=timezone.utc)


def _moving_average_forecast(values: list[int], steps: int) -> list[float]:
    if not values:
        return [0.0] * steps
    window = values[-min(3, len(values)):]
    average = sum(window) / len(window)
    return [round(average, 2)] * steps


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    try:
        values = tuple(float(value.strip()) for value in bbox.split(','))
    except ValueError as exc:
        raise ValueError('bbox must be min_lon,min_lat,max_lon,max_lat') from exc
    if len(values) != 4 or not all(isfinite(value) for value in values):
        raise ValueError('bbox must be min_lon,min_lat,max_lon,max_lat')
    min_lon, min_lat, max_lon, max_lat = values
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ValueError('bbox coordinates or ordering are invalid')
    return min_lon, min_lat, max_lon, max_lat


def _arima_or_fallback(values: list[int], steps: int, order: tuple[int, int, int]):
    minimum_points = max(8, sum(order) + 3)
    if len(values) < minimum_points or len(set(values)) < 2:
        return _moving_average_forecast(values, steps), 'MOVING_AVERAGE', 'fallback'
    try:
        from statsmodels.tsa.arima.model import ARIMA
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            fitted = ARIMA(values, order=order).fit()
            predictions: Sequence[float] = fitted.forecast(steps=steps)
        forecast = [round(max(0.0, float(value)), 2) if isfinite(float(value)) else 0.0 for value in predictions]
        return forecast, 'ARIMA', 'ok'
    except (ValueError, TypeError, ArithmeticError, RuntimeError, LinAlgError):
        return _moving_average_forecast(values, steps), 'MOVING_AVERAGE', 'fallback'


def forecast_density(
    db: Session,
    h3_cell_id: str | None = None,
    bbox: str | None = None,
    hours: int = 24,
    interval_minutes: int = 15,
    steps: int = 8,
    order: tuple[int, int, int] = (1, 1, 1),
) -> dict:
    """Forecast distinct aircraft per completed interval for an optional area."""
    if h3_cell_id and bbox:
        raise ValueError('Choose either h3_cell_id or bbox, not both')
    if h3_cell_id and not h3.is_valid_cell(h3_cell_id):
        raise ValueError('h3_cell_id is not a valid H3 cell')
    bounds = _parse_bbox(bbox)
    if len(order) != 3 or any(isinstance(value, bool) or not isinstance(value, int) for value in order):
        raise ValueError('ARIMA order must contain three integers')

    interval = timedelta(minutes=interval_minutes)
    end_bucket = _bucket_time(datetime.now(timezone.utc), interval_minutes)
    start_bucket = _bucket_time(end_bucket - timedelta(hours=hours), interval_minutes)
    interval_seconds = interval_minutes * 60
    epoch = func.extract('epoch', AircraftPosition.created_at)
    bucket = func.to_timestamp(func.floor(epoch / interval_seconds) * interval_seconds)
    query = db.query(
        bucket.label('bucket'),
        func.count(func.distinct(AircraftPosition.aircraft_id)).label('aircraft_count'),
    ).filter(
        AircraftPosition.created_at >= start_bucket,
        AircraftPosition.created_at < end_bucket,
    )
    if h3_cell_id:
        query = query.filter(AircraftPosition.h3_cell_id == h3_cell_id)
    if bounds:
        geometry = cast(AircraftPosition.position, Geometry('POINT', srid=4326))
        query = query.filter(func.ST_Intersects(geometry, func.ST_MakeEnvelope(*bounds, 4326)))
    rows = query.group_by(bucket).order_by(bucket).all()

    counts = {}
    for row in rows:
        time = row.bucket
        if time.tzinfo is None:
            time = time.replace(tzinfo=timezone.utc)
        counts[_bucket_time(time, interval_minutes)] = int(row.aircraft_count)

    history = []
    cursor = start_bucket
    while cursor < end_bucket:
        history.append({'time': cursor.isoformat(), 'aircraft_count': counts.get(cursor, 0)})
        cursor += interval
    values = [item['aircraft_count'] for item in history]
    predictions, model, status = _arima_or_fallback(values, steps, order)
    forecast = [
        {
            'time': (end_bucket + interval * index).isoformat(),
            'predicted_aircraft_count': prediction,
        }
        for index, prediction in enumerate(predictions)
    ]
    scope = {'h3_cell_id': h3_cell_id, 'bbox': list(bounds) if bounds else None}
    if model == 'ARIMA':
        message = 'Traffic density forecast generated with ARIMA.'
    else:
        message = 'Not enough varied history for ARIMA; using a three-interval moving average.'
    return {
        'model': model,
        'status': status,
        'message': message,
        'order': list(order),
        'interval_minutes': interval_minutes,
        'scope': scope,
        'history': history,
        'forecast': forecast,
    }
